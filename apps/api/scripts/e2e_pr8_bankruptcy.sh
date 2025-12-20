#!/bin/bash
# PR8 E2E Test: 債務超過ペナルティとゲーム終了条件
# v1Spec Section 1.1, 14.1

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
AUTH_HEADER="X-User-Email: gm@example.com"

echo "=== PR8 E2E Test: Bankruptcy and Penalties ==="
echo "Base URL: $BASE_URL"

# ===== 1. ゲーム・クラブ・シーズン作成 =====
echo ""
echo "1. Creating game, club, and season..."

GAME_RESP=$(curl -s -X POST "$BASE_URL/api/games" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"name": "PR8 Test Game"}')
echo "Game response: $GAME_RESP"
GAME_ID=$(echo $GAME_RESP | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -z "$GAME_ID" ]; then
  echo "ERROR: Failed to create game"
  exit 1
fi
echo "Game ID: $GAME_ID"

CLUB_RESP=$(curl -s -X POST "$BASE_URL/api/games/$GAME_ID/clubs" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"name": "Test Club", "short_name": "TST"}')
echo "Club response: $CLUB_RESP"
CLUB_ID=$(echo $CLUB_RESP | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -z "$CLUB_ID" ]; then
  echo "ERROR: Failed to create club"
  exit 1
fi
echo "Club ID: $CLUB_ID"

# 2つ目のクラブ作成（試合に必要）
CLUB2_RESP=$(curl -s -X POST "$BASE_URL/api/games/$GAME_ID/clubs" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"name": "Opponent Club", "short_name": "OPP"}')
CLUB2_ID=$(echo $CLUB2_RESP | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Club2 ID: $CLUB2_ID"

# シーズン作成
SEASON_RESP=$(curl -s -X POST "$BASE_URL/api/seasons/games/$GAME_ID" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"year_label": "2025"}')
echo "Season response: $SEASON_RESP"
SEASON_ID=$(echo $SEASON_RESP | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -z "$SEASON_ID" ]; then
  echo "ERROR: Failed to create season"
  exit 1
fi
echo "Season ID: $SEASON_ID"

# ===== 2. 初期状態確認（債務超過ではない） =====
echo ""
echo "2. Checking initial bankruptcy status (should be false)..."

BANKRUPT_STATUS=$(curl -s "$BASE_URL/api/clubs/$CLUB_ID/finance/bankruptcy-status?season_id=$SEASON_ID" \
  -H "$AUTH_HEADER")
echo "Bankruptcy Status: $BANKRUPT_STATUS"

IS_BANKRUPT=$(echo $BANKRUPT_STATUS | grep -o '"is_bankrupt":[^,}]*' | cut -d':' -f2)
if [ "$IS_BANKRUPT" = "false" ]; then
  echo "✓ Club is correctly NOT bankrupt initially"
else
  echo "✗ Club should not be bankrupt initially"
  exit 1
fi

CAN_REINFORCE=$(echo $BANKRUPT_STATUS | grep -o '"can_add_reinforcement":[^,}]*' | cut -d':' -f2)
if [ "$CAN_REINFORCE" = "true" ]; then
  echo "✓ Club can add reinforcement initially"
else
  echo "✗ Club should be able to add reinforcement initially"
  exit 1
fi

# ===== 3. 債務超過クラブ一覧（空のはず） =====
echo ""
echo "3. Checking bankrupt clubs list (should be empty)..."

BANKRUPT_CLUBS=$(curl -s "$BASE_URL/api/seasons/$SEASON_ID/bankrupt-clubs" \
  -H "$AUTH_HEADER")
echo "Bankrupt Clubs: $BANKRUPT_CLUBS"

if [ "$BANKRUPT_CLUBS" = "[]" ]; then
  echo "✓ No bankrupt clubs initially"
else
  echo "✗ Bankrupt clubs list should be empty"
  exit 1
fi

# ===== 4. 勝点剥奪履歴（空のはず） =====
echo ""
echo "4. Checking penalty history (should be empty)..."

PENALTIES=$(curl -s "$BASE_URL/api/clubs/$CLUB_ID/penalties?season_id=$SEASON_ID" \
  -H "$AUTH_HEADER")
echo "Penalties: $PENALTIES"

if [ "$PENALTIES" = "[]" ]; then
  echo "✓ No penalties initially"
else
  echo "✗ Penalties list should be empty"
  exit 1
fi

# ===== 5. 最下位ペナルティ設定テスト =====
echo ""
echo "5. Testing last place penalty settings..."

# 初期値確認
LPP_GET=$(curl -s "$BASE_URL/api/games/$GAME_ID/settings/last-place-penalty" \
  -H "$AUTH_HEADER")
echo "Last Place Penalty (initial): $LPP_GET"

LPP_ENABLED=$(echo $LPP_GET | grep -o '"last_place_penalty_enabled":[^,}]*' | cut -d':' -f2)
if [ "$LPP_ENABLED" = "false" ]; then
  echo "✓ Last place penalty is disabled by default"
else
  echo "✗ Last place penalty should be disabled by default"
  exit 1
fi

# ONに設定
LPP_UPDATE=$(curl -s -X PUT "$BASE_URL/api/games/$GAME_ID/settings/last-place-penalty" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"enabled": true}')
echo "Last Place Penalty (updated): $LPP_UPDATE"

LPP_ENABLED=$(echo $LPP_UPDATE | grep -o '"last_place_penalty_enabled":[^,}]*' | cut -d':' -f2)
if [ "$LPP_ENABLED" = "true" ]; then
  echo "✓ Last place penalty enabled successfully"
else
  echo "✗ Failed to enable last place penalty"
  exit 1
fi

# OFFに戻す
LPP_UPDATE=$(curl -s -X PUT "$BASE_URL/api/games/$GAME_ID/settings/last-place-penalty" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"enabled": false}')
LPP_ENABLED=$(echo $LPP_UPDATE | grep -o '"last_place_penalty_enabled":[^,}]*' | cut -d':' -f2)
if [ "$LPP_ENABLED" = "false" ]; then
  echo "✓ Last place penalty disabled successfully"
else
  echo "✗ Failed to disable last place penalty"
  exit 1
fi

# ===== 6. API正常動作確認完了 =====
echo ""
echo "=== PR8 E2E Test PASSED ==="
echo ""
echo "Verified:"
echo "  - GET /api/clubs/{club_id}/finance/bankruptcy-status"
echo "  - GET /api/seasons/{season_id}/bankrupt-clubs"
echo "  - GET /api/clubs/{club_id}/penalties"
echo "  - GET/PUT /api/games/{game_id}/settings/last-place-penalty"
echo ""
echo "Note: Full bankruptcy flow testing (balance goes negative -> penalty applied)"
echo "      requires more complex setup with turn processing."
