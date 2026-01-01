# CLI 入力コマンド仕様（v1Spec準拠）

## 1. 入力項目と許可条件

### 1.1 毎月入力（通年：8〜7月、month_index 1〜12）

| 項目 | フィールド名 | 型 | 備考 |
|------|------------|------|------|
| 営業費用 | `sales_expense` | Decimal | 当月計上 |
| プロモーション費用 | `promo_expense` | Decimal | 当月計上 |
| ホームタウン活動費用 | `hometown_expense` | Decimal | 当月計上 |

### 1.2 条件付き入力

| 項目 | フィールド名 | 許可条件 | バリデーション |
|------|------------|----------|----------------|
| 翌月ホーム向けプロモ費 | `next_home_promo` | 翌月がホームゲーム月の前月のみ | 非対象月は400エラー |
| 追加強化費 | `additional_reinforcement` | 12月（month_index=5）のみ、債務超過でない | 債務超過時は400エラー |

### 1.3 年次（5月イベント時）

| 項目 | フィールド名 | 許可条件 |
|------|------------|----------|
| 採用目標 | `hiring_target` | 5月（month_index=10）のみ |
| 解雇 | `firing` | 5月（month_index=10）のみ |
| アカデミー投資額（翌年度） | `academy_budget` | 5月（month_index=10）のみ |
| 強化費（翌年度） | `reinforcement_budget` | 6月・7月（month_index=11,12）の合算 |

### 1.4 営業リソース配分（四半期開始月のみ）

| 四半期 | 対象月 | month_index | 入力可能月 |
|--------|--------|-------------|-----------|
| Q1 | 8〜10月 | 1〜3 | 8月（1） |
| Q2 | 11〜1月 | 4〜6 | 11月（4） |
| Q3 | 2〜4月 | 7〜9 | 2月（7） |
| Q4 | 5〜7月 | 10〜12 | 5月（10） |

フィールド: `rho_new` (0.0〜1.0)

## 2. ターン状態と入力可否

| ターン状態 | 入力可否 | commit可否 |
|-----------|---------|------------|
| `open` | ✓ | ✓ |
| `collecting` | ✓ | ✓ |
| `locked` | ✗ | ✗ |
| `resolved` | ✗ | ✗ |
| `acked` | ✗ | ✗ |

## 3. エラーコードとCLI表示

| HTTPステータス | 原因 | CLI表示 |
|---------------|------|---------|
| 400 | バリデーションエラー（条件外入力等） | `Error: {detail}` |
| 404 | リソース不存在（turn/club/season） | `Error: Not found - {detail}` |
| 409 | 状態競合（ターンlocked等） | `Error: Conflict - {detail}` |
| 422 | リクエストボディ不正 | `Error: Validation failed - {detail}` |
| 5xx | サーバーエラー | `Error: Server error ({status_code})` |

## 4. コマンド設計

### 4.1 `input` - 月次入力

```
club-game input [OPTIONS]
  --sales-expense DECIMAL      営業費用
  --promo-expense DECIMAL      プロモーション費用
  --hometown-expense DECIMAL   ホームタウン活動費用
  --next-home-promo DECIMAL    翌月ホーム向けプロモ費（条件付き）
  --additional-reinforcement DECIMAL  追加強化費（12月のみ）
  --rho-new FLOAT              営業リソース新規配分比率（四半期開始月のみ）
  --season-id UUID             シーズンID（config優先）
  --club-id UUID               クラブID（config優先）
```

### 4.2 `commit` - 入力確定

```
club-game commit [OPTIONS]
  --season-id UUID             シーズンID（config優先）
  --club-id UUID               クラブID（config優先）
  -y, --yes                    確認プロンプトをスキップ
```

### 4.3 `view` - 入力確認（既存 show current_input と同等）

```
club-game view [OPTIONS]
  --season-id UUID             シーズンID（config優先）
  --club-id UUID               クラブID（config優先）
  --json-output                JSON出力
```

## 5. 実装優先順位

1. `input` - 基本3項目（sales/promo/hometown）
2. `commit` - 確定処理
3. `view` - 確認（show current_input のエイリアス）
4. `input` - 条件付き項目（next_home_promo, additional_reinforcement）
5. `input` - 営業リソース配分（rho_new）
6. 5月イベント系（採用/解雇/アカデミー/強化費）

## 6. テスト方針

- 入力系はPOST/PUTを伴うためモック中心
- `ApiClient.post`/`ApiClient.put` をmonkeypatchしてペイロード検証
- エラー系は各HTTPステータスをモックして表示確認
- 副作用ゼロを維持（DB/APIへの実際の書き込みなし）
