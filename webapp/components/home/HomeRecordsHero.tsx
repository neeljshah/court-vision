"use client";

// HomeRecordsHero -- W6-home-records-hero-nav
// Reads /api/paper/predictions + /api/paper/clv live. Shows headline count,
// top recent records, CLV strip (INSUFFICIENT_DATA when n_bets=0), and CTAs
// to /records and /bets. UNITS only -- no $/roi/profit. Stale-never-green.

import { useCallback } from "react";
import Link from "next/link";
import { api, isUnavailable } from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import type { PaperPredictions, PaperPredictionRow, ClvScoreboard, Unavailable } from "@/lib/types";

const POLL_MS   = 30_000;
const STALE_SEC = 90;
const PREVIEW_ROWS = 8;

function fmtProb(p: number | null | undefined): string {
  if (p == null) return "--";
  return `${(p * 100).toFixed(1)}%`;
}

function fmtOutcome(outcome: string | null | undefined): string {
  if (!outcome) return "pending";
  return outcome.toLowerCase();
}

function fmtTier(tier: string | null | undefined): string {
  if (!tier) return "--";
  return tier;
}

function outcomeClass(outcome: string | null | undefined): string {
  const v = (outcome ?? "").toLowerCase();
  if (v === "win")  return "text-emerald-600 dark:text-emerald-400";
  if (v === "loss") return "text-red-500 dark:text-red-400";
  return "text-muted-foreground";
}

function AgeBadge({
  ageSec,
  isStale,
}: {
  ageSec: number | null;
  isStale: boolean;
}) {
  if (ageSec === null) return null;
  const secs = Math.max(0, ageSec);
  let label: string;
  if (secs < 5)       label = "just now";
  else if (secs < 60) label = `${secs}s ago`;
  else                label = `${Math.floor(secs / 60)}m ago`;

  return (
    <span
      className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground/60"
      data-testid="records-hero-age"
    >
      updated {label}
      {isStale && (
        <span
          className="ml-1.5 text-warning"
          data-testid="records-hero-stale-badge"
          aria-label="data may be stale"
        >
          (stale)
        </span>
      )}
    </span>
  );
}

function PreviewRow({ row }: { row: PaperPredictionRow }) {
  return (
    <tr className="border-b border-border/40 last:border-0">
      <td className="py-1.5 pr-3 text-xs text-foreground truncate max-w-[140px]" data-testid="row-matchup">
        {row.matchup ?? "--"}
      </td>
      <td className="py-1.5 pr-3 text-xs text-muted-foreground truncate max-w-[100px]">
        {row.market_type ?? row.side ?? "--"}
      </td>
      <td className="py-1.5 pr-3 text-xs text-foreground tabular-nums" data-testid="row-model-prob">
        {fmtProb(row.model_prob)}
      </td>
      <td className="py-1.5 pr-3 text-xs text-muted-foreground" data-testid="row-tier">
        {fmtTier(row.tier)}
      </td>
      <td className={`py-1.5 pr-3 text-xs font-medium ${outcomeClass(row.outcome)}`} data-testid="row-outcome">
        {fmtOutcome(row.outcome)}
      </td>
    </tr>
  );
}

function HonestEmpty() {
  return (
    <div
      className="rounded-lg border border-border/50 bg-surface-1/40 px-4 py-6 text-center"
      data-testid="records-hero-empty"
    >
      <p className="text-sm text-muted-foreground">No paper records yet.</p>
      <p className="mt-1 text-xs text-muted-foreground/70">
        Records appear here once the prediction pipeline runs and logs results.
        Paper mode only -- no real-money positions.
      </p>
    </div>
  );
}

function ClvStrip({ clv }: { clv: ClvScoreboard | null }) {
  if (clv === null) {
    return (
      <div
        className="mt-3 rounded border border-border/30 bg-surface-1/30 px-3 py-2"
        data-testid="clv-strip"
        data-clv-state="loading"
      >
        <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground/50">
          CLV -- loading...
        </span>
      </div>
    );
  }

  const nBets = clv.n_bets ?? 0;
  const isInsufficient = nBets === 0;

  return (
    <div
      className="mt-3 rounded border border-border/30 bg-surface-1/30 px-3 py-2"
      data-testid="clv-strip"
      data-clv-state={isInsufficient ? "insufficient" : "ok"}
    >
      <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground/60 mr-3">
        CLV
      </span>
      {isInsufficient ? (
        <span
          className="text-[11px] text-warning"
          data-testid="clv-insufficient"
        >
          INSUFFICIENT_DATA -- n_bets=0; no bets graded against a real close yet.
          Cannot compute a meaningful CLV %.
        </span>
      ) : (
        <span className="text-[11px] text-muted-foreground" data-testid="clv-value">
          n={nBets} graded bets
          {clv.pct_beat_close != null
            ? ` -- beat close: ${(clv.pct_beat_close * 100).toFixed(1)}%`
            : " -- beat-close: pending"}
          {clv.clv_is_proxy && (
            <span className="ml-1.5 text-muted-foreground/60">(proxy close)</span>
          )}
        </span>
      )}
    </div>
  );
}

