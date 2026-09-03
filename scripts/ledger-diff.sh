#!/usr/bin/env bash
# ledger-diff.sh : print what changed in the watched files since the last run.
# Read-only on the watched files; only writes its own snapshot cache.
# Snapshots live in OPS_STATE_DIR/ledger-snap/. Exit 0 no change, 10 changes found, 2 missing config/file.
#
# Config (env vars, see ops-pack.env.example):
#   OPS_WATCH_DIR    directory the watched files live in (required)
#   OPS_WATCH_FILES  comma-separated file paths, relative to OPS_WATCH_DIR (required)
#   OPS_STATE_DIR    where the snapshot cache lives (optional, default ~/.openclaw/state)
set -uo pipefail

I="${OPS_WATCH_DIR:-}"
FILES_CSV="${OPS_WATCH_FILES:-}"
if [ -z "$I" ] || [ -z "$FILES_CSV" ]; then
  echo "OPS_WATCH_DIR and OPS_WATCH_FILES must be set, see ops-pack.env.example"
  exit 2
fi
IFS=',' read -ra FILES <<< "$FILES_CSV"

S="${OPS_STATE_DIR:-$HOME/.openclaw/state}/ledger-snap"; mkdir -p "$S"
changed=0
for f in "${FILES[@]}"; do
  src="$I/$f"; snap="$S/$(basename "$f")"
  [ -f "$src" ] || { echo "MISSING $f"; exit 2; }
  if [ -f "$snap" ]; then
    d=$(diff -u "$snap" "$src" | grep -E '^[-+]' | grep -vE '^(\+\+\+|---)' | grep -vE '^[-+]\s*$' | head -40)
    if [ -n "$d" ]; then changed=1; echo "== $(basename "$f") changed $(echo "$d" | grep -c '^+') added / $(echo "$d" | grep -c '^-') removed"; echo "$d" | cut -c1-200; fi
  else
    echo "== $(basename "$f") first snapshot ($(wc -l < "$src") lines)"; changed=1
  fi
  [ "${1:-}" = "--dry-run" ] || cp "$src" "$snap"
done
[ $changed -eq 1 ] && exit 10 || { echo "no changes"; exit 0; }
