"use client";

import { useCallback, useState } from "react";
import {
  api,
  SPORTS,
  type Sport,
  type QuantValidate,
  type QuantValidateGame,
  type QuantValidation,
  type QuantRisk,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Unavailable, Badge } from "./Primitives";
import { Num, Dot } from "@/components/ui/terminal";
import { cn } from "@/lib/utils";

// QuantPanel -- the quant EXECUTION surface (transparency only).
// Reads GET /api/quant/{sport}/validate (per-market BetValidation verdicts:
// side/market/model_prob/devigged_close/edge/tier/UNITS/CLV/gate_proven) and
// GET /api/quant/risk (UNIT-space variance/exposure over the open paper book).
//
// HONESTY: NO $ column anywhere -- every stake is in UNITS, every prob is in
// [0,1]. MOST verdicts are no_bet / match-the-efficient-close, which is a
// SUCCESS, not a miss. gate_proven is shown verbatim (mostly false); we never
// paint an unproven verdict as a proven edge.
//
// Live polling: uses useLiveData (pause-on-hidden, last-good, stale badge).
// No bespoke setInterval.

function pct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "--";
  return `${(x * 100).toFixed(1)}%`;
}

function signed(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "--";
  const p = x * 100;
  return `${p >= 0 ? "+" : ""}${p.toFixed(1)}pp`;
}

