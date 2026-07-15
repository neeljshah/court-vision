"use client";

// ProgressView -- the client orchestrator for /progress. Fetches the honest
// progress payload ONCE from the frozen @/lib/api getProgress() and distributes
// the REAL data to the presentational panels. Everything here is COVERAGE /
// COMPLETENESS / engine-readiness -- NEVER a live accuracy or edge climb. The
// model is STATIC until the self-improve gate is enabled. NO $ field anywhere.

import { useEffect, useState } from "react";
import { getProgress, type ProgressPayload } from "@/lib/api";
import { Unavailable } from "@/components/p6/Primitives";
import { CoverageBars } from "./CoverageBars";
import { VerdictTally } from "./VerdictTally";
import { VerdictTrend } from "./VerdictTrend";
import { BacklogBurndown } from "./BacklogBurndown";
import { CompletenessStrip } from "./CompletenessStrip";
import { WhatsNext } from "./WhatsNext";
import { ClvOverTimePanel } from "@/components/system/ClvOverTimePanel";

export function ProgressView() {
  const [data, setData] = useState<ProgressPayload | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    getProgress(ac.signal).then(setData);
    return () => ac.abort();
  }, []);

  if (!data) {
    return <p className="text-sm text-muted-foreground">loading progress...</p>;
  }

  const snap = data.snapshot;
  // Prefer the append-only series for the trend; fall back to the reconstructed
  // verdict-mtime history (both are REAL coverage/verdict trends, never accuracy).
  const history =
    data.series && data.series.length > 1
      ? data.series.map((s) => ({
          ts: s.ts,
          date_et: s.date_et,
          n_verdicts_cumulative: Object.values(s.per_sport).reduce(
            (a, p) => a + (p.n_tested ?? 0),
            0,
          ),
          backlog_total: s.backlog_total,
          model_static: true as const,
          edge_claimed: false as const,
        }))
      : data.reconstructed_history;

  return (
    <div className="flex flex-col gap-4">
      {data.status === "unavailable" || !snap ? (
        <Unavailable
          reason={
            data.reason ||
            "progress snapshot unavailable -- honest empty, never green-on-missing"
          }
        />
      ) : (
        <>
          {/* COMPLETENESS + engine readiness (the model-static fact up front). */}
          <CompletenessStrip
            parityGreen={snap.parity_green}
            engineReady={snap.engine_ready}
            engineEnabled={snap.engine_enabled || data.engine_enabled}
          />

          {/* COVERAGE growth (per-sport) | the REAL recorded-verdict trend. */}
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 lg:col-span-6">
              <CoverageBars perSport={snap.per_sport} />
            </div>
            <div className="col-span-12 lg:col-span-6">
              <VerdictTrend history={history} />
            </div>
          </div>

          {/* Gate-verdict tally (SHIP survivors highlighted) | backlog burn-down. */}
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 lg:col-span-6">
              <VerdictTally perSport={snap.per_sport} />
            </div>
            <div className="col-span-12 lg:col-span-6">
              <BacklogBurndown
                total={snap.backlog_total}
                remaining={snap.backlog_remaining}
              />
            </div>
          </div>

          {/* CLV over time (measurement-only, INSUFFICIENT_DATA honest) | what's next. */}
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 lg:col-span-5">
              <ClvOverTimePanel />
            </div>
            <div className="col-span-12 lg:col-span-7">
              <WhatsNext />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
