#!/bin/bash
set -euo pipefail

# Configuration
API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="test@example.com"
USER_NAME="Test User"

echo "Starting E2E PR2 Idempotency Verification..."

# 1. Create Game
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "Idempotency Game"}')
GAME_ID=$(echo $GAME_RESP | jq -r .id)
echo "Game ID: $GAME_ID"

# 2. Create Club
echo "Creating Club..."
CLUB_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "Idempotency Club"}')
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

# 9. Capture State BEFORE Resolve
echo "Capturing State BEFORE Resolve..."
STATE_BEFORE=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
BALANCE_BEFORE=$(echo $STATE_BEFORE | jq -r .balance)
echo "Balance Before: $BALANCE_BEFORE"

# 10. Resolve Turn (1st time)
echo "Resolving Turn (1st time)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

# 11. Capture State AFTER 1st Resolve
echo "Capturing State AFTER 1st Resolve..."
STATE_AFTER_1=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
BALANCE_AFTER_1=$(echo $STATE_AFTER_1 | jq -r .balance)
echo "Balance After 1st Resolve: $BALANCE_AFTER_1"

# 12. Resolve Turn (2nd time)
echo "Resolving Turn (2nd time)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

# 13. Capture State AFTER 2nd Resolve
echo "Capturing State AFTER 2nd Resolve..."
STATE_AFTER_2=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
BALANCE_AFTER_2=$(echo $STATE_AFTER_2 | jq -r .balance)
echo "Balance After 2nd Resolve: $BALANCE_AFTER_2"

# 14. Assertions
EXPECTED_BALANCE=$((BALANCE_BEFORE + 1000 - 500))

if [ "$BALANCE_AFTER_1" -ne "$EXPECTED_BALANCE" ]; then
  echo "❌ FAIL: Balance after 1st resolve is incorrect. Expected $EXPECTED_BALANCE, got $BALANCE_AFTER_1"
  exit 1
fi

if [ "$BALANCE_AFTER_1" -ne "$BALANCE_AFTER_2" ]; then
  echo "❌ FAIL: Balance changed after 2nd resolve. Idempotency failed."
  echo "1st: $BALANCE_AFTER_1, 2nd: $BALANCE_AFTER_2"
  exit 1
fi

echo "✅ PASS: Idempotency verified. Balance stable at $BALANCE_AFTER_2"
