# LAN Playtest Runbook

この手順は、Docker Desktop が起動しているホストPC上で Web Multiplayer V1 を起動し、同じLAN上の複数端末からブラウザで接続して検証するためのものです。初期版は社内/小規模対戦向けであり、公開インターネット向けのTLS、外部認証、監視、バックアップ、濫用対策は対象外です。

## 起動

```bash
docker compose --profile web up -d --build
docker compose exec api alembic upgrade head
```

起動後、ホストPC自身では以下を開きます。

```text
http://localhost:3000
```

API の疎通確認は以下です。

```bash
curl http://localhost:8000/api/health
```

## LAN 参加URL

他端末から参加する場合は、ホストPCのLAN IPを使います。

```text
http://<host-lan-ip>:3000
```

macOS でLAN IPを確認する例:

```bash
ipconfig getifaddr en0
```

有線LANなどで `en0` に出ない場合は、以下で候補を確認します。

```bash
ifconfig | grep "inet "
```

参加者はブラウザでLAN参加URLを開き、ホストが画面に表示した招待コードを入力します。

## 検証シナリオ

1. ホストがルームを作成し、「ホスト兼プレーヤー」または「専任ホスト」を選ぶ。
2. 参加者が招待コードでルームへ入る。専任ホストの場合は、ホストとは別にクラブ数と同数のブラウザを用意する。
3. 各クラブ担当者がクラブを担当し、ready にする。専任ホストにはクラブ選択・ready操作が表示されないことを確認する。
4. ホストがゲームを開始する。
5. 各クラブがターン入力を保存し、入力を確定する。
6. ホストが `lock`、`resolve` を実行する。
7. 各クラブが結果を確認して `ack` する。
8. ホストが `advance` し、次ターンが入力受付になることを確認する。

両モードをそれぞれ確認します。専任ホストでは、ホストのターン入力欄が表示されず、公開進捗とホスト操作だけが利用できること、終了後は全クラブの結果を閲覧できることも確認します。

## 停止

```bash
docker compose --profile web down
```

DBデータも破棄して最初から検証する場合のみ、以下を使います。

```bash
docker compose --profile web down -v
```

## 既知の注意点

- ブラウザセッションは HttpOnly Cookie で保持されます。同じブラウザで別プレイヤーとして入り直す場合は、別ブラウザまたはプライベートウィンドウを使ってください。
- Web は短周期ポーリングです。別端末の操作反映には数秒かかることがあります。
- API テストでは Pydantic v2 と httpx の deprecation warning が出ますが、現時点では既存コード由来の警告です。
- ルーターやOSファイアウォールがホストPCの 3000 番ポートを遮断している場合、他端末から接続できません。
