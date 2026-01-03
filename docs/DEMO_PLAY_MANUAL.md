# Jリーグクラブ経営ゲーム デモプレイマニュアル

本ドキュメントでは、ゲームを起動してデモプレイを行うまでの手順を説明します。

---

## 目次

1. [前提条件](#1-前提条件)
2. [環境構築・起動](#2-環境構築起動)
3. [ゲーム初期設定（API経由）](#3-ゲーム初期設定api経由)
4. [CLI設定](#4-cli設定)
5. [デモプレイの流れ](#5-デモプレイの流れ)
6. [よく使うコマンド一覧](#6-よく使うコマンド一覧)
7. [トラブルシューティング](#7-トラブルシューティング)

---

## 1. 前提条件

以下がインストールされていることを確認してください。

- Docker / Docker Compose
- Python 3.11以上（CLI使用時）
- curl（API直接操作時）

---

## 2. 環境構築・起動

### 2.1 リポジトリのクローン

```bash
git clone https://github.com/tsuyoppon/Club_Management_game.git
cd Club_Management_game
```

### 2.2 環境変数の設定

```bash
cp .env.example .env
```

`.env` ファイルには以下の環境変数が含まれます。必要に応じて編集してください。

| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@db:5432/club_game` | PostgreSQLへの接続文字列 |
| `API_PREFIX` | `/api` | APIエンドポイントのプレフィックス |

#### 設定例（.env）

```dotenv
# データベース接続設定
# 形式: postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/club_game

# APIプレフィックス（通常は変更不要）
API_PREFIX=/api
```

**注意事項**:
- Docker Compose を使用する場合、ホスト名は `db`（コンテナ名）を使用します
- ローカル開発で直接PostgreSQLに接続する場合は `localhost` に変更してください
- 本番環境ではパスワードを強固なものに変更してください

### 2.3 Docker Composeで起動

#### 初回起動またはクリーンスタート

```bash
# データベースを含めて完全にリセットして起動
docker compose down -v
docker compose up -d

# データベース準備完了まで待機（5秒程度）
sleep 5

# マイグレーション実行
docker compose exec api alembic upgrade head
```

#### 既存環境の再起動

```bash
# データを保持したまま起動
docker compose up -d
```

起動完了後、以下にアクセスできます。

| サービス | URL |
|----------|-----|
| API | http://localhost:8000 |
| APIドキュメント | http://localhost:8000/docs |
| Web（オプション） | http://localhost:3000 |

### 2.4 マイグレーション状態の確認

```bash
# 現在のマイグレーションバージョンを確認
docker compose exec api alembic current

# 最新版でない場合はアップグレード
docker compose exec api alembic upgrade head
```

### 2.5 ヘルスチェック

```bash
curl http://localhost:8000/api/health
# {"status":"ok"} が返ればOK
```

---

## 3. ゲーム初期設定（API経由）

curlを使ってゲームをセットアップします。すべてのリクエストには `X-User-Email` ヘッダが必要です。

### ユーザー識別とメールアドレスについて

> **重要**: `X-User-Email` ヘッダはユーザーを一意に識別するキーとして使用されます。
>
> - **各プレイヤーには異なるメールアドレスを設定してください**
> - 同じメールアドレスを使用すると同一ユーザーとして扱われます
> - メールアドレスが初めて使用された時点でユーザーが自動作成されます
> - 1ユーザーは1クラブのオーナーとしてのみ登録可能です（GM除く）
>
> **推奨設定例**:
> | 役割 | メールアドレス例 |
> |------|------------------|
> | ゲームマスター | gm@example.com |
> | クラブ1オーナー | owner1@example.com |
> | クラブ2オーナー | owner2@example.com |
> | クラブ3オーナー | owner3@example.com |
>
> **注意**: GMは全クラブを操作可能ですが、各クラブオーナーは自分のクラブのみ操作できます。

### 3.1 ゲーム作成（GMユーザー）

```bash
curl -X POST http://localhost:8000/api/games \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"研修リーグ2025"}'
```

**レスポンス例**:
```json
{
  "id": "44a889ca-eb9f-4d21-8bee-1ea8064694ef",
  "name": "研修リーグ2025",
  "status": "active",
  "created_at": "2026-01-03T12:49:20.935269"
}
```

レスポンスから `id`（game_id）をメモしてください。

### 3.2 クラブ追加（最大5クラブ）

```bash
# 環境変数にゲームIDを設定
export GAME_ID="<your_game_id>"

# クラブ1
curl -X POST http://localhost:8000/api/games/$GAME_ID/clubs \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"大阪イレブン","short_name":"OSA"}'

# クラブ2
curl -X POST http://localhost:8000/api/games/$GAME_ID/clubs \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"東京ユナイテッド","short_name":"TYO"}'

# 必要に応じて3〜5クラブまで追加
```

**レスポンス例**:
```json
{
  "id": "586c6f92-ea66-4ebf-899a-ef3772333011",
  "name": "大阪イレブン",
  "short_name": "OSA",
  "game_id": "44a889ca-eb9f-4d21-8bee-1ea8064694ef"
}
```

各レスポンスから `id`（club_id）をメモしてください。

### 3.3 メンバーシップ追加（クラブオーナー設定）

**重要**: `role` フィールドには `club_owner` を指定してください（`owner` ではありません）。

```bash
# 環境変数にIDを設定
export GAME_ID="<your_game_id>"
export CLUB_ID_1="<club_1_id>"
export CLUB_ID_2="<club_2_id>"

# クラブ1のオーナー設定
curl -X POST http://localhost:8000/api/games/$GAME_ID/memberships \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"email":"owner1@example.com","role":"club_owner","club_id":"'"$CLUB_ID_1"'"}'

# クラブ2のオーナー設定
curl -X POST http://localhost:8000/api/games/$GAME_ID/memberships \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"email":"owner2@example.com","role":"club_owner","club_id":"'"$CLUB_ID_2"'"}'
```

**レスポンス例**:
```json
{
  "id": "e4f049e3-ff6e-4c37-bf1a-0436b598acd3"
}
```

### 旧 3.3 メンバーシップ追加（クラブオーナー設定）



### 3.4 シーズン作成

```bash
export GAME_ID="<your_game_id>"

curl -X POST http://localhost:8000/api/seasons/games/$GAME_ID \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"year_label":"2025"}'
```

**レスポンス例**:
```json
{
  "id": "dc091eb3-2604-46eb-a3c5-f3c4524149a0",
  "game_id": "44a889ca-eb9f-4d21-8bee-1ea8064694ef",
  "season_number": 1,
  "year_label": "2025",
  "status": "running"
}
```

レスポンスから `id`（season_id）をメモしてください。

### 3.5 試合日程生成

**重要**: このエンドポイントには `Content-Type: application/json` ヘッダーが必要です。

```bash
export SEASON_ID="<your_season_id>"

curl -X POST http://localhost:8000/api/seasons/$SEASON_ID/fixtures/generate \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{}'
```

**レスポンス例**:
```json
{"fixtures": 10}
```

これで8月〜5月の10試合分の対戦表が生成されます。

---

## 4. CLI設定

### 4.1 依存パッケージのインストール

```bash
pip install -r apps/cli/requirements.txt
```

### 4.2 設定ファイルの作成

複数のプレイヤー（GM、各クラブオーナー）用に、それぞれ設定ファイルを作成します。

#### GM用設定（全クラブを操作可能）

```bash
mkdir -p ~/.club-game
cat > ~/.club-game/config << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "gm@example.com",
  "season_id": "<season_id>",
  "club_id": null
}
EOF
```

#### クラブオーナー用設定（各クラブごと）

```bash
# クラブ1オーナー用
cat > ~/.club-game/config.club1 << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "owner1@example.com",
  "season_id": "<season_id>",
  "club_id": "<club_1_id>"
}
EOF

# クラブ2オーナー用
cat > ~/.club-game/config.club2 << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "owner2@example.com",
  "season_id": "<season_id>",
  "club_id": "<club_2_id>"
}
EOF
```

**注意**: `<season_id>`、`<club_1_id>`、`<club_2_id>` は実際の値に置き換えてください。

#### 設定ファイルの使い方

```bash
# デフォルト設定（~/.club-game/config）を使用
python -m apps.cli.main <command>

# 特定の設定ファイルを指定
python -m apps.cli.main --config ~/.club-game/config.club1 <command>

# GMとして実行（club_idを明示的に指定）
python -m apps.cli.main --club-id <club_id> <command>
```

### 4.3 CLIの動作確認

```bash
python -m apps.cli.main help
```

### 4.4 シーズンIDを最新シーズンへ更新（自動解決）

シーズンロールオーバー後に設定ファイルの `season_id` を最新の running シーズンへ差し替えるには、GM/各クラブがそれぞれの設定ファイルで以下を実行してください。

```bash
python -m apps.cli.main --config-path ~/.club-game/config config set-season --latest
# game_id が設定ファイルに無い場合は --game-id <GAME_ID> を指定
```

- ゲームIDから最新の running シーズン（なければ直近シーズン）を取得し、`season_id` を上書き保存します。
- 各ユーザー（GM/クラブオーナー）が自分の設定ファイルに対して実行してください。
- 実行後に `season_id set to latest: <UUID>` と表示されれば更新完了です。

---

## 5. デモプレイの流れ

### 5.1 ターンライフサイクルの概要

```
open → commit → lock → resolve → ack → advance
  │       │       │        │       │       │
  │       │       │        │       │       └─ 次ターンへ進行
  │       │       │        │       └─ 結果確認
  │       │       │        └─ 試合/財務処理実行
  │       │       └─ 入力締切
  │       └─ 各クラブが意思決定を確定
  └─ ターン開始（GMが実行）
```

### 5.2 GMの操作（ターン進行）

> **GM認証の仕組み**:
> - CLIは設定ファイル（`~/.club-game/config`）の `user_email` を `X-User-Email` ヘッダとしてAPIに送信します
> - API側で、そのメールアドレスのユーザーがゲームのGMとして登録されているかを確認します
> - GMでない場合は **403 Forbidden** エラーが返されます
>
> **ローカルデモ時にGM操作を行う方法**:
>
> 方法1: configの`user_email`をGMのメールアドレスに設定
> ```json
> {
>   "base_url": "http://localhost:8000",
>   "user_email": "gm@example.com",
>   "season_id": "<season_id>"
> }
> ```
>
> 方法2: `--user-email` オプションでGMを指定
> ```bash
> python -m apps.cli.main gm open --season-id <season_id> --user-email gm@example.com
> ```
>
> 方法3: GM専用のconfigファイルを用意
> ```bash
> python -m apps.cli.main --config-path ~/.club-game/config-gm gm open --season-id <season_id>
> ```

#### メンバーを追加（GMが実行）

- 対象: GMのみ（`X-User-Email` にGMメールが必要）
- 役割ごとの注意: `club_owner` / `club_viewer` では `--club-id` が必須、`gm` では `--club-id` は指定不可
- `--game-id` を省略した場合はconfigの `game_id` を使用します

クラブオーナーとして招待する例（推奨）

```bash
python -m apps.cli.main game add-member \
  --game-id <game_id> \
  --email player1@example.com \
  --role club_owner \
  --club-id <club_id>
```

クラブ閲覧者として招待する例

```bash
python -m apps.cli.main game add-member \
  --game-id <game_id> \
  --email analyst@example.com \
  --role club_viewer \
  --club-id <club_id>
```

GM権限を追加する例（クラブ指定なし）

```bash
python -m apps.cli.main game add-member \
  --game-id <game_id> \
  --email gm2@example.com \
  --role gm
```

#### ターンを開く

```bash
python -m apps.cli.main gm open --season-id <season_id>
```

#### ターンをロック（入力締切）

```bash
python -m apps.cli.main gm lock --season-id <season_id>
```

#### ターンを解決（試合・財務処理）

```bash
python -m apps.cli.main gm resolve --season-id <season_id>
```

#### 次ターンへ進行

```bash
python -m apps.cli.main gm advance --season-id <season_id>
```

### 5.3 クラブオーナーの操作

> **重要**: 各クラブの入力データは `turn_id + club_id` ごとに**独立したレコード**として保存されます。
> クラブ1の入力とクラブ2の入力は互いに影響せず、別々に管理されます。

#### 現在のターン情報を確認

```bash
python -m apps.cli.main show current_input
```

#### 月次入力を行う

```bash
python -m apps.cli.main input \
  --sales-expense 5000000 \
  --promo-expense 3000000 \
  --hometown-expense 2000000
```

#### 入力内容を確認

```bash
python -m apps.cli.main view
```

#### 入力を確定

```bash
python -m apps.cli.main commit -y
```

#### スタッフ採用/解雇（5月のみ: month_index=10）

- 役職: director / coach / scout
- countを減らすと解雇（即時に退職金計上）、増やすと採用リクエスト（次シーズン開始時に反映）
- May以外で実行すると400エラー

```bash
# 例: コーチを3→2へ削減（解雇）
python -m apps.cli.main --config-path ~/.club-game/config-alpha staff plan \
  --role coach \
  --count 2

# 例: スカウトを1→2へ増員（採用リクエスト）
python -m apps.cli.main --config-path ~/.club-game/config-beta staff plan \
  --role scout \
  --count 2
```

### 5.4 複数クラブの入力（ローカルデモ時）

ローカル環境で複数クラブを1人で操作する場合、以下の方法があります。

#### 方法1: コマンドラインオプションで切り替え（推奨）

`--user-email` と `--club-id` オプションで、操作するクラブを一時的に切り替えます。

```bash
# クラブ1として入力（config設定を使用）
python -m apps.cli.main input --sales-expense 5000000

# クラブ2として入力（オプションで切り替え）
python -m apps.cli.main input --sales-expense 3000000 \
  --user-email owner2@example.com \
  --club-id <club_id_2>

# クラブ1をコミット
python -m apps.cli.main commit -y

# クラブ2をコミット
python -m apps.cli.main commit -y \
  --user-email owner2@example.com \
  --club-id <club_id_2>
```

**注意**: 各クラブの入力は完全に独立しています。クラブ2の入力がクラブ1のデータを上書きすることはありません。

#### 方法2: 複数の設定ファイルを使用

クラブごとに設定ファイルを用意し、`--config-path` で切り替えます。

```bash
# クラブ1用設定
cat > ~/.club-game/config-club1 << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "owner1@example.com",
  "season_id": "<season_id>",
  "club_id": "<club_id_1>"
}
EOF

# クラブ2用設定
cat > ~/.club-game/config-club2 << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "owner2@example.com",
  "season_id": "<season_id>",
  "club_id": "<club_id_2>"
}
EOF

# クラブ1として操作
python -m apps.cli.main --config-path ~/.club-game/config-club1 input --sales-expense 5000000
python -m apps.cli.main --config-path ~/.club-game/config-club1 commit -y

# クラブ2として操作
python -m apps.cli.main --config-path ~/.club-game/config-club2 input --sales-expense 3000000
python -m apps.cli.main --config-path ~/.club-game/config-club2 commit -y
```

#### 方法3: API直接操作（curl）

```bash
# クラブ1の入力
curl -X PUT http://localhost:8000/api/turns/<turn_id>/decisions/<club_id_1> \
  -H 'X-User-Email: owner1@example.com' \
  -H 'Content-Type: application/json' \
  -d '{"payload":{"sales_expense":5000000,"promo_expense":3000000}}'

# クラブ2の入力
curl -X PUT http://localhost:8000/api/turns/<turn_id>/decisions/<club_id_2> \
  -H 'X-User-Email: owner2@example.com' \
  -H 'Content-Type: application/json' \
  -d '{"payload":{"sales_expense":3000000,"promo_expense":2000000}}'

# 各クラブのコミット
curl -X POST http://localhost:8000/api/turns/<turn_id>/decisions/<club_id_1>/commit \
  -H 'X-User-Email: owner1@example.com'
curl -X POST http://localhost:8000/api/turns/<turn_id>/decisions/<club_id_2>/commit \
  -H 'X-User-Email: owner2@example.com'
```

### 5.5 結果確認（ack）

```bash
# CLI（クラブオーナーまたはGM）
# configのclub_idを使う場合
python -m apps.cli.main ack -y

# GMが別クラブを代行してACKする場合
python -m apps.cli.main --config-path ~/.club-game/config-gm ack --club-id <club_id> -y

# curl で直接叩く場合
curl -X POST http://localhost:8000/api/turns/<turn_id>/ack \
  -H 'X-User-Email: owner1@example.com' \
  -H 'Content-Type: application/json' \
  -d '{"club_id":"<club_id>","ack":true}'
```
※ ACK はクラブオーナーまたはGMのみ実行できます。

### 5.6 参照コマンド

```bash
# 順位表
python -m apps.cli.main show table

# 試合結果
python -m apps.cli.main show match

# チーム力指標
python -m apps.cli.main show team_power

# スタッフ状況
python -m apps.cli.main show staff

# ファン指標
python -m apps.cli.main show fan_indicator

# スポンサー状況
python -m apps.cli.main show sponsor_status
```

---

## 6. よく使うコマンド一覧

### GMコマンド

| コマンド | 説明 |
|----------|------|
| `gm open` | ターンを開く |
| `gm lock` | 入力を締め切る |
| `gm resolve` | 試合・財務処理を実行 |
| `gm advance` | 次ターンへ進行 |

### 参照コマンド（show）

| コマンド | 説明 |
|----------|------|
| `show table` | 順位表 |
| `show match` | 試合結果一覧 |
| `show team_power` | チーム力指標 |
| `show staff` | スタッフ状況 |
| `show staff_history` | スタッフ変動履歴 |
| `show current_input` | 当ターン入力内容 |
| `show history` | 過去の入力一覧 |
| `show fan_indicator` | ファン指標 |
| `show sponsor_status` | スポンサー状況 |

### 入力コマンド

| コマンド | 説明 |
|----------|------|
| `input --sales-expense <金額>` | 営業費用 |
| `input --promo-expense <金額>` | プロモーション費用 |
| `input --hometown-expense <金額>` | ホームタウン活動費 |
| `input --next-home-promo <金額>` | 翌月ホーム向けプロモ（条件付き） |
| `input --additional-reinforcement <金額>` | 追加強化費（12月のみ） |
| `input --reinforcement-budget <金額>` | 翌シーズン強化費（6月・7月に入力し合算） |
| `input --rho-new <0.0-1.0>` | 新規スポンサー配分（四半期開始月のみ） |
| `staff plan --role <director|coach|scout> --count <人数>` | スタッフ採用/解雇（5月のみ、count増で採用・減で解雇） |
| `ack` | 解決済みターンをACK（クラブオーナーまたはGM。GMはclub_id指定で代行可） |
| `view` | 入力内容確認 |
| `commit` | 入力確定（`-y`で確認スキップ） |

### 共通オプション

| オプション | 説明 |
|------------|------|
| `--json-output` | JSON形式で出力 |
| `--verbose` | HTTPステータスを表示 |
| `--season-id <UUID>` | シーズン指定 |
| `--club-id <UUID>` | クラブ指定 |

---

## 7. トラブルシューティング

### APIに接続できない

```bash
# Dockerコンテナが起動しているか確認
docker compose ps

# ログを確認
docker compose logs api
```

### マイグレーションエラー

```bash
# マイグレーションを再実行
docker compose exec api alembic upgrade head
```

### CLIで認証エラー

- `~/.club-game/config` の `user_email` が正しいか確認
- そのユーザーがゲームのメンバーシップに登録されているか確認

### ターンが進行できない

- 全クラブがcommitを完了しているか確認
- resolve後、全クラブがackを完了しているか確認

---

## Appendix A: 完全セットアップ例（2クラブでのテストプレイ）

このセクションでは、実際に動作確認済みの完全なセットアップ例を示します。

### A.0 前提条件の確認

```bash
# Dockerサービスが起動していることを確認
docker compose ps

# 出力例:
# NAME                         STATUS
# club_management_game-api-1   Up
# club_management_game-db-1    Up

# ヘルスチェック
curl http://localhost:8000/api/health

# 期待される出力: {"status":"ok","app":"club-management-api"}
```

### A.1 データベースの初期化

新規ゲームを開始する場合は、データベースを完全にリセットします。

```bash
# サービスを停止し、データベースボリュームを削除
docker compose down -v

# 再起動
docker compose up -d

# データベース準備完了まで待機
sleep 5

# マイグレーション実行
docker compose exec api alembic upgrade head

# マイグレーション状態の確認
docker compose exec api alembic current
# 最新のリビジョンID（例: a1b2c3d4e5f6）が表示されればOK
```

### A.2 ゲームとクラブの作成

#### A.2.1 環境変数の設定

実際のID値を環境変数に保存しておくと便利です。

```bash
# これらの値は後のステップで取得します
export GAME_ID=""
export SEASON_ID=""
export CLUB_TOK=""  # FC東京
export CLUB_NAG=""  # FC名古屋
```

#### A.2.2 ゲーム作成（GMとして）

```bash
curl -X POST http://localhost:8000/api/games \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"テストリーグ"}' | python3 -m json.tool
```

**レスポンス例**:
```json
{
  "id": "44a889ca-eb9f-4d21-8bee-1ea8064694ef",
  "name": "テストリーグ",
  "status": "active",
  "created_at": "2026-01-03T12:49:20.935269"
}
```

`id` フィールドの値を `GAME_ID` に設定:
```bash
export GAME_ID="44a889ca-eb9f-4d21-8bee-1ea8064694ef"
```

#### A.2.3 クラブの作成

```bash
# FC東京を作成
curl -X POST http://localhost:8000/api/games/$GAME_ID/clubs \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"FC東京","short_name":"TOK"}' | python3 -m json.tool

# FC名古屋を作成
curl -X POST http://localhost:8000/api/games/$GAME_ID/clubs \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"FC名古屋","short_name":"NAG"}' | python3 -m json.tool
```

**レスポンス例（FC東京）**:
```json
{
  "id": "586c6f92-ea66-4ebf-899a-ef3772333011",
  "name": "FC東京",
  "short_name": "TOK",
  "game_id": "44a889ca-eb9f-4d21-8bee-1ea8064694ef"
}
```

各クラブの `id` を環境変数に設定:
```bash
export CLUB_TOK="586c6f92-ea66-4ebf-899a-ef3772333011"
export CLUB_NAG="b7d7d964-e72d-450d-bff3-19522e5c7b3f"
```

#### A.2.4 クラブオーナーの設定

**重要**: `role` には `club_owner` を指定してください（`owner` ではありません）。

```bash
# FC東京のオーナーを設定
curl -X POST http://localhost:8000/api/games/$GAME_ID/memberships \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"email":"owner_tokyo@example.com","role":"club_owner","club_id":"'"$CLUB_TOK"'"}'

# FC名古屋のオーナーを設定
curl -X POST http://localhost:8000/api/games/$GAME_ID/memberships \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"email":"owner_nagoya@example.com","role":"club_owner","club_id":"'"$CLUB_NAG"'"}'
```

**レスポンス例**:
```json
{"id": "e4f049e3-ff6e-4c37-bf1a-0436b598acd3"}
```

#### A.2.5 シーズンの作成

```bash
curl -X POST http://localhost:8000/api/seasons/games/$GAME_ID \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"year_label":"2025"}' | python3 -m json.tool
```

**レスポンス例**:
```json
{
  "id": "dc091eb3-2604-46eb-a3c5-f3c4524149a0",
  "game_id": "44a889ca-eb9f-4d21-8bee-1ea8064694ef",
  "season_number": 1,
  "year_label": "2025",
  "status": "running"
}
```

`id` を環境変数に設定:
```bash
export SEASON_ID="dc091eb3-2604-46eb-a3c5-f3c4524149a0"
```

#### A.2.6 試合日程の生成

**重要**: このエンドポイントには `Content-Type: application/json` ヘッダーが必須です。

```bash
curl -X POST http://localhost:8000/api/seasons/$SEASON_ID/fixtures/generate \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{}'
```

**レスポンス例**:
```json
{"fixtures": 10}
```

これで8月〜5月の10試合分の対戦表が生成されました。

### A.3 CLI設定ファイルの作成

3つの設定ファイルを作成します。環境変数を使用して自動的にIDを埋め込みます。

#### A.3.1 CLI依存パッケージのインストール

```bash
cd /path/to/Club_Management_game/apps/cli
pip install -r requirements.txt
```

#### A.3.2 GM用設定

```bash
mkdir -p ~/.club-game
cat > ~/.club-game/config << EOF
{
  "base_url": "http://localhost:8000",
  "user_email": "gm@example.com",
  "season_id": "$SEASON_ID",
  "club_id": null
}
EOF
```

#### A.3.3 FC東京オーナー用設定

```bash
cat > ~/.club-game/config.tokyo << EOF
{
  "base_url": "http://localhost:8000",
  "user_email": "owner_tokyo@example.com",
  "season_id": "$SEASON_ID",
  "club_id": "$CLUB_TOK"
}
EOF
```

#### A.3.4 FC名古屋オーナー用設定

```bash
cat > ~/.club-game/config.nagoya << EOF
{
  "base_url": "http://localhost:8000",
  "user_email": "owner_nagoya@example.com",
  "season_id": "$SEASON_ID",
  "club_id": "$CLUB_NAG"
}
EOF
```

### A.4 CLI動作確認

```bash
# FC東京オーナーとして現在のターン状況を確認
python -m apps.cli.main --config ~/.club-game/config.tokyo show current_input
```

**期待される出力**:
```
Turn:
season_number | month_index | month_name | decision_state | committed_at
--------------+-------------+------------+----------------+-------------
1             | 1           | Aug        | draft          | -           
Available inputs this turn:
- sales_expense
- promo_expense
- hometown_expense
- sales_allocation_new
```

これでゲームのセットアップが完了しました！

---

## Appendix B: 旧セットアップ例（参考）

### B.1 前提条件

以下の3つの準備が完了している必要があります。

#### 1. Docker Composeでapi/dbが起動済み

プロジェクトルートディレクトリで以下を実行します。

```bash
cd /path/to/Club_Management_game

# コンテナをビルド・起動（初回のみビルドが必要）
docker compose up -d --build

# 起動確認
docker compose ps
```

期待される出力（例）:
```
NAME                    STATUS
club_management_game-api-1   Up
club_management_game-db-1    Up
```

APIが正常に起動しているか確認:
```bash
curl http://localhost:8000/health
# または
curl http://localhost:8000/docs  # Swagger UIが表示されれば成功
```

#### 2. マイグレーション完了済み

データベーススキーマを最新状態に更新します。

```bash
# マイグレーションを実行
docker compose exec api alembic upgrade head
```

成功時の出力例:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, Initial tables
INFO  [alembic.runtime.migration] Running upgrade 0001_initial -> 0002_pr1_skeleton, PR1 skeleton
...
```

マイグレーション状態の確認:
```bash
docker compose exec api alembic current
```

#### 3. 基本的なCLIセットアップ完了

Python仮想環境を作成し、CLI依存パッケージをインストールします。

```bash
# プロジェクトルートに移動
cd /path/to/Club_Management_game

# 仮想環境を作成（未作成の場合）
python -m venv .venv

# 仮想環境を有効化
source .venv/bin/activate   # macOS/Linux
# または
.venv\Scripts\activate      # Windows

# CLI依存パッケージをインストール
pip install -r apps/cli/requirements.txt
```

インストール確認:
```bash
python -m apps.cli.main help
```

期待される出力:
```
Usage: python -m apps.cli.main [OPTIONS] COMMAND [ARGS]...

Options:
  --config-path PATH  Path to config file (default: ~/.club-game/config)
  ...

Commands:
  commit  Commit (finalize) current turn decision.
  game    Game-level commands (GM only).
  gm      Commands for game masters to manage turns.
  ...
```

### A.2 初期セットアップ（GMとして実行）

#### ステップ1: ゲーム作成

```bash
curl -X POST http://localhost:8000/api/games \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"テストリーグ"}'
```

レスポンス例:
```json
{"id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "name": "テストリーグ", ...}
```

→ `game_id` をメモ

#### ステップ2: 2つのクラブを作成

```bash
# クラブ1: FCアルファ
curl -X POST http://localhost:8000/api/games/<game_id>/clubs \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"FCアルファ","short_name":"ALP"}'

# クラブ2: FCベータ
curl -X POST http://localhost:8000/api/games/<game_id>/clubs \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"name":"FCベータ","short_name":"BET"}'
```

→ それぞれの `club_id` をメモ（例: `club_alpha_id`, `club_beta_id`）

#### ステップ3: シーズン作成

```bash
curl -X POST http://localhost:8000/api/games/<game_id>/seasons \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: gm@example.com' \
  -d '{"year_label":"2025"}'
```

→ `season_id` をメモ

#### ステップ4: 試合日程生成

```bash
curl -X POST http://localhost:8000/api/seasons/<season_id>/fixtures/generate \
  -H 'X-User-Email: gm@example.com' \
  -d '{}'
```

#### ステップ5: 2つのクラブオーナー用メンバーシップを登録

```bash
# クラブ1のオーナーを登録
python -m apps.cli.main game add-member \
  --game-id <game_id> \
  --email owner_alpha@example.com \
  --role club_owner \
  --club-id <club_alpha_id> \
  --user-email gm@example.com

# クラブ2のオーナーを登録
python -m apps.cli.main game add-member \
  --game-id <game_id> \
  --email owner_beta@example.com \
  --role club_owner \
  --club-id <club_beta_id> \
  --user-email gm@example.com
```

### A.3 CLI設定ファイルの準備

3つのconfigファイルを作成します（GM用、クラブ1用、クラブ2用）。

```bash
mkdir -p ~/.club-game
```

#### GM用設定 (`~/.club-game/config-gm`)

```bash
cat > ~/.club-game/config-gm << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "gm@example.com",
  "game_id": "<game_id>",
  "season_id": "<season_id>"
}
EOF
```

#### クラブ1（FCアルファ）用設定 (`~/.club-game/config-alpha`)

```bash
cat > ~/.club-game/config-alpha << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "owner_alpha@example.com",
  "game_id": "<game_id>",
  "season_id": "<season_id>",
  "club_id": "<club_alpha_id>"
}
EOF
```

#### クラブ2（FCベータ）用設定 (`~/.club-game/config-beta`)

```bash
cat > ~/.club-game/config-beta << 'EOF'
{
  "base_url": "http://localhost:8000",
  "user_email": "owner_beta@example.com",
  "game_id": "<game_id>",
  "season_id": "<season_id>",
  "club_id": "<club_beta_id>"
}
EOF
```

### A.4 エイリアス設定（推奨）

毎回 `--config-path` を指定するのは面倒なので、シェルエイリアスを設定すると便利です。

```bash
# ~/.zshrc または ~/.bashrc に追加
alias cli-gm='python -m apps.cli.main --config-path ~/.club-game/config-gm'
alias cli-alpha='python -m apps.cli.main --config-path ~/.club-game/config-alpha'
alias cli-beta='python -m apps.cli.main --config-path ~/.club-game/config-beta'
```

設定後、シェルを再読み込み:

```bash
source ~/.zshrc
```

### A.5 テストプレイの流れ（1ターン分）

以下のセクションでは、エイリアスを使用した例を示します。エイリアスを設定していない場合は `cli-gm` を `python -m apps.cli.main --config-path ~/.club-game/config-gm` に置き換えてください。

#### ターン1: 8月

##### 1. GMがターンを開く

```bash
cli-gm gm open
```

出力例: `Turn opened (id=xxx).`

##### 2. クラブ1（FCアルファ）が入力

```bash
# 現在の入力状況を確認
cli-alpha show current_input

# 月次入力を行う（8月は四半期開始月なのでrho_newも入力可能）
cli-alpha input \
  --sales-expense 5000000 \
  --promo-expense 3000000 \
  --hometown-expense 2000000 \
  --rho-new 0.3

# 入力内容を確認
cli-alpha view

# 入力を確定
cli-alpha commit -y
```

##### 3. クラブ2（FCベータ）が入力

```bash
# 月次入力を行う
cli-beta input \
  --sales-expense 4000000 \
  --promo-expense 2500000 \
  --hometown-expense 1500000 \
  --rho-new 0.4

# 入力を確定
cli-beta commit -y
```

##### 4. GMが入力を締め切り

```bash
cli-gm gm lock
```

##### 5. GMがターンを解決（試合・財務処理）

```bash
cli-gm gm resolve
```

##### 6. 結果を確認

```bash
# 順位表
cli-alpha show table

# 試合結果
cli-alpha show match

# ファン指標（両クラブ比較）
cli-gm show fan_indicator --from 2025-08 --to 2025-08
```

##### 7. 各クラブがACKする（必須）

resolve後は全クラブがACKしないとadvanceできません。ターンIDを取得し、クラブごとに `ack:true` を送ります。

```bash
# ターンID取得（GMメール）
TURN_ID=$(curl -s -H 'X-User-Email: gm@example.com' \
  "http://localhost:8000/api/turns/seasons/<season_id>/current" | jq -r .id)

# クラブ1がACK
curl -s -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: owner1@example.com' \
  "http://localhost:8000/api/turns/${TURN_ID}/ack" \
  -d '{"club_id":"<club_id_1>","ack":true}'

# クラブ2がACK
curl -s -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: owner2@example.com' \
  "http://localhost:8000/api/turns/${TURN_ID}/ack" \
  -d '{"club_id":"<club_id_2>","ack":true}'
```

##### 8. GMが次ターンへ進行

```bash
cli-gm gm advance
```

### A.6 複数ターンを連続実行

以下のスクリプトで複数ターンを自動化できます（参考）:

```bash
#!/bin/bash
# simple_demo.sh - 3ターン分のデモ

for month in 8 9 10; do
  echo "=== ターン開始: ${month}月 ==="
  
  # GMがターンを開く
  cli-gm gm open
  
  # クラブ1が入力・確定
  cli-alpha input --sales-expense 5000000 --promo-expense 3000000 --hometown-expense 2000000
  cli-alpha commit -y
  
  # クラブ2が入力・確定
  cli-beta input --sales-expense 4000000 --promo-expense 2500000 --hometown-expense 1500000
  cli-beta commit -y
  
  # GMがlock → resolve → advance
  cli-gm gm lock
  cli-gm gm resolve
  cli-gm gm advance
  
  echo "=== ${month}月 完了 ==="
done

# 最終結果確認
cli-alpha show table
```

### A.7 入力条件の月別まとめ

| 月 | month_index | 入力可能項目 |
|----|-------------|-------------|
| 8月 | 1 | 通年項目 + rho_new（四半期開始） |
| 9月 | 2 | 通年項目のみ |
| 10月 | 3 | 通年項目のみ |
| 11月 | 4 | 通年項目 + rho_new（四半期開始）+ next_home_promo |
| 12月 | 5 | 通年項目 + additional_reinforcement（冬移籍） |
| 1月 | 6 | 通年項目のみ |
| 2月 | 7 | 通年項目 + rho_new（四半期開始）+ next_home_promo |
| 3月 | 8 | 通年項目のみ |
| 4月 | 9 | 通年項目のみ |
| 5月 | 10 | 通年項目 + rho_new（四半期開始）+ next_home_promo |

**通年項目**: `sales_expense`, `promo_expense`, `hometown_expense`

### A.8 データの確認

#### 各クラブの財務状況

```bash
# クラブ1の財務
curl http://localhost:8000/api/clubs/<club_alpha_id>/finance \
  -H 'X-User-Email: owner_alpha@example.com'

# クラブ2の財務
curl http://localhost:8000/api/clubs/<club_beta_id>/finance \
  -H 'X-User-Email: owner_beta@example.com'
```

#### DB直接確認（デバッグ用）

```bash
docker compose exec db psql -U postgres -d club_game -c "SELECT * FROM clubs;"
docker compose exec db psql -U postgres -d club_game -c "SELECT * FROM memberships;"
```

---

## 参考資料

- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) - 実装ロードマップ
- [apps/cli/docs/INPUT_SPEC.md](apps/cli/docs/INPUT_SPEC.md) - 入力条件仕様
- [v1Spec_test.md](v1Spec_test.md) - ゲーム仕様書

---

**最終更新日**: 2025年12月
