# Rebuild, Launch, and Start New Game Runbook

この手順は、最新コードで Web Multiplayer を再ビルドし、既存サーバーを停止してから新しく起動し、新規ゲームを開始状態まで進めるためのものです。

## 前提

- Docker Desktop が起動していること。
- リポジトリルートで実行すること。
- `curl` と `jq` が使えること。
- DB データを残す場合は `down` を使う。DB も初期化する場合だけ `down -v` を使う。

```bash
cd /Users/scide_furusawa/Documents/Club_Management_game
```

## 既存サーバーの停止

通常はこのプロジェクトの Compose スタックを停止する。

```bash
docker compose --profile web down
```

DB データも破棄して完全に最初から検証する場合のみ、以下を使う。

```bash
docker compose --profile web down -v
```

Codex 環境では Docker daemon への接続がサンドボックスで拒否されることがある。その場合は、同じ `docker compose` コマンドを権限付きで再実行する。

## 最新状態で再ビルドして起動

```bash
docker compose --profile web up -d --build
```

起動状態と公開ポートを確認する。

```bash
docker compose --profile web ps
```

期待する公開ポート:

- Web: `0.0.0.0:3000->3000/tcp`
- API: `0.0.0.0:8000->8000/tcp`
- DB: `0.0.0.0:5432->5432/tcp`

## DB マイグレーション

```bash
docker compose exec -T api alembic upgrade head
```

## 疎通確認

API:

```bash
curl -sS http://localhost:8000/api/health
```

期待値:

```json
{"status":"ok","app":"club-management-api"}
```

Web:

```bash
curl -sS -I http://localhost:3000
```

`HTTP/1.1 200 OK` が返ればよい。

## LAN URL の確認

macOS の Wi-Fi では通常 `en0` を確認する。

```bash
ipconfig getifaddr en0
```

有線 LAN や環境差で取れない場合は候補を確認する。

```bash
ifconfig | grep "inet "
```

提示する URL は以下。

```text
http://localhost:3000
http://<host-lan-ip>:3000
```

API も提示する場合:

```text
http://localhost:8000
http://<host-lan-ip>:8000
```

他端末から Web に接続できない場合は、ホスト OS、ルーター、セキュリティソフトが 3000 番ポートを遮断していないか確認する。

## 新規ゲームを API で開始する

Web UI の通常フローでは、ホストがルームを作成し、参加者が招待コードで参加し、各クラブを claim して ready にした後、ホストが開始する。

自動で新規ゲームを開始状態まで作る場合は、以下の例を使う。この例では 2 クラブ、2 プレイヤーのゲームを作成し、初月ターンが入力受付状態になる。

```bash
set -eu

rm -f /tmp/club-game-host.cookies /tmp/club-game-player2.cookies

room_json=$(curl -sS \
  -c /tmp/club-game-host.cookies \
  -b /tmp/club-game-host.cookies \
  -H 'Content-Type: application/json' \
  -d '{
    "display_name": "Host GM",
    "room_name": "Latest Build Playtest",
    "club_names": ["Tokyo Training FC", "Osaka Workshop SC"]
  }' \
  http://localhost:8000/api/rooms)

echo "$room_json" | jq '{id, game_id, status, invite_code, clubs: [.clubs[] | {id,name,ready,claimed_by_name}]}'

room_id=$(echo "$room_json" | jq -r '.id')
invite_code=$(echo "$room_json" | jq -r '.invite_code')
club1=$(echo "$room_json" | jq -r '.clubs[0].id')
club2=$(echo "$room_json" | jq -r '.clubs[1].id')

curl -sS \
  -c /tmp/club-game-host.cookies \
  -b /tmp/club-game-host.cookies \
  -X POST \
  "http://localhost:8000/api/rooms/$room_id/clubs/$club1/claim" >/tmp/club-game-host-claim.json

curl -sS \
  -c /tmp/club-game-host.cookies \
  -b /tmp/club-game-host.cookies \
  -X PATCH \
  -H 'Content-Type: application/json' \
  -d '{"ready":true}' \
  "http://localhost:8000/api/rooms/$room_id/memberships/me/ready" >/tmp/club-game-host-ready.json

curl -sS \
  -c /tmp/club-game-player2.cookies \
  -b /tmp/club-game-player2.cookies \
  -H 'Content-Type: application/json' \
  -d '{"display_name":"Player Two"}' \
  "http://localhost:8000/api/rooms/$invite_code/join" >/tmp/club-game-player2-join.json

curl -sS \
  -c /tmp/club-game-player2.cookies \
  -b /tmp/club-game-player2.cookies \
  -X POST \
  "http://localhost:8000/api/rooms/$room_id/clubs/$club2/claim" >/tmp/club-game-player2-claim.json

curl -sS \
  -c /tmp/club-game-player2.cookies \
  -b /tmp/club-game-player2.cookies \
  -X PATCH \
  -H 'Content-Type: application/json' \
  -d '{"ready":true}' \
  "http://localhost:8000/api/rooms/$room_id/memberships/me/ready" >/tmp/club-game-player2-ready.json

start_json=$(curl -sS \
  -c /tmp/club-game-host.cookies \
  -b /tmp/club-game-host.cookies \
  -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"year_label\":\"$(date +%Y)\"}" \
  "http://localhost:8000/api/rooms/$room_id/start")

echo "$start_json" | jq '{
  season_id,
  room: {
    id: .room.id,
    game_id: .room.game_id,
    status: .room.status,
    invite_code: .room.invite_code,
    clubs: [.room.clubs[] | {name, ready, claimed_by_name}]
  }
}'
```

注意:

- API で作成したホスト/プレイヤーのブラウザセッションは `/tmp/club-game-*.cookies` に保持される。
- 通常ブラウザでそのまま同じホストとして入るには、その Cookie をブラウザに移す必要があるため、実プレイでは Web UI からルーム作成する方が自然。
- API 自動作成は、起動確認、デモデータ作成、疎通検証に向いている。

## 開始済みゲームの確認

上のスクリプトで得た `game_id` を使って確認する。

```bash
curl -sS \
  -b /tmp/club-game-host.cookies \
  "http://localhost:8000/api/games/<game_id>/play-state" \
  | jq '{room, season, turn, clubs}'
```

開始直後の期待状態:

- `room.status` が `active`
- `season.status` が `running`
- `turn.month_name` が `Aug`
- `turn.state` が `collecting`

## 最終報告に含める情報

起動完了後は、少なくとも以下を提示する。

- Web local URL: `http://localhost:3000`
- Web LAN URL: `http://<host-lan-ip>:3000`
- API local URL: `http://localhost:8000`
- API LAN URL: `http://<host-lan-ip>:8000`
- Invite code
- Room ID
- Game ID
- Season ID
- 現在ターンと state

## トラブルシュート

`curl: Failed to connect to localhost port 3000/8000`:

- `docker compose --profile web ps` でコンテナが `Up` か確認する。
- `docker compose logs --tail=120 web` と `docker compose logs --tail=120 api` を見る。
- Codex 環境ではホストネットワークアクセスが制限されることがあるため、権限付きで再実行する。

`permission denied while trying to connect to the docker API`:

- Docker daemon へのアクセス権限がない。Codex では `docker compose` を権限付きで再実行する。

他端末から LAN URL にアクセスできない:

- ホストと端末が同じ LAN にいるか確認する。
- `ipconfig getifaddr en0` の IP が現在のネットワークのものか確認する。
- macOS ファイアウォール、ルーター、セキュリティソフトが 3000 番ポートを遮断していないか確認する。
