"""Focused pages used by the explicit Streamlit dashboard router."""

from datetime import datetime, timedelta, timezone
import math

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import func
from streamlit_autorefresh import st_autorefresh

from config.settings import get_settings
from src.database import (
    HorizonModelStatus, HorizonPrediction, NotificationDelivery, Price,
    RetrainingRun, ServiceHeartbeat, get_session, init_db,
)
from src.background_lifecycle import HeartbeatService, WORKER_NAME
from src.horizon_prediction_service import HORIZONS, HorizonPredictionService


def _rows(query):
    return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in query]


TRAINING_CHART_METRICS = {
    "mae": "candidate_mae",
    "persistence_mae": "persistence_mae",
    "rmse": "candidate_rmse",
    "persistence_rmse": "persistence_rmse",
}


def build_training_metric_chart_data(source) -> pd.DataFrame:
    """Normalize heterogeneous retraining JSON into safe long-form chart rows."""
    columns = [
        "completed_at", "candidate_version", "algorithm", "horizon",
        "metric", "value", "status",
    ]
    frame = source.copy() if isinstance(source, pd.DataFrame) else pd.DataFrame(source or [])
    if frame.empty:
        return pd.DataFrame(columns=columns)
    records = []
    for row in frame.to_dict("records"):
        completed_at = pd.to_datetime(row.get("completed_at"), utc=True, errors="coerce")
        if pd.isna(completed_at):
            continue
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            continue
        horizons = metrics.get("horizons", metrics)
        if not isinstance(horizons, dict):
            continue
        for horizon, payload in horizons.items():
            try:
                horizon_value = int(horizon)
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            payload = payload.get("test", payload)
            if not isinstance(payload, dict):
                continue
            for source_name, display_name in TRAINING_CHART_METRICS.items():
                value = pd.to_numeric(pd.Series([payload.get(source_name)]), errors="coerce").iloc[0]
                if pd.isna(value):
                    continue
                records.append({
                    "completed_at": completed_at,
                    "candidate_version": row.get("new_version") or "unknown",
                    "algorithm": row.get("model_name") or "unknown",
                    "horizon": horizon_value,
                    "metric": display_name,
                    "value": float(value),
                    "status": str(row.get("status") or "unknown").upper(),
                })
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records, columns=columns).sort_values(
        ["horizon", "completed_at", "candidate_version", "metric"]
    ).reset_index(drop=True)


def build_training_metrics_figure(source):
    chart = build_training_metric_chart_data(source)
    if chart.empty:
        return None
    return px.line(
        chart, x="completed_at", y="value", color="metric", facet_row="horizon",
        line_dash="candidate_version", markers=True,
        hover_data=["algorithm", "status", "candidate_version"],
        title="Candidate and persistence metrics by horizon",
    )


def _latest_data():
    init_db()
    session = get_session()
    try:
        price = session.query(Price).order_by(Price.timestamp.desc()).first()
        batch = session.query(HorizonPrediction.batch_id).filter(
            HorizonPrediction.algorithm_name == "trained_multi_horizon",
            HorizonPrediction.status != "LEGACY",
        ).order_by(
            HorizonPrediction.prediction_created_at.desc()
        ).first()
        predictions = [] if not batch else _rows(session.query(HorizonPrediction).filter(
            HorizonPrediction.batch_id == batch[0]
        ).order_by(HorizonPrediction.horizon_minutes).all())
        return price, predictions
    finally:
        session.close()


def _header(price):
    st.title("🥇 Gold Price Intelligence")
    if not price:
        st.warning("No live prices are stored. Start the collection service first.")
        return
    timestamp = price.timestamp.replace(tzinfo=timezone.utc) if price.timestamp.tzinfo is None else price.timestamp.astimezone(timezone.utc)
    age = (datetime.now(timezone.utc) - timestamp).total_seconds()
    columns = st.columns(4)
    columns[0].metric("Live gold price", f"${price.price_usd:,.2f}")
    columns[1].metric("Market status", "LIVE" if age <= 120 else "STALE")
    columns[2].metric("Provider", price.provider or "unknown")
    columns[3].metric("Last update", timestamp.strftime("%H:%M:%S UTC"))


