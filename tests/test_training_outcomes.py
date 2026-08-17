import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dashboard_pages import build_training_metric_chart_data, build_training_metrics_figure
from realtime.training_scheduler import BackgroundTrainingScheduler
from src.database import Base, RetrainingRun, TrainingSchedulerState
from src.model_pipeline import CandidateRejectedError


def metrics(mae=.11, persistence_mae=.10, rmse=.22, persistence_rmse=.20):
    return {
        "mae": mae, "persistence_mae": persistence_mae,
        "rmse": rmse, "persistence_rmse": persistence_rmse,
        "directional_accuracy": 48.0, "common_direction_accuracy": 51.0,
    }


class DashboardMetricTransformationTests(unittest.TestCase):
    def test_empty_missing_and_null_metrics(self):
        self.assertTrue(build_training_metric_chart_data([]).empty)
        rows = [
            {"completed_at": datetime.now(timezone.utc), "metrics": None},
            {"completed_at": None, "metrics": {"3": metrics()}},
            {"completed_at": datetime.now(timezone.utc), "metrics": {"3": {"mae": None}}},
        ]
        self.assertTrue(build_training_metric_chart_data(rows).empty)
        self.assertIsNone(build_training_metrics_figure(rows))

    def test_rejected_mixed_json_metrics_create_long_figure(self):
        rows = [{
            "completed_at": "2026-08-17T04:00:00+00:00", "new_version": "candidate-a",
            "model_name": "linear_regression", "status": "REJECTED",
            "metrics": {"horizons": {
                "3": {"mae": "0.11", "persistence_mae": .10, "rmse": None, "persistence_rmse": ".20"},
                "5": metrics(.2, .19, .3, .29),
                "metadata": "ignored",
            }},
        }]
        chart = build_training_metric_chart_data(rows)
        self.assertEqual(set(chart.horizon), {3, 5})
        self.assertTrue(chart.value.map(lambda value: isinstance(value, float)).all())
        self.assertEqual(set(chart.status), {"REJECTED"})
        self.assertIsNotNone(build_training_metrics_figure(rows))

    def test_multiple_versions_and_successful_single_run(self):
        now = datetime.now(timezone.utc)
        rows = [
            {"completed_at": now, "new_version": "v1", "model_name": "linear_regression",
             "status": "PROMOTED", "metrics": {"3": metrics()}},
            {"completed_at": now.isoformat(), "new_version": "v2", "model_name": "random_forest",
             "status": "REJECTED", "metrics": {"3": metrics(.12, .1), "240": metrics(.4, .3)}},
        ]
        chart = build_training_metric_chart_data(rows)
        self.assertEqual(set(chart.candidate_version), {"v1", "v2"})
        self.assertEqual(set(chart.horizon), {3, 240})
        self.assertIsNotNone(build_training_metrics_figure(rows[:1]))


class _FakeManager:
    def __init__(self, root, outcome):
        self.root = Path(root)
        self.production_manifest_path = self.root / "production" / "manifest.json"
        self.production_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.production_manifest_path.write_text('{"model_version":"production-v1"}')
        self.outcome = outcome

    def load_manifest(self):
        return {"model_version": "production-v1"}

    def promote(self, candidate, initial=False):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _FakeTrainer:
    def __init__(self, session, manager, candidate, failure=None):
        self.candidate = candidate
        self.failure = failure

    def train_candidate(self, algorithm):
        if self.failure:
            raise self.failure
        return self.candidate


class SchedulerOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        session = self.Session()
        session.add(TrainingSchedulerState(id=1))
        session.commit()
        session.close()
        self.candidate = Path(self.temp.name) / "candidates" / "candidate-v2" / "manifest.json"
        self.candidate.parent.mkdir(parents=True)
        self.candidate.write_text("{}")

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def scheduler(self, manager, trainer):
        return BackgroundTrainingScheduler(
            session_factory=self.Session, manager_factory=lambda: manager,
            trainer_factory=lambda session, selected: trainer,
        )

    def latest_run(self):
        session = self.Session()
        try:
            return session.query(RetrainingRun).order_by(RetrainingRun.id.desc()).first()
        finally:
            session.close()

    def test_rejection_is_expected_preserved_and_scheduler_survives(self):
        reason = {"criterion": "worse_than_persistence", "horizon": 3,
                  "candidate_mae": .11, "persistence_mae": .10,
                  "candidate_rmse": .22, "persistence_rmse": .20,
                  "absolute_difference": .01, "percentage_improvement": -10,
                  "test_sample_count": 1000, "candidate_directional_accuracy": 48,
                  "baseline_directional_accuracy": 51}
        rejection = CandidateRejectedError([reason], {"3": metrics()}, self.candidate.parent)
        manager = _FakeManager(self.temp.name, rejection)
        trainer = _FakeTrainer(None, None, self.candidate)
        scheduler = self.scheduler(manager, trainer)
        with patch("realtime.training_scheduler.logger.warning") as warning, \
             patch("realtime.training_scheduler.logger.exception") as unexpected:
            asyncio.run(scheduler._train("manual"))
            warning.assert_called_once()
            unexpected.assert_not_called()
        run = self.latest_run()
        self.assertEqual(run.status, "REJECTED")
        self.assertFalse(run.production_changed)
        self.assertEqual(run.candidate_path, str(self.candidate.parent))
        self.assertEqual(run.metrics["rejection_reasons"][0]["horizon"], 3)
        self.assertTrue(manager.production_manifest_path.exists())

    def test_unexpected_training_failure_is_failed(self):
        manager = _FakeManager(self.temp.name, {})
        trainer = _FakeTrainer(None, None, self.candidate, OSError("disk failure"))
        scheduler = self.scheduler(manager, trainer)
        with patch("realtime.training_scheduler.logger.exception") as logged:
            scheduler._train_sync("manual")
            logged.assert_called_once()
        run = self.latest_run()
        self.assertEqual(run.status, "FAILED")
        self.assertFalse(run.production_changed)

    def test_valid_candidate_is_promoted(self):
        manifest = {"model_version": "candidate-v2", "horizons": {
            str(h): {"metrics": {"test": metrics(.09, .10, .18, .20)}}
            for h in (3, 5, 15, 30, 60, 240)
        }}
        manager = _FakeManager(self.temp.name, manifest)
        trainer = _FakeTrainer(None, None, self.candidate)
        self.scheduler(manager, trainer)._train_sync("manual")
        run = self.latest_run()
        self.assertEqual(run.status, "PROMOTED")
        self.assertTrue(run.production_changed)
        self.assertEqual(run.new_version, "candidate-v2")


if __name__ == "__main__":
    unittest.main()
