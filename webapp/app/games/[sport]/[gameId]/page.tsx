import { GameView } from "./GameView";

export const metadata = {
  title: "Game",
};

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
