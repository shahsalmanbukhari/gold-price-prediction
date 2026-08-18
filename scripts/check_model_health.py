#!/usr/bin/env python3
"""Check durable rolling model health by horizon."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database import get_session
from src.model_health import monitor_from_predictions
from src.model_pipeline import ModelBundleManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", default="15,30,60")
    parser.add_argument("--model-version")
    parser.add_argument("--window-size", type=int, default=100)
    parser.add_argument("--alert-on-degradation", action="store_true")
    args = parser.parse_args()
    version = args.model_version
    if not version:
        try:
            version = ModelBundleManager().load_manifest()["model_version"]
        except FileNotFoundError:
            raise SystemExit("No production model exists; pass --model-version to inspect historical results")
    session = get_session()
    degraded = False
    try:
        for horizon in [int(value) for value in args.horizons.split(",") if value.strip()]:
            monitor = monitor_from_predictions(session, horizon, version, args.window_size)
            metrics = monitor._compute_metrics(monitor.predictions) if monitor.predictions else {
                "model_mae": float("nan"), "persistence_mae": float("nan"),
                "directional_accuracy": float("nan"), "n_samples": 0,
            }
            print(f"{horizon}m {version}: {monitor.status} samples={metrics['n_samples']} "
                  f"MAE={metrics['model_mae']:.4f} persistence={metrics['persistence_mae']:.4f} "
                  f"direction={metrics['directional_accuracy']:.1%}")
            degraded |= monitor.status == "DEGRADED"
        session.commit()
    finally:
        session.close()
    return 2 if degraded and args.alert_on_degradation else 0


if __name__ == "__main__":
    raise SystemExit(main())
