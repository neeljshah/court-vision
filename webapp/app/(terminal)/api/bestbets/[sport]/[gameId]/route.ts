// GET /api/bestbets/[sport]/[gameId] -- same-origin, file-backed replacement
// for the :8099 live /api/v1/bestbets/{sport}/{game_id} route (see ../../_lib.ts).

import { NextResponse } from "next/server";
import { getBestBetsForGame } from "../../_lib";

export const dynamic =
  process.env.NEXT_PUBLIC_DATA_MODE === "snapshot" ? "force-static" : "force-dynamic";
export const runtime = "nodejs";

// See ../route.ts -- static export needs a pre-rendered path; never hit in
// snapshot mode (fetchHonest goes to /demo-data/*.json first).
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";
export async function generateStaticParams() {
  return [{ sport: "nba", gameId: "none" }];
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ sport: string; gameId: string }> },
) {
  const { sport, gameId } = await params;
  if (process.env.NEXT_PUBLIC_DATA_MODE === "snapshot") {
    return NextResponse.json(
      { status: "unavailable", reason: "static demo build -- no digest file" },
      { status: 503 },
    );
  }
  const game = await getBestBetsForGame(sport, gameId);
  if (!game) {
    return NextResponse.json(
      { status: "unavailable", reason: "best_bets.json missing or unreadable" },
      { status: 503 },
    );
  }
  return NextResponse.json(game);
}
