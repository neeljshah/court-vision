"use client";

// /paper -- REAL settled paper book (primary) + PM trail (secondary honest-empty).
//
// PRIMARY: /api/paper/trail (54 settled rows from the real ledger).
//   - Shows settled (win/loss/push) tally + per-row result + CLV/clv_status.
//   - Open positions shown beneath settled records.
//   - Auto-refresh via useLiveData (pause-on-hidden, last-good, isStale).
//
// SECONDARY: /api/paper/pm/trail (Kalshi/Polymarket).
//   - Honestly labelled "no liquid PM markets right now -- here is why" when empty.
//   - Never shown as the primary record.
//
// HONESTY RAILS:
//   - UNITS only. NO $ P&L column. NO dollar field.
//   - CLV is the only honest calibration yardstick.
//   - stale-never-green: if data is stale the badge turns amber, NEVER green.
//   - Real-money: DENY banner always visible.
//
// UNIT-CONVENTION NOTE (QA #3 / iter10-P2):
//   stake_units / total_exposure_units here reflect Kelly-style (quarter-Kelly)
//   sizing and can exceed 1.0. All values are UNITS, never dollars.

import { useCallback, useState } from "react";
import {
  api,
  isUnavailable,
  type PaperTrail,
  type ClvScoreboard,
  type PnlSeries,
  type PaperOpen,
} from "@/lib/p5api";
import { getPaperToday, type PaperToday } from "@/lib/paperToday";
import { useLiveData } from "@/lib/useLiveData";
import type { Unavailable } from "@/lib/types";
import { Panel, Badge, Unavailable as UnavailablePanel } from "@/components/p6/Primitives";
import { PmTrailTable } from "@/components/paper_pm/PmTrailTable";
import { PaperTrailSettled } from "@/components/paper_pm/PaperTrailSettled";
import { PredictionHistoryPanel } from "@/components/paper_pm/PredictionHistoryPanel";
import { PerMarketClvStrips } from "@/components/paper/PerMarketClvStrips";
import { ExecutionQualityPanel } from "@/components/paper/ExecutionQualityPanel";
import { CircuitBreakerPanel } from "@/components/paper/CircuitBreakerPanel";
import { RealizedIngameClvPanel } from "@/components/paper/RealizedIngameClvPanel";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PaperPageData {
  trail: PaperTrail | null;
  clv: ClvScoreboard | null;
  series: PnlSeries | null;
  // Uncapped open positions (from /api/paper/open) -- the primary trail fetch
  // below is capped at limit=2000 and can drop every open row once settled
  // rows alone fill the cap; this fetch has no limit param, so it is always
  // the true, complete open-book source.
  open: PaperOpen | null;
}

// The capped quarter-Kelly overlay fields the bankroll daemon adds to the series
// (UNITS only; reconciles to the placed bets at their Kelly sizes; no $ field).
interface KellyOverlay {
  kelly_current_units?: number;
  kelly_net_units?: number;
  kelly_n_sized?: number;
  kelly_reconciles?: boolean;
}

function fmtUnits(u: number | null | undefined): string {
  if (u == null || Number.isNaN(u)) return EMPTY_CELL;
  return `${u >= 0 ? "+" : ""}${u.toFixed(2)}u`;
}

// ---------------------------------------------------------------------------
// Freshness display helpers
// ---------------------------------------------------------------------------

function fmtAge(ageSec: number | null): string {
  if (ageSec === null) return "checking";
  if (ageSec < 5) return "just now";
  if (ageSec < 60) return `${ageSec}s ago`;
  const m = Math.round(ageSec / 60);
  return `${m}m ago`;
}

// ---------------------------------------------------------------------------
// CLV stat tiles
// ---------------------------------------------------------------------------

function ClvStatSkeleton({ label }: { label: string }) {
  return (
    <div
      className="rounded-lg bg-bg-subtle px-3 py-2.5"
      aria-busy="true"
      aria-label={`${label} loading`}
    >
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className="mt-0.5 h-7 w-16 animate-pulse rounded bg-slate-700/50"
        role="presentation"
      />
    </div>
  );
}

