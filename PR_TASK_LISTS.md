# PR単位の詳細タスクリスト

このドキュメントは、各PRの実装に必要な詳細タスクを記載しています。

---

## PR5: ファンベース（FB）モデルと入場者数モデル

### フェーズ1: データベース設計・マイグレーション

- [ ] `club_fanbase_states`テーブルの設計
  - [ ] カラム定義（fb_count, fb_rate, cumulative_promo, cumulative_ht, last_ht_spend, followers_public）
  - [ ] インデックス設計
  - [ ] 外部キー制約
- [ ] `fixtures`テーブルの拡張
  - [ ] `weather`カラム追加（VARCHAR(10)）
  - [ ] `home_attendance`, `away_attendance`, `total_attendance`カラム追加
- [ ] Alembicマイグレーションファイル作成
  - [ ] `0004_pr5_fanbase_attendance.py`
  - [ ] 既存クラブへの初期データ投入ロジック
- [ ] マイグレーションテスト

### フェーズ2: FBモデル実装

- [ ] `services/fanbase.py`作成
  - [ ] `ensure_fanbase_state()` - FB状態の初期化
  - [ ] `update_cumulative_promo()` - 累積プロモ更新（EWMA, λ=0.10）
  - [ ] `update_cumulative_ht()` - 累積ホームタウン活動費更新（EWMA + 急変ペナルティ, φ=0.00002）
  - [ ] `calculate_fb_growth_rate()` - 成長率計算（g_0, a_1-a_4係数）
  - [ ] `update_fb()` - FB更新（上限制約 f_max=0.25）
  - [ ] `calculate_followers()` - 公開ファン指標計算（κ_F=1.0, σ_F=0.15）
- [ ] `models.py`に`ClubFanbaseState`モデル追加
- [ ] `schemas.py`にFB関連スキーマ追加
  - [ ] `FanbaseStateRead`
  - [ ] `FanIndicatorRead`
- [ ] ユニットテスト作成

### フェーズ3: 天候システム実装

- [ ] `services/weather.py`作成
  - [ ] `determine_weather()` - 天候決定（晴0.55/曇0.30/雨0.15）
  - [ ] `get_weather_effect()` - 天候効果取得（g_W: 晴0/曇-0.2/雨-0.6）
- [ ] 試合処理時に天候を設定
- [ ] ユニットテスト作成

### フェーズ4: 入場者数モデル実装

- [ ] `services/attendance.py`作成
  - [ ] `calculate_home_attendance_rate()` - ホーム来場率計算
    - [ ] ロジスティック回帰モデル実装（β_0=-1.986, β_W=1.0, β_1=0.8, β_2=0.4, β_3=0.6, β_4=0.3, β_5=0.5）
    - [ ] プロモ効果計算（前月ホーム向けプロモ）
    - [ ] イベント効果（開幕/最終戦: g_event=0.4）
    - [ ] Cap制約適用
  - [ ] `calculate_away_attendance()` - アウェイ来場計算
    - [ ] 基準遠征率（r_away_0=0.018）
    - [ ] 天候影響（κ_W=0.20）
    - [ ] 上限制約（q_max=0.20）
  - [ ] `apply_capacity_constraint()` - Cap超過時の比率縮小
  - [ ] `calculate_total_attendance()` - 合計入場者数計算
- [ ] `services/ticket.py`の更新
  - [ ] 簡易版から詳細モデルへ移行
  - [ ] 入場者数モデルを使用
- [ ] 試合処理時に入場者数を計算・保存
- [ ] ユニットテスト作成

### フェーズ5: API実装

- [ ] `routers/fanbase.py`作成
  - [ ] `GET /api/clubs/{club_id}/fanbase` - FB状態取得
  - [ ] `GET /api/clubs/{club_id}/fan_indicator` - 公開ファン指標取得
- [ ] `routers/seasons.py`の更新
  - [ ] `GET /api/seasons/{season_id}/fixtures/{fixture_id}` - 試合詳細（天候・入場者数含む）
- [ ] APIテスト作成

### フェーズ6: 統合・テスト

- [ ] `apply_finance_for_turn`にFB更新ロジック統合
- [ ] `process_matches_for_turn`に入場者数計算統合
- [ ] 統合テスト作成
- [ ] E2Eテスト作成
- [ ] パフォーマンステスト

### フェーズ7: ドキュメント

- [ ] API仕様書更新
- [ ] 開発者ガイド更新
- [ ] マイグレーション手順書

---

## PR6: 月次入力項目と会計項目の拡張

### フェーズ1: 入力スキーマ設計

- [ ] `TurnDecision.payload_json`の構造定義
  - [ ] `DecisionPayload`スキーマ作成
    - [ ] `sales_expense: Optional[Decimal]`
    - [ ] `promo_expense: Optional[Decimal]`
    - [ ] `hometown_expense: Optional[Decimal]`
    - [ ] `next_home_promo: Optional[Decimal]`
    - [ ] `additional_reinforcement: Optional[Decimal]` (12月のみ)
- [ ] バリデーションロジック設計
  - [ ] 翌月ホーム向けプロモ費の条件チェック
  - [ ] 追加強化費の条件チェック（12月、債務超過チェック）

### フェーズ2: 入力API拡張

