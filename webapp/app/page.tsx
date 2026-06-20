// Home (/) -- the cohesive CourtVision landing page.
//
// The welcoming front door AND an honest, in-depth scan of the system:
//   1. Hero -- what CourtVision is.
//   2. HOW IT WORKS funnel strip -- DATA -> SIGNALS -> MODELS -> ENGINES ->
//      ONE PREDICTION -> VALIDATION.
//   3. Live status row -- all_honest badge, what's live now, parity GREEN,
//      self-improve READY/INERT, real-money DENY (all from real endpoints).
//   4. Entry cards into Games / How it works / System.
//   5. Honest headline findings (depth plateau, the confirmed corners
//      CALIBRATION survivor, parity green) + a clear "calibration, not a
//      market edge" disclaimer.
//
// HONESTY RAILS: NO $ field; honest empty states (no fabricated slate); the
// confirmed survivor is CALIBRATION not a market edge; paper mode only; local
// only. All numbers come from live endpoints; this page never invents one.

import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { FUNNEL_STAGES, HONEST_FINDINGS, PRODUCT_NAME, HONEST_DISCLAIMER } from "@/lib/api";
import { HomeStatusRow } from "@/components/home/HomeStatusRow";
import { HomeRecordsHero } from "@/components/home/HomeRecordsHero";

export const metadata: Metadata = {
  title: "Home",
  description:
    "CourtVision -- a calibrated multi-sport prediction system. Honest calibration, " +
    "no dollar edge claimed. Paper mode only.",
};

function Hero() {
  return (
    <section className="mx-auto max-w-4xl px-4 pb-8 pt-12 text-center sm:px-6 sm:pt-16">
      <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
        calibrated multi-sport prediction system
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        {PRODUCT_NAME}
      </h1>
      <p className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-base">
        One pipeline turns raw game data into a single calibrated prediction per
        market across NBA, MLB and soccer. The honest, defensible win is matching
        the devigged close within noise -- plus a measured in-game calibration
        edge. Markets are efficient; <span className="text-foreground">no dollar edge is claimed.</span>
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/games"
          className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
        >
          View Games
        </Link>
        <Link
          href="/how-it-works"
          className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
        >
          How it works
        </Link>
      </div>
    </section>
  );
}

function FunnelStrip() {
  return (
    <section className="mx-auto max-w-5xl px-4 py-8 sm:px-6" aria-label="how it works funnel">
      <h2 className="mb-4 text-center font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
        how it works
      </h2>
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {FUNNEL_STAGES.map((stage, i) => (
          <li
            key={stage.key}
            className="rounded-md border border-border bg-surface-1/60 p-3 text-left"
          >
            <div className="font-mono text-[10px] text-muted-foreground">{`0${i + 1}`}</div>
            <div className="mt-0.5 text-xs font-semibold tracking-tight text-foreground">
              {stage.label}
            </div>
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{stage.blurb}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function EntryCards() {
  const cards = [
    { href: "/games", title: "Games", body: "Today's slate as cards -> one coherent prediction, key markets, a best bet in units (or no bet), and the full dashboard." },
    { href: "/records", title: "Records", body: "Full paper-bets history: all 3284 logged predictions with matchup, model prob, tier, result, and CLV status. Filters by sport, tier, and result." },
    { href: "/paper-trading", title: "Paper trading", body: "Paper-mode prediction pipeline: live predictions tracked in units only. No real-money positions. Calibration, not edge." },
    { href: "/how-it-works", title: "How it works", body: "The full DATA -> VALIDATION funnel, and why an honest REJECT is a success." },
    { href: "/system", title: "System", body: "Parity grid, the self-improve ratchet (READY, not enabled), honest findings." },
  ];
  return (
    <section className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {cards.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="group rounded-lg border border-border bg-surface-1/60 p-4 transition-colors hover:border-foreground/30 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
          >
            <div className="text-sm font-semibold tracking-tight text-foreground">{c.title}</div>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{c.body}</p>
            <span className="mt-3 inline-block font-mono text-[10px] uppercase tracking-wider text-muted-foreground group-hover:text-foreground">
              open -&gt;
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function Findings() {
  return (
    <section className="mx-auto max-w-5xl px-4 py-8 sm:px-6" aria-label="honest findings">
      <h2 className="mb-4 text-center font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
        honest headline findings
      </h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {HONEST_FINDINGS.map((f) => (
          <div key={f.title} className="rounded-lg border border-border bg-surface-1/60 p-4">
            <div className="text-sm font-semibold tracking-tight text-foreground">{f.title}</div>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{f.body}</p>
          </div>
        ))}
      </div>
      <p className="mx-auto mt-6 max-w-3xl rounded-md border border-warning/30 bg-warning/5 px-4 py-3 text-center text-[11px] leading-relaxed text-muted-foreground">
        <span className="font-semibold uppercase tracking-wider text-warning">
          Calibration, not a market edge.
        </span>{" "}
        {HONEST_DISCLAIMER}
      </p>
    </section>
  );
}

export default function Home() {
  return (
    <div className="pb-12">
      <Hero />
      <Suspense fallback={null}><HomeStatusRow /></Suspense>
      <Suspense fallback={null}><HomeRecordsHero /></Suspense>
      <FunnelStrip />
      <EntryCards />
      <Findings />
    </div>
  );
}
