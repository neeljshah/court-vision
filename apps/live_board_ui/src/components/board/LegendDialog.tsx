/** "How to read this board" help dialog for non-technical users and mobile (no hover). */
import { HelpCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
} from "@/components/ui/dialog";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LegendRowProps {
  label: React.ReactNode;
  meaning: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LegendRow({ label, meaning }: LegendRowProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-1.5 sm:gap-3 py-2 border-b border-line last:border-0">
      <div className="shrink-0 min-w-[120px]">{label}</div>
      <p className="text-xs text-muted leading-relaxed">{meaning}</p>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mt-4 mb-1">
      {children}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

/** Named export: LegendDialog -- no required props. */
export function LegendDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          aria-label="How to read this board"
          className="
            inline-flex items-center gap-1.5
            border border-line rounded-md px-2.5 py-1.5
            text-sm text-muted
            hover:text-txt hover:bg-surface2
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent
            transition-colors
          "
        >
          <HelpCircle size={14} aria-hidden="true" />
          <span>How to read this</span>
        </button>
      </DialogTrigger>

      <DialogContent title="How to read this board">

        {/* ---- Source badges ---- */}
        <SectionHeading>Source badges</SectionHeading>

        <LegendRow
          label={<Badge variant="model">MODEL</Badge>}
          meaning="Our calibrated win-prob, shown when this matchup is in our data (in-corpus)."
        />
        <LegendRow
          label={<Badge variant="market">MARKET</Badge>}
          meaning="Devigged market-implied probability, used when we have no in-corpus model for this matchup."
        />
        <LegendRow
          label={
            <span className="text-xs text-muted italic">
              MODEL-LIVE / MARKET-LIVE
            </span>
          }
          meaning={'Either source, updating live during the game. The "-LIVE" suffix means the number is refreshing as play proceeds.'}
        />
        <LegendRow
          label={<Badge variant="muted">SCORE ONLY</Badge>}
          meaning="No model and no usable odds available -> just the live score and clock are shown."
        />

        {/* ---- Win % ---- */}
        <SectionHeading>Win %</SectionHeading>

        <LegendRow
          label={
            <span className="text-xs font-semibold text-txt">Home / Away</span>
          }
          meaning={`Each side's chance to win (home and away; soccer also shows "Draw"). The bar is a visual aid only -- the printed percent is the authoritative number.`}
        />

        {/* ---- Live indicator ---- */}
        <SectionHeading>Live indicator</SectionHeading>

        <LegendRow
          label={
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full bg-live animate-pulse"
                aria-hidden="true"
              />
              <span className="text-xs font-semibold text-live">LIVE</span>
            </span>
          }
          meaning={`Pulsing red dot = game in progress. "delayed" next to it means the data feed may be lagging and we are trying to refresh.`}
        />

        {/* ---- Details ---- */}
        <SectionHeading>Details</SectionHeading>

        <LegendRow
          label={
            <span className="text-xs font-semibold text-txt">Tap a game</span>
          }
          meaning="Tap any matchup to open full details -- all win probabilities, market context, exact start time, and notes. Live scores briefly highlight when they change."
        />

        {/* ---- Disclaimer ---- */}
        <p className="mt-5 text-[11px] text-muted leading-relaxed border-t border-line pt-3">
          Decision support, not a money machine. Model where in-corpus,
          market-implied otherwise. No $ edge claimed.
        </p>
      </DialogContent>
    </Dialog>
  );
}
