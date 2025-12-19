#!/bin/bash
set -euo pipefail

# Configuration
API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="pr4_5@example.com"
USER_NAME="PR4_5 User"

echo "Starting E2E PR4.5 Match Results Verification..."

# 1. Create Game
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "PR4.5 Game"}')
echo "GAME_RESP: $GAME_RESP"
GAME_ID=$(echo $GAME_RESP | jq -r .id)
echo "Game ID: $GAME_ID"

# 2. Create Clubs (Need at least 2 for a match)
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

# 5. Get Current Turn (Should be Month 1)
echo "Getting Current Turn..."
TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
echo "TURN_RESP: $TURN_RESP"
TURN_ID=$(echo $TURN_RESP | jq -r .id)
MONTH_INDEX=$(echo $TURN_RESP | jq -r .month_index)
echo "Current Turn ID: $TURN_ID, Month: $MONTH_INDEX"

# 6. Resolve Turn (Month 1 -> Month 2)
# Matches usually start in Month 2 or later depending on schedule generation.
# Let's resolve Month 1.
echo "Resolving Turn (Month 1)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}' > /dev/null

# 6.5 Ack Turn (Month 1) to advance
echo "Acking Turn (Month 1)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/ack" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d "{\"club_id\": \"$CLUB1_ID\", \"ack\": true}" > /dev/null

curl -s -X POST "$API_URL/turns/$TURN_ID/ack" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d "{\"club_id\": \"$CLUB2_ID\", \"ack\": true}" > /dev/null

# 6.6 Advance Turn (Month 1 -> Month 2)
echo "Advancing Turn (Month 1)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/advance" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}' > /dev/null
# I can list all turns for the season.

echo "Getting All Turns..."
TURNS_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/turns" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
# echo "TURNS_RESP: $TURNS_RESP" # This endpoint might not exist or return list.

# Let's try to find Month 2 turn ID from database or by guessing?
# No, I should use the API.
# Is there an endpoint to list turns?
# I'll check routers/turns.py.

# 7. Get New Turn (Month 2)
echo "Getting New Turn..."
TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")
TURN_ID=$(echo $TURN_RESP | jq -r .id)
MONTH_INDEX=$(echo $TURN_RESP | jq -r .month_index)
echo "Current Turn ID: $TURN_ID, Month: $MONTH_INDEX"

# 8. Resolve Turn (Month 2) - This should process matches for Month 2
echo "Resolving Turn (Month 2)..."
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}' > /dev/null

# 9. Check Schedule for Results
echo "Checking Schedule for Results..."
SCHEDULE_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/schedule" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

# We expect matches in month 2 to have status 'played' and scores
# Month 2 matches are in key "2" (or whatever the month index is)
# Note: The schedule response is grouped by month index.
# We need to check if there are matches in month 2 and if they have scores.

echo "Schedule Response Sample (Month 2):"
echo $SCHEDULE_RESP | jq '."2"'

MATCH_STATUS=$(echo $SCHEDULE_RESP | jq -r '."2"[0].status')
HOME_GOALS=$(echo $SCHEDULE_RESP | jq -r '."2"[0].home_goals')

if [ "$MATCH_STATUS" == "played" ] && [ "$HOME_GOALS" != "null" ]; then
  echo "SUCCESS: Match processed. Status: $MATCH_STATUS, Home Goals: $HOME_GOALS"
else
  echo "FAILURE: Match not processed correctly."
  echo "Status: $MATCH_STATUS"
  echo "Home Goals: $HOME_GOALS"
  exit 1
fi

echo "E2E Verification Complete."
