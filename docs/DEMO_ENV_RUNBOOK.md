# デモ環境ワンコマンド起動 Runbook

`docs/DEMO_PLAY_MANUAL.md` の手順を、当日すぐ確認できる Web Multiplayer デモ用にまとめた runbook です。

## 最短手順

リポジトリ直下で以下を実行します。

```bash
./scripts/demo_env.py up --reset
```

このコマンドで以下をまとめて実行します。

- `docker compose --profile web up -d --build`
- API ヘルスチェック待機
- `alembic upgrade head`
- Web 起動待機
- Web Multiplayer API でルーム/ゲーム作成
- ホストとプレイヤーを作成
- 各クラブを claim
- 全クラブを ready
- ルームを start
- `.demo/demo-state.json` と `.demo/cookies/*.cookies` に当日の操作情報を保存

起動後に表示される `Web` URL を開きます。

```text
http://localhost:3000
```

同じ LAN 上の別端末から接続する場合は、スクリプト出力の `Web LAN` URL を使います。

## 生成されるデモ

デフォルトでは以下の 2 クラブを持つ開始済みルームを作ります。

| 役割 | 表示名 | クラブ |
| --- | --- | --- |
| ホスト | Host GM | Tokyo Training FC |
| プレイヤー | Player Two | Osaka Workshop SC |

クラブ数やルーム名を変える場合:

```bash
./scripts/demo_env.py up --reset \
  --room-name "Sales Training Demo" \
  --clubs "Tokyo Training FC" "Osaka Workshop SC" "Nagoya Demo AC"
```

開始直前の lobby 状態で止めたい場合:

```bash
./scripts/demo_env.py up --reset --lobby-only
```

## 状態確認

```bash
./scripts/demo_env.py status
```

開始済みルームでは、現在シーズン、ターン、各クラブの commit/ack 状態を表示します。

保存先:

```text
.demo/demo-state.json
.demo/cookies/host.cookies
.demo/cookies/player2.cookies
```

Cookie jar は、スクリプトが Web API の resume/archive/delete を実行するために使います。

## リセット

再実演用に、既存の Web API の archive/delete フローを使って前回デモを削除し、新しいデモを作り直します。

```bash
./scripts/demo_env.py reset
```

DB volume ごと完全に初期化したい場合だけ、hard reset を使います。

```bash
./scripts/demo_env.py reset --hard
```

`--hard` は `docker compose --profile web down -v` を実行するため、デモ以外の保存済みゲームも削除されます。

## アーカイブ

当日中に「通常の再開一覧から隠す」状態にしたい場合:

```bash
./scripts/demo_env.py archive
```

アーカイブ後も、ホストのブラウザでは Web のアーカイブ一覧から削除確認へ進めます。スクリプトで完全削除する場合:

```bash
./scripts/demo_env.py delete
```

## 停止

DB を残してコンテナだけ止めます。

```bash
./scripts/demo_env.py down
```

または:

```bash
docker compose --profile web down
```

## Web UI での resume/archive について

Web Multiplayer V1 の resume は HttpOnly Cookie に紐づきます。同じブラウザで作った/参加したルームは、トップ画面の再開一覧から戻れます。ホストは active/lobby のルームを archive し、archive 一覧から完全削除できます。

スクリプトで作成したデモ用ホスト/プレイヤーの Cookie は `.demo/cookies/` に保存され、通常ブラウザには自動投入されません。そのため、スクリプト作成済みルームの resume/archive/delete は `./scripts/demo_env.py status|archive|delete|reset` で扱います。実プレイヤーのブラウザセッションをそのまま resume させたい当日は、Docker 起動だけを先に行い、Web UI からルーム作成/参加する運用が自然です。

```bash
./scripts/demo_env.py up --no-seed
```

その後、ホストが `http://localhost:3000` または `http://<host-lan-ip>:3000` でルームを作成します。

## トラブルシューティング

API が起動しない場合:

```bash
docker compose logs api
docker compose logs db
```

Web が見えない場合:

```bash
docker compose logs web
curl http://localhost:8000/api/health
```

LAN 端末から接続できない場合:

- ホストPCのファイアウォールで 3000 番ポートが許可されているか確認します。
- 同一 Wi-Fi/LAN にいるか確認します。
- スクリプト出力の `Web LAN` URL を使います。
