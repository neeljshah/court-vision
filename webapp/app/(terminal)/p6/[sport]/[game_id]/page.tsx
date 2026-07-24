import { GameDetail } from "@/components/p6/GameDetail";
import { readManifest } from "@/lib/manifest.server";

export const metadata = {
  title: "Game",
};

// Static export (output:'export') requires every path to be pre-rendered --
// no server exists to handle an unlisted param. Live/dev builds keep true so
// any sport/gameId still renders on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";
export async function generateStaticParams() {
  const m = await readManifest();
  const games = m?.games ?? [];
  if (!games.length) return [{ sport: "nba", game_id: "none" }];
  return games.map((g) => ({ sport: g.sport, game_id: g.game_id }));
}

// Per-game live report route: /p6/{sport}/{game_id}
export default function GamePage({
  params,
}: {
  params: { sport: string; game_id: string };
}) {
  return <GameDetail sport={params.sport} gameId={params.game_id} />;
}
