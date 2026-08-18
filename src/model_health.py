"""Rolling, baseline-relative production model health monitoring."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from src.database import ModelHealth


class ModelHealthMonitor:
    def __init__(self, horizon_minutes, window_size=100, alert_threshold=1.02, session=None, model_version=None):
        self.horizon = horizon_minutes
        self.window_size = max(30, window_size)
        self.alert_threshold = alert_threshold
        self.predictions = []
        self.status = "HEALTHY"
        self.alerts = []
        self.session = session
        self.model_version = model_version

    def update(self, prediction_result):
        if prediction_result.status != "EVALUATED":
            return self.status
        self.model_version = prediction_result.model_version
        baseline_error = prediction_result.baseline_absolute_error
        if baseline_error is None:
            baseline_error = abs(float(prediction_result.actual_price) - float(prediction_result.reference_price))
        self.predictions.append({
            "timestamp": prediction_result.target_at,
            "model_mae": float(prediction_result.absolute_error),
            "persistence_mae": float(baseline_error),
            "direction_correct": bool(prediction_result.direction_correct),
        })
        self.predictions = self.predictions[-self.window_size:]
        if len(self.predictions) >= 30:
            self._check_health()
            self._persist()
        return self.status

    def _check_health(self):
        recent = self.predictions[-30:]
        historic = self.predictions[-self.window_size:]
        metrics, history = self._compute_metrics(recent), self._compute_metrics(historic)
        reason = None
        if metrics["model_mae"] > metrics["persistence_mae"] * self.alert_threshold:
            reason = f"Model MAE {metrics['model_mae']:.4f} > {metrics['persistence_mae']:.4f} persistence"
        elif metrics["directional_accuracy"] < .45:
            reason = f"Directional accuracy dropped to {metrics['directional_accuracy']:.2%}"
        elif history["model_mae"] > 0 and metrics["model_mae"] > history["model_mae"] * 1.10:
            reason = f"MAE increased by {(metrics['model_mae']/history['model_mae'] - 1):.2%}"
        self.status = "DEGRADED" if reason else "HEALTHY"
        if reason:
            self._send_alert(reason)

    @staticmethod
    def _compute_metrics(predictions):
        return {
            "model_mae": float(np.mean([row["model_mae"] for row in predictions])),
            "persistence_mae": float(np.mean([row["persistence_mae"] for row in predictions])),
            "directional_accuracy": float(np.mean([row["direction_correct"] for row in predictions])),
            "n_samples": len(predictions),
        }

    def _send_alert(self, message):
        if not self.alerts or self.alerts[-1]["message"] != message:
            self.alerts.append({"created_at": datetime.now(timezone.utc), "message": message})

    def _persist(self):
        if self.session is None or not self.model_version:
            return
        metrics = self._compute_metrics(self.predictions[-30:])
        self.session.add(ModelHealth(
            horizon_minutes=self.horizon, model_version=self.model_version, status=self.status,
            model_mae=metrics["model_mae"], persistence_mae=metrics["persistence_mae"],
            directional_accuracy=metrics["directional_accuracy"], sample_count=metrics["n_samples"],
            checked_at=datetime.now(timezone.utc).replace(tzinfo=None), alert_sent=self.status == "DEGRADED",
        ))
        self.session.flush()


def monitor_from_predictions(session, horizon, model_version, window_size=100, alert_threshold=1.02):
    """Rebuild deterministic health state from durable evaluated predictions."""
    from src.database import HorizonPrediction
    rows = session.query(HorizonPrediction).filter(
        HorizonPrediction.horizon_minutes == horizon,
        HorizonPrediction.model_version == model_version,
        HorizonPrediction.status == "EVALUATED",
    ).order_by(HorizonPrediction.evaluated_at.desc()).limit(window_size).all()
    monitor = ModelHealthMonitor(horizon, window_size, alert_threshold, None, model_version)
    for row in reversed(rows):
        monitor.update(row)
    monitor.session = session
    if len(monitor.predictions) >= 30:
        monitor._persist()
    return monitor
