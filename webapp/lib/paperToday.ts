// paperToday.ts -- typed client + honest fallback for the TODAY digest.
//
// PRIMARY source: GET /api/paper/today (same-origin Next route reading
//   data/frontend/paper_today.json off disk). Shape:
//     { date, placed[], pending[], settled_today[], day_units,
//       cumulative_units, start_units, current_units, net_units }
//
// FALLBACK (when /api/paper/today is 404/503/unavailable): we DEGRADE HONESTLY by
//   composing the digest from the existing live endpoints --
//     /api/paper/pnl/series  -> cumulative_units / day_units / settled tally
//     /api/paper/bankroll     -> bankroll / start_units
//   PLACED bets are NOT derivable from those endpoints, so in fallback mode
//   placed/pending stay empty and the UI shows an explicit "placed-bet feed
//   unavailable" note. We NEVER fabricate a placed bet.
//
// HONESTY RAILS: UNITS only -- NO $ token; edge_claimed=false; stale-never-green;
// real-money DENY. ASCII only. Under 300 LOC.

import { api, isUnavailable } from "./p5api";
import { fetchHonest } from "./fetchHonest";
import type { Unavailable, PnlSeries, PaperBankroll } from "./types";

export const P5_BASE =
  process.env.NEXT_PUBLIC_P5_BASE || "/p5";

// One placed / pending / settled paper bet in the today digest. UNITS only.
export type TodayBet = {
  game_id?: string | null;
  sport?: string | null;
  matchup?: string | null;
  market_type?: string | null;
  side?: string | null;
  model_prob?: number | null;
  tier?: string | null;
  stake_units?: number | null;     // UNITS staked (placed bets only)
  outcome?: string | null;         // win | loss | push | pending
  pnl_units?: number | null;       // settled P&L in UNITS
  clv_pct?: number | null;
  clv_status?: string | null;      // may be "INSUFFICIENT_DATA"
  // Prop identity (market_type=="prop") -- paper_today._PLACED_FIELDS already
  // serves these; without them a placed prop row would describe as bare
  // "AWAY"/"prop" instead of "Player UNDER 0.5 Hits".
  prop_player?: string | null;
  prop_stat?: string | null;
  prop_side?: string | null;
  line?: number | null;
};

// Per-market_type rolling CLV + circuit-breaker state (paper_exec_summary block).
// Breaker gates on median_clv_pct (true-close preferred; "proxy_only" basis is an
// honest fallback), NOT the mean -- see circuit_breaker.py's 2026-07-15
// pre-registered decision. mean_clv_pct is winsorized at +/-50 and context-only.
export type MarketExecState = {
  mean_clv_pct: number | null;
  median_clv_pct: number | null;
  mean_winsorized: boolean;
  n: number;
  n_proxy: number;
  basis: "true_close" | "proxy_only" | null;
  state: "LIVE" | "CAPPED" | "UNKNOWN";
  cap_per_day: number | null;
  placed_today: number | null;
};

export type ExecutionQuality = {
  n_gated: number;
  n_ungated: number;
  avg_expected_clv_pct: number | null;
  median_placement_latency_ms: number | null;
};

// The digest's "execution" block. Absent (older backend) or breaker module not
// yet on disk -> callers must render honest empty/UNKNOWN states, never zeros.
export type ExecutionBlock = {
  by_market_type: Record<string, MarketExecState>;
  quality: ExecutionQuality;
  breaker_module_loaded: boolean;
} | null;

// The digest envelope served by /api/paper/today (or composed in fallback mode).
export type PaperToday = {
  status?: string;                 // "ok" | "unavailable"
  date?: string | null;            // ISO day this digest is for (stale-never-green)
  placed: TodayBet[];              // bets the system actually STAKED today
  pending: TodayBet[];             // staked + not yet graded
  settled_today: TodayBet[];       // graded today (W/L)
  day_units: number | null;        // today's net P&L in UNITS
  cumulative_units: number | null; // all-time net P&L vs start (UNITS)
  bankroll: number | null;         // current bankroll (UNITS)
  start_units: number | null;      // starting bankroll (UNITS)
  // provenance: "today_route" = real placed feed; "fallback" = composed, no placed feed
  source: "today_route" | "fallback";
  reason?: string | null;          // honest note when degraded
  edge_claimed: boolean;           // ALWAYS false
  execution?: ExecutionBlock;      // per-market CLV/breaker/exec-quality (may be absent)
};

