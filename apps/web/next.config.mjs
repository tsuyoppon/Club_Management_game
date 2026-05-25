/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const apiOrigin = process.env.API_PROXY_ORIGIN || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
