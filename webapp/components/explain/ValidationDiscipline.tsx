"use client";

// ValidationDiscipline.tsx -- the validation gate explained visually.
//
// The 8 controls every candidate signal must clear, framed as "why most signals
// honestly REJECT and that's success". Each control carries a one-line plain-
// language "why it matters", and the three subtlest ideas (planted-null, FWER,
// nested-CV) get a simple analogy via an InfoTip. No numbers, no $.
// Each control is one defense against fooling ourselves.

import { InfoTip } from "@/components/depth";
import { Panel, PanelHead } from "@/components/ui/terminal";

interface Control {
  name: string;
  guards: string; // what it defends against
  /** A simple, plain-language analogy for the subtler ideas (rendered as InfoTip). */
  plain?: string;
}

const CONTROLS: Control[] = [
  {
    name: "Leak-free features",
    guards: "no future information (e.g. season-final aggregates) reaching a per-game feature.",
  },
  {
    name: "Walk-forward",
    guards: "training only on the past, scoring only on the held-out future -- never in-sample.",
  },
  {
    name: "Cross-corpus (>= 2)",
    guards: "a lucky single corpus: the lift must replicate on independent league/data pairs, BOTH directions.",
  },
  {
    name: "Clustered Diebold-Mariano",
    guards: "treating correlated rows as independent: the DM test clusters by event so p-values are honest.",
  },
  {
    name: "Planted-null control",
    guards: "a 'signal' that is really noise: a deliberately-null column must FAIL the same gate.",
    plain:
      "We secretly slip a column of pure random noise into the same test. If the " +
      "gate ever 'passes' that fake signal, the gate is broken -- so a real signal " +
      "only counts when the planted fake reliably fails.",
  },
  {
    name: "FWER tightening",
    guards: "multiple-comparisons luck: running many signals tightens the bar so chance winners are caught.",
    plain:
      "Test enough coin-flippers and someone flips ten heads by luck. FWER raises " +
      "the bar in proportion to how many signals we tried, so a chance 'winner' " +
      "among many candidates no longer clears it.",
  },
  {
    name: "Degenerate-base guard",
    guards: "a base model so weak that anything beats it -- the base must itself be skillful first.",
  },
  {
    name: "Nested-CV anti-selection",
    guards: "tuning on the test fold: selection happens inside an inner fold, never on the held-out judge.",
    plain:
      "You can't grade your own exam. Picking the best version happens on an INNER " +
      "practice fold; the held-out fold is the untouched judge it never sees while " +
      "choosing -- so the final score isn't inflated by selection.",
  },
];

export function ValidationDiscipline() {
  return (
    <section aria-label="validation discipline">
    <Panel>
      <PanelHead title="validation discipline -- why most signals honestly reject" />
      <div className="flex flex-col gap-3 p-4">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Markets are efficient, so most candidate signals carry no real information once
          you stop fooling yourself. Eight stacked controls each remove one way to fool
          yourself. A signal must clear ALL of them to ship -- and an honest{" "}
          <span className="font-semibold text-foreground">REJECT is the product working</span>,
          not a failure.
        </p>
        <ol className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {CONTROLS.map((c, i) => (
            <li key={c.name} className="flex gap-3 border border-border bg-surface-1 p-3">
              <span className="mt-0.5 font-data text-[11px] font-semibold text-muted-foreground">
                {`0${i + 1}`}
              </span>
              <div>
                <div className="flex items-center gap-1 text-xs font-semibold tracking-tight text-foreground">
                  {c.name}
                  {c.plain && (
                    <InfoTip text={c.plain} ariaLabel={`${c.name} explained simply`} />
                  )}
                </div>
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                  <span className="text-foreground/70">why it matters --</span> {c.guards}
                </p>
              </div>
            </li>
          ))}
        </ol>
        <p className="border border-info/40 bg-info/5 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
          Only a signal that survives every control becomes a CALIBRATION prior or scouting
          note -- and even then,{" "}
          <span className="font-semibold text-foreground">vs_close stays UNPROVEN</span> until
          a separate closing-line-value test passes. No dollar edge is claimed at any step.
        </p>
      </div>
    </Panel>
    </section>
  );
}
