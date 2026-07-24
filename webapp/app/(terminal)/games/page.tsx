// Games (/games) -- per-sport SLATE of game CARDS.
//
// Each card = one matchup + the ONE coherent prediction (probability) + a few
// key markets + a best-bet chip (UNITS + tier, or an honest NO BET). Clicking a
// card opens the full per-game view at /games/[sport]/[gameId].
//
// HONESTY RAILS: UNITS / probability only -- NO $ anywhere. edge_claimed is
// false; vs_close is UNPROVEN. An offseason / unavailable sport shows an honest
// empty state, NEVER a fabricated slate. Paper mode only. Local only.

import Link from "next/link";
import { SlateCards } from "./SlateCards";
import { HONEST_DISCLAIMER } from "@/lib/api";

export const metadata = {
  title: "Games",
};

export default function GamesPage() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">
          Games{" "}
          <span className="font-data text-sm text-muted-foreground">
            today&apos;s slate
          </span>
        </h1>
        <Link
          href="/p6"
          className="border border-border bg-surface-1 px-3 py-1.5 font-data text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          Dashboard &rarr;
        </Link>
      </header>

      <SlateCards />

      <footer className="mt-4 text-center font-data text-[11px] text-faint">
        {HONEST_DISCLAIMER}
      </footer>
    </main>
  );
}
