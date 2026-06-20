"use client";

import type { PaperTrailRow } from "@/lib/p5api";
import { Badge } from "./Primitives";
import { TableCell, TableHead, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn, fmtPct } from "@/lib/utils";
import { EMPTY_CELL, tierBadgeClass } from "@/lib/tokens";
import {
  clvCellClass,
  deriveResult,
  fmtDec,
  fmtProb,
  fmtTs,
  fmtUnits,
  RESULT_TONE,
  showClv,
  sportLabel,
  type SortDir,
  type SortKey,
} from "./paper-history-utils";

// Presentational pieces for the paper-trade history table. UNITS / probability
// only -- there is NO dollar column or $ field anywhere.

type SortHeadProps = {
  label: string;
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey) => void;
  align?: "left" | "right";
};

export function SortHead({
  label,
  col,
  sortKey,
  sortDir,
  onSort,
  align = "left",
}: SortHeadProps) {
  const active = sortKey === col;
  const ariaSort = active
    ? sortDir === "asc"
      ? "ascending"
      : "descending"
    : "none";
  return (
    <TableHead
      aria-sort={ariaSort}
      className={cn(
        "h-9 px-2 text-[10px] uppercase tracking-wide text-slate-400",
        align === "right" && "text-right",
      )}
    >
      <Button
        type="button"
        variant="ghost"
        onClick={() => onSort(col)}
        aria-label={`Sort by ${label} ${active && sortDir === "asc" ? "descending" : "ascending"}`}
        className={cn(
          "-mx-1 h-6 px-1 text-[10px] font-medium uppercase tracking-wide text-slate-400 hover:text-slate-200",
          align === "right" && "ml-auto",
        )}
      >
        {label}
        <span className="ml-1 font-mono text-slate-500">
          {active ? (sortDir === "asc" ? "^" : "v") : ""}
        </span>
      </Button>
    </TableHead>
  );
}

export function TradeRow({ row: r }: { row: PaperTrailRow }) {
  const res = deriveResult(r);
  const voided = res === "void";
  const withClv = showClv(r);

  return (
    <TableRow
      className={cn(
        "border-slate-800/60 text-slate-300",
        voided && "text-muted-foreground",
      )}
    >
      <TableCell className="px-2 py-1.5">
        <div className="font-medium">{r.matchup || r.game_id}</div>
        <div className="font-mono text-[10px] text-slate-600">{r.game_id}</div>
      </TableCell>
      <TableCell className="px-2 py-1.5">
        <span className="font-mono text-[10px] uppercase text-slate-400">
          {sportLabel(r.sport)}
        </span>
      </TableCell>
      <TableCell className="px-2 py-1.5 font-mono text-[11px]">
        {r.market_type || EMPTY_CELL}
      </TableCell>
      <TableCell className="px-2 py-1.5 font-mono text-[11px] text-slate-400">
        {r.side || EMPTY_CELL}
      </TableCell>
      <TableCell className="px-2 py-1.5">
        {r.tier ? (
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase",
              tierBadgeClass(r.tier),
            )}
          >
            {r.tier}
          </span>
        ) : (
          <span className="text-slate-600">{EMPTY_CELL}</span>
        )}
      </TableCell>
      <TableCell className="px-2 py-1.5 text-right font-mono tabular-nums">
        {fmtProb(r.model_prob)}
      </TableCell>
      <TableCell className="px-2 py-1.5 text-right font-mono tabular-nums">
        {fmtDec(r.taken_decimal)}
      </TableCell>
      <TableCell
        className={cn(
          "px-2 py-1.5 text-right font-mono tabular-nums",
          withClv ? clvCellClass(r.clv_pct) : "text-muted-foreground",
        )}
      >
        {withClv ? (
          <span className="inline-flex items-center gap-1">
            {r.clv_is_proxy ? (
              <span
                title="CLV vs proxy close, not real book"
                className="text-warning"
              >
                ~
              </span>
            ) : null}
            {fmtPct(r.clv_pct as number)}
          </span>
        ) : (
          EMPTY_CELL
        )}
      </TableCell>
      <TableCell className="px-2 py-1.5">
        <Badge tone={RESULT_TONE[res]}>{res}</Badge>
      </TableCell>
      <TableCell className="px-2 py-1.5 text-right font-mono tabular-nums">
        {fmtUnits(r.stake_units)}
      </TableCell>
      <TableCell
        className="px-2 py-1.5 text-right font-mono text-[10px] text-slate-500"
        title={r.ts || ""}
      >
        {fmtTs(r.ts)}
      </TableCell>
    </TableRow>
  );
}

export function Stat({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string | null;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg bg-bg-subtle px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      {value == null ? (
        <Skeleton className="mt-1 h-6 w-16" />
      ) : (
        <div
          className={cn(
            "mt-0.5 font-mono text-lg tabular-nums",
            valueClass || "text-slate-100",
          )}
        >
          {value}
        </div>
      )}
    </div>
  );
}

export function FilterGroup<T extends string>({
  label,
  value,
  onChange,
  options,
  render,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: T[];
  render: (v: T) => string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <div className="flex flex-wrap gap-1">
        {options.map((opt) => (
          <Button
            key={opt}
            type="button"
            variant={value === opt ? "default" : "outline"}
            size="sm"
            onClick={() => onChange(opt)}
            className="h-6 px-2 text-[10px] capitalize"
          >
            {render(opt)}
          </Button>
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  message,
  onClear,
}: {
  message: string;
  onClear?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-10 text-center">
      <p className="text-sm text-slate-500">{message}</p>
      {onClear ? (
        <Button type="button" variant="outline" size="sm" onClick={onClear}>
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading trade history"
      className="space-y-2 rounded-lg border border-slate-800 p-3"
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
