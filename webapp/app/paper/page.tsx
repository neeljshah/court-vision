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
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import type { Unavailable } from "@/lib/types";
import { Panel, Badge, Unavailable as UnavailablePanel } from "@/components/p6/Primitives";
import { PmTrailTable } from "@/components/paper_pm/PmTrailTable";
import { PaperTrailSettled } from "@/components/paper_pm/PaperTrailSettled";
import { PredictionHistoryPanel } from "@/components/paper_pm/PredictionHistoryPanel";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PaperPageData {
  trail: PaperTrail | null;
  clv: ClvScoreboard | null;
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
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
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
}: {
  label: string;
  value: string;
  cls?: string;
}) {
  return (
    <div className="rounded-lg bg-bg-subtle px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div
        className={`mt-0.5 font-mono text-lg tabular-nums ${cls ?? "text-slate-100"}`}
      >
        {value}
      </div>
    </div>
  );
}

function meanClvClass(clv: ClvScoreboard | null): string {
  if (clv?.mean_clv_pct == null) return "text-slate-100";
  if (clv.mean_clv_pct > 0) return "text-success";
  if (clv.mean_clv_pct < 0) return "text-danger";
  return "text-slate-100";
}

// ---------------------------------------------------------------------------
// PaperPage
// ---------------------------------------------------------------------------

export default function PaperPage() {
  const [rankMode, setRankMode] = useState(false);

  // Primary fetch: real paper trail + CLV scoreboard.
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<PaperPageData | Unavailable> => {
      const [t, c] = await Promise.all([
        api.getPaperTrail({ limit: 2000 }, signal),
        api.getPaperClv(signal),
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
  });

  const trail = data?.trail ?? null;
  const clv = data?.clv ?? null;
  const rows = trail?.trail ?? [];

  // Settled rows are the primary display (win/loss/push graded).
  const settledRows = rows.filter((r) => r.graded && r.status !== "open");
  const hasSettled = settledRows.length > 0;
  // CLV summary: use /api/paper/clv n_bets as authoritative settled count.
  const settledClvCount = clv?.n_bets ?? 0;

  const showSkeleton = isLoading && data === null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">
            Paper book
          </h1>
          <p className="mt-0.5 text-[12px] text-slate-500">
            Real settled paper bets -- units only, no dollars. CLV is the
            calibration yardstick.
          </p>
          <p
            data-testid="paper-unit-convention-note"
            className="mt-1 text-[11px] text-slate-600"
          >
            stake_units reflect{" "}
            <span className="font-medium text-slate-500">
              Kelly-style (quarter-Kelly) sizing
            </span>{" "}
            and can exceed 1.0 -- distinct from the bets board&apos;s flat{" "}
            <span className="font-mono text-slate-500">1.0-per-bet</span>{" "}
            display. All values are{" "}
            <span className="font-mono text-slate-500">UNITS</span>, never
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
                ? "text-slate-500"
                : "text-slate-600"
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
            <ClvStatSkeleton label="Mean CLV" />
          </>
        ) : (
          <>
            <ClvStat
              label="Graded bets"
              value={String(settledClvCount > 0 ? settledClvCount : settledRows.length)}
            />
            <ClvStat
              label="% beat close"
              value={
                clv?.pct_beat_close != null
                  ? fmtPct(clv.pct_beat_close, false)
                  : EMPTY_CELL
              }
            />
            <ClvStat
              label="Mean CLV"
              value={
                clv?.mean_clv_pct != null
                  ? fmtPct(clv.mean_clv_pct)
                  : EMPTY_CELL
              }
              cls={meanClvClass(clv)}
            />
          </>
        )}
      </div>

      {/* Honest empty state -- neutral, never red, no fabricated edge claim */}
      {!showSkeleton && !hasSettled && settledClvCount === 0 ? (
        <p
          data-testid="paper-no-settled-bets"
          className="mb-4 text-[11px] text-slate-500"
        >
          No settled bets yet -- CLV populates as paper bets grade against the
          close. No edge is claimed.
        </p>
      ) : null}

      {/* PRIMARY: Real settled book */}
      <Panel
        title="Settled book (real paper record)"
        right={
          <span className="font-mono text-[10px] text-slate-500">
            {showSkeleton
              ? "loading"
              : `${settledRows.length} settled / ${rows.length} total`}
          </span>
        }
      >
        {error && data === null ? (
          <UnavailablePanel reason={error} />
        ) : (
          <PaperTrailSettled
            rows={rows}
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
                  : "border-slate-700 text-slate-500 hover:text-slate-300"
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
                className="mt-3 rounded-lg border border-slate-800 bg-bg-subtle/30 px-4 py-4 text-center text-[11px] text-slate-500"
              >
                <span className="font-semibold text-slate-400">
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
