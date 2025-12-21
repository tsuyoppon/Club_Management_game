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

### ✅ PR6: 月次入力項目と会計項目の拡張
- 配分金（8月一括入金）
- 物販収入・費用（ホームゲーム月）
- 試合運営費（ホームゲーム月）
- 賞金（6月）
- 月次入力バリデーション（翌月ホーム向けプロモ費制約）

### ✅ PR7: スポンサー内定進捗と営業努力モデルの完全実装
- 営業リソース配分管理（四半期ごとのρ_new入力）
- 月次有効営業努力計算（E_ret, E_new）
- 累積営業努力EWMA（C_ret, C_new）
- スポンサー内定進捗（4-7月パイプライン）
- 次年度スポンサー情報API

### ✅ PR8: 債務超過ペナルティとゲーム終了条件
- 債務超過判定（balance < 0 でis_bankrupt = true）
- 勝点剥奪（-6点）順位表への反映
- ClubPointPenaltyテーブル追加（履歴管理）
- 追加強化費禁止（12月入力ブロック）
- 最下位ペナルティ設定（ON/OFF、デフォルトOFF）
- bankruptcy.py サービス（判定・ペナルティ適用）
- bankruptcy.py ルーター（5エンドポイント）
- E2Eテスト（e2e_pr8_bankruptcy.sh）

---

## 今後の実装PR計画

### ✅ PR9: 情報公開イベントと最終結果表示 (完了)

**目的**: v1Spec セクション4, 13, 1.2の完全実装

**実装内容**:

#### 9.1 情報公開イベント
- [x] 12月ターン終了時の公開処理
  - 全クラブの前期財務サマリー（PL/BS簡易）公開
  - チーム力指標（最新）再公開
- [x] 7月ターン終了時の公開処理
  - 次シーズンのチーム力指標公開（不確実性付き）
- [x] 公開情報の保存
  - `season_public_disclosures`テーブル作成
  - 公開タイミング、公開内容を記録

#### 9.2 5月順位表の追加表示
- [x] 優勝・準優勝の表示
  - 1位「優勝」、2位「準優勝」を横に表示
- [x] 平均入場者数の追加
  - 各クラブのホームゲーム平均入場者数を順位表に追加

#### 9.3 最終結果表示
- [x] ゲーム終了時の総合結果
  - 売上規模（最終期）＋順位
  - 純資産（期末現金残高）＋順位
  - 成績（優勝回数、準優勝回数、平均順位）
  - ホームゲーム平均入場者数（全シーズン）＋順位
- [x] 結果表示API
  - `GET /api/games/{game_id}/final-results`

**作成したファイル**:
- `apps/api/app/services/team_power.py` - チーム力計算サービス
- `apps/api/app/services/public_disclosure.py` - 情報公開サービス
- `apps/api/app/services/final_results.py` - 最終結果計算サービス
- `apps/api/app/routers/disclosures.py` - 情報公開APIルーター
- `apps/api/alembic/versions/7a8b9c0d1e2f_pr9_disclosure_results.py` - マイグレーション

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


