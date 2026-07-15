"use client";

// PmTradeRow -- single row in the PM paper-trail table. Click -> /paper/[betId].
// UNITS / probability only -- there is NO dollar column or $ field here.

import Link from "next/link";
import { cn } from "@/lib/utils";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL, tierBadgeClass } from "@/lib/tokens";
import { Badge } from "@/components/p6/Primitives";
import { ClvInline } from "./ClvInline";
import { humanizeMatchup, describeBetShort } from "@/lib/betdesc";
import type { PaperTrailRow } from "@/lib/p5api";

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

// bet_id is constructed from the ledger row fields for stable routing.
export function toBetId(r: PaperTrailRow): string {
  // Mirrors the durable bet_id pattern from clv_ledger: sport|matchup|side|ts
  const parts = [
    r.sport || "unknown",
    r.game_id || "unknown",
    r.market_type || "moneyline",
    r.side || "home",
    r.taken_book || "paper",
  ];
  return encodeURIComponent(parts.join("|"));
}

type Props = {
  row: PaperTrailRow;
  rank?: number;
};

export function PmTradeRow({ row, rank }: Props) {
  const res = deriveResult(row);
  const voided = res === "void";
  const betId = toBetId(row);

  return (
    <tr
      className={cn(
        "border-b border-slate-800/60 text-[12px] text-slate-300 transition-colors hover:bg-slate-800/30",
        voided && "text-muted-foreground",
      )}
    >
      {rank != null ? (
        <td className="px-2 py-1.5 text-right font-mono text-[10px] text-slate-600">
          {rank}
        </td>
      ) : null}
      <td className="px-2 py-1.5">
        <Link href={`/paper/${betId}`} className="hover:underline">
          <span className="font-medium">{humanizeMatchup(row.matchup || row.game_id)}</span>
          <span className="ml-1.5 font-mono text-[10px] text-slate-600">
            {row.sport?.toUpperCase()}
          </span>
        </Link>
      </td>
      <td className="px-2 py-1.5 font-mono text-[11px] text-slate-400">
        {row.market_type || EMPTY_CELL}
      </td>
      <td className="px-2 py-1.5 font-mono text-[11px] text-slate-400">
        {describeBetShort(row)}
      </td>
      <td className="px-2 py-1.5">
        {row.tier ? (
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase",
              tierBadgeClass(row.tier),
            )}
          >
            {row.tier}
          </span>
        ) : (
          <span className="text-slate-600">{EMPTY_CELL}</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
        {fmtProb(row.model_prob)}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
        {fmtDec(row.taken_decimal)}
      </td>
      <td className="px-2 py-1.5 text-right">
        <ClvInline row={row} />
      </td>
      <td className="px-2 py-1.5">
        <Badge tone={RESULT_TONE[res]}>{res}</Badge>
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
        {fmtUnits(row.stake_units)}
      </td>
      <td className="px-2 py-1.5 text-right">
        <Link
          href={`/paper/${betId}`}
          className="font-mono text-[10px] text-slate-500 hover:text-slate-300"
          aria-label={`View detail for ${row.matchup || row.game_id}`}
        >
          detail &rsaquo;
        </Link>
      </td>
    </tr>
  );
}
