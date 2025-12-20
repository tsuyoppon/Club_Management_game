# PR単位の詳細タスクリスト

このドキュメントは、各PRの実装に必要な詳細タスクを記載しています。

---

## PR5: ファンベース（FB）モデルと入場者数モデル ✅ 完了

### フェーズ1: データベース設計・マイグレーション

- [x] `club_fanbase_states`テーブルの設計
  - [x] カラム定義（fb_count, fb_rate, cumulative_promo, cumulative_ht, last_ht_spend, followers_public）
  - [x] インデックス設計
  - [x] 外部キー制約
- [x] `fixtures`テーブルの拡張
  - [x] `weather`カラム追加（VARCHAR(10)）
  - [x] `home_attendance`, `away_attendance`, `total_attendance`カラム追加
- [x] Alembicマイグレーションファイル作成
  - [x] `3a4b5c6d7e8f_pr5_fanbase_attendance.py`
  - [x] 既存クラブへの初期データ投入ロジック
- [x] マイグレーションテスト

### フェーズ2: FBモデル実装

- [x] `services/fanbase.py`作成
  - [x] `ensure_fanbase_state()` - FB状態の初期化
  - [x] `update_cumulative_promo()` - 累積プロモ更新（EWMA, λ=0.10）
  - [x] `update_cumulative_ht()` - 累積ホームタウン活動費更新（EWMA + 急変ペナルティ, φ=0.00002）
  - [x] `calculate_fb_growth_rate()` - 成長率計算（g_0, a_1-a_4係数）
  - [x] `update_fb()` - FB更新（上限制約 f_max=0.25）
  - [x] `calculate_followers()` - 公開ファン指標計算（κ_F=1.0, σ_F=0.15）
- [x] `models.py`に`ClubFanbaseState`モデル追加
- [x] `schemas.py`にFB関連スキーマ追加
  - [x] `FanbaseStateRead`
  - [x] `FanIndicatorRead`
- [x] 統合テスト作成

### フェーズ3: 天候システム実装

- [x] `services/weather.py`作成
  - [x] `determine_weather()` - 天候決定（晴0.55/曇0.30/雨0.15）
  - [x] `get_weather_effect()` - 天候効果取得（g_W: 晴0/曇-0.2/雨-0.6）
- [x] 試合処理時に天候を設定
- [x] 統合テスト作成

### フェーズ4: 入場者数モデル実装

- [x] `services/attendance.py`作成
  - [x] `calculate_home_attendance_rate()` - ホーム来場率計算
    - [x] ロジスティック回帰モデル実装（β_0=-1.986, β_W=1.0, β_1=0.8, β_2=0.4, β_3=0.6, β_4=0.3, β_5=0.5）
    - [x] プロモ効果計算（前月ホーム向けプロモ）
    - [x] イベント効果（開幕/最終戦: g_event=0.4）
    - [x] Cap制約適用
  - [x] `calculate_away_attendance()` - アウェイ来場計算
    - [x] 基準遠征率（r_away_0=0.018）
    - [x] 天候影響（κ_W=0.20）
    - [x] 上限制約（q_max=0.20）
  - [x] `apply_capacity_constraint()` - Cap超過時の比率縮小
  - [x] `calculate_total_attendance()` - 合計入場者数計算
- [x] `services/ticket.py`の更新
  - [x] 簡易版から詳細モデルへ移行
  - [x] 入場者数モデルを使用
- [x] 試合処理時に入場者数を計算・保存
- [x] 統合テスト作成

### フェーズ5: API実装

- [x] `routers/fanbase.py`作成
  - [x] `GET /api/clubs/{club_id}/fanbase` - FB状態取得
  - [x] `GET /api/clubs/{club_id}/fan_indicator` - 公開ファン指標取得
- [x] `routers/seasons.py`の更新
  - [x] `GET /api/seasons/{season_id}/fixtures/{fixture_id}` - 試合詳細（天候・入場者数含む）
- [x] APIテスト作成

### フェーズ6: 統合・テスト

- [x] `apply_finance_for_turn`にFB更新ロジック統合
- [x] `process_matches_for_turn`に入場者数計算統合
- [x] 統合テスト作成
- [x] E2Eテスト作成（e2e_pr5_fanbase.sh）
- [x] 回帰テスト合格

