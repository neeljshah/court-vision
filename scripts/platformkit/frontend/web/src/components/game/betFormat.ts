// Honest formatting helpers specific to the game detail bet board.
// EV is a PERCENT here (e.g. 4.2 -> "+4.2%"); null -> "n/a" everywhere.
import type { BetRow } from "@/lib/api";

export function fmtModelProb(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "n/a";
  return (p * 100).toFixed(1) + "%";
}

export function fmtDec(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
  return x.toFixed(2);
}

export function fmtLine(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "";
  return x > 0 ? "+" + x : String(x);
}

/** EV percent (already in percent units). Signed, with sign for >= 0. */
export function fmtEvPct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
  const s = x.toFixed(1) + "%";
  return x >= 0 ? "+" + s : s;
}

export function evTone(x: number | null | undefined): "pos" | "neg" | "neutral" {
  if (x === null || x === undefined || Number.isNaN(x)) return "neutral";
  return x > 0 ? "pos" : x < 0 ? "neg" : "neutral";
}

/** A row has a real tradeable price (so EV is meaningful) when a book + price exist. */
export function hasPrice(row: BetRow): boolean {
  return row.best_book !== null && row.best_price !== null && row.best_price !== undefined;
}

const POSITIVE = new Set(["BET", "AHEAD", "MATCH", "CALIBRATED", "VALUE", "PLAY"]);
const NEGATIVE = new Set(["BEHIND", "PASS", "AVOID", "FADE"]);

export function verdictVariant(
  verdict: string
): "success" | "destructive" | "warning" | "muted" {
  const v = verdict.toUpperCase();
  if (POSITIVE.has(v)) return "success";
  if (NEGATIVE.has(v)) return "destructive";
  if (v === "UNAVAILABLE" || v === "UNKNOWN") return "muted";
  return "warning";
}
