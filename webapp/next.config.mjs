/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  // Same-origin proxies to the local services so the browser never does a
  // cross-origin fetch (predict service has no CORS; phones/tunnels see ONE
  // origin). Client code targets /p5/* via NEXT_PUBLIC_P5_BASE default.
  async rewrites() {
    const p5 = process.env.P5_UPSTREAM || 'http://127.0.0.1:8099';
    const boards = process.env.BOARD_UPSTREAM || 'http://127.0.0.1:8098';
    return [
      { source: '/p5/:path*', destination: `${p5}/:path*` },
      { source: '/boards/:path*', destination: `${boards}/:path*` },
    ];
  },
};

export default nextConfig;
