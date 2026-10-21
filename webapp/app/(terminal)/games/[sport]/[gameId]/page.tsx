import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import { GameView } from "./GameView";
import { readManifest } from "@/lib/manifest.server";
import { gameMeta } from "@/lib/seo/families";

// The baked slate (public/demo-data/api_board_slate_sport_<sport>.json) names the teams; a game
// it does not list falls back to the id (KX tickers decode to "AWAY @ HOME" in lib/betdesc).
type SlateGame = { game_id: string; home?: string; away?: string; tipoff?: string };
function slateGame(sport: string, gameId: string): SlateGame | null {
  if (!/^[a-z_]+$/.test(sport)) return null;
  try {
    const raw = readFileSync(join(process.cwd(), "public", "demo-data", `api_board_slate_sport_${sport}.json`), "utf-8");
    return ((JSON.parse(raw).games ?? []) as SlateGame[]).find((g) => g.game_id === gameId) ?? null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: { sport: string; gameId: string } }): Promise<Metadata> {
  const g = slateGame(params.sport, params.gameId);
  return gameMeta({ sport: params.sport, gameId: params.gameId, home: g?.home, away: g?.away, tipoff: g?.tipoff, asOf: (await readManifest())?.generated_at });
}

// Static-export param list (snapshot demo build). Live/dev builds ignore this
// list at request time -- dynamicParams=true still serves any sport/gameId.
// Static export (output:'export') requires every path to be pre-rendered --
// no server exists to handle an unlisted param. Live/dev builds keep true so
// any sport/gameId still renders on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";
export async function generateStaticParams() {
  const m = await readManifest();
  const games = m?.games ?? [];
  // output:'export' errors if a dynamic route resolves to 0 static paths.
  if (!games.length) return [{ sport: "nba", gameId: "none" }];
  return games.map((g) => ({ sport: g.sport, gameId: g.game_id }));
}

// Full per-game view route: /games/{sport}/{gameId}
// The one coherent prediction (provenance + uncertainty), the full market
// surface, best-bets (units/tier/decision), the in-game calibration number, the
// CLV scoreboard, and a paper-bet action -- all UNITS / probability only, no $.
export default function GamePage({
  params,
}: {
  params: { sport: string; gameId: string };
}) {
  return <GameView sport={params.sport} gameId={params.gameId} />;
}