def render_overview():
    """Route: /overview. Cross-system summary without duplicating prediction cards."""
    st_autorefresh(interval=30_000, key="intelligence-overview-refresh")
    init_db()
    session = get_session()
    try:
        price = session.query(Price).order_by(Price.timestamp.desc()).first()
        recent_prices = list(reversed(session.query(Price).order_by(
            Price.timestamp.desc()
        ).limit(240).all()))
        resolved = session.query(HorizonPrediction).filter(
            HorizonPrediction.status == "EVALUATED",
            HorizonPrediction.algorithm_name == "trained_multi_horizon",
        ).order_by(HorizonPrediction.evaluated_at.desc()).limit(500).all()
        pending_count = session.query(HorizonPrediction).filter(
            HorizonPrediction.status == "PENDING",
            HorizonPrediction.algorithm_name == "trained_multi_horizon",
        ).count()
        latest_run = session.query(RetrainingRun).order_by(
            RetrainingRun.requested_at.desc()
        ).first()
    finally:
        session.close()

    _header(price)
    st.subheader("System overview")
    if resolved:
        mae = sum(float(row.absolute_error) for row in resolved) / len(resolved)
        baseline_mae = sum(float(row.baseline_absolute_error) for row in resolved) / len(resolved)
        direction_accuracy = sum(bool(row.direction_correct) for row in resolved) / len(resolved) * 100
    else:
        mae = baseline_mae = direction_accuracy = 0.0
    columns = st.columns(4)
    columns[0].metric("Model MAE", f"${mae:.4f}", help="Production trained predictions only")
    columns[1].metric("Persistence MAE", f"${baseline_mae:.4f}")
    columns[2].metric("Directional accuracy", f"{direction_accuracy:.2f}%")
    columns[3].metric("Awaiting outcomes", pending_count)

    chart_col, status_col = st.columns([2, 1])
    with chart_col:
        st.subheader("Recent live price activity")
        if recent_prices:
            price_frame = pd.DataFrame({
                "timestamp": [row.timestamp for row in recent_prices],
                "price": [row.price_usd for row in recent_prices],
            })
            st.plotly_chart(px.line(
                price_frame, x="timestamp", y="price", title="Gold price (USD)",
            ), use_container_width=True)
        else:
            st.info("No live price history is available yet.")
    with status_col:
        st.subheader("Learning status")
        if latest_run:
            st.metric("Latest retraining", latest_run.status.upper())
            st.caption(f"Trigger: {latest_run.trigger}")
            st.caption(f"Requested: {latest_run.requested_at:%Y-%m-%d %H:%M UTC}")
            if latest_run.accuracy_before is not None:
                st.metric("Accuracy before", f"{latest_run.accuracy_before:.2f}%")
        else:
            st.metric("Retraining", "No runs yet")

    st.subheader("Open a detailed dashboard")
    links = st.columns(4)
    with links[0]:
        st.link_button("🧪 Legacy experimental", "/forecast", use_container_width=True)
    with links[1]:
        st.link_button("⚡ Live predictions", "/live-predictions", use_container_width=True)
    with links[2]:
        st.link_button("📊 Performance", "/performance", use_container_width=True)
    with links[3]:
        st.link_button("🧠 Self-learning", "/self-learning", use_container_width=True)


def render_live_predictions():
    """Route: /live-predictions."""
    st_autorefresh(interval=30_000, key="live-prediction-refresh")
    price, predictions = _latest_data()
    _header(price)
    st.subheader("Live multi-horizon predictions")
    st.caption("Automatically refreshes every 30 seconds; upstream API requests retain the 35-second cache floor.")

    if not predictions and price:
        service = HorizonPredictionService()
        service.generate()
        if service.last_unavailable_reason:
            st.warning(service.last_unavailable_reason)
        else:
            st.rerun()
    if not predictions:
        st.info("No approved trained prediction batch is currently available.")
    for start in range(0, len(predictions), 3):
        columns = st.columns(3)
        for column, prediction in zip(columns, predictions[start:start + 3]):
            icon = {"up": "▲", "down": "▼", "stable": "●"}.get(prediction["predicted_trend"], "●")
            with column.container(border=True):
                st.subheader(f"{prediction['horizon_minutes']} minutes")
                st.caption(prediction["horizon_label"])
                st.metric(
                    "Predicted price",
                    f"${prediction['predicted_price']:,.2f}",
                    f"{icon} {prediction['predicted_price'] - prediction['current_price']:+,.2f}",
                )
                st.caption(f"Interval ({prediction['interval_method']}): ${prediction['lower_bound']:,.2f} – ${prediction['upper_bound']:,.2f}")
                st.caption(f"{prediction['model_name']} · {prediction['model_version']} · {prediction['feature_schema_version']}")


