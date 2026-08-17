#!/usr/bin/env bash
set -euo pipefail
TARGET="$HOME/Library/LaunchAgents/com.goldpriceprediction.worker.plist"
launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
[[ ! -f "$TARGET" ]] || mv "$TARGET" "$TARGET.disabled"
printf 'Background service uninstalled. Configuration and logs were preserved.\n'
