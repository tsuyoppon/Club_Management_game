#!/bin/bash
set -euo pipefail

API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="pr5_fanbase@example.com"
USER_NAME="PR5 Fanbase User"

echo "Starting E2E PR5 Fanbase Verification..."

# 1. Setup Game, Clubs, Season, Fixtures
GAME_RESP=$(curl -s -X POST "$API_URL/games" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"name": "PR5 Game"}')
GAME_ID=$(echo $GAME_RESP | jq -r .id)
CLUB1_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"name": "Club A"}')
CLUB1_ID=$(echo $CLUB1_RESP | jq -r .id)
CLUB2_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"name": "Club B"}')
CLUB2_ID=$(echo $CLUB2_RESP | jq -r .id)
SEASON_RESP=$(curl -s -X POST "$API_URL/seasons/games/$GAME_ID" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"year_label": "2025"}')
SEASON_ID=$(echo $SEASON_RESP | jq -r .id)
curl -s -X POST "$API_URL/seasons/$SEASON_ID/fixtures/generate" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{}' > /dev/null

# 2. Get Current Turn (Aug)
TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" -H "X-User-Email: $USER_EMAIL")
TURN_ID=$(echo $TURN_RESP | jq -r .id)
echo "Turn ID: $TURN_ID (Aug)"

# 3. Input Decisions (Promo/HT)
echo "Inputting decisions..."
curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB1_ID/commit" \
  -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
  -d '{"payload": {"promo_expense": 10000000, "hometown_expense": 5000000, "next_home_promo": 5000000}}' > /dev/null

curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB2_ID/commit" \
  -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
  -d '{"payload": {"promo_expense": 5000000, "hometown_expense": 5000000}}' > /dev/null

# 4. Lock & Resolve
curl -s -X POST "$API_URL/turns/$TURN_ID/lock" -H "X-User-Email: $USER_EMAIL" > /dev/null
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" -H "X-User-Email: $USER_EMAIL" > /dev/null
echo "Turn Resolved."

# 5. Check FB State
echo "Checking FB State..."
FB_RESP=$(curl -s -X GET "$API_URL/clubs/$CLUB1_ID/fanbase?season_id=$SEASON_ID" -H "X-User-Email: $USER_EMAIL")
FB_COUNT=$(echo $FB_RESP | jq -r .fb_count)
echo "Club A FB Count: $FB_COUNT"

if [ "$FB_COUNT" -le 55000 ]; then
  echo "Error: FB Count did not increase (Expected > 55000, got $FB_COUNT)"
  exit 1
fi

# 6. Check Fixture Details (Weather/Attendance)
echo "Checking Fixture Details..."
# Find a fixture for Aug (Month 1)
SCHEDULE_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/clubs/$CLUB1_ID/schedule" -H "X-User-Email: $USER_EMAIL")
# We need fixture_id. But schedule endpoint returns simplified list.
# We need to use season schedule or just check if fields are present in schedule response (I added them).
WEATHER=$(echo $SCHEDULE_RESP | jq -r '.[0].weather')
ATTENDANCE=$(echo $SCHEDULE_RESP | jq -r '.[0].total_attendance')

echo "Weather: $WEATHER"
echo "Attendance: $ATTENDANCE"

if [ "$WEATHER" == "null" ] || [ "$ATTENDANCE" == "null" ]; then
  echo "Error: Weather or Attendance not populated."
  exit 1
fi

echo "E2E PR5 Fanbase Verification Passed!"
