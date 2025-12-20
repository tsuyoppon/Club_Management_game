# Jリーグクラブ経営ゲーム v1 実装ロードマップ

## 概要

このドキュメントは、v1Spec.pdfの仕様に基づいた実装ロードマップとPR単位の作業計画を記載しています。

**現在の実装状況**: 約40-50%完了（コア機能は実装済み）

---

## 実装済みPR一覧

### ✅ PR1: ゲームスケルトン
- 基本ゲーム構造（Game, Club, User, Membership）
- シーズン・ターン管理
- ラウンドロビン対戦表生成
- ロールベース権限制御

### ✅ PR2: 財務コア
- 財務プロファイル・状態・台帳・スナップショット
- 月次財務処理フロー

### ✅ PR3: 構造的財務テーブル
- 補強予算（ClubReinforcementPlan）
- スポンサー状態（ClubSponsorState）
- スタッフ管理（ClubStaff）

### ✅ PR4: 動的機能
- アカデミー（ClubAcademy）
- チケット収入（簡易版）
- スタッフ採用・解雇ロジック

### ✅ PR4.5: 試合結果・順位表
- 試合勝敗・得点モデル（完全実装）
- 順位表計算（H2H考慮）
- シーズン終了処理

### ✅ PR5: ファンベース（FB）モデルと入場者数モデル
- FB状態管理テーブル追加（`club_fanbase_states`）
- FB更新ロジック実装（EWMA, 成長率, 上限制約）
- 公開ファン指標（Followers）計算
- 天候システム実装（確率分布, 効果）
- 入場者数モデル実装（ホーム/アウェイ来場率, Cap制約）
- チケット収入計算の更新

---

## 今後の実装PR計画

### 🔄 PR6: 月次入力項目と会計項目の拡張

**目的**: v1Spec セクション9の完全実装

**実装内容**:

#### 5.1 ファンベース（FB）モデル
- [ ] FB状態管理テーブル追加（`club_fanbase_states`）
  - `club_id`, `season_id`
  - `fb_count` (FB人数)
  - `fb_rate` (f = FB/Pop)
  - `cumulative_promo` (累積プロモ、EWMA)
  - `cumulative_ht` (累積ホームタウン活動費、EWMA)
  - `last_ht_spend` (前月ホームタウン活動費、急変ペナルティ用)
- [ ] FB更新ロジック実装
  - EWMA更新（λ=0.10）
  - 成長率計算（g_0, a_1-a_4係数）
  - 上限制約（f_max=0.25）
- [ ] 公開ファン指標（Followers）計算
  - `ln(Followers) = ln(κ_F * FB) + ε`
  - κ_F=1.0, σ_F=0.15

#### 5.2 入場者数モデル
- [ ] 天候システム実装
  - 天候確率分布（晴0.55/曇0.30/雨0.15）
  - 天候効果（g_W: 晴0/曇-0.2/雨-0.6）
- [ ] ホーム来場率計算
  - ロジスティック回帰モデル（β_0-β_5係数）
  - プロモ効果、イベント効果（開幕/最終戦）
  - Cap制約
- [ ] アウェイ来場計算
  - 基準遠征率（r_away_0=0.018）
  - 天候影響（κ_W=0.20）
  - 上限制約（q_max=0.20）
- [ ] Cap超過時の比率縮小処理
- [ ] チケット収入計算の更新
  - 現在の簡易版から詳細モデルへ移行

**データベース変更**:
```sql
-- 新規テーブル: club_fanbase_states
CREATE TABLE club_fanbase_states (
    id UUID PRIMARY KEY,
    club_id UUID NOT NULL,
    season_id UUID NOT NULL,
    fb_count INTEGER NOT NULL DEFAULT 60000,
    fb_rate NUMERIC(10, 6) NOT NULL DEFAULT 0.06,
    cumulative_promo NUMERIC(14, 2) NOT NULL DEFAULT 0,
    cumulative_ht NUMERIC(14, 2) NOT NULL DEFAULT 0,
    last_ht_spend NUMERIC(14, 2) NOT NULL DEFAULT 0,
    followers_public INTEGER, -- 公開指標（キャッシュ）
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(club_id, season_id)
);

-- Fixture テーブルに天候カラム追加
ALTER TABLE fixtures ADD COLUMN weather VARCHAR(10); -- 'sunny', 'cloudy', 'rain'
ALTER TABLE fixtures ADD COLUMN home_attendance INTEGER;
ALTER TABLE fixtures ADD COLUMN away_attendance INTEGER;
ALTER TABLE fixtures ADD COLUMN total_attendance INTEGER;
```

