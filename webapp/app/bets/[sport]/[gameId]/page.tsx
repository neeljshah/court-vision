import { CardDetailView } from "@/components/bets_detail";

export const metadata = {
  title: "Bet detail",
};

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
