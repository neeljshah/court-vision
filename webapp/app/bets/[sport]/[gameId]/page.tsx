import { CardDetailView } from "@/components/bets_detail";
import { readManifest } from "@/lib/manifest.server";

export const metadata = {
  title: "Bet detail",
};

// Static export (output:'export') requires every path to be pre-rendered --
// no server exists to handle an unlisted param. Live/dev builds keep true so
// any sport/gameId still renders on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";
export async function generateStaticParams() {
  const m = await readManifest();
  const games = m?.games ?? [];
  if (!games.length) return [{ sport: "nba", gameId: "none" }];
  return games.map((g) => ({ sport: g.sport, gameId: g.game_id }));
}

// /bets/[sport]/[gameId] -- full per-card bet detail.
//
// Shows every betting detail for one game: the full prediction + probability
// interval (with prop P(over/under) from W2), the per-book odds matrix (W1),
// model rationale (validated signals + notes), live boxscore if in-game (W4),
// and the settle/grade + CLV summary when done.
//
// HONESTY RAILS: UNITS / probability only -- no $ anywhere. CLV = beat-the-
// close yardstick only. in-game CLV may be INSUFFICIENT_DATA (shown honestly).
// Paper mode only; real-money default-DENY.
export default function BetDetailPage({
  params,
}: {
  params: { sport: string; gameId: string };
}) {
  return <CardDetailView sport={params.sport} gameId={params.gameId} />;
}
