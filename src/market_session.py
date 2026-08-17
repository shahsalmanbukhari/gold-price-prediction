"""Minimal explicit XAU/USD weekend-session policy in UTC."""
from datetime import datetime, timezone

WEEKLY_CLOSE_HOUR_UTC = 22


def aware_utc(value):
    if value is None: return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("market timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def is_expected_market_closure(now: datetime) -> bool:
    now = aware_utc(now)
    weekday = now.weekday()  # Monday=0
    return weekday == 5 or (weekday == 4 and now.hour >= WEEKLY_CLOSE_HOUR_UTC) or (weekday == 6 and now.hour < WEEKLY_CLOSE_HOUR_UTC)


def candle_context(candle_time, now, freshness_seconds):
    now, candle_time = aware_utc(now), aware_utc(candle_time) if candle_time else None
    if candle_time is None:
        return "NO_DATA", "No completed one-minute candle is available", False
    age = max(0, int((now-candle_time).total_seconds()))
    if is_expected_market_closure(now):
        return "MARKET_CLOSED", "Candle context retained from the last market session", False
    if age > freshness_seconds:
        return "STALE_AFTER_REOPEN", "Live quote available, but completed candle context is stale", False
    return "CURRENT", "Completed candle context is current", True
