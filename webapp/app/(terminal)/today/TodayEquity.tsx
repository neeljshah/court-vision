"use client";

// TodayEquity.tsx -- the FULL paper equity curve + bankroll panel for /today.
// Reuses PaperEquityPanel (the same component /paper-trading renders) so the
// "how much you WOULD have made" money view is front-and-center on the morning
// view too. Live-refresh via useLiveData (30s poll).
//
// HONESTY RAILS: UNITS only -- NO $ token; PAPER; edge_claimed=false; real-money
// DENY; INSUFFICIENT_DATA surfaced verbatim. Degrades honestly when the series /
// bankroll endpoints are offline (PaperEquityPanel renders its honest empty).

import { useCallback } from "react";
import { useLiveData } from "@/lib/useLiveData";
import { api, isUnavailable } from "@/lib/p5api";
import type { PnlSeries, PaperBankroll } from "@/lib/types";
import { PaperEquityPanel } from "@/components/paper/PaperEquityPanel";

const POLL_MS = 30_000;
const STALE_SEC = 90;

export function TodayEquity() {
  const pnlFetcher = useCallback((s: AbortSignal) => api.getPaperPnlSeries(s), []);
  const bankrollFetcher = useCallback((s: AbortSignal) => api.getPaperBankroll(s), []);

  const { data: pnlRaw, isLoading } =
    useLiveData<PnlSeries>(pnlFetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC, cacheKey: "today:pnl" });
  const { data: bankrollRaw } =
    useLiveData<PaperBankroll>(bankrollFetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC, cacheKey: "today:bankroll" });

  const pnl: PnlSeries | null = pnlRaw && !isUnavailable(pnlRaw) ? (pnlRaw as PnlSeries) : null;
  const bankroll: PaperBankroll | null =
    bankrollRaw && !isUnavailable(bankrollRaw) ? (bankrollRaw as PaperBankroll) : null;

  return (
    <section
      className="mx-auto max-w-5xl px-4 pt-2 sm:px-6"
      aria-label="paper equity curve"
      data-testid="today-equity"
    >
      <h2 className="microlabel mb-2">
        how much you would have made -- paper, units
      </h2>
      <PaperEquityPanel series={pnl} bankroll={bankroll} loading={isLoading && pnl === null} />
      <p className="mb-8 mt-1 text-center font-data text-[10px] text-faint">
        This is a PAPER track record / hypothesis -- units, not dollars. CLV
        (beat-the-close) is the yardstick (INSUFFICIENT_DATA at small-N), not a
        realized profit. Real-money: DENY. No edge is claimed.
      </p>
    </section>
  );
}
