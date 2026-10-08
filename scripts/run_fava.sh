#!/usr/bin/env bash
# Fava on localhost only. Never expose to the network — use Tailscale if remote access is wanted.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
BOOKS="${DANZA_BOOKS:-$ROOT/books}"
PORT="${FAVA_PORT:-5050}"   # 5000 is held by macOS AirPlay Receiver
cd "$ROOT"
exec uv run fava "$BOOKS/main.beancount" --host 127.0.0.1 --port "$PORT"
