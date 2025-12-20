#!/bin/bash
# PR7 E2E Test: Sponsor Sales Effort Model
# v1Spec Section 10 準拠

set -e

BASE_URL="http://localhost:8000/api"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_EMAIL="pr7test@example.com"
AUTH_HEADER="-H X-User-Email:$USER_EMAIL"

echo "=========================================="
echo "PR7 E2E Test: Sponsor Sales Effort Model"
echo "=========================================="

# Helper functions
check_response() {
    local response="$1"
    local expected="$2"
    local message="$3"
    
    if echo "$response" | grep -q "$expected"; then
        echo "✅ $message"
        return 0
    else
        echo "❌ $message"
        echo "Response: $response"
        return 1
    fi
}

# Step 1: Create Game and Club
echo ""
echo "Step 1: Create Game and Club"
echo "----------------------------"

GAME_RESP=$(curl -s -X POST "$BASE_URL/games" \
  $AUTH_HEADER \
  -H "Content-Type: application/json" \
  -d '{"name": "PR7 Test Game"}')

GAME_ID=$(echo "$GAME_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created Game: $GAME_ID"

CLUB_RESP=$(curl -s -X POST "$BASE_URL/games/$GAME_ID/clubs" \
  $AUTH_HEADER \
  -H "Content-Type: application/json" \
  -d '{"name": "Test FC", "short_name": "TFC"}')

CLUB_ID=$(echo "$CLUB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created Club: $CLUB_ID"

# Step 2: Create Season and Generate Fixtures
echo ""
echo "Step 2: Create Season and Generate Fixtures"
echo "--------------------------------------------"

SEASON_RESP=$(curl -s -X POST "$BASE_URL/seasons/games/$GAME_ID" \
  $AUTH_HEADER \
  -H "Content-Type: application/json" \
  -d '{"year_label": "2024-25"}')

SEASON_ID=$(echo "$SEASON_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created Season: $SEASON_ID"

# Generate fixtures
curl -s -X POST "$BASE_URL/seasons/$SEASON_ID/fixtures/generate" \
  $AUTH_HEADER \
  -H "Content-Type: application/json" \
  -d '{"force": true}' > /dev/null

echo "Generated fixtures"

# Step 3: Test Sales Allocation API
echo ""
echo "Step 3: Test Sales Allocation API"
echo "----------------------------------"

# Get default allocation for Q1
ALLOC_RESP=$(curl -s -X GET "$BASE_URL/sponsors/seasons/$SEASON_ID/clubs/$CLUB_ID/allocation?quarter=1" $AUTH_HEADER)
check_response "$ALLOC_RESP" '"rho_new"' "Get Q1 allocation"
check_response "$ALLOC_RESP" '0.5' "Default rho_new is 0.5"

# Set allocation to 0.7 (70% new, 30% existing)
SET_RESP=$(curl -s -X PUT "$BASE_URL/sponsors/seasons/$SEASON_ID/clubs/$CLUB_ID/allocation?quarter=1" \
  $AUTH_HEADER \
  -H "Content-Type: application/json" \
  -d '{"rho_new": 0.7}')
check_response "$SET_RESP" '0.7' "Set Q1 rho_new to 0.7"

# Get all allocations
ALL_ALLOC=$(curl -s -X GET "$BASE_URL/sponsors/seasons/$SEASON_ID/clubs/$CLUB_ID/allocations" $AUTH_HEADER)
check_response "$ALL_ALLOC" '"quarter":1' "Get all allocations includes Q1"
check_response "$ALL_ALLOC" '"quarter":4' "Get all allocations includes Q4"

# Step 4: Test Pipeline Status API
echo ""
echo "Step 4: Test Pipeline Status API"
echo "---------------------------------"

PIPELINE_RESP=$(curl -s -X GET "$BASE_URL/sponsors/seasons/$SEASON_ID/clubs/$CLUB_ID/pipeline" $AUTH_HEADER)
check_response "$PIPELINE_RESP" '"current_sponsors"' "Pipeline status has current_sponsors"
check_response "$PIPELINE_RESP" '"cumulative_effort_ret"' "Pipeline status has cumulative_effort_ret"
check_response "$PIPELINE_RESP" '"cumulative_effort_new"' "Pipeline status has cumulative_effort_new"

# Step 5: Test Cumulative Effort API
echo ""
echo "Step 5: Test Cumulative Effort API"
echo "-----------------------------------"

EFFORT_RESP=$(curl -s -X GET "$BASE_URL/sponsors/seasons/$SEASON_ID/clubs/$CLUB_ID/effort" $AUTH_HEADER)
check_response "$EFFORT_RESP" '"cumulative_effort_ret"' "Effort has cumulative_effort_ret"
check_response "$EFFORT_RESP" '"cumulative_effort_new"' "Effort has cumulative_effort_new"

# Step 6: Process a turn and verify effort updates
echo ""
echo "Step 6: Process Turn and Verify Effort Updates"
echo "-----------------------------------------------"

# Get first turn
TURNS_RESP=$(curl -s -X GET "$BASE_URL/turns/seasons/$SEASON_ID/current" $AUTH_HEADER)
TURN_ID=$(echo "$TURNS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "First Turn: $TURN_ID"

# Submit decision with sales_expense
DECISION_RESP=$(curl -s -X POST "$BASE_URL/turns/$TURN_ID/decisions/$CLUB_ID/commit" \
  $AUTH_HEADER \
  -H "Content-Type: application/json" \
  -d '{"payload": {"sales_expense": 5000000, "promo_expense": 1000000, "hometown_expense": 500000}}')
check_response "$DECISION_RESP" '"state"' "Decision committed with sales_expense"

# Resolve turn
curl -s -X POST "$BASE_URL/turns/$TURN_ID/resolve" $AUTH_HEADER > /dev/null
echo "Turn resolved"

# Ack turn
curl -s -X POST "$BASE_URL/turns/$TURN_ID/ack" \
  $AUTH_HEADER \
  -H "Content-Type: application/json" \
  -d "{\"club_id\": \"$CLUB_ID\", \"ack\": true}" > /dev/null

# Advance turn
curl -s -X POST "$BASE_URL/turns/$TURN_ID/advance" $AUTH_HEADER > /dev/null
echo "Processed first turn"

# Check cumulative effort updated
EFFORT_AFTER=$(curl -s -X GET "$BASE_URL/sponsors/seasons/$SEASON_ID/clubs/$CLUB_ID/effort" $AUTH_HEADER)
C_RET=$(echo "$EFFORT_AFTER" | python3 -c "import sys,json; print(json.load(sys.stdin)['cumulative_effort_ret'])")
C_NEW=$(echo "$EFFORT_AFTER" | python3 -c "import sys,json; print(json.load(sys.stdin)['cumulative_effort_new'])")

if (( $(echo "$C_RET > 0 || $C_NEW > 0" | bc -l) )); then
    echo "✅ Cumulative effort updated after turn (C_ret=$C_RET, C_new=$C_NEW)"
else
    echo "❌ Cumulative effort not updated (C_ret=$C_RET, C_new=$C_NEW)"
    exit 1
fi

# Step 7: Test Next Sponsor Info API
echo ""
echo "Step 7: Test Next Sponsor Info API"
echo "-----------------------------------"

NEXT_SPONSOR=$(curl -s -X GET "$BASE_URL/sponsors/seasons/$SEASON_ID/clubs/$CLUB_ID/next-sponsor" $AUTH_HEADER)
check_response "$NEXT_SPONSOR" '"next_sponsors_total"' "Next sponsor info has total"
check_response "$NEXT_SPONSOR" '"expected_revenue"' "Next sponsor info has expected_revenue"
check_response "$NEXT_SPONSOR" '"is_finalized"' "Next sponsor info has is_finalized"

echo ""
echo "=========================================="
echo "PR7 E2E Test PASSED"
echo "=========================================="
exit 0
