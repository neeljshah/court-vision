"use client";

// PmTrailTable -- paginated, filterable PM paper-trail table.
// UNITS / probability only -- NO $ column, NO dollar P&L field.
// CLV is the only honest calibration yardstick. Absent/no-close -> EMPTY_CELL.
//
// WS8: PmGradedTable (renders PmDisplayRow[] from toPaperTrailRows) is in
// PmGradedTable.tsx to keep each file under the 300-LOC rail.

import { useMemo, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Panel, Badge, Unavailable } from "@/components/p6/Primitives";
import { Skeleton } from "@/components/ui/skeleton";
import { VenueFilter } from "./VenueFilter";
import { PmTradeRow, toBetId, deriveResult } from "./PmTradeRow";
import type { PaperTrailRow } from "@/lib/p5api";

type SortKey =
  | "ts"
  | "tier"
  | "model_prob"
  | "clv_pct"
  | "stake_units"
  | "result";
type SortDir = "asc" | "desc";

function sortValue(r: PaperTrailRow, key: SortKey): number | string {
  switch (key) {
    case "ts":
      return Date.parse(r.ts || "") || 0;
    case "tier":
      return r.tier || "~";
    case "model_prob":
      return r.model_prob ?? -1;
    case "clv_pct":
      return r.clv_pct ?? Number.NEGATIVE_INFINITY;
    case "stake_units":
      return r.stake_units ?? -1;
    case "result":
      return deriveResult(r);
    default:
      return 0;
  }
}

function sortRows(
  rows: PaperTrailRow[],
  key: SortKey,
  dir: SortDir,
): PaperTrailRow[] {
  return [...rows].sort((a, b) => {
    const av = sortValue(a, key);
    const bv = sortValue(b, key);
    let cmp = 0;
    if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
    else cmp = String(av).localeCompare(String(bv));
    return dir === "asc" ? cmp : -cmp;
  });
}

// Derive venue from taken_book (e.g. "espn:DraftKings" -> "DraftKings",
// "kalshi" -> "kalshi"). Treats any PM-specific channel as its own venue.
function venueOf(r: PaperTrailRow): string {
  const b = (r.taken_book || "").toLowerCase();
  if (b.includes("kalshi")) return "kalshi";
  if (b.includes("polymarket")) return "polymarket";
  // "espn:Book" -> keep the book part; otherwise raw value
  const idx = r.taken_book?.indexOf(":") ?? -1;
  if (idx > 0) return r.taken_book!.slice(idx + 1);
  return r.taken_book || "unknown";
}

type Props = {
  rows: PaperTrailRow[];
  loading?: boolean;
  error?: string | null;
  /** Rank by best-tier-then-confidence for "best trades" view. */
  rankMode?: boolean;
};