**API変更**:
- `GET /api/clubs/{club_id}/fanbase` - FB状態取得
- `GET /api/clubs/{club_id}/fan_indicator` - 公開ファン指標取得
- `GET /api/seasons/{season_id}/fixtures/{fixture_id}` - 試合詳細（天候・入場者数含む）

**テスト要件**:
- FB成長率計算のテスト
- 入場者数モデルの各種シナリオテスト
- 天候分布の統計的検証

**依存関係**: PR6（月次入力項目）と連携が必要

---

### 🔄 PR6: 月次入力項目と会計項目の拡張

**目的**: v1Spec セクション5, 7の完全実装

**実装内容**:

#### 6.1 月次入力項目
- [ ] 入力スキーマ拡張（`TurnDecision.payload_json`の構造化）
  - `sales_expense` (営業費用)
  - `promo_expense` (プロモーション費用)
  - `hometown_expense` (ホームタウン活動費用)
  - `next_home_promo` (翌月ホーム向けプロモ費、条件付き)
- [ ] 入力バリデーション
  - 翌月ホーム向けプロモ費は「ホームゲームがある月の前月」のみ入力可能
- [ ] 追加強化費入力（12月）
  - 債務超過ペナルティ中は入力不可（PR8と連携）

#### 6.2 会計項目の追加
- [ ] 配分金（8月一括入金）
  - 固定額または計算式で決定
  - `ClubFinancialLedger`に`kind="distribution_revenue"`追加
- [ ] 物販収入・費用（ホームゲーム月）
  - 物販収入計算ロジック
  - 物販費用（原価）計算
  - `kind="merchandise_revenue"`, `kind="merchandise_cost"`
- [ ] 試合運営費（ホームゲーム月）
  - 固定費または変動費モデル
  - `kind="match_operation_cost"`
- [ ] 賞金（6月ターン終了で表示＆入金）
  - 順位に基づく賞金額計算
  - `kind="prize_revenue"`
- [ ] 退職金（7月）
  - 解雇に伴う割増退職金計算
  - 年収の0.75年分（v1固定）
  - `kind="severance_cost"`

#### 6.3 財務処理の統合
- [ ] `apply_finance_for_turn`の拡張
  - 新規会計項目の処理を追加
  - 月次入力項目の費用計上

**データベース変更**:
```sql
-- 配分金設定（ゲーム単位または固定値）
-- 既存のClubFinancialProfileに追加するか、別テーブルで管理

-- 賞金テーブル（オプション、計算式で管理する場合は不要）
CREATE TABLE season_prizes (
    id UUID PRIMARY KEY,
    season_id UUID NOT NULL,
    rank INTEGER NOT NULL,
    prize_amount NUMERIC(14, 2) NOT NULL,
    UNIQUE(season_id, rank)
);
```

**API変更**:
- `POST /api/turns/{turn_id}/decisions/{club_id}/commit` - 入力スキーマ拡張
- `GET /api/turns/{turn_id}/decisions/{club_id}` - 入力内容取得
- `GET /api/seasons/{season_id}/prizes` - 賞金情報取得（6月）

**テスト要件**:
- 月次入力のバリデーションテスト
- 各会計項目の計算ロジックテスト
- 賞金計算のテスト

**依存関係**: PR5（FB・入場者数モデル）の結果を使用

---

### 🔄 PR7: スポンサー内定進捗と営業努力モデルの完全実装

**目的**: v1Spec セクション10の完全実装

**実装内容**:

#### 7.1 営業努力モデル
- [ ] 営業リソース配分管理
  - 四半期ごとの新規配分率（ρ_new）入力
  - 入力可能月: 8/11/2/5月（四半期開始月）
- [ ] 月次有効営業努力計算
  - `E_ret = w_s^ret * RetStaff + w_m^ret * RetSpend/10^6`
  - `E_new = w_s^new * NewStaff + w_m^new * NewSpend/10^6`
  - 係数: w_s^ret=1.4, w_m^ret=0.12, w_s^new=1.6, w_m^new=0.08
- [ ] 累積営業努力（EWMA）
  - `C_ret(t) = (1-λ_ret)*C_ret(t-1) + λ_ret*E_ret(t)`
  - `C_new(t) = (1-λ_new)*C_new(t-1) + λ_new*E_new(t)`
  - λ_ret=0.12, λ_new=0.05

