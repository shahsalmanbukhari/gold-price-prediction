"""Repositories for historical candles and their import audit records."""

from datetime import datetime
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.database import GoldPriceCandle, HistoricalDataImport


class GoldPriceCandleRepository:
    """Persistence boundary used exclusively by the historical importer."""

    def __init__(self, session):
        self.session = session

    def upsert_batch(self, candles: list[dict]) -> tuple[int, int]:
        if not candles:
            return 0, 0
        # Collapse duplicate keys inside the current batch before DB conflict handling.
        unique = {
            (row["provider"], row["symbol"], row["timeframe"], row["candle_time"]): row
            for row in candles
        }
        duplicate_count = len(candles) - len(unique)
        rows = list(unique.values())
        dialect = self.session.bind.dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(GoldPriceCandle).values(rows).on_conflict_do_nothing(
                constraint="uq_gold_price_candle"
            )
        elif dialect == "sqlite":
            statement = sqlite_insert(GoldPriceCandle).values(rows).on_conflict_do_nothing(
                index_elements=["provider", "symbol", "timeframe", "candle_time"]
            )
        else:
            raise RuntimeError(f"Unsupported import database dialect: {dialect}")
        result = self.session.execute(statement)
        self.session.commit()
        inserted = max(0, result.rowcount or 0)
        return inserted, duplicate_count + len(rows) - inserted

    def aggregate(self, timeframe: str, start: datetime, end: datetime):
        """Aggregate stored 1m candles on demand using PostgreSQL date_bin."""
        minutes = {"3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}.get(timeframe)
        if minutes is None:
            raise ValueError(f"Unsupported aggregate timeframe: {timeframe}")
        query = text("""
            SELECT
                date_bin(make_interval(mins => :minutes), candle_time,
                         TIMESTAMPTZ '1970-01-01 00:00:00+00') AS candle_time,
                (array_agg(open_price ORDER BY candle_time ASC))[1] AS open_price,
                MAX(high_price) AS high_price,
                MIN(low_price) AS low_price,
                (array_agg(close_price ORDER BY candle_time DESC))[1] AS close_price,
                SUM(volume) AS volume
            FROM gold_price_candles
            WHERE provider = 'histdata' AND symbol = 'XAUUSD' AND timeframe = '1m'
              AND candle_time >= :start AND candle_time < :end
            GROUP BY 1 ORDER BY 1
        """)
        return self.session.execute(query, {"minutes": minutes, "start": start, "end": end}).mappings().all()


class HistoricalDataImportRepository:
    def __init__(self, session):
        self.session = session

    def start(self, source_zip: str, source_csv: str | None = None, checksum: str | None = None):
        record = HistoricalDataImport(
            provider="histdata", symbol="XAUUSD", timeframe="1m",
            source_zip=source_zip[:255], source_csv=source_csv[:255] if source_csv else None,
            file_checksum=checksum, status="running",
        )
        self.session.add(record)
        self.session.commit()
        return record

    def complete(self, record, status: str, checksum: str | None = None, error: str | None = None):
        record.status = status
        record.file_checksum = checksum or record.file_checksum
        record.error_message = error
        record.completed_at = datetime.now().astimezone()
        self.session.commit()
