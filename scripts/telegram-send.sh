#!/usr/bin/env bash
# telegram-send.sh
# Stateless Telegram send wrapper: no gateway or session dependency, just curl.
#
# Config (env vars, see ops-pack.env.example): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
#
# Usage:
#   telegram-send.sh <body-file>             # send to TELEGRAM_CHAT_ID
#   telegram-send.sh <body-file> <chat_id>   # explicit chat_id override
#
# Behavior:
#   - If ~/.openclaw/scripts/pre-fire-guard.py exists and is executable, it runs
#     first and blocks the send on violation (exit 2). Optional: this pack does
#     not ship a guard script, drop your own compliance/tone checker at that
#     path to opt in, or skip it entirely.
#   - Body truncated to 3900 chars before send (Telegram cap is 4096; leave
#     room for any UTF-8 expansion).
#   - parse_mode is OFF (plain text), to avoid Markdown breakage on slugs with
#     `_*[]` characters.
#   - One retry on HTTP 429 (rate limit) after the Telegram-API-suggested wait.
#
# Exit codes:
#   0  delivered
#   1  bad arguments / missing file
#   2  pre-fire-guard blocked
#   3  Telegram API error (post-retry)
#   4  config missing (bot token or chat id)

set -euo pipefail

BODY_FILE="${1:-}"

if [[ -z "$BODY_FILE" || ! -f "$BODY_FILE" ]]; then
  echo "usage: telegram-send.sh <body-file> [chat_id]" >&2
  exit 1
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
DEFAULT_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

if [[ -z "$BOT_TOKEN" || -z "$DEFAULT_CHAT_ID" ]]; then
  echo "FATAL: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, see ops-pack.env.example" >&2
  exit 4
fi

CHAT_ID="${2:-$DEFAULT_CHAT_ID}"

# Optional pre-fire-guard hook (bring your own, see comment above)
GUARD="$HOME/.openclaw/scripts/pre-fire-guard.py"
if [[ -x "$GUARD" ]]; then
  if ! python3 "$GUARD" "$BODY_FILE"; then
    echo "pre-fire-guard blocked. fix violations before re-running." >&2
    exit 2
  fi
fi

# Truncate body to 3900 chars (Telegram cap is 4096; leave 196 char headroom).
TRUNCATED=$(mktemp /tmp/ops-pack-tg-truncate.XXXXXX.txt)
trap 'rm -f "$TRUNCATED"' EXIT
python3 -c "
import sys, pathlib
src = pathlib.Path('$BODY_FILE').read_text()
if len(src) > 3900:
    src = src[:3870] + '\n\n[truncated]'
pathlib.Path('$TRUNCATED').write_text(src)
"

# Send via Telegram Bot API. Plain text (no parse_mode).
send_once() {
  curl -sS \
    -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text@${TRUNCATED}" \
    --data-urlencode "disable_web_page_preview=true" \
    -m 15 2>&1
}

RESPONSE=$(send_once)
OK=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('ok',False))" 2>/dev/null || echo "False")

# One retry on rate limit (429) using Telegram-suggested retry_after
if [[ "$OK" != "True" ]]; then
  RETRY_AFTER=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('parameters',{}).get('retry_after',0) if d.get('error_code')==429 else 0)" 2>/dev/null || echo "0")
  if [[ "$RETRY_AFTER" -gt 0 && "$RETRY_AFTER" -le 30 ]]; then
    sleep "$RETRY_AFTER"
    RESPONSE=$(send_once)
    OK=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('ok',False))" 2>/dev/null || echo "False")
  fi
fi

# JSONL telemetry
LOG_FILE="${OPS_LOG_DIR:-$HOME/.openclaw/logs}/telegram-send-$(date -u +%Y-%m-%d).jsonl"
mkdir -p "$(dirname "$LOG_FILE")"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
BYTES=$(stat -f%z "$TRUNCATED" 2>/dev/null || stat -c%s "$TRUNCATED" 2>/dev/null || echo 0)
python3 -c "
import json
print(json.dumps({
    'ts': '$TS',
    'chat_id': '$CHAT_ID',
    'body_file': '$BODY_FILE',
    'bytes': $BYTES,
    'ok': '$OK' == 'True',
    'response_excerpt': '''$RESPONSE'''[:300],
}))
" >> "$LOG_FILE"

if [[ "$OK" != "True" ]]; then
  echo "TELEGRAM FAIL: $RESPONSE" >&2
  exit 3
fi

MSGID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['result']['message_id'])" 2>/dev/null || echo "?")
echo "SENT to chat_id=$CHAT_ID message_id=$MSGID bytes=$BYTES"