def render_performance_analysis():
    """Route: /performance."""
    st.title("📊 Prediction Performance Analysis")
    c1, c2, c3 = st.columns(3)
    days = c1.selectbox("History window", [1, 7, 30, 90], index=1, format_func=lambda x: f"{x} day(s)")
    horizon = c2.selectbox(
        "Time horizon", [0, *HORIZONS],
        format_func=lambda value: "All horizons" if value == 0 else f"{value} min — {HORIZONS[value]}",
    )
    status = c3.selectbox("Status", ["ALL", "EVALUATED", "PENDING", "UNRESOLVABLE", "FAILED"])
    init_db()
    session = get_session()
    try:
        query = session.query(HorizonPrediction).filter(
            HorizonPrediction.algorithm_name == "trained_multi_horizon",
            HorizonPrediction.status != "LEGACY",
            HorizonPrediction.prediction_created_at >= datetime.now(timezone.utc) - timedelta(days=days),
        )
        if horizon:
            query = query.filter(HorizonPrediction.horizon_minutes == horizon)
        providers = [r[0] for r in query.with_entities(HorizonPrediction.provider).distinct()]
        algorithms = [r[0] for r in query.with_entities(HorizonPrediction.algorithm_name).distinct()]
        versions = [r[0] for r in query.with_entities(HorizonPrediction.model_version).distinct()]
        f1, f2, f3 = st.columns(3)
        provider = f1.selectbox("Provider", ["ALL", *providers])
        algorithm = f2.selectbox("Algorithm", ["ALL", *algorithms])
        version = f3.selectbox("Model version", ["ALL", *versions])
        if status != "ALL": query = query.filter(HorizonPrediction.status == status)
        if provider != "ALL": query = query.filter(HorizonPrediction.provider == provider)
        if algorithm != "ALL": query = query.filter(HorizonPrediction.algorithm_name == algorithm)
        if version != "ALL": query = query.filter(HorizonPrediction.model_version == version)
        records = _rows(query.order_by(HorizonPrediction.prediction_created_at).all())
    finally:
        session.close()

    if not records:
        st.info("No non-legacy production predictions match these filters.")
        return
    frame = pd.DataFrame(records)
    counts = frame.status.value_counts()
    count_cols = st.columns(4)
    for col, value in zip(count_cols, ("EVALUATED", "PENDING", "UNRESOLVABLE", "FAILED")):
        col.metric(value.title(), int(counts.get(value, 0)))
    evaluated = frame[frame.status == "EVALUATED"].copy()
    if evaluated.empty:
        st.info("Metrics appear after predictions are evaluated within their approved tolerance.")
        st.dataframe(frame, use_container_width=True, hide_index=True)
        return
    evaluated["squared_error"] = evaluated.absolute_error.astype(float) ** 2
    evaluated["baseline_squared_error"] = evaluated.baseline_absolute_error.astype(float) ** 2
    evaluated["smape"] = (
        2 * evaluated.absolute_error.astype(float)
        / (evaluated.actual_price.astype(float).abs() + evaluated.predicted_price.astype(float).abs())
        * 100
    )
    evaluated["evaluation_delay_seconds"] = evaluated.evaluation_delay_seconds.astype(float)
    summary = evaluated.groupby(["horizon_minutes", "model_version"]).agg(
        samples=("id", "count"), mae=("absolute_error", "mean"), rmse=("squared_error", lambda x: math.sqrt(x.mean())),
        smape=("smape", "mean"), directional_accuracy=("direction_correct", "mean"),
        persistence_mae=("baseline_absolute_error", "mean"),
        persistence_rmse=("baseline_squared_error", lambda x: math.sqrt(x.mean())),
        evaluation_delay_seconds=("evaluation_delay_seconds", "mean"),
    ).reset_index()
    summary["directional_accuracy"] *= 100
    summary["mae_improvement"] = summary.persistence_mae - summary.mae
    summary["mae_improvement_pct"] = (
        summary.mae_improvement / summary.persistence_mae.replace(0, float("nan")) * 100
    )
    minimum = get_settings().ml.performance_minimum_samples
    eligible = summary[summary.samples >= minimum]
    if eligible.empty:
        st.warning(f"At least {minimum} evaluated samples per horizon/model version are required before ranking or declaring improvement.")
    else:
        best = eligible.loc[eligible.mae.idxmin()]
        st.metric("Best sufficiently sampled horizon", f"{int(best.horizon_minutes)} min", f"MAE ${best.mae:.4f}")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    evaluated["rolling_mae"] = evaluated.groupby(["horizon_minutes", "model_version"])["absolute_error"].transform(
        lambda values: values.astype(float).rolling(minimum, min_periods=minimum).mean()
    )
    st.plotly_chart(px.line(
        evaluated, x="evaluated_at", y="rolling_mae", color="horizon_minutes",
        line_dash="model_version", title="Rolling MAE by horizon and model version",
    ), use_container_width=True)
    st.plotly_chart(px.histogram(evaluated, x="evaluation_delay_seconds", color="horizon_minutes",
                                title="Evaluation-delay distribution"), use_container_width=True)
    comparison = frame[[
        "prediction_created_at", "feature_data_until", "target_at", "horizon_minutes", "reference_price",
        "predicted_price", "baseline_price", "actual_price", "actual_at", "evaluation_delay_seconds",
        "absolute_error", "percentage_error", "baseline_absolute_error", "direction_correct", "provider",
        "algorithm_name", "model_version", "feature_schema_version", "status", "failure_reason",
    ]].sort_values("prediction_created_at", ascending=False)
    st.dataframe(comparison, use_container_width=True, hide_index=True)


