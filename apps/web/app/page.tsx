import Link from 'next/link';

const FeatureList = () => (
  <ul className="list">
    <li>FastAPI backend with PostgreSQL via Docker Compose</li>
    <li>Next.js App Router UI scaffold</li>
    <li>Alembic migrations ready for core models</li>
    <li>Seeded RNG and game logic coming in follow-up PRs</li>
  </ul>
);

export default function Home() {
  return (
    <main className="container">
      <h1>Jリーグ クラブ経営トレーニングゲーム</h1>
      <p>このリポジトリは社内研修用のターン制クラブ経営シミュレーションのプロトタイプです。</p>
      <FeatureList />
      <p>
        APIドキュメント: <Link href="http://localhost:8000/docs">http://localhost:8000/docs</Link>
      </p>
    </main>
  );
}
