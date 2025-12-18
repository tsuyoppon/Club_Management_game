#!/bin/bash
set -euo pipefail

# Configuration
API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="test@example.com"
USER_NAME="Test User"

echo "Starting E2E PR2 Concurrency Verification..."

# 1. Create Game
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "Concurrency Game"}')
GAME_ID=$(echo $GAME_RESP | jq -r .id)
echo "Game ID: $GAME_ID"

# 2. Create Club
echo "Creating Club..."
CLUB_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "Concurrency Club"}')
CLUB_ID=$(echo $CLUB_RESP | jq -r .id)
echo "Club ID: $CLUB_ID"

# 3. Create Season
echo "Creating Season..."
SEASON_RESP=$(curl -s -X POST "$API_URL/seasons/games/$GAME_ID" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"year_label": "2024"}')
SEASON_ID=$(echo $SEASON_RESP | jq -r .id)
echo "Season ID: $SEASON_ID"

# 4. Generate Fixtures
echo "Generating Fixtures..."
curl -s -X POST "$API_URL/seasons/$SEASON_ID/fixtures/generate" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}' > /dev/null

# 5. Setup Finance Profile
echo "Setting up Finance Profile..."
curl -s -X PUT "$API_URL/clubs/$CLUB_ID/finance/profile" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"sponsor_base_monthly": 1000, "monthly_cost": 500}' > /dev/null

# 6. Get Current Turn
echo "Getting Current Turn..."
TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
TURN_ID=$(echo $TURN_RESP | jq -r .id)
echo "Turn ID: $TURN_ID"

# 7. Open Turn
echo "Opening Turn..."
curl -s -X POST "$API_URL/turns/$TURN_ID/open" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

# 8. Lock Turn
echo "Locking Turn..."
curl -s -X POST "$API_URL/turns/$TURN_ID/lock" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

# 9. Concurrent Resolve
echo "Launching Concurrent Resolve Requests..."
(curl -s -o /tmp/r1.json -w "%{http_code}" -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /tmp/code1) &
PID1=$!

(curl -s -o /tmp/r2.json -w "%{http_code}" -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /tmp/code2) &
PID2=$!

wait $PID1
wait $PID2

CODE1=$(cat /tmp/code1)
CODE2=$(cat /tmp/code2)

echo "Response 1: $CODE1"
echo "Response 2: $CODE2"

# 10. Verify Ledger Count
# We expect 2 entries (1 sponsor, 1 cost) for this turn.
# If we have 4, race condition failed.
# We need to query the DB directly or use an endpoint that exposes ledgers.
# Assuming we don't have a ledger list endpoint, we can check the balance.
# If balance is 500, good. If 1000, bad.

echo "Verifying Balance..."
STATE_AFTER=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
BALANCE_AFTER=$(echo $STATE_AFTER | jq -r .balance)
echo "Balance After: $BALANCE_AFTER"

if [ "$BALANCE_AFTER" -ne 500 ]; then
  echo "❌ FAIL: Balance is $BALANCE_AFTER, expected 500. Race condition detected!"
  exit 1
fi

echo "✅ PASS: Concurrency verified. Balance is 500."