export function QuantPanel() {
  const [sport, setSport] = useState<Sport>("nba");

  const validateFetcher = useCallback(
    (s: AbortSignal) => api.getQuantValidate(sport, s) as Promise<QuantValidate>,
    [sport],
  );
  const {
    data: validate,
    error: valErr,
    isLoading: valLoading,
  } = useLiveData<QuantValidate>(validateFetcher, {
    intervalMs: 15000,
    staleAfterSec: 60,
  });

  const riskFetcher = useCallback(
    (s: AbortSignal) => api.getQuantRisk(s) as Promise<QuantRisk>,
    [],
  );
  const {
    data: risk,
    error: riskErr,
  } = useLiveData<QuantRisk>(riskFetcher, {
    intervalMs: 15000,
    staleAfterSec: 60,
  });

  const rows: Array<{ game: QuantValidateGame; v: QuantValidation }> = [];
  for (const g of validate?.games || []) {
    for (const v of g.validations || []) rows.push({ game: g, v });
  }
  const nBet = rows.filter((r) => r.v.decision === "bet").length;

  return (
    <Panel
      title="quant execution -- bet validation (units only)"
      right={
        <div className="flex items-center gap-2">
          <select
            aria-label="sport"
            value={sport}
            onChange={(e) => setSport(e.target.value as Sport)}
            className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] uppercase text-slate-300"
          >
            {SPORTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          {validate ? (
            <Badge tone={nBet > 0 ? "amber" : "slate"}>
              {nBet} bet / {rows.length - nBet} no_bet
            </Badge>
          ) : null}
        </div>
      }
    >
      <RiskStrip risk={risk} err={riskErr} />

      {valErr ? (
        <Unavailable reason={valErr} />
      ) : valLoading && !validate ? (
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          no validation candidates for {sport} -- matching the close everywhere
          is a SUCCESS, not a miss.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="microlabel py-1.5 px-3">Game</th>
                <th className="microlabel py-1.5 px-3">Side / market</th>
                <th className="microlabel py-1.5 px-3">Model</th>
                <th className="microlabel py-1.5 px-3">Devig close</th>
                <th className="microlabel py-1.5 px-3">Edge</th>
                <th className="microlabel py-1.5 px-3">Tier</th>
                <th className="microlabel py-1.5 px-3">Units</th>
                <th className="microlabel py-1.5 px-3">Decision</th>
                <th className="microlabel py-1.5 px-3">Gate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((r, i) => (
                <QuantRow key={i} game={r.game} v={r.v} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {validate?.honest_note ? (
        <p className="mt-3 text-[11px] text-faint">{validate.honest_note}</p>
      ) : null}
    </Panel>
  );
}

// RiskStrip -- UNIT-space exposure/variance over the open paper book. NO $.
function RiskStrip({
  risk,
  err,
}: {
  risk: QuantRisk | null;
  err: string | null;
}) {
  if (err) {
    return (
      <div className="mb-3 border border-amber-900/40 bg-amber-950/20 px-3 py-2">
        <span className="font-mono text-[10px] text-amber-400">
          risk unavailable
        </span>
        <span className="ml-2 text-[10px] text-muted-foreground">{err}</span>
      </div>
    );
  }
  if (!risk) return null;
  return (
    <div className="mb-3 border border-border bg-surface-1 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <Stat label="open" value={String(risk.n_open)} />
        <Stat label="exposure (u)" value={risk.total_exposure_units.toFixed(2)} />
        <Stat label="max single (u)" value={risk.max_single_units.toFixed(2)} />
        <Stat label="mean (u)" value={risk.mean_units.toFixed(2)} />
        <Stat label="variance (u2)" value={risk.variance_units2.toFixed(3)} />
      </div>
      <p className="mt-1 text-[10px] text-faint">
        Exposure / variance are in UNITS, never dollars. RoR is a
        model-conditional descriptive stat, NOT a profit/safety guarantee.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="microlabel">{label}</span>
      <Num className="text-foreground">{value}</Num>
    </span>
  );
}

function QuantRow({
  game,
  v,
}: {
  game: QuantValidateGame;
  v: QuantValidation;
}) {
  const bet = v.decision === "bet";
  const matchup =
    game.away && game.home
      ? `${game.away} @ ${game.home}`
      : game.game_id || "--";
  const clvPct =
    v.clv && typeof (v.clv as { clv_pct?: number }).clv_pct === "number"
      ? (v.clv as { clv_pct: number }).clv_pct
      : null;
  return (
    <tr className="text-foreground hover:bg-surface-2">
      <td className="py-1.5 px-3 font-mono text-[10px] text-muted-foreground">
        {matchup}
      </td>
      <td className="py-1.5 px-3">
        <span className="font-mono text-[10px] uppercase text-foreground">
          {v.side}
        </span>
        <span className="ml-1 font-mono text-[9px] text-muted-foreground">
          {v.market}
        </span>
      </td>
      <td className="py-1.5 px-3"><Num className="text-[10px]">{pct(v.model_prob)}</Num></td>
      <td className="py-1.5 px-3">
        <Num className="text-[10px] text-muted-foreground">{pct(v.devigged_close)}</Num>
        {v.clv_is_proxy ? (
          <span className="ml-1 text-[8px] text-amber-600/80">proxy</span>
        ) : null}
      </td>
      <td className="py-1.5 px-3">
        <Num
          className={cn(
            "text-[10px]",
            v.edge !== null && v.edge > 0 ? "text-tier-a" : "text-muted-foreground",
          )}
        >
          {signed(v.edge)}
        </Num>
      </td>
      <td className="py-1.5 px-3">
        <TierBadge tier={v.tier} />
      </td>
      <td className="py-1.5 px-3">
        <Num className="text-[10px]">{v.stake_units.toFixed(2)}u</Num>
      </td>
      <td className="py-1.5 px-3">
        <span className="inline-flex items-center gap-1.5">
          <Dot state={bet ? "warn" : "ok"} />
          <span
            className={cn(
              "inline-flex rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase",
              bet
                ? "border-amber-900/50 bg-amber-950/30 text-amber-400"
                : "border-slate-700 bg-slate-800 text-slate-400",
            )}
          >
            {v.decision}
          </span>
        </span>
        {clvPct !== null ? (
          <Num className={cn("ml-1 text-[9px]", clvPct >= 0 ? "text-up" : "text-down")}>
            clv {clvPct >= 0 ? "+" : ""}
            {clvPct.toFixed(1)}%
          </Num>
        ) : null}
      </td>
      <td className="py-1.5 px-3">
        <span className="inline-flex items-center gap-1.5">
          <Dot state={v.gate_proven ? "ok" : "warn"} />
          <span
            className={cn(
              "font-mono text-[9px] uppercase",
              v.gate_proven ? "text-tier-a" : "text-muted-foreground",
            )}
          >
            {v.gate_proven ? "proven" : "unproven"}
          </span>
        </span>
      </td>
    </tr>
  );
}

function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) {
    return <span className="font-mono text-[9px] text-faint">--</span>;
  }
  return (
    <span className="inline-flex rounded border border-tier-a/40 bg-tier-a/10 px-1.5 py-0.5 font-mono text-[9px] uppercase text-tier-a">
      {tier}
    </span>
  );
}
