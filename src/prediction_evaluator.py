"""Concurrency-safe, provider-pinned prediction lifecycle evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from config.settings import get_settings
from src.database import HorizonPrediction, Price

EVALUATOR_VERSION = "bounded_provider_actual_v3"


def aware_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _direction(value, threshold):
    return "up" if value > threshold else "down" if value < -threshold else "stable"


class PredictionEvaluator:
    def __init__(self, tolerance_seconds=90, max_retries=3, on_evaluated=None):
        self.tolerance = tolerance_seconds
        self.max_retries = max_retries
        self.on_evaluated = on_evaluated

    def find_actual_price(self, session, prediction, now):
        target = aware_utc(prediction.target_at)
        deadline = target + timedelta(seconds=prediction.actual_tolerance_seconds or self.tolerance)
        actual = session.query(Price).filter(
            Price.symbol == prediction.symbol, Price.source == "live_api",
            Price.provider == prediction.provider, Price.timestamp >= target,
            Price.timestamp <= deadline, Price.timestamp <= now, Price.price_usd > 0,
        ).order_by(Price.timestamp.asc()).first()
        if actual:
            actual_at = aware_utc(actual.timestamp)
            ingested = aware_utc(actual.ingested_at or actual.created_at or actual.timestamp)
            if actual_at > ingested + timedelta(seconds=get_settings().streaming.live_clock_skew_seconds):
                return None
        return actual

    def evaluate_pending(self, session, prediction, now=None):
        now = aware_utc(now or datetime.now(timezone.utc))
        target = aware_utc(prediction.target_at)
        if target > now:
            return False
        prediction.evaluation_attempts = (prediction.evaluation_attempts or 0) + 1
        prediction.retry_count = (prediction.retry_count or 0) + 1
        prediction.last_evaluation_attempt = now
        try:
            actual = self.find_actual_price(session, prediction, now)
            tolerance_seconds = prediction.actual_tolerance_seconds or self.tolerance
            if actual is None:
                if now < target + timedelta(seconds=tolerance_seconds):
                    return False
                reason = f"No matching {prediction.provider} quote within {tolerance_seconds} seconds"
                prediction.status = "UNRESOLVABLE"
                prediction.unresolvable_reason = reason
                prediction.failure_reason = reason
                prediction.status_reason = reason
                prediction.evaluated_at = now
                prediction.evaluator_version = EVALUATOR_VERSION
                return True
            reference, predicted = Decimal(prediction.reference_price), Decimal(prediction.predicted_price)
            actual_price = Decimal(str(actual.price_usd))
            absolute = abs(actual_price - predicted)
            baseline_error = abs(actual_price - Decimal(prediction.baseline_price))
            actual_return = (actual_price - reference) / reference
            prediction.status = "EVALUATED"
            prediction.actual_price = actual_price
            prediction.actual_at = aware_utc(actual.timestamp)
            prediction.actual_provider = actual.provider
            prediction.evaluation_delay_seconds = max(0, int((prediction.actual_at - target).total_seconds()))
            prediction.evaluator_version = EVALUATOR_VERSION
            prediction.absolute_error = absolute
            prediction.percentage_error = absolute / reference * 100
            prediction.baseline_absolute_error = baseline_error
            prediction.model_improvement_over_baseline = baseline_error - absolute
            prediction.error_amount = float(actual_price - predicted)
            prediction.error_pct = float(absolute / reference * 100)
            prediction.actual_trend = _direction(float(actual_return), float(prediction.direction_threshold))
            prediction.direction_correct = prediction.predicted_trend == prediction.actual_trend
            prediction.evaluated_at = now
            prediction.status_reason = None
            if self.on_evaluated:
                self.on_evaluated(prediction)
            return True
        except Exception as exc:
            attempts = prediction.evaluation_attempts
            prediction.status_reason = str(exc)[:2000]
            if attempts >= (prediction.max_retries or self.max_retries):
                prediction.status = "FAILED"
                prediction.failed_at = now
                prediction.failure_reason = prediction.status_reason
            else:
                prediction.status = "RETRYING"
            return True

    def evaluate_due(self, session, now=None):
        now = aware_utc(now or datetime.now(timezone.utc))
        query = session.query(HorizonPrediction).filter(
            HorizonPrediction.status.in_(("PENDING", "RETRYING")), HorizonPrediction.target_at <= now,
        ).order_by(HorizonPrediction.target_at)
        if session.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        changed = 0
        for prediction in query.all():
            original = prediction.status
            if self.evaluate_pending(session, prediction, now):
                # Conditional state ownership is provided by the row lock on
                # PostgreSQL; SQLite tests run in one process.
                changed += int(prediction.status != original or prediction.status == "EVALUATED")
        session.commit()
        return changed
