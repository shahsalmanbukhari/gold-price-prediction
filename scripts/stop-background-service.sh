#!/usr/bin/env bash
set -euo pipefail
LABEL="gui/$(id -u)/com.goldpriceprediction.worker"
launchctl kill SIGTERM "$LABEL"
printf 'Background worker stop requested. launchd will restart it after unexpected exit; uninstall to disable it.\n'
