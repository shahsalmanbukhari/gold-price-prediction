#!/usr/bin/env bash
# Safe compatibility wrapper. The Python orchestrator owns backup and invariants.
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
PYTHON="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"
if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
  [[ -x "$ROOT/.venv312/bin/python" ]] && PYTHON="$ROOT/.venv312/bin/python" || PYTHON="$ROOT/.venv/bin/python"
fi
[[ -x "$PYTHON" ]] || { printf 'Python virtual environment not found.\n' >&2; exit 1; }

if [[ "${1:-}" == "--dry-run" ]]; then
  exec "$PYTHON" "$SCRIPT_DIR/complete_reset.py" --dry-run
fi
if [[ "${1:-}" != "--yes" ]]; then
  printf 'Destructive wash refused. Run %s --dry-run, then %s --yes.\n' "$0" "$0" >&2
  exit 2
fi
exec "$PYTHON" "$SCRIPT_DIR/complete_reset.py" --yes
