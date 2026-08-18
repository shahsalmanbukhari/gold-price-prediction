"""Durable baseline-relative scheduler for safe candidate training/promotion."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy import func

from src.database import (
    GoldPriceCandle, HorizonPrediction, RetrainingRun, TrainingSchedulerState, get_session,
)
from src.model_pipeline import (
    CandidateRejectedError, ModelBundleManager, MultiHorizonTrainer, training_lock,
)


class BackgroundTrainingScheduler:
    def __init__(self, min_new_records=50, retrain_interval_hours=24,
                 check_interval_seconds=60, model_name="linear_regression",
                 session_factory=get_session, manager_factory=ModelBundleManager,
                 trainer_factory=MultiHorizonTrainer):
        self.min_new_records = max(1, min_new_records)
        self.retrain_interval = timedelta(hours=max(.01, retrain_interval_hours))
        self.check_interval_seconds = max(1, check_interval_seconds)
        self.model_name = model_name
        self._stop_event = asyncio.Event()
        self._training_task: Optional[asyncio.Task] = None
        self.session_factory = session_factory
        self.manager_factory = manager_factory
        self.trainer_factory = trainer_factory
        self._ensure_state()

    def _ensure_state(self):
        session = self.session_factory()
        try:
            if session.get(TrainingSchedulerState, 1) is None:
                session.add(TrainingSchedulerState(id=1))
                session.commit()
        finally:
            session.close()

    def _trigger_reason(self):
        session = self.session_factory()
        try:
            # Initial training is always an explicit CLI operation. Without an
            # approved production manifest there is nothing safe to retrain or
            # compare, so ordinary startup must remain idle.
            if not self.manager_factory().production_manifest_path.exists():
                return None
            state = session.get(TrainingSchedulerState, 1)
            manual = session.query(RetrainingRun).filter(
                func.lower(RetrainingRun.status) == "pending"
            ).order_by(RetrainingRun.requested_at).first()
            if manual:
                return "manual"
            now = datetime.now(timezone.utc)
            attempt = state.last_training_attempt_at
            if attempt and attempt.tzinfo is None:
                attempt = attempt.replace(tzinfo=timezone.utc)
            # A rejected or failed candidate must not cause a rapid restart loop.
            if attempt and now - attempt < timedelta(hours=1):
                return None
            last = state.last_successful_training_at
            if last and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last is None or now - last >= self.retrain_interval:
                return "scheduled"
            candle_count = session.query(func.count(GoldPriceCandle.id)).filter(
                GoldPriceCandle.id > state.last_candle_id,
                GoldPriceCandle.provider == "histdata", GoldPriceCandle.symbol == "XAUUSD",
                GoldPriceCandle.timeframe == "1m",
            ).scalar() or 0
            if candle_count >= self.min_new_records:
                return "new_candles"
            # Trigger only from sufficiently sampled production outcomes and
            # baseline-relative/directional degradation, never closeness score.
            version = self.manager_factory().load_manifest().get("model_version")
            for horizon in (3, 5, 15, 30, 60, 240):
                rows = session.query(HorizonPrediction).filter(
                    HorizonPrediction.id > state.last_outcome_id,
                    HorizonPrediction.status == "EVALUATED",
                    HorizonPrediction.model_version == version,
                    HorizonPrediction.horizon_minutes == horizon,
                ).order_by(HorizonPrediction.evaluated_at.desc()).limit(200).all()
                if len(rows) >= self.min_new_records:
                    improvement = sum(float(r.model_improvement_over_baseline) for r in rows) / len(rows)
                    directional = sum(bool(r.direction_correct) for r in rows) / len(rows)
                    if improvement < 0 or directional < .45:
                        return "baseline_degradation"
            return None
        except FileNotFoundError:
            return None  # Initial training is explicit.
        except Exception as exc:
            logger.warning(f"Could not evaluate retraining triggers: {exc}")
            return None
        finally:
            session.close()

    async def trigger(self, force=False):
        if self._training_task and not self._training_task.done():
            return False
        reason = "manual" if force else self._trigger_reason()
        if not reason:
            return False
        self._training_task = asyncio.create_task(self._train(reason))
        return True

    def request_retraining(self, reason="model_degradation"):
        """Persist an idempotent manual review request; training remains asynchronous."""
        session = self.session_factory()
        try:
            existing = session.query(RetrainingRun).filter(
                func.lower(RetrainingRun.status) == "pending",
                RetrainingRun.trigger == reason,
            ).first()
            if existing:
                return existing.id
            run = RetrainingRun(trigger=reason, status="PENDING", model_name=self.model_name)
            session.add(run)
            session.commit()
            return run.id
        finally:
            session.close()

    def _train_sync(self, reason):
        session = self.session_factory()
        run = session.query(RetrainingRun).filter(func.lower(RetrainingRun.status) == "pending").order_by(
            RetrainingRun.requested_at
        ).first()
        if run is None:
            run = RetrainingRun(trigger=reason, status="PENDING", model_name=self.model_name)
            session.add(run)
            session.flush()
        run.status = "RUNNING"
        run.started_at = datetime.now(timezone.utc)
        state = session.get(TrainingSchedulerState, 1)
        state.last_training_attempt_at = run.started_at
        state.updated_at = run.started_at
        session.commit()
        try:
            with training_lock(session):
                manager = self.manager_factory()
                previous = manager.load_manifest().get("model_version") if manager.production_manifest_path.exists() else None
                run.previous_version = previous
                candidate_path = self.trainer_factory(session, manager).train_candidate(self.model_name)
                run.candidate_path = str(candidate_path.parent)
                run.new_version = candidate_path.parent.name
                manifest = manager.promote(candidate_path, initial=False)
                run.status = "PROMOTED"
                run.new_version = manifest["model_version"]
                run.production_changed = True
                run.metrics = {h: item["metrics"]["test"] for h, item in manifest["horizons"].items()}
                run.completed_at = datetime.now(timezone.utc)
                state = session.get(TrainingSchedulerState, 1)
                state.last_candle_id = int(session.query(func.max(GoldPriceCandle.id)).scalar() or 0)
                state.last_outcome_id = int(session.query(func.max(HorizonPrediction.id)).filter(
                    HorizonPrediction.status == "EVALUATED").scalar() or 0)
                state.last_successful_training_at = run.completed_at
                state.updated_at = run.completed_at
                session.commit()
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
            state.last_candle_id = int(session.query(func.max(GoldPriceCandle.id)).scalar() or 0)
            state.last_outcome_id = int(session.query(func.max(HorizonPrediction.id)).filter(
                HorizonPrediction.status == "EVALUATED").scalar() or 0)
            state.updated_at = run.completed_at
            session.commit()
            first = next(
                (reason for reason in exc.reasons if reason.get("criterion") == "worse_than_persistence"),
                exc.reasons[0],
            )
            logger.warning(
                "Candidate {} was rejected. {}m test MAE was {:.2f}% worse than persistence. "
                "Production model remains unchanged. Candidate bundle: {}",
                run.new_version, first.get("horizon"),
                abs(float(first.get("percentage_improvement") or 0)), exc.candidate_path,
            )
        except Exception as exc:
            session.rollback()
            run = session.get(RetrainingRun, run.id)
            run.status = "FAILED"
            run.production_changed = False
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            state = session.get(TrainingSchedulerState, 1)
            state.last_training_attempt_at = run.completed_at
            state.updated_at = run.completed_at
            session.commit()
            logger.exception(f"Candidate training/promotion failed: {exc}")
        finally:
            session.close()

    async def _train(self, reason):
        await asyncio.to_thread(self._train_sync, reason)

    async def run(self):
        logger.info("Durable model scheduler started")
        while not self._stop_event.is_set():
            await self.trigger()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.check_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def stop(self):
        self._stop_event.set()
        if self._training_task and not self._training_task.done():
            await self._training_task
