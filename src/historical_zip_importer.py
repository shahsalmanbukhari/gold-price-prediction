"""Safe, streaming, directory-based historical XAU/USD ZIP importer."""

import csv
import hashlib
import io
import os
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Optional

from loguru import logger
from config.settings import HistoricalDataSettings, get_settings
from src.candle_repository import GoldPriceCandleRepository, HistoricalDataImportRepository
from src.database import get_session


@dataclass
class ImportSummary:
    directory: str
    zip_files_discovered: int = 0
    zip_files_processed: int = 0
    zip_files_skipped: int = 0
    zip_files_failed: int = 0
    csv_files_imported: int = 0
    total_csv_rows: int = 0
    inserted_candles: int = 0
    duplicate_candles: int = 0
    invalid_rows: int = 0
    elapsed_seconds: float = 0.0


class HashingReader(io.RawIOBase):
    """Update a digest while TextIOWrapper streams an underlying ZIP entry."""

    def __init__(self, raw, digest, maximum_bytes: int):
        self.raw = raw
        self.digest = digest
        self.maximum_bytes = maximum_bytes
        self.bytes_read = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.raw.read(len(buffer))
        size = len(data)
        self.bytes_read += size
        if self.bytes_read > self.maximum_bytes:
            raise ValueError("ZIP entry exceeded maximum uncompressed size while streaming")
        buffer[:size] = data
        if data:
            self.digest.update(data)
        return size


