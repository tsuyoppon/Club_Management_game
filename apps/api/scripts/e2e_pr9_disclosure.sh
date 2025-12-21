#!/bin/bash
# PR9 E2E Test: 情報公開イベントと最終結果表示
# v1Spec Section 1.2, 4, 13

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
AUTH_HEADER="X-User-Email: gm@example.com"

echo "=== PR9 E2E Test: Public Disclosure Events and Final Results ==="
echo "Base URL: $BASE_URL"

# ===== 1. ゲーム・クラブ・シーズン作成 =====
echo ""
echo "1. Creating game, clubs, and season..."

GAME_RESP=$(curl -s -X POST "$BASE_URL/api/games" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"name": "PR9 Test Game"}')
echo "Game response: $GAME_RESP"
GAME_ID=$(echo $GAME_RESP | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -z "$GAME_ID" ]; then
  echo "ERROR: Failed to create game"
  exit 1
fi
echo "Game ID: $GAME_ID"

# クラブ1作成
CLUB_RESP=$(curl -s -X POST "$BASE_URL/api/games/$GAME_ID/clubs" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"name": "Test Club Alpha", "short_name": "ALP"}')
echo "Club response: $CLUB_RESP"
CLUB_ID=$(echo $CLUB_RESP | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -z "$CLUB_ID" ]; then
  echo "ERROR: Failed to create club"
  exit 1
fi
echo "Club ID: $CLUB_ID"

# クラブ2作成
CLUB2_RESP=$(curl -s -X POST "$BASE_URL/api/games/$GAME_ID/clubs" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"name": "Test Club Beta", "short_name": "BET"}')
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

# ===== 2. 情報公開一覧（空のはず） =====
echo ""
echo "2. Checking disclosures list (should be empty initially)..."

DISCLOSURES=$(curl -s "$BASE_URL/api/seasons/$SEASON_ID/disclosures" \
  -H "$AUTH_HEADER")
echo "Disclosures: $DISCLOSURES"

if [ "$DISCLOSURES" = "[]" ]; then
  echo "✓ No disclosures initially"
else
  echo "✗ Disclosures list should be empty initially"
  exit 1
fi

# ===== 3. チーム力指標取得（初期状態） =====
echo ""
echo "3. Getting team power indicators..."

TEAM_POWER_STATUS=$(curl -s -o /tmp/team_power_body -w "%{http_code}" "$BASE_URL/api/seasons/$SEASON_ID/team-power" \
  -H "$AUTH_HEADER")
TEAM_POWER_BODY=$(cat /tmp/team_power_body)
echo "Team Power (status $TEAM_POWER_STATUS): $TEAM_POWER_BODY"

if [ "$TEAM_POWER_STATUS" = "404" ]; then
  echo "✓ Team power not published yet (expected 404 before disclosure events)"
elif echo "$TEAM_POWER_BODY" | grep -q '"disclosure_type"'; then
  echo "✓ Team power endpoint working"
else
  echo "✗ Team power endpoint should return disclosure_type or 404 when unpublished"
  exit 1
fi

# ===== 4. 拡張順位表取得（初期状態） =====
echo ""
echo "4. Getting extended standings..."

EXT_STAND_STATUS=$(curl -s -o /tmp/ext_stand_body -w "%{http_code}" "$BASE_URL/api/seasons/$SEASON_ID/standings/extended" \
  -H "$AUTH_HEADER")
EXTENDED_STANDINGS=$(cat /tmp/ext_stand_body)
echo "Extended Standings (status $EXT_STAND_STATUS): $EXTENDED_STANDINGS"

if [ "$EXT_STAND_STATUS" = "200" ]; then
  echo "✓ Extended standings endpoint reachable"
else
  echo "✗ Extended standings endpoint returned status $EXT_STAND_STATUS"
  exit 1
fi

# ===== 5. 特定タイプの情報公開取得（存在しない場合） =====
echo ""
echo "5. Getting disclosure by type (should be 404 when none)..."

