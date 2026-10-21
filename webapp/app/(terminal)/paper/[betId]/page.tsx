// Server wrapper -- carries generateStaticParams (a "use client" file can't export it) and,
// in snapshot builds, seeds the client with the page's own baked fill so the exported HTML
// carries the fill's as-of date, contracts, probability and status instead of "not stated"
// and "loading" until the client fetch lands (the /paper-trading pattern). The exported ids
// are the forward paper fills in the baked trail (public/demo-data/api_paper_trail_limit_400.json,
// written by scripts/platformkit/publish_demo/export_forward_record.py), one page per fill,
// keyed by components/paper_pm/paperIds.fillParam -- the same key the client's findFill
// resolves, so every exported page opens its own fill. A live API build seeds nothing.
import type { Metadata } from "next";
import { bakedFillParams, bakedFillRows, bakedFillSeed } from "@/components/paper_pm/bakedFillParams.server";
import { fillParam, findFill } from "@/components/paper_pm/paperIds";
import { fillMeta } from "@/lib/seo/families";
import { isSnapshotMode } from "@/lib/fetchHonest";
import BetDetailPageClient from "./BetDetailPageClient";

// Static export pre-renders every path; live/dev builds render any id on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";

export async function generateStaticParams() {
  const ids = bakedFillParams();
  // output:'export' errors on 0 static paths -- a placeholder renders the honest "not found".
  return (ids.length ? ids : ["none"]).map((betId) => ({ betId }));
}

// Title + description from the fill itself (matchup, side, time, venue, status); the canonical
// is the double-encoded href the export serves. An unknown id (live mode) keeps the family title.
export function generateMetadata({ params }: { params: { betId: string } }): Metadata {
  const row = findFill(bakedFillRows(), params.betId);
  if (!row) return { title: "Paper fill", description: "One forward paper fill from the paper record. Paper units only; calibration record." };
  return fillMeta({ param: fillParam(row), sport: row.sport, gameId: row.game_id, matchup: row.matchup, side: row.side, ts: row.ts,
    book: row.taken_book, marketType: row.market_type, status: row.status, stakeUnits: row.stake_units });
}

export default function BetDetailPage({ params }: { params: { betId: string } }) {
  const initial = isSnapshotMode ? bakedFillSeed(params.betId) : undefined;
  return <BetDetailPageClient initial={initial} />;
}
