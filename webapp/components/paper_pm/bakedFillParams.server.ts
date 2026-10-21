// Server-only helper: the baked paper fill ids for /paper/[betId] static params.
// Lives outside the page module because Next.js rejects extra exports on a page.
// In a snapshot build a missing, unreadable or empty trail THROWS: an empty list
// would export zero /paper/<id> pages with a green build. Live builds keep [].
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PaperTrailRow } from "@/lib/p5api";
import { isSnapshotMode } from "@/lib/fetchHonest";
import { fillParam } from "@/components/paper_pm/paperIds";

export const TRAIL_FILE = "public/demo-data/api_paper_trail_limit_400.json";
const TRAIL = join(process.cwd(), TRAIL_FILE);

/** The baked trail rows (empty in a live/dev build when the file is absent; a snapshot build throws). */
export function bakedFillRows(file = TRAIL, snapshot = isSnapshotMode): PaperTrailRow[] {
  let rows: PaperTrailRow[];
  try {
    rows = (JSON.parse(readFileSync(file, "utf-8")).trail ?? []) as PaperTrailRow[];
  } catch (e) {
    if (snapshot) {
      const why = e instanceof Error ? e.message : String(e);
      throw new Error(`snapshot build: ${file} is missing or unreadable (${why}), so no /paper/<id> page can be exported`);
    }
    return [];
  }
  if (snapshot && !rows.length) throw new Error(`snapshot build: ${file} has no trail rows, so no /paper/<id> page can be exported`);
  return rows;
}

export function bakedFillParams(file = TRAIL, snapshot = isSnapshotMode): string[] {
  return bakedFillRows(file, snapshot).map(fillParam);
}
