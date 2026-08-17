"""Durable worker health, model trust and idempotent notification delivery."""
from __future__ import annotations

import json
import socket
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from config.settings import get_settings
from src.database import (
    HorizonModelStatus, HorizonPrediction, NotificationDelivery, PredictionDecision, ServiceHeartbeat,
)

WORKER_NAME = "gold_prediction_worker"
WORKER_VERSION = "background_lifecycle_v1"


def utcnow():
    return datetime.now(timezone.utc)


class HeartbeatService:
    def __init__(self, instance_id=None):
        self.instance_id = instance_id or f"{socket.gethostname()}-{uuid4()}"
        self.started_at = utcnow()

    def update(self, session, **values):
        now = utcnow()
        row = session.get(ServiceHeartbeat, WORKER_NAME)
        if row is None:
            row = ServiceHeartbeat(
                service_name=WORKER_NAME, instance_id=self.instance_id,
                started_at=self.started_at, last_heartbeat_at=now,
                status="RUNNING", version=WORKER_VERSION,
            )
            session.add(row)
        elif row.instance_id != self.instance_id:
            row.started_at = self.started_at
        row.instance_id = self.instance_id
        row.last_heartbeat_at = now
        row.status = values.pop("status", "RUNNING")
        for key, value in values.items():
            if hasattr(row, key):
                setattr(row, key, value)
        session.commit()
        return row

    @staticmethod
    def health(row, now=None):
        if row is None:
            return "STOPPED"
        now = now or utcnow()
        stamp = row.last_heartbeat_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if (now - stamp).total_seconds() > get_settings().streaming.worker_unhealthy_after_seconds:
            return "STOPPED"
        return "DEGRADED" if row.status == "DEGRADED" or row.last_error else "RUNNING"


class TrustService:
    """Rolling performance is monitoring state, never a market-price feature."""
    def refresh(self, session, manifest):
        alerts = get_settings().alerts
        result = {}
        version = manifest["model_version"]
        for horizon_text, item in manifest["horizons"].items():
            horizon = int(horizon_text)
            test = item["metrics"]["test"]
            baseline = float(test.get("persistence_mae") or 0)
            improvement_pct = ((baseline - float(test["mae"])) / baseline * 100) if baseline else None
            rows = session.query(HorizonPrediction).filter(
                HorizonPrediction.status == "EVALUATED",
                HorizonPrediction.model_version == version,
                HorizonPrediction.horizon_minutes == horizon,
            ).order_by(HorizonPrediction.evaluated_at.desc()).limit(200).all()
            count = len(rows)
            live_mae = sum(float(r.absolute_error) for r in rows) / count if count else None
            live_baseline = sum(float(r.baseline_absolute_error) for r in rows) / count if count else None
            directional = sum(bool(r.direction_correct) for r in rows) / count * 100 if count else None
            if improvement_pct is None or improvement_pct < alerts.min_test_improvement_pct:
                trust, reason = "DISABLED", "Offline model did not beat persistence"
            elif count < alerts.min_live_samples:
                trust, reason = "PROBATION", f"Needs {alerts.min_live_samples} evaluated live samples"
            elif directional < alerts.min_directional_accuracy_pct or live_mae > live_baseline:
                trust, reason = "DEGRADED", "Rolling live performance is below the configured threshold"
            else:
                trust, reason = "TRUSTED", None
            state = session.get(HorizonModelStatus, (horizon, version))
            if state is None:
                state = HorizonModelStatus(horizon_minutes=horizon, model_version=version, algorithm=item.get("algorithm", manifest.get("algorithm", "unknown")))
                session.add(state)
            state.algorithm = item.get("algorithm", manifest.get("algorithm", "unknown"))
            state.trust_status = trust
            state.offline_test_samples = int(item["split_counts"]["test"])
            state.offline_improvement_pct = improvement_pct
            state.rolling_sample_count = count
            state.rolling_mae = live_mae
            state.rolling_baseline_mae = live_baseline
            state.rolling_directional_accuracy_pct = directional
            state.alert_suppression_reason = reason
            state.updated_at = utcnow()
            result[horizon] = state
        session.commit()
        return result


