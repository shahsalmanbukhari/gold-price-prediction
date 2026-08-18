#!/usr/bin/env python3
"""Orchestrate confirmed backup, reset, session rebuild, training and validation."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("complete-reset")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class CompleteReset:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path or ROOT / "config" / "reset_config.json")
        self.config = json.loads(self.config_path.read_text())
        self.log_dir = ROOT / "logs" / "reset"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.python = Path(sys.executable).resolve()
        self.results = {}

    def _run(self, name, command, required=True):
        LOGGER.info("Running %s", name)
        completed = subprocess.run([str(value) for value in command], cwd=ROOT, text=True,
                                   capture_output=True, env=os.environ.copy())
        log_path = self.log_dir / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{name.replace(' ', '-')}.log"
        log_path.write_text((completed.stdout or "") + ("\nSTDERR\n" + completed.stderr if completed.stderr else ""))
        self.results[name] = {"status": "SUCCESS" if completed.returncode == 0 else "FAILED",
                              "returncode": completed.returncode, "log": str(log_path)}
        if completed.returncode and required:
            raise RuntimeError(f"{name} failed; see {log_path}")
        return completed

    @staticmethod
    def _stop_pid_file(path, expected):
        if not path.exists():
            return
        raw = path.read_text().strip()
        if not raw.isdigit():
            raise RuntimeError(f"Invalid PID file: {path}")
        pid = int(raw)
        try:
            command = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
            if command and expected not in command:
                raise RuntimeError(f"PID {pid} is not the expected {expected} process")
            if command:
                os.kill(pid, signal.SIGTERM)
                for _ in range(50):
                    try: os.kill(pid, 0)
                    except ProcessLookupError: break
                    time.sleep(.1)
        finally:
            path.unlink(missing_ok=True)

    def stop_services(self):
        target = Path.home() / "Library" / "LaunchAgents" / "com.goldpriceprediction.worker.plist"
        if target.exists():
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(target)], capture_output=True)
        self._stop_pid_file(ROOT / ".run" / "streamer.pid", "realtime/streamer_enhanced.py")
        self._stop_pid_file(ROOT / ".run" / "background-worker.lock", "realtime/streamer_enhanced.py")
        self._stop_pid_file(ROOT / ".run" / "dashboard.pid", "streamlit run")
        self.results["Stop services"] = {"status": "SUCCESS"}

    def start_services(self):
        # Install regenerates a secret-free plist from the repository template.
        self._run("Start background service", [ROOT / "scripts" / "install-background-service.sh"])
        port = int(os.getenv("STREAMLIT_PORT", "8501"))
        health = f"http://localhost:{port}/_stcore/health"
        try:
            urllib.request.urlopen(health, timeout=2).close()
            self.results["Start dashboard"] = {"status": "ALREADY_RUNNING", "url": health}
            return
        except Exception:
            pass
        streamlit = self.python.parent / "streamlit"
        if not streamlit.exists():
            raise RuntimeError(f"Streamlit executable not found: {streamlit}")
        log_path = ROOT / "logs" / "launcher" / "dashboard.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_stream = log_path.open("a")
        process = subprocess.Popen([
            str(streamlit), "run", str(ROOT / "app/main.py"), "--server.address", "localhost",
            "--server.port", str(port), "--server.headless", "true",
        ], cwd=ROOT, stdout=log_stream, stderr=subprocess.STDOUT, start_new_session=True)
        run_dir = ROOT / ".run"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "dashboard.pid").write_text(f"{process.pid}\n")
        for _ in range(30):
            if process.poll() is not None:
                raise RuntimeError(f"Dashboard exited during startup; see {log_path}")
            try:
                urllib.request.urlopen(health, timeout=2).close()
                self.results["Start dashboard"] = {"status": "SUCCESS", "pid": process.pid, "url": health}
                return
            except Exception:
                time.sleep(1)
        process.terminate()
        raise RuntimeError(f"Dashboard did not become healthy; see {log_path}")

    def run(self, confirmed=False, dry_run=False):
        if not confirmed and not dry_run:
            raise RuntimeError("Complete reset refused. Use --dry-run first, then --yes")
        horizons = ",".join(str(value) for value in self.config["horizons"])
        try:
            if dry_run:
                self._run("Database dry run", [self.python, ROOT / "scripts/reset_database.py", "--dry-run"])
                self._run("Artifact dry run", [self.python, ROOT / "scripts/reset_artifacts.py", "--dry-run"])
                return self.results
            if self.config.get("stop_services"):
                self.stop_services()
            if self.config.get("reset_database"):
                command = [self.python, ROOT / "scripts/reset_database.py", "--yes"]
                if not self.config.get("backup_database", True):
                    if os.getenv("RESET_ALLOW_SKIP_BACKUP", "").lower() != "true":
                        raise RuntimeError("Skipping backup requires RESET_ALLOW_SKIP_BACKUP=true")
                    command.append("--skip-backup")
                self._run("Reset database", command)
            if self.config.get("reset_artifacts"):
                self._run("Reset artifacts", [self.python, ROOT / "scripts/reset_artifacts.py", "--yes"])
            self._run("Verify clean reset", [self.python, ROOT / "scripts/verify_reset.py"])
            if self.config.get("rebuild_sessions"):
                self._run("Rebuild sessions", [self.python, ROOT / "scripts/build_trading_sessions.py",
                                                "--gap-threshold", self.config["gap_threshold_minutes"]])
            if self.config.get("retrain_models"):
                self._run("Initial training", [self.python, ROOT / "train_models.py", "--mode", "train",
                                                "--algorithm", self.config.get("training_algorithm", "benchmark")])
                production = ROOT / "models" / "production" / "manifest.json"
                if not production.exists() or json.loads(production.read_text()).get("feature_schema_version") != "candle_features_v2":
                    raise RuntimeError("Training did not produce an approved candle_features_v2 production bundle")
            if self.config.get("run_validation"):
                self._run("Walk forward validation", [self.python, ROOT / "scripts/run_walk_forward.py",
                                                       "--horizons", horizons, "--min-folds",
                                                       self.config.get("minimum_walk_forward_folds", 6)])
            if self.config.get("start_services"):
                self.start_services()
            return self.results
        finally:
            summary = self.log_dir / f"summary-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
            summary.write_text(json.dumps(self.results, indent=2, default=str) + "\n")
            LOGGER.info("Reset summary: %s", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config")
    args = parser.parse_args()
    result = CompleteReset(args.config).run(args.yes, args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
