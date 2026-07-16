const SNAPSHOT = process.env.NEXT_PUBLIC_DATA_MODE === 'snapshot';
// Mirrors output.basePath below -- read by lib/fetchHonest.ts to prefix the
// plain fetch() calls to /demo-data/*.json that Next's basePath rewriting
// does not touch (it only rewrites Link/Image/router navigation).
if (SNAPSHOT) process.env.NEXT_PUBLIC_BASE_PATH = '/court-vision';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  ...(SNAPSHOT
    ? {
        // Static demo build for GitHub Pages project site (neeljshah/court-vision).
        // No rewrites (no backend at build time) -- fetchHonest resolves every
        // call to a baked /demo-data/*.json instead. See lib/fetchHonest.ts.
        output: 'export',
        basePath: '/court-vision',
        assetPrefix: '/court-vision/',
        images: { unoptimized: true },
      }
    : {
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
      }),
};

export default nextConfig;