### フェーズ7: ドキュメント

- [x] IMPLEMENTATION_ROADMAP.md更新

---

## PR6: 月次入力項目と会計項目の拡張 ✅ 完了

### フェーズ1: 入力スキーマ設計

- [x] `TurnDecision.payload_json`の構造定義
  - [x] `DecisionPayload`スキーマ作成
    - [x] `sales_expense: Optional[Decimal]`
    - [x] `promo_expense: Optional[Decimal]`
    - [x] `hometown_expense: Optional[Decimal]`
    - [x] `next_home_promo: Optional[Decimal]`
    - [x] `additional_reinforcement: Optional[Decimal]` (12月のみ)
- [x] バリデーションロジック設計
  - [x] 翌月ホーム向けプロモ費の条件チェック
  - [x] 追加強化費の条件チェック（12月、債務超過チェック）

### フェーズ2: 入力API拡張

- [x] `routers/turns.py`の更新
  - [x] `POST /api/turns/{turn_id}/decisions/{club_id}/commit` - スキーマ拡張
  - [x] バリデーション追加
- [x] `GET /api/turns/{turn_id}/decisions/{club_id}` - 入力内容取得API
- [x] 入力テスト作成

### フェーズ3: 会計項目実装

- [x] `services/distribution.py`作成
  - [x] `process_distribution_revenue()` - 配分金処理（8月）
- [x] `services/merchandise.py`作成
  - [x] `process_merchandise_revenue()` - 物販収入計算
  - [x] `process_merchandise_cost()` - 物販費用計算
- [x] `services/match_operation.py`作成
  - [x] `process_match_operation_cost()` - 試合運営費計算
- [x] `services/prize.py`作成
  - [x] `calculate_prize_amount()` - 賞金額計算（順位ベース）
  - [x] `process_prize_revenue()` - 賞金入金（6月）
- [x] 退職金計算ロジック実装

### フェーズ4: 財務処理統合

- [x] `services/finance.py`の`apply_finance_for_turn`更新
  - [x] 月次入力項目の費用計上
  - [x] 新規会計項目の処理追加
  - [x] 処理順序の最適化
- [x] 統合テスト作成

### フェーズ5: データベース変更

- [x] Alembicマイグレーションファイル作成
  - [x] `4a2b3c4d5e6f_pr6_input_accounting.py`
- [x] マイグレーションテスト

### フェーズ6: API実装

- [x] 会計API実装
- [x] APIテスト作成

### フェーズ7: テスト・ドキュメント

- [x] 統合テスト
- [x] E2Eテスト作成（e2e_pr6_input_accounting.sh）
- [x] 回帰テスト合格
- [x] IMPLEMENTATION_ROADMAP.md更新

---

## PR7: スポンサー内定進捗と営業努力モデルの完全実装 ✅ 完了

### フェーズ1: データベース設計

- [x] `club_sales_allocations`テーブル設計
  - [x] カラム定義（club_id, season_id, quarter, rho_new）
  - [x] インデックス・制約
- [x] `club_sponsor_states`テーブル拡張
  - [x] `cumulative_effort_ret`, `cumulative_effort_new`追加
  - [x] `pipeline_confirmed_exist`, `pipeline_confirmed_new`追加
  - [x] `next_exist_count`, `next_new_count`追加
- [x] Alembicマイグレーションファイル作成
  - [x] `5b6c7d8e9f0a_pr7_sponsor_sales_effort.py`

### フェーズ2: 営業努力モデル実装

- [x] `services/sales_effort.py`作成
  - [x] `ensure_sales_allocation()` - 営業リソース配分の初期化
  - [x] `set_sales_allocation()` - 四半期配分更新
  - [x] `calculate_monthly_effort()` - 月次有効営業努力計算
    - [x] `E_ret = w_s^ret * S_ret + w_m^ret * M/10^6`
    - [x] `E_new = w_s^new * S_new + w_m^new * M/10^6`
  - [x] `update_cumulative_effort()` - 累積営業努力更新（EWMA）
    - [x] `C_ret(t) = (1-λ_ret)*C_ret(t-1) + λ_ret*E_ret(t)`
    - [x] `C_new(t) = (1-λ_new)*C_new(t-1) + λ_new*E_new(t)`
