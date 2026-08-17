#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv312/bin/python"
TEMPLATE="$SCRIPT_DIR/com.goldpriceprediction.worker.plist.template"
TARGET="$HOME/Library/LaunchAgents/com.goldpriceprediction.worker.plist"
[[ -x "$PYTHON" ]] || { printf 'Missing virtual environment: %s\n' "$PYTHON" >&2; exit 1; }
[[ -f "$PROJECT_DIR/.env" ]] || { printf 'Missing required configuration: %s/.env\n' "$PROJECT_DIR" >&2; exit 1; }
mkdir -p "$PROJECT_DIR/logs/background" "$HOME/Library/LaunchAgents"
python3 - "$TEMPLATE" "$TARGET" "$PROJECT_DIR" "$PYTHON" <<'PY'
from pathlib import Path
import sys
source, target, project, python = sys.argv[1:]
text = Path(source).read_text().replace("__PROJECT__", project).replace("__PYTHON__", python)
Path(target).write_text(text)
PY
plutil -lint "$TARGET"
launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
printf 'Installed and started %s\n' "$TARGET"