function ClvStat({
  label,
  value,
  cls,
  sub,
}: {
  label: string;
  value: string;
  cls?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg bg-bg-subtle px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-0.5 font-mono text-lg tabular-nums ${cls ?? "text-foreground"}`}
      >
        {value}
      </div>
      {sub ? (
        <div className="mt-0.5 text-[10px] text-faint">{sub}</div>
      ) : null}
    </div>
  );
}

// headlineClv -- median (true-close) preferred, mean as an honest fallback
// labelled as such until the service is serving median_clv_pct. Note: the
// wire values are already percent-scale (e.g. 35.8687 == 35.87%), NOT a
// 0-1 fraction, so they are divided by 100 before going through fmtPct
// (which multiplies by 100 for the usual fraction inputs elsewhere in the
// app -- passing the raw percent straight in double-multiplies, e.g. the
// 3586.9% bug).
function headlineClv(clv: ClvScoreboard | null): {
  label: string;
  pct: number | null;
} {
  if (clv?.median_clv_pct != null) {
    return { label: "Median CLV (true-close)", pct: clv.median_clv_pct };
  }
  return { label: "Mean CLV (mean, incl. outliers)", pct: clv?.mean_clv_pct ?? null };
}

function headlineClvClass(pct: number | null): string {
  if (pct == null) return "text-foreground";
  if (pct > 0) return "text-success";
  if (pct < 0) return "text-danger";
  return "text-foreground";
}

// ---------------------------------------------------------------------------
// PaperPage
// ---------------------------------------------------------------------------

export default function PaperPage() {
  const [rankMode, setRankMode] = useState(false);

  // Primary fetch: real paper trail + CLV scoreboard.
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<PaperPageData | Unavailable> => {
      const [t, c, s, o] = await Promise.all([
        api.getPaperTrail({ limit: 2000 }, signal),
        api.getPaperClv(signal),
        api.getPaperPnlSeries(signal),
        api.paperOpenSport(undefined, signal),
      ]);
      if (isUnavailable(t)) {
        return {
          status: "unavailable",
          reason: (t as Unavailable).reason ?? "unavailable",
        } as Unavailable;
      }
      return {
        trail: t as PaperTrail,
        clv: isUnavailable(c) ? null : (c as ClvScoreboard),
        series: isUnavailable(s) ? null : (s as PnlSeries),
        open: isUnavailable(o) ? null : (o as PaperOpen),
      };
    },
    [],
  );

  const {
    data,
    lastUpdatedAt,
    ageSec,
    isStale,
    error,
    isLoading,
  } = useLiveData<PaperPageData>(fetcher, {
    intervalMs: 30_000,
    staleAfterSec: 90,
    cacheKey: "paper:page",
  });

  const trail = data?.trail ?? null;
  const clv = data?.clv ?? null;
  const rows = trail?.trail ?? [];

  // Execution-quality feed (today digest's "execution" block: per-market
  // rolling CLV, circuit-breaker state, exec-quality aggregates).
  const todayFetcher = useCallback((s: AbortSignal) => getPaperToday(s), []);
  const {
    data: todayData,
    ageSec: execAgeSec,
    isStale: execStale,
  } = useLiveData<PaperToday>(todayFetcher, {
    intervalMs: 30_000,
    staleAfterSec: 90,
    cacheKey: "paper:today:execution",
  });
  const execution = todayData?.execution ?? null;
  const execAsOf =
    execAgeSec == null
      ? null
      : new Date(Date.now() - Math.max(0, execAgeSec) * 1000).toLocaleTimeString(
          "en-US",
          { hour12: false },
        );

  // Execution engine -> paper bankroll: the FLAT-1u curve (conservative, CLV-reconciling)
  // and the edge-proportional capped quarter-Kelly OVERLAY ("try to make the most -- in
  // UNITS"). Both reconcile to the same placed bets; neither is proven profit.
  const series = data?.series ?? null;
  const kelly = (series ?? {}) as KellyOverlay;
  const flatNet = series?.summary?.total_units ?? null;
  const flatCur = series?.summary?.current_units ?? null;
  const kellyBetter =
    kelly.kelly_net_units != null && flatNet != null
      ? kelly.kelly_net_units > flatNet
      : false;

  // Settled rows are the primary display (win/loss/push graded).
  const settledRows = rows.filter((r) => r.graded && r.status !== "open");
  const hasSettled = settledRows.length > 0;
  // CLV summary: use /api/paper/clv n_bets as authoritative settled count.
  const settledClvCount = clv?.n_bets ?? 0;

  // TRUE (uncapped) totals -- /api/paper/trail hard-caps at limit=2000, which
  // silently drops open rows once settled rows alone fill the cap (the
  // reported bug: "2000 settled / 2000 total" with OPEN showing 0 while
  // hundreds of open bets exist). Fix without touching the human-gated
  // frontend/ route: source the open count from the UNCAPPED /api/paper/open
  // endpoint, and the settled count from /api/paper/clv's raw-ledger tallies
  // (n_bets = gradeable settled, n_no_close = settled-but-no-close -- their
  // sum is the true settled-bet count regardless of the trail page cap).
  const openRowsFull = data?.open?.open ?? [];
  const nOpenTrue = data?.open?.count ?? openRowsFull.length;
  const nSettledTrue = (clv?.n_bets ?? 0) + (clv?.n_no_close ?? 0);
  const nTotalTrue = nSettledTrue + nOpenTrue;

  const showSkeleton = isLoading && data === null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            Paper book
          </h1>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Real settled paper bets -- units only, no dollars. CLV is the
            calibration yardstick.
          </p>
          <p
            data-testid="paper-unit-convention-note"
            className="mt-1 text-[11px] text-faint"
          >
            stake_units reflect{" "}
            <span className="font-medium text-muted-foreground">
              Kelly-style (quarter-Kelly) sizing
            </span>{" "}
            and can exceed 1.0 -- distinct from the bets board&apos;s flat{" "}
            <span className="font-mono text-muted-foreground">1.0-per-bet</span>{" "}
            display. All values are{" "}
            <span className="font-mono text-muted-foreground">UNITS</span>, never
            dollars.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <Badge tone="amber">paper mode</Badge>
          <span
            data-testid="paper-last-updated"
            className={`font-mono text-[10px] ${
              isStale
                ? "text-amber-400"
                : lastUpdatedAt !== null
                ? "text-muted-foreground"
                : "text-faint"
            }`}
          >
            {isStale
              ? `stale: ${fmtAge(ageSec)}`
              : lastUpdatedAt !== null
              ? fmtAge(ageSec)
              : "checking"}
          </span>
        </div>
      </div>

      {/* Real-money DENY banner */}
      <div
        role="alert"
        data-testid="real-money-deny-banner"
        aria-label="Real money is DENIED -- paper mode only"
        className="mb-5 rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-2.5 text-[11px] text-amber-400"
      >
        <span className="font-semibold">Real-money: DENY.</span>{" "}
        Paper mode only. No real money placed. No dollar edge is claimed.
      </div>

      {/* CLV summary strip */}
      <div
        aria-label="CLV summary"
        className="mb-5 grid grid-cols-3 gap-3"
      >
        {showSkeleton ? (
          <>
            <ClvStatSkeleton label="Graded bets" />
            <ClvStatSkeleton label="% beat close" />
            <ClvStatSkeleton label="CLV" />
          </>
        ) : (
          <>
            <ClvStat
              label="Graded bets"
              value={String(settledClvCount > 0 ? settledClvCount : settledRows.length)}
              sub={
                clv?.n_proxy != null ? `n_proxy ${clv.n_proxy}` : undefined
              }
            />
            <ClvStat
              label="% beat close (of true-close graded)"
              value={
                clv?.pct_beat_close != null
                  ? fmtPct(clv.pct_beat_close / 100, false)
                  : EMPTY_CELL
              }
            />
            <ClvStat
              label={headlineClv(clv).label}
              value={
                headlineClv(clv).pct != null
                  ? fmtPct((headlineClv(clv).pct as number) / 100)
                  : EMPTY_CELL
              }
              cls={headlineClvClass(headlineClv(clv).pct)}
            />
          </>
        )}
      </div>

      {/* Execution engine: paper bankroll -- flat (CLV record) vs edge-proportional Kelly */}
      {series ? (
        <Panel
          title="Paper bankroll (UNITS only)"
          right={
            <span className="font-mono text-[10px] text-muted-foreground">
              {kelly.kelly_n_sized != null
                ? `${kelly.kelly_n_sized} sized`
                : "reconciles"}
            </span>
          }
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-slate-800 bg-bg-subtle/30 px-4 py-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Flat 1u (conservative · CLV record)
              </div>
              <div className="mt-1 font-mono text-lg text-foreground">
                {fmtUnits(flatCur)}
              </div>
              <div
                className={`text-[11px] ${
                  flatNet != null && flatNet < 0 ? "text-danger" : "text-success"
                }`}
              >
                net {fmtUnits(flatNet)}
              </div>
            </div>
            <div
              className={`rounded-lg border px-4 py-3 ${
                kellyBetter
                  ? "border-success/40 bg-success/5"
                  : "border-slate-800 bg-bg-subtle/30"
              }`}
            >
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Edge-proportional (capped 1/4-Kelly)
              </div>
              <div className="mt-1 font-mono text-lg text-foreground">
                {fmtUnits(kelly.kelly_current_units)}
              </div>
              <div
                className={`text-[11px] ${
                  kelly.kelly_net_units != null && kelly.kelly_net_units < 0
                    ? "text-danger"
                    : "text-success"
                }`}
              >
                net {fmtUnits(kelly.kelly_net_units)}
              </div>
            </div>
          </div>
          <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground">
            Both curves reconcile to the same placed bets (one position per market). The
            Kelly overlay sizes each bet by conviction to maximise expected UNIT growth --
            it is a paper track record, NOT proven profit and NOT a realized-money figure.
            CLV is the yardstick; no edge is claimed; real money stays default-DENY.
          </p>
        </Panel>
      ) : null}

      {/* Execution-quality panels: per-market rolling CLV, breaker state, quality */}
      <div className="mb-6 flex flex-col gap-4">
        <PerMarketClvStrips execution={execution} asOf={execAsOf} stale={execStale} />
        <CircuitBreakerPanel execution={execution} asOf={execAsOf} stale={execStale} />
        <ExecutionQualityPanel execution={execution} asOf={execAsOf} stale={execStale} />
        <RealizedIngameClvPanel execution={execution} asOf={execAsOf} stale={execStale} />
      </div>

      {/* Honest empty state -- neutral, never red, no fabricated edge claim */}
      {!showSkeleton && !hasSettled && settledClvCount === 0 ? (
        <p
          data-testid="paper-no-settled-bets"
          className="mb-4 text-[11px] text-muted-foreground"
        >
          No settled bets yet -- CLV populates as paper bets grade against the
          close. No edge is claimed.
        </p>
      ) : null}

      {/* PRIMARY: Real settled book */}
      <Panel
        title="Settled book (real paper record)"
        right={
          <span className="font-mono text-[10px] text-muted-foreground">
            {showSkeleton
              ? "loading"
              : `${nSettledTrue} settled / ${nOpenTrue} open / ${nTotalTrue} total`}
          </span>
        }
      >
        {error && data === null ? (
          <UnavailablePanel reason={error} />
        ) : (
          <PaperTrailSettled
            rows={rows}
            openRows={openRowsFull}
            tallyOverride={{ nSettled: nSettledTrue, nOpen: nOpenTrue }}
            loading={isLoading && data === null}
            error={error}
          />
        )}
      </Panel>

      {/* SECONDARY: PM trail -- honestly labelled as no-liquid-markets when empty */}
      <div className="mt-6">
        <Panel
          title="PM trail (Kalshi / Polymarket)"
          right={
            <button
              type="button"
              onClick={() => setRankMode((v) => !v)}
              className={`h-6 rounded-full border px-3 text-[10px] font-mono uppercase tracking-wide transition-colors ${
                rankMode
                  ? "border-amber-700 bg-amber-950/40 text-amber-400"
                  : "border-slate-700 text-muted-foreground hover:text-foreground"
              }`}
            >
              {rankMode ? "ranked: best first" : "rank by best trades"}
            </button>
          }
        >
          {/* PM trail uses rows from the primary trail filtered to kalshi/polymarket.
              If the PM endpoint is genuinely empty (no liquid PM game markets right
              now), show an honest-empty block with explanation -- NOT an error. */}
          <PmTrailTable
            rows={rows.filter((r) => {
              const b = (r.taken_book || "").toLowerCase();
              return b.includes("kalshi") || b.includes("polymarket");
            })}
            loading={isLoading && data === null}
            error={error}
            rankMode={rankMode}
          />
          {/* Honest empty: no PM markets right now */}
          {!isLoading &&
            data !== null &&
            rows.filter((r) => {
              const b = (r.taken_book || "").toLowerCase();
              return b.includes("kalshi") || b.includes("polymarket");
            }).length === 0 ? (
              <div
                data-testid="pm-no-liquid-markets"
                className="mt-3 rounded-lg border border-slate-800 bg-bg-subtle/30 px-4 py-4 text-center text-[11px] text-muted-foreground"
              >
                <span className="font-semibold text-muted-foreground">
                  No liquid PM markets right now.
                </span>{" "}
                Kalshi / Polymarket paper trades appear once the PM daemon places
                bets on live prediction markets. NBA offseason = no liquid in-play
                prices. No edge is claimed.
              </div>
            ) : null}
        </Panel>
      </div>

      {/* Prediction history panel */}
      <div className="mt-6">
        <PredictionHistoryPanel />
      </div>
    </div>
  );
}