#### 7.2 スポンサー内定進捗（4-7月）
- [ ] 内定進捗状態管理
  - `ClubSponsorState`に`pipeline_existing`, `pipeline_new`追加
  - 4-6月: 確率的抽選（既存q_4=0.40/q_5=0.35/q_6=0.30、新規q_4=0.15/q_5=0.25/q_6=0.35）
  - 7月: 強制確定
- [ ] UI表示用API
  - 4-6月: 内定累計（既存/新規/合計）＋増分
  - 7月: 最終確定＋次年度スポンサー収入見込み

#### 7.3 スポンサー確定ロジックの改善
- [ ] 7月のスポンサー確定処理
  - 既存スポンサー数（チャーン後）
  - 新規スポンサー数（Leads × Conversion）
  - 次年度スポンサー収入見込み表示

**データベース変更**:
```sql
-- ClubSponsorState に追加
ALTER TABLE club_sponsor_states ADD COLUMN cumulative_ret_effort NUMERIC(14, 4) DEFAULT 0;
ALTER TABLE club_sponsor_states ADD COLUMN cumulative_new_effort NUMERIC(14, 4) DEFAULT 0;
ALTER TABLE club_sponsor_states ADD COLUMN pipeline_existing INTEGER DEFAULT 0;
ALTER TABLE club_sponsor_states ADD COLUMN pipeline_new INTEGER DEFAULT 0;
ALTER TABLE club_sponsor_states ADD COLUMN next_revenue_forecast NUMERIC(14, 2);

-- 営業リソース配分テーブル（新規）
CREATE TABLE club_sales_allocations (
    id UUID PRIMARY KEY,
    club_id UUID NOT NULL,
    season_id UUID NOT NULL,
    quarter INTEGER NOT NULL, -- 1-4 (Q1: Aug-Oct, Q2: Nov-Jan, Q3: Feb-Apr, Q4: May-Jul)
    rho_new NUMERIC(5, 4) NOT NULL, -- 0-1
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(club_id, season_id, quarter)
);
```

**API変更**:
- `POST /api/clubs/{club_id}/management/sales/allocation` - 営業リソース配分設定（四半期開始月のみ）
- `GET /api/clubs/{club_id}/sponsor/pipeline` - 内定進捗取得（4-7月）
- `GET /api/clubs/{club_id}/sponsor/next` - 次年度スポンサー情報取得（7月）

**テスト要件**:
- 営業努力計算のテスト
- 内定進捗の確率分布検証
- 四半期配分のバリデーションテスト

**依存関係**: PR6（月次入力項目）の営業費用データを使用

---

### 🔄 PR8: 債務超過ペナルティとゲーム終了条件

**目的**: v1Spec セクション1.1, 14.1の完全実装

**実装内容**:

#### 8.1 債務超過判定
- [ ] 月次債務超過チェック
  - ターン解決時に各クラブの残高をチェック
  - マイナス残高の検出
- [ ] 債務超過状態管理
  - `ClubFinancialState`に`is_bankrupt`フラグ追加
  - `bankrupt_since_turn_id`（債務超過開始ターン）

#### 8.2 債務超過ペナルティ
- [ ] 勝点剥奪（-6点）
  - 債務超過クラブの順位表から勝点を減算
  - マイナス勝点は0にクリップ
- [ ] 追加強化費禁止
  - 12月の追加強化費入力をブロック
- [ ] 最下位ペナルティ（オプション）
  - 次年度配分金ゼロ設定
  - ゲーム設定でON/OFF可能

#### 8.3 ゲーム終了条件
- [ ] 年度終了時の脱落判定（7月）
  - 債務超過クラブの最終確認
  - 脱落フラグ設定
- [ ] 脱落クラブの処理
  - 試合参加は継続（スケジュール通り）
  - 勝点剥奪は継続

**データベース変更**:
```sql
-- ClubFinancialState に追加
ALTER TABLE club_financial_states ADD COLUMN is_bankrupt BOOLEAN DEFAULT FALSE;
ALTER TABLE club_financial_states ADD COLUMN bankrupt_since_turn_id UUID;

-- 勝点剥奪履歴（オプション、監査用）
CREATE TABLE club_point_penalties (
    id UUID PRIMARY KEY,
    club_id UUID NOT NULL,
    season_id UUID NOT NULL,
    turn_id UUID NOT NULL,
    points_deducted INTEGER NOT NULL,
    reason VARCHAR(100) NOT NULL, -- 'bankruptcy'
    created_at TIMESTAMP NOT NULL
);

-- Game テーブルに設定追加
ALTER TABLE games ADD COLUMN last_place_penalty_enabled BOOLEAN DEFAULT FALSE;
```

