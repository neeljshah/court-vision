// Server wrapper -- carries generateStaticParams (a "use client" file can't export it).
// The exported ids are the forward paper fills in the baked trail
// (public/demo-data/api_paper_trail_limit_400.json, written by
// scripts/platformkit/publish_demo/export_forward_record.py), one page per fill,
// keyed by components/paper_pm/paperIds.fillParam -- the same key the client's
// findFill resolves, so every exported page opens its own fill.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PaperTrailRow } from "@/lib/p5api";
import { fillParam } from "@/components/paper_pm/paperIds";
import BetDetailPageClient from "./BetDetailPageClient";

// Static export pre-renders every path; live/dev builds render any id on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";

function bakedFillParams(file = join(process.cwd(), "public/demo-data/api_paper_trail_limit_400.json")): string[] {
  try {
    const rows = (JSON.parse(readFileSync(file, "utf-8")).trail ?? []) as PaperTrailRow[];
    return rows.map(fillParam);
  } catch {
    return [];
  }
}

export async function generateStaticParams() {
  const ids = bakedFillParams();
  // output:'export' errors on 0 static paths -- a placeholder renders the honest "not found".
  return (ids.length ? ids : ["none"]).map((betId) => ({ betId }));
}

export default function BetDetailPage() {
  return <BetDetailPageClient />;
}
