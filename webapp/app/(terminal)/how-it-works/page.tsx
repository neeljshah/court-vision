// How it works (/how-it-works) -- the in-depth, honest "how the AI works" page.
//
// Four parts, all honest, no $ field, no fabricated edge:
//   (a) the FULL funnel DATA -> SIGNALS -> MODELS -> ENGINES -> ONE PREDICTION ->
//       INTELLIGENCE, with what each stage IS (FunnelDetail).
//   (b) the VALIDATION DISCIPLINE explained visually -- 8 stacked controls and
//       why most signals honestly REJECT and that's success (ValidationDiscipline).
//   (c) the HONEST FINDINGS: the depth plateau per sport, the CONFIRMED soccer
//       corners CALIBRATION survivor, parity GREEN (HonestFindings, from the
//       on-disk gate verdict artifacts).
//   (d) the self-improve ratchet as READY-but-INERT, human-gated (SelfImproveExplainer).
//
// HONESTY RAILS: everything is CALIBRATION, not a market edge; vs_close UNPROVEN;
// markets are efficient; CLV is the only honest yardstick; real-money default-DENY;
// paper mode only; local only. Live status is fetched from real endpoints; the
// narrative is the documented honest framing -- no number is invented here.

import Link from "next/link";
import { HONEST_DISCLAIMER, PRODUCT_NAME } from "@/lib/api";
import { WhatAmILookingAt } from "@/components/explain/WhatAmILookingAt";
import { FunnelDetail } from "@/components/explain/FunnelDetail";
import { ValidationDiscipline } from "@/components/explain/ValidationDiscipline";
import { HonestFindings } from "@/components/explain/HonestFindings";
import { SelfImproveExplainer } from "@/components/explain/SelfImproveExplainer";

export const metadata = {
  title: "How it works",
  description:
    "How CourtVision works, honestly: the full data-to-intelligence funnel, the " +
    "validation discipline that makes most signals reject, the recorded findings, " +
    "and the ready-but-inert self-improve ratchet. Calibration, not a market edge.",
};

export default function HowItWorksPage() {
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-10 p-6">
      <header>
        <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
          how the AI works -- in depth
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          How {PRODUCT_NAME} works
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          One pipeline turns raw game data into a single calibrated prediction per
          market, then re-validates every stage. Markets are efficient; the honest,
          defensible win is matching the devigged close within noise -- plus a measured
          in-game calibration edge.{" "}
          <span className="text-foreground">No dollar edge is claimed.</span>
        </p>
      </header>

      <WhatAmILookingAt />
      <FunnelDetail />
      <ValidationDiscipline />
      <HonestFindings />
      <SelfImproveExplainer />

      <p className="rounded-md border border-warning/30 bg-warning/5 px-4 py-3 text-center text-[11px] leading-relaxed text-muted-foreground">
        <span className="font-semibold uppercase tracking-wider text-warning">
          Calibration, not a market edge.
        </span>{" "}
        {HONEST_DISCLAIMER}
      </p>

      <div className="flex flex-wrap justify-center gap-3">
        <Link
          href="/games"
          className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
        >
          See it on live Games
        </Link>
        <Link
          href="/system"
          className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
        >
          Inspect the System
        </Link>
      </div>
    </main>
  );
}
