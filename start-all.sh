#!/usr/bin/env bash
# Start the real application processes. PostgreSQL is externally managed because
# this repository has no Docker/Compose file or PostgreSQL cluster definition.
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

VENV_DIR="${VIRTUAL_ENV:-}"
if [[ -z "$VENV_DIR" ]]; then
  if [[ -x "$SCRIPT_DIR/.venv312/bin/python" ]]; then
    VENV_DIR="$SCRIPT_DIR/.venv312"
  elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    VENV_DIR="$SCRIPT_DIR/.venv"
  else
    printf 'Error: no Python virtual environment found (.venv312 or .venv).\n' >&2
    printf 'Create one and install requirements.txt before starting.\n' >&2
    exit 1
  fi
fi

PYTHON="$VENV_DIR/bin/python"
ALEMBIC="$VENV_DIR/bin/alembic"
STREAMLIT="$VENV_DIR/bin/streamlit"
RUN_DIR="$SCRIPT_DIR/.run"
LOG_DIR="$SCRIPT_DIR/logs/launcher"
STREAMER_PID_FILE="$RUN_DIR/streamer.pid"
WORKER_LOCK_FILE="$RUN_DIR/background-worker.lock"
DASHBOARD_PID_FILE="$RUN_DIR/dashboard.pid"
DASHBOARD_PORT="${STREAMLIT_PORT:-8501}"
DASHBOARD_URL="http://localhost:${DASHBOARD_PORT}"
CHILD_PIDS=()
OWN_STREAMER=false
OWN_DASHBOARD=false
IMPORT_HISTORY=false
TRAIN=false
RETRAIN=false

usage() {
  cat <<'EOF'
Usage: ./start-all.sh [option]

Starts the Gold Price Prediction dashboard and live collection process after
checking PostgreSQL and applying Alembic migrations. Redis is optional.

Options:
  --import-history  Run the configured ZIP-directory importer before startup.
  --train           Explicitly train the candle model before startup.
  --retrain         Explicitly retrain the candle model before startup.
  --help             Show this help.

Environment:
  STREAMLIT_PORT     Dashboard port (default: 8501).

Normal startup never imports historical files or starts training explicitly.
EOF
}

for argument in "$@"; do
  case "$argument" in
    --help) usage; exit 0 ;;
    --import-history) IMPORT_HISTORY=true ;;
    --train) TRAIN=true ;;
    --retrain) RETRAIN=true ;;
    *) printf 'Error: unknown option: %s\n\n' "$argument" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$TRAIN" == true && "$RETRAIN" == true ]]; then
  printf 'Error: choose either --train or --retrain, not both.\n' >&2
  exit 2
fi

require_executable() {
  [[ -x "$1" ]] || { printf 'Error: required executable not found: %s\n' "$1" >&2; exit 1; }
}

require_executable "$PYTHON"
require_executable "$ALEMBIC"
require_executable "$STREAMLIT"
command -v curl >/dev/null 2>&1 || { printf 'Error: curl is required for readiness checks.\n' >&2; exit 1; }
[[ -f "$SCRIPT_DIR/.env" ]] || { printf 'Error: .env is missing; copy .env.example and configure it.\n' >&2; exit 1; }
[[ -f "$SCRIPT_DIR/requirements.txt" ]] || { printf 'Error: requirements.txt is missing.\n' >&2; exit 1; }

"$PYTHON" - <<'PY'
import sys
if not ((3, 12) <= sys.version_info[:2] < (3, 13)):
    raise SystemExit(f"Python 3.12 is required; found {sys.version.split()[0]}")
for module in ("streamlit", "sqlalchemy", "psycopg2", "alembic"):
    __import__(module)
PY

mkdir -p "$RUN_DIR" "$LOG_DIR"

