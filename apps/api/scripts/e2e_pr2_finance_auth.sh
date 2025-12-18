#!/bin/bash
set -euo pipefail

# Configuration
API_URL=${API_URL:-"http://localhost:8000/api"}
GM_EMAIL="gm_e2e@example.com"
GM_NAME="GM User"
OWNER_EMAIL="owner_e2e@example.com"
OWNER_NAME="Owner User"

echo "Starting E2E PR2 Finance Auth Verification..."

# 1. Create Game (as GM)
echo "Creating Game..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $GM_EMAIL" \
  -H "X-User-Name: $GM_NAME" \
  -d '{"name": "Auth E2E Game"}')
GAME_ID=$(echo $GAME_RESP | jq -r .id)
echo "Game ID: $GAME_ID"

# 2. Create Club (as GM)
echo "Creating Club..."
CLUB_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $GM_EMAIL" \
  -H "X-User-Name: $GM_NAME" \
  -d '{"name": "Auth E2E Club"}')
CLUB_ID=$(echo $CLUB_RESP | jq -r .id)
echo "Club ID: $CLUB_ID"

# 3. Create Owner User (by making a request)
# We'll create a dummy game to ensure user exists
echo "Creating Dummy Game to register Owner User..."
curl -s -X POST "$API_URL/games" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $OWNER_EMAIL" \
  -H "X-User-Name: $OWNER_NAME" \
  -d '{"name": "Dummy Game"}' > /dev/null

# Now insert membership via SQL
echo "Assigning Owner Role..."
# We need to find the user_id for OWNER_EMAIL
# We can use docker compose exec to run psql
# Note: This assumes we are running from the host and have access to docker.
# If this script runs inside the container, it won't work.
# The instructions say "Prefer adding E2E scripts under: apps/api/scripts/".
# If I run this from host, I can use docker compose.

OWNER_USER_ID=$(docker compose exec -T db psql -U postgres -d club_game -t -c "SELECT id FROM users WHERE email = '$OWNER_EMAIL'" | tr -d '[:space:]')
echo "Owner User ID: $OWNER_USER_ID"

# Insert Membership
docker compose exec -T db psql -U postgres -d club_game -c "INSERT INTO memberships (id, game_id, user_id, role, club_id, created_at) VALUES (gen_random_uuid(), '$GAME_ID', '$OWNER_USER_ID', 'club_owner', '$CLUB_ID', now());"

# 4. Attempt PUT as Owner
echo "Attempting PUT as Owner (Should Fail)..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$API_URL/clubs/$CLUB_ID/finance/profile" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $OWNER_EMAIL" \
  -H "X-User-Name: $OWNER_NAME" \
  -d '{"sponsor_base_monthly": 9999, "monthly_cost": 100}')

echo "HTTP Code: $HTTP_CODE"

if [ "$HTTP_CODE" -eq 403 ]; then
  echo "✅ PASS: Owner was forbidden (403)."
else
  echo "❌ FAIL: Expected 403, got $HTTP_CODE"
  exit 1
fi
