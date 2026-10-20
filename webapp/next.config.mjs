import { readdirSync, readFileSync } from 'node:fs';

const SNAPSHOT = process.env.NEXT_PUBLIC_DATA_MODE === 'snapshot';
// Mirrors output.basePath below -- read by lib/fetchHonest.ts to prefix the
// plain fetch() calls to /demo-data/*.json that Next's basePath rewriting
// does not touch (it only rewrites Link/Image/router navigation).
if (SNAPSHOT) process.env.NEXT_PUBLIC_BASE_PATH = '/court-vision';

// The baked files, read at build time and inlined for lib/fetchHonest.ts: a GET
// whose /demo-data/*.json was never exported degrades to the honest Unavailable
// sentinel without a network round-trip (no 404 in the console). Left unset when
// the directory is missing so the client falls back to plain fetching.
function snapshotFiles() {
  if (!SNAPSHOT) return null;
  try {
    const names = readdirSync(new URL('./public/demo-data/', import.meta.url)).filter((f) => f.endsWith('.json'));
    return names.length ? JSON.stringify(names) : null;
  } catch {
    return null;
  }
}
const SNAPSHOT_FILES = snapshotFiles();

// The games whose detail pages the export actually contains (manifest.games is
// what generateStaticParams builds). Client lists link only those; the rest
// render as plain cards instead of links that would 404.
function snapshotGames() {
  if (!SNAPSHOT) return null;
  try {
    const manifest = JSON.parse(readFileSync(new URL('./public/demo-data/manifest.json', import.meta.url), 'utf8'));
    const games = (manifest.games || []).map((g) => `${g.sport}/${g.game_id}`);
    return games.length ? JSON.stringify(games) : null;
  } catch {
    return null;
  }
}
const SNAPSHOT_GAMES = snapshotGames();

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Cap build workers. The default (cores - 1 = 11 here, about 5 GB; two still took 1.5 GB) starves the
  // paper-desk recorder that shares this 16 GB box. Override: NEXT_BUILD_CPUS=<n>.
  experimental: { cpus: Number(process.env.NEXT_BUILD_CPUS) || 1 },
  env: {
    ...(SNAPSHOT_FILES ? { NEXT_PUBLIC_SNAPSHOT_FILES: SNAPSHOT_FILES } : {}),
    ...(SNAPSHOT_GAMES ? { NEXT_PUBLIC_SNAPSHOT_GAMES: SNAPSHOT_GAMES } : {}),
  },
  ...(SNAPSHOT
    ? {
        // Static demo build for GitHub Pages project site (neeljshah/court-vision).
        // No rewrites (no backend at build time) -- fetchHonest resolves every
        // call to a baked /demo-data/*.json instead. See lib/fetchHonest.ts.
        output: 'export',
        basePath: '/court-vision',
        assetPrefix: '/court-vision/',
        // Pages serves foo/index.html at both /foo and /foo/ -- without this,
        // shared links with a trailing slash 404 (foo.html only maps to /foo).
        trailingSlash: true,
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
