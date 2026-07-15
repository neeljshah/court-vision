"use client";

// PaperEquityPanel.tsx -- BANKROLL + EQUITY CURVE for /paper-trading.
//
// Reads GET /api/paper/pnl/series + GET /api/paper/bankroll (both UNITS only).
// Renders:
//   - current balance vs start in UNITS + net P&L in UNITS
//   - cumulative-units line chart over points[] ("how much I would have made")
//   - a daily P&L mini strip from daily[]
//   - a tally (n_bets / W-L / win_rate / mean CLV)
//
// HONESTY RAILS:
//   - PAPER simulation; UNITS not $ -- NO "$" token anywhere.
//   - edge_claimed=false -> NO profit/edge claim language.
//   - mean_clv_pct_or_INSUFFICIENT shown as "CLV: INSUFFICIENT_DATA" honestly
//     when that's the value; never fabricated.
//   - Unavailable -> honest empty state, never a fabricated curve.
//   - ASCII only. Under 300 LOC (chart split into PaperEquityChart.tsx).

import type { PnlSeries, PaperBankroll } from "@/lib/types";
import { PaperEquityChart, fmtUnits, fmtSignedUnits } from "./PaperEquityChart";

// ---------------------------------------------------------------------------
// CLV display -- number -> "+1.23%"; "INSUFFICIENT_DATA" surfaced verbatim.
// ---------------------------------------------------------------------------

function clvDisplay(v: number | string | null | undefined): {
  text: string;
  cls: string;
} {
  if (v === null || v === undefined || v === "INSUFFICIENT_DATA") {
    return { text: "INSUFFICIENT_DATA", cls: "text-muted-foreground" };
  }
  if (typeof v === "string") {
    // any other string (e.g. "UNPROVEN") surfaced verbatim, never greened
    return { text: v, cls: "text-muted-foreground" };
  }
  const sign = v >= 0 ? "+" : "";
  const cls = v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-foreground";
  return { text: `${sign}${(v * 100).toFixed(2)}%`, cls };
}

// ---------------------------------------------------------------------------
// Tile
// ---------------------------------------------------------------------------

