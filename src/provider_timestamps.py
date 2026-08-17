"""Strict provider timestamp parsing and validation."""
from datetime import datetime, timezone
from numbers import Real
from typing import Any


class AmbiguousProviderTimestamp(ValueError):
    pass


def parse_provider_timestamp(value: Any) -> datetime:
    """Parse ISO-8601 or Unix seconds/milliseconds into aware UTC."""
    if value is None or value == "":
        raise AmbiguousProviderTimestamp("provider timestamp is missing")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        # Current Unix milliseconds are 13 digits; seconds are 10 digits.
        if abs(numeric) >= 100_000_000_000:
            numeric /= 1000.0
        parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AmbiguousProviderTimestamp("naive provider timestamp is not accepted")
    return parsed.astimezone(timezone.utc)


def timestamp_evidence(field_name, raw, parsed, provider, request_started_at, request_completed_at, now=None):
    now = now or datetime.now(timezone.utc)
    return {
        "provider": provider,
        "raw_timestamp_field": field_name,
        "raw_timestamp_value": raw,
        "raw_timestamp_type": type(raw).__name__,
        "parsed_offset": str(parsed.utcoffset()),
        "parsed_provider_timestamp_utc": parsed.isoformat(),
        "server_utc_now": now.isoformat(),
        "difference_seconds": round((parsed - now).total_seconds(), 3),
        "request_started_at": request_started_at.isoformat(),
        "request_completed_at": request_completed_at.isoformat(),
    }
