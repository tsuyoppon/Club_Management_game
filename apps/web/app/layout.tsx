import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'J-League Club Management Multiplayer',
  description: 'Role-aware multiplayer club management console',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