- [ ] `routers/turns.py`の更新
  - [ ] `POST /api/turns/{turn_id}/decisions/{club_id}/commit` - スキーマ拡張
  - [ ] バリデーション追加
- [ ] `GET /api/turns/{turn_id}/decisions/{club_id}` - 入力内容取得API
- [ ] 入力テスト作成

### フェーズ3: 会計項目実装

- [ ] `services/distribution.py`作成
  - [ ] `process_distribution_revenue()` - 配分金処理（8月）
- [ ] `services/merchandise.py`作成
  - [ ] `process_merchandise_revenue()` - 物販収入計算
  - [ ] `process_merchandise_cost()` - 物販費用計算
- [ ] `services/match_operation.py`作成
  - [ ] `process_match_operation_cost()` - 試合運営費計算
- [ ] `services/prize.py`作成
  - [ ] `calculate_prize_amount()` - 賞金額計算（順位ベース）
  - [ ] `process_prize_revenue()` - 賞金入金（6月）
- [ ] `services/severance.py`作成
  - [ ] `calculate_severance_cost()` - 退職金計算（年収の0.75年分）
  - [ ] `process_severance_cost()` - 退職金処理（7月）

### フェーズ4: 財務処理統合

- [ ] `services/finance.py`の`apply_finance_for_turn`更新
  - [ ] 月次入力項目の費用計上
  - [ ] 新規会計項目の処理追加
  - [ ] 処理順序の最適化
- [ ] 統合テスト作成

### フェーズ5: データベース変更

- [ ] 賞金テーブル設計（オプション）
  - [ ] `season_prizes`テーブル作成
- [ ] Alembicマイグレーションファイル作成
  - [ ] `0005_pr6_input_accounting.py`
- [ ] マイグレーションテスト

### フェーズ6: API実装

- [ ] `routers/seasons.py`の更新
  - [ ] `GET /api/seasons/{season_id}/prizes` - 賞金情報取得（6月）
- [ ] APIテスト作成

### フェーズ7: テスト・ドキュメント

- [ ] 全機能のユニットテスト
- [ ] 統合テスト
- [ ] E2Eテスト
- [ ] API仕様書更新

---

## PR7: スポンサー内定進捗と営業努力モデルの完全実装

### フェーズ1: データベース設計

- [ ] `club_sales_allocations`テーブル設計
  - [ ] カラム定義（club_id, season_id, quarter, rho_new）
  - [ ] インデックス・制約
- [ ] `club_sponsor_states`テーブル拡張
  - [ ] `cumulative_ret_effort`, `cumulative_new_effort`追加
  - [ ] `pipeline_existing`, `pipeline_new`追加
  - [ ] `next_revenue_forecast`追加
- [ ] Alembicマイグレーションファイル作成
  - [ ] `0006_pr7_sponsor_effort.py`

### フェーズ2: 営業努力モデル実装

- [ ] `services/sales_effort.py`作成
  - [ ] `ensure_sales_allocation()` - 営業リソース配分の初期化
  - [ ] `update_sales_allocation()` - 四半期配分更新（8/11/2/5月のみ）
  - [ ] `calculate_effective_effort()` - 月次有効営業努力計算
    - [ ] `E_ret = w_s^ret * RetStaff + w_m^ret * RetSpend/10^6`
    - [ ] `E_new = w_s^new * NewStaff + w_m^new * NewSpend/10^6`
  - [ ] `update_cumulative_effort()` - 累積営業努力更新（EWMA）
    - [ ] `C_ret(t) = (1-λ_ret)*C_ret(t-1) + λ_ret*E_ret(t)`
    - [ ] `C_new(t) = (1-λ_new)*C_new(t-1) + λ_new*E_new(t)`
- [ ] `models.py`に`ClubSalesAllocation`モデル追加
- [ ] ユニットテスト作成

### フェーズ3: スポンサー内定進捗実装

- [ ] `services/sponsor.py`の更新
  - [ ] `process_pipeline_progress()` - 内定進捗処理（4-7月）
    - [ ] 4-6月: 確率的抽選（既存/新規で異なる確率）
    - [ ] 7月: 強制確定
  - [ ] `get_pipeline_status()` - 内定進捗状態取得
  - [ ] `calculate_next_revenue_forecast()` - 次年度収入見込み計算
- [ ] ユニットテスト作成

### フェーズ4: API実装

- [ ] `routers/management.py`の更新
  - [ ] `POST /api/clubs/{club_id}/management/sales/allocation` - 営業リソース配分設定
- [ ] `routers/sponsor.py`作成（または既存拡張）
  - [ ] `GET /api/clubs/{club_id}/sponsor/pipeline` - 内定進捗取得（4-7月）
  - [ ] `GET /api/clubs/{club_id}/sponsor/next` - 次年度スポンサー情報取得（7月）
- [ ] APIテスト作成

### フェーズ5: 統合

- [ ] `apply_finance_for_turn`に営業努力更新統合
- [ ] `determine_next_sponsors`に内定進捗統合
- [ ] 統合テスト作成

### フェーズ6: テスト・ドキュメント

- [ ] 全機能のユニットテスト
- [ ] 統合テスト
- [ ] E2Eテスト
- [ ] API仕様書更新

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