cleanup() {
  local status=$?
  trap - INT TERM EXIT
  if ((${#CHILD_PIDS[@]})); then
    printf '\nStopping locally launched services...\n'
    for pid in "${CHILD_PIDS[@]}"; do
      kill -TERM "$pid" 2>/dev/null || true
    done
    for pid in "${CHILD_PIDS[@]}"; do
      wait "$pid" 2>/dev/null || true
    done
  fi
  [[ "$OWN_STREAMER" == false ]] || rm -f "$STREAMER_PID_FILE"
  [[ "$OWN_DASHBOARD" == false ]] || rm -f "$DASHBOARD_PID_FILE"
  exit "$status"
}
trap cleanup INT TERM EXIT

pid_is_ours() {
  local pid_file=$1 pattern=$2 pid
  [[ -f "$pid_file" ]] || return 1
  pid="$(<"$pid_file")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  ps -p "$pid" -o command= 2>/dev/null | grep -F "$pattern" >/dev/null
}

printf 'Checking PostgreSQL...\n'
"$PYTHON" - <<'PY'
from sqlalchemy import text
from src.database import get_engine
try:
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("DATABASE_URL must select PostgreSQL for this launcher")
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
except Exception as exc:
    raise SystemExit(
        "PostgreSQL is not reachable using DATABASE_URL. Start the configured "
        "PostgreSQL service and verify .env. Details: " + str(exc).splitlines()[0]
    )
PY

printf 'Applying database migrations...\n'
"$ALEMBIC" upgrade head

IFS='|' read -r REDIS_DISPLAY_HOST REDIS_DISPLAY_PORT < <("$PYTHON" - <<'PY'
from config.settings import get_settings
s = get_settings().redis
print(f"{s.host}|{s.port}")
PY
)
if "$PYTHON" - <<'PY' >/dev/null 2>&1
from config.settings import get_settings
import redis
s = get_settings().redis
client = redis.Redis(host=s.host, port=s.port, db=s.db, password=s.password,
                     socket_connect_timeout=1, socket_timeout=1)
raise SystemExit(0 if client.ping() else 1)
PY
then
  printf 'Optional Redis cache: ready at %s:%s\n' "$REDIS_DISPLAY_HOST" "$REDIS_DISPLAY_PORT"
else
  printf 'Optional Redis cache: unavailable; the application will use PostgreSQL directly.\n'
fi

if [[ "$IMPORT_HISTORY" == true ]]; then
  printf 'Importing configured historical ZIP directory...\n'
  "$PYTHON" "$SCRIPT_DIR/import_historical_data.py"
fi

run_candle_training() {
  local label=$1 mode=$2
  printf '%s candle model (explicit request)...\n' "$label"
  "$PYTHON" "$SCRIPT_DIR/train_models.py" --mode "$mode"
}

[[ "$TRAIN" == false ]] || run_candle_training "Training" "train"
[[ "$RETRAIN" == false ]] || run_candle_training "Retraining" "retrain"

if pid_is_ours "$WORKER_LOCK_FILE" "realtime/streamer_enhanced.py"; then
  read -r STREAMER_PID < "$WORKER_LOCK_FILE"
  printf 'Independent background worker already running (PID %s); not starting a duplicate.\n' "$STREAMER_PID"
elif pid_is_ours "$STREAMER_PID_FILE" "realtime/streamer_enhanced.py"; then
  read -r STREAMER_PID < "$STREAMER_PID_FILE"
  printf 'Live collection process already running (PID %s).\n' "$STREAMER_PID"
else
  rm -f "$STREAMER_PID_FILE"
  printf 'Starting live collection, prediction lifecycle, and retraining scheduler...\n'
  "$PYTHON" "$SCRIPT_DIR/realtime/streamer_enhanced.py" >>"$LOG_DIR/streamer.log" 2>&1 &
  STREAMER_PID=$!
  OWN_STREAMER=true
  CHILD_PIDS+=("$STREAMER_PID")
  printf '%s\n' "$STREAMER_PID" > "$STREAMER_PID_FILE"
  # This process exposes no port; surviving provider initialization is its readiness signal.
  sleep 5
  kill -0 "$STREAMER_PID" 2>/dev/null || {
    printf 'Error: live collection process exited. See %s\n' "$LOG_DIR/streamer.log" >&2
    exit 1
  }
fi

if curl --silent --fail --max-time 2 "$DASHBOARD_URL/_stcore/health" >/dev/null 2>&1; then
  printf 'Streamlit dashboard already healthy at %s.\n' "$DASHBOARD_URL"
elif pid_is_ours "$DASHBOARD_PID_FILE" "streamlit run"; then
  read -r DASHBOARD_PID < "$DASHBOARD_PID_FILE"
  printf 'Streamlit dashboard process already running (PID %s).\n' "$DASHBOARD_PID"
else
  rm -f "$DASHBOARD_PID_FILE"
  printf 'Starting Streamlit dashboard on port %s...\n' "$DASHBOARD_PORT"
  "$STREAMLIT" run "$SCRIPT_DIR/app/main.py" \
    --server.address localhost --server.port "$DASHBOARD_PORT" \
    --server.headless true >>"$LOG_DIR/dashboard.log" 2>&1 &
  DASHBOARD_PID=$!
  OWN_DASHBOARD=true
  CHILD_PIDS+=("$DASHBOARD_PID")
  printf '%s\n' "$DASHBOARD_PID" > "$DASHBOARD_PID_FILE"
fi

ready=false
for _ in {1..30}; do
  if curl --silent --fail --max-time 2 "$DASHBOARD_URL/_stcore/health" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
[[ "$ready" == true ]] || { printf 'Error: dashboard did not become healthy. See %s\n' "$LOG_DIR/dashboard.log" >&2; exit 1; }

DB_LOCATION="$($PYTHON - <<'PY'
from sqlalchemy.engine import make_url
from dotenv import dotenv_values
url = make_url(dotenv_values(".env")["DATABASE_URL"])
print(f"{url.host or 'local-file'}:{url.port or 5432}/{url.database or ''}")
PY
)"

cat <<EOF

Gold Price Prediction is running

Dashboard:       $DASHBOARD_URL
Dashboard health:$DASHBOARD_URL/_stcore/health
PostgreSQL:      $DB_LOCATION
Redis:           optional ($REDIS_DISPLAY_HOST:$REDIS_DISPLAY_PORT)
Logs:            $LOG_DIR

No backend REST API or API documentation service exists in this repository.
Press Ctrl+C to stop all locally launched application processes.
EOF

# Keep signal handling attached to the locally launched processes.
if ((${#CHILD_PIDS[@]})); then
  while true; do
    for pid in "${CHILD_PIDS[@]}"; do
      kill -0 "$pid" 2>/dev/null || { printf 'Error: service PID %s exited unexpectedly.\n' "$pid" >&2; exit 1; }
    done
    sleep 2
  done
else
  printf 'All application processes were already running; nothing is attached to this launcher.\n'
  trap - INT TERM EXIT
fi
