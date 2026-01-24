# CLIコマンド一覧（GM/プレイヤー）

本ドキュメントは、`club-game` CLIで利用できるコマンドとオプションをコードベースから網羅的に整理したものです。GM専用コマンドとプレイヤー（クラブ運営者/閲覧者）向けコマンドを分けて記載します。

## 1. 共通（全ロール共通のトップレベル）

### グローバルオプション（全コマンド共通）
`club-game`の全サブコマンドに共通で指定可能です。

- `--config-path <PATH>`: 設定ファイルパスを指定（未指定時は `~/.club-game/config`）。
- `--base-url <URL>`: APIのベースURLを上書き。
- `--user-email <EMAIL>`: リクエストヘッダ `X-User-Email` を上書き。
- `--game-id <UUID>`: デフォルトのゲームID。
- `--season-id <UUID>`: デフォルトのシーズンID。
- `--club-id <UUID>`: デフォルトのクラブID。
- `--timeout <SECONDS>`: HTTPタイムアウト秒数（デフォルト: 10.0）。
- `--verbose`: デバッグ用にHTTPステータスを表示。

### `help`
CLIまたは特定コマンドのヘルプを表示します。

- `club-game help` : CLI全体のヘルプ。
- `club-game help <command>` : 指定コマンドのヘルプ。
- `club-game help <command> <subcommand>` : 指定サブコマンドのヘルプ。

## 2. GM専用コマンド

### `gm`（ターン管理）
ゲームマスター向けのターン制御コマンドです。

- `club-game gm open`
  - `--turn-id <UUID>`: 対象ターンID（省略時は現在のシーズンのターン）。
  - `--season-id <UUID>`: `--turn-id`未指定時のシーズンID（未指定なら設定ファイル）。
  - `--json-output`: JSONをそのまま出力。
  - **用途**: ターンを開放（意思決定の受付開始）。

- `club-game gm lock`
  - `--turn-id <UUID>`
  - `--season-id <UUID>`
  - `--json-output`
  - **用途**: 意思決定が揃ったターンをロック。

- `club-game gm resolve`
  - `--turn-id <UUID>`
  - `--season-id <UUID>`
  - `--json-output`
  - **用途**: ロック済みターンを解決（シミュレーション実行）。

- `club-game gm advance`
  - `--turn-id <UUID>`
  - `--season-id <UUID>`
  - `--json-output`
  - **用途**: ACK完了後に次ターンへ進行。

### `game`（ゲーム管理 / GMのみ）

- `club-game game add-member`
  - `--game-id <UUID>`: ゲームID（未指定時は設定ファイル）。
  - `--email <EMAIL>`: 追加するユーザーのメール（必須）。
  - `--display-name <NAME>`: 表示名。
  - `--role <gm|club_owner|club_viewer>`: 付与するロール（必須）。
  - `--club-id <UUID>`: `club_owner` / `club_viewer` の場合は必須。
  - `--json-output`: JSONをそのまま出力。
  - **用途**: ゲームへのメンバー追加。

## 3. プレイヤー（クラブ運営者）向けコマンド

### `input`（意思決定入力 / ドラフト保存）

- `club-game input`
  - `--season-id <UUID>`: 対象シーズンID（未指定時は設定ファイル）。
  - `--club-id <UUID>`: 対象クラブID（未指定時は設定ファイル）。
  - `--sales-expense <DECIMAL>`: 営業費。
  - `--promo-expense <DECIMAL>`: プロモーション費。
  - `--hometown-expense <DECIMAL>`: 地元活動費。
  - `--next-home-promo <DECIMAL>`: 次月ホームプロモ（条件付き）。
  - `--additional-reinforcement <DECIMAL>`: 追加補強（12月のみ）。
  - `--reinforcement-budget <DECIMAL>`: 次シーズン補強予算（6月/7月のみ）。
  - `--rho-new <FLOAT>`: 新規スポンサー比率（0.0〜1.0、四半期開始月のみ）。
  - `--clear`: ローカルドラフトを削除。
  - `--json-output`: JSON出力。
  - **用途**: 月次の意思決定値をローカルドラフトとして保存。

### `commit`（意思決定の確定送信）

- `club-game commit`
  - `--season-id <UUID>`
  - `--club-id <UUID>`
  - `-y, --yes`: 確認プロンプトを省略。
  - `--json-output`
  - **用途**: 現在ターンの意思決定を確定送信。

