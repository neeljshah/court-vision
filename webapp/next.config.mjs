import { readdirSync, readFileSync } from 'node:fs';

const SNAPSHOT = process.env.NEXT_PUBLIC_DATA_MODE === 'snapshot';
// Mirrors output.basePath below -- read by lib/fetchHonest.ts to prefix the
// plain fetch() calls to /demo-data/*.json that Next's basePath rewriting
// does not touch (it only rewrites Link/Image/router navigation).
if (SNAPSHOT) process.env.NEXT_PUBLIC_BASE_PATH = '/court-vision';

// In a snapshot build the baked files ARE the data source, so an empty or missing
// public/demo-data, or a manifest without games or bet_ids, THROWS here. Left unset,
// the NEXT_PUBLIC_SNAPSHOT_* lists would make lib/fetchHonest.ts snapshotHas* answer
// true for everything and every game/bet link would render and 404 on the live site.
function fail(message) {
  throw new Error(`next.config.mjs (NEXT_PUBLIC_DATA_MODE=snapshot): ${message}`);
}

// The baked files, read at build time and inlined for lib/fetchHonest.ts: a GET
// whose /demo-data/*.json was never exported degrades to the honest Unavailable
// sentinel without a network round-trip (no 404 in the console).
function snapshotFiles() {
  if (!SNAPSHOT) return null;
  let names;
  try {
    names = readdirSync(new URL('./public/demo-data/', import.meta.url)).filter((f) => f.endsWith('.json'));
  } catch (e) {
    fail(`webapp/public/demo-data is missing or unreadable (${e.message})`);
  }
  if (!names.length) fail('webapp/public/demo-data holds no baked *.json; stage the export (scripts/platformkit/publish_demo) first');
  return JSON.stringify(names);
}
const SNAPSHOT_FILES = snapshotFiles();

// The games whose detail pages the export actually contains (manifest.games is
// what generateStaticParams builds). Client lists link only those; the rest
// render as plain cards instead of links that would 404. Same for the paper-trade
// detail pages (/paper/<bet id>, built from manifest.bet_ids).
function readManifest() {
  if (!SNAPSHOT) return null;
  let m;
  try {
    m = JSON.parse(readFileSync(new URL('./public/demo-data/manifest.json', import.meta.url), 'utf8'));
  } catch (e) {
    fail(`webapp/public/demo-data/manifest.json is missing or invalid (${e.message})`);
  }
  const games = (Array.isArray(m?.games) ? m.games : [])
    .filter((g) => g && typeof g.sport === 'string' && typeof g.game_id === 'string');
  const bets = (Array.isArray(m?.bet_ids) ? m.bet_ids : []).filter((b) => typeof b === 'string');
  if (!games.length) fail('manifest.json lists no games, so no game detail page would be exported');
  if (!bets.length) fail('manifest.json lists no bet_ids, so no /paper/<id> page would be exported');
  return { games: games.map((g) => `${g.sport}/${g.game_id}`), bets };
}
const MANIFEST = readManifest();
const SNAPSHOT_GAMES = MANIFEST ? JSON.stringify(MANIFEST.games) : null;
const SNAPSHOT_BETS = MANIFEST ? JSON.stringify(MANIFEST.bets) : null;

// A build id for client caches: lib/useLiveData.ts prefixes its last-known-value
// sessionStorage key with it, so a redeploy never repaints a previous build's payload.
// The commit in CI; a per-process stamp for a local build.
const BUILD_ID = (process.env.GITHUB_SHA || '').slice(0, 12) || `local-${Date.now().toString(36)}`;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Cap build workers. The default (cores - 1 = 11 here, about 5 GB; two still took 1.5 GB) starves the
  // paper-desk recorder that shares this 16 GB box. Override: NEXT_BUILD_CPUS=<n>.
  experimental: { cpus: Number(process.env.NEXT_BUILD_CPUS) || 1 },
  env: {
    NEXT_PUBLIC_BUILD_ID: BUILD_ID,
    ...(SNAPSHOT_FILES ? { NEXT_PUBLIC_SNAPSHOT_FILES: SNAPSHOT_FILES } : {}),
    ...(SNAPSHOT_GAMES ? { NEXT_PUBLIC_SNAPSHOT_GAMES: SNAPSHOT_GAMES } : {}),
    ...(SNAPSHOT_BETS ? { NEXT_PUBLIC_SNAPSHOT_BETS: SNAPSHOT_BETS } : {}),
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
