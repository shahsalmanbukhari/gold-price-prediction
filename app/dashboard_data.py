"""Shared read-only dashboard queries. No method promotes, trains or predicts."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import func

from config.settings import get_settings
from src.background_lifecycle import HeartbeatService, WORKER_NAME
from src.database import (
    GoldPriceCandle, HistoricalDataImport, HorizonModelStatus, HorizonPrediction,
    NotificationDelivery, PredictionDecision, Price, ProviderStatus, RetrainingRun,
    ServiceHeartbeat, TrainingSchedulerState, get_session,
    latest_valid_live_price,
)

HORIZONS = (3, 5, 15, 30, 60, 240)


@dataclass(frozen=True)
class ModelOption:
    model_name: str
    model_version: str
    horizon: int
    status: str
    label: str

    @property
    def key(self): return f"{self.model_name}|{self.model_version}|{self.horizon}"


def _production_manifest():
    path = Path(get_settings().ml.model_dir) / "production" / "manifest.json"
    if not path.exists(): return None
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return None


def model_options(horizon):
    session = get_session()
    try:
        rows = session.query(
            HorizonPrediction.model_name, HorizonPrediction.model_version,
            HorizonPrediction.horizon_minutes, HorizonPrediction.algorithm_name,
        ).filter(HorizonPrediction.horizon_minutes == horizon).distinct().all()
        runs = {r.new_version: str(r.status).upper() for r in session.query(RetrainingRun).all() if r.new_version}
    finally: session.close()
    production = _production_manifest()
    production_version = production.get("model_version") if production else None
    options = {}
    for name, version, item_horizon, algorithm_name in rows:
        if algorithm_name == "adaptive_momentum_baseline": status = "BASELINE"
        elif algorithm_name.startswith("legacy") or str(version).startswith("legacy"): status = "LEGACY"
        elif version == production_version: status = "PRODUCTION"
        else: status = runs.get(version, "CANDIDATE")
        option = ModelOption(name, version, item_horizon, status, f"{name.replace('_',' ').title()} · {item_horizon}m · {version} · {status}")
        options[option.key] = option
    if production:
        item = production.get("horizons", {}).get(str(horizon))
        if item:
            name, version = item.get("algorithm", production.get("algorithm", "unknown")), production["model_version"]
            option = ModelOption(name, version, horizon, "PRODUCTION", f"{name.replace('_',' ').title()} · {horizon}m · {version} · PRODUCTION")
            options[option.key] = option
    candidates_root=Path(get_settings().ml.model_dir)/"candidates"
    for manifest_path in candidates_root.glob("*/manifest.json") if candidates_root.exists() else []:
        try: manifest=json.loads(manifest_path.read_text())
        except (OSError,ValueError): continue
        item=manifest.get("horizons",{}).get(str(horizon))
        if not item: continue
        version=manifest.get("model_version") or manifest_path.parent.name
        name=item.get("algorithm",manifest.get("algorithm","unknown"))
        status="PRODUCTION" if version==production_version else runs.get(version,"CANDIDATE")
        option=ModelOption(name,version,horizon,status,f"{name.replace('_',' ').title()} · {horizon}m · {version} · {status}")
        options[option.key]=option
    return sorted(options.values(), key=lambda x: (x.status != "PRODUCTION", x.label))


def latest_market():
    session = get_session()
    try:
        price = latest_valid_live_price(session)
        candle = session.query(GoldPriceCandle).filter_by(symbol="XAUUSD", timeframe="1m", provider="histdata").order_by(GoldPriceCandle.candle_time.desc()).first()
        heartbeat = session.get(ServiceHeartbeat, WORKER_NAME)
        return price, candle, heartbeat, HeartbeatService.health(heartbeat)
    finally: session.close()


def market_series(limit=360):
    """Recent valid live snapshots for the overview chart."""
    session = get_session()
    try:
        rows = session.query(Price).filter(Price.source == "live_api", Price.symbol == "XAUUSD").order_by(Price.timestamp.desc()).limit(limit).all()
        return pd.DataFrame([{"timestamp": r.timestamp, "actual_price": r.price_usd, "provider": r.provider} for r in reversed(rows)])
    finally:
        session.close()


def predictions(model_name, model_version, horizon, date_from, date_to, statuses=None):
    if not model_name or not model_version: return pd.DataFrame()
    session = get_session()
    try:
        query = session.query(HorizonPrediction).filter(
            HorizonPrediction.model_name == model_name,
            HorizonPrediction.model_version == model_version,
            HorizonPrediction.horizon_minutes == horizon,
            HorizonPrediction.prediction_created_at >= date_from,
            HorizonPrediction.prediction_created_at <= date_to,
        )
        if statuses: query = query.filter(HorizonPrediction.status.in_(statuses))
        rows = query.order_by(HorizonPrediction.prediction_created_at).all()
        return pd.DataFrame([{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in rows])
    finally: session.close()


def latest_forecasts(model_name, model_version, horizon, date_from, date_to):
    return predictions(model_name, model_version, horizon, date_from, date_to).tail(12)


def performance(frame):
    if frame is None or frame.empty: return {}
    evaluated = frame[frame.status == "EVALUATED"].copy()
    if evaluated.empty: return {"evaluated":0, "pending":int((frame.status=="PENDING").sum()), "unresolvable":int((frame.status=="UNRESOLVABLE").sum())}
    error = pd.to_numeric(evaluated.absolute_error, errors="coerce")
    baseline = pd.to_numeric(evaluated.baseline_absolute_error, errors="coerce")
    actual = pd.to_numeric(evaluated.actual_price, errors="coerce")
    predicted = pd.to_numeric(evaluated.predicted_price, errors="coerce")
    denominator = actual.abs()+predicted.abs()
    return {
        "evaluated":len(evaluated), "pending":int((frame.status=="PENDING").sum()),
        "unresolvable":int((frame.status=="UNRESOLVABLE").sum()),
        "mae":error.mean(), "rmse":float(np.sqrt(np.nanmean(error**2))),
        "smape":float(np.nanmean(2*error/denominator*100)),
        "directional_accuracy":pd.to_numeric(evaluated.direction_correct, errors="coerce").mean()*100,
        "baseline_mae":baseline.mean(), "improvement":baseline.mean()-error.mean(),
        "median_delay":pd.to_numeric(evaluated.evaluation_delay_seconds, errors="coerce").median(),
    }


def aligned_comparison(a_name, a_version, b_name, b_version, horizon, date_from, date_to):
    a = predictions(a_name,a_version,horizon,date_from,date_to,["EVALUATED"])
    b = predictions(b_name,b_version,horizon,date_from,date_to,["EVALUATED"])
    if a.empty or b.empty: return pd.DataFrame()
    columns = ["target_at","actual_price","baseline_price","predicted_price","actual_at","provider","evaluator_version"]
    merged = a[columns].merge(b[columns], on=["target_at","provider","evaluator_version"], suffixes=("_a","_b"), how="inner")
    if merged.empty: return merged
    merged = merged[pd.to_datetime(merged.actual_at_a,utc=True)==pd.to_datetime(merged.actual_at_b,utc=True)]
    return merged.rename(columns={"predicted_price_a":"viewing_predicted_price", "predicted_price_b":"comparison_predicted_price", "actual_price_a":"actual_price", "baseline_price_a":"baseline_price"})


def decisions(model_name, model_version, horizon, date_from, date_to, nonaccepted=False):
    session=get_session()
    try:
        q=session.query(PredictionDecision).filter(PredictionDecision.decision_at>=date_from,PredictionDecision.decision_at<=date_to)
        if model_name: q=q.filter(PredictionDecision.model_name==model_name)
        if model_version: q=q.filter(PredictionDecision.model_version==model_version)
        if horizon: q=q.filter(PredictionDecision.horizon_minutes==horizon)
        if nonaccepted: q=q.filter(PredictionDecision.acceptance_status.in_(["SUPPRESSED","REJECTED"]))
        rows=q.order_by(PredictionDecision.decision_at.desc()).all()
        return pd.DataFrame([{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in rows])
    finally: session.close()


def overview_state(model_name, model_version, horizon, date_from, date_to):
    frame=predictions(model_name,model_version,horizon,date_from,date_to)
    session=get_session()
    try:
        states=session.query(HorizonModelStatus).order_by(HorizonModelStatus.horizon_minutes).all()
        latest_run=session.query(RetrainingRun).order_by(RetrainingRun.requested_at.desc()).first()
        heartbeat=session.get(ServiceHeartbeat,WORKER_NAME)
        latest_notice=session.query(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()).first()
        scheduler=session.get(TrainingSchedulerState,1)
        return frame, states, latest_run, heartbeat, latest_notice, scheduler
    finally: session.close()


def training_runs():
    session=get_session()
    try:
        rows=session.query(RetrainingRun).order_by(RetrainingRun.requested_at.desc()).limit(200).all()
        return pd.DataFrame([{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in rows])
    finally: session.close()


def historical_summary():
    session=get_session()
    try:
        candle=session.query(func.count(GoldPriceCandle.id),func.min(GoldPriceCandle.candle_time),func.max(GoldPriceCandle.candle_time)).filter_by(symbol="XAUUSD",timeframe="1m",provider="histdata").one()
        imports=session.query(HistoricalDataImport).order_by(HistoricalDataImport.started_at.desc()).all()
        return candle, pd.DataFrame([{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in imports])
    finally: session.close()


def system_state():
    session=get_session()
    try:
        heartbeat=session.get(ServiceHeartbeat,WORKER_NAME)
        provider=session.query(ProviderStatus).order_by(ProviderStatus.updated_at.desc()).first()
        scheduler=session.get(TrainingSchedulerState,1)
        notification=session.query(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()).first()
        return heartbeat, provider, scheduler, notification, HeartbeatService.health(heartbeat)
    finally: session.close()
