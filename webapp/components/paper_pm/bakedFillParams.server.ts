// Server-only helper: the baked paper fill ids for /paper/[betId] static params.
// Lives outside the page module because Next.js rejects extra exports on a page.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PaperTrailRow } from "@/lib/p5api";
import { fillParam } from "@/components/paper_pm/paperIds";

const TRAIL = join(process.cwd(), "public/demo-data/api_paper_trail_limit_400.json");

/** The baked trail rows (empty when the snapshot file is absent, e.g. a live/dev build). */
export function bakedFillRows(file = TRAIL): PaperTrailRow[] {
  try {
    return (JSON.parse(readFileSync(file, "utf-8")).trail ?? []) as PaperTrailRow[];
  } catch {
    return [];
  }
}

export function bakedFillParams(file = TRAIL): string[] {
  return bakedFillRows(file).map(fillParam);
}
