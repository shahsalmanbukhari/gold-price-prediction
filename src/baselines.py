"""Transparent price baselines and common comparison metrics."""

from __future__ import annotations

from math import sqrt

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error


def directional_accuracy(y_true, y_pred, current_prices=None) -> float:
    """Fraction of predicted directions matching actual directions."""
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    if current_prices is None:
        if len(actual) < 2:
            return float("nan")
        return float(np.mean(np.sign(np.diff(actual)) == np.sign(np.diff(predicted))))
    current = np.asarray(current_prices, dtype=float)
    return float(np.mean(np.sign(actual - current) == np.sign(predicted - current)))


def comparison_metrics(y_true, y_pred, current_prices=None) -> dict[str, float]:
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(sqrt(mean_squared_error(actual, predicted))),
        "directional_accuracy": directional_accuracy(actual, predicted, current_prices),
        "mape": float(mean_absolute_percentage_error(actual, predicted)),
    }


class PersistenceBaseline:
    def __init__(self, horizon_minutes):
        self.horizon = horizon_minutes

    def predict(self, current_price):
        """Future price equals current price."""
        return np.asarray(current_price, dtype=float)

    def get_metrics(self, y_true, y_pred, current_prices=None):
        return comparison_metrics(y_true, y_pred, current_prices)


class ZeroReturnBaseline(PersistenceBaseline):
    pass


class HistoricalMeanBaseline:
    def __init__(self, historical_prices, horizon_minutes):
        prices = np.asarray(historical_prices, dtype=float)
        if len(prices) <= horizon_minutes or np.any(prices <= 0):
            raise ValueError("Insufficient positive history for historical-mean baseline")
        self.horizon = horizon_minutes
        self.mean_return = float(np.mean(np.log(prices[horizon_minutes:] / prices[:-horizon_minutes])))

    def predict(self, current_price):
        return np.asarray(current_price, dtype=float) * np.exp(self.mean_return)


def should_promote(model_metrics, persistence_metrics, threshold=0.02, stable=True):
    """Apply minimum sample, baseline, direction, and fold-stability gates."""
    if int(model_metrics.get("n_samples", 0)) < 30:
        return False, "Insufficient samples"
    baseline_mae = float(persistence_metrics.get("mae", 0))
    if baseline_mae <= 0:
        return False, "Persistence MAE must be positive"
    improvement = (baseline_mae - float(model_metrics["mae"])) / baseline_mae
    if improvement < threshold:
        return False, f"MAE improvement {improvement:.2%} < {threshold:.0%}"
    directional = float(model_metrics.get("directional_accuracy", 0))
    if directional <= .50:
        return False, f"Directional accuracy {directional:.2%} <= 50%"
    if not stable:
        return False, "Walk-forward stability criteria were not satisfied"
    return True, "Passed all gates"
