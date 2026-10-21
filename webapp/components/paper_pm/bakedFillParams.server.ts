// Server-only helpers over the baked paper trail (public/demo-data/api_paper_trail_limit_400.json,
// written by scripts/platformkit/publish_demo/export_forward_record.py): the fill ids for
// /paper/[betId] static params, and the one fill a page seeds its client with. Lives outside
// the page module because Next.js rejects extra exports on a page.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PaperTrailRow } from "@/lib/p5api";
import { fillParam, findFill, type FillSeed } from "@/components/paper_pm/paperIds";

export const BAKED_TRAIL_FILE = join(process.cwd(), "public/demo-data/api_paper_trail_limit_400.json");

type BakedTrail = { as_of?: unknown; trail?: PaperTrailRow[] };

/** The parsed baked trail, or null when the file is absent or not JSON (the client path is unchanged). */
function readBakedTrail(file: string): BakedTrail | null {
  try {
    const parsed = JSON.parse(readFileSync(file, "utf-8")) as BakedTrail | null;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function bakedFillParams(file = BAKED_TRAIL_FILE): string[] {
  return (readBakedTrail(file)?.trail ?? []).map(fillParam);
}

/**
 * The baked row for a route param (matched on the decoded fill id, exactly as the client's
 * findFill matches) with the export's as_of. undefined when the file or the fill is absent:
 * the page then renders without a seed and the client loads as before.
 */
export function bakedFillSeed(betId: string, file = BAKED_TRAIL_FILE): FillSeed | undefined {
  const baked = readBakedTrail(file);
  const row = baked ? findFill(baked.trail ?? [], betId) : null;
  if (!row) return undefined;
  return { row, asOf: typeof baked?.as_of === "string" ? baked.as_of : null };
}
