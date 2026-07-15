"use client";

import type { PaperTrailRow } from "@/lib/p5api";
import { Badge } from "./Primitives";
import { Num } from "@/components/ui/terminal";
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
        "microlabel h-9 px-3",
        align === "right" && "text-right",
      )}
    >
      <Button
        type="button"
        variant="ghost"
        onClick={() => onSort(col)}
        aria-label={`Sort by ${label} ${active && sortDir === "asc" ? "descending" : "ascending"}`}
        className={cn(
          "-mx-1 h-6 px-1 text-[10px] font-medium uppercase tracking-wide text-faint hover:text-foreground",
          align === "right" && "ml-auto",
        )}
      >
        {label}
        <span className="ml-1 font-data text-faint">
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
        "border-border text-foreground hover:bg-surface-2",
        voided && "text-muted-foreground",
      )}
    >
      <TableCell className="px-3 py-1.5">
        <div className="font-medium">{r.matchup || r.game_id}</div>
        <div className="font-data text-[10px] text-faint">{r.game_id}</div>
      </TableCell>
      <TableCell className="px-3 py-1.5">
        <span className="font-data text-[10px] uppercase text-faint">
          {sportLabel(r.sport)}
        </span>
      </TableCell>
      <TableCell className="px-3 py-1.5 font-data text-[11px]">
        {r.market_type || EMPTY_CELL}
      </TableCell>
      <TableCell className="px-3 py-1.5 font-data text-[11px] text-faint">
        {r.side || EMPTY_CELL}
      </TableCell>
      <TableCell className="px-3 py-1.5">
        {r.tier ? (
          <span
            className={cn(
              "inline-flex items-center border px-2 py-0.5 text-[10px] font-data uppercase",
              tierBadgeClass(r.tier),
            )}
          >
            {r.tier}
          </span>
        ) : (
          <span className="text-faint">{EMPTY_CELL}</span>
        )}
      </TableCell>
      <TableCell className="px-3 py-1.5 text-right">
        <Num>{fmtProb(r.model_prob)}</Num>
      </TableCell>
      <TableCell className="px-3 py-1.5 text-right">
        <Num>{fmtDec(r.taken_decimal)}</Num>
      </TableCell>
      <TableCell
        className={cn(
          "px-3 py-1.5 text-right",
          withClv ? clvCellClass(r.clv_pct) : "text-muted-foreground",
        )}
      >
        {withClv ? (
          <Num className="inline-flex items-center gap-1">
            {r.clv_is_proxy ? (
              <span
                title="CLV vs proxy close, not real book"
                className="text-stale"
              >
                ~
              </span>
            ) : null}
            {fmtPct(r.clv_pct as number)}
          </Num>
        ) : (
          <Num>{EMPTY_CELL}</Num>
        )}
      </TableCell>
      <TableCell className="px-3 py-1.5">
        <Badge tone={RESULT_TONE[res]}>{res}</Badge>
      </TableCell>
      <TableCell className="px-3 py-1.5 text-right">
        <Num>{fmtUnits(r.stake_units)}</Num>
      </TableCell>
      <TableCell
        className="px-3 py-1.5 text-right font-data text-[10px] text-faint"
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
    <div className="border border-border bg-surface-1 px-3 py-2.5">
      <div className="microlabel">{label}</div>
      {value == null ? (
        <Skeleton className="mt-1 h-6 w-16" />
      ) : (
        <Num className={cn("mt-0.5 block text-lg", valueClass || "text-foreground")}>
          {value}
        </Num>
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
      <span className="microlabel">{label}</span>
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
    <div className="flex flex-col items-center gap-2 border border-border bg-surface-1/40 px-4 py-10 text-center">
      <p className="text-sm text-faint">{message}</p>
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
      className="space-y-2 border border-border p-3"
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
