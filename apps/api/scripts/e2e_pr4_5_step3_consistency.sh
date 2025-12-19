#!/bin/bash
set -euo pipefail

# Configuration
API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="pr4_5_step3@example.com"
USER_NAME="PR4_5 Step3 User"

echo "Starting E2E PR4.5 Step 3 Consistency Verification..."

# 1. Create Game
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "PR4.5 Step3 Game"}')

if ! echo "$GAME_RESP" | jq -e .id > /dev/null; then
  echo "Error creating game. Response:"
  echo "$GAME_RESP"
  exit 1
fi

GAME_ID=$(echo $GAME_RESP | jq -r .id)
echo "Game ID: $GAME_ID"

# 2. Create Clubs
echo "Creating Home Club..."
CLUB1_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "Home FC"}')
CLUB1_ID=$(echo $CLUB1_RESP | jq -r .id)

echo "Creating Away Club..."
CLUB2_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "Away FC"}')
CLUB2_ID=$(echo $CLUB2_RESP | jq -r .id)

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

# 5. Verify Initial State (Month 1)
echo "Verifying Initial Schedule (Month 1)..."
SCHEDULE_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/schedule" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

# Check Month 1 matches are scheduled
MONTH1_MATCHES=$(echo $SCHEDULE_RESP | jq -r '."1"')
STATUS=$(echo $MONTH1_MATCHES | jq -r '.[0].status')
HOME_GOALS=$(echo $MONTH1_MATCHES | jq -r '.[0].home_goals')

if [ "$STATUS" != "scheduled" ]; then
  echo "Error: Expected status 'scheduled', got '$STATUS'"
  exit 1
fi

if [ "$HOME_GOALS" != "null" ]; then
  echo "Error: Expected home_goals null, got '$HOME_GOALS'"
  exit 1
fi

echo "Initial Schedule Verified."

echo "Verifying Initial Standings..."
STANDINGS_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/standings" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

PLAYED_COUNT=$(echo $STANDINGS_RESP | jq -r '.[0].played')
# If standings are empty or played is 0
if [ "$PLAYED_COUNT" != "null" ] && [ "$PLAYED_COUNT" != "0" ]; then
   echo "Error: Expected played 0, got '$PLAYED_COUNT'"
   exit 1
fi
echo "Initial Standings Verified."

# 6. Resolve Turn (Month 1)
echo "Getting Current Turn..."
TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
TURN_ID=$(echo $TURN_RESP | jq -r .id)

echo "Resolving Turn (Month 1)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}' > /dev/null

# 7. Verify Post-Resolve State
echo "Verifying Post-Resolve Schedule..."
SCHEDULE_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/schedule" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

MONTH1_MATCHES=$(echo $SCHEDULE_RESP | jq -r '."1"')
STATUS=$(echo $MONTH1_MATCHES | jq -r '.[0].status')
HOME_GOALS=$(echo $MONTH1_MATCHES | jq -r '.[0].home_goals')

if [ "$STATUS" != "played" ]; then
  echo "Error: Expected status 'played', got '$STATUS'"
  exit 1
fi

if [ "$HOME_GOALS" == "null" ]; then
  echo "Error: Expected home_goals not null"
  exit 1
fi
echo "Post-Resolve Schedule Verified. Goals: $HOME_GOALS"

echo "Verifying Post-Resolve Standings..."
STANDINGS_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/standings" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

PLAYED_COUNT=$(echo $STANDINGS_RESP | jq -r '.[0].played')
if [ "$PLAYED_COUNT" != "1" ]; then
   echo "Error: Expected played 1, got '$PLAYED_COUNT'"
   exit 1
fi
echo "Post-Resolve Standings Verified."

# 8. Verify Idempotency
echo "Resolving Turn Again (Idempotency Check)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}' > /dev/null

SCHEDULE_RESP_2=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/schedule" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

MONTH1_MATCHES_2=$(echo $SCHEDULE_RESP_2 | jq -r '."1"')
HOME_GOALS_2=$(echo $MONTH1_MATCHES_2 | jq -r '.[0].home_goals')

if [ "$HOME_GOALS" != "$HOME_GOALS_2" ]; then
  echo "Error: Idempotency failed. Goals changed from $HOME_GOALS to $HOME_GOALS_2"
  exit 1
fi

echo "Idempotency Verified."
echo "E2E PR4.5 Step 3 Consistency Verification Passed!"
