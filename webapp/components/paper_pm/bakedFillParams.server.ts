// Server-only helpers over the baked paper trail (public/demo-data/api_paper_trail_limit_400.json,
// written by scripts/platformkit/publish_demo/export_forward_record.py): the fill ids for
// /paper/[betId] static params, and the one fill a page seeds its client with. Lives outside
// the page module because Next.js rejects extra exports on a page.
// In a snapshot build a missing, unreadable or empty trail THROWS: an empty list
// would export zero /paper/<id> pages with a green build. Live builds keep [].
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PaperTrailRow } from "@/lib/p5api";
import { isSnapshotMode } from "@/lib/fetchHonest";
import { fillParam, findFill, type FillSeed } from "@/components/paper_pm/paperIds";

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

/** The trail file's top-level as_of, or null when absent/unreadable. */
function bakedAsOf(file: string): string | null {
  try {
    const v = (JSON.parse(readFileSync(file, "utf-8")) as { as_of?: unknown } | null)?.as_of;
    return typeof v === "string" ? v : null;
  } catch {
    return null;
  }
}

/**
 * The baked row for a route param (matched on the decoded fill id, exactly as the client's
 * findFill matches) with the export's as_of. undefined when the fill is absent: the page then
 * renders without a seed and the client loads as before. snapshot=false: the snapshot-mode
 * throw already fires in bakedFillParams (generateStaticParams), so a seed never throws.
 */
export function bakedFillSeed(betId: string, file = TRAIL, snapshot = false): FillSeed | undefined {
  const row = findFill(bakedFillRows(file, snapshot), betId);
  return row ? { row, asOf: bakedAsOf(file) } : undefined;
}