def render_self_learning():
    """Route: /self-learning."""
    st.title("🧠 Self-Learning & Retraining")
    init_db()
    session = get_session()
    try:
        active = session.query(RetrainingRun).filter(
            func.lower(RetrainingRun.status).in_(["pending", "running"])
        ).order_by(RetrainingRun.requested_at).first()
        runs = _rows(session.query(RetrainingRun).order_by(
            RetrainingRun.requested_at.desc()
        ).limit(100).all())
    finally:
        session.close()

    status_col, trigger_col = st.columns([2, 1])
    status_col.metric("Retraining status", active.status.upper() if active else "IDLE")
    if trigger_col.button("Start manual retraining", type="primary", use_container_width=True):
        if active:
            st.warning("A retraining job is already pending or running.")
        else:
            session = get_session()
            try:
                session.add(RetrainingRun(trigger="manual", status="PENDING", model_name="linear_regression"))
                session.commit()
                st.success("Retraining request queued. The collection service will process it.")
                st.rerun()
            finally:
                session.close()
    st.info("Automatic retraining uses durable time/new-candle watermarks and sufficiently sampled baseline-relative or directional degradation. It never uses the legacy closeness score.")
    if runs:
        frame = pd.DataFrame(runs)
        display_columns = [column for column in [
            "requested_at", "completed_at", "trigger", "status", "model_name",
            "previous_version", "new_version", "candidate_path", "production_changed", "error_message",
        ] if column in frame.columns]
        st.dataframe(frame[display_columns], use_container_width=True, hide_index=True)
        rejected = frame[frame.status.astype(str).str.upper() == "REJECTED"]
        if not rejected.empty:
            structured = rejected[rejected.get("candidate_path", pd.Series(index=rejected.index, dtype=object)).notna()]
            latest = (structured if not structured.empty else rejected).iloc[0]
            reasons = (latest.get("error_analysis") or {}).get("rejection_reasons", [])
            if reasons and reasons[0].get("criterion") == "worse_than_persistence":
                reason_text = f"{reasons[0].get('horizon')}m model was worse than persistence"
            else:
                reason_text = latest.get("error_message") or "quality criteria were not met"
            st.warning(f"Status: Rejected — {reason_text}")
            details = st.columns(3)
            details[0].metric("Production changed", "No")
            details[1].metric("Candidate version", latest.get("new_version") or "unknown")
            details[2].metric("Algorithm", latest.get("model_name") or "unknown")
            if latest.get("candidate_path"):
                st.code(str(latest.candidate_path), language=None)
            if reasons:
                st.dataframe(pd.DataFrame(reasons), use_container_width=True, hide_index=True)
        figure = build_training_metrics_figure(frame)
        if figure is None:
            st.info("No numeric training metrics are available yet.")
        else:
            st.plotly_chart(figure, use_container_width=True)
    else:
        st.info("No retraining history has been recorded yet.")


