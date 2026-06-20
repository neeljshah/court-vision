"use client";

// RecordsClvStrip.tsx -- W2-records-clv-deep CLV scoreboard strip.
//
// Reads /api/paper/clv (ClvScoreboard) and renders:
//   n_bets | pct_beat_close | mean_clv_pct
//
// Honesty rails:
//   - n_bets=0 -> renders INSUFFICIENT_DATA (never fabricates a CLV%).
//   - error/unavailable -> degrades gracefully, still shows "INSUFFICIENT_DATA".
//   - CLV is proxy (clv_is_proxy) -> rendered with a "(proxy close)" note.
//   - UNITS only. NO $ / ROI / P&L token anywhere. ASCII only.
//   - Under 300 LOC rail.

import type { ClvScoreboard, Unavailable } from "@/lib/types";
import { EMPTY_CELL } from "@/lib/tokens";

// ---------------------------------------------------------------------------
// StatCell
// ---------------------------------------------------------------------------

function StatCell({
  label,
  value,
  tone = "slate",
  note,
}: {
  label: string;
  value: string | number;
  tone?: "slate" | "green" | "red" | "amber" | "muted";
  note?: string;
}) {
  const valueCls = (() => {
    switch (tone) {
      case "green":  return "font-mono text-[14px] font-semibold tabular-nums text-emerald-400";
      case "red":    return "font-mono text-[14px] font-semibold tabular-nums text-rose-400";
      case "amber":  return "font-mono text-[14px] font-semibold tabular-nums text-amber-400";
      case "muted":  return "font-mono text-[14px] font-semibold tabular-nums text-slate-600";
      default:       return "font-mono text-[14px] font-semibold tabular-nums text-slate-200";
    }
  })();

  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[9px] uppercase tracking-widest text-slate-600">
        {label}
      </span>
      <span className={valueCls} data-testid={`clv-strip-${label.toLowerCase().replace(/\s+/g, "-")}`}>
        {value}
      </span>
      {note ? (
        <span className="font-mono text-[9px] text-slate-700">{note}</span>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecordsClvStrip
// ---------------------------------------------------------------------------

interface RecordsClvStripProps {
  /** Already-fetched CLV data (or unavailable sentinel / null while loading). */
  clv:     ClvScoreboard | Unavailable | null;
  loading?: boolean;
}

export function RecordsClvStrip({ clv, loading = false }: RecordsClvStripProps) {
  if (loading) {
    return (
      <div
        data-testid="records-clv-strip"
        aria-label="CLV scoreboard loading"
        className="flex flex-wrap gap-6 rounded border border-slate-800 bg-slate-900/30 px-4 py-3"
      >
        {["n-bets", "beat-close", "mean-clv"].map((k) => (
          <div key={k} className="h-8 w-20 animate-pulse rounded bg-slate-800/50" role="presentation" />
        ))}
      </div>
    );
  }

  // Resolve whether we have real data
  const scoreboard = (clv && (clv as { status?: string }).status !== "unavailable")
    ? (clv as ClvScoreboard)
    : null;

  const nBets         = scoreboard?.n_bets          ?? 0;
  const pctBeatClose  = scoreboard?.pct_beat_close  ?? null;
  const meanClvPct    = scoreboard?.mean_clv_pct    ?? null;
  const isProxy       = scoreboard?.clv_is_proxy    ?? false;
  const insufficient  = nBets === 0 || scoreboard === null;

  // Format mean_clv_pct with sign
  function fmtClv(v: number | null): string {
    if (v == null) return EMPTY_CELL;
    const s = (v * 100).toFixed(1);
    return v >= 0 ? `+${s}%` : `${s}%`;
  }

  // Format pct_beat_close (already a 0-1 fraction or 0-100?)
  // API returns a fraction (0.0-1.0); render as percentage.
  function fmtPctBeat(v: number | null): string {
    if (v == null) return EMPTY_CELL;
    // If value looks like it is already a percentage (>1), show as-is; else scale.
    const pct = v > 1 ? v : v * 100;
    return `${pct.toFixed(1)}%`;
  }

  // Tone for mean CLV
  const meanTone: "green" | "red" | "slate" | "muted" = (() => {
    if (insufficient || meanClvPct == null) return "muted";
    return meanClvPct > 0 ? "green" : meanClvPct < 0 ? "red" : "slate";
  })();

  // Tone for beat-close
  const beatTone: "green" | "red" | "slate" | "muted" = (() => {
    if (insufficient || pctBeatClose == null) return "muted";
    const pct = pctBeatClose > 1 ? pctBeatClose : pctBeatClose * 100;
    return pct >= 55 ? "green" : pct < 45 ? "red" : "slate";
  })();

  return (
    <div
      data-testid="records-clv-strip"
      role="region"
      aria-label="CLV scoreboard"
      className="flex flex-wrap items-end gap-6 rounded border border-slate-800 bg-slate-900/30 px-4 py-3"
    >
      {/* n_bets */}
      <StatCell
        label="graded bets"
        value={nBets}
        tone={nBets > 0 ? "slate" : "muted"}
      />

      {/* Honest INSUFFICIENT_DATA gate */}
      {insufficient ? (
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[9px] uppercase tracking-widest text-slate-600">
            CLV score
          </span>
          <span
            data-testid="clv-strip-insufficient"
            className="font-mono text-[13px] font-semibold text-slate-600"
          >
            INSUFFICIENT_DATA
          </span>
          <span className="font-mono text-[9px] text-slate-700">
            {nBets === 0
              ? "no graded bets with a close yet -- not enough data to score"
              : "CLV service unavailable"}
          </span>
        </div>
      ) : (
        <>
          {/* pct_beat_close */}
          <StatCell
            label="beat close"
            value={fmtPctBeat(pctBeatClose)}
            tone={beatTone}
            note={isProxy ? "(proxy close)" : undefined}
          />

          {/* mean_clv_pct */}
          <StatCell
            label="mean CLV"
            value={fmtClv(meanClvPct)}
            tone={meanTone}
            note={isProxy ? "(proxy close)" : undefined}
          />
        </>
      )}

      {/* Honesty footnote */}
      <span className="self-end font-mono text-[9px] text-slate-700">
        CLV = beat-the-close; calibration only -- not a market edge
      </span>
    </div>
  );
}
