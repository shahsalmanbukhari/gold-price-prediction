import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import get_settings
from src.background_lifecycle import HeartbeatService, NotificationService, TrustService, WORKER_NAME
from src.database import (
    Base, HorizonModelStatus, HorizonPrediction, NotificationDelivery, PredictionDecision, ServiceHeartbeat,
)


def prediction(horizon=3, status="PENDING", model_version="v1"):
    now = datetime.now(timezone.utc)
    row = HorizonPrediction(
        batch_id="batch", symbol="XAUUSD", timeframe="1m", provider="gold_api",
        algorithm_name="trained_multi_horizon", algorithm_version="bundle-v1",
        feature_schema_version="candle_features_v1", prediction_created_at=now,
        created_at=now, feature_data_until=now-timedelta(minutes=1), target_at=now+timedelta(minutes=horizon),
        horizon_minutes=horizon, horizon_label=f"{horizon}m", current_price=100,
        reference_price=100, predicted_price=101, predicted_return=.01, baseline_price=100,
        predicted_trend="up", model_name="linear_regression", model_version=model_version,
        status=status, latest_live_price_at=now, last_completed_candle_at=now-timedelta(minutes=1),
        missing_period_count=0, actual_tolerance_seconds=90, direction_threshold=.0005,
        direction_policy_version="v1",
    )
    if status == "EVALUATED":
        row.actual_price, row.actual_at, row.actual_provider = 102, now, "gold_api"
        row.absolute_error, row.baseline_absolute_error = 1, 2
        row.direction_correct, row.evaluated_at = True, now
    return row


class BackgroundLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.alerts = get_settings().alerts
        self.original = {
            "webhook_url": self.alerts.webhook_url, "enabled": self.alerts.enabled,
            "min_live_samples": self.alerts.min_live_samples,
            "min_absolute_return_pct": self.alerts.min_absolute_return_pct,
            "max_retries": self.alerts.max_retries,
        }

    def tearDown(self):
        for key, value in self.original.items():
            setattr(self.alerts, key, value)
        self.session.close()

    def test_heartbeat_health_and_timeout(self):
        service = HeartbeatService("test-instance")
        row = service.update(self.session, last_error=None)
        self.assertEqual("RUNNING", service.health(row))
        row.last_heartbeat_at = datetime.now(timezone.utc)-timedelta(hours=1)
        self.assertEqual("STOPPED", service.health(row))

    def test_forecast_notification_is_idempotent_and_probation_suppresses_webhook(self):
        row = prediction()
        self.session.add(row); self.session.commit()
        trust = HorizonModelStatus(
            horizon_minutes=3, model_version="v1", algorithm="linear_regression",
            trust_status="PROBATION", offline_test_samples=100, offline_improvement_pct=1,
            rolling_sample_count=0,
        )
        service = NotificationService()
        service.enqueue_forecasts(self.session, [row], {3: trust})
        service.enqueue_forecasts(self.session, [row], {3: trust})
        deliveries = self.session.query(NotificationDelivery).all()
        self.assertEqual(0, len(deliveries))
        decision = self.session.query(PredictionDecision).one()
        self.assertEqual("SUPPRESSED", decision.acceptance_status)
        self.assertEqual("MODEL_IN_PROBATION", decision.acceptance_reason_code)

    def test_outcome_notification_is_distinct(self):
        row = prediction(status="EVALUATED")
        self.session.add(row); self.session.commit()
        service = NotificationService()
        service.enqueue_outcomes(self.session, [row])
        delivery = self.session.query(NotificationDelivery).one()
        self.assertEqual("OUTCOME_EVALUATED", delivery.event_type)
        self.assertTrue(delivery.payload["directionCorrect"])

    def test_webhook_failure_retries_without_changing_prediction(self):
        self.alerts.webhook_url = "https://example.invalid/hook"
        self.alerts.max_retries = 3
        row = prediction(status="EVALUATED")
        self.session.add(row); self.session.commit()
        service = NotificationService(opener=Mock(side_effect=TimeoutError("timeout")))
        service.enqueue_outcomes(self.session, [row])
        service.deliver_due(self.session)
        webhook = self.session.query(NotificationDelivery).filter_by(channel="webhook").one()
        self.assertEqual("RETRY", webhook.status)
        self.assertEqual(1, webhook.attempt_count)
        self.assertEqual("EVALUATED", self.session.get(HorizonPrediction, row.id).status)

    def test_trust_probation_trusted_and_degraded(self):
        self.alerts.min_live_samples = 2
        manifest = {"model_version": "v1", "algorithm": "benchmark", "horizons": {
            "3": {"algorithm": "linear_regression", "split_counts": {"test": 100},
                  "metrics": {"test": {"mae": .8, "persistence_mae": 1.0}}}
        }}
        state = TrustService().refresh(self.session, manifest)[3]
        self.assertEqual("PROBATION", state.trust_status)
        first, second = prediction(status="EVALUATED"), prediction(status="EVALUATED")
        second.batch_id = "batch-2"; second.latest_live_price_at += timedelta(seconds=1)
        self.session.add_all([first, second]); self.session.commit()
        state = TrustService().refresh(self.session, manifest)[3]
        self.assertEqual("TRUSTED", state.trust_status)
        first.absolute_error = second.absolute_error = 3
        first.baseline_absolute_error = second.baseline_absolute_error = 1
        first.direction_correct = second.direction_correct = False
        self.session.commit()
        state = TrustService().refresh(self.session, manifest)[3]
        self.assertEqual("DEGRADED", state.trust_status)

    def test_streamlit_is_not_imported_by_background_lifecycle(self):
        import src.background_lifecycle as lifecycle
        self.assertFalse(hasattr(lifecycle, "st"))


if __name__ == "__main__":
    unittest.main()
