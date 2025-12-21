#!/bin/bash
# PR9 Integration E2E: Turn flow -> disclosure events -> final results
# Verifies that resolving turns triggers disclosures (Dec/Jul) and final-results generation works

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_URL="$BASE_URL/api"
AUTH_HEADER_EMAIL="X-User-Email: gm@example.com"
AUTH_HEADER_NAME="X-User-Name: E2E Runner"

log() { echo "$@"; }

log "=== PR9 Turn Flow E2E ==="
log "Base URL: $BASE_URL"

# 1. Create game & clubs & season
log "1) Creating game/clubs/season..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{"name": "PR9 Turn Flow Game"}')
GAME_ID=$(echo $GAME_RESP | jq -r .id)
log "Game ID: $GAME_ID"

CLUB_A_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{"name": "Flow Club A", "short_name": "FCA"}')
CLUB_A_ID=$(echo $CLUB_A_RESP | jq -r .id)
log "Club A ID: $CLUB_A_ID"

CLUB_B_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{"name": "Flow Club B", "short_name": "FCB"}')
CLUB_B_ID=$(echo $CLUB_B_RESP | jq -r .id)
log "Club B ID: $CLUB_B_ID"

SEASON_RESP=$(curl -s -X POST "$API_URL/seasons/games/$GAME_ID" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{"year_label": "2025"}')
SEASON_ID=$(echo $SEASON_RESP | jq -r .id)
log "Season ID: $SEASON_ID"

log "Generating fixtures..."
curl -s -X POST "$API_URL/seasons/$SEASON_ID/fixtures/generate" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{}' > /dev/null

# helper to ack both clubs
ack_turn() {
  local turn_id="$1"
  curl -s -X POST "$API_URL/turns/$turn_id/ack" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{"club_id": "'$CLUB_A_ID'", "ack": true}' > /dev/null
  curl -s -X POST "$API_URL/turns/$turn_id/ack" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{"club_id": "'$CLUB_B_ID'", "ack": true}' > /dev/null
}

# helper to check disclosures
check_disclosure() {
  local type="$1"
  local expect_status="$2"
  STATUS=$(curl -s -o /tmp/disc_body -w "%{http_code}" "$API_URL/seasons/$SEASON_ID/disclosures/$type" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME")
  BODY=$(cat /tmp/disc_body)
  log "  Disclosure $type status $STATUS: $BODY"
  if [ "$STATUS" != "$expect_status" ]; then
    echo "❌ FAIL: disclosure $type expected $expect_status, got $STATUS"; exit 1
  fi
}

# 2. Iterate through turns until none left
TURN_COUNT=0
while true; do
  CURR_RESP=$(curl -s "$API_URL/turns/seasons/$SEASON_ID/current" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME")
  CURR_ID=$(echo $CURR_RESP | jq -r .id)
  if [ "$CURR_ID" = "null" ] || [ -z "$CURR_ID" ]; then
    log "No current turn found; season likely completed."; break
  fi
  MONTH_INDEX=$(echo $CURR_RESP | jq -r .month_index)
  TURN_COUNT=$((TURN_COUNT+1))
  log "-- Turn $TURN_COUNT | month_index=$MONTH_INDEX (id=$CURR_ID)"

  # open/lock/resolve
  curl -s -X POST "$API_URL/turns/$CURR_ID/open" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" > /dev/null
  curl -s -X POST "$API_URL/turns/$CURR_ID/lock" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" > /dev/null
  curl -s -X POST "$API_URL/turns/$CURR_ID/resolve" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" > /dev/null

  # disclosure checkpoints
  if [ "$MONTH_INDEX" -eq 5 ]; then
    log "  Checking December disclosures..."
    check_disclosure "financial_summary" "200"
    check_disclosure "team_power_december" "200"
  fi
  if [ "$MONTH_INDEX" -eq 12 ]; then
    log "  Checking July disclosures..."
    check_disclosure "team_power_july" "200"
  fi

  # ack & advance
  ack_turn "$CURR_ID"
  curl -s -X POST "$API_URL/turns/$CURR_ID/advance" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME" -H "Content-Type: application/json" -d '{"club_id": "'$CLUB_A_ID'"}' > /dev/null || true
  # loop continues to pick next current
done

# 3. Finalize season (needed before final results exist)
log "3) Finalizing season..."
FINALIZE_STATUS=$(curl -s -o /tmp/finalize_body -w "%{http_code}" -X POST "$API_URL/seasons/$SEASON_ID/finalize" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME")
FINALIZE_BODY=$(cat /tmp/finalize_body)
log "  Finalize status $FINALIZE_STATUS: $FINALIZE_BODY"
if [ "$FINALIZE_STATUS" != "200" ]; then
  echo "❌ FAIL: season finalize failed"; exit 1
fi
FINALIZE_LEN=$(echo "$FINALIZE_BODY" | jq length 2>/dev/null || echo "0")
if [ "$FINALIZE_LEN" -eq 0 ]; then
  echo "❌ FAIL: finalize returned empty standings"; exit 1
fi

# 4. Final results generation (should now be non-empty)
log "4) Generating final results..."
FINAL_GEN_STATUS=$(curl -s -o /tmp/final_gen_body -w "%{http_code}" -X POST "$API_URL/games/$GAME_ID/final-results/generate" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME")
FINAL_GEN_BODY=$(cat /tmp/final_gen_body)
log "  Final results generate status $FINAL_GEN_STATUS: $FINAL_GEN_BODY"
if [ "$FINAL_GEN_STATUS" != "200" ]; then
  echo "❌ FAIL: final results generation failed"; exit 1
fi

log "Fetching final results..."
FINAL_STATUS=$(curl -s -o /tmp/final_body -w "%{http_code}" "$API_URL/games/$GAME_ID/final-results" -H "$AUTH_HEADER_EMAIL" -H "$AUTH_HEADER_NAME")
FINAL_BODY=$(cat /tmp/final_body)
log "  Final results status $FINAL_STATUS: $FINAL_BODY"
if [ "$FINAL_STATUS" != "200" ]; then
  echo "❌ FAIL: final results retrieval failed"; exit 1
fi
FINAL_LEN=$(echo "$FINAL_BODY" | jq length 2>/dev/null || echo "0")
if [ "$FINAL_LEN" -eq 0 ]; then
  echo "❌ FAIL: final results empty; expected entries after season finalize"; exit 1
fi

log "=== PR9 Turn Flow E2E PASSED ==="
