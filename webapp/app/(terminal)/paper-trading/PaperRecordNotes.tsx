// PaperRecordNotes.tsx -- the fixed copy blocks of /paper-trading (Paper record):
// what the book is, the paper-only banner (re-exported), the units convention, and the boxed
// retired July 2026 model snapshot. Split from page.tsx for the 300-line rail.

import Link from "next/link";
import type { ReactNode } from "react";
import { ReceiptChip } from "@/components/evidence";

export const LEDGER_SRC = "docs/evidence/forward/paper_result/LEDGER.jsonl";

/** One-paragraph definition of the book; dates come from the trail export, never the viewer clock. */
export function PaperRecordIntro({ asOf, lastNight }: { asOf: string | null; lastNight: string | null }) {
  return (
    <p data-testid="paper-record-intro" className="mt-1 max-w-3xl text-[12px] text-muted-foreground">
      The paper fill ledger: simulated maker fills on the recorded Kalshi in-game tape, read from the desk
      ledger. 29 fills over four ledger nights (2026-10-03, 10-04, 10-05 and 10-08; the first three come before
      the prospective series that starts 2026-10-06); counts, contracts and probabilities only. stake_units =
      contracts per fill. A count only: not an execution-quality result, not a money result, and not a verdict on the model.{" "}
      <span className="font-data text-foreground">
        Fills through night {lastNight ?? "not stated"}; ledger as of {asOf ? asOf.slice(0, 10) : "not stated"}.
      </span>{" "}
      <ReceiptChip source={LEDGER_SRC} asOf={asOf} status="descriptive_only" />{" "}
      Nights, coverage and the scoreboard are on the <Link href="/desk/" className="underline">desk record</Link>.
    </p>
  );
}

// The banner itself lives in components/paper/PaperOnlyBanner so /paper/<fill>/ shows the same one.
export { PaperOnlyBanner } from "@/components/paper/PaperOnlyBanner";

export function UnitsClarifier() {
  return (
    <div
      data-testid="unit-convention-clarifier"
      className="mb-5 rounded-lg border border-border bg-bg-subtle/60 px-4 py-2.5 text-[12px] text-muted-foreground"
    >
      <span className="font-semibold text-foreground">Units convention:</span>{" "}
      Stakes are in <span className="font-mono font-semibold">UNITS</span>, not dollars. In the forward record a
      unit is one contract. Older rows used quarter-Kelly sizing, so a stake there can exceed 1.0u. No return
      figure is published. No closing-line reading exists as of 2026-10-19 (evidence packet section 5).
    </div>
  );
}

/** The July 2026 panels: kept only inside this labelled box, below the real record. */
export function JulySnapshotBox({ children }: { children: ReactNode }) {
  return (
    <section
      data-testid="july-snapshot-box"
      aria-label="July 2026 model snapshot, simulated units"
      className="mb-5 mt-6 rounded-lg border border-dashed border-border p-3"
    >
      <h2 className="mb-1 text-[12px] font-semibold uppercase tracking-widest text-muted-foreground">
        July 2026 model snapshot, simulated units (retired)
      </h2>
      <p className="mb-3 text-[12px] text-faint">
        The unit balance, closing-line and bankroll panels came from the July 2026 model snapshot (as of
        2026-07-16). They are no longer published: the forward record is a count ledger with no unit ledger
        and no closing price per fill, so each panel below shows the exporter&apos;s reason instead.
      </p>
      {children}
    </section>
  );
}
