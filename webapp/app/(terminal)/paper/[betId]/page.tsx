// Server wrapper -- carries generateStaticParams (a "use client" file can't export it) and,
// in snapshot builds, seeds the client with the page's own baked fill so the exported HTML
// carries the fill's as-of date, contracts, probability and status instead of "not stated"
// and "loading" until the client fetch lands (the /paper-trading pattern). The exported ids
// are the forward paper fills in the baked trail (public/demo-data/api_paper_trail_limit_400.json,
// written by scripts/platformkit/publish_demo/export_forward_record.py), one page per fill,
// keyed by components/paper_pm/paperIds.fillParam -- the same key the client's findFill
// resolves, so every exported page opens its own fill. A live API build seeds nothing.
import { bakedFillParams, bakedFillSeed } from "@/components/paper_pm/bakedFillParams.server";
import { isSnapshotMode } from "@/lib/fetchHonest";
import BetDetailPageClient from "./BetDetailPageClient";

// Static export pre-renders every path; live/dev builds render any id on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";

export async function generateStaticParams() {
  const ids = bakedFillParams();
  // output:'export' errors on 0 static paths -- a placeholder renders the honest "not found".
  return (ids.length ? ids : ["none"]).map((betId) => ({ betId }));
}

export default function BetDetailPage({ params }: { params: { betId: string } }) {
  const initial = isSnapshotMode ? bakedFillSeed(params.betId) : undefined;
  return <BetDetailPageClient initial={initial} />;
}
