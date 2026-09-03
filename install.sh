#!/usr/bin/env bash
# install.sh : copy this pack's scripts into ~/.openclaw/scripts and remind
# you to fill in ops-pack.env. Safe to re-run (overwrites in place).
set -euo pipefail

DEST="$HOME/.openclaw/scripts"
mkdir -p "$DEST"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts"

for f in "$SRC"/*; do
  cp "$f" "$DEST/"
  chmod +x "$DEST/$(basename "$f")"
done

echo "copied $(ls "$SRC" | wc -l | tr -d ' ') scripts to $DEST"

ENV_DEST="$HOME/.openclaw/ops-pack.env"
if [[ ! -f "$ENV_DEST" ]]; then
  cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ops-pack.env.example" "$ENV_DEST"
  echo "wrote $ENV_DEST, edit it before running any job"
else
  echo "$ENV_DEST already exists, left untouched"
fi

echo
echo "next: edit $ENV_DEST, then 'source $ENV_DEST' in whatever runs your cron jobs"
echo "(or point your scheduler's env config at it), then run ./jobs.sh"
