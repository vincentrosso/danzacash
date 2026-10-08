#!/usr/bin/env bash
# Monthly close: pull -> extract -> bean-check -> report flags -> commit (books repo).
#   scripts/monthly_close.sh                 # previous month via SimpleFIN
#   scripts/monthly_close.sh 2026-09         # a specific month
#   scripts/monthly_close.sh 2026-09 ~/Downloads/Chase1234_Activity.CSV   # CSV fallback
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
BOOKS="${DANZA_BOOKS:-$ROOT/books}"
export DANZA_BOOKS="$BOOKS"
MONTH="${1:-$(date -v-1m +%Y-%m)}"
CSV="${2:-}"
YEAR="${MONTH%-*}"; MM="${MONTH#*-}"
OUT="$BOOKS/ledger/$YEAR/$MM.beancount"
cd "$ROOT"

if [ -n "$CSV" ]; then
  SRC="$CSV"
else
  SRC="$(uv run python importers/simplefin_pull.py pull --month "$MONTH" | tail -1 | awk '{print $1}')"
fi

mkdir -p "$(dirname "$OUT")"
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
uv run python import.py extract -q -e "$BOOKS/main.beancount" "$SRC" > "$TMP"
NEW="$(grep -cE '^ +(simplefin|chase)_id:' "$TMP" || true)"
if [ "$NEW" -gt 0 ] || grep -q ' balance ' "$TMP"; then
  { echo; echo ";; --- import $(date +%F) from $(basename "$SRC")"; grep -v '^;; -\*-' "$TMP"; } >> "$OUT"
fi
echo "new transactions: $NEW -> ${OUT#$BOOKS/}"

uv run bean-check "$BOOKS/main.beancount" || { echo "bean-check FAILED — not committing" >&2; exit 1; }

FLAGGED="$(uv run python - "$BOOKS/main.beancount" <<'PY'
import sys
from beancount import loader
from beancount.core import data
entries, _, _ = loader.load_file(sys.argv[1])
print(sum(1 for e in entries if isinstance(e, data.Transaction)
          and (e.flag == "!" or any("Uncategorized" in p.account for p in e.postings))))
PY
)"
echo "needs attention (! or Uncategorized txns): $FLAGGED"

git -C "$BOOKS" add -A
if git -C "$BOOKS" diff --cached --quiet; then
  echo "nothing to commit"
else
  git -C "$BOOKS" commit -q -m "close $MONTH" && echo "committed: close $MONTH"
fi
