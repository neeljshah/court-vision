// GameStatusChip -- corner status chip for a GameCard: LIVE / PREGAME / DONE.
// Derived from tipoff (ISO string) and optional liveState from the backend.
//
// HONESTY RAILS: stale-never-green -- LIVE (green pulse) ONLY when liveState
// is explicitly "in_progress" or "live". Past tipoff with no live state -> DONE
// (muted). Future tipoff -> PREGAME (slate). Never a fabricated "live" label.
// No $ anywhere.

import { cn } from "@/lib/utils";
import { Dot } from "@/components/ui/terminal";

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
          "inline-flex items-center gap-1.5 border border-success px-1.5 py-px",
          "font-data text-[10px] font-bold uppercase tracking-wider text-up",
        )}
      >
        <Dot state="ok" />
        LIVE
      </span>
    );
  }

  if (status === "done") {
    return (
      <span
        aria-label="game is done"
        className="inline-flex items-center border border-border px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-faint"
      >
        DONE
      </span>
    );
  }

  // pregame
  return (
    <span
      aria-label="game is pregame"
      className="inline-flex items-center border border-border px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-muted-foreground"
    >
      PREGAME
    </span>
  );
}
