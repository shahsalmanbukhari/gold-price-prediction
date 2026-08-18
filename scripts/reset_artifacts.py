#!/usr/bin/env python3
"""Archive and remove generated model bundles without touching source files."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArtifactResetter:
    def __init__(self, model_dir=None, backup_root=None):
        self.model_dir = Path(model_dir or ROOT / "models").resolve()
        self.backup_root = Path(backup_root or ROOT / "backups" / "models").resolve()

    def artifacts(self):
        paths = []
        for directory in ("candidates", "production", "previous_production", "versions", "quarantine"):
            path = self.model_dir / directory
            if path.exists():
                paths.append(path)
        for pattern in ("*.pkl", "*.joblib", "*.h5", "*.keras", "*.onnx", "*.pt", "*.pth"):
            paths.extend(path for path in self.model_dir.glob(pattern) if path.is_file())
        return sorted(set(paths))

    def run(self, confirmed=False, dry_run=False):
        artifacts = self.artifacts()
        if dry_run:
            return {"dry_run": True, "artifacts": [str(path.relative_to(ROOT)) for path in artifacts]}
        if not confirmed:
            raise RuntimeError("Artifact reset refused. Re-run with --yes after reviewing --dry-run")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.backup_root / stamp
        backup.mkdir(parents=True, exist_ok=False)
        archived = []
        for source in artifacts:
            relative = source.relative_to(self.model_dir)
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            archived.append(str(relative))
        manifest = {"reset_time": datetime.now(timezone.utc).isoformat(), "backup_dir": str(backup),
                    "archived": archived, "feature_schema_required": "candle_features_v2"}
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        self.model_dir.mkdir(parents=True, exist_ok=True)
        (self.model_dir / ".clean_state").write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ArtifactResetter().run(args.yes, args.dry_run), indent=2))


if __name__ == "__main__":
    main()
