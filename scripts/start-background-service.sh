#!/usr/bin/env bash
set -euo pipefail
LABEL="gui/$(id -u)/com.goldpriceprediction.worker"
launchctl kickstart -k "$LABEL"
printf 'Background worker start requested.\n'
