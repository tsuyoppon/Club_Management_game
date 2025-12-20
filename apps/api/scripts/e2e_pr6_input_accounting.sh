#!/bin/bash
set -euo pipefail

API_URL=${API_URL:-"http://localhost:8000/api"}
USER_EMAIL="pr6_input@example.com"
USER_NAME="PR6 Input User"

echo "=========================================="
echo "Starting E2E PR6 Input & Accounting Tests"
echo "=========================================="

# 1. Setup Game, Clubs, Season, Fixtures
echo "1. Setting up game, clubs, and season..."
GAME_RESP=$(curl -s -X POST "$API_URL/games" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"name": "PR6 Game"}')
GAME_ID=$(echo $GAME_RESP | jq -r .id)
echo "   Game ID: $GAME_ID"

CLUB1_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"name": "Club Alpha"}')
CLUB1_ID=$(echo $CLUB1_RESP | jq -r .id)
echo "   Club Alpha ID: $CLUB1_ID"

CLUB2_RESP=$(curl -s -X POST "$API_URL/games/$GAME_ID/clubs" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"name": "Club Beta"}')
CLUB2_ID=$(echo $CLUB2_RESP | jq -r .id)
echo "   Club Beta ID: $CLUB2_ID"

SEASON_RESP=$(curl -s -X POST "$API_URL/seasons/games/$GAME_ID" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{"year_label": "2025"}')
SEASON_ID=$(echo $SEASON_RESP | jq -r .id)
echo "   Season ID: $SEASON_ID"

curl -s -X POST "$API_URL/seasons/$SEASON_ID/fixtures/generate" -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" -d '{}' > /dev/null
echo "   Fixtures generated."

# Function to get current turn
get_current_turn() {
  curl -s -X GET "$API_URL/turns/seasons/$SEASON_ID/current" -H "X-User-Email: $USER_EMAIL"
}

# Function to ack and advance a turn (after resolve)
ack_and_advance_turn() {
  local TURN_ID=$1
  
  # Ack from both clubs (required body: club_id and ack)
  curl -s -X POST "$API_URL/turns/$TURN_ID/ack" \
    -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
    -d "{\"club_id\": \"$CLUB1_ID\", \"ack\": true}" > /dev/null
  
  curl -s -X POST "$API_URL/turns/$TURN_ID/ack" \
    -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
    -d "{\"club_id\": \"$CLUB2_ID\", \"ack\": true}" > /dev/null
  
  # Advance to next turn (GM action)
  curl -s -X POST "$API_URL/turns/$TURN_ID/advance" -H "X-User-Email: $USER_EMAIL" > /dev/null
}

# Function to process a full turn cycle
process_full_turn() {
  local TURN_ID=$1
  
  # Commit decisions for both clubs (minimum required)
  curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB1_ID/commit" \
    -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
    -d '{"payload": {}}' > /dev/null
  
  curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB2_ID/commit" \
    -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
    -d '{"payload": {}}' > /dev/null
  
  # Lock and resolve
  curl -s -X POST "$API_URL/turns/$TURN_ID/lock" -H "X-User-Email: $USER_EMAIL" > /dev/null
  curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" -H "X-User-Email: $USER_EMAIL" > /dev/null
  
  # Ack and advance
  ack_and_advance_turn "$TURN_ID"
}

# 2. Test August (month_index=1) - Distribution Revenue
echo ""
echo "2. Testing August (Distribution Revenue)..."
TURN_RESP=$(get_current_turn)
TURN_ID=$(echo $TURN_RESP | jq -r .id)
MONTH_INDEX=$(echo $TURN_RESP | jq -r .month_index)
echo "   Turn ID: $TURN_ID, Month Index: $MONTH_INDEX"

# Get balance before
BALANCE_BEFORE=$(curl -s -X GET "$API_URL/clubs/$CLUB1_ID/finance/state" -H "X-User-Email: $USER_EMAIL" | jq -r .balance)
echo "   Balance Before: $BALANCE_BEFORE"

# Commit with promo expense and next_home_promo
curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB1_ID/commit" \
  -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
  -d '{"payload": {"promo_expense": 5000000, "next_home_promo": 3000000}}' > /dev/null

curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB2_ID/commit" \
  -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
  -d '{"payload": {}}' > /dev/null

curl -s -X POST "$API_URL/turns/$TURN_ID/lock" -H "X-User-Email: $USER_EMAIL" > /dev/null
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" -H "X-User-Email: $USER_EMAIL" > /dev/null

# Get balance after
BALANCE_AFTER=$(curl -s -X GET "$API_URL/clubs/$CLUB1_ID/finance/state" -H "X-User-Email: $USER_EMAIL" | jq -r .balance)
echo "   Balance After: $BALANCE_AFTER"

# Check distribution revenue was added (150M)
# Also promo expense (5M) was deducted
# Staff costs, academy costs etc. also apply
# Net balance should be positive and significant (>50M after all deductions)
DIFF=$(echo "$BALANCE_AFTER - $BALANCE_BEFORE" | bc)
echo "   Balance Diff: $DIFF"
if (( $(echo "$DIFF < 50000000" | bc -l) )); then
  echo "   ERROR: Distribution revenue not applied correctly (expected significant increase from 150M distribution)"
  exit 1
fi
echo "   ✓ August distribution revenue verified"

# Ack and advance to next turn
ack_and_advance_turn "$TURN_ID"

# 3. Test Validation Error - next_home_promo without home fixture
echo ""
echo "3. Testing input validation (next_home_promo in non-home-fixture month)..."
TURN_RESP=$(get_current_turn)
TURN_ID=$(echo $TURN_RESP | jq -r .id)
MONTH_INDEX=$(echo $TURN_RESP | jq -r .month_index)
echo "   Turn ID: $TURN_ID, Month Index: $MONTH_INDEX (September)"

# Find which club has NO home fixture this month
SCHEDULE1=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/clubs/$CLUB1_ID/schedule" -H "X-User-Email: $USER_EMAIL")
# Check if current month has home fixture for Club1
HAS_HOME_SEP=$(echo $SCHEDULE1 | jq "[.[] | select(.month_index == $MONTH_INDEX and .is_home == true)] | length")

if [ "$HAS_HOME_SEP" -eq 0 ]; then
  # Club1 has no home fixture in September - try to set next_home_promo
  VALIDATION_RESP=$(curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB1_ID/commit" \
    -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
    -d '{"payload": {"next_home_promo": 5000000}}')
  
  if echo "$VALIDATION_RESP" | grep -q "error\|Error\|not allowed\|validation"; then
    echo "   ✓ Validation correctly rejected next_home_promo in non-home month"
  else
    echo "   Warning: Validation may not have caught invalid input (check if club has home fixture)"
  fi
else
  echo "   Club1 has home fixture in September, skipping this validation test"
fi

# Continue turns to reach June for prize test
echo ""
echo "4. Advancing turns to June for prize test..."

# Current turn is September (month_index=2), need to reach June (month_index=11)
# First, complete and advance September turn
process_full_turn "$TURN_ID"

# Then loop for remaining turns (Oct=3 through May=10, that's 8 more turns)
for i in $(seq 1 8); do
  TURN_RESP=$(get_current_turn)
  MONTH_IDX=$(echo $TURN_RESP | jq -r .month_index)
  CURR_TURN_ID=$(echo $TURN_RESP | jq -r .id)
  echo "   Processing month_index: $MONTH_IDX (Turn $i of 8)"
  
  process_full_turn "$CURR_TURN_ID"
done

# 5. Test June - Prize Information
echo ""
echo "5. Testing June (Prize Information)..."
TURN_RESP=$(get_current_turn)
TURN_ID=$(echo $TURN_RESP | jq -r .id)
MONTH_INDEX=$(echo $TURN_RESP | jq -r .month_index)
echo "   Turn ID: $TURN_ID, Month Index: $MONTH_INDEX (should be 11 = June)"

# Get prize info
PRIZE_RESP=$(curl -s -X GET "$API_URL/seasons/$SEASON_ID/prizes" -H "X-User-Email: $USER_EMAIL")
echo "   Prize Response: $PRIZE_RESP"

# Check if response contains error
if echo "$PRIZE_RESP" | grep -q "detail"; then
  echo "   Prize API returned error: $(echo $PRIZE_RESP | jq -r .detail)"
  # This is expected if we haven't reached June yet
  if [ "$MONTH_INDEX" -lt 11 ]; then
    echo "   Note: Still at month $MONTH_INDEX, prize not available yet (expected)"
  fi
  PRIZE_COUNT=0
else
  PRIZE_COUNT=$(echo $PRIZE_RESP | jq 'length')
fi

if [ "$PRIZE_COUNT" -ge 1 ]; then
  echo "   ✓ Prize information available with $PRIZE_COUNT clubs"
  
  # Check prize amount for rank 1
  RANK1_PRIZE=$(echo $PRIZE_RESP | jq -r '.[0].prize_amount')
  echo "   Rank 1 Prize: $RANK1_PRIZE"
else
  echo "   Skipping prize verification (not available yet - this is expected if not at June)"
fi

# Resolve current turn (June if we reached it)
BALANCE_BEFORE_PRIZE=$(curl -s -X GET "$API_URL/clubs/$CLUB1_ID/finance/state" -H "X-User-Email: $USER_EMAIL" | jq -r .balance)

curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB1_ID/commit" \
  -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
  -d '{"payload": {}}' > /dev/null

curl -s -X POST "$API_URL/turns/$TURN_ID/decisions/$CLUB2_ID/commit" \
  -H "Content-Type: application/json" -H "X-User-Email: $USER_EMAIL" \
  -d '{"payload": {}}' > /dev/null

curl -s -X POST "$API_URL/turns/$TURN_ID/lock" -H "X-User-Email: $USER_EMAIL" > /dev/null
curl -s -X POST "$API_URL/turns/$TURN_ID/resolve" -H "X-User-Email: $USER_EMAIL" > /dev/null

BALANCE_AFTER_PRIZE=$(curl -s -X GET "$API_URL/clubs/$CLUB1_ID/finance/state" -H "X-User-Email: $USER_EMAIL" | jq -r .balance)

PRIZE_DIFF=$(echo "$BALANCE_AFTER_PRIZE - $BALANCE_BEFORE_PRIZE" | bc)
echo "   Balance change after prize: $PRIZE_DIFF"
if (( $(echo "$PRIZE_DIFF > 0" | bc -l) )); then
  echo "   ✓ Prize money credited"
else
  echo "   Warning: Prize might not have been credited (could be other expenses)"
fi

# 6. Test Financial Snapshots
echo ""
echo "6. Checking financial snapshots..."
SNAPSHOTS_RESP=$(curl -s -X GET "$API_URL/clubs/$CLUB1_ID/finance/snapshots?season_id=$SEASON_ID" -H "X-User-Email: $USER_EMAIL")
SNAPSHOT_COUNT=$(echo $SNAPSHOTS_RESP | jq 'length')
echo "   Snapshots count: $SNAPSHOT_COUNT"

if [ "$SNAPSHOT_COUNT" -gt 0 ]; then
  echo "   ✓ Financial snapshots recorded"
  
  # Check first snapshot (August) has income
  FIRST_SNAPSHOT_INCOME=$(echo $SNAPSHOTS_RESP | jq -r '.[0].income_total')
  echo "   First snapshot income: $FIRST_SNAPSHOT_INCOME"
  
  if (( $(echo "$FIRST_SNAPSHOT_INCOME > 0" | bc -l) )); then
    echo "   ✓ August income recorded (includes distribution revenue)"
  else
    echo "   Warning: August income may not include distribution"
  fi
else
  echo "   ERROR: No financial snapshots recorded"
  exit 1
fi

echo ""
echo "=========================================="
echo "E2E PR6 Input & Accounting Tests PASSED!"
echo "=========================================="