**API変更**:
- `GET /api/clubs/{club_id}/finance/state` - 債務超過状態を含む
- `GET /api/seasons/{season_id}/bankrupt_clubs` - 債務超過クラブ一覧
- `POST /api/seasons/{season_id}/check_bankruptcy` - 債務超過チェック（7月）

**テスト要件**:
- 債務超過判定のテスト
- 勝点剥奪のテスト
- 追加強化費禁止のテスト
- 最下位ペナルティのテスト

**依存関係**: PR6（会計項目）の実装後

---

### 🔄 PR9: 情報公開イベントと最終結果表示

**目的**: v1Spec セクション4, 13, 1.2の完全実装

**実装内容**:

#### 9.1 情報公開イベント
- [ ] 12月ターン終了時の公開処理
  - 全クラブの前期財務サマリー（PL/BS簡易）公開
  - チーム力指標（最新）再公開
- [ ] 7月ターン終了時の公開処理
  - 次シーズンのチーム力指標公開（不確実性付き）
- [ ] 公開情報の保存
  - `season_public_disclosures`テーブル作成
  - 公開タイミング、公開内容を記録

#### 9.2 5月順位表の追加表示
- [ ] 優勝・準優勝の表示
  - 1位「優勝」、2位「準優勝」を横に表示
- [ ] 平均入場者数の追加
  - 各クラブのホームゲーム平均入場者数を順位表に追加

#### 9.3 最終結果表示
- [ ] ゲーム終了時の総合結果
  - 売上規模（最終期）＋順位
  - 純資産（期末現金残高）＋順位
  - 成績（優勝回数、準優勝回数、平均順位）
  - ホームゲーム平均入場者数（全シーズン）＋順位
- [ ] 結果表示API
  - `GET /api/games/{game_id}/final_results`

**データベース変更**:
```sql
-- 公開情報テーブル
CREATE TABLE season_public_disclosures (
    id UUID PRIMARY KEY,
    season_id UUID NOT NULL,
    disclosure_type VARCHAR(50) NOT NULL, -- 'financial_summary', 'team_power', etc.
    disclosure_month INTEGER NOT NULL, -- 12 or 7
    disclosed_data JSONB NOT NULL, -- 全クラブの公開データ
    created_at TIMESTAMP NOT NULL
);

-- ゲーム結果サマリーテーブル
CREATE TABLE game_final_results (
    id UUID PRIMARY KEY,
    game_id UUID NOT NULL,
    club_id UUID NOT NULL,
    final_sales_rank INTEGER,
    final_sales_amount NUMERIC(14, 2),
    final_equity_rank INTEGER,
    final_equity_amount NUMERIC(14, 2),
    championship_count INTEGER DEFAULT 0,
    runner_up_count INTEGER DEFAULT 0,
    average_rank NUMERIC(5, 2),
    average_attendance_rank INTEGER,
    average_attendance NUMERIC(10, 0),
    created_at TIMESTAMP NOT NULL,
    UNIQUE(game_id, club_id)
);
```

**API変更**:
- `GET /api/seasons/{season_id}/public/financial_summary` - 財務サマリー公開（12月）
- `GET /api/seasons/{season_id}/public/team_power` - チーム力指標公開（12月/7月）
- `GET /api/seasons/{season_id}/standings` - 5月時は優勝/準優勝/平均入場者数を含む
- `GET /api/games/{game_id}/final_results` - 最終結果表示

**テスト要件**:
- 公開情報の正確性テスト
- 最終結果計算のテスト
- 順位表の追加表示テスト

**依存関係**: PR5-PR8の実装後

---

### 🔄 PR10: 参照コマンド（CLI）インターフェース

**目的**: v1Spec セクション6の完全実装

**実装内容**:

#### 10.1 CLI基盤
- [ ] CLIフレームワーク導入
  - `click`または`argparse`を使用
  - 認証・セッション管理
- [ ] コマンド構造
  - `club-game <command> [options]`
  - 設定ファイル（`.club-game/config`）でAPIエンドポイント管理

#### 10.2 実装コマンド
- [ ] `show match` - 試合結果一覧
  - `--month YYYY-MM` オプション
- [ ] `show table` - 順位表
- [ ] `show team_power` - チーム力指標
- [ ] `show staff` - 部署別人数
- [ ] `show staff_history` - 人員変動履歴
  - `--from YYYY-MM`, `--to YYYY-MM` オプション
