"use client";

// BetsMoneyHeadline.tsx -- the July 2026 model snapshot's simulated paper equity
// atop /bets, labelled as that snapshot (simulated units, not the forward record).
// CLV renders the site-wide Unavailable sentence (lib/clvUnavailable.ts): no
// closing-line-value reading exists (JOB_EVIDENCE_PACKET s4/s5).
//
// Data: GET /api/paper/pnl/series + /api/paper/bankroll, polled
// via useLiveData (pause-on-hidden, last-good, stale-never-green).
//
// HONESTY RAILS:
//   - UNITS only -- there is NO $ figure anywhere; this is a PAPER simulation.
//   - net P&L colored up/down but labeled "paper units", never a $ profit.
//   - < 2 equity points -> EquitySparkline renders an honest "no curve yet" note.
//   - edge_claimed / executed are ALWAYS false; no edge is claimed.

import { useCallback } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { api, isUnavailable } from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { EquitySparkline } from "@/components/home/EquitySparkline";
import { PanelHead } from "@/components/ui/terminal";
import { PaperSourceTime } from "./PaperSummaryProvenance";
import { Unavailable } from "@/components/p6/Primitives";
import { CLV_UNAVAILABLE, JULY_SNAPSHOT_LABEL } from "@/lib/clvUnavailable";
import type { PnlSeries, PaperBankroll } from "@/lib/types";

type DatedPnlSeries = PnlSeries & { generated_at?: string | null };

const POLL_MS = 30_000;
const STALE_SEC = 90;

function finiteValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function countValue(value: unknown): number | null {
  const count = finiteValue(value);
  return count != null && Number.isSafeInteger(count) && count >= 0 ? count : null;
}

function fmtUnitsSigned(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "--";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}u`;
}

function Stat({
  label,
  value,
  tone = "slate",
  testid,
}: {
  label: string;
  value: string;
  tone?: "slate" | "up" | "down" | "amber";
  testid?: string;
}) {
  const toneClass =
    tone === "up"
      ? "text-up"
      : tone === "down"
      ? "text-down"
      : tone === "amber"
      ? "text-stale"
      : "text-foreground";
  return (
    <div className="flex flex-col">
      <span className="microlabel">
        {label}
      </span>
      <span
        className={cn("font-data tabular text-sm", toneClass)}
        data-testid={testid}
      >
        {value}
      </span>
    </div>
  );
}

export function BetsMoneyHeadline() {
  const pnlFetcher = useCallback(
    (s: AbortSignal) => api.getPaperPnlSeries(s) as Promise<PnlSeries>,
    [],
  );
  const bankFetcher = useCallback(
    (s: AbortSignal) => api.getPaperBankroll(s) as Promise<PaperBankroll>,
    [],
  );

  const { data: pnlData, isStale: pnlStale } = useLiveData<DatedPnlSeries>(pnlFetcher, {
    intervalMs: POLL_MS,
    staleAfterSec: STALE_SEC,
  });
  const { data: bankData, isStale: bankStale } = useLiveData<PaperBankroll>(bankFetcher, {
    intervalMs: POLL_MS,
    staleAfterSec: STALE_SEC,
  });

  const pnl = pnlData && !isUnavailable(pnlData) ? pnlData : null;
  const bank = bankData && !isUnavailable(bankData) ? bankData : null;

  const bankStart = finiteValue(bank?.start_units);
  const bankCurrent = finiteValue(bank?.current_units);
  const startUnits = bankStart ?? finiteValue(pnl?.start_units);
  const retainedStale = (pnl != null && pnlStale) || (bank != null && bankStale);
  const curveValues =
    pnl && pnl.points && pnl.points.length > 0
      ? pnl.points.map((p) => p.balance_units)
      : null;

  // A bankroll delta requires both operands from the same feed.
  const bankDelta = bankCurrent != null && bankStart != null
    ? finiteValue(bankCurrent - bankStart) : null;
  const netUnits = bankDelta ?? finiteValue(pnl?.summary?.total_units);
  const netTone = netUnits == null ? "slate" : netUnits >= 0 ? "up" : "down";

  const summary = pnl?.summary;
  const nBets = countValue(summary?.n_bets);
  const wins = countValue(summary?.n_win);
  const losses = countValue(summary?.n_loss);
  const pushes = countValue(summary?.n_push);
  const winRate = summary?.win_rate;
  const winRateStr =
    winRate != null && Number.isFinite(winRate)
      ? `${(winRate * 100).toFixed(0)}%`
      : "--";
  const recordStr =
    wins != null && losses != null
      ? `${wins}-${losses}${pushes != null && pushes > 0 ? `-${pushes}` : ""}`
      : "--";


  return (
    <section
      aria-label="July 2026 model snapshot paper equity"
      data-testid="bets-money-headline"
      className="border border-border bg-card"
    >
      <PanelHead
        title="Paper equity -- July 2026 model snapshot (simulated units)"
        right={
          retainedStale ? (
            <span
              className="font-data text-xs uppercase tracking-wider text-stale"
              data-testid="money-headline-stale"
            >
              stale -- last-good
            </span>
          ) : undefined
        }
      />
      <div className="p-4">
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 font-data text-xs text-muted-foreground">
        <span>P&amp;L snapshot generated: <PaperSourceTime value={pnl?.generated_at} /></span>
        <span>Bankroll updated: <PaperSourceTime value={bank?.updated_at} /></span>
      </div>
      <p className="text-xs text-muted-foreground" data-testid="money-snapshot-label">
        {JULY_SNAPSHOT_LABEL}. Paper simulation, units only -- no $.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex items-center gap-3">
          <EquitySparkline values={curveValues} startUnits={startUnits} width={140} height={38} />
        </div>
        <Stat
          label="net simulated units"
          value={fmtUnitsSigned(netUnits)}
          tone={netTone}
          testid="money-net-units"
        />
        <Stat
          label="bankroll (u)"
          value={bankCurrent != null ? `${bankCurrent.toFixed(2)}u` : "--"}
          testid="money-bankroll"
        />
        <Stat label="graded" value={nBets != null ? String(nBets) : "--"} testid="money-nbets" />
        <Stat label={pushes != null && pushes > 0 ? "record (W-L-P)" : "record (W-L)"} value={recordStr} testid="money-record" />
        <Stat label="win rate" value={winRateStr} testid="money-winrate" />
        <Link
          href="/paper-trading"
          className="ml-auto border border-border px-3 py-1.5 font-data text-xs text-muted-foreground transition-colors hover:border-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-card"
          data-testid="money-equity-cta"
        >
          full equity curve -&gt;
        </Link>
      </div>

      <div className="mt-3" data-testid="money-clv">
        <Unavailable reason={CLV_UNAVAILABLE} />
      </div>
      </div>
    </section>
  );
}
