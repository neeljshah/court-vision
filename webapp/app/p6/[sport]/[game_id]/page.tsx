import { GameDetail } from "@/components/p6/GameDetail";

export const metadata = {
  title: "Game",
};

// Per-game live report route: /p6/{sport}/{game_id}
export default function GamePage({
  params,
}: {
  params: { sport: string; game_id: string };
}) {
  return <GameDetail sport={params.sport} gameId={params.game_id} />;
}
