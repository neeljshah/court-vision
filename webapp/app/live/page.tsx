// page.tsx -- /live route: dedicated Live Games surface.
//
// Three sections (LIVE / PREGAME / DONE) derived from game state + tipoff.
// Client-side polling every ~20s; pauses when tab is hidden; live badge shows
// last-updated age (stale-never-green). Honest offseason empty state with the
// refresh mechanism still visibly running.
//
// HONESTY RAILS: probability / UNITS only -- NO $ anywhere. Stale-never-green.
// Offseason -> "No live games right now" (not red, not fabricated). Paper only.

import { LiveGamesView } from "./LiveGamesView";
import { HONEST_DISCLAIMER } from "@/lib/api";

export const metadata = {
  title: "Live Games",
};

export default function LivePage() {
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-4 p-6">
      <LiveGamesView />

      <footer className="mt-4 text-center font-data text-[11px] text-faint">
        {HONEST_DISCLAIMER}
      </footer>
    </main>
  );
}