function Tile({
  label,
  value,
  valueCls,
  sub,
  testId,
}: {
  label: string;
  value: string;
  valueCls?: string;
  sub?: string;
  testId?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-bg-subtle px-3 py-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={`mt-1 font-mono text-lg tabular-nums ${valueCls ?? "text-foreground"}`}
        data-testid={testId}
      >
        {value}
      </div>
      {sub ? <div className="mt-0.5 font-mono text-[9px] text-faint">{sub}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Daily P&L mini strip -- last N days as small signed-unit bars.
// ---------------------------------------------------------------------------

function DailyStrip({ daily }: { daily: PnlSeries["daily"] }) {
  if (!daily || daily.length === 0) {
    return (
      <p
        data-testid="paper-daily-empty"
        className="font-mono text-[10px] text-faint"
      >
        no settled days yet -- day units appear once paper bets grade
      </p>
    );
  }
  const recent = daily.slice(-14);
  const maxAbs = Math.max(1e-9, ...recent.map((d) => Math.abs(d.daily_units)));
  return (
    <ul
      className="flex flex-wrap items-end gap-2"
      aria-label="Daily paper units (last 14 days)"
      data-testid="paper-daily-strip"
    >
      {recent.map((d, i) => {
        const up = d.daily_units >= 0;
        const h = 6 + Math.round((Math.abs(d.daily_units) / maxAbs) * 28);
        return (
          <li
            key={`${d.day}-${i}`}
            className="flex flex-col items-center gap-1"
            title={`${d.day}: ${fmtSignedUnits(d.daily_units)}u`}
          >
            <span
              className={`block w-3 rounded-sm ${up ? "bg-emerald-600/70" : "bg-rose-600/70"}`}
              style={{ height: `${h}px` }}
              aria-hidden="true"
            />
            <span className="font-mono text-[8px] text-faint">
              {d.day ? d.day.slice(5) : "--"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// PaperEquityPanel -- main export.
// ---------------------------------------------------------------------------

export interface PaperEquityPanelProps {
  series: PnlSeries | null;
  bankroll: PaperBankroll | null;
  loading?: boolean;
}

export function PaperEquityPanel({ series, bankroll, loading }: PaperEquityPanelProps) {
  const isUnavail =
    series === null ||
    (series as { status?: string }).status === "unavailable" ||
    !Array.isArray(series.points);

  // Prefer the bankroll endpoint for start/current; fall back to series summary.
  const startUnits =
    bankroll?.start_units ?? series?.start_units ?? null;
  const currentUnits =
    bankroll?.current_units ?? series?.summary?.current_units ?? null;
  const netUnits =
    startUnits != null && currentUnits != null ? currentUnits - startUnits : null;

  const summary = !isUnavail ? series!.summary : null;
  const clv = clvDisplay(summary?.mean_clv_pct_or_INSUFFICIENT);
  const winRate =
    summary?.win_rate != null ? `${(summary.win_rate * 100).toFixed(0)}%` : "--";

  return (
    <section
      data-testid="paper-equity-panel"
      aria-label="Paper bankroll and equity curve"
      className="mb-6 rounded-xl border border-slate-800 bg-bg-panel"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-2.5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Bankroll &amp; equity curve
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-wide text-amber-400">
          paper simulation -- units, not $
        </span>
      </header>

      <div className="p-4">
        {/* Headline balance */}
        <div
          className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1"
          data-testid="paper-balance-headline"
        >
          {loading && currentUnits == null ? (
            <div className="h-8 w-48 animate-pulse rounded bg-slate-700/40" aria-busy="true" />
          ) : currentUnits != null && startUnits != null ? (
            <>
              <span className="font-mono text-3xl font-semibold tabular-nums text-foreground">
                {fmtUnits(currentUnits)}
              </span>
              <span className="font-mono text-sm text-muted-foreground">
                / {fmtUnits(startUnits)} units
              </span>
              {netUnits != null && (
                <span
                  data-testid="paper-net-units"
                  className={`font-mono text-sm font-semibold tabular-nums ${
                    netUnits > 0
                      ? "text-emerald-400"
                      : netUnits < 0
                        ? "text-rose-400"
                        : "text-foreground"
                  }`}
                >
                  net {fmtSignedUnits(netUnits)}u
                </span>
              )}
            </>
          ) : (
            <span className="font-mono text-sm text-muted-foreground">
              bankroll unavailable -- no paper book yet
            </span>
          )}
        </div>

        {/* Equity curve */}
        <div className="mb-4">
          <PaperEquityChart
            points={isUnavail ? null : series!.points}
            startUnits={startUnits}
            honestNote={isUnavail ? series?.reason : series?.honest_note}
            loading={loading}
          />
        </div>

        {/* Tally tiles */}
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Tile
            label="Bets"
            testId="paper-tally-bets"
            value={summary ? String(summary.n_bets) : "--"}
          />
          <Tile
            label="W - L"
            testId="paper-tally-wl"
            value={summary ? `${summary.n_win} - ${summary.n_loss}` : "--"}
          />
          <Tile
            label="Win rate"
            testId="paper-tally-winrate"
            value={winRate}
          />
          <Tile
            label="Push"
            testId="paper-tally-push"
            value={summary ? String(summary.n_push) : "--"}
          />
          <Tile
            label="CLV (mean)"
            testId="paper-tally-clv"
            value={clv.text}
            valueCls={clv.cls}
            sub="beat-the-close; calibration only"
          />
        </div>

        {/* Daily units mini strip */}
        <div>
          <span className="mb-2 block font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
            Day units (last 14 days)
          </span>
          <DailyStrip daily={isUnavail ? [] : series!.daily ?? []} />
        </div>

        {/* Honest footer */}
        <p className="mt-4 border-t border-slate-800 pt-3 font-mono text-[10px] text-faint">
          PAPER simulation -- this is "how much you WOULD have made" in UNITS, not
          dollars. Executed: false. Real-money: DENY. No edge or profit is claimed;
          a flat/negative curve that tracks the efficient close is an honest result.
        </p>
      </div>
    </section>
  );
}
