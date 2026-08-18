import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.reset_artifacts import ArtifactResetter
from scripts.reset_database import DatabaseResetter, _safe_pg_url


class ResetToolTests(unittest.TestCase):
    def test_safe_pg_url_removes_password(self):
        url, environment = _safe_pg_url("postgresql://user:secret@localhost:5432/database")
        self.assertNotIn("secret", url)
        self.assertEqual("secret", environment["PGPASSWORD"])

    def test_database_reset_requires_confirmation(self):
        resetter = DatabaseResetter("postgresql://unused", backup_dir=tempfile.mkdtemp())
        with patch.object(resetter, "inspect", return_value=(["prices"], {"prices": 1}, (6_100_000, None, None))):
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                resetter.run()
            dry = resetter.run(dry_run=True)
            self.assertTrue(dry["dry_run"])

    def test_artifacts_are_archived_and_source_markers_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models, backups = root / "models", root / "backups"
            (models / "candidates" / "v1").mkdir(parents=True)
            (models / "candidates" / "v1" / "model.joblib").write_text("artifact")
            (models / "legacy").mkdir()
            (models / "legacy" / "README.md").write_text("keep")
            (models / "old_model.pkl").write_text("legacy artifact")
            resetter = ArtifactResetter(models, backups)
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                resetter.run()
            result = resetter.run(confirmed=True)
            self.assertTrue((models / ".clean_state").exists())
            self.assertTrue((models / "legacy" / "README.md").exists())
            self.assertFalse((models / "old_model.pkl").exists())
            self.assertTrue((Path(result["backup_dir"]) / "old_model.pkl").exists())
            self.assertEqual("candle_features_v2", json.loads((models / ".clean_state").read_text())["feature_schema_required"])


if __name__ == "__main__":
    unittest.main()
