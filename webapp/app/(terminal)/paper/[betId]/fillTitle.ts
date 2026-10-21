// fillTitle.ts -- "Paper fill: <sport> <game> <side> <date>" from one paper trail row.
// Shared by the server generateMetadata and the client header so the two never drift.
import type { PaperTrailRow } from "@/lib/p5api";
import { humanizeMatchup } from "@/lib/betdesc";
import { sportLabel } from "@/lib/seo/families";

export function fillTitle(row: Pick<PaperTrailRow, "sport" | "game_id" | "matchup" | "side" | "ts">): string {
  const game = humanizeMatchup(row.game_id) || humanizeMatchup(row.matchup) || "matchup not published";
  const side = row.side ? row.side.toUpperCase() : "side not published";
  const date = row.ts ? row.ts.slice(0, 10) : "date not published";
  return `Paper fill: ${sportLabel(row.sport)} ${game} ${side} ${date}`;
}
