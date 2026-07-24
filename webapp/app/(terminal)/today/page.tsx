// /today -- the dedicated "wake up and SEE everything for today" morning view.
//
// Mirrors the Home TODAY digest (HomeTodayCard) and adds the FULL paper equity
// curve below it (the prominent "how much you WOULD have made" in UNITS view).
// Both live-refresh via useLiveData.
//
// HONESTY RAILS: UNITS only -- NO $ token; PAPER; edge_claimed=false; real-money
// DENY; CLV = the yardstick (INSUFFICIENT_DATA at small-N); stale-never-green.
// Degrades honestly when /api/paper/today is absent. Local only.

import type { Metadata } from "next";
import { Suspense } from "react";
import { HomeTodayCard } from "@/components/home/HomeTodayCard";
import { TodayEquity } from "./TodayEquity";

export const metadata: Metadata = {
  title: "Today",
  description:
    "Today's autonomous paper cycle at a glance -- best bets, placed (staked) bets, " +
    "settled W-L, day P&L, bankroll and the paper equity curve. UNITS only, paper, " +
    "no dollar edge claimed.",
};

export default function TodayPage() {
  return (
    <div className="pb-12">
      <header className="mx-auto max-w-5xl px-4 pt-8 sm:px-6">
        <p className="microlabel">
          autonomous daily cycle
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          Today
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          What the system did today and how much you would have made in UNITS --
          best bets, the PLACED (staked) money-makers, settled W-L, day P&amp;L,
          bankroll and the paper equity curve. PAPER mode only; no dollar edge is
          claimed; CLV (beat-the-close) is the only honest yardstick.
        </p>
      </header>

      {/* The shared digest card (live-refresh, honest fallback). */}
      <Suspense fallback={null}><HomeTodayCard /></Suspense>

      {/* The FULL equity curve + bankroll panel (prominent money view). */}
      <Suspense fallback={null}><TodayEquity /></Suspense>
    </div>
  );
}
