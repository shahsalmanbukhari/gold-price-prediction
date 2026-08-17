"""Integration tests for safe directory-based ZIP imports."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import HistoricalDataSettings
from src.database import Base, GoldPriceCandle, HistoricalDataImport, Price
from src.historical_zip_importer import HistoricalZipImporter


HEADER = "Date,Time,Open,High,Low,Close,Volume\n"
ROWS = (
    "2026.08.02,18:00,4081.935,4081.935,4069.685,4073.295,0\n"
    "2026.08.02,18:01,4073.295,4078.000,4071.500,4077.250,12\n"
)


class HistoricalZipImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "historical-data"
        self.directory = self.root / "xauusd"
        self.directory.mkdir(parents=True)
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        settings = HistoricalDataSettings(
            allowed_import_root=self.root,
            import_directory=self.directory,
            batch_size=2,
            maximum_uncompressed_file_size=1024 * 1024,
            maximum_archive_uncompressed_size=2 * 1024 * 1024,
            maximum_compression_ratio=200,
            maximum_archive_entries=20,
        )
        self.importer = HistoricalZipImporter(
            settings=settings,
            session_factory=self.Session,
            schema_initializer=lambda: Base.metadata.create_all(self.engine),
        )

    def tearDown(self):
        self.temp.cleanup()

    def _zip(self, name, entries):
        with zipfile.ZipFile(self.directory / name, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename, content in entries:
                archive.writestr(filename, content)

    def test_complete_archive_matrix_and_idempotency(self):
        self._zip("HISTDATA_XAUUSD_202501.zip", [
            ("DAT_ASCII_XAUUSD_M1_202501.csv", HEADER + ROWS),
            ("DAT_ASCII_XAUUSD_M1_202501.txt", "report must be ignored"),
            ("folder/", ""),
        ])
        self._zip("HISTDATA_XAUUSD_202502.zip", [("report.TXT", "no data")])
        self._zip("HISTDATA_XAUUSD_202503.zip", [
            ("first.csv", HEADER + "2026.08.02,18:02,4077,4080,4076,4079,50\n"),
            ("nested/SECOND.CSV", HEADER + "2026.08.02,18:03,4079,4082,4078,4081,60\n"),
        ])
        self._zip("HISTDATA_XAUUSD_202504.zip", [
            ("malformed.csv", HEADER + "bad,row\n2026.08.02,18:04,4081,4084,4080,4083,70\n"),
        ])
        self._zip("HISTDATA_XAUUSD_202505.ZIP", [("duplicate.csv", HEADER + ROWS)])
        self._zip("HISTDATA_XAUUSD_202506.zip", [
            ("../../escape.csv", HEADER + ROWS),
            ("valid.csv", HEADER + ROWS),
        ])

        summary = self.importer.run()

        self.assertEqual(summary.zip_files_discovered, 6)
        self.assertEqual(summary.zip_files_processed, 4)
        self.assertEqual(summary.zip_files_skipped, 1)
        self.assertEqual(summary.zip_files_failed, 1)
        self.assertEqual(summary.csv_files_imported, 5)
        self.assertEqual(summary.total_csv_rows, 8)
        self.assertEqual(summary.inserted_candles, 5)
        self.assertEqual(summary.duplicate_candles, 2)
        self.assertEqual(summary.invalid_rows, 1)

        session = self.Session()
        self.assertEqual(session.query(Price).count(), 0)
        self.assertEqual(session.query(GoldPriceCandle).count(), 5)
        first_candle = session.query(GoldPriceCandle).order_by(GoldPriceCandle.candle_time).first()
        self.assertEqual(first_candle.symbol, "XAUUSD")
        self.assertEqual(first_candle.timeframe, "1m")
        self.assertEqual(first_candle.provider, "histdata")
        self.assertEqual(first_candle.candle_time.hour, 23)
        self.assertIsNone(first_candle.volume)
        audits = session.query(HistoricalDataImport).order_by(HistoricalDataImport.id).all()
        self.assertEqual([row.source_zip for row in audits], sorted(
            [row.source_zip for row in audits], key=str.lower
        ))
        completed_entries = [row for row in audits if row.source_csv]
        self.assertTrue(all(row.file_checksum for row in audits))
        self.assertTrue(all(row.file_checksum for row in completed_entries if row.status != "failed"))
        self.assertTrue(any(row.status == "skipped" and "no CSV" in row.error_message for row in audits))
        self.assertTrue(any(row.status == "failed" and "unsafe ZIP entry" in row.error_message for row in audits))
        session.close()

        second = self.importer.run()
        self.assertEqual(second.inserted_candles, 0)
        self.assertEqual(second.duplicate_candles, 7)
        session = self.Session()
        self.assertEqual(session.query(Price).count(), 0)
        self.assertEqual(session.query(GoldPriceCandle).count(), 5)
        session.close()

    def test_directory_must_be_inside_allowed_root(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        settings = HistoricalDataSettings(
            allowed_import_root=self.root,
            import_directory=outside,
        )
        importer = HistoricalZipImporter(settings, self.Session, lambda: None)
        with self.assertRaisesRegex(ValueError, "inside allowed root"):
            importer.run()

    def test_zip_bomb_limits_and_malformed_archive_do_not_stop_run(self):
        with zipfile.ZipFile(self.directory / "202501_oversized.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("large.csv", "x" * (1024 * 1024 + 1))
        (self.directory / "202502_malformed.zip").write_bytes(b"not a zip archive")
        self._zip("202503_valid.zip", [
            ("valid.csv", HEADER + "2026.08.02,18:05,4083,4085,4082,4084,80\n"),
        ])

        summary = self.importer.run()

        self.assertEqual(summary.zip_files_discovered, 3)
        self.assertEqual(summary.zip_files_failed, 2)
        self.assertEqual(summary.zip_files_processed, 1)
        self.assertEqual(summary.inserted_candles, 1)


if __name__ == "__main__":
    unittest.main()
