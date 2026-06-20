// Progress (/progress) -- the HONEST "the product is getting better" view.
//
// The product improves along THREE honest axes, and NONE of them is a live
// accuracy / edge climb:
//   (1) COVERAGE -- more data points run through the leak-free gate with a
//       RECORDED verdict (a REJECT counts; a recorded reject is a SUCCESS).
//   (2) COMPLETENESS -- parity matrix GREEN, more coherent markets exposed, the
//       discovered backlog burning down (73 -> remaining).
//   (3) a proven-READY-but-INERT improvement ENGINE -- calibration is PROVEN to
//       improve WHEN a human enables the gate (sealed-fold Brier 0.2025 ->
//       0.0958), but the gate is OFF, so the MODEL ITSELF IS STATIC.
//
// HONESTY RAILS: NO $ field anywhere; no fabricated accuracy / edge climb; the
// trend lines are coverage / verdicts / backlog over time, honestly labelled;
// the model is STATIC until the self-improve gate is enabled; engine_enabled is
// false; edge_claimed is false; units / probability only; real money default-DENY;
// local only. Live numbers come from /api/progress; an unreachable endpoint
// degrades to an honest empty state, never green-on-missing.

import { Legend, InfoTip } from "@/components/depth";
import { HONEST_DISCLAIMER, PRODUCT_NAME } from "@/lib/api";
import { ProgressView } from "@/components/progress/ProgressView";

export const metadata = {
  title: "Progress",
  description:
    "How CourtVision is getting better, honestly: validation COVERAGE growth, " +
    "COMPLETENESS (parity green, backlog burn-down), and a proven-ready-but-inert " +
    "improvement engine. The model itself is STATIC until the self-improve gate " +
    "is enabled. No live accuracy or edge climb; no dollar edge claimed.",
};

export default function ProgressPage() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
            how the product gets better -- honestly
          </p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">
            Progress{" "}
            <span className="font-mono text-sm text-muted-foreground">
              coverage + completeness + a proven-ready engine
            </span>
          </h1>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">
          reads /api/progress -- units only -- no $ claimed
        </span>
      </header>

      {/* The headline story -- the three honest axes + the model-static fact. */}
      <section className="rounded-xl border border-border bg-surface-1/60 p-5">
        <p className="text-sm leading-relaxed text-muted-foreground">
          The product gets better by growing validation{" "}
          <span className="text-foreground">COVERAGE</span> (more data points run
          through the leak-free gate with a recorded verdict) and{" "}
          <span className="text-foreground">COMPLETENESS</span> (parity grid
          GREEN, more coherent markets exposed, the discovered backlog burning
          down), backed by a proven-ready improvement{" "}
          <span className="text-foreground">ENGINE</span>.{" "}
          <InfoTip term="calibration" ariaLabel="what is calibration?" />
        </p>
        <p className="mt-3 rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
          <span className="font-semibold uppercase tracking-wider text-warning">
            honest note --{" "}
          </span>
          The <span className="text-foreground">model itself is STATIC</span>{" "}
          until the self-improve gate is enabled. Calibration is{" "}
          <span className="text-foreground">PROVEN to improve when enabled</span>{" "}
          on a sealed held-out fold (Brier{" "}
          <span className="font-mono text-foreground">0.2025 -&gt; 0.0958</span>),
          but the engine is{" "}
          <span className="font-mono text-amber-400">INERT</span> (human-gated
          OFF). Nothing below is a live accuracy or edge climb -- the trends are
          coverage / verdicts / backlog over time.{" "}
          <InfoTip term="inert" ariaLabel="what does INERT mean?" />
        </p>
      </section>

      {/* Page-level key: the terms a reader needs to read every panel below. */}
      <Legend
        title="how to read this page"
        terms={["calibration", "edge", "vs_close", "brier", "clv", "inert", "units"]}
      />

      {/* The live, REAL data panels (coverage, verdicts, backlog, parity, CLV). */}
      <ProgressView />

      <footer className="mt-4 text-center text-[11px] text-muted-foreground">
        {HONEST_DISCLAIMER} Progress = coverage + completeness + a ready engine,
        NOT a live accuracy / edge climb. The {PRODUCT_NAME} model is STATIC
        until the self-improve gate is enabled (engine INERT, human-gated OFF);
        real money is default-DENY; vs_close is UNPROVEN where no in-play odds
        exist.
      </footer>
    </main>
  );
}
