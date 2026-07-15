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
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

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
  tone?: "slate" | "up" | "down" | "stale" | "muted";
  note?: string;
}) {
  const valueCls = (() => {
    switch (tone) {
      case "up":     return "text-[14px] font-semibold text-up";
      case "down":   return "text-[14px] font-semibold text-down";
      case "stale":  return "text-[14px] font-semibold text-stale";
      case "muted":  return "text-[14px] font-semibold text-faint";
      default:       return "text-[14px] font-semibold text-foreground";
    }
  })();

  return (
    <div className="flex flex-col gap-0.5">
      <span className="microlabel">{label}</span>
      <span data-testid={`clv-strip-${label.toLowerCase().replace(/\s+/g, "-")}`}>
        <Num className={valueCls}>{value}</Num>
      </span>
      {note ? (
        <span className="font-data text-[9px] text-faint">{note}</span>
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
  /** Fetch time for the CLV feed (no upstream timestamp exists on this shape). */
  asOf?:   string | null;
}

export function RecordsClvStrip({ clv, loading = false, asOf = null }: RecordsClvStripProps) {
  if (loading) {
    return (
      <div data-testid="records-clv-strip" aria-label="CLV scoreboard loading">
        <Panel>
          <PanelHead title="CLV Scoreboard" asOf={asOf} />
          <div className="flex flex-wrap gap-6 px-4 py-3">
            {["n-bets", "beat-close", "mean-clv"].map((k) => (
              <div key={k} className="h-8 w-20 animate-pulse bg-surface-2" role="presentation" />
            ))}
          </div>
        </Panel>
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
  const meanTone: "up" | "down" | "slate" | "muted" = (() => {
    if (insufficient || meanClvPct == null) return "muted";
    return meanClvPct > 0 ? "up" : meanClvPct < 0 ? "down" : "slate";
  })();

  // Tone for beat-close
  const beatTone: "up" | "down" | "slate" | "muted" = (() => {
    if (insufficient || pctBeatClose == null) return "muted";
    const pct = pctBeatClose > 1 ? pctBeatClose : pctBeatClose * 100;
    return pct >= 55 ? "up" : pct < 45 ? "down" : "slate";
  })();

  return (
    <div data-testid="records-clv-strip" role="region" aria-label="CLV scoreboard">
      <Panel>
        <PanelHead
          title="CLV Scoreboard"
          asOf={asOf}
          right={
            <span className="font-data text-[9px] text-faint">
              beat-the-close; calibration only -- not a market edge
            </span>
          }
        />
        <div className="flex flex-wrap items-end gap-6 px-4 py-3">
          {/* n_bets */}
          <StatCell
            label="graded bets"
            value={nBets}
            tone={nBets > 0 ? "slate" : "muted"}
          />

          {/* Honest INSUFFICIENT_DATA gate */}
          {insufficient ? (
            <div className="flex flex-col gap-0.5">
              <span className="microlabel">CLV score</span>
              <span
                data-testid="clv-strip-insufficient"
                className="font-data text-[13px] font-semibold text-faint"
              >
                INSUFFICIENT_DATA
              </span>
              <span className="font-data text-[9px] text-faint">
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
        </div>
      </Panel>
    </div>
  );
}
