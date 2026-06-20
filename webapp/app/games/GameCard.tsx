"use client";

import Link from "next/link";
import type { PredictRecord, GameEdge } from "@/lib/p5api";
import { Badge } from "@/components/p6/Primitives";
import { cn, fmtPct, tierClass } from "@/lib/utils";
import { coherentPick, keyMarkets, bestBetChip } from "./card-utils";
import { InfoTip } from "@/components/depth";
import { sportSignals } from "@/components/games_depth";

// GameCard -- ONE matchup as a clickable card. Shows the single coherent
// prediction (anchor probability), a few key markets, and a best-bet chip in
// UNITS + tier (or an honest NO BET). Clicking opens the full /games view.
//
// HONESTY RAILS: UNITS / probability only -- NO $ anywhere. A best-bet chip is
// a real 'bet' decision or an honest NO BET; never a fabricated edge. vs_close
// is UNPROVEN (we never label a market beat). Proxy closes are flagged.
//
// A11Y: the card <Link> carries a descriptive aria-label and a focus-visible
// ring so keyboard users can navigate the slate. Key state changes (bet vs no
// bet) are visually distinct and labelled for screen readers.
export function GameCard({
  sport,
  rec,
  edge,
}: {
  sport: string;
  rec: PredictRecord;
  edge: GameEdge | null;
}) {
  const pick = coherentPick(rec);
  const markets = keyMarkets(rec, 3);
  const chip = bestBetChip(edge);
  // How many gate-tested signals SHIP for this sport (calibration priors only).
  const ships = sportSignals(sport).filter((s) => s.verdict === "SHIP").length;

  // Descriptive label for the card link -- matchup + tipoff for screen readers.
  const linkAriaLabel = `${rec.away} at ${rec.home}${rec.tipoff ? `, ${rec.tipoff}` : ""} -- open game detail`;

  return (
    <Link
      href={`/games/${sport}/${rec.game_id}`}
      aria-label={linkAriaLabel}
      className={cn(
        "group flex flex-col gap-0 rounded-xl border border-slate-800 bg-bg-panel",
        "transition-colors hover:border-slate-600",
        // Focus-visible ring so keyboard users can see focus on the card.
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel",
      )}
    >
      {/* ------------------------------------------------------------------ */}
      {/* Matchup header: team names + tipoff + leak-guard badge             */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-start justify-between gap-2 px-4 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          {/* Away @ Home -- primary headline */}
          <div className="truncate text-[15px] font-semibold leading-snug text-slate-100">
            {rec.away}{" "}
            <span className="font-normal text-slate-500">@</span>{" "}
            {rec.home}
          </div>
          {/* Tipoff + game id -- secondary metadata */}
          <div className="mt-0.5 font-mono text-[10px] tracking-wide text-slate-500">
            {rec.tipoff || "tipoff TBD"}
            <span className="mx-1.5 text-slate-700">&middot;</span>
            {rec.game_id}
          </div>
        </div>
        {rec.leak_guard ? (
          <div className="mt-0.5 shrink-0">
            <Badge tone={rec.leak_guard.in_sample ? "red" : "green"}>
              {rec.leak_guard.in_sample ? "in-sample" : "leak-free"}
            </Badge>
          </div>
        ) : null}
      </div>

      {/* Horizontal rule */}
      <div className="mx-4 border-t border-slate-800/60" />

      {/* ------------------------------------------------------------------ */}
      {/* Coherent prediction block: ONE probability-only headline           */}
      {/* ------------------------------------------------------------------ */}
      <div className="px-4 pt-3 pb-3">
        <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-bg-subtle px-3 py-2.5">
          <span className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-slate-500">
            prediction
            <InfoTip
              text="The one coherent pick: the highest-probability side of the pregame anchor. This same engine spines every market on the game page."
              ariaLabel="what is the prediction?"
            />
          </span>
          <span className="flex items-baseline gap-1.5">
            <span className="text-sm font-semibold text-slate-100">
              {pick.teamLabel}
            </span>
            <span className="font-mono text-xs text-slate-400">
              {pick.prob != null ? fmtPct(pick.prob, false) : "--"}
            </span>
          </span>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Key markets: devigged probability/odds rows (no $)                 */}
      {/* ------------------------------------------------------------------ */}
      {markets.length ? (
        <ul
          className="mx-4 mb-3 divide-y divide-slate-800/50 rounded-lg border border-slate-800/60"
          aria-label="key markets (devigged probability, no $)"
        >
          {markets.map((m, i) => (
            <li
              key={i}
              className="flex items-center justify-between px-3 py-2 font-mono text-[11px]"
            >
              <span className="truncate text-slate-400">
                {m.market_type} {m.side}
                {m.line != null ? ` ${m.line}` : ""}
              </span>
              <span className="ml-2 shrink-0 tabular-nums text-slate-500">
                {m.odds != null ? m.odds.toFixed(2) : "--"}
                {m.devigged_prob != null
                  ? ` | ${fmtPct(m.devigged_prob, false)}`
                  : ""}
                {m.clv_is_proxy ? (
                  <span className="ml-1 text-amber-600/80">proxy</span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mx-4 mb-3 font-mono text-[11px] text-slate-700">
          no market rows
        </p>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Best-bet chip footer: UNITS + tier, or honest NO BET. NO $.        */}
      {/* ------------------------------------------------------------------ */}
      <div className="mt-auto flex items-center justify-between border-t border-slate-800 px-4 py-3">
        {chip.decision === "bet" ? (
          <span
            className="inline-flex items-center gap-1.5"
            aria-label={`best bet: tier ${chip.tier ?? "--"}, ${chip.stakeUnits != null ? chip.stakeUnits.toFixed(2) : "--"} units`}
          >
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-mono font-semibold uppercase tracking-wide",
                tierClass(chip.tier || undefined),
              )}
            >
              tier {chip.tier || "--"}
              <span className="opacity-60">&middot;</span>
              {chip.stakeUnits != null ? chip.stakeUnits.toFixed(2) : "--"}u
            </span>
            <InfoTip
              term="units"
              ariaLabel="what are units and tier?"
            />
          </span>
        ) : (
          <span
            className="inline-flex items-center gap-1.5"
            aria-label="no bet: no candidate cleared the tier floor"
          >
            {/* Muted slate chip -- visually distinct from a live-bet tier chip */}
            <span className="inline-flex items-center rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-slate-500">
              no bet (below floor)
            </span>
            <InfoTip
              text="No candidate cleared the tier floor for this game, so the honest decision is NO BET. We never fabricate a bet to fill the slot."
              ariaLabel="why no bet?"
            />
          </span>
        )}
        <span
          className="font-mono text-[10px] text-slate-600 transition-colors group-hover:text-slate-400"
          aria-hidden
        >
          {ships > 0 ? `${ships} calib signal - ` : ""}open game &rarr;
        </span>
      </div>
    </Link>
  );
}
