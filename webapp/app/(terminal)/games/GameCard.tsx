"use client";

import Link from "next/link";
import type { PredictRecord, GameEdge } from "@/lib/p5api";
import { cn, fmtPct, tierClass } from "@/lib/utils";
import { coherentPick, keyMarkets, bestBetChip } from "./card-utils";
import { InfoTip } from "@/components/depth";
import { sportSignals } from "@/components/games_depth";
import { GameStatusChip } from "./GameStatusChip";
import { AsOf, Num } from "@/components/ui/terminal";
import {
  type SlateGame,
  bestPrice,
  american,
  newestCapture,
  STALE_AFTER_MS,
} from "@/lib/board";
import { humanizeMatchup } from "@/lib/betdesc";

function fmtProb(p: number | null | undefined): string {
  return p == null ? "--" : p.toFixed(3).replace(/^0/, "");
}

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
  slateGame,
}: {
  sport: string;
  rec: PredictRecord;
  edge: GameEdge | null;
  /** Matched /api/board/slate row (best price + book per side). Optional --
   * an unmatched/unavailable board feed degrades to an honest "no board
   * price" line, never a fabricated one. */
  slateGame?: SlateGame | null;
}) {
  const pick = coherentPick(rec);
  const markets = keyMarkets(rec, 3);
  const chip = bestBetChip(edge);
  const cap = newestCapture(slateGame?.markets);
  const boardStale = cap !== null && Date.now() - cap.getTime() > STALE_AFTER_MS;
  // How many gate-tested signals SHIP for this sport (calibration priors only).
  const ships = sportSignals(sport).filter((s) => s.verdict === "SHIP").length;

  // Descriptive label for the card link -- matchup + tipoff for screen readers.
  const linkAriaLabel = `${rec.away} at ${rec.home}${rec.tipoff ? `, ${rec.tipoff}` : ""} -- open game detail`;

  return (
    <Link
      href={`/games/${sport}/${rec.game_id}`}
      aria-label={linkAriaLabel}
      className={cn(
        "group flex flex-col gap-0 border border-border bg-card",
        "transition-colors hover:border-muted-foreground",
        // Focus-visible ring so keyboard users can see focus on the card.
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
      )}
    >
      {/* ------------------------------------------------------------------ */}
      {/* Matchup header: team names + tipoff + leak-guard badge             */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-start justify-between gap-2 px-4 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          {/* Away @ Home -- primary headline */}
          <div className="truncate text-[15px] font-semibold leading-snug text-foreground">
            {rec.away}{" "}
            <span className="font-normal text-muted-foreground">@</span>{" "}
            {rec.home}
          </div>
          {/* Tipoff + game id -- secondary metadata */}
          <div className="mt-0.5 font-data text-[10px] tracking-wide text-faint">
            {rec.tipoff || "tipoff TBD"}
            <span className="mx-1.5 text-border">&middot;</span>
            {humanizeMatchup(rec.game_id)}
          </div>
        </div>
        <div className="mt-0.5 flex shrink-0 flex-col items-end gap-1">
          <GameStatusChip tipoff={rec.tipoff} liveState={edge?.live?.status ?? edge?.status} />
          {edge?.live?.home_score != null && edge?.live?.away_score != null ? (
            <span className="font-data text-xs tabular text-foreground">
              {edge.live.away_score} <span className="text-faint">-</span> {edge.live.home_score}
            </span>
          ) : null}
          {rec.leak_guard ? (
            <span
              className={cn(
                "border px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider",
                rec.leak_guard.in_sample ? "border-danger text-down" : "border-success text-up",
              )}
            >
              {rec.leak_guard.in_sample ? "in-sample" : "leak-free"}
            </span>
          ) : null}
        </div>
      </div>

      {/* Horizontal rule */}
      <div className="mx-4 border-t border-border" />

      {/* ------------------------------------------------------------------ */}
      {/* Coherent prediction block: ONE probability-only headline           */}
      {/* ------------------------------------------------------------------ */}
      <div className="px-4 pt-3 pb-3">
        <div className="flex items-center justify-between border border-border bg-surface-2 px-3 py-2.5">
          <span className="microlabel flex items-center gap-1">
            prediction
            <InfoTip
              text="The one coherent pick: the highest-probability side of the pregame anchor. This same engine spines every market on the game page."
              ariaLabel="what is the prediction?"
            />
          </span>
          <span className="flex items-baseline gap-1.5">
            <span className="text-sm font-semibold text-foreground">
              {pick.teamLabel}
            </span>
            <Num className="text-xs text-muted-foreground">
              {pick.prob != null ? fmtPct(pick.prob, false) : "--"}
            </Num>
          </span>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Model vs market, best price + book per side (from board slate)     */}
      {/* ------------------------------------------------------------------ */}
      {slateGame ? (
        <div className="mx-4 mb-3 border border-border">
          <div className="flex items-center justify-between border-b border-border bg-surface-2 px-3 py-1">
            <span className="microlabel">model / mkt</span>
            {cap ? (
              <AsOf stamp={cap.toLocaleTimeString([], { hour12: false })} stale={boardStale} />
            ) : (
              <span className="font-data text-[10px] text-faint">no price</span>
            )}
          </div>
          {(["away", "home"] as const).map((side) => {
            const best = bestPrice(slateGame.markets, side);
            const modelProb =
              side === "home" ? rec.pregame_probs?.home_ml : rec.pregame_probs?.away_ml;
            return (
              <div
                key={side}
                className="flex items-center justify-between gap-2 border-t border-border px-3 py-1.5 font-data text-[11px] first:border-t-0"
              >
                <span className="truncate text-muted-foreground">
                  {side === "home" ? rec.home : rec.away}
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="text-s-model">{fmtProb(modelProb)}</span>
                  <span className="text-faint">/</span>
                  <span className="text-s-market">{fmtProb(best?.devigged_prob)}</span>
                  <Num className="ml-1 text-faint">{american(best?.odds)}</Num>
                  <span className="text-faint">{best?.book ?? "--"}</span>
                </span>
              </div>
            );
          })}
        </div>
      ) : null}

      {/* ------------------------------------------------------------------ */}
      {/* Key markets: devigged probability/odds rows (no $)                 */}
      {/* ------------------------------------------------------------------ */}
      {markets.length ? (
        <ul
          className="mx-4 mb-3 divide-y divide-border border border-border"
          aria-label="key markets (devigged probability, no $)"
        >
          {markets.map((m, i) => (
            <li
              key={`${m.market_type ?? "m"}|${m.side ?? "s"}|${m.line ?? ""}|${i}`}
              className="flex items-center justify-between px-3 py-1.5 font-data text-[11px]"
            >
              <span className="truncate text-muted-foreground">
                {m.market_type} {m.side}
                {m.line != null ? ` ${m.line}` : ""}
              </span>
              <Num className="ml-2 shrink-0 text-faint">
                {m.odds != null ? m.odds.toFixed(2) : "--"}
                {m.devigged_prob != null
                  ? ` | ${fmtPct(m.devigged_prob, false)}`
                  : ""}
                {m.clv_is_proxy ? (
                  <span className="ml-1 text-stale">proxy</span>
                ) : null}
              </Num>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mx-4 mb-3 font-data text-[11px] text-faint">
          no market rows
        </p>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Best-bet chip footer: UNITS + tier, or honest NO BET. NO $.        */}
      {/* ------------------------------------------------------------------ */}
      <div className="mt-auto flex items-center justify-between border-t border-border px-4 py-3">
        {chip.decision === "bet" ? (
          <span
            className="inline-flex items-center gap-1.5"
            aria-label={`best bet: tier ${chip.tier ?? "--"}, ${chip.stakeUnits != null ? chip.stakeUnits.toFixed(2) : "--"} units`}
          >
            <span
              className={cn(
                "inline-flex items-center gap-1.5 border px-2 py-1 font-data text-[10px] font-semibold uppercase tracking-wide",
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
            {/* Muted chip -- visually distinct from a live-bet tier chip */}
            <span className="inline-flex items-center border border-border bg-surface-2 px-2 py-1 font-data text-[10px] uppercase tracking-wide text-faint">
              no bet (below floor)
            </span>
            <InfoTip
              text="No candidate cleared the tier floor for this game, so the honest decision is NO BET. We never fabricate a bet to fill the slot."
              ariaLabel="why no bet?"
            />
          </span>
        )}
        <span
          className="font-data text-[10px] text-faint transition-colors group-hover:text-muted-foreground"
          aria-hidden
        >
          {ships > 0 ? `${ships} calib signal - ` : ""}open game &rarr;
        </span>
      </div>
    </Link>
  );
}
