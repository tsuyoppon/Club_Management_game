#!/bin/bash
set -euo pipefail

# Configuration
API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="pr4_5_step4@example.com"
USER_NAME="PR4_5 Step4 User"

echo "Starting E2E PR4.5 Step 4 Finalize Verification..."

# 1. Create Game
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{"name": "PR4.5 Step4 Game"}')
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

# 5. Verify Status (Incomplete)
echo "Verifying Status (Incomplete)..."
STATUS_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/status" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

IS_COMPLETED=$(echo $STATUS_RESP | jq -r .is_completed)
if [ "$IS_COMPLETED" != "false" ]; then
  echo "Error: Expected is_completed false, got $IS_COMPLETED"
  exit 1
fi

# 6. Try Finalize (Should Fail)
echo "Attempting Premature Finalize..."
FINALIZE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/seasons/$SEASON_ID/finalize" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}')

if [ "$FINALIZE_CODE" != "409" ]; then
  echo "Error: Expected 409 Conflict, got $FINALIZE_CODE"
  exit 1
fi
echo "Premature Finalize Rejected (Correct)."

# 7. Resolve All Turns
echo "Resolving All Turns..."
# We need to find all turns or just iterate months.
# Fixtures are generated for 10 months (usually).
# Let's get current turn and advance until no more turns or season finished.
# But simpler: just loop 12 times.

for i in {1..12}; do
    TURN_RESP=$(curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" \
      -H "X-User-Email: $USER_EMAIL" \
      -H "X-User-Name: $USER_NAME")
    
    # Check if turn exists (might return 404 if season finished? or empty)
    # The API returns 404 if no current turn? Or returns the last one?
    # Assuming it returns valid turn.
    TURN_ID=$(echo $TURN_RESP | jq -r .id)
    if [ "$TURN_ID" == "null" ]; then
        echo "No more turns."
        break
    fi
    
    echo "Resolving Turn $i (ID: $TURN_ID)..."
    curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" \
      -H "Content-Type: application/json" \
      -H "X-User-Email: $USER_EMAIL" \
      -H "X-User-Name: $USER_NAME" \
      -d '{}' > /dev/null
      
    # Ack to advance
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
      
    # Advance
    curl -s -X POST "$API_URL/turns/$TURN_ID/advance" \
      -H "Content-Type: application/json" \
      -H "X-User-Email: $USER_EMAIL" \
      -H "X-User-Name: $USER_NAME" \
      -d '{}' > /dev/null
done

# 8. Verify Status (Completed)
echo "Verifying Status (Completed)..."
STATUS_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/status" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME")

IS_COMPLETED=$(echo $STATUS_RESP | jq -r .is_completed)
UNPLAYED=$(echo $STATUS_RESP | jq -r .unplayed_matches)

if [ "$IS_COMPLETED" != "true" ]; then
  echo "Error: Expected is_completed true, got $IS_COMPLETED. Unplayed: $UNPLAYED"
  exit 1
fi

# 9. Finalize (Should Success)
echo "Finalizing Season..."
FINALIZE_RESP=$(curl -s -X POST "$API_URL/seasons/$SEASON_ID/finalize" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}')

# Check if response is a list (standings)
IS_ARRAY=$(echo $FINALIZE_RESP | jq 'if type=="array" then "yes" else "no" end')
if [ "$IS_ARRAY" != "\"yes\"" ]; then
  echo "Error: Expected array response, got $FINALIZE_RESP"
  exit 1
fi
echo "Season Finalized Successfully."

# 10. Verify Idempotency
echo "Finalizing Again (Idempotency)..."
FINALIZE_RESP_2=$(curl -s -X POST "$API_URL/seasons/$SEASON_ID/finalize" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $USER_EMAIL" \
  -H "X-User-Name: $USER_NAME" \
  -d '{}')

if [ "$FINALIZE_RESP" != "$FINALIZE_RESP_2" ]; then
  echo "Error: Idempotency failed."
  exit 1
fi

echo "E2E PR4.5 Step 4 Finalize Verification Passed!"
