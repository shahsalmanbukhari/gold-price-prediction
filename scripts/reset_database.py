#!/usr/bin/env python3
"""Backup and reset derived/live state while preserving canonical candles.

This destructive command requires ``--yes``. It never truncates
``gold_price_candles`` or ``historical_data_imports``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
LOGGER = logging.getLogger("database-reset")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# Actual project tables. Import audit/canonical candles are intentionally absent.
RESET_TABLES = (
    "notification_deliveries", "prediction_decisions", "horizon_predictions",
    "model_health", "horizon_model_status", "walk_forward_results",
    "retraining_runs", "training_scheduler_state", "service_heartbeats",
    "provider_status", "prices", "trading_sessions",
    "predictions", "features", "models",
)
PRESERVED_TABLES = ("gold_price_candles", "historical_data_imports")


def _safe_pg_url(dsn):
    """Return password-free pg_dump URL plus environment carrying the password."""
    parsed = urlsplit(dsn.replace("postgresql+psycopg2://", "postgresql://", 1))
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError("DATABASE_URL must be PostgreSQL")
    username = unquote(parsed.username or "")
    host = parsed.hostname or "localhost"
    user_part = quote(username) + "@" if username else ""
    port = f":{parsed.port}" if parsed.port else ""
    safe = urlunsplit((parsed.scheme, f"{user_part}{host}{port}", parsed.path, parsed.query, ""))
    environment = os.environ.copy()
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    return safe, environment


class DatabaseResetter:
    def __init__(self, dsn=None, backup_dir=None):
        self.dsn = dsn or os.getenv("DATABASE_URL")
        if not self.dsn:
            raise RuntimeError("DATABASE_URL is required; no default credentials are embedded")
        self.backup_dir = Path(backup_dir or ROOT / "backups" / "database")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _existing_tables(self, cursor, candidates=RESET_TABLES):
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        existing = {row[0] for row in cursor.fetchall()}
        return [table for table in candidates if table in existing]

    @staticmethod
    def _candle_signature(cursor):
        cursor.execute("SELECT COUNT(*), MIN(candle_time), MAX(candle_time) FROM gold_price_candles")
        return cursor.fetchone()

    def inspect(self):
        with psycopg2.connect(self.dsn) as connection, connection.cursor() as cursor:
            tables = self._existing_tables(cursor)
            counts = {}
            for table in tables:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                counts[table] = cursor.fetchone()[0]
            return tables, counts, self._candle_signature(cursor)

    def backup_tables(self, tables):
        if not tables:
            raise RuntimeError("No resettable tables were found; refusing to continue")
        executable = shutil.which("pg_dump")
        if not executable:
            for candidate in (
                Path("/opt/homebrew/opt/libpq/bin/pg_dump"),
                Path("/usr/local/opt/libpq/bin/pg_dump"),
                Path("/Applications/Postgres.app/Contents/Versions/latest/bin/pg_dump"),
            ):
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    executable = str(candidate)
                    break
        if not executable:
            raise RuntimeError("pg_dump is required before destructive reset")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.backup_dir / f"prediction-state-{stamp}.dump"
        safe_dsn, environment = _safe_pg_url(self.dsn)
        command = [executable, "--format=custom", "--no-owner", "--no-privileges", "--file", str(path)]
        for table in tables:
            command.extend(("--table", f"public.{table}"))
        command.append(safe_dsn)
        subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("pg_dump returned without creating a non-empty backup")
        manifest = path.with_suffix(".json")
        manifest.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(),
                                        "backup": str(path), "tables": tables}, indent=2) + "\n")
        LOGGER.info("Backup created: %s", path)
        return path

    def reset_all(self, tables, expected_candles):
        quoted = ", ".join(f'"{table}"' for table in tables)
        with psycopg2.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY")
                after = self._candle_signature(cursor)
                if after != expected_candles:
                    raise RuntimeError(f"Candle invariant failed: before={expected_candles}, after={after}")
            connection.commit()
        return True

    def verify_reset(self, tables, expected_candles):
        with psycopg2.connect(self.dsn) as connection, connection.cursor() as cursor:
            residual = {}
            for table in tables:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                count = cursor.fetchone()[0]
                if count:
                    residual[table] = count
            candle_signature = self._candle_signature(cursor)
        return {"clean": not residual and candle_signature == expected_candles,
                "residual": residual, "candles": candle_signature}

    def run(self, confirmed=False, skip_backup=False, dry_run=False):
        tables, counts, candles = self.inspect()
        LOGGER.info("Will reset %d existing tables containing %d rows", len(tables), sum(counts.values()))
        LOGGER.info("Preserving gold_price_candles: count=%s range=%s to %s", *candles)
        if dry_run:
            return {"dry_run": True, "tables": counts, "candles": candles}
        if not confirmed:
            raise RuntimeError("Destructive reset refused. Re-run with --yes after reviewing --dry-run")
        backup = None if skip_backup else self.backup_tables(tables)
        self.reset_all(tables, candles)
        verification = self.verify_reset(tables, candles)
        if not verification["clean"]:
            raise RuntimeError(f"Reset verification failed: {verification}")
        return {"backup": str(backup) if backup else None, "tables": tables,
                "preserved_candles": candles[0], "verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-backup", action="store_true",
                        help="Dangerous: allowed only with RESET_ALLOW_SKIP_BACKUP=true")
    args = parser.parse_args()
    if args.skip_backup and os.getenv("RESET_ALLOW_SKIP_BACKUP", "").lower() != "true":
        parser.error("--skip-backup requires RESET_ALLOW_SKIP_BACKUP=true")
    result = DatabaseResetter().run(args.yes, args.skip_backup, args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
