import Link from "next/link";
import { SlateBrowser } from "@/components/p6/SlateBrowser";
import { ClvScoreboardLive } from "@/components/p6/ClvScoreboardLive";
import { ParityGrid } from "@/components/p6/ParityGrid";
import { RatchetPanel } from "@/components/p6/RatchetPanel";
import { PaperTrail } from "@/components/p6/PaperTrail";
import { LiveLinesPanel } from "@/components/p6/LiveLinesPanel";
import { PropsPanel } from "@/components/p6/PropsPanel";
import { InGamePanel } from "@/components/p6/InGamePanel";
import { OpsPanel } from "@/components/p6/OpsPanel";
import { SelfImprovePanel } from "@/components/p6/SelfImprovePanel";
import { GateMatrix } from "@/components/p6/GateMatrix";
import { FacesPanel } from "@/components/p6/FacesPanel";
import { QuantPanel } from "@/components/p6/QuantPanel";
import { ClvFeedbackPanel } from "@/components/p6/ClvFeedbackPanel";

export const metadata = {
  title: "Dashboard",
};

// The P6 dashboard. READ-ONLY over the P5 Auto-API (:8099). Browse the slate,
// click into a game, watch the live paper trail + ratchet + parity health.
// Panels update autonomously via SSE or polling to show the system working.
export default function P6Dashboard() {
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">
          CourtVision{" "}
          <span className="font-mono text-muted-foreground">dashboard</span>
        </h1>
        <span className="font-mono text-[11px] text-faint">
          reads P5 Auto-API -- paper-only -- no $ claimed
        </span>
      </header>

      {/* Quick-nav tiles -- links to the three dedicated view routes */}
      <nav
        aria-label="View shortcuts"
        className="flex flex-wrap gap-2"
      >
        <Link
          href="/p6/history"
          className="rounded-md border border-border bg-surface-1 px-3 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          History &rarr;
        </Link>
        <Link
          href="/system"
          className="rounded-md border border-border bg-surface-1 px-3 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          System &rarr;
        </Link>
      </nav>

      {/* Row 1: slate browser + CLV + ratchet (existing) */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-7">
          <SlateBrowser />
        </div>
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-5">
          <ClvScoreboardLive />
          <RatchetPanel />
        </div>
      </div>

      {/* Row 1b: the unified-gateway faces + the single ALL-HONEST bit
          (one model, many contracted faces; GREEN only when all_honest=true). */}
      <FacesPanel />

      {/* Row 1c: the multi-API surface made visible -- quant bet-validation
          (units only) + execution-in-the-loop CLV feedback (measurement-only). */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-7">
          <QuantPanel />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <ClvFeedbackPanel />
        </div>
      </div>

      {/* Row 2: live lines (captured odds/lines with venue + freshness) +
          player props (calibrated P(over) vs real scraped book lines, MLB +
          World Cup soccer only -- other sports have no live prop bridge yet) */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-7">
          <LiveLinesPanel />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <PropsPanel />
        </div>
      </div>

      {/* Row 3: in-game numbers + gate matrix side by side */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-7">
          <InGamePanel />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <GateMatrix />
        </div>
      </div>

      {/* Row 4: system health (incl. autonomy_status) + the self-improve loop
          state (honestly INERT / measurement-only -- ships nothing). */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-6">
          <OpsPanel />
        </div>
        <div className="col-span-12 lg:col-span-6">
          <SelfImprovePanel />
        </div>
      </div>

      {/* Row 4b: live SSE paper positions */}
      <PaperTrail />

      {/* Row 5: parity grid (existing cross-sport coverage) */}
      <ParityGrid />

      <footer className="mt-4 text-center text-[11px] text-faint">
        Calibrated decision-support only. Markets are efficient; no $ edge is
        claimed. CLV (better-number-than-close) is the only honest yardstick.
        vs-close UNPROVEN where no in-play odds are available.
      </footer>
    </main>
  );
}