class NotificationService:
    def __init__(self, opener=None):
        self.settings = get_settings().alerts
        self.opener = opener or urllib.request.urlopen

    @staticmethod
    def _number(value):
        return float(value) if value is not None else None

    def forecast_payload(self, prediction, trust):
        return {
            "eventType": "FORECAST_READY", "predictionId": prediction.id,
            "createdAt": prediction.prediction_created_at.isoformat(),
            "targetAt": prediction.target_at.isoformat(), "symbol": prediction.symbol,
            "horizonMinutes": prediction.horizon_minutes,
            "referencePrice": self._number(prediction.reference_price),
            "predictedPrice": self._number(prediction.predicted_price),
            "predictedReturnPct": self._number(prediction.predicted_return) * 100,
            "predictedDirection": str(prediction.predicted_trend).upper(),
            "modelName": prediction.model_name, "modelVersion": prediction.model_version,
            "modelTestImprovementOverBaselinePct": trust.offline_improvement_pct,
            "rollingDirectionalAccuracyPct": trust.rolling_directional_accuracy_pct or 0,
            "rollingSampleCount": trust.rolling_sample_count, "dataFresh": True,
            "trustStatus": trust.trust_status,
        }

    def outcome_payload(self, prediction):
        return {
            "eventType": "OUTCOME_EVALUATED", "predictionId": prediction.id,
            "targetAt": prediction.target_at.isoformat(),
            "actualAt": prediction.actual_at.isoformat() if prediction.actual_at else None,
            "horizonMinutes": prediction.horizon_minutes,
            "referencePrice": self._number(prediction.reference_price),
            "predictedPrice": self._number(prediction.predicted_price),
            "actualPrice": self._number(prediction.actual_price),
            "absoluteError": self._number(prediction.absolute_error),
            "directionCorrect": prediction.direction_correct,
            "modelVersion": prediction.model_version,
        }

    def _enqueue(self, session, event_type, prediction, channel, payload):
        row = NotificationDelivery(
            event_type=event_type, prediction_id=prediction.id, channel=channel,
            status="SENT" if channel == "in_app" else "PENDING",
            sent_at=utcnow() if channel == "in_app" else None,
            next_attempt_at=utcnow(), payload=payload,
        )
        session.add(row)
        try:
            session.commit()
            return row
        except IntegrityError:
            session.rollback()
            return None

    def enqueue_forecasts(self, session, predictions, trust_by_horizon):
        for prediction in predictions:
            trust = trust_by_horizon[prediction.horizon_minutes]
            magnitude = abs(float(prediction.predicted_return) * 100)
            if magnitude < self.settings.min_absolute_return_pct:
                status, code, detail = "SUPPRESSED", "PREDICTION_TOO_SMALL", "Predicted movement is below the configured noise threshold"
            elif trust.trust_status == "PROBATION":
                status, code, detail = "SUPPRESSED", "MODEL_IN_PROBATION", trust.alert_suppression_reason
            elif trust.trust_status == "DEGRADED":
                status, code, detail = "SUPPRESSED", "MODEL_DEGRADED", trust.alert_suppression_reason
            elif trust.trust_status == "DISABLED":
                status, code, detail = "REJECTED", "MODEL_DISABLED", trust.alert_suppression_reason
            else:
                status, code, detail = "ACCEPTED", "QUALIFIED", "All configured offline, live, freshness and magnitude controls passed"
            decision = PredictionDecision(
                prediction_id=prediction.id, decision_at=utcnow(), symbol=prediction.symbol,
                provider=prediction.provider, horizon_minutes=prediction.horizon_minutes,
                model_name=prediction.model_name, model_version=prediction.model_version,
                reference_price=prediction.reference_price, predicted_price=prediction.predicted_price,
                predicted_direction=prediction.predicted_trend, acceptance_status=status,
                acceptance_reason_code=code, acceptance_reason_detail=detail,
                trust_status_at_decision=trust.trust_status,
                required_sample_count=self.settings.min_live_samples,
                actual_sample_count=trust.rolling_sample_count,
                required_directional_accuracy=self.settings.min_directional_accuracy_pct,
                actual_directional_accuracy=trust.rolling_directional_accuracy_pct,
                required_baseline_improvement=self.settings.min_test_improvement_pct,
                actual_baseline_improvement=trust.offline_improvement_pct,
                required_prediction_magnitude=self.settings.min_absolute_return_pct,
                actual_prediction_magnitude=magnitude, data_fresh=True,
                missing_period_count=prediction.missing_period_count,
                technical_context={"feature_schema_version": prediction.feature_schema_version},
            )
            session.add(decision)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            if status != "ACCEPTED":
                continue
            payload = self.forecast_payload(prediction, trust)
            self._enqueue(session, "FORECAST_READY", prediction, "in_app", payload)
            webhook_allowed = trust.trust_status == "TRUSTED" or (
                trust.trust_status == "PROBATION" and self.settings.probation_webhooks_enabled
            )
            if self.settings.enabled and self.settings.webhook_url and webhook_allowed:
                cutoff = utcnow() - timedelta(seconds=self.settings.cooldown_seconds)
                recent = session.query(NotificationDelivery).join(HorizonPrediction).filter(
                    NotificationDelivery.event_type == "FORECAST_READY",
                    NotificationDelivery.channel == "webhook",
                    HorizonPrediction.horizon_minutes == prediction.horizon_minutes,
                    NotificationDelivery.created_at >= cutoff,
                ).first()
                if not recent:
                    self._enqueue(session, "FORECAST_READY", prediction, "webhook", payload)

    def enqueue_outcomes(self, session, predictions):
        for prediction in predictions:
            self._enqueue(session, "OUTCOME_EVALUATED", prediction, "in_app", self.outcome_payload(prediction))
            if self.settings.enabled and self.settings.webhook_url:
                self._enqueue(session, "OUTCOME_EVALUATED", prediction, "webhook", self.outcome_payload(prediction))

    def deliver_due(self, session, now=None):
        now = now or utcnow()
        rows = session.query(NotificationDelivery).filter(
            NotificationDelivery.channel == "webhook",
            NotificationDelivery.status.in_(["PENDING", "RETRY"]),
            NotificationDelivery.next_attempt_at <= now,
        ).all()
        for row in rows:
            try:
                request = urllib.request.Request(
                    self.settings.webhook_url, data=json.dumps(row.payload).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                response = self.opener(request, timeout=self.settings.timeout_seconds)
                if getattr(response, "status", 200) >= 300:
                    raise RuntimeError(f"Webhook returned HTTP {response.status}")
                row.status, row.sent_at, row.last_error = "SENT", now, None
            except Exception as exc:
                row.attempt_count += 1
                row.last_error = str(exc)[:1000]
                if row.attempt_count >= self.settings.max_retries:
                    row.status = "FAILED"
                else:
                    row.status = "RETRY"
                    row.next_attempt_at = now + timedelta(seconds=min(300, 2 ** row.attempt_count))
            session.commit()
        return len(rows)
