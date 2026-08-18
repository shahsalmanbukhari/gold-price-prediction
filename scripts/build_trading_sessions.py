#!/usr/bin/env python3
"""Rebuild trading_sessions server-side from canonical 1m candles."""

import argparse
import json
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
from datetime import timezone

LOCK_ID = 476655019
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def rebuild(dsn, provider="histdata", symbol="XAUUSD", gap_threshold=5):
    if gap_threshold <= 1:
        raise ValueError("gap threshold must be greater than one minute")
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            cursor.execute("""
                SELECT COUNT(*), MIN(candle_time), MAX(candle_time)
                FROM gold_price_candles
                WHERE provider=%s AND symbol=%s AND timeframe='1m'
            """, (provider, symbol))
            candle_count, minimum, maximum = cursor.fetchone()
            if not candle_count:
                raise RuntimeError("No matching canonical 1m candles; refusing to create empty sessions")
            cursor.execute("DELETE FROM trading_sessions WHERE provider=%s AND symbol=%s", (provider, symbol))
            cursor.execute("""
                INSERT INTO trading_sessions
                    (provider, symbol, session_start, session_end, candle_count, duration_minutes)
                WITH ordered AS (
                    SELECT candle_time,
                           LAG(candle_time) OVER (ORDER BY candle_time) AS previous_time
                    FROM gold_price_candles
                    WHERE provider=%s AND symbol=%s AND timeframe='1m'
                ), marked AS (
                    SELECT candle_time,
                           CASE WHEN previous_time IS NULL
                                  OR candle_time - previous_time >= (%s * INTERVAL '1 minute')
                                THEN 1 ELSE 0 END AS starts_session
                    FROM ordered
                ), grouped AS (
                    SELECT candle_time,
                           SUM(starts_session) OVER (ORDER BY candle_time) AS session_number
                    FROM marked
                )
                SELECT %s, %s,
                       (MIN(candle_time) AT TIME ZONE 'UTC'),
                       (MAX(candle_time) AT TIME ZONE 'UTC'),
                       COUNT(*)::INTEGER,
                       (EXTRACT(EPOCH FROM (MAX(candle_time)-MIN(candle_time)))/60)::INTEGER + 1
                FROM grouped
                GROUP BY session_number
                ORDER BY MIN(candle_time)
            """, (provider, symbol, gap_threshold, provider, symbol))
            inserted_sessions = cursor.rowcount
            cursor.execute("""
                SELECT COUNT(*), COALESCE(SUM(candle_count),0), MIN(session_start), MAX(session_end)
                FROM trading_sessions WHERE provider=%s AND symbol=%s
            """, (provider, symbol))
            session_count, represented, session_min, session_max = cursor.fetchone()
            expected_min = minimum.astimezone(timezone.utc).replace(tzinfo=None)
            expected_max = maximum.astimezone(timezone.utc).replace(tzinfo=None)
            if represented != candle_count or session_min != expected_min or session_max != expected_max:
                raise RuntimeError("Session rebuild invariant failed; transaction will roll back")
        connection.commit()
    return {"provider": provider, "symbol": symbol, "gap_threshold_minutes": gap_threshold,
            "candle_count": candle_count, "session_count": session_count,
            "inserted_sessions": inserted_sessions, "minimum": minimum, "maximum": maximum}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gap-threshold", type=int, default=5)
    parser.add_argument("--provider", default="histdata")
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL is required")
    print(json.dumps(rebuild(dsn, args.provider, args.symbol, args.gap_threshold), indent=2, default=str))


if __name__ == "__main__":
    main()