- [x] `models.py`に`ClubSalesAllocation`モデル追加
- [x] 統合テスト作成

### フェーズ3: スポンサー内定進捗実装

- [x] `services/sponsor.py`の更新
  - [x] `process_pipeline_progress()` - 内定進捗処理（4-7月）
    - [x] 4-6月: 確率的抽選（既存/新規で異なる確率 q^exist, q^new）
    - [x] 7月: 強制確定 + determine_next_sponsors呼び出し
  - [x] `get_pipeline_status()` - 内定進捗状態取得
  - [x] `get_next_sponsor_info()` - 次年度スポンサー情報取得
- [x] 統合テスト作成

### フェーズ4: API実装

- [x] `routers/sponsors.py`作成
  - [x] `PUT /api/sponsors/{club_id}/allocation` - 営業リソース配分設定
  - [x] `GET /api/sponsors/{club_id}/allocation` - 現在の配分取得
  - [x] `GET /api/sponsors/{club_id}/allocations` - 全四半期配分取得
  - [x] `GET /api/sponsors/{club_id}/pipeline` - 内定進捗取得
  - [x] `GET /api/sponsors/{club_id}/next-sponsor` - 次年度スポンサー情報取得
  - [x] `GET /api/sponsors/{club_id}/effort` - 累積営業努力取得
- [x] APIテスト作成

### フェーズ5: 統合

- [x] `finance.py`に営業努力更新統合（process_sales_effort_for_turn）
- [x] `finance.py`にパイプライン進捗統合（process_pipeline_progress）
- [x] 統合テスト作成

### フェーズ6: テスト・ドキュメント

- [x] E2Eテスト作成（e2e_pr7_sponsor.sh）
- [x] 全E2Eテスト回帰テスト合格
- [x] IMPLEMENTATION_ROADMAP.md更新

---

## PR8: 債務超過ペナルティとゲーム終了条件

### フェーズ1: データベース設計

- [ ] `club_financial_states`テーブル拡張
  - [ ] `is_bankrupt`フラグ追加
  - [ ] `bankrupt_since_turn_id`追加
- [ ] `club_point_penalties`テーブル設計（監査用）
  - [ ] カラム定義（club_id, season_id, turn_id, points_deducted, reason）
- [ ] `games`テーブル拡張
  - [ ] `last_place_penalty_enabled`フラグ追加
- [ ] Alembicマイグレーションファイル作成
  - [ ] `0007_pr8_bankruptcy_penalty.py`

### フェーズ2: 債務超過判定実装

- [ ] `services/bankruptcy.py`作成
  - [ ] `check_bankruptcy()` - 債務超過チェック
  - [ ] `mark_bankrupt()` - 債務超過状態設定
  - [ ] `is_bankrupt()` - 債務超過状態確認
- [ ] `apply_finance_for_turn`に債務超過チェック統合
- [ ] ユニットテスト作成

### フェーズ3: 勝点剥奪実装

- [ ] `services/penalty.py`作成
  - [ ] `deduct_points()` - 勝点剥奪（-6点）
  - [ ] `apply_point_penalty()` - 順位表への勝点剥奪適用
- [ ] `services/standings.py`の更新
  - [ ] 債務超過クラブの勝点を減算
  - [ ] マイナス勝点は0にクリップ
- [ ] ユニットテスト作成

### フェーズ4: 追加強化費禁止実装

- [ ] `routers/turns.py`の更新
  - [ ] `POST /api/turns/{turn_id}/decisions/{club_id}/commit` - 債務超過チェック追加
  - [ ] 12月の追加強化費入力をブロック
- [ ] バリデーションテスト作成

### フェーズ5: 最下位ペナルティ実装（オプション）

- [ ] `services/penalty.py`の更新
  - [ ] `apply_last_place_penalty()` - 最下位ペナルティ適用
  - [ ] 次年度配分金ゼロ設定
