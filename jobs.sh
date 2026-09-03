#!/usr/bin/env bash
# jobs.sh : create the 6 OpenClaw cron jobs this pack ships. Edit the
# placeholders below (CHAT_ID, MODEL, TZ) before running, or export them first:
#   CHAT_ID=123456789 MODEL=cf-workers-ai/@cf/deepseek-ai/deepseek-v4-pro-0813 TZ=Europe/Dublin ./jobs.sh
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

CHAT_ID="${CHAT_ID:-YOUR_TELEGRAM_CHAT_ID}"
MODEL="${MODEL:-cf-workers-ai/@cf/deepseek-ai/deepseek-v4-pro-0813}"
TZ_NAME="${TZ:-Europe/Dublin}"

if [[ "$CHAT_ID" == "YOUR_TELEGRAM_CHAT_ID" && "$DRY_RUN" == 0 ]]; then
  echo "set CHAT_ID (and optionally MODEL, TZ) before running this, see the header comment"
  exit 1
fi

# ponytail: --dry-run prints the command instead of executing it, one line per job
cron_add() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf 'openclaw cron add'
    printf ' %q' "$@"
    printf '\n'
  else
    openclaw cron add "$@"
  fi
}

cron_add --name mail-sweep-hourly \
  --description "[MAIL] hourly sweep of configured mailboxes for your keyword list" \
  --cron "5 8-22 * * *" --tz "$TZ_NAME" \
  --session isolated --wake now --model "$MODEL" --timeout-seconds 600 \
  --tools exec,read,write \
  --message 'Job [MAIL] mail-sweep-hourly. Run exactly: python3 "$HOME/.openclaw/scripts/mail-sweep.py" --hours 3 --text ; note the exit code. Exit 0 = no hits: reply with the single word SILENT and nothing else (no Telegram). Exit 10 = hits: reply with the script text block verbatim, prefixed [MAIL]. Exit 2 = error: reply "[MAIL] sweep error, exit 2" plus the first error line. Always end with the gate in brackets like [exit 10, 2 hits]. Never open, forward or reply to any mail. No em-dashes.' \
  --announce --channel telegram --to "$CHAT_ID"

cron_add --name loops-brief-daily \
  --description "[LOOPS] daily top loops, due-in-7-days, latest ledger section" \
  --cron "30 7 * * *" --tz "$TZ_NAME" \
  --session isolated --wake now --model "$MODEL" --timeout-seconds 300 \
  --tools exec,read,write \
  --message 'Job [LOOPS] loops-brief-daily. Run exactly: python3 "$HOME/.openclaw/scripts/loops-brief.py" and note the exit code. Reply with the brief prefixed [LOOPS], trimmed to the 3 headings and at most 12 lines total, then one line "Do first today: <the single highest-impact next action from TOP LOOPS or DUE 7D>". End with the gate in brackets like [exit 0]. Read-only. No em-dashes.' \
  --announce --channel telegram --to "$CHAT_ID"

cron_add --name calendar-prep-daily \
  --description "[PREP] daily calendar look-ahead and per-event prep note" \
  --cron "0 7 * * *" --tz "$TZ_NAME" \
  --session isolated --wake now --model "$MODEL" --timeout-seconds 300 \
  --tools exec,read,write \
  --message 'Job [PREP] calendar-prep-daily. Run exactly: bash "$HOME/.openclaw/scripts/calendar-next.sh" 14 and note the exit code. For every event starting within the next 48 hours, write or update a one-paragraph prep note (what it is, where, what to bring). Reply prefixed [PREP] with a summary, at most 10 lines. End with the gate in brackets like [exit 0, N events]. No em-dashes.' \
  --announce --channel telegram --to "$CHAT_ID"

cron_add --name ledger-diff-daily \
  --description "[LEDGER] daily diff of the files in OPS_WATCH_FILES" \
  --cron "0 18 * * *" --tz "$TZ_NAME" \
  --session isolated --wake now --model "$MODEL" --timeout-seconds 300 \
  --tools exec,read,write \
  --message 'Job [LEDGER] ledger-diff-daily. Run exactly: bash "$HOME/.openclaw/scripts/ledger-diff.sh" and note the exit code. Exit 0 = reply the single word SILENT and nothing else. Exit 10 = reply prefixed [LEDGER] with a 6-line max summary of what changed (which file, added or removed lines in plain words). Exit 2 = "[LEDGER] missing file" plus the line. End with the gate in brackets like [exit 10, 2 files changed]. Read-only. No em-dashes.' \
  --announce --channel telegram --to "$CHAT_ID"

cron_add --name research-weekly \
  --description "[RESEARCH] weekly web research scan, topic set in the job message" \
  --cron "0 9 * * 1" --tz "$TZ_NAME" \
  --session isolated --wake now --model "$MODEL" --timeout-seconds 900 \
  --tools exec,read,write \
  --message 'Job [RESEARCH] research-weekly. Research the last 7 days on YOUR TOPIC HERE using whatever web-research tool or skill you have connected, 6 to 10 sources. Write findings to a dated file and reply prefixed [RESEARCH] with a 6-line max summary. End with the gate in brackets like [exit 0, N sources]. No em-dashes. EDIT THIS MESSAGE before relying on this job, it ships as a placeholder.' \
  --announce --channel telegram --to "$CHAT_ID"

cron_add --name credit-burn-nightly \
  --description "[CF-BURN] nightly Cloudflare credit burn line to Telegram" \
  --cron "0 22 * * *" --tz "$TZ_NAME" \
  --session isolated --wake now --model "$MODEL" --timeout-seconds 300 \
  --tools exec \
  --message 'Job [CF-BURN] credit-burn-nightly. Run exactly: bash "$HOME/.openclaw/scripts/cf-cost-tracker.sh" --telegram ; the script sends its own Telegram line. Reply with the single word SILENT plus the exit code in brackets, nothing else.'

echo "6 jobs created (or updated). Run: openclaw cron list"
