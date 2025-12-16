const http = require('http');

const html = `<!doctype html>
<html lang="ja">
<head><meta charset="utf-8"><title>Jリーグ クラブ経営トレーニングゲーム</title></head>
<body><h1>Jリーグ クラブ経営トレーニングゲーム</h1><p>Next.js UI scaffold placeholder. Static preview for offline mode.</p></body>
</html>`;

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(html);
});

const port = process.env.PORT || 3000;
server.listen(port, '0.0.0.0', () => {
  console.log(`Static web server running on ${port}`);
});