class HistoricalZipImporter:
    """Import every configured archive without accepting caller-supplied paths."""

    PROVIDER = "histdata"
    SYMBOL = "XAUUSD"
    TIMEFRAME = "1m"
    SOURCE_TIMEZONE = timezone(timedelta(hours=-5))

    def __init__(self, settings: Optional[HistoricalDataSettings] = None, session_factory=get_session, schema_initializer=lambda: None):
        self.settings = settings or get_settings().historical_data
        self.session_factory = session_factory
        self.schema_initializer = schema_initializer

    def _validated_directory(self) -> Path:
        root = self.settings.allowed_import_root.expanduser().resolve(strict=True)
        directory = self.settings.import_directory.expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"Allowed import root is not a directory: {root}")
        if not directory.is_dir():
            raise ValueError(f"Import directory is not a directory: {directory}")
        if not directory.is_relative_to(root):
            raise ValueError(f"Import directory must be inside allowed root: {root}")
        if not os.access(directory, os.R_OK | os.X_OK):
            raise ValueError(f"Import directory is not readable: {directory}")
        try:
            next(directory.iterdir(), None)
        except PermissionError as exc:
            raise ValueError(f"Import directory is not readable: {directory}") from exc
        return directory

    @staticmethod
    def _file_checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _safe_csv_entries(self, archive: zipfile.ZipFile):
        entries = archive.infolist()
        if len(entries) > self.settings.maximum_archive_entries:
            raise ValueError(f"archive has {len(entries)} entries; limit is {self.settings.maximum_archive_entries}")
        total_size = sum(entry.file_size for entry in entries if not entry.is_dir())
        if total_size > self.settings.maximum_archive_uncompressed_size:
            raise ValueError("archive exceeds maximum total uncompressed size")
        csv_entries = []
        for entry in entries:
            normalized = entry.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            if entry.is_dir():
                continue
            if path.is_absolute() or ".." in path.parts or (path.parts and path.parts[0].endswith(":")):
                raise ValueError(f"unsafe ZIP entry path: {entry.filename}")
            if entry.flag_bits & 0x1:
                raise ValueError(f"encrypted ZIP entry is not supported: {entry.filename}")
            if entry.file_size > self.settings.maximum_uncompressed_file_size:
                raise ValueError(f"entry exceeds maximum uncompressed size: {entry.filename}")
            ratio = entry.file_size / max(1, entry.compress_size)
            if ratio > self.settings.maximum_compression_ratio:
                raise ValueError(f"suspicious compression ratio for entry: {entry.filename}")
            if path.name.lower().endswith(".csv"):
                csv_entries.append(entry)
        return csv_entries

    @classmethod
    def _parse_timestamp(cls, date_value: str, time_value: Optional[str] = None) -> datetime:
        combined = f"{date_value.strip()} {time_value.strip()}" if time_value else date_value.strip()
        formats = (
            "%Y%m%d %H%M%S", "%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S",
            "%Y.%m.%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
        )
        for fmt in formats:
            try:
                local_time = datetime.strptime(combined, fmt).replace(tzinfo=cls.SOURCE_TIMEZONE)
                return local_time.astimezone(timezone.utc)
            except ValueError:
                continue
        raise ValueError(f"unsupported timestamp: {combined}")

    @classmethod
    def _parse_row(cls, row: list[str]):
        values = [value.strip() for value in row]
        if len(values) < 6:
            raise ValueError("expected at least 6 columns")
        if values[0].lower().strip("<>") in {"date", "timestamp", "datetime", "time"}:
            return None
        if len(values) >= 7:
            timestamp = cls._parse_timestamp(values[0], values[1])
            offset = 2
        else:
            timestamp = cls._parse_timestamp(values[0])
            offset = 1
        open_price, high, low, close = map(Decimal, values[offset:offset + 4])
        raw_volume = Decimal(values[offset + 4]) if len(values) > offset + 4 and values[offset + 4] else None
        volume = raw_volume if raw_volume and raw_volume > 0 else None
        if min(open_price, high, low, close) <= 0 or high < low:
            raise ValueError("invalid OHLC values")
        return timestamp, open_price, high, low, close, volume

    @staticmethod
    def _reader(text_stream) -> Iterator[list[str]]:
        first = text_stream.readline()
        if not first:
            return iter(())
        delimiter = ";" if first.count(";") >= first.count(",") else ","
        return iter(csv.reader(_PrependLine(first, text_stream), delimiter=delimiter))

    def _import_entry(self, archive, entry, audit, candle_repository):
        batch = []
        digest = hashlib.sha256()
        with archive.open(entry, "r") as binary:
            hashing = HashingReader(
                binary, digest, self.settings.maximum_uncompressed_file_size
            )
            with io.TextIOWrapper(io.BufferedReader(hashing), encoding="utf-8-sig", errors="replace", newline="") as text_stream:
                for row in self._reader(text_stream):
                    audit.total_rows += 1
                    try:
                        candle = self._parse_row(row)
                        if candle is None:
                            audit.total_rows -= 1
                            continue
                        timestamp, open_price, high, low, close, volume = candle
                        batch.append({
                            "candle_time": timestamp, "symbol": self.SYMBOL,
                            "timeframe": self.TIMEFRAME, "open_price": open_price,
                            "high_price": high, "low_price": low, "close_price": close,
                            "volume": volume, "provider": self.PROVIDER,
                            "source_file": audit.source_csv,
                        })
                    except (ValueError, TypeError):
                        audit.invalid_rows += 1
                    if len(batch) >= self.settings.batch_size:
                        inserted, duplicates = candle_repository.upsert_batch(batch)
                        audit.inserted_rows += inserted
                        audit.duplicate_rows += duplicates
                        batch.clear()
                inserted, duplicates = candle_repository.upsert_batch(batch)
                audit.inserted_rows += inserted
                audit.duplicate_rows += duplicates
        return digest.hexdigest()

    def run(self) -> ImportSummary:
        started = time.monotonic()
        directory = self._validated_directory()
        archives = sorted(
            (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".zip"),
            key=lambda path: path.name.lower(),
        )
        summary = ImportSummary(directory=str(directory), zip_files_discovered=len(archives))
        self.schema_initializer()

        for archive_path in archives:
            archive_failed = False
            archive_checksum = None
            logger.info(f"Historical import: processing {archive_path.name}")
            try:
                archive_checksum = self._file_checksum(archive_path)
                with zipfile.ZipFile(archive_path, "r") as archive:
                    csv_entries = self._safe_csv_entries(archive)
                    if not csv_entries:
                        self._record_archive_result(directory, archive_path.name, archive_checksum, "skipped", "archive contains no CSV entries")
                        summary.zip_files_skipped += 1
                        logger.warning(f"Historical import: skipped {archive_path.name} (no CSV entries)")
                        continue
                    for entry in csv_entries:
                        session = self.session_factory()
                        audit_repository = HistoricalDataImportRepository(session)
                        candle_repository = GoldPriceCandleRepository(session)
                        audit = audit_repository.start(archive_path.name, entry.filename)
                        try:
                            checksum = self._import_entry(archive, entry, audit, candle_repository)
                            status = "completed" if audit.invalid_rows == 0 else "completed_with_errors"
                            audit_repository.complete(audit, status, checksum=checksum)
                            summary.csv_files_imported += 1
                            summary.total_csv_rows += audit.total_rows
                            summary.inserted_candles += audit.inserted_rows
                            summary.duplicate_candles += audit.duplicate_rows
                            summary.invalid_rows += audit.invalid_rows
                            logger.info(
                                f"Historical import: {archive_path.name}/{entry.filename} "
                                f"rows={audit.total_rows} inserted={audit.inserted_rows} "
                                f"duplicates={audit.duplicate_rows} invalid={audit.invalid_rows}"
                            )
                        except Exception as exc:
                            session.rollback()
                            audit_repository.complete(audit, "failed", error=str(exc))
                            archive_failed = True
                            logger.error(f"Historical import entry failed: {archive_path.name}/{entry.filename}: {exc}")
                        finally:
                            session.close()
                summary.zip_files_failed += int(archive_failed)
                summary.zip_files_processed += int(not archive_failed)
            except Exception as exc:
                self._record_archive_result(directory, archive_path.name, archive_checksum, "failed", str(exc))
                summary.zip_files_failed += 1
                logger.error(f"Historical import archive failed: {archive_path.name}: {exc}")

        summary.elapsed_seconds = time.monotonic() - started
        logger.info(f"Historical import complete: {asdict(summary)}")
        return summary

    def _record_archive_result(self, directory, filename, checksum, status, error):
        session = self.session_factory()
        try:
            repository = HistoricalDataImportRepository(session)
            record = repository.start(filename, checksum=checksum)
            repository.complete(record, status, error=error)
        finally:
            session.close()


class _PrependLine:
    """Small iterator that prepends the delimiter-detection line without buffering."""

    def __init__(self, first: str, stream):
        self.first = first
        self.stream = stream
        self.used = False

    def __iter__(self):
        return self

    def __next__(self):
        if not self.used:
            self.used = True
            return self.first
        line = self.stream.readline()
        if not line:
            raise StopIteration
        return line
