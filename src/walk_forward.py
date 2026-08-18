"""Leakage-safe calendar walk-forward validation for direct-horizon models."""

from __future__ import annotations

import inspect
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.baselines import PersistenceBaseline, comparison_metrics
from src.candle_features import FEATURE_COLUMNS


def _atr(frame: pd.DataFrame, window=14) -> pd.Series:
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat([
        frame["High"] - frame["Low"],
        (frame["High"] - previous_close).abs(),
        (frame["Low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.rolling(window, min_periods=window).mean()


def classify_regime(df: pd.DataFrame, reference_atr_median=None) -> str:
    """Classify a chronological period without using data after that period."""
    if df.empty or len(df) < 2:
        return "UNKNOWN"
    ordered = df.sort_values("Date")
    elapsed_years = max((pd.Timestamp(ordered.Date.iloc[-1]) - pd.Timestamp(ordered.Date.iloc[0])).total_seconds()
                        / (365.25 * 86400), 1 / 365.25)
    annualized_return = (float(ordered.Close.iloc[-1]) / float(ordered.Close.iloc[0])) ** (1 / elapsed_years) - 1
    direction = "BULL" if annualized_return > .20 else "BEAR" if annualized_return < -.20 else "SIDEWAYS"
    atr = _atr(ordered).dropna()
    if atr.empty:
        return direction
    reference = float(reference_atr_median) if reference_atr_median is not None else float(atr.median())
    level = float(atr.mean())
    if reference > 0 and level > 2 * reference:
        return "HIGH_VOL"
    if reference > 0 and level < .5 * reference:
        return "LOW_VOL"
    return direction


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train: pd.DataFrame
    test: pd.DataFrame


class WalkForwardValidator:
    def __init__(self, data, horizon_minutes, config):
        self.data = data.copy()
        self.horizon = horizon_minutes
        self.config = config

    def generate_folds(self):
        """Generate rolling calendar folds with disjoint test windows and purging."""
        data = self.data.sort_values("Date").reset_index(drop=True)
        data["Date"] = pd.to_datetime(data["Date"], utc=True)
        data["target_time"] = pd.to_datetime(data["target_time"], utc=True)
        train_years = int(self.config.get("train_years", 3))
        test_months = int(self.config.get("test_months", 6))
        step_months = int(self.config.get("step_months", test_months))
        if min(train_years, test_months, step_months) <= 0:
            raise ValueError("Walk-forward durations must be positive")
        if step_months < test_months:
            raise ValueError("step_months must be >= test_months so test folds do not overlap")
        if data.empty:
            return []
        first_test_start = data.Date.min() + pd.DateOffset(years=train_years)
        maximum_time = data.Date.max()
        folds, fold_id, test_start = [], 1, first_test_start
        while test_start < maximum_time:
            train_start = test_start - pd.DateOffset(years=train_years)
            train_end = test_start - pd.Timedelta(minutes=self.horizon)
            test_end = test_start + pd.DateOffset(months=test_months)
            train = data[(data.Date >= train_start) & (data.Date < test_start)
                         & (data.target_time <= train_end)].copy()
            test = data[(data.Date >= test_start) & (data.Date < test_end)
                        & (data.target_time < test_end)].copy()
            if not train.empty and not test.empty:
                if train.target_time.max() >= test.Date.min():
                    raise AssertionError("Walk-forward target crosses the train/test boundary")
                folds.append(WalkForwardFold(fold_id, train, test))
                fold_id += 1
            test_start += pd.DateOffset(months=step_months)
        return folds

    def _new_model(self, model_class):
        return model_class() if inspect.isclass(model_class) else model_class()

    def validate(self, model_class):
        """Fit train-only scalers/models and return price-level per-fold metrics."""
        rows = []
        feature_columns = self.config.get("feature_columns", FEATURE_COLUMNS)
        for fold in self.generate_folds():
            scaler = StandardScaler().fit(fold.train[feature_columns])
            model = self._new_model(model_class)
            model.fit(scaler.transform(fold.train[feature_columns]), fold.train["target_return"])
            predicted_return = np.asarray(model.predict(scaler.transform(fold.test[feature_columns])), dtype=float)
            current = fold.test["Close"].to_numpy(dtype=float)
            actual = fold.test["target_close"].to_numpy(dtype=float)
            predicted = current * (1 + predicted_return)
            baseline_prediction = PersistenceBaseline(self.horizon).predict(current)
            model_metrics = comparison_metrics(actual, predicted, current)
            baseline_metrics = comparison_metrics(actual, baseline_prediction, current)
            strategy_returns = np.sign(predicted_return) * fold.test["target_return"].to_numpy(dtype=float)
            sharpe = 0.0 if np.std(strategy_returns) == 0 else float(
                np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252 * 24 * 60 / self.horizon)
            )
            training_atr = _atr(fold.train).median()
            improvement = ((baseline_metrics["mae"] - model_metrics["mae"]) / baseline_metrics["mae"] * 100
                           if baseline_metrics["mae"] else 0.0)
            rows.append({
                "fold_id": fold.fold_id, "horizon_minutes": self.horizon,
                "train_start": fold.train.Date.min(), "train_end": fold.train.Date.max(),
                "test_start": fold.test.Date.min(), "test_end": fold.test.Date.max(),
                "train_rows": len(fold.train), "test_rows": len(fold.test),
                "mae": model_metrics["mae"], "rmse": model_metrics["rmse"],
                "directional_accuracy": model_metrics["directional_accuracy"], "mape": model_metrics["mape"],
                "sharpe": sharpe, "persistence_mae": baseline_metrics["mae"],
                "persistence_rmse": baseline_metrics["rmse"],
                "persistence_directional_accuracy": baseline_metrics["directional_accuracy"],
                "mae_improvement_pct": improvement,
                "market_regime": classify_regime(fold.test, training_atr),
            })
        return pd.DataFrame(rows)

    def assess_stability(self, results):
        if results.empty:
            return {"stable": False, "reason": "No valid walk-forward folds", "fold_count": 0}
        mean_mae = float(results.mae.mean())
        coefficient = float(results.mae.std(ddof=0) / mean_mae) if mean_mae else float("inf")
        beat_rate = float((results.mae < results.persistence_mae).mean())
        median_mae = float(results.mae.median())
        catastrophic = int((results.mae > 2 * median_mae).sum()) if median_mae else len(results)
        stable = coefficient < .20 and beat_rate > .80 and catastrophic == 0
        return {
            "stable": bool(stable), "fold_count": len(results), "mae_coefficient_of_variation": coefficient,
            "persistence_win_rate": beat_rate, "catastrophic_failure_count": catastrophic,
            "reason": "Passed all stability criteria" if stable else "One or more stability criteria failed",
        }
