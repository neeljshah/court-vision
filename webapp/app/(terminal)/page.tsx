// Home (/) -- Today's front door, built to the first-screen contract (DESIGN_BRIEF section 4,
// DESIGN_PRINCIPLES P2.1-P2.4): sentence; plain-words verdict; how to check (scoring rule and
// reference as Term tooltips); packet headline verdicts (largest n first) read from
// docs/evidence/CANONICAL_FIGURES.json; forward paper series status with the last night's
// receipt; what this is not; exactly two primary actions; byline. Below the fold: the in-game
// scoreboard sorted by n and the reproduce line. Build-time only; no client fetch.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import Link from "next/link";
import { loadArtifact } from "@/lib/showcase.server";
import { loadDesk } from "@/lib/desk.server";
import { headlineFigures, CANONICAL_PATH } from "@/lib/canonicalFigures.server";
import { VERDICT_QUALIFIER, type PacketVerdict } from "@/lib/packetVerdicts";
import { HomeVerdictRows } from "@/components/home/HomeVerdictRows";
import { HomeForwardStatus } from "@/components/home/HomeForwardStatus";
import { HomeNotClaimed } from "@/components/home/HomeNotClaimed";
import { HomeByline } from "@/components/home/HomeByline";
import { HomeScoreboard, type Scoreboard } from "@/components/home/HomeScoreboard";
import { Term } from "@/components/evidence";
import { JsonLd } from "@/components/seo/JsonLd";
import { pageMeta } from "@/lib/seo/meta";
import { personJsonLd, websiteJsonLd } from "@/lib/seo/jsonld";

export const metadata: Metadata = pageMeta("/", {
  title: "Calibration Scoreboard",
  description:
    "A calibrated sports forecaster that publishes its own scorecard against the market, including losses, nulls and retractions.",
});

// check_all.py's own report (build-time read): PASS / NO_CHECK counts + its as-of.
function checkCounts(): { pass: number; noCheck: number; total: number; asOf: string } | null {
  try {
    const rows = JSON.parse(readFileSync(join(process.cwd(),
      "../scripts/platformkit/analytics_showcase/out/check_all_report.json"), "utf-8")) as
      { status: string; as_of?: string }[];
    const asOf = rows.map((x) => x.as_of ?? "").sort().pop()?.slice(0, 10) ?? "";
    return { pass: rows.filter((x) => x.status === "PASS").length,
      noCheck: rows.filter((x) => x.status === "NO_CHECK").length, total: rows.length, asOf };
  } catch {
    return null;
  }
}

const PRIMARY =
  "inline-flex min-h-[44px] items-center border border-primary bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";

export default function Home() {
  const figures = headlineFigures();
  const desk = loadDesk();
  const board = loadArtifact("cross_sport_scoreboard") as Scoreboard | null;
  const checks = checkCounts();
  const asOf = figures[0]?.as_of ?? null;

  return (
    <div className="mx-auto max-w-[1200px] px-4 pb-16 sm:px-6 [overflow-wrap:anywhere]">
      <JsonLd data={[websiteJsonLd(), personJsonLd()]} />
      <section aria-labelledby="home-h1" className="space-y-3 pt-5 sm:pt-8">
        <h1 id="home-h1" className="max-w-3xl text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-2xl">
          A calibrated sports forecaster that publishes its own scorecard against the market,
          including losses, nulls and retractions.
        </h1>
        <h2 className="text-sm font-semibold text-foreground" data-testid="home-h2">
          Pregame vs the devigged close:{" "}
          {figures.map((f) => {
            const q = VERDICT_QUALIFIER[f.verdict as PacketVerdict];
            return `${f.sport.toUpperCase()} ${f.market} ${f.verdict}${q ? ` (${q})` : ""}`;
          }).join("; ")}.
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Each row below is scored by <Term id="brier">Brier score</Term> against the{" "}
          <Term id="devigged-close">devigged close</Term> and carries its sample size, 95% interval,
          as-of date and receipt. To check a number, open its receipt or the truth source,{" "}
          <span className="font-data">docs/JOB_EVIDENCE_PACKET.md</span>.
        </p>
        <HomeVerdictRows figures={figures} />
        <HomeForwardStatus desk={desk} />
        <HomeNotClaimed asOf={desk?.date ?? asOf} />
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/evidence/" className={PRIMARY}>Read the evidence</Link>
          <Link href="/games/" className={PRIMARY}>See today&apos;s board</Link>
        </div>
        <HomeByline />
      </section>

      <HomeScoreboard board={board} />

      <p className="mt-8 border-t border-border pt-4 text-xs leading-relaxed text-muted-foreground">
        How to check: the headline figures are read from <span className="font-data">{CANONICAL_PATH}</span> (recompute memo{" "}
        <span className="font-data">docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md</span>). Reproduce the
        scoreboard with{" "}
        <span className="font-data">python scripts/platformkit/analytics_showcase/check_all.py</span>{" "}
        ({checks
          ? `${checks.pass} of ${checks.total} module self-checks PASS, ${checks.noCheck} have no self-check; report as of ${checks.asOf}`
          : "check report not present on this clone"}). Truth source:{" "}
        <span className="font-data">docs/JOB_EVIDENCE_PACKET.md</span>.
      </p>
    </div>
  );
}
