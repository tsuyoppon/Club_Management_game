#!/bin/bash
set -e

API_URL="http://localhost:8000/api"
USER_EMAIL=${USER_EMAIL:-"e2e@example.com"}
USER_NAME=${USER_NAME:-"E2E User"}

echo "Starting E2E PR2 Finance..."

# 1. Create Game
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "E2E Finance Game"}')
echo "Response: $GAME_RESP"
GAME_ID=$(echo $GAME_RESP | jq -r .id)
echo "Game ID: $GAME_ID"

# 2. Create Club
echo "Creating Club..."
CLUB_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "E2E Club"}')
CLUB_ID=$(echo $CLUB_RESP | jq -r .id)
echo "Club ID: $CLUB_ID"

# 3. Create Season
echo "Creating Season..."
SEASON_RESP=$(curl -s -X POST "$API_URL/seasons/games/$GAME_ID" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"year_label": "2024"}')
echo "Season Response: $SEASON_RESP"
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
  -d '{"sponsor_base_monthly": 5000, "monthly_cost": 3000}' > /dev/null

# 6. Get Current Turn
echo "Getting Current Turn..."
TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
TURN_ID=$(echo $TURN_RESP | jq -r .id)
echo "Turn ID: $TURN_ID"

# Capture initial balance before processing
INIT_STATE_RESP=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
INIT_BALANCE=$(echo $INIT_STATE_RESP | jq -r .balance)
echo "Initial Balance: $INIT_BALANCE"

# 7. Advance Turn (Open -> Lock -> Resolve)
echo "Opening Turn..."
curl -s -X POST "$API_URL/turns/$TURN_ID/open" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

echo "Locking Turn..."
curl -s -X POST "$API_URL/turns/$TURN_ID/lock" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

echo "Resolving Turn..."
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

# 8. Verify Finance State
echo "Verifying Finance State..."
STATE_RESP=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
BALANCE=$(echo $STATE_RESP | jq -r .balance)

echo "Current Balance: $BALANCE"

EXPECTED=$(python - <<PY
init_bal = float("$INIT_BALANCE")
expected = init_bal + 5000 - 3000
print(int(expected) if expected.is_integer() else expected)
PY
)

DELTA=$(python - <<PY
init_bal = float("$INIT_BALANCE")
final_bal = float("$BALANCE")
print(final_bal - init_bal)
PY
)

if python - <<PY
delta = float("$DELTA")
expected_min = float("$EXPECTED") - float("$INIT_BALANCE")
import sys
sys.exit(0 if delta >= expected_min else 1)
PY
then
  echo "SUCCESS: Balance increased by at least monthly net (+2000)"
else
  echo "FAILURE: Balance did not increase as expected. Delta=$DELTA, Expected minimum increase=$(python - <<PY
init_bal = float("$INIT_BALANCE")
expected = init_bal + 5000 - 3000
print(expected - init_bal)
PY
)"
  exit 1
fi

echo "E2E PR2 Finance Completed Successfully."
