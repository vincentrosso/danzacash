#!/usr/bin/env bash
# Create the private books repo from template/ (once). Refuses to touch an existing one.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOOKS="${1:-${DANZA_BOOKS:-$ROOT/books}}"
[ -e "$BOOKS/main.beancount" ] && { echo "$BOOKS already initialised"; exit 0; }
mkdir -p "$BOOKS"
cp -R "$ROOT/template/." "$BOOKS/"
mkdir -p "$BOOKS/documents" "$BOOKS/.cache/simplefin"
git -C "$BOOKS" init -q -b main
git -C "$BOOKS" add -A
git -C "$BOOKS" commit -q -m "Initial books from danzacash template"
echo "books initialised at $BOOKS"
