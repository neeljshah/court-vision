// Server-only helper: the baked paper fill ids for /paper/[betId] static params.
// Lives outside the page module because Next.js rejects extra exports on a page.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PaperTrailRow } from "@/lib/p5api";
import { fillParam } from "@/components/paper_pm/paperIds";

export function bakedFillParams(
  file = join(process.cwd(), "public/demo-data/api_paper_trail_limit_400.json"),
): string[] {
  try {
    const rows = (JSON.parse(readFileSync(file, "utf-8")).trail ?? []) as PaperTrailRow[];
    return rows.map(fillParam);
  } catch {
    return [];
  }
}