- [ ] ゲーム設定でのON/OFF機能
- [ ] ユニットテスト作成

### フェーズ6: ゲーム終了条件実装

- [ ] `services/bankruptcy.py`の更新
  - [ ] `check_final_bankruptcy()` - 年度終了時の脱落判定（7月）
  - [ ] `mark_dropped()` - 脱落フラグ設定
- [ ] 脱落クラブの処理
  - [ ] 試合参加継続
  - [ ] 勝点剥奪継続
- [ ] ユニットテスト作成

### フェーズ7: API実装

- [ ] `routers/finance.py`の更新
  - [ ] `GET /api/clubs/{club_id}/finance/state` - 債務超過状態を含む
- [ ] `routers/seasons.py`の更新
  - [ ] `GET /api/seasons/{season_id}/bankrupt_clubs` - 債務超過クラブ一覧
  - [ ] `POST /api/seasons/{season_id}/check_bankruptcy` - 債務超過チェック（7月）
- [ ] APIテスト作成

### フェーズ8: テスト・ドキュメント

- [ ] 全機能のユニットテスト
- [ ] 統合テスト
- [ ] E2Eテスト
- [ ] API仕様書更新

---

## PR9: 情報公開イベントと最終結果表示

### フェーズ1: データベース設計

- [ ] `season_public_disclosures`テーブル設計
  - [ ] カラム定義（season_id, disclosure_type, disclosure_month, disclosed_data）
- [ ] `game_final_results`テーブル設計
  - [ ] カラム定義（game_id, club_id, final_sales_rank, final_sales_amount, etc.）
- [ ] Alembicマイグレーションファイル作成
  - [ ] `0008_pr9_public_disclosure_results.py`

### フェーズ2: 情報公開イベント実装

- [ ] `services/public_disclosure.py`作成
  - [ ] `publish_financial_summary()` - 財務サマリー公開（12月）
  - [ ] `publish_team_power()` - チーム力指標公開（12月/7月）
  - [ ] `get_disclosure_history()` - 公開履歴取得
- [ ] `services/team_power.py`作成
  - [ ] `calculate_team_power()` - チーム力計算
  - [ ] `calculate_team_power_with_uncertainty()` - 不確実性付きチーム力（7月）
- [ ] ユニットテスト作成

### フェーズ3: 5月順位表の追加表示

- [ ] `services/standings.py`の更新
  - [ ] `calculate_with_championship()` - 優勝・準優勝表示
  - [ ] `calculate_with_attendance()` - 平均入場者数追加
- [ ] `routers/seasons.py`の更新
  - [ ] `GET /api/seasons/{season_id}/standings` - 5月時は追加情報を含む
- [ ] ユニットテスト作成

### フェーズ4: 最終結果表示実装

- [ ] `services/final_results.py`作成
  - [ ] `calculate_final_sales()` - 最終売上規模計算
  - [ ] `calculate_final_equity()` - 最終純資産計算
  - [ ] `calculate_championship_stats()` - 優勝回数・準優勝回数・平均順位
  - [ ] `calculate_average_attendance()` - 全シーズン平均入場者数
  - [ ] `generate_final_results()` - 最終結果生成
- [ ] `models.py`に`GameFinalResult`モデル追加
- [ ] ユニットテスト作成

### フェーズ5: API実装

- [ ] `routers/seasons.py`の更新
  - [ ] `GET /api/seasons/{season_id}/public/financial_summary` - 財務サマリー公開
  - [ ] `GET /api/seasons/{season_id}/public/team_power` - チーム力指標公開
- [ ] `routers/games.py`の更新
  - [ ] `GET /api/games/{game_id}/final_results` - 最終結果表示
- [ ] APIテスト作成

### フェーズ6: 統合

- [ ] 12月ターン終了時の公開処理統合
- [ ] 7月ターン終了時の公開処理統合
- [ ] ゲーム終了時の最終結果生成統合
- [ ] 統合テスト作成

### フェーズ7: テスト・ドキュメント

- [ ] 全機能のユニットテスト
- [ ] 統合テスト
- [ ] E2Eテスト
- [ ] API仕様書更新

---

## PR10: 参照コマンド（CLI）インターフェース

