import type { PaperTrailRow } from "@/lib/p5api";
import { EMPTY_CELL } from "@/lib/tokens";

// Shared pure helpers + types for the paper-trade history view. UNITS /
// probability only -- no dollar / ROI value is ever derived here.

// Derived honest result label. open|ungraded -> pending; void/push or a settled
// bet with no real outcome -> void; otherwise the real win/loss outcome. A
// no-close / pending bet is NEVER coerced to a fabricated win.
export type DerivedResult = "win" | "loss" | "void" | "pending";

export function deriveResult(r: PaperTrailRow): DerivedResult {
  if (r.status === "open" || !r.graded) return "pending";
  const o = (r.outcome || "").toLowerCase();
  if (o === "win") return "win";
  if (o === "loss") return "loss";
  // push / void / unknown-but-settled -> void (never a fabricated win).
  return "void";
}

export type ResultFilter = "all" | DerivedResult;
export type SportFilter = "all" | string;
export type SortKey =
  | "matchup"
  | "sport"
  | "market_type"
  | "tier"
  | "model_prob"
  | "taken_decimal"
  | "clv_pct"
  | "result"
  | "stake_units"
  | "ts";
export type SortDir = "asc" | "desc";

export const RESULT_TONE: Record<
  DerivedResult,
  "green" | "red" | "slate" | "amber"
> = {
  win: "green",
  loss: "red",
  void: "slate",
  pending: "amber",
};

const SPORT_LABEL: Record<string, string> = {
  nba: "NBA",
  mlb: "MLB",
  soccer: "SOC",
  soccer_intl: "SOC",
  tennis: "TEN",
};

export function sportLabel(s: string): string {
  return SPORT_LABEL[s] || (s || "").toUpperCase();
}

export function fmtProb(p: number | null): string {
  return p != null ? `${(p * 100).toFixed(1)}%` : EMPTY_CELL;
}

export function fmtDec(d: number | null): string {
  return d != null ? d.toFixed(2) : EMPTY_CELL;
}

export function fmtUnits(u: number | null): string {
  return u != null ? `${u.toFixed(2)}u` : EMPTY_CELL;
}

// Condensed local timestamp "Jun-15 14:32" from an ISO string (or "--").
export function fmtTs(iso: string | null): string {
  if (!iso) return EMPTY_CELL;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return EMPTY_CELL;
  const d = new Date(t);
  const mon = d.toLocaleString("en-US", { month: "short" });
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${mon}-${day} ${hh}:${mm}`;
}

// clvCellClass -- positive=success, negative=danger, zero/neutral=muted.
export function clvCellClass(v: number | null): string {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-success";
  if (v < 0) return "text-danger";
  return "text-muted-foreground";
}

// showClv -- CLV is only shown when graded against a (real or proxy) close. A
// pending / void / no-close bet renders "--", NEVER 0.0.
export function showClv(r: PaperTrailRow): boolean {
  const res = deriveResult(r);
  return (
    res !== "pending" &&
    res !== "void" &&
    r.clv_pct != null &&
    !r.clv_unavailable
  );
}

export function sortValue(r: PaperTrailRow, key: SortKey): string | number {
  switch (key) {
    case "matchup":
      return (r.matchup || r.game_id || "").toLowerCase();
    case "sport":
      return (r.sport || "").toLowerCase();
    case "market_type":
      return (r.market_type || "").toLowerCase();
    case "tier":
      return r.tier || "~"; // null tiers sort last
    case "model_prob":
      return r.model_prob ?? -1;
    case "taken_decimal":
      return r.taken_decimal ?? -1;
    case "clv_pct":
      return r.clv_pct ?? Number.NEGATIVE_INFINITY;
    case "result":
      return deriveResult(r);
    case "stake_units":
      return r.stake_units ?? -1;
    case "ts":
      return Date.parse(r.ts || "") || 0;
    default:
      return 0;
  }
}

// Stable client-side sort comparator over the filtered rows.
export function sortRows(
  rows: PaperTrailRow[],
  key: SortKey,
  dir: SortDir,
): PaperTrailRow[] {
  const sorted = [...rows].sort((a, b) => {
    const av = sortValue(a, key);
    const bv = sortValue(b, key);
    let cmp = 0;
    if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
    else cmp = String(av).localeCompare(String(bv));
    return dir === "asc" ? cmp : -cmp;
  });
  return sorted;
}
