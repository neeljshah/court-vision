// GameStatusChip -- corner status chip for a GameCard: LIVE / PREGAME / DONE.
// Derived from tipoff (ISO string) and optional liveState from the backend.
//
// HONESTY RAILS: stale-never-green -- LIVE (green pulse) ONLY when liveState
// is explicitly "in_progress" or "live". Past tipoff with no live state -> DONE
// (muted). Future tipoff -> PREGAME (slate). Never a fabricated "live" label.
// No $ anywhere.

import { cn } from "@/lib/utils";

type ChipStatus = "live" | "pregame" | "done";

function classify(tipoff: string | null, liveState?: string): ChipStatus {
  if (
    liveState &&
    /in_progress|live/i.test(liveState)
  ) {
    return "live";
  }
  if (!tipoff) return "pregame";
  const tipoffMs = Date.parse(tipoff);
  if (Number.isNaN(tipoffMs)) return "pregame";
  return tipoffMs < Date.now() ? "done" : "pregame";
}

export function GameStatusChip({
  tipoff,
  liveState,
}: {
  tipoff: string | null;
  liveState?: string;
}) {
  const status = classify(tipoff, liveState);

  if (status === "live") {
    return (
      <span
        aria-label="game is live"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5",
          "border border-green-700/60 bg-green-950/50",
          "font-mono text-[9px] font-semibold uppercase tracking-wider text-green-400",
        )}
      >
        {/* Animated pulse dot -- live indicator */}
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-green-400" />
        </span>
        LIVE
      </span>
    );
  }

  if (status === "done") {
    return (
      <span
        aria-label="game is done"
        className={cn(
          "inline-flex items-center rounded-full px-2 py-0.5",
          "border border-slate-700 bg-slate-800/40",
          "font-mono text-[9px] font-semibold uppercase tracking-wider text-slate-500",
        )}
      >
        DONE
      </span>
    );
  }

  // pregame
  return (
    <span
      aria-label="game is pregame"
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5",
        "border border-slate-600/60 bg-slate-900/40",
        "font-mono text-[9px] font-semibold uppercase tracking-wider text-slate-400",
      )}
    >
      PREGAME
    </span>
  );
}