### `view`（入力内容の簡易表示）
`show current_input`のエイリアスです。

- `club-game view`
  - `--season-id <UUID>`
  - `--club-id <UUID>`
  - `--json-output`

### `ack`（ターンのACK）
クラブ運営者またはGMが、解決済みターンを承認するためのコマンドです。

- `club-game ack`
  - `--turn-id <UUID>`: 対象ターンID（省略時は現在のシーズン）。
  - `--season-id <UUID>`: `--turn-id`未指定時に使用。
  - `--club-id <UUID>`: 対象クラブID（未指定時は設定ファイル）。
  - `-y, --yes`: 確認プロンプトを省略。
  - `--json-output`

### `staff`（スタッフ計画 / 5月のみ）

- `club-game staff plan`
  - `--role <sales|hometown|operations|promotion|administration|topteam|academy>`: スタッフ種別（必須）。
  - `--count <INT>`: 目標人数（1以上、必須）。
  - `--club-id <UUID>`
  - `--season-id <UUID>`
  - `--turn-id <UUID>`: 省略時は現在ターン。
  - `--json-output`

### `academy`（アカデミー / 5月のみ）

- `club-game academy budget`
  - `--annual-budget <INT>`: 年間予算（0以上、必須）。
  - `--club-id <UUID>`
  - `--season-id <UUID>`
  - `--turn-id <UUID>`
  - `--json-output`

### `show`（参照系コマンド）
読み取り専用の参照系コマンド群です。

- `club-game show match`（試合スケジュール）
  - `--season-id <UUID>`
  - `--club-id <UUID>`
  - `--month <YYYY-MM>`: 月指定。
  - `--month-index <1-12>`: 月インデックス指定。
  - `--json-output`

- `club-game show table`（順位表）
  - `--season-id <UUID>`
  - `--json-output`

- `club-game show final_standings`（クラブの最終順位履歴）
  - `--club-id <UUID>`
  - `--club-name <NAME>`: ゲーム内でのクラブ名。
  - `--json-output`

- `club-game show finance`（財務・台帳）
  - `--season-id <UUID>`
  - `--club-id <UUID>`
  - `--month-index <1-12>`
  - `--json-output`

- `club-game show tax`（税金情報）
  - `--season-id <UUID>`
  - `--club-id <UUID>`
  - `--json-output`

- `club-game show team_power`（チーム力開示）
  - `--season-id <UUID>`
  - `--json-output`

- `club-game show disclosure`（開示データ）
  - `--season-id <UUID>`
  - `--type <financial_summary|team_power_december|team_power_july>`: 開示種別（必須）。
  - `--json-output`

- `club-game show staff`（スタッフ構成）
  - `--club-id <UUID>`
  - `--json-output`

- `club-game show staff_history`（スタッフ履歴）
  - `--club-id <UUID>`
  - `--season-id <UUID>`: フィルタ。
  - `--from <YYYY-MM>`: 開始月。
  - `--to <YYYY-MM>`: 終了月。
  - `--json-output`

- `club-game show current_input`（現在の入力状態）
  - `--season-id <UUID>`
  - `--club-id <UUID>`
  - `--json-output`

- `club-game show history`（入力履歴）
  - `--season-id <UUID>`
  - `--club-id <UUID>`
  - `--from <YYYY-MM>`
  - `--to <YYYY-MM>`
  - `--json-output`

- `club-game show fan_indicator`（ファン指標）
  - `--club-id <UUID>`
  - `--club <ID>`: 互換用エイリアス。
  - `--season-id <UUID>`
  - `--from <YYYY-MM>`
  - `--to <YYYY-MM>`
  - `--json-output`

- `club-game show sponsor_status`（スポンサー状況）
  - `--club-id <UUID>`
  - `--season-id <UUID>`
  - `--pipeline`: パイプライン表示（デフォルト）。
  - `--next`: 次年度スポンサー情報を表示。
  - `--json-output`

## 4. 設定管理コマンド

### `config`

- `club-game config set-season`
  - `--game-id <UUID>`: 対象ゲームID（未指定時は設定ファイル）。
  - `--latest`: 最新の実行中シーズンを自動取得して `season_id` に設定。

