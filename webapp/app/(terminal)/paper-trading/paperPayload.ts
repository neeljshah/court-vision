// paperPayload.ts -- the pure assembly of the /paper-trading payload, shared by the
// client fetcher (paperTradingHelpers.fetchPaperCombined) and the build-time reader
// of the baked demo files (paperTrading.server). No directive on purpose: it runs on
// both sides. Each feed degrades independently: an Unavailable sentinel becomes null
// plus its reason under `errors`, never a fabricated empty value. UNITS only, no $.

import type { PaperTrail, PmTrail, ClvScoreboard } from "@/lib/p5api";
import type { PnlSeries, PaperBankroll, Unavailable } from "@/lib/types";
import { isUnavailable } from "@/lib/p5api";

export type PaperFeedKey = "trail" | "pmTrail" | "clv" | "pnl" | "bankroll";

export interface CombinedPayload {
  trail: PaperTrail | null;
  pmTrail: PmTrail | null;
  clv: ClvScoreboard | null;
  pnl: PnlSeries | null;
  bankroll: PaperBankroll | null;
  errors?: Partial<Record<PaperFeedKey, string>>;
}

/** Fold the five feeds into one payload; a sentinel stays a sentinel (null + reason). */
export function combinePaperPayload(
  t: PaperTrail | Unavailable,
  pt: PmTrail | Unavailable,
  c: ClvScoreboard | Unavailable,
  pnl: PnlSeries | Unavailable,
  bank: PaperBankroll | Unavailable,
): CombinedPayload {
  const errors: NonNullable<CombinedPayload["errors"]> = {};
  // A 200 body that is not the expected object (null, {}, {"detail": ...}) is unavailable, never {} passed through.
  function available<T>(key: PaperFeedKey, value: T | Unavailable, ok: (o: Record<string, unknown>) => boolean): T | null {
    if (isUnavailable(value)) {
      errors[key] = value.reason || "unavailable";
      return null;
    }
    const o = value as unknown as Record<string, unknown> | null;
    if (!o || typeof o !== "object" || Array.isArray(o) || !ok(o)) {
      errors[key] = "bad shape";
      return null;
    }
    return value;
  }
  const arr = (k: string) => (o: Record<string, unknown>) => Array.isArray(o[k]);
  const num = (k: string) => (o: Record<string, unknown>) => typeof o[k] === "number";
  return {
    trail: available("trail", t, arr("trail")),
    pmTrail: available("pmTrail", pt, arr("trades")),
    clv: available("clv", c, num("n_bets")),
    pnl: available("pnl", pnl, arr("points")),
    bankroll: available("bankroll", bank, num("current_units")),
    errors,
  };
}

/**
 * The payload's own as-of stamp as epoch ms: the trail export's `as_of`, else its
 * `generated_at_utc`. undefined when the payload carries neither, so a caller never
 * invents a freshness the export did not state.
 */
export function payloadAsOfMs(p: CombinedPayload | undefined): number | undefined {
  const meta = (p?.trail ?? null) as { as_of?: string; generated_at_utc?: string } | null;
  const stamp = meta?.as_of ?? meta?.generated_at_utc;
  if (!stamp) return undefined;
  const ms = Date.parse(stamp);
  return Number.isFinite(ms) ? ms : undefined;
}