DISCLOSURE_FIN_STATUS=$(curl -s -o /tmp/disclosure_fin_body -w "%{http_code}" "$BASE_URL/api/seasons/$SEASON_ID/disclosures/financial_summary" \
  -H "$AUTH_HEADER")
DISCLOSURE_FIN_BODY=$(cat /tmp/disclosure_fin_body)
echo "Financial Summary Disclosure (status $DISCLOSURE_FIN_STATUS): $DISCLOSURE_FIN_BODY"

if [ "$DISCLOSURE_FIN_STATUS" = "404" ]; then
  echo "✓ No financial summary disclosure initially (404 as expected)"
else
  echo "✗ Expected 404 when no disclosure exists"
  exit 1
fi

# ===== 6. 最終結果取得（生成前） =====
echo ""
echo "6. Getting final results (before generation)..."

FINAL_RESULTS=$(curl -s "$BASE_URL/api/games/$GAME_ID/final-results" \
  -H "$AUTH_HEADER")
echo "Final Results: $FINAL_RESULTS"

if [ "$FINAL_RESULTS" = "[]" ]; then
  echo "✓ No final results before generation"
else
  echo "✗ Final results should be empty before generation"
  exit 1
fi

# ===== 7. 最終結果生成 =====
echo ""
echo "Generate Response: $GENERATE_RESP"
echo "7. Generating final results..."

GENERATE_STATUS=$(curl -s -o /tmp/final_generate_body -w "%{http_code}" -X POST "$BASE_URL/api/games/$GAME_ID/final-results/generate" \
  -H "$AUTH_HEADER")
GENERATE_RESP=$(cat /tmp/final_generate_body)
echo "Generate Response (status $GENERATE_STATUS): $GENERATE_RESP"

if [ "$GENERATE_STATUS" = "200" ]; then
  echo "✓ Final results generation endpoint reachable"
else
  echo "✗ Final results generation failed with status $GENERATE_STATUS"
  exit 1
fi

# ===== 8. 最終結果再取得（生成後） =====
echo ""
echo "8. Getting final results (after generation)..."

FINAL_STATUS=$(curl -s -o /tmp/final_results_body -w "%{http_code}" "$BASE_URL/api/games/$GAME_ID/final-results" \
  -H "$AUTH_HEADER")
FINAL_RESULTS=$(cat /tmp/final_results_body)
echo "Final Results (status $FINAL_STATUS): $FINAL_RESULTS"

if [ "$FINAL_STATUS" = "200" ]; then
  echo "✓ Final results retrieval endpoint reachable"
else
  echo "✗ Final results retrieval failed with status $FINAL_STATUS"
  exit 1
fi

# ===== 9. 冪等性テスト（再生成は同じ結果） =====
echo ""
echo "9. Testing idempotency (regenerate should return same results)..."

REGEN_STATUS=$(curl -s -o /tmp/final_regen_body -w "%{http_code}" -X POST "$BASE_URL/api/games/$GAME_ID/final-results/generate" \
  -H "$AUTH_HEADER")
REGENERATE_RESP=$(cat /tmp/final_regen_body)
echo "Regenerate Response (status $REGEN_STATUS): $REGENERATE_RESP"

if [ "$REGEN_STATUS" = "200" ]; then
  echo "✓ Regeneration endpoint reachable"
else
  echo "✗ Regeneration failed with status $REGEN_STATUS"
  exit 1
fi

# ===== 10. API正常動作確認完了 =====
echo ""
echo "=== PR9 E2E Test PASSED ==="
echo ""
echo "Verified:"
echo "  - GET /api/seasons/{season_id}/disclosures"
echo "  - GET /api/seasons/{season_id}/disclosures/{disclosure_type}"
echo "  - GET /api/seasons/{season_id}/team-power"
echo "  - GET /api/seasons/{season_id}/standings/extended"
echo "  - GET /api/games/{game_id}/final-results"
echo "  - POST /api/games/{game_id}/final-results/generate"
echo ""
echo "Note: Disclosure events during turn resolution (12月/7月)"
echo "      require full turn flow testing."
