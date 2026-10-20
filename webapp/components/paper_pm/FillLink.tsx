// FillLink -- the matchup label of a paper row; a forward fill (channel paper_ingame,
// one exported /paper/<id>/ page each) links to its detail page via the shared id chain.
import Link from "next/link";
import type { PaperTrailRow } from "@/lib/p5api";
import { humanizeMatchup } from "@/lib/betdesc";
import { paperDetailHref } from "@/lib/paperLinks";
import { fillParam } from "./paperIds";

export function FillLink({ row }: { row: PaperTrailRow }) {
  const label = humanizeMatchup(row.matchup || row.game_id);
  if (row.channel !== "paper_ingame") return <span className="font-medium">{label}</span>;
  return (
    <Link href={paperDetailHref(fillParam(row))} prefetch={false} className="font-medium underline">
      {label}
    </Link>
  );
}