### フェーズ1: CLI基盤構築

- [ ] `apps/cli/`ディレクトリ作成
- [ ] CLIフレームワーク選定・導入
  - [ ] `click`または`argparse`の選定
- [ ] プロジェクト構造設計
  - [ ] `cli/main.py` - エントリーポイント
  - [ ] `cli/config.py` - 設定管理
  - [ ] `cli/auth.py` - 認証・セッション管理
  - [ ] `cli/api_client.py` - APIクライアント

### フェーズ2: 認証・セッション管理

- [ ] 設定ファイル管理（`.club-game/config`）
  - [ ] APIエンドポイント設定
  - [ ] ユーザー情報保存（オプション）
- [ ] 認証機能実装
  - [ ] `X-User-Email`ヘッダの設定
  - [ ] セッション管理

### フェーズ3: コマンド実装（基本）

- [ ] `cli/commands/show_match.py`
  - [ ] `show match` - 試合結果一覧
  - [ ] `--month YYYY-MM` オプション
- [ ] `cli/commands/show_table.py`
  - [ ] `show table` - 順位表
- [ ] `cli/commands/show_team_power.py`
  - [ ] `show team_power` - チーム力指標
- [ ] `cli/commands/show_staff.py`
  - [ ] `show staff` - 部署別人数
  - [ ] `show staff_history` - 人員変動履歴
    - [ ] `--from YYYY-MM`, `--to YYYY-MM` オプション

### フェーズ4: コマンド実装（入力関連）

- [ ] `cli/commands/show_input.py`
  - [ ] `show current_input` - 当ターン入力内容
  - [ ] `show history` - 過去の入力一覧
    - [ ] `--from YYYY-MM`, `--to YYYY-MM` オプション

### フェーズ5: コマンド実装（ファン・スポンサー）

- [ ] `cli/commands/show_fan.py`
  - [ ] `show fan_indicator` - ファン指標
    - [ ] `--club <name>` オプション
    - [ ] `--from YYYY-MM`, `--to YYYY-MM` オプション
- [ ] `cli/commands/show_sponsor.py`
  - [ ] `show sponsor_status` - スポンサー状態
    - [ ] `--pipeline` オプション（4-6月）
    - [ ] `--next` オプション（7月）

### フェーズ6: 入力コマンド（オプション）

- [ ] `cli/commands/input.py`
  - [ ] `input` - 月次入力
    - [ ] `--sales-expense`, `--promo-expense`, `--hometown-expense`
    - [ ] `--next-home-promo`
- [ ] `cli/commands/commit.py`
  - [ ] `commit` - 入力確定
- [ ] `cli/commands/view.py`
  - [ ] `view` - 入力確認

### フェーズ7: ヘルプ・エラーハンドリング

- [ ] `cli/commands/help.py`
  - [ ] `help` - 全コマンド一覧
  - [ ] `help <command>` - コマンド詳細ヘルプ
- [ ] エラーハンドリング実装
  - [ ] APIエラー処理
  - [ ] バリデーションエラー処理
  - [ ] ネットワークエラー処理

### フェーズ8: テスト

- [ ] 各コマンドのユニットテスト
- [ ] 統合テスト
- [ ] エラーハンドリングテスト

### フェーズ9: ドキュメント・パッケージング

- [ ] CLI使用ガイド作成
- [ ] インストール手順書
- [ ] パッケージング（pip install可能にする）
- [ ] README更新

---

## 共通タスク（全PR）

### コード品質

- [ ] リントチェック（flake8, pylint等）
- [ ] 型チェック（mypy）
- [ ] コードレビュー

### テスト

- [ ] ユニットテスト（カバレッジ80%以上）
- [ ] 統合テスト
- [ ] E2Eテスト
- [ ] パフォーマンステスト（必要に応じて）

### ドキュメント

- [ ] API仕様書更新
- [ ] 開発者ガイド更新
- [ ] マイグレーション手順書
- [ ] 変更履歴（CHANGELOG）更新

### デプロイ

- [ ] マイグレーション実行計画
- [ ] ロールバック計画
- [ ] 本番環境デプロイ手順

---

**最終更新日**: 2024年12月

