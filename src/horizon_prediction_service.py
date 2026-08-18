"""Approved trained multi-horizon inference and bounded outcome evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from config.settings import get_settings
from src.candle_data_service import CandleDataService
from src.candle_features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, HORIZONS as APPROVED_HORIZONS, latest_continuous_features
from src.database import HorizonPrediction, Price, get_session, init_db, latest_valid_live_price
from src.market_session import candle_context, is_expected_market_closure
from src.model_pipeline import BUNDLE_VERSION, DIRECTION_THRESHOLD, ModelBundleManager

HORIZONS = {
    3: "Ultra-short term", 5: "Very short term", 15: "Short term",
    30: "Medium-short term", 60: "Medium term", 240: "Long-short term",
}
EVALUATOR_VERSION = "bounded_live_quote_v1"
DIRECTION_POLICY_VERSION = "direction_0.0005_v1"


def aware_utc(value: datetime) -> datetime:
    # PostgreSQL is aware; SQLite test fixtures can lose the offset on read.
    # Provider inputs are rejected before persistence by strict parsing/save.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def direction_for_return(value: float, threshold: float = DIRECTION_THRESHOLD) -> str:
    return "up" if value > threshold else "down" if value < -threshold else "stable"


def trend_for(start: float, end: float, stable_pct: float = 0.05) -> str:
    """Legacy-compatible wrapper; stable_pct is expressed as a percentage."""
    return direction_for_return((end - start) / start if start else 0, stable_pct / 100)


class PredictionUnavailable(RuntimeError):
    pass


class HorizonPredictionService:
    """Generate only approved artifact predictions and resolve them within tolerance."""

    def __init__(self, bundle_manager: ModelBundleManager | None = None):
        init_db()
        self.bundle_manager = bundle_manager or ModelBundleManager()
        self.last_unavailable_reason: Optional[str] = None

    @staticmethod
    def _latest_live_price(session) -> Optional[Price]:
        return latest_valid_live_price(session)

    def _validated_inputs(self, session):
        settings = get_settings().streaming
        now = datetime.now(timezone.utc)
        if is_expected_market_closure(now):
            raise PredictionUnavailable("Market is closed; production prediction is unavailable")
        live = self._latest_live_price(session)
        if live is None:
            raise PredictionUnavailable("No live reference price is available")
        live_time = aware_utc(live.timestamp)
        age = (now - live_time).total_seconds()
        if age < -settings.live_clock_skew_seconds:
            raise PredictionUnavailable("Latest live price is future-dated")
        if age > settings.maximum_live_price_age_seconds:
            raise PredictionUnavailable("Latest live price is stale")
        frame, continuity = CandleDataService(session).inference_frame(limit=300)
        latest, reason = latest_continuous_features(frame)
        if reason:
            raise PredictionUnavailable(reason)
        candle_time = aware_utc(pd.Timestamp(latest.iloc[-1]["Date"]).to_pydatetime())
        candle_status, candle_detail, eligible = candle_context(
            candle_time, now, settings.completed_candle_freshness_seconds
        )
        if not eligible:
            raise PredictionUnavailable(f"{candle_status}: {candle_detail}")
        return now, live, live_time, candle_time, latest, continuity

    def generate(self, session=None) -> List[HorizonPrediction]:
        owns_session = session is None
        session = session or get_session()
        try:
            try:
                now, live, live_time, candle_time, features, continuity = self._validated_inputs(session)
                manager = getattr(self, "bundle_manager", ModelBundleManager())
                self.bundle_manager = manager
                manifest = manager.validate(manager.production_manifest_path)
            except (PredictionUnavailable, FileNotFoundError, ValueError) as exc:
                self.last_unavailable_reason = str(exc)
                return []
            reference = Decimal(str(live.price_usd))
            batch_id = str(uuid4())
            rows: list[HorizonPrediction] = []
            configured = {
                int(value.strip()) for value in get_settings().streaming.prediction_horizons.split(",")
                if value.strip()
            }
            invalid = configured.difference(APPROVED_HORIZONS)
            if invalid:
                raise PredictionUnavailable(f"Unsupported configured horizons: {sorted(invalid)}")
            for horizon in APPROVED_HORIZONS:
                if horizon not in configured:
                    continue
                item = manifest["horizons"][str(horizon)]
                _, model, scaler = self.bundle_manager.load_horizon(horizon)
                inputs = features[FEATURE_COLUMNS]
                predicted_return = Decimal(str(float(model.predict(scaler.transform(inputs))[0])))
                predicted_price = reference * (Decimal("1") + predicted_return)
                if predicted_price <= 0:
                    raise PredictionUnavailable(f"{horizon}m model produced a non-positive price")
                residual = Decimal(str(item["metrics"]["test"]["rmse"]))
                interval = reference * residual * Decimal("1.96")
                row = HorizonPrediction(
                    batch_id=batch_id, symbol="XAUUSD", timeframe="1m", provider=live.provider,
                    algorithm_name="trained_multi_horizon", algorithm_version=BUNDLE_VERSION,
                    model_name=item.get("algorithm", manifest["algorithm"]), model_version=manifest["model_version"],
                    feature_schema_version=FEATURE_SCHEMA_VERSION,
                    prediction_created_at=now, created_at=now, feature_data_until=candle_time,
                    target_at=now + timedelta(minutes=horizon), horizon_minutes=horizon,
                    horizon_label=HORIZONS[horizon], current_price=float(reference), reference_price=reference,
                    predicted_price=predicted_price, predicted_return=predicted_return,
                    baseline_price=reference, lower_bound=max(Decimal("0.000001"), predicted_price-interval),
                    upper_bound=predicted_price+interval, interval_method="test_rmse_normal_v1",
                    confidence=None, predicted_trend=direction_for_return(float(predicted_return)),
                    status="PENDING", latest_live_price_at=live_time,
                    last_completed_candle_at=candle_time,
                    missing_period_count=len(continuity.missing_periods),
                    actual_tolerance_seconds=get_settings().streaming.prediction_actual_tolerance_seconds,
                    retry_count=0, direction_threshold=Decimal(str(DIRECTION_THRESHOLD)),
                    direction_policy_version=DIRECTION_POLICY_VERSION,
                    context={"feature_names": FEATURE_COLUMNS, "bundle_version": BUNDLE_VERSION},
                )
                session.add(row)
                rows.append(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                self.last_unavailable_reason = "Production predictions already exist for this feature cutoff"
                return []
            return rows
        finally:
            if owns_session:
                session.close()

    def evaluate_due(self, session=None, now: datetime | None = None) -> int:
        owns_session = session is None
        session = session or get_session()
        try:
            from src.prediction_evaluator import PredictionEvaluator
            return PredictionEvaluator(
                tolerance_seconds=get_settings().streaming.prediction_actual_tolerance_seconds,
            ).evaluate_due(session, now)
        finally:
            if owns_session:
                session.close()

    def performance_summary(self, session=None):
        owns_session = session is None
        session = session or get_session()
        try:
            result = {}
            for minutes in APPROVED_HORIZONS:
                rows = session.query(HorizonPrediction).filter(
                    HorizonPrediction.horizon_minutes == minutes,
                    HorizonPrediction.status == "EVALUATED",
                    HorizonPrediction.algorithm_name == "trained_multi_horizon",
                ).all()
                if not rows:
                    result[minutes] = {"count": 0}
                    continue
                errors = np.array([float(r.absolute_error) for r in rows])
                actual = np.array([float(r.actual_price) for r in rows])
                predicted = np.array([float(r.predicted_price) for r in rows])
                smape = np.mean(2*errors/(np.abs(actual)+np.abs(predicted))*100)
                result[minutes] = {
                    "count": len(rows), "mae": float(errors.mean()),
                    "rmse": float(np.sqrt(np.mean(errors ** 2))), "smape": float(smape),
                    "directional_accuracy": float(np.mean([bool(r.direction_correct) for r in rows])*100),
                    "baseline_mae": float(np.mean([float(r.baseline_absolute_error) for r in rows])),
                }
            return result
        finally:
            if owns_session:
                session.close()
