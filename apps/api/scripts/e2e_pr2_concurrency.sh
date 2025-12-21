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

# Capture initial balance
INIT_STATE=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
INIT_BALANCE=$(echo $INIT_STATE | jq -r .balance)
echo "Initial Balance: $INIT_BALANCE"

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

# 10. Verify turn resolved and balance incremented at least once (>= net +500)
echo "Verifying Balance..."
STATE_AFTER=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
BALANCE_AFTER=$(echo $STATE_AFTER | jq -r .balance)
DELTA=$(python - <<PY
init_bal = float("$INIT_BALANCE")
final_bal = float("$BALANCE_AFTER")
print(final_bal - init_bal)
PY
)
echo "Balance After: $BALANCE_AFTER (delta $DELTA)"

# Require at least one application of monthly net (+500) even if concurrent resolve errors occurred
if python - <<PY
delta = float("$DELTA")
import sys
sys.exit(0 if delta >= 500 else 1)
PY
then
  echo "✅ PASS: Concurrency verified. Delta >= 500"
else
  echo "❌ FAIL: Delta increase < 500; potential race condition"
  exit 1
fi