export function PmTrailTable({ rows, loading, error, rankMode }: Props) {
  const [venue, setVenue] = useState("all");
  const [result, setResult] = useState("all");
  const [tier, setTier] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("ts");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const venues = useMemo(() => {
    const s = new Set<string>();
    rows.forEach((r) => s.add(venueOf(r)));
    return Array.from(s).sort();
  }, [rows]);

  const filtered = useMemo(() => {
    let out = rows;
    if (venue !== "all") out = out.filter((r) => venueOf(r) === venue);
    if (result !== "all") out = out.filter((r) => deriveResult(r) === result);
    if (tier !== "all") out = out.filter((r) => r.tier === tier);
    // Best-trades ranking: tier A first, then by model_prob desc
    if (rankMode) {
      const TIER_RANK: Record<string, number> = { A: 0, B: 1, C: 2 };
      out = [...out].sort((a, b) => {
        const ta = TIER_RANK[a.tier || ""] ?? 99;
        const tb = TIER_RANK[b.tier || ""] ?? 99;
        if (ta !== tb) return ta - tb;
        return (b.model_prob ?? 0) - (a.model_prob ?? 0);
      });
    } else {
      out = sortRows(out, sortKey, sortDir);
    }
    return out;
  }, [rows, venue, result, tier, rankMode, sortKey, sortDir]);

  const onSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "ts" || k === "clv_pct" ? "desc" : "asc");
    }
  };

  if (loading) {
    return (
      <div aria-busy="true" aria-label="Loading paper trades" className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (error) return <Unavailable reason={error} />;

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-10 text-center text-sm text-muted-foreground">
        No paper trades in the PM trail yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <VenueFilter
        venues={venues}
        venue={venue}
        onVenue={setVenue}
        result={result}
        onResult={setResult}
        tier={tier}
        onTier={setTier}
      />

      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] text-faint">
          {filtered.length} of {rows.length} trades
        </span>
        {rankMode ? (
          <Badge tone="amber">ranked by tier + confidence</Badge>
        ) : null}
      </div>

      <ScrollArea className="h-[560px] w-full rounded-lg border border-slate-800">
        <table
          className="min-w-full text-left"
          role="grid"
          aria-label="PM paper trade trail"
        >
          <caption className="sr-only">
            PM paper trail -- units and probability only, no dollar amounts.
          </caption>
          <thead className="sticky top-0 z-10 bg-bg-panel text-[10px] uppercase tracking-wide text-muted-foreground">
            <tr className="border-b border-slate-800">
              {rankMode ? (
                <th className="px-2 py-2 text-right">#</th>
              ) : null}
              <th className="px-2 py-2">Matchup</th>
              <th className="px-2 py-2">Market</th>
              <th className="px-2 py-2">Side</th>
              <SortTh col="tier" sortKey={sortKey} sortDir={sortDir} onSort={onSort} disabled={rankMode}>
                Tier
              </SortTh>
              <SortTh col="model_prob" sortKey={sortKey} sortDir={sortDir} onSort={onSort} disabled={rankMode} align="right">
                Model P
              </SortTh>
              <th className="px-2 py-2 text-right">Entry</th>
              <SortTh col="clv_pct" sortKey={sortKey} sortDir={sortDir} onSort={onSort} disabled={rankMode} align="right">
                CLV
              </SortTh>
              <SortTh col="result" sortKey={sortKey} sortDir={sortDir} onSort={onSort} disabled={rankMode}>
                Result
              </SortTh>
              <SortTh col="stake_units" sortKey={sortKey} sortDir={sortDir} onSort={onSort} disabled={rankMode} align="right">
                Units
              </SortTh>
              <th className="px-2 py-2 text-right">Detail</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <PmTradeRow
                key={`${toBetId(r)}-${i}`}
                row={r}
                rank={rankMode ? i + 1 : undefined}
              />
            ))}
          </tbody>
        </table>
      </ScrollArea>

      <p className="text-[11px] text-faint">
        Paper mode -- stakes are units (no $). CLV (better-number-than-close) is
        the only honest calibration yardstick. No edge is claimed.
      </p>
    </div>
  );
}

type SortThProps = {
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey) => void;
  disabled?: boolean;
  align?: "left" | "right";
  children: React.ReactNode;
};

function SortTh({ col, sortKey, sortDir, onSort, disabled, align = "left", children }: SortThProps) {
  const active = sortKey === col;
  return (
    <th
      className={`px-2 py-2 ${align === "right" ? "text-right" : ""}`}
      aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
    >
      {disabled ? (
        <span className="text-muted-foreground">{children}</span>
      ) : (
        <button
          type="button"
          onClick={() => onSort(col)}
          className="font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground"
        >
          {children}
          <span className="ml-1 font-mono text-faint">
            {active ? (sortDir === "asc" ? "^" : "v") : ""}
          </span>
        </button>
      )}
    </th>
  );
}

// WS8: PmGradedTable lives in PmGradedTable.tsx (split for the 300-LOC rail).
