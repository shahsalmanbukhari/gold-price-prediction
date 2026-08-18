import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.candle_features import (
    ADVANCED_FEATURE_COLUMNS, FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION,
    add_advanced_features, build_features, select_features, test_feature_stability as feature_stability,
)
from src.database import Base, ModelHealth
from src.model_health import ModelHealthMonitor


def candle_frame(count=100):
    dates = pd.date_range("2026-01-05T00:00:00Z", periods=count, freq="min")
    close = 4000 + np.sin(np.arange(count) / 5) + np.arange(count) * .01
    return pd.DataFrame({"Date": dates, "Open": close-.1, "High": close+.5,
                         "Low": close-.5, "Close": close, "Volume": None})


class AdvancedFeatureTests(unittest.TestCase):
    def test_features_are_finite_causal_and_schema_versioned(self):
        frame = candle_frame()
        advanced = add_advanced_features(frame)
        self.assertTrue(set(ADVANCED_FEATURE_COLUMNS).issubset(advanced.columns))
        self.assertIn("session_remaining", advanced)
        production = build_features(frame)
        self.assertTrue(set(FEATURE_COLUMNS).issubset(production.columns))
        self.assertNotIn("session_remaining", FEATURE_COLUMNS)
        self.assertNotIn("session_minute_pct", FEATURE_COLUMNS)
        self.assertTrue(np.isfinite(production[FEATURE_COLUMNS].to_numpy()).all())
        self.assertEqual("candle_features_v2", FEATURE_SCHEMA_VERSION)

    def test_rolling_features_reset_after_gap(self):
        frame = candle_frame(90)
        frame.loc[45:, "Date"] += pd.Timedelta(minutes=10)
        built = build_features(frame)
        second_start = frame.Date.iloc[45]
        self.assertGreaterEqual(built[built.Date >= second_start].Date.min(), second_start + pd.Timedelta(minutes=29))

    def test_selection_and_stability(self):
        frame = add_advanced_features(candle_frame(150), include_ex_post_session_features=False)
        frame["target"] = frame.Close.shift(-1) / frame.Close - 1
        selected = select_features(frame, "target", max_features=10)
        self.assertLessEqual(len(selected), 10)
        self.assertNotIn("target", selected)
        stable_input = frame.dropna(subset=selected[:3])
        stability = feature_stability(stable_input, selected[:3], num_folds=5)
        self.assertEqual(set(selected[:3]), set(stability))


class ModelHealthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()

    @staticmethod
    def result(index, model_error=2, baseline_error=1, correct=False):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
        return SimpleNamespace(status="EVALUATED", target_at=now, absolute_error=model_error,
                               baseline_absolute_error=baseline_error, actual_price=100,
                               reference_price=99, direction_correct=correct, model_version="v2")

    def test_degradation_persists_and_deduplicates_alert_message(self):
        monitor = ModelHealthMonitor(15, session=self.session, model_version="v2")
        for index in range(30):
            monitor.update(self.result(index))
        self.assertEqual("DEGRADED", monitor.status)
        self.assertEqual(1, len(monitor.alerts))
        self.session.commit()
        row = self.session.query(ModelHealth).order_by(ModelHealth.id.desc()).first()
        self.assertEqual("DEGRADED", row.status)
        self.assertTrue(row.alert_sent)

    def test_healthy_and_insufficient_sample_states(self):
        monitor = ModelHealthMonitor(30)
        for index in range(29):
            monitor.update(self.result(index, .5, 1, True))
        self.assertEqual("HEALTHY", monitor.status)
        monitor.update(self.result(30, .5, 1, True))
        self.assertEqual("HEALTHY", monitor.status)


if __name__ == "__main__":
    unittest.main()
