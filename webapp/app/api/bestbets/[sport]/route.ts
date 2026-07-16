// GET /api/bestbets/[sport] -- same-origin, file-backed replacement for the
// :8099 live /api/v1/bestbets/{sport} route (see _lib.ts header for why).

import { NextResponse } from "next/server";
import { getBestBetsForSport } from "../_lib";

// Snapshot demo build (output:'export') can't ship a force-dynamic route --
// never called by the client there anyway (fetchHonest redirects to
// /demo-data/*.json first); stub it so the static export still builds.
export const dynamic =
  process.env.NEXT_PUBLIC_DATA_MODE === "snapshot" ? "force-static" : "force-dynamic";
export const runtime = "nodejs";

// Static export (output:'export') requires every dynamic-segment path to be
// pre-rendered; this route is never called in snapshot mode (fetchHonest goes
// to /demo-data/*.json first), so one placeholder path is enough for the
// build. Live/dev builds ignore this (dynamicParams stays true).
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";
export async function generateStaticParams() {
  return [{ sport: "nba" }];
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ sport: string }> },
) {
  const { sport } = await params;
  if (process.env.NEXT_PUBLIC_DATA_MODE === "snapshot") {
    return NextResponse.json(
      { sport, status: "unavailable", games: [], reason: "static demo build -- no digest file" },
      { status: 503 },
    );
  }
  const env = await getBestBetsForSport(sport);
  if (!env) {
    return NextResponse.json(
      { sport, status: "unavailable", games: [], reason: "best_bets.json missing or unreadable" },
      { status: 503 },
    );
  }
  return NextResponse.json(env);
}
