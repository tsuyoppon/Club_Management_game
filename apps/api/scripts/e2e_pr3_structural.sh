#!/bin/bash
set -euo pipefail

# Configuration
API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="pr3@example.com"
USER_NAME="PR3 User"

echo "Starting E2E PR3 Structural Finance Verification..."

# 1. Create Game
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "PR3 Game"}')
GAME_ID=$(echo $GAME_RESP | jq -r .id)

# 2. Create Club
echo "Creating Club..."
CLUB_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "PR3 Club"}')
CLUB_ID=$(echo $CLUB_RESP | jq -r .id)

# 3. Create Season
echo "Creating Season..."
SEASON_RESP=$(curl -s -X POST "$API_URL/seasons/games/$GAME_ID" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"year_label": "2024"}')
SEASON_ID=$(echo $SEASON_RESP | jq -r .id)

# 4. Generate Fixtures
echo "Generating Fixtures..."
curl -s -X POST "$API_URL/seasons/$SEASON_ID/fixtures/generate" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}' > /dev/null

# 5. Setup Structural Elements
echo "Setting up Sponsors (10)..."
curl -s -X PUT "$API_URL/finance/clubs/$CLUB_ID/sponsors?count=10" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" > /dev/null

echo "Setting up Reinforcement (12M)..."
curl -s -X PUT "$API_URL/finance/clubs/$CLUB_ID/reinforcement" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"annual_budget": 12000000}' > /dev/null

# 6. Process Turn 1 (August)
echo "Processing Turn 1 (August)..."
TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
TURN_ID=$(echo $TURN_RESP | jq -r .id)

curl -s -X POST "$API_URL/turns/$TURN_ID/open" -H "X-User-Email: $USER_EMAIL" -H "X-User-Name: $USER_NAME" > /dev/null
curl -s -X POST "$API_URL/turns/$TURN_ID/lock" -H "X-User-Email: $USER_EMAIL" -H "X-User-Name: $USER_NAME" > /dev/null
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" -H "X-User-Email: $USER_EMAIL" -H "X-User-Name: $USER_NAME" > /dev/null

# 7. Verify Balance
echo "Verifying Balance..."
STATE=$(curl -s -X GET "$API_URL/clubs/$CLUB_ID/finance/state" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
BALANCE=$(echo $STATE | jq -r .balance)
echo "Balance: $BALANCE"

# Expected: 50M (Sponsor) - 1M (Reinf) - 3M (Staff) = 46M
if [ "$BALANCE" == "46000000.00" ] || [ "$BALANCE" == "46000000" ]; then
  echo "✅ PASS: Balance is 46M"
else
  echo "❌ FAIL: Expected 46000000, got $BALANCE"
  exit 1
fi

echo "E2E PR3 Structural Finance Completed Successfully."
