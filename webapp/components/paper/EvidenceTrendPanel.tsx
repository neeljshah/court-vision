"use client";

// EvidenceTrendPanel.tsx -- per-market CLV trend strip from the m44 append-only
// evidence series (data/frontend/exec_evidence_series.jsonl, one vintage/hour).
// The series is BRAND NEW (currently ~1-2 lines) -- the honest short-series
// state is the point of this panel right now, not a fake chart.
//
// Polls GET /api/evidence itself at a slow (5min) cadence -- no page-level
// wiring needed beyond the render slot.
//
// HONESTY RAILS: UNITS/percent only, no $. <3 daily points per market -> show
// "evidence accumulating", never a fabricated trend line. ASCII only. <=300 LOC.

import { useCallback } from "react";
import type { Unavailable } from "@/lib/types";
import { fetchHonest } from "@/lib/fetchHonest";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { Sparkline } from "@/components/Sparkline";
import { EMPTY_CELL } from "@/lib/tokens";
import type { EvidenceResponse } from "@/app/(terminal)/api/evidence/_lib";

const MIN_TREND_POINTS = 3;

function fmtPctSigned(v: number | null): string {
  if (v == null) return EMPTY_CELL;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function EvidenceTrendPanel({ asOf, stale }: { asOf?: string | null; stale?: boolean }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => fetchHonest<EvidenceResponse>("/api/evidence", { signal }),
    [],
  );
  const { data, ageSec, isStale, error, isLoading } = useLiveData<EvidenceResponse>(fetcher, {
    intervalMs: 300_000,
    staleAfterSec: 900,
    cacheKey: "paper:evidence-trend",
  });

  const markets = Object.keys(data?.series_by_market ?? {}).sort();
  const nVintages = data?.n_vintages ?? 0;
  // useLiveData's isLoading only flips false after a SUCCESSFUL fetch -- a
  // first-load failure leaves it true forever, so gate the skeleton on the
  // absence of an error too (otherwise the honest empty state never shows).
  const showSkeleton = isLoading && data === null && !error;
  const showEmpty = !showSkeleton && (!!error || markets.length === 0);
  const effAsOf = asOf ?? (data?.as_of ?? undefined);
  const effStale = stale ?? isStale;

  return (
    <div data-testid="evidence-trend-panel">
      <Panel>
        <PanelHead title="Evidence trend (CLV over time)" asOf={effAsOf ?? null} stale={effStale} />
        {showSkeleton ? (
          <p className="px-4 py-3 text-[11px] text-faint">loading evidence series...</p>
        ) : showEmpty ? (
          <p
            data-testid="evidence-trend-short-series"
            className="px-4 py-3 text-[11px] text-faint"
          >
            Evidence accumulating -- {nVintages} hourly vintage{nVintages === 1 ? "" : "s"} so far,
            trend appears after 3+ days. No edge is claimed.
          </p>
        ) : (
          <div className="flex flex-col gap-2 px-4 py-3">
            {markets.map((market) => {
              const series = data!.series_by_market[market];
              const latest = data!.latest[market];
              const hasTrend = series.length >= MIN_TREND_POINTS;
              return (
                <div
                  key={market}
                  data-testid={`evidence-trend-row-${market}`}
                  className="flex items-center gap-4"
                >
                  <span className="microlabel w-24">{market}</span>
                  <Num
                    className={`text-[13px] font-semibold ${
                      latest?.median_clv_pct != null
                        ? latest.median_clv_pct >= 0
                          ? "text-up"
                          : "text-down"
                        : "text-faint"
                    }`}
                  >
                    {fmtPctSigned(latest?.median_clv_pct ?? null)}
                  </Num>
                  {hasTrend ? (
                    <Sparkline
                      data={series.map((p) => p.median_clv_pct ?? 0)}
                      positive={(latest?.median_clv_pct ?? 0) >= 0}
                    />
                  ) : (
                    <span
                      data-testid={`evidence-trend-market-short-${market}`}
                      className="text-[10px] text-faint"
                    >
                      {series.length} day{series.length === 1 ? "" : "s"} -- trend after 3+ days
                    </span>
                  )}
                  <span className="font-data text-[9px] text-faint">n={latest?.n ?? 0}</span>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
