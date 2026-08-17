"""Single source of truth for dashboard data and worker health."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from src.market_session import candle_context


class Status(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class HealthSummary:
    live_quote_status: str
    worker_status: str
    candle_status: str
    overall_data_status: str
    live_detail: str
    worker_detail: str
    candle_detail: str
    quote_age_seconds: int | None
    candle_age_seconds: int | None
    provider_ahead_seconds: int | None


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def compute_health(live: Any, candle: Any, heartbeat: Any, settings: Any, now=None) -> HealthSummary:
    now = _utc(now) or datetime.now(timezone.utc)
    stream = settings.streaming

    quote_time = _utc(getattr(live, "timestamp", None))
    quote_age = None if quote_time is None else int((now - quote_time).total_seconds())
    ahead = -quote_age if quote_age is not None and quote_age < 0 else None
    if quote_time is None:
        live_status, live_detail = "NO_DATA", "No live provider quote is available"
    elif quote_age < -stream.live_clock_skew_seconds:
        live_status = "INVALID_FUTURE_TIMESTAMP"
        live_detail = f"Provider time is {format_offset(ahead)} ahead of server UTC"
        quote_age = None
    elif quote_age > stream.maximum_live_price_age_seconds:
        live_status, live_detail = "STALE", f"Last quote is {format_age(quote_age)} old"
    else:
        live_status, live_detail = "FRESH", "Provider timestamp is within the freshness window"

    candle_time = _utc(getattr(candle, "candle_time", None))
    candle_age = None if candle_time is None else max(0, int((now - candle_time).total_seconds()))
    candle_status, candle_detail, _ = candle_context(
        candle_time, now, stream.completed_candle_freshness_seconds
    )

    heartbeat_time = _utc(getattr(heartbeat, "last_heartbeat_at", None))
    heartbeat_age = None if heartbeat_time is None else max(0, int((now - heartbeat_time).total_seconds()))
    raw_worker = str(getattr(heartbeat, "status", "") or "").upper()
    last_error = getattr(heartbeat, "last_error", None)
    if heartbeat_time is None or heartbeat_age > stream.worker_unhealthy_after_seconds:
        worker_status = "OFFLINE"
        worker_detail = "No recent background-worker heartbeat"
    elif raw_worker in {"DEGRADED", "FAILED", "ERROR"} or last_error:
        worker_status = "DEGRADED"
        worker_detail = str(last_error or "Worker reported a degraded state")
    else:
        worker_status = "RUNNING"
        worker_detail = f"Heartbeat received {format_age(heartbeat_age)} ago"

    if live_status == "INVALID_FUTURE_TIMESTAMP":
        overall = Status.INVALID.value
    elif worker_status == "OFFLINE":
        overall = Status.OFFLINE.value
    elif worker_status == "DEGRADED":
        overall = Status.DEGRADED.value
    elif live_status in {"NO_DATA", "STALE"} or candle_status in {"NO_DATA", "STALE_AFTER_REOPEN", "MARKET_CLOSED"}:
        overall = Status.WARNING.value
    else:
        overall = Status.HEALTHY.value
    return HealthSummary(live_status, worker_status, candle_status, overall, live_detail,
                         worker_detail, candle_detail, quote_age, candle_age, ahead)


def format_age(seconds):
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def format_offset(seconds):
    if seconds is None:
        return "an unknown interval"
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{seconds // 60}m"
