// Memoized readers for the showcase data-layer JSON: percentile ranks feeding
// the entity-card bars, and cross-module joins layered onto entity cards. Both
// parse once per build (module-scope cache, like the page's own _modTitles) and
// degrade silently to an empty map on a missing file -- the caller's optional
// chaining turns that into the same honest "nothing here" as a present-but-thin entry.
import { readFileSync } from "node:fs";
import { join } from "node:path";

const SHOWCASE = join(process.cwd(), "public", "data", "showcase");

export type PctPack = { n_in_pack: number; entities: Record<string, Record<string, number>> };
export type JoinItem = {
  key: string; label: string; value: string; detail?: string;
  source_artifact: string; confound: string;
};
export type JoinPack = {
  coverage: Record<string, number>;
  entities: Record<string, { items: JoinItem[] }>;
};

// calibration (26 entities, under the artifact's min_n_ranked=30 floor) ships an
// empty entities map, so no percentile bar renders there.
let _percentiles: Record<string, PctPack> | null = null;
export function packPercentiles(pack: string): PctPack | null {
  if (!_percentiles) {
    try { _percentiles = (JSON.parse(readFileSync(join(SHOWCASE, "entity_percentiles.json"), "utf-8")) as { packs?: Record<string, PctPack> }).packs || {}; }
    catch { _percentiles = {}; }
  }
  return _percentiles[pack] || null;
}

// Only nba_teams (30 of 30 cards) and nba_players (345 of 482) carry any joins;
// the other five packs have no entry at all in entity_joins.json.
//
// NOTE the artifact's shape: `coverage` is TOP-LEVEL and keyed by pack, while
// `packs.<pack>` holds only `entities`. Reading coverage from inside packs
// silently yields undefined -- which is how the honesty line first shipped as
// "All 0 team cards carry these 0 joins." Stitch the two together here so the
// component always receives a populated coverage object or an explicit null.
type JoinsFile = { coverage?: Record<string, Record<string, number>>; packs?: Record<string, { entities: JoinPack["entities"] }> };
let _joins: JoinsFile | null = null;
export function packJoins(pack: string): JoinPack | null {
  if (!_joins) {
    try { _joins = JSON.parse(readFileSync(join(SHOWCASE, "entity_joins.json"), "utf-8")) as JoinsFile; }
    catch { _joins = {}; }
  }
  const entry = _joins.packs?.[pack];
  if (!entry) return null;
  return { coverage: _joins.coverage?.[pack] || {}, entities: entry.entities };
}