function asArray(v: unknown): TodayBet[] {
  return Array.isArray(v) ? (v as TodayBet[]) : [];
}

function asNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

// Compose a digest from the live pnl-series + bankroll endpoints. PLACED bets are
// not available from these, so placed/pending stay empty and we flag it honestly.
function composeFallback(
  pnl: PnlSeries | null,
  bankroll: PaperBankroll | null,
): PaperToday {
  // day_units: the most-recent daily point (today's net, if the writer keyed by day).
  const daily = pnl?.daily ?? [];
  const lastDay = daily.length > 0 ? daily[daily.length - 1] : null;
  const startUnits = bankroll?.start_units ?? pnl?.start_units ?? null;
  const currentUnits =
    bankroll?.current_units ?? pnl?.summary?.current_units ?? null;
  const cumulative =
    pnl?.summary?.total_units ??
    (startUnits != null && currentUnits != null ? currentUnits - startUnits : null);

  // settled_today rows from the last day's settled bets are not enumerated by the
  // series endpoint, so we leave settled_today empty (counts come from day P&L).
  return {
    status: "ok",
    date: lastDay?.day ?? null,
    placed: [],
    pending: [],
    settled_today: [],
    day_units: lastDay?.daily_units ?? null,
    cumulative_units: cumulative,
    bankroll: currentUnits,
    start_units: startUnits,
    source: "fallback",
    reason:
      "placed-bet feed unavailable (/api/paper/today absent) -- showing bankroll " +
      "and P&L from the live series; placed bets cannot be listed honestly here.",
    edge_claimed: false,
  };
}

// Normalize the raw /api/paper/today document into the PaperToday shape.
function normalizeTodayDoc(doc: Record<string, unknown>): PaperToday {
  return {
    status: typeof doc.status === "string" ? doc.status : "ok",
    date: typeof doc.date === "string" ? doc.date : null,
    placed: asArray(doc.placed),
    pending: asArray(doc.pending),
    settled_today: asArray(doc.settled_today),
    day_units: asNum(doc.day_units),
    cumulative_units: asNum(doc.cumulative_units),
    // Bankroll is served as flat *_units keys (the bare 'bankroll' token is banned
    // by the honesty linter). current_units IS the bankroll; both were previously
    // read from non-existent top-level keys -> always null, masked by the fallback.
    bankroll: asNum(doc.current_units),
    start_units: asNum(doc.start_units),
    source: "today_route",
    reason: typeof doc.reason === "string" ? doc.reason : null,
    edge_claimed: false,
    execution: (doc.execution as ExecutionBlock) ?? null,
  };
}

// getPaperToday -- fetch the digest, degrading honestly to the live endpoints.
// NEVER throws (returns a fallback digest on any failure). NEVER fabricates a
// placed bet.
export async function getPaperToday(signal?: AbortSignal): Promise<PaperToday> {
  // 1) Try the same-origin today route.
  const raw = await fetchHonest<Record<string, unknown>>(
    `/api/paper/today`,
    { signal },
  );

  if (!isUnavailable(raw)) {
    return normalizeTodayDoc(raw as Record<string, unknown>);
  }

  // 2) Fallback: compose from the live pnl-series + bankroll endpoints.
  const [pnlRes, bankrollRes] = await Promise.all([
    api.getPaperPnlSeries(signal),
    api.getPaperBankroll(signal),
  ]);
  const pnl = !isUnavailable(pnlRes) ? (pnlRes as PnlSeries) : null;
  const bankroll = !isUnavailable(bankrollRes) ? (bankrollRes as PaperBankroll) : null;

  // If BOTH live endpoints are also down, surface an honest all-unavailable digest.
  if (pnl === null && bankroll === null) {
    return {
      status: "unavailable",
      date: null,
      placed: [],
      pending: [],
      settled_today: [],
      day_units: null,
      cumulative_units: null,
      bankroll: null,
      start_units: null,
      source: "fallback",
      reason:
        "today digest unavailable -- /api/paper/today, pnl/series and bankroll " +
        "all offline. The predict service may be down.",
      edge_claimed: false,
    };
  }

  return composeFallback(pnl, bankroll);
}

// Re-export the Unavailable type for consumer convenience.
export type { Unavailable };
