"use client";

// PmTradeRow -- single row in the PM paper-trail table. Click -> /paper/[betId].
// UNITS / probability only -- there is NO dollar column or $ field here.

import Link from "next/link";
import { snapshotHasBet } from "@/lib/fetchHonest";
import { paperDetailHref } from "@/lib/paperLinks";
import { cn } from "@/lib/utils";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL, tierBadgeClass } from "@/lib/tokens";
import { Badge } from "@/components/p6/Primitives";
import { ClvInline } from "./ClvInline";
import { humanizeMatchup, describeBetShort } from "@/lib/betdesc";
import type { PaperTrailRow } from "@/lib/p5api";
import { toBetId } from "./betId";
// re-exported for the client consumers (PmTrailTable, tests); server code imports ./betId directly
export { toBetId };

type DerivedResult = "win" | "loss" | "void" | "pending";

export function deriveResult(r: PaperTrailRow): DerivedResult {
  if (r.status === "open" || !r.graded) return "pending";
  const o = (r.outcome || "").toLowerCase();
  if (o === "win") return "win";
  if (o === "loss") return "loss";
  return "void";
}

const RESULT_TONE: Record<DerivedResult, "green" | "red" | "slate" | "amber"> =
  {
    win: "green",
    loss: "red",
    void: "slate",
    pending: "amber",
  };

function fmtProb(p: number | null): string {
  return p != null ? `${(p * 100).toFixed(1)}%` : EMPTY_CELL;
}

function fmtDec(d: number | null): string {
  return d != null ? d.toFixed(2) : EMPTY_CELL;
}

function fmtUnits(u: number | null): string {
  return u != null ? `${u.toFixed(2)}u` : EMPTY_CELL;
}

type Props = {
  row: PaperTrailRow;
  rank?: number;
};

export function PmTradeRow({ row, rank }: Props) {
  const res = deriveResult(row);
  const voided = res === "void";
  const betId = toBetId(row);
  // Snapshot export: only the bets in manifest.bet_ids have a detail page.
  const published = snapshotHasBet(betId);

  return (
    <tr
      className={cn(
        "border-b border-border text-[12px] text-foreground transition-colors hover:bg-surface-2",
        voided && "text-muted-foreground",
      )}
    >
      {rank != null ? (
        <td className="px-2 py-1.5 text-right font-mono text-[12px] text-faint">
          {rank}
        </td>
      ) : null}
      <td className="px-2 py-1.5">
        {published ? (
          <Link href={paperDetailHref(betId)} className="hover:underline">
            <span className="font-medium">{humanizeMatchup(row.matchup || row.game_id)}</span>
            <span className="ml-1.5 font-mono text-[12px] text-faint">
              {row.sport?.toUpperCase()}
            </span>
          </Link>
        ) : (
          <span title="Detail page is not included in this snapshot">
            <span className="font-medium">{humanizeMatchup(row.matchup || row.game_id)}</span>
            <span className="ml-1.5 font-mono text-[12px] text-faint">
              {row.sport?.toUpperCase()}
            </span>
          </span>
        )}
      </td>
      <td className="px-2 py-1.5 font-mono text-[12px] text-muted-foreground">
        {row.market_type || EMPTY_CELL}
      </td>
      <td className="px-2 py-1.5 font-mono text-[12px] text-muted-foreground">
        {describeBetShort(row)}
      </td>
      <td className="px-2 py-1.5">
        {row.tier ? (
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2 py-0.5 text-[12px] font-mono uppercase",
              tierBadgeClass(row.tier),
            )}
          >
            {row.tier}
          </span>
        ) : (
          <span className="text-faint">{EMPTY_CELL}</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">
        {fmtProb(row.model_prob)}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">
        {fmtDec(row.taken_decimal)}
      </td>
      <td className="px-2 py-1.5 text-right">
        <ClvInline row={row} />
      </td>
      <td className="px-2 py-1.5">
        <Badge tone={RESULT_TONE[res]}>{res}</Badge>
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">
        {fmtUnits(row.stake_units)}
      </td>
      <td className="px-2 py-1.5 text-right">
        {published ? (
          <Link
            href={paperDetailHref(betId)}
            className="font-mono text-[12px] text-muted-foreground hover:text-foreground"
            aria-label={`View detail for ${row.matchup || row.game_id}`}
          >
            detail &rsaquo;
          </Link>
        ) : (
          <span className="font-mono text-[12px] text-faint" title="Detail page is not included in this snapshot">
            no detail
          </span>
        )}
      </td>
    </tr>
  );
}
