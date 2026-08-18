"""Versioned direct-horizon training, validation, and atomic model promotion."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from config.settings import get_settings
from src.candle_data_service import CandleDataService
from src.candle_features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, HORIZONS, build_horizon_dataset
from src.session_builder import build_sessions, persist_sessions
from src.baselines import should_promote
from src.walk_forward import WalkForwardValidator
from src.database import WalkForwardResult

BUNDLE_VERSION = "trained_horizon_bundle_v1"
TARGET_DEFINITION = "(close_at_exact_t_plus_h - close_at_t) / close_at_t"
DIRECTION_THRESHOLD = 0.0005
LOCK_ID = 476_655_018


class CandidateRejectedError(Exception):
    """Valid candidate bundle that did not satisfy the promotion policy."""

    def __init__(self, reasons, metrics=None, candidate_path=None):
        self.reasons = list(reasons)
        self.metrics = metrics or {}
        self.candidate_path = str(candidate_path) if candidate_path else None
        horizons = ", ".join(f"{reason.get('horizon')}m" for reason in self.reasons)
        super().__init__(f"Candidate rejected by the all-horizons promotion policy ({horizons})")


def _utc(value):
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _smape(actual, predicted) -> float:
    denominator = np.abs(actual) + np.abs(predicted)
    values = np.zeros_like(denominator, dtype=float)
    np.divide(2 * np.abs(predicted - actual), denominator, out=values, where=denominator != 0)
    return float(np.mean(values) * 100)


def _direction(values):
    return np.where(values > DIRECTION_THRESHOLD, 1, np.where(values < -DIRECTION_THRESHOLD, -1, 0))


def regression_metrics(actual, predicted, current_returns=None, common_direction=0) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    zero = np.zeros_like(actual)
    model_mae = mean_absolute_error(actual, predicted)
    model_rmse = mean_squared_error(actual, predicted) ** 0.5
    baseline_mae = mean_absolute_error(actual, zero)
    baseline_rmse = mean_squared_error(actual, zero) ** 0.5
    return {
        "mae": float(model_mae), "rmse": float(model_rmse), "smape": _smape(actual, predicted),
        "r2": float(r2_score(actual, predicted)),
        "directional_accuracy": float(np.mean(_direction(actual) == _direction(predicted)) * 100),
        "persistence_mae": float(baseline_mae), "persistence_rmse": float(baseline_rmse),
        "zero_return_mae": float(baseline_mae), "zero_return_rmse": float(baseline_rmse),
        "common_direction_accuracy": float(np.mean(_direction(actual) == common_direction) * 100),
        "mae_improvement_over_persistence": float(baseline_mae - model_mae),
        "rmse_improvement_over_persistence": float(baseline_rmse - model_rmse),
    }


def chronological_split(dataset: pd.DataFrame, train_ratio=.70, validation_ratio=.15, purge_minutes=240):
    if not 0 < train_ratio < 1 or not 0 < validation_ratio < 1 or train_ratio + validation_ratio >= 1:
        raise ValueError("Training/validation/test ratios must be positive and sum to one")
    data = dataset.sort_values("Date").reset_index(drop=True)
    train_cut = data.iloc[max(0, int(len(data) * train_ratio) - 1)]["Date"]
    validation_cut = data.iloc[max(0, int(len(data) * (train_ratio + validation_ratio)) - 1)]["Date"]
    embargo = pd.Timedelta(minutes=purge_minutes)
    train = data[(data["Date"] <= train_cut) & (data["target_time"] <= train_cut)].copy()
    validation = data[(data["Date"] > train_cut + embargo) & (data["Date"] <= validation_cut) & (data["target_time"] <= validation_cut)].copy()
    test = data[data["Date"] > validation_cut + embargo].copy()
    return train, validation, test


@contextmanager
def training_lock(session):
    if session.bind.dialect.name == "postgresql":
        acquired = bool(session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_ID}).scalar())
        if not acquired:
            raise RuntimeError("Another training or promotion job holds the project advisory lock")
        try:
            yield
        finally:
            session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID})
    else:
        yield


class ModelBundleManager:
    def __init__(self, model_dir: str | Path | None = None):
        self.root = Path(model_dir or get_settings().ml.model_dir)
        self.candidates = self.root / "candidates"
        self.production = self.root / "production"
        self.candidates.mkdir(parents=True, exist_ok=True)
        self.production.mkdir(parents=True, exist_ok=True)

    @property
    def production_manifest_path(self):
        return self.production / "manifest.json"

    def load_manifest(self, path: Path | None = None) -> dict[str, Any]:
        manifest_path = path or self.production_manifest_path
        if not manifest_path.exists():
            raise FileNotFoundError("No approved trained model is currently available. Run initial training and pass promotion checks.")
        return json.loads(manifest_path.read_text())

    def validate(self, manifest_path: Path) -> dict[str, Any]:
        manifest = self.load_manifest(manifest_path)
        if manifest.get("bundle_version") != BUNDLE_VERSION:
            raise ValueError("Unsupported model bundle version")
        if manifest.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            raise ValueError("Feature schema version mismatch")
        if manifest.get("feature_names") != FEATURE_COLUMNS:
            raise ValueError("Ordered feature names mismatch")
        if manifest.get("library_versions", {}).get("scikit_learn") != sklearn.__version__:
            raise ValueError("Scikit-learn version mismatch")
        bundle = manifest_path.parent
        for horizon in HORIZONS:
            item = manifest["horizons"].get(str(horizon))
            if not item or item.get("horizon") != horizon:
                raise ValueError(f"Missing or wrong horizon artifact: {horizon}")
            for field in ("model_file", "scaler_file"):
                path = bundle / item[field]
                if not path.exists() or _hash(path) != item["checksums"][field]:
                    raise ValueError(f"Artifact checksum mismatch: {path}")
            model = joblib.load(bundle / item["model_file"])
            scaler = joblib.load(bundle / item["scaler_file"])
            if getattr(model, "n_features_in_", None) != len(FEATURE_COLUMNS):
                raise ValueError(f"Model feature count mismatch for {horizon}m")
            if getattr(scaler, "n_features_in_", None) != len(FEATURE_COLUMNS):
                raise ValueError(f"Scaler feature count mismatch for {horizon}m")
        return manifest

    def load_horizon(self, horizon: int):
        manifest = self.validate(self.production_manifest_path)
        item = manifest["horizons"][str(horizon)]
        return manifest, joblib.load(self.production / item["model_file"]), joblib.load(self.production / item["scaler_file"])

    def promote(self, candidate_manifest: Path, initial=False) -> dict[str, Any]:
        candidate = self.validate(candidate_manifest)
        policy = get_settings().ml
        if self.production_manifest_path.exists() and initial:
            raise RuntimeError("Initial training refused: an approved production bundle already exists")
        reasons = []
        if self.production_manifest_path.exists() and not initial:
            current = self.load_manifest()
            tolerance = get_settings().ml.promotion_regression_tolerance
            for horizon in HORIZONS:
                new = candidate["horizons"][str(horizon)]["metrics"]["test"]["mae"]
                old = current["horizons"][str(horizon)]["metrics"]["test"]["mae"]
                if new > old * (1 + tolerance):
                    reasons.append({
                        "criterion": "production_regression", "horizon": horizon,
                        "candidate_mae": new, "production_mae": old,
                        "absolute_difference": new-old,
                        "percentage_degradation": ((new-old)/old*100) if old else None,
                        "test_sample_count": candidate["horizons"][str(horizon)]["split_counts"]["test"],
                    })
        for horizon in HORIZONS:
            horizon_item = candidate["horizons"][str(horizon)]
            metrics = horizon_item["metrics"]["test"]
            samples = horizon_item["split_counts"]["test"]
            walk_forward = horizon_item.get("walk_forward_validation", {})
            stability = walk_forward.get("stability", {})
            folds = walk_forward.get("folds", [])
            common = {
                "horizon": horizon, "candidate_mae": metrics.get("mae"),
                "candidate_rmse": metrics.get("rmse"),
                "persistence_mae": metrics.get("persistence_mae"),
                "persistence_rmse": metrics.get("persistence_rmse"),
                "test_sample_count": samples,
                "candidate_directional_accuracy": metrics.get("directional_accuracy"),
                "baseline_directional_accuracy": metrics.get("common_direction_accuracy"),
                "walk_forward_fold_count": len(folds),
                "walk_forward_stability": stability,
            }
            if samples < get_settings().ml.minimum_test_samples:
                reasons.append({**common, "criterion": "insufficient_test_samples"})
            if not all(np.isfinite(metrics[k]) for k in ("mae", "rmse", "smape", "directional_accuracy")):
                reasons.append({**common, "criterion": "non_finite_metrics"})
            accepted, gate_reason = should_promote(
                {"n_samples": samples, "mae": metrics["mae"],
                 "directional_accuracy": metrics["directional_accuracy"] / 100},
                {"mae": metrics["persistence_mae"]},
                threshold=policy.promotion_minimum_mae_improvement,
                stable=(bool(stability.get("stable")) and len(folds) >= policy.walk_forward_minimum_folds),
            )
            if not accepted:
                difference = metrics["mae"] - metrics["persistence_mae"]
                reasons.append({
                    **common, "criterion": "promotion_gate_failed", "gate_reason": gate_reason,
                    "absolute_difference": difference,
                    "percentage_improvement": (
                        (metrics["persistence_mae"]-metrics["mae"])/metrics["persistence_mae"]*100
                        if metrics["persistence_mae"] else None
                    ),
                })
        if reasons:
            raise CandidateRejectedError(
                reasons=reasons,
                metrics={h: item["metrics"]["test"] for h, item in candidate["horizons"].items()},
                candidate_path=candidate_manifest.parent,
            )
        version_dir = candidate_manifest.parent
        staging = Path(tempfile.mkdtemp(prefix="production-", dir=self.root))
        try:
            for source in version_dir.iterdir():
                if source.is_file():
                    shutil.copy2(source, staging / source.name)
            self.validate(staging / "manifest.json")
            previous = self.root / "previous_production"
            if self.production.exists() and any(self.production.iterdir()):
                if previous.exists():
                    shutil.rmtree(previous)
                os.replace(self.production, previous)
            os.replace(staging, self.production)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return candidate


class MultiHorizonTrainer:
    def __init__(self, session, manager: ModelBundleManager | None = None):
        self.session = session
        self.settings = get_settings().ml
        self.manager = manager or ModelBundleManager()

    def _model(self, algorithm):
        if algorithm == "linear_regression":
            return LinearRegression()
        if algorithm == "ridge_regression":
            return Ridge(alpha=1.0)
        if algorithm == "random_forest":
            return RandomForestRegressor(n_estimators=100, max_depth=14, random_state=42, n_jobs=-1)
        if algorithm == "xgboost":
            from xgboost import XGBRegressor
            return XGBRegressor(n_estimators=200, max_depth=5, learning_rate=.05, random_state=42, n_jobs=-1)
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    def _walk_forward(self, dataset, algorithm):
        validator = WalkForwardValidator(dataset, int(dataset.horizon_minutes.iloc[0]), {
            "train_years": self.settings.walk_forward_train_years,
            "test_months": self.settings.walk_forward_test_months,
            "step_months": self.settings.walk_forward_step_months,
        })
        results = validator.validate(lambda: self._model(algorithm))
        return {
            "folds": results.to_dict("records"),
            "stability": validator.assess_stability(results),
        }

    def train_candidate(self, algorithm="linear_regression") -> Path:
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + algorithm
        target = self.manager.candidates / version
        target.mkdir(parents=True, exist_ok=False)
        candles = CandleDataService(self.session).completed_1m(limit=self.settings.training_max_candles)
        from src.candle_features import candles_to_frame
        frame = candles_to_frame(candles)
        sessions = build_sessions(frame)
        new_session_rows = persist_sessions(self.session, sessions, provider="histdata", symbol="XAUUSD")
        self.session.commit()
        manifest: dict[str, Any] = {
            "bundle_version": BUNDLE_VERSION, "model_version": version, "algorithm": algorithm,
            "feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_names": FEATURE_COLUMNS,
            "target_definition": TARGET_DEFINITION, "created_at": datetime.now(timezone.utc).isoformat(),
            "training_data": {"provider": "histdata", "symbol": "XAUUSD", "timeframe": "1m",
                              "minimum_time": _utc(frame.Date.min()).isoformat(), "maximum_time": _utc(frame.Date.max()).isoformat(),
                              "loaded_rows": len(frame), "gap_policy": "exact target and continuous 30-candle feature session",
                              "trading_session_gap_threshold_minutes": 5,
                              "trading_session_count": len(sessions),
                              "new_trading_session_rows": new_session_rows},
            "split_policy": {"train": self.settings.training_ratio, "validation": self.settings.validation_ratio,
                             "test": self.settings.test_ratio, "purge_minutes": max(HORIZONS)},
            "library_versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                                 "numpy": np.__version__, "pandas": pd.__version__}, "horizons": {},
        }
        for horizon in HORIZONS:
            dataset = build_horizon_dataset(frame, horizon)
            train, validation, test = chronological_split(dataset, self.settings.training_ratio, self.settings.validation_ratio)
            if min(len(train), len(validation), len(test)) == 0:
                raise RuntimeError(f"Insufficient split data for {horizon}m")
            scaler = StandardScaler().fit(train[FEATURE_COLUMNS])
            algorithms = [algorithm]
            if algorithm == "benchmark":
                algorithms = [name.strip() for name in self.settings.candidate_algorithms.split(",") if name.strip()]
            benchmark_metrics = {}
            models = {}
            for candidate_algorithm in algorithms:
                candidate_model = self._model(candidate_algorithm)
                candidate_model.fit(scaler.transform(train[FEATURE_COLUMNS]), train["target_return"])
                validation_prediction = candidate_model.predict(scaler.transform(validation[FEATURE_COLUMNS]))
                common = int(pd.Series(_direction(train["target_return"])).mode().iloc[0])
                benchmark_metrics[candidate_algorithm] = regression_metrics(
                    validation["target_return"], validation_prediction, common_direction=common,
                )
                models[candidate_algorithm] = candidate_model
            selected_algorithm = min(algorithms, key=lambda name: benchmark_metrics[name]["mae"])
            model = models[selected_algorithm]
            model.fit(scaler.transform(train[FEATURE_COLUMNS]), train["target_return"])
            common_direction = int(pd.Series(_direction(train["target_return"])).mode().iloc[0])
            metrics = {}
            for name, split in (("train", train), ("validation", validation), ("test", test)):
                predicted = model.predict(scaler.transform(split[FEATURE_COLUMNS]))
                metrics[name] = regression_metrics(split["target_return"], predicted, common_direction=common_direction)
            model_file, scaler_file = f"model_{horizon}m.joblib", f"scaler_{horizon}m.joblib"
            joblib.dump(model, target / model_file)
            joblib.dump(scaler, target / scaler_file)
            manifest["horizons"][str(horizon)] = {
                "horizon": horizon, "model_file": model_file, "scaler_file": scaler_file,
                "algorithm": selected_algorithm,
                "hyperparameters": model.get_params(), "common_training_direction": common_direction,
                "split_counts": {"train": len(train), "validation": len(validation), "test": len(test)},
                "split_ranges": {name: {"minimum": _utc(split.Date.min()).isoformat(), "maximum": _utc(split.Date.max()).isoformat()}
                                 for name, split in (("train", train), ("validation", validation), ("test", test))},
                "metrics": metrics, "candidate_validation_metrics": benchmark_metrics,
                "selection_policy": "lowest chronological validation MAE; final test used only after selection",
                "walk_forward_validation": self._walk_forward(dataset, selected_algorithm),
                "dataset_diagnostics": dict(dataset.attrs.get("diagnostics", {})),
                "checksums": {},
            }
            item = manifest["horizons"][str(horizon)]
            item["checksums"] = {"model_file": _hash(target/model_file), "scaler_file": _hash(target/scaler_file)}
        manifest_path = target / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n")
        self.manager.validate(manifest_path)
        for horizon, item in manifest["horizons"].items():
            for fold in item["walk_forward_validation"]["folds"]:
                def naive_utc(value):
                    return _utc(value).to_pydatetime().replace(tzinfo=None)
                self.session.add(WalkForwardResult(
                    model_name=item["algorithm"], model_version=version,
                    horizon_minutes=int(horizon), fold_id=int(fold["fold_id"]),
                    train_start=naive_utc(fold["train_start"]), train_end=naive_utc(fold["train_end"]),
                    test_start=naive_utc(fold["test_start"]), test_end=naive_utc(fold["test_end"]),
                    train_rows=int(fold["train_rows"]), test_rows=int(fold["test_rows"]),
                    mae=float(fold["mae"]), rmse=float(fold["rmse"]),
                    directional_accuracy=float(fold["directional_accuracy"]),
                    persistence_mae=float(fold["persistence_mae"]),
                    mae_improvement_pct=float(fold["mae_improvement_pct"]),
                    market_regime=fold["market_regime"],
                ))
        self.session.commit()
        return manifest_path
