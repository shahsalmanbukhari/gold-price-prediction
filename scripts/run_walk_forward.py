#!/usr/bin/env python3
"""Run and persist chronological walk-forward validation evidence."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from src.candle_data_service import CandleDataService
from src.candle_features import HORIZONS, build_horizon_dataset, candles_to_frame
from src.database import WalkForwardResult, get_session
from src.walk_forward import WalkForwardValidator


def model_factory(name):
    if name == "linear_regression":
        return LinearRegression
    if name == "random_forest":
        return lambda: RandomForestRegressor(n_estimators=100, max_depth=14, random_state=42, n_jobs=-1)
    if name == "xgboost":
        from xgboost import XGBRegressor
        return lambda: XGBRegressor(n_estimators=200, max_depth=5, learning_rate=.05, random_state=42, n_jobs=-1)
    raise ValueError(f"Unsupported model: {name}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", default="15,30,60")
    parser.add_argument("--min-folds", type=int, default=6)
    parser.add_argument("--train-years", type=int, default=3)
    parser.add_argument("--test-months", type=int, default=6)
    parser.add_argument("--step-months", type=int, default=6)
    parser.add_argument("--model", choices=("linear_regression", "random_forest", "xgboost"), default="linear_regression")
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--max-candles", type=int, default=None,
                        help="Optional newest-candle cap; omit to validate the complete history")
    return parser.parse_args()


def main():
    args = parse_args()
    horizons = [int(value) for value in args.horizons.split(",")]
    invalid = set(horizons).difference(HORIZONS)
    if invalid:
        raise SystemExit(f"Unsupported horizons: {sorted(invalid)}")
    if args.min_folds < 1:
        raise SystemExit("--min-folds must be positive")
    version = args.model_version or datetime.now(timezone.utc).strftime("wf-%Y%m%dT%H%M%SZ")
    session = get_session()
    try:
        candles = CandleDataService(session).completed_1m(limit=args.max_candles)
        raw = candles_to_frame(candles)
        if raw.empty:
            raise SystemExit("No HistData XAUUSD 1m candles are available")
        exit_code = 0
        for horizon in horizons:
            dataset = build_horizon_dataset(raw, horizon)
            validator = WalkForwardValidator(dataset, horizon, {
                "train_years": args.train_years, "test_months": args.test_months,
                "step_months": args.step_months,
            })
            results = validator.validate(model_factory(args.model))
            stability = validator.assess_stability(results)
            if len(results) < args.min_folds:
                stability.update(stable=False, reason=f"Only {len(results)} folds; minimum is {args.min_folds}")
                exit_code = 2
            for row in results.to_dict("records"):
                session.add(WalkForwardResult(
                    model_name=args.model, model_version=version, horizon_minutes=horizon,
                    fold_id=row["fold_id"], train_start=row["train_start"].to_pydatetime().replace(tzinfo=None),
                    train_end=row["train_end"].to_pydatetime().replace(tzinfo=None),
                    test_start=row["test_start"].to_pydatetime().replace(tzinfo=None),
                    test_end=row["test_end"].to_pydatetime().replace(tzinfo=None),
                    train_rows=row["train_rows"], test_rows=row["test_rows"], mae=row["mae"], rmse=row["rmse"],
                    directional_accuracy=row["directional_accuracy"], persistence_mae=row["persistence_mae"],
                    mae_improvement_pct=row["mae_improvement_pct"], market_regime=row["market_regime"],
                ))
            session.commit()
            print(f"{horizon}m: folds={len(results)} stable={stability['stable']} "
                  f"persistence_win_rate={stability.get('persistence_win_rate', 0):.1%} "
                  f"MAE_CV={stability.get('mae_coefficient_of_variation', float('nan')):.3f}")
        return exit_code
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
