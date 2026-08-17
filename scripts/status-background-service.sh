#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="gui/$(id -u)/com.goldpriceprediction.worker"
launchctl print "$LABEL" 2>/dev/null | sed -n '1,35p' || printf 'launchd service is not loaded.\n'
cd "$PROJECT_DIR"
"$PROJECT_DIR/.venv312/bin/python" - <<'PY'
from src.background_lifecycle import HeartbeatService, WORKER_NAME
from src.database import ServiceHeartbeat, get_session
s = get_session()
try:
    row = s.get(ServiceHeartbeat, WORKER_NAME)
    if not row:
        print("Heartbeat: no worker heartbeat recorded")
    else:
        print(f"Heartbeat status: {HeartbeatService.health(row)}")
        print(f"Instance: {row.instance_id}")
        print(f"Started: {row.started_at}")
        print(f"Last heartbeat: {row.last_heartbeat_at}")
        print(f"Last live quote: {row.last_live_quote_at}")
        print(f"Last prediction: {row.last_prediction_at}")
        print(f"Last evaluation: {row.last_evaluation_at}")
        print(f"Last training: {row.last_training_at}")
        print(f"Last error: {row.last_error or '-'}")
finally:
    s.close()
PY
