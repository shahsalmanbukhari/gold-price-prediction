"""Trading-session construction and persistence for completed candle data."""

from __future__ import annotations

from datetime import timezone
from typing import Iterable

import pandas as pd

from src.database import TradingSession


def build_sessions(df: pd.DataFrame, gap_threshold_minutes: int = 5) -> list[pd.DataFrame]:
    """Split candles into chronological sessions at gaps >= ``gap_threshold_minutes``.

    Session fields are descriptive metadata.  In particular, progress and remaining
    values must not be added to the production model feature schema because the end
    of a live session is not known at inference time.
    """
    if gap_threshold_minutes <= 1:
        raise ValueError("gap_threshold_minutes must be greater than one")
    if "Date" not in df.columns:
        raise ValueError("Candle frame must contain a Date column")
    if df.empty:
        return []

    ordered = df.copy()
    ordered["Date"] = pd.to_datetime(ordered["Date"], utc=True, errors="raise")
    ordered = ordered.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)
    gaps = ordered["Date"].diff()
    group_ids = gaps.ge(pd.Timedelta(minutes=gap_threshold_minutes)).fillna(False).cumsum()
    session_count = int(group_ids.nunique())
    sessions: list[pd.DataFrame] = []

    for ordinal, (_, group) in enumerate(ordered.groupby(group_ids, sort=True), start=1):
        result = group.copy().reset_index(drop=True)
        start, end = result["Date"].iloc[0], result["Date"].iloc[-1]
        count = len(result)
        result["session_id"] = ordinal
        result["session_start"] = start
        result["session_end"] = end
        result["session_minute"] = range(1, count + 1)
        result["session_minute_pct"] = (
            0.0 if count == 1 else (result["session_minute"] - 1) / (count - 1)
        )
        result["session_remaining"] = count - result["session_minute"]
        result["session_count"] = session_count
        sessions.append(result)
    return sessions


def session_metadata(sessions: Iterable[pd.DataFrame]) -> list[dict]:
    """Return normalized database rows for non-empty built sessions."""
    rows = []
    for frame in sessions:
        if frame.empty:
            continue
        start = pd.Timestamp(frame["session_start"].iloc[0]).tz_convert("UTC")
        end = pd.Timestamp(frame["session_end"].iloc[0]).tz_convert("UTC")
        # The mandated table uses TIMESTAMP without timezone; persist canonical
        # naive UTC values and convert back to aware UTC at application boundaries.
        rows.append({
            "session_start": start.to_pydatetime().replace(tzinfo=None),
            "session_end": end.to_pydatetime().replace(tzinfo=None),
            "candle_count": int(len(frame)),
            "duration_minutes": int((end - start).total_seconds() // 60) + 1,
        })
    return rows


def persist_sessions(db_session, sessions: Iterable[pd.DataFrame], provider: str, symbol: str) -> int:
    """Idempotently persist newly discovered session metadata."""
    inserted = 0
    for values in session_metadata(sessions):
        exists = db_session.query(TradingSession.id).filter(
            TradingSession.provider == provider,
            TradingSession.symbol == symbol,
            TradingSession.session_start == values["session_start"],
            TradingSession.session_end == values["session_end"],
        ).first()
        if exists:
            continue
        db_session.add(TradingSession(provider=provider, symbol=symbol, **values))
        inserted += 1
    db_session.flush()
    return inserted


def assert_targets_within_sessions(dataset: pd.DataFrame) -> None:
    """Fail fast if a training target crosses a session or lacks exact timing."""
    required = {"Date", "target_time", "session_id", "target_session_id", "horizon_minutes"}
    missing = required.difference(dataset.columns)
    if missing:
        raise ValueError(f"Dataset lacks session validation columns: {sorted(missing)}")
    same_session = dataset["session_id"].eq(dataset["target_session_id"])
    exact_time = (
        pd.to_datetime(dataset["target_time"], utc=True)
        - pd.to_datetime(dataset["Date"], utc=True)
    ).eq(pd.to_timedelta(dataset["horizon_minutes"], unit="m"))
    if not same_session.all() or not exact_time.all():
        raise AssertionError("Training target crosses a session boundary or has a non-exact timestamp")
