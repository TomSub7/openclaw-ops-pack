#!/bin/bash
# cf-cost-tracker.sh
# Daily Cloudflare spend tracker: a Worker's request cost, Workers AI neuron
# burn, and AI Gateway request counts by provider. Meant to run once a day
# from a scheduler (cron, launchd, or an OpenClaw job).
#
# One JSONL line per run to OPS_LOG_DIR (default ~/.openclaw/logs/), exit code
# reflects whether budget thresholds are tripped.
#
# Usage:
#   cf-cost-tracker.sh                    # uses CF_API_TOKEN from env
#   cf-cost-tracker.sh --telegram         # also send the daily burn line via Telegram
#                                          # (needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)
#
# Config (env vars, see ops-pack.env.example):
#   CF_API_TOKEN          Cloudflare API token, GraphQL Account Analytics Read
#   CF_ACCOUNT_ID         Cloudflare account id (required)
#   CF_WORKER_NAME         Worker service name to report request cost for (required)
#   CF_CREDIT_TOTAL_USD    total credit pool to pace against (default 5000)
#   CF_CREDIT_EXPIRY       ISO date the credit pool expires (default one year out)
#   CF_PACE_START          ISO date pacing starts from (default today)
#
# Workers AI neurons + AI Gateway request counts come from the Cloudflare GraphQL
# analytics API (the REST .../ai/run endpoint does not carry usage data).
#
# Exit codes:
#   0  spend within thresholds (an "under_pace" trip reason is informational only,
#      it never changes the exit code)
#   1  worker req cost over $5/day OR Workers AI neurons (today) over 3000000
#   2  IO error, missing token/config, or CF API non-200

set -uo pipefail

LOG_DIR="${OPS_LOG_DIR:-$HOME/.openclaw/logs}"
LOG_FILE="$LOG_DIR/cf-cost-$(date +%F).jsonl"
ACCOUNT_ID="${CF_ACCOUNT_ID:-}"
WORKER_NAME="${CF_WORKER_NAME:-}"

CREDIT_TOTAL_USD="${CF_CREDIT_TOTAL_USD:-5000}"
CREDIT_EXPIRY="${CF_CREDIT_EXPIRY:-$(date -u -v+1y +%Y-%m-%d 2>/dev/null || date -u -d '+1 year' +%Y-%m-%d)}"
PACE_START="${CF_PACE_START:-$(date -u +%Y-%m-%d)}"

TELEGRAM=false
for arg in "$@"; do
  [[ "$arg" == "--telegram" ]] && TELEGRAM=true
done

mkdir -p "$LOG_DIR" || exit 2
command -v curl >/dev/null 2>&1 || { echo "curl missing"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "jq missing"; exit 2; }

if [[ -z "$ACCOUNT_ID" || -z "$WORKER_NAME" ]]; then
  echo "CF_ACCOUNT_ID and CF_WORKER_NAME must be set, see ops-pack.env.example"
  exit 2
fi

TOKEN="${CF_API_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "CF_API_TOKEN not set"
  exit 2
fi

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TODAY=$(date -u +"%Y-%m-%d")
MONTH_START=$(date -u +"%Y-%m-01")
SINCE=$(date -u -v-24H +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "24 hours ago" +"%Y-%m-%dT%H:%M:%SZ")

API="https://api.cloudflare.com/client/v4"
HDR_AUTH="Authorization: Bearer $TOKEN"
HDR_TYPE="Content-Type: application/json"

# Worker analytics, 24h
WORKER_RESPONSE=$(curl -s -m 20 -H "$HDR_AUTH" -H "$HDR_TYPE" \
  "$API/accounts/$ACCOUNT_ID/workers/services/$WORKER_NAME" 2>/dev/null)
if ! echo "$WORKER_RESPONSE" | jq -e '.success' >/dev/null 2>&1; then
  WORKER_REQUESTS="null"
  WORKER_ERRORS="null"
