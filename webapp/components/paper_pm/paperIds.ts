// paperIds.ts -- one id per forward paper fill, and the one matcher the
// /paper/<id>/ detail page uses, so link -> exported directory -> route param ->
// lookup round-trips. Encoding chain (see lib/paperLinks.ts):
//   fillId(row)        raw   "nba|KXNBAGAME-...|no|2026-10-09T00:51:29.008426Z|0.23"
//   fillParam(row)     once  the generateStaticParams value = the exported directory name
//   paperDetailHref()  twice the href; the host decodes one layer to find the directory
// The route param can arrive with one or two layers still encoded depending on how
// the client reads it, so findFill compares fully decoded forms on both sides.
import type { PaperTrail, PaperTrailRow } from "@/lib/p5api";
import { toBetId } from "./betId";

// ponytail: ts + qty separates the two partial fills that share one fill receipt;
// a collision would need two identical quantities on one receipt (the test checks the baked trail).
export function fillId(r: PaperTrailRow): string {
  return [r.sport || "unknown", r.game_id || "unknown", r.side || "unknown", r.ts || "unknown",
    r.stake_units ?? "unknown"].join("|");
}

export const fillParam = (r: PaperTrailRow) => encodeURIComponent(fillId(r));

/** Decode until stable (at most 3 layers); a malformed escape stops at the last good form. */
export function canonicalId(s: string): string {
  let cur = s;
  for (let i = 0; i < 3 && cur.includes("%"); i++) {
    try {
      const next = decodeURIComponent(cur);
      if (next === cur) break;
      cur = next;
    } catch {
      break;
    }
  }
  return cur;
}

/** Exact match only (never a same-game fallback: that would show a different fill). */
export function findFill(rows: PaperTrailRow[], param: string): PaperTrailRow | null {
  const target = canonicalId(param);
  return rows.find((r) => canonicalId(fillId(r)) === target || canonicalId(toBetId(r)) === target) ?? null;
}

/** The one baked fill a /paper/<id>/ page is seeded with, plus the trail export's own as_of. */
export interface FillSeed {
  row: PaperTrailRow;
  asOf: string | null;
}

/**
 * The seed as the PaperTrail shape useLiveData holds: a one-row trail (count is that row count,
 * nothing invented) carrying the export's as_of so the page's "as of" reads the baked date. The
 * client's first poll replaces it with the full trail.
 */
export function fillSeedTrail(seed: FillSeed): PaperTrail & { as_of?: string } {
  return { status: "ok", count: 1, trail: [seed.row], ...(seed.asOf ? { as_of: seed.asOf } : {}) };
}
