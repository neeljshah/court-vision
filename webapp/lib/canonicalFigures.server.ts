// canonicalFigures.server.ts -- build-time reader for docs/evidence/CANONICAL_FIGURES.json,
// the one file every public pregame-vs-close / in-game-vs-market figure comes from.
// Pages read numbers through here so no canonical figure is typed by hand.
// Server-only (node:fs). A missing/malformed file THROWS (build-time failure is the honest outcome).
import { readFileSync } from "node:fs";
import { join } from "node:path";

export const CANONICAL_PATH = "docs/evidence/CANONICAL_FIGURES.json";

export type CanonicalFigure = {
  key: string;
  sport: string;
  market: string;
  metric: string;
  devig?: string;
  n?: number;
  n_unit?: string;
  model?: number;
  close?: number;
  gap?: number;
  ci95?: [number, number];
  dm_p?: string;
  mde?: number;
  verdict: string;
  source: string;
  as_of: string;
  licenses: string;
};

let cache: CanonicalFigure[] | null = null;

export function canonicalFigures(file = join(process.cwd(), "..", CANONICAL_PATH)): CanonicalFigure[] {
  if (cache) return cache;
  try {
    const d = JSON.parse(readFileSync(file, "utf-8")) as { figures?: CanonicalFigure[] };
    if (!Array.isArray(d.figures)) throw new Error("no figures array");
    cache = d.figures;
  } catch (e) {
    throw new Error(`canonicalFigures: cannot read ${file}: ${e instanceof Error ? e.message : String(e)}`);
  }
  return cache;
}

export function figure(key: string): CanonicalFigure | null {
  return canonicalFigures().find((f) => f.key === key) ?? null;
}

/** The home headline rows: the three pregame-vs-close figures, largest n first (P2.3). */
export const HEADLINE_KEYS = [
  "mlb_ml_pregame_vs_close",
  "soccer_ou25_pregame_vs_close",
  "nba_ml_pregame_vs_close_shin",
] as const;

export function headlineFigures(): CanonicalFigure[] {
  const got = HEADLINE_KEYS.map((k) => ({ k, f: figure(k) }));
  const missing = got.filter((g) => !g.f).map((g) => g.k);
  if (missing.length) throw new Error(`headlineFigures: missing keys in ${CANONICAL_PATH}: ${missing.join(", ")}`);
  return got.map((g) => g.f as CanonicalFigure)
    .sort((a, b) => (b.n ?? 0) - (a.n ?? 0));
}