else
  WORKER_REQUESTS=$(echo "$WORKER_RESPONSE" | jq -r '.result.usage.requests_24h // 0')
  WORKER_ERRORS=$(echo "$WORKER_RESPONSE" | jq -r '.result.usage.errors_24h // 0')
fi

if [[ "$WORKER_REQUESTS" =~ ^[0-9]+$ ]]; then
  REQ_M=$(awk -v r="$WORKER_REQUESTS" 'BEGIN {printf "%.6f", r/1000000}')
  REQ_COST=$(awk -v rm="$REQ_M" 'BEGIN {printf "%.4f", rm*0.30}')
else
  REQ_M="null"
  REQ_COST="null"
fi

# Workers AI neurons (today + month-to-date) and AI Gateway request counts by
# provider, both in one GraphQL call.
GQL_QUERY=$(cat <<GQL
query {
  viewer {
    accounts(filter: {accountTag: "$ACCOUNT_ID"}) {
      aiInferenceAdaptiveGroups(limit: 200, filter: {date_geq: "$MONTH_START"}) {
        dimensions { date modelId }
        count
        sum { totalNeurons }
      }
      aiGatewayRequestsAdaptiveGroups(limit: 1000, filter: {datetime_geq: "$SINCE"}) {
        dimensions { provider gateway }
        count
      }
    }
  }
}
GQL
)
GQL_PAYLOAD=$(jq -n --arg q "$GQL_QUERY" '{query: $q}')
GQL_RESPONSE=$(curl -s -m 20 -X POST "$API/graphql" -H "$HDR_AUTH" -H "$HDR_TYPE" -d "$GQL_PAYLOAD" 2>/dev/null)

ACC=$(echo "$GQL_RESPONSE" | jq -c '.data.viewer.accounts[0] // empty' 2>/dev/null)
if [[ -z "$ACC" ]]; then
  NEURON_ROWS='[]'
  GATEWAY_ROWS='[]'
else
  NEURON_ROWS=$(echo "$ACC" | jq -c '.aiInferenceAdaptiveGroups // []')
  GATEWAY_ROWS=$(echo "$ACC" | jq -c '.aiGatewayRequestsAdaptiveGroups // []')
fi

