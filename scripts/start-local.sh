#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f ".env.local" ]; then
  set -a
  # shellcheck disable=SC1091
  . ".env.local"
  set +a
fi

PORT="${AUGUR_PORT:-8000}"
exec .venv/bin/augur serve --port "$PORT"