- [ ] `show current_input` - 当ターン入力内容
- [ ] `show history` - 過去の入力一覧
  - `--from YYYY-MM`, `--to YYYY-MM` オプション（デフォルト: 先月）
- [ ] `show fan_indicator` - ファン指標
  - `--club <name>` オプション
  - `--from YYYY-MM`, `--to YYYY-MM` オプション
- [ ] `show sponsor_status` - スポンサー状態
  - `--pipeline` オプション（4-6月）
  - `--next` オプション（7月）
- [ ] `help` / `help <command>` - ヘルプ表示

#### 10.3 入力コマンド（オプション）
- [ ] `input` - 月次入力
  - `--sales-expense`, `--promo-expense`, `--hometown-expense`
  - `--next-home-promo`
- [ ] `commit` - 入力確定
- [ ] `view` - 入力確認

**実装方針**:
- CLIは別パッケージとして実装（`apps/cli/`）
- 既存のREST APIを呼び出す形で実装
- 認証は`X-User-Email`ヘッダを使用

**テスト要件**:
- 各コマンドの動作テスト
- エラーハンドリングテスト
- 認証・セッション管理のテスト

**依存関係**: PR5-PR9の実装後（APIが完成してから）

---

## PR実装順序と依存関係

```
PR5 (FB・入場者数モデル)
  ↓
PR6 (月次入力・会計項目)
  ↓
PR7 (スポンサー内定進捗・営業努力)
  ↓
PR8 (債務超過ペナルティ)
  ↓
PR9 (情報公開・最終結果)
  ↓
PR10 (CLI)
```

## 実装優先度マトリックス

| PR | 優先度 | 難易度 | 依存関係 | 推定工数 |
|----|--------|--------|----------|----------|
| PR5 | 高 | 高 | なし | 3-4週間 |
| PR6 | 高 | 中 | PR5 | 2-3週間 |
| PR7 | 中 | 中 | PR6 | 2週間 |
| PR8 | 高 | 低 | PR6 | 1週間 |
| PR9 | 中 | 低 | PR5-PR8 | 1-2週間 |
| PR10 | 低 | 中 | PR5-PR9 | 2週間 |

**合計推定工数**: 11-14週間（約3-3.5ヶ月）

## 各PRの完了基準

### PR5完了基準
- [ ] FBモデルがv1Spec通りに動作
- [ ] 入場者数モデルがv1Spec通りに動作
- [ ] 天候システムが実装されている
- [ ] テストカバレッジ80%以上

### PR6完了基準
- [ ] 全月次入力項目が入力可能
- [ ] 全会計項目が計上される
- [ ] バリデーションが正しく動作
- [ ] テストカバレッジ80%以上

### PR7完了基準
- [ ] 営業努力モデルが完全実装
- [ ] スポンサー内定進捗が4-7月で動作
- [ ] UI表示APIが実装されている
- [ ] テストカバレッジ80%以上

### PR8完了基準
- [ ] 債務超過判定が正しく動作
- [ ] 勝点剥奪が実装されている
- [ ] 追加強化費禁止が動作
- [ ] テストカバレッジ80%以上

### PR9完了基準
- [ ] 全情報公開イベントが動作
- [ ] 最終結果表示が実装されている
- [ ] 5月順位表の追加表示が実装されている
- [ ] テストカバレッジ80%以上

### PR10完了基準
- [ ] 全参照コマンドが実装されている
- [ ] CLIが安定して動作
- [ ] ドキュメントが整備されている
- [ ] テストカバレッジ70%以上

## リスクと対策

### リスク1: FBモデルの複雑さ
**対策**: 段階的実装（EWMA → 成長率 → 上限制約）

### リスク2: 入場者数モデルの精度
**対策**: プレイテストで係数調整、簡易版から段階的に移行

### リスク3: 月次入力のバリデーション複雑化
**対策**: スキーマ定義を明確化、テストを充実

### リスク4: 会計項目の漏れ
**対策**: v1Specと照合チェックリストを作成

### リスク5: CLIの実装遅延
**対策**: REST APIを優先、CLIは後回しでも可

## 次のアクション

1. **PR5の設計レビュー**
   - FBモデルのデータ構造設計
   - 入場者数モデルの計算フロー設計

2. **テスト戦略の策定**
   - 各PRのテスト計画
   - 統合テスト計画

3. **ドキュメント整備**
   - API仕様書の更新
   - 開発者ガイドの作成

---

**最終更新日**: 2024年12月
**次回レビュー**: PR5実装開始前

