#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[run] %s\n' "$1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
log "Arbeitsverzeichnis: $REPO_ROOT"

export UV_PROJECT_ENVIRONMENT="$REPO_ROOT/.venv"
log "uv Projektumgebung: $UV_PROJECT_ENVIRONMENT"

if command -v uv >/dev/null 2>&1; then
  if PYTHON_INFO="$(uv run -- python --version 2>&1)"; then
    log "uv Python: $PYTHON_INFO"
  fi
fi

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  log "Lade Umgebungsvariablen aus $env_file ..."
  eval "$(
    python - "$env_file" <<'PY'
import pathlib
import re
import shlex
import sys

path = pathlib.Path(sys.argv[1])
pattern = re.compile(r'^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$')
exports = []
for raw_line in path.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#'):
        continue
    match = pattern.match(line)
    if not match:
        continue
    key, value = match.groups()
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = bytes(value[1:-1], 'utf-8').decode('unicode_escape')
    elif value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
    else:
        if ' #' in value:
            value = value.split('#', 1)[0].rstrip()
        value = value.strip()
    exports.append(f"export {key}={shlex.quote(value)}")

print('\n'.join(exports))
PY
  )"
}

load_env_file "$REPO_ROOT/.env"

: "${APP_PORT:=3000}"
log "API Port: $APP_PORT"

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

log 'Starte API und Worker (Ctrl+C zum Beenden)...'
uv run uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" &
PIDS+=($!)
# Worker findet Tasks automatisch via app.workers.celery_app Import
uv run celery -A app.workers.celery_app worker -l info &
PIDS+=($!)

set +e
wait -n "${PIDS[@]}"
EXIT_CODE=$?
set -e

cleanup

if [[ $EXIT_CODE -ne 0 ]]; then
  exit "$EXIT_CODE"
fi