def render_background_system():
    """Read-only operational view; it never drives worker lifecycle actions."""
    init_db()
    st.title("🛰️ Background Prediction System")
    st.caption("This page observes the independent worker. Closing Streamlit does not stop it.")
    session = get_session()
    try:
        heartbeat = session.get(ServiceHeartbeat, WORKER_NAME)
        horizon_rows = session.query(HorizonModelStatus).order_by(HorizonModelStatus.horizon_minutes).all()
        notifications = session.query(NotificationDelivery).order_by(
            NotificationDelivery.created_at.desc()
        ).limit(200).all()
    finally:
        session.close()

    status = HeartbeatService.health(heartbeat)
    cols = st.columns(4)
    cols[0].metric("Background worker", status)
    cols[1].metric("Last heartbeat", str(heartbeat.last_heartbeat_at) if heartbeat else "Never")
    cols[2].metric("Last live quote", str(heartbeat.last_live_quote_at) if heartbeat else "Never")
    cols[3].metric("Last prediction", str(heartbeat.last_prediction_at) if heartbeat else "Never")
    cols = st.columns(3)
    cols[0].metric("Last evaluation", str(heartbeat.last_evaluation_at) if heartbeat else "Never")
    cols[1].metric("Last training", str(heartbeat.last_training_at) if heartbeat else "Never")
    uptime = "-"
    if heartbeat:
        uptime = str(pd.Timestamp.now(tz="UTC") - pd.Timestamp(heartbeat.started_at))
    cols[2].metric("Worker uptime", uptime)
    if heartbeat and heartbeat.last_error:
        st.warning(f"Latest worker diagnostic: {heartbeat.last_error}")

    alerts = get_settings().alerts
    st.subheader("Alert qualification thresholds")
    st.caption(
        f"Offline improvement ≥ {alerts.min_test_improvement_pct:.2f}% · "
        f"Live samples ≥ {alerts.min_live_samples} · Directional accuracy ≥ "
        f"{alerts.min_directional_accuracy_pct:.1f}% · Absolute forecast return ≥ "
        f"{alerts.min_absolute_return_pct:.3f}%. These are analytical controls, not profitability guarantees."
    )
    st.subheader("Horizon trust status")
    if not horizon_rows:
        st.info("No approved production horizon state is available.")
    else:
        st.dataframe(pd.DataFrame([{
            "horizon": f"{row.horizon_minutes}m", "algorithm": row.algorithm,
            "model_version": row.model_version, "trust_status": row.trust_status,
            "offline_test_samples": row.offline_test_samples,
            "offline_improvement_pct": row.offline_improvement_pct,
            "rolling_live_samples": row.rolling_sample_count,
            "rolling_mae": row.rolling_mae, "rolling_baseline_mae": row.rolling_baseline_mae,
            "rolling_directional_accuracy_pct": row.rolling_directional_accuracy_pct,
            "last_prediction": row.last_prediction_at, "next_target": row.next_target_at,
            "alerts": "enabled" if row.trust_status == "TRUSTED" else "suppressed",
            "reason": row.alert_suppression_reason,
        } for row in horizon_rows]), use_container_width=True, hide_index=True)

    st.subheader("Notifications")
    if not notifications:
        st.info("No forecast or outcome notifications have been recorded.")
    else:
        event_filter = st.multiselect(
            "Event type", ["FORECAST_READY", "OUTCOME_EVALUATED"],
            default=["FORECAST_READY", "OUTCOME_EVALUATED"],
        )
        display = []
        for item in notifications:
            if item.event_type not in event_filter:
                continue
            display.append({
                "meaning": "Forecast signal — outcome not yet known" if item.event_type == "FORECAST_READY"
                else "Evaluated result — target time has passed",
                "event_type": item.event_type, "prediction_id": item.prediction_id,
                "channel": item.channel, "status": item.status, "attempts": item.attempt_count,
                "next_attempt": item.next_attempt_at, "sent_at": item.sent_at,
                "last_error": item.last_error, "created_at": item.created_at,
            })
        st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
