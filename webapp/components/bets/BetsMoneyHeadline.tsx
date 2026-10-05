"use client";

// BetsMoneyHeadline.tsx -- the money-geared hero atop /bets. Frames the best-bets
// board below as the money-makers: it shows the paper equity curve ("how much you
// WOULD have made" in UNITS), net P&L, graded win record, and mean CLV -- the
// headline outcome of staking the system's best bets.
//
// Data: GET /api/paper/pnl/series + /api/paper/bankroll + /api/paper/clv, polled
// via useLiveData (pause-on-hidden, last-good, stale-never-green).
//
// HONESTY RAILS:
//   - UNITS only -- there is NO $ figure anywhere; this is a PAPER simulation.
//   - net P&L colored up/down but labeled "paper units", never a $ profit.
//   - mean CLV may be INSUFFICIENT_DATA (string) -> shown honestly, never greened.
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
import type { PnlSeries, PaperBankroll, ClvScoreboard } from "@/lib/types";

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

// Mean CLV arrives in percent units; sentinel strings pass through unchanged.
function fmtMeanClv(v: number | string | null | undefined): {
  text: string;
  insufficient: boolean;
} {
  if (v == null) return { text: "--", insufficient: true };
  if (typeof v === "string") {
    return { text: v, insufficient: v === "INSUFFICIENT_DATA" };
  }
  if (!Number.isFinite(v)) return { text: "--", insufficient: true };
  const sign = v >= 0 ? "+" : "";
  return { text: `${sign}${v.toFixed(1)}%`, insufficient: false };
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
  const clvFetcher = useCallback(
    (s: AbortSignal) => api.getPaperClv(s) as Promise<ClvScoreboard>,
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
  const { data: clvData, isStale: clvStale } = useLiveData<ClvScoreboard>(clvFetcher, {
    intervalMs: POLL_MS,
    staleAfterSec: STALE_SEC,
  });

  const pnl = pnlData && !isUnavailable(pnlData) ? pnlData : null;
  const bank = bankData && !isUnavailable(bankData) ? bankData : null;
  const clv = clvData && !isUnavailable(clvData) ? clvData : null;

  const bankStart = finiteValue(bank?.start_units);
  const bankCurrent = finiteValue(bank?.current_units);
  const startUnits = bankStart ?? finiteValue(pnl?.start_units);
  const retainedStale = (pnl != null && pnlStale) || (bank != null && bankStale) ||
    (clv != null && clvStale);
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

  const meanClv = summary != null ? fmtMeanClv(summary.mean_clv_pct_or_INSUFFICIENT)
    : { text: "--", insufficient: true };
  const closeCount = countValue(clv?.n_bets);
  const closeRate = finiteValue(clv?.pct_beat_close);

  return (
    <section
      aria-label="paper money headline"
      data-testid="bets-money-headline"
      className="border border-border bg-card"
    >
      <PanelHead
        title="Money-makers -- paper equity (units)"
        right={
          retainedStale ? (
            <span
              className="font-data text-[9px] uppercase tracking-wider text-stale"
              data-testid="money-headline-stale"
            >
              stale -- last-good
            </span>
          ) : undefined
        }
      />
      <div className="p-4">
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 font-data text-[11px] text-muted-foreground">
        <span>P&amp;L snapshot generated: <PaperSourceTime value={pnl?.generated_at} /></span>
        <span>Bankroll updated: <PaperSourceTime value={bank?.updated_at} /></span>
        <span>CLV scoreboard time: unavailable</span>
      </div>
      <p className="text-[11px] text-muted-foreground">
        How much you <strong className="text-foreground">would have made</strong>{" "}
        staking the best bets below. PAPER simulation, units only -- no $.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex items-center gap-3">
          <EquitySparkline values={curveValues} startUnits={startUnits} width={140} height={38} />
        </div>
        <Stat
          label="net paper P&L"
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
        <Stat
          label="mean CLV"
          value={meanClv.text}
          tone={meanClv.insufficient ? "amber" : "slate"}
          testid="money-clv"
        />
        <Link
          href="/paper-trading"
          className="ml-auto border border-border px-3 py-1.5 font-data text-[11px] text-muted-foreground transition-colors hover:border-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-card"
          data-testid="money-equity-cta"
        >
          full equity curve -&gt;
        </Link>
      </div>

      <p className="mt-3 border-t border-border pt-2 font-data text-[9px] leading-relaxed text-faint">
        {closeCount == null ? "CLV scoreboard unavailable." : closeCount > 0
          ? `${closeCount} graded vs close; beat-close ${
              closeRate != null
                ? `${closeRate.toFixed(0)}%`
                : "pending"
            }.`
          : "CLV vs-close INSUFFICIENT_DATA until bets grade against a real close."}{" "}
        Paper only -- no $ ROI is claimed; CLV = beat-the-close calibration
        yardstick. Real money is DENY.
      </p>
      </div>
    </section>
  );
}
