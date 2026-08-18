import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from src.baselines import (
    HistoricalMeanBaseline, PersistenceBaseline, ZeroReturnBaseline,
    comparison_metrics, should_promote,
)
from src.candle_features import FEATURE_COLUMNS
from src.walk_forward import WalkForwardValidator, classify_regime


def synthetic_dataset():
    dates = pd.date_range(datetime(2010, 1, 1, tzinfo=timezone.utc),
                          datetime(2026, 1, 1, tzinfo=timezone.utc), freq="D", inclusive="left")
    index = np.arange(len(dates), dtype=float)
    close = 1000 + index * .08 + 5 * np.sin(index / 20)
    future_return = .002 * np.sin(index / 17)
    frame = pd.DataFrame({
        "Date": dates, "target_time": dates + pd.Timedelta(minutes=15),
        "Close": close, "target_close": close * (1 + future_return),
        "target_return": future_return, "High": close + 2, "Low": close - 2,
        "Open": close - .5, "horizon_minutes": 15,
    })
    for offset, column in enumerate(FEATURE_COLUMNS):
        if column not in frame:
            frame[column] = np.sin(index / (7 + offset))
    return frame


class BaselineTests(unittest.TestCase):
    def test_price_baselines_and_metrics(self):
        current = np.array([100., 101., 99.])
        actual = np.array([101., 100., 99.])
        persistence = PersistenceBaseline(15)
        np.testing.assert_array_equal(current, persistence.predict(current))
        np.testing.assert_array_equal(current, ZeroReturnBaseline(15).predict(current))
        metrics = persistence.get_metrics(actual, current, current)
        self.assertAlmostEqual(2 / 3, metrics["mae"])
        self.assertIn("directional_accuracy", metrics)
        self.assertIn("mape", metrics)
        historical = HistoricalMeanBaseline([100, 101, 102, 103], 1)
        self.assertGreater(float(historical.predict(100)), 100)

    def test_promotion_gates(self):
        accepted, _ = should_promote({"n_samples": 100, "mae": .90, "directional_accuracy": .55}, {"mae": 1.0})
        self.assertTrue(accepted)
        self.assertFalse(should_promote({"n_samples": 29, "mae": .5, "directional_accuracy": .9}, {"mae": 1})[0])
        self.assertFalse(should_promote({"n_samples": 100, "mae": .99, "directional_accuracy": .9}, {"mae": 1})[0])
        self.assertFalse(should_promote({"n_samples": 100, "mae": .5, "directional_accuracy": .5}, {"mae": 1})[0])
        self.assertFalse(should_promote({"n_samples": 100, "mae": .5, "directional_accuracy": .9}, {"mae": 1}, stable=False)[0])


class WalkForwardTests(unittest.TestCase):
    def setUp(self):
        self.data = synthetic_dataset()
        self.validator = WalkForwardValidator(self.data, 15, {
            "train_years": 3, "test_months": 6, "step_months": 6,
        })

    def test_folds_are_chronological_purged_and_tests_do_not_overlap(self):
        folds = self.validator.generate_folds()
        self.assertGreaterEqual(len(folds), 20)
        previous_end = None
        for fold in folds:
            self.assertLess(fold.train.target_time.max(), fold.test.Date.min())
            if previous_end is not None:
                self.assertGreaterEqual(fold.test.Date.min(), previous_end)
            previous_end = fold.test.Date.max()
        with self.assertRaises(ValueError):
            WalkForwardValidator(self.data, 15, {
                "train_years": 3, "test_months": 6, "step_months": 3,
            }).generate_folds()

    def test_validation_metrics_regimes_and_stability(self):
        results = self.validator.validate(LinearRegression)
        self.assertFalse(results.empty)
        required = {"mae", "rmse", "directional_accuracy", "sharpe", "persistence_mae",
                    "mae_improvement_pct", "market_regime"}
        self.assertTrue(required.issubset(results.columns))
        self.assertTrue(np.isfinite(results[["mae", "rmse", "persistence_mae"]]).all().all())
        assessment = self.validator.assess_stability(results)
        self.assertEqual(len(results), assessment["fold_count"])
        self.assertIn("stable", assessment)

    def test_regime_classification(self):
        bull = self.data.iloc[:366].copy()
        bull["Close"] = np.linspace(100, 130, len(bull))
        bull["High"], bull["Low"] = bull.Close + 1, bull.Close - 1
        self.assertEqual("BULL", classify_regime(bull, reference_atr_median=2))


if __name__ == "__main__":
    unittest.main()