export function HomeRecordsHero() {
  const predFetcher = useCallback(
    async (signal: AbortSignal): Promise<PaperPredictions | Unavailable> => {
      return api.getPaperPredictions({ limit: PREVIEW_ROWS }, signal);
    },
    [],
  );

  const clvFetcher = useCallback(
    async (signal: AbortSignal): Promise<ClvScoreboard | Unavailable> => {
      return api.getPaperClv(signal);
    },
    [],
  );

  const { data, ageSec, isStale, isLoading, error } = useLiveData<PaperPredictions>(
    predFetcher,
    { intervalMs: POLL_MS, staleAfterSec: STALE_SEC },
  );

  const { data: clvData } = useLiveData<ClvScoreboard>(
    clvFetcher,
    { intervalMs: POLL_MS, staleAfterSec: STALE_SEC },
  );

  // Resolve CLV: null when not yet loaded, or null when unavailable sentinel.
  const clv: ClvScoreboard | null =
    clvData && !isUnavailable(clvData) ? (clvData as ClvScoreboard) : null;

  // While loading and no data yet -- neutral skeleton
  if (isLoading && data === null) {
    return (
      <section
        className="mx-auto max-w-5xl px-4 py-6 sm:px-6"
        aria-label="paper bets record loading"
        data-testid="records-hero-loading"
      >
        <div className="rounded-lg border border-border bg-surface-1/60 p-5">
          <p className="text-xs text-muted-foreground/60">Loading paper bets record...</p>
        </div>
      </section>
    );
  }

  // Unavailable / error -- degrade honestly
  if (!data || isUnavailable(data) || error) {
    return (
      <section
        className="mx-auto max-w-5xl px-4 py-6 sm:px-6"
        aria-label="paper bets record unavailable"
        data-testid="records-hero-unavailable"
      >
        <div className="rounded-lg border border-border bg-surface-1/60 p-5">
          <p className="text-xs text-muted-foreground">
            Paper bets record temporarily unavailable. The predict service may be
            offline. Data will refresh automatically.
          </p>
        </div>
      </section>
    );
  }

  const total = data.count ?? 0;
  const rows  = (data.predictions ?? []).slice(0, PREVIEW_ROWS);

  return (
    <section
      className="mx-auto max-w-5xl px-4 py-6 sm:px-6"
      aria-label="paper bets record"
    >
      <div className="rounded-lg border border-border bg-surface-1/60 p-5">

        {/* Header row */}
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              My Paper Bets / Records
            </p>
            <div className="mt-1 flex items-baseline gap-2">
              <span
                className="text-3xl font-semibold tabular-nums text-foreground"
                data-testid="records-hero-total"
              >
                {total.toLocaleString()}
              </span>
              <span className="text-sm text-muted-foreground">
                total paper predictions
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground/70">
              Units only -- no real-money positions; calibration, not edge.
            </p>
          </div>
          <AgeBadge ageSec={ageSec} isStale={isStale} />
        </div>

        {/* Preview table or honest-empty */}
        {total === 0 ? (
          <HonestEmpty />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[440px] text-left" data-testid="records-hero-table">
              <thead>
                <tr className="border-b border-border/60">
                  {["Matchup", "Market/Side", "Model prob", "Tier", "Result"].map(
                    (h) => (
                      <th
                        key={h}
                        className="pb-1.5 pr-3 font-mono text-[9px] uppercase tracking-wider text-muted-foreground"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <PreviewRow key={row.game_id ?? row.ts ?? i} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* CLV strip */}
        <ClvStrip clv={clv} />

        {/* CTA links -- primary: /records and /bets */}
        <div className="mt-4 flex flex-wrap gap-3">
          <Link
            href="/records"
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
            data-testid="cta-records"
          >
            All records -&gt;
          </Link>
          <Link
            href="/bets"
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
            data-testid="cta-bets"
          >
            Bets -&gt;
          </Link>
        </div>
      </div>
    </section>
  );
}
