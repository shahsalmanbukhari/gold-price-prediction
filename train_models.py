#!/usr/bin/env python3
"""Explicit initial training and guarded retraining entry point."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from config.settings import get_settings
from src.database import RetrainingRun, TrainingSchedulerState, get_session
from src.model_pipeline import CandidateRejectedError, ModelBundleManager, MultiHorizonTrainer, training_lock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("train", "retrain"))
    parser.add_argument("--algorithm", default=get_settings().ml.default_model,
                        choices=("benchmark", "linear_regression", "random_forest", "xgboost"))
    args = parser.parse_args()
    session = get_session()
    manager = ModelBundleManager()
    if args.mode == "train" and manager.production_manifest_path.exists():
        raise SystemExit("Initial training refused: an approved production bundle already exists; use --retrain")
    if args.mode == "retrain" and not manager.production_manifest_path.exists():
        raise SystemExit("Retraining refused: no approved production bundle exists; use --train")
    run = RetrainingRun(trigger=f"cli_{args.mode}", status="RUNNING", model_name=args.algorithm,
                        started_at=datetime.now(timezone.utc))
    session.add(run)
    state = session.get(TrainingSchedulerState, 1)
    if state:
        state.last_training_attempt_at = run.started_at
        state.updated_at = run.started_at
    session.commit()
    try:
        with training_lock(session):
            candidate = MultiHorizonTrainer(session, manager).train_candidate(args.algorithm)
            run.candidate_path = str(candidate.parent)
            run.new_version = candidate.parent.name
            manifest = manager.promote(candidate, initial=args.mode == "train")
            run.status = "PROMOTED"
            run.new_version = manifest["model_version"]
            run.production_changed = True
            run.completed_at = datetime.now(timezone.utc)
            run.metrics = {h: item["metrics"]["test"] for h, item in manifest["horizons"].items()}
            state = session.get(TrainingSchedulerState, 1)
            if state:
                state.last_successful_training_at = run.completed_at
                state.updated_at = run.completed_at
            session.commit()
            print(json.dumps({"promotion": "PROMOTED", "model_version": manifest["model_version"],
                              "test_metrics": run.metrics}, indent=2))
    except CandidateRejectedError as exc:
        session.rollback()
        run = session.get(RetrainingRun, run.id)
        run.status = "REJECTED"
        run.new_version = Path(exc.candidate_path).name if exc.candidate_path else run.new_version
        run.candidate_path = exc.candidate_path
        run.production_changed = False
        run.metrics = {"horizons": exc.metrics, "rejection_reasons": exc.reasons}
        run.error_analysis = {"rejection_reasons": exc.reasons}
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        state = session.get(TrainingSchedulerState, 1)
        if state:
            state.last_training_attempt_at = run.completed_at
            state.updated_at = run.completed_at
        session.commit()
        print(json.dumps({"promotion": "REJECTED", "candidate_version": run.new_version,
                          "candidate_path": run.candidate_path, "production_changed": False,
                          "reasons": exc.reasons, "test_metrics": exc.metrics}, indent=2))
    except Exception as exc:
        session.rollback()
        run = session.get(RetrainingRun, run.id)
        run.status = "FAILED"
        run.production_changed = False
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