NEURONS_MTD=$(echo "$NEURON_ROWS" | jq '[.[].sum.totalNeurons] | add // 0')
NEURONS_24H=$(echo "$NEURON_ROWS" | jq --arg d "$TODAY" '[.[] | select(.dimensions.date==$d) | .sum.totalNeurons] | add // 0')
TOP_MODELS=$(echo "$NEURON_ROWS" | jq -r --arg d "$TODAY" '
  [.[] | select(.dimensions.date==$d)]
  | group_by(.dimensions.modelId)
  | map({model: (.[0].dimensions.modelId | split("/") | last), neurons: ([.[].sum.totalNeurons] | add)})
  | sort_by(-.neurons) | .[0:2]
  | map("\(.model) \(.neurons | round)") | join(", ")')

GATEWAY_SUMMARY=$(echo "$GATEWAY_ROWS" | jq -r '
  group_by(.dimensions.provider)
  | map({provider: .[0].dimensions.provider, count: ([.[].count] | add)})
  | map("\(.provider) \(.count)") | join(", ")')

AI_COST_24H=$(awk -v n="$NEURONS_24H" 'BEGIN {printf "%.4f", n*0.011/1000}')
AI_COST_MTD=$(awk -v n="$NEURONS_MTD" 'BEGIN {printf "%.4f", n*0.011/1000}')

# Pace: flat daily burn to spend CREDIT_TOTAL_USD by CREDIT_EXPIRY, from PACE_START.
DAYS_TOTAL=$(( ( $(date -u -j -f "%Y-%m-%d" "$CREDIT_EXPIRY" +%s 2>/dev/null || date -u -d "$CREDIT_EXPIRY" +%s) \
               - $(date -u -j -f "%Y-%m-%d" "$PACE_START" +%s 2>/dev/null || date -u -d "$PACE_START" +%s) ) / 86400 ))
[[ "$DAYS_TOTAL" -le 0 ]] && DAYS_TOTAL=1
PACE_TARGET=$(awk -v c="$CREDIT_TOTAL_USD" -v d="$DAYS_TOTAL" 'BEGIN {printf "%.2f", c/d}')

# Threshold check (worker req cost + Workers AI neurons)
TRIPPED="false"
TRIP_REASONS=""
if [[ "$REQ_COST" != "null" ]] && (( $(awk -v c="$REQ_COST" 'BEGIN {print (c > 5.0)}') )); then
  TRIPPED="true"
  TRIP_REASONS+="daily_spend_over_5usd,"
fi
if (( $(awk -v n="$NEURONS_24H" 'BEGIN {print (n > 3000000)}') )); then
  TRIPPED="true"
  TRIP_REASONS+="workers_ai_neurons_over_3000000,"
fi
# Informational only: under-pace never trips the exit code.
if (( $(awk -v c="$AI_COST_24H" -v t="$PACE_TARGET" 'BEGIN {print (c < t*0.5)}') )); then
  TRIP_REASONS+="under_pace,"
fi
TRIP_REASONS="${TRIP_REASONS%,}"

EXIT_CODE=0
[[ "$TRIPPED" == "true" ]] && EXIT_CODE=1

# Emit JSONL
printf '{"ts":"%s","worker_requests_24h":%s,"worker_errors_24h":%s,"worker_req_cost_usd":"%s","ai_neurons_24h":%s,"ai_neurons_mtd":%s,"ai_cost_24h_usd":"%s","ai_cost_mtd_usd":"%s","pace_target_usd":"%s","gateway_requests_by_provider_24h":"%s","tripped":%s,"trip_reasons":"%s"}\n' \
  "$TS" "$WORKER_REQUESTS" "$WORKER_ERRORS" "$REQ_COST" "$NEURONS_24H" "$NEURONS_MTD" "$AI_COST_24H" "$AI_COST_MTD" "$PACE_TARGET" "$GATEWAY_SUMMARY" "$TRIPPED" "$TRIP_REASONS" >> "$LOG_FILE"

printf '[%s] worker_reqs=%s ai_neurons_24h=%s spend_24h=$%s pace: today USD %s vs target %s (Workers AI only), month-to-date USD %s | gateway 24h: %s | tripped=%s\n' \
  "$TS" "$WORKER_REQUESTS" "$NEURONS_24H" "$REQ_COST" "$AI_COST_24H" "$PACE_TARGET" "$AI_COST_MTD" "${GATEWAY_SUMMARY:-none}" "$TRIPPED"

if [[ "$TELEGRAM" == "true" ]]; then
  DATE_DD_MM=$(date -u -j -f "%Y-%m-%d" "$TODAY" +"%d.%m" 2>/dev/null || date -u -d "$TODAY" +"%d.%m")
  NEURONS_K=$(awk -v n="$NEURONS_24H" 'BEGIN {printf "%.0f", n/1000}')
  MSG_FILE=$(mktemp /tmp/cf-cost-tg.XXXXXX.txt)
  printf '[CF-BURN] %s | Workers AI today USD %s (%sk neurons) | MTD USD %s | target %s per day | top: %s\n' \
    "$DATE_DD_MM" "$AI_COST_24H" "$NEURONS_K" "$AI_COST_MTD" "$PACE_TARGET" "${TOP_MODELS:-none}" > "$MSG_FILE"
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  bash "$SCRIPT_DIR/telegram-send.sh" "$MSG_FILE"
  TG_EXIT=$?
  rm -f "$MSG_FILE"
  if [[ "$TG_EXIT" -ne 0 && "$EXIT_CODE" -eq 0 ]]; then
    EXIT_CODE=2
  fi
fi

exit "$EXIT_CODE"
