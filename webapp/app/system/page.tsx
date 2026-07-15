// System (/system) -- the honest "WHAT IT'S DOING" observability view.
//
// Answers ONE honest question: "is the stack running, learning, and healthy --
// and what has it honestly proven?" -- NOT "is it making money". Composes the
// existing self-fetching p6 panels (each degrades to an honest Unavailable
// sentinel, never a fabricated green) plus three page-local artifact surfaces:
// the GATE-VERDICT LEDGER (every signal tested), the CLV-over-time measurement,
// and the IMPROVEMENT BACKLOG (what we'll get better at next).
//
// UNITS / probability only. NO $ field. Self-improve is READY but INERT
// (human-gated OFF). Real money is default-DENY. An honest REJECT / idle is a
// SUCCESS state, not a failure. vs_close is UNPROVEN where no in-play odds
// exist. Local only.

import { ParityGrid } from "@/components/p6/ParityGrid";
import { LiveIndicator } from "@/components/system/LiveIndicator";
import { OpsPanel } from "@/components/p6/OpsPanel";
import { SchedulerFreshnessPanel } from "@/components/p6/SchedulerFreshnessPanel";
import { RatchetPanel } from "@/components/p6/RatchetPanel";
import { SelfImprovePanel } from "@/components/p6/SelfImprovePanel";
import { GateMatrix } from "@/components/p6/GateMatrix";
import { GateLedgerPanel } from "@/components/system/GateLedgerPanel";
import { ClvOverTimePanel } from "@/components/system/ClvOverTimePanel";
import { BacklogPanel } from "@/components/system/BacklogPanel";
import { Legend, InfoTip } from "@/components/depth";
import { HONEST_FINDINGS, HONEST_DISCLAIMER } from "@/lib/api";

export const metadata = {
  title: "System",
};

export default function SystemPage() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">
          System{" "}
          <span className="font-mono text-sm text-muted-foreground">
            what it&apos;s doing -- health / learning / proof
          </span>
        </h1>
        <span className="font-mono text-[11px] text-muted-foreground">
          reads the Auto-API -- paper only -- no $ claimed
        </span>
      </header>

      {/* PROMINENT: is the stack running INDEPENDENTLY right now? Reads the REAL
          supervisor doc (fresh + all_ready + no-degraded -> green; else IDLE/
          DEGRADED honestly). Self-heal/uptime/restart counts + honest badges. */}
      <LiveIndicator />

      {/* Page-level key: the terms a reader needs to understand every number below. */}
      <Legend
        title="how to read this page"
        terms={["calibration", "edge", "vs_close", "brier", "clv", "inert", "units"]}
      />

      {/* Honest findings (prose framing; live numbers live in the panels below). */}
      <section className="grid grid-cols-1 gap-3 md:grid-cols-2" aria-label="honest findings">
        {HONEST_FINDINGS.map((f) => (
          <div key={f.title} className="rounded-lg border border-border bg-surface-1/60 p-4">
            <div className="text-sm font-semibold tracking-tight text-foreground">{f.title}</div>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{f.body}</p>
          </div>
        ))}
      </section>

      {/* SERVICES / health + the canonical autonomy status (stale=RED, never green-on-missing). */}
      <OpsPanel />

      {/* PRODUCER / SCHEDULER freshness: per-sport last-update age (stale never
          green; a sport dropped from the scheduler rotation is shown as a gap). */}
      <SchedulerFreshnessPanel />

      {/* Self-improve ratchet: explain READY-but-INERT + the human gate up front. */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-1/40 px-3 py-2 text-[11px] text-muted-foreground">
        <span className="font-mono uppercase tracking-wide text-muted-foreground">
          self-improve ratchet
        </span>
        <span>
          built and READY, but{" "}
          <span className="font-mono text-amber-400">INERT</span> -- the pipeline
          flag is human-gated OFF, so it measures only and ships nothing.
        </span>
        <InfoTip term="inert" ariaLabel="what does INERT mean?" />
        <InfoTip
          text="The ratchet is a finite-state machine that can recalibrate when an eval-gate passes. It is wired but the PIPELINE_ENABLED flag stays OFF (a human gate); real money is default-DENY. Nothing here flips a flag, promotes a feature, or claims an edge."
          ariaLabel="what is the human gate?"
        />
      </div>

      {/* Self-improve loop: timeline (READY/INERT, n_promoted honest) | ratchet FSM state. */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-6">
          <SelfImprovePanel />
        </div>
        <div className="col-span-12 lg:col-span-6">
          <RatchetPanel />
        </div>
      </div>

      {/* Cross-sport parity grid (FULLY GREEN is the honest finding) | CLV over time (measurement). */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-7">
          <ParityGrid />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <ClvOverTimePanel />
        </div>
      </div>

      {/* 4-sport in-game calibration gate verdicts (the proven measured edge = in-game prior-conditioning). */}
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-mono uppercase tracking-wide text-muted-foreground">
          in-game calibration gate
        </span>
        <span>
          per-sport, both-direction cross-corpus verdicts. The meta-finding:
          generic in-game micro-state REJECTS across NBA / MLB / soccer / tennis.
        </span>
        <InfoTip
          text="Each cell is a leak-free CALIBRATION verdict (held-out Brier), not a market edge. A REJECT is a SUCCESS -- it means the live market already prices that micro-state. vs_close is UNPROVEN where no in-play odds exist."
          ariaLabel="what is the in-game gate?"
        />
      </div>
      <GateMatrix />

      {/* The GATE-VERDICT LEDGER -- every signal run through the leak-free gate. */}
      <GateLedgerPanel />

      {/* The IMPROVEMENT BACKLOG -- ranked "what we'll get better at next" (measurement-only). */}
      <BacklogPanel />

      <footer className="mt-4 text-center text-[11px] text-muted-foreground">
        {HONEST_DISCLAIMER} The self-improve loop is READY but INERT (human-gated
        OFF); real money is default-DENY (paper only). vs-close is UNPROVEN where
        no in-play odds are available.
      </footer>
    </main>
  );
}
