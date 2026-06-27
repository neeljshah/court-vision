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
import type { PnlSeries, PaperBankroll, ClvScoreboard } from "@/lib/types";

const POLL_MS = 30_000;
const STALE_SEC = 90;

function fmtUnitsSigned(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "--";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}u`;
}

// mean CLV: number -> "+x.x%"; "INSUFFICIENT_DATA" string -> honest passthrough.
function fmtMeanClv(v: number | string | null | undefined): {
  text: string;
  insufficient: boolean;
} {
  if (v == null) return { text: "INSUFFICIENT_DATA", insufficient: true };
  if (typeof v === "string") {
    return { text: v, insufficient: v === "INSUFFICIENT_DATA" };
  }
  if (!Number.isFinite(v)) return { text: "INSUFFICIENT_DATA", insufficient: true };
  const sign = v >= 0 ? "+" : "";
  return { text: `${sign}${(v * 100).toFixed(1)}%`, insufficient: false };
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
      ? "text-emerald-400"
      : tone === "down"
      ? "text-rose-400"
      : tone === "amber"
      ? "text-amber-400"
      : "text-slate-100";
  return (
    <div className="flex flex-col">
      <span className="font-mono text-[9px] uppercase tracking-widest text-slate-500">
        {label}
      </span>
      <span
        className={cn("font-mono text-sm tabular-nums", toneClass)}
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

  const { data: pnlData, isStale } = useLiveData<PnlSeries>(pnlFetcher, {
    intervalMs: POLL_MS,
    staleAfterSec: STALE_SEC,
  });
  const { data: bankData } = useLiveData<PaperBankroll>(bankFetcher, {
    intervalMs: POLL_MS,
    staleAfterSec: STALE_SEC,
  });
  const { data: clvData } = useLiveData<ClvScoreboard>(clvFetcher, {
    intervalMs: POLL_MS,
    staleAfterSec: STALE_SEC,
  });

  const pnl = pnlData && !isUnavailable(pnlData) ? pnlData : null;
  const bank = bankData && !isUnavailable(bankData) ? bankData : null;
  const clv = clvData && !isUnavailable(clvData) ? clvData : null;

  const startUnits = bank?.start_units ?? pnl?.start_units ?? null;
  const curveValues =
    pnl && pnl.points && pnl.points.length > 0
      ? pnl.points.map((p) => p.balance_units)
      : null;

  // net P&L: prefer bankroll delta, else the summary total.
  const netUnits =
    bank != null && startUnits != null
      ? bank.current_units - startUnits
      : pnl?.summary?.total_units ?? null;
  const netTone = netUnits == null ? "slate" : netUnits >= 0 ? "up" : "down";

  const summary = pnl?.summary;
  const nBets = summary?.n_bets ?? 0;
  const winRate = summary?.win_rate;
  const winRateStr =
    winRate != null && Number.isFinite(winRate)
      ? `${(winRate * 100).toFixed(0)}%`
      : "--";
  const recordStr =
    summary != null
      ? `${summary.n_win ?? 0}-${summary.n_loss ?? 0}${
          (summary.n_push ?? 0) > 0 ? `-${summary.n_push}` : ""
        }`
      : "--";

  const meanClv = fmtMeanClv(summary?.mean_clv_pct_or_INSUFFICIENT);

  return (
    <section
      aria-label="paper money headline"
      data-testid="bets-money-headline"
      className="rounded-xl border border-slate-800 bg-bg-panel p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col">
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">
            Money-makers -- paper equity (units)
          </span>
          <span className="mt-0.5 text-[11px] text-slate-400">
            How much you <strong className="text-slate-200">would have made</strong>{" "}
            staking the best bets below. PAPER simulation, units only -- no $.
          </span>
        </div>
        {isStale && pnl != null && (
          <span
            className="font-mono text-[9px] uppercase tracking-wider text-amber-400"
            data-testid="money-headline-stale"
          >
            stale -- last-good
          </span>
        )}
      </div>

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
          value={
            bank != null
              ? `${bank.current_units.toFixed(2)}u`
              : startUnits != null
              ? `${startUnits.toFixed(2)}u`
              : "--"
          }
          testid="money-bankroll"
        />
        <Stat label="graded" value={String(nBets)} testid="money-nbets" />
        <Stat label="record (W-L)" value={recordStr} testid="money-record" />
        <Stat label="win rate" value={winRateStr} testid="money-winrate" />
        <Stat
          label="mean CLV"
          value={meanClv.text}
          tone={meanClv.insufficient ? "amber" : "slate"}
          testid="money-clv"
        />
        <Link
          href="/paper-trading"
          className="ml-auto rounded-md border border-slate-700 px-3 py-1.5 font-mono text-[11px] text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel"
          data-testid="money-equity-cta"
        >
          full equity curve -&gt;
        </Link>
      </div>

      <p className="mt-3 border-t border-slate-800 pt-2 font-mono text-[9px] leading-relaxed text-slate-600">
        {clv != null && clv.n_bets > 0
          ? `${clv.n_bets} graded vs close; beat-close ${
              clv.pct_beat_close != null
                ? `${(clv.pct_beat_close * 100).toFixed(0)}%`
                : "pending"
            }.`
          : "CLV vs-close INSUFFICIENT_DATA until bets grade against a real close."}{" "}
        Paper only -- no $ ROI is claimed; CLV = beat-the-close calibration
        yardstick. Real money is DENY.
      </p>
    </section>
  );
}
