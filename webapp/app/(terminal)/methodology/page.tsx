// app/methodology/page.tsx -- how every number on this site is earned, and
// what it is forbidden to claim. Static export: the self-check sentence reads
// check_all.py's report through the same loader as the home page
// (components/desk/deskExtras.server loadChecks), never hand-typed. No client fetch.
//
// This page is the anchor target for every receipt chip's "what does verified
// mean" link (#verified) and the do-not-claim rail (#do-not-claim).

import Link from "next/link";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { HonestBanner } from "@/components/showcase/HonestBanner";
import { ReproduceBlock } from "@/components/showcase/ReproduceBlock";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";
import { GateStatus, GateStatusLegend, Term, gateStatusesIn, isGateStatus } from "@/components/evidence";
import { AsOfBadge } from "@/components/evidence/AsOfBadge";
import { PACKET_HREF } from "@/components/evidence/kit";
import { loadChecks } from "@/components/desk/deskExtras.server";
import { EntryMeta, MethodList } from "@/components/methodology/MethodEntries";
import { selfCheckSentence } from "@/components/methodology/selfCheck";
import { FIGURES, FIGURES_AS_OF } from "@/lib/figures";

export const metadata: Metadata = pageMeta("/methodology/", {
  title: "Methodology",
  description:
    "The discipline behind every number: leak-free, walk-forward, " +
    "truncation-invariant, two or more corpora -- plus the one-command proof " +
    "harness and the do-not-claim rail.",
});

const VERIFIED_ROWS: { badge: string; tone: string; meaning: string }[] = [
  {
    badge: "edge_claimed:false",
    tone: "text-info border-info/50",
    meaning:
      "Measured out of sample, with no claim of an advantage over the market: " +
      "calibration and sharpness only. This is the default badge, and the point.",
  },
  {
    badge: "descriptive_only",
    tone: "text-info border-info/50",
    meaning:
      "A descriptive summary of past data (atlas cards). Not a prediction and not " +
      "a claim about future performance.",
  },
  {
    badge: "MODEL_SHARPER_PROVISIONAL",
    tone: "text-success border-success/50",
    meaning:
      "The model scored sharper than the live market on this cell (CRPS or Brier) " +
      "in a small-sample retrospective diagnostic. Provisional: the reference is " +
      "the live market, not the devigged close. Shown at the same size as a loss.",
  },
  {
    badge: "MARKET_SHARPER_PROVISIONAL",
    tone: "text-danger border-danger/50",
    meaning:
      "The market scored sharper than the model here and the interval excludes " +
      "zero, on a single corpus. A loss, shown in red at full size, never softened.",
  },
  {
    badge: "UNDERPOWERED",
    tone: "text-faint border-border",
    meaning:
      "The sample was too small to separate model from market. Neutral, not green: " +
      "an underpowered result is not a win.",
  },
  {
    badge: "VALIDATION_PENDING",
    tone: "text-stale border-stale/50",
    meaning:
      "The cited artifact was not built on this clone, so the number is not yet " +
      "measured here. Amber, never silently green.",
  },
];

const RETIRED_HREF = `${PACKET_HREF}#4-retired-figures-retracted-or-unverifiable-not-claimed-anywhere-in-this-repository`;

const DO_NOT_CLAIM = [
  "+18.38%  (a pregame market-follow artifact, not the model)",
  "0.119    (an end-of-Q3 win-prob figure with a Q4 leak)",
  "+54%     (an in-play L5-proxy ceiling, not realized performance)",
  "78.11    (the same L5-proxy ceiling as an accuracy figure)",
  "8.94  /  54.57  (retracted inflated figures)",
];

export default function MethodologyPage() {
  const checks = loadChecks();

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header className="prose-console">
        <p className="microlabel">methodology</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          How every number here is checked
        </h1>
        <p className="text-sm leading-relaxed text-muted-foreground">
          This page says how a number earns a place on this site and what the site
          is forbidden to claim. The headline result of those checks: pregame, the
          model trails the <Term id="devigged-close">devigged close</Term> on MLB
          moneyline and soccer over/under 2.5; on NBA moneyline it cannot tell (interval
          includes zero; underpowered). In play, its win probabilities score behind
          the live Kalshi price on the same ticks for MLB and international soccer
          (measured before a join-integrity repair; the MLB verdict survived two
          repairs, the soccer verdict has not been re-established). A recorded null is a result, not a failure. To check a figure, open
          its receipt chip (each links back here) or run the one-command harness below.
        </p>
      </header>

      <HonestBanner kind="no_edge" />

      <Panel>
        <PanelHead title="the discipline behind every claim" />
        <MethodList />
      </Panel>

      <Panel>
        <PanelHead
          title="one-command proof harness"
          asOf={checks?.asOf ?? undefined}
          stale={!checks}
        />
        <div className="flex flex-col gap-3 p-4">
          <p className="prose-console m-0 text-sm leading-relaxed text-muted-foreground">
            Every showcase module ships a self-check. One command runs them all and
            prints a pass ledger. On the report committed with this build:{" "}
            <span data-testid="self-check" className="font-data font-semibold text-foreground">
              {checks
                ? `${selfCheckSentence(checks)} (report as of ${checks.asOf})`
                : "check report not present on this clone"}
            </span>
            . The home page reads the same report through the same loader.
          </p>
          <ReproduceBlock
            command="python -m scripts.platformkit.analytics_showcase.check_all"
            note={
              "Fresh clone: data-dependent modules fall back to a recorded artifact " +
              "so the harness stays green on a bare checkout. CI runs the same " +
              "command on pushes that touch the showcase or the evidence, and " +
              "weekly; a red run stays in the Actions history, never hidden."
            }
          />
        </div>
      </Panel>

      <Panel>
        <PanelHead title="what 'verified' means" />
        <div id="verified" className="scroll-mt-20 p-4">
          <p className="prose-console m-0 mb-4 text-sm leading-relaxed text-muted-foreground">
            Each receipt chip carries one of these badges. Color is meaning: blue is
            a measured result that claims nothing against the market; green is a
            provisional model win; red is a loss shown at full size; amber is pending
            or stale. Green is never the default.
          </p>
          <dl className="m-0 grid gap-3">
            {VERIFIED_ROWS.map((r) => (
              <div
                key={r.badge}
                className="grid gap-1.5 sm:grid-cols-[minmax(0,220px)_1fr] sm:items-start sm:gap-4"
              >
                <dt>
                  {isGateStatus(r.badge) ? (
                    <GateStatus token={r.badge} />
                  ) : (
                    <span
                      className={`inline-block border px-1.5 py-px font-data text-[11px] ${r.tone}`}
                    >
                      {r.badge}
                    </span>
                  )}
                </dt>
                <dd className="m-0 text-sm leading-relaxed text-muted-foreground">
                  {r.meaning}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-4">
            <GateStatusLegend tokens={gateStatusesIn(VERIFIED_ROWS.map((r) => r.badge))} />
          </div>
        </div>
      </Panel>

      <Panel className="border-stale/40">
        <PanelHead title="do-not-claim rail" />
        <div id="do-not-claim" className="scroll-mt-20 p-4">
          <p className="prose-console m-0 mb-3 text-sm leading-relaxed text-muted-foreground">
            These figures were measured, then retracted as artifacts. They are listed
            here so they can never quietly reappear as live results. Each is a
            documented measurement artifact, cited in{" "}
            <a href={RETIRED_HREF} className="font-data text-primary underline-offset-2 hover:underline">
              docs/JOB_EVIDENCE_PACKET.md
            </a>{" "}
            section 4, and appears on this site only inside retraction framing.
          </p>
          <ul className="m-0 grid list-none gap-1.5 p-0">
            {DO_NOT_CLAIM.map((line) => (
              <li
                key={line}
                className="font-data text-[13px] text-faint line-through decoration-danger/60"
              >
                {line}
              </li>
            ))}
          </ul>
          <p className="prose-console m-0 mt-4 text-sm leading-relaxed text-muted-foreground">
            The full record, each withdrawn figure beside the wording that replaces
            it, is the{" "}
            <Link
              href="/evidence/retractions/"
              className="text-primary underline-offset-2 hover:underline"
            >
              retraction record
            </Link>
            .
          </p>
          <p data-entry="retractions" className="prose-console m-0 mt-3 text-sm leading-relaxed text-muted-foreground">
            Each was found by the project&apos;s own audits: a source-level audit showed the
            pregame ROI grader bet the market&apos;s own devigged lean and never read the model, a
            lookahead audit found the Q4 leak, and the in-play figures proved to be an L5-proxy
            ceiling, not realized performance. Since then the canonical-figures check fails a build
            that reprints one outside retraction framing.{" "}
            <EntryMeta
              links={[
                { label: "/evidence/retractions/", route: "/evidence/retractions/" },
                { label: "docs/KNOWN_LIMITATIONS.md", path: "docs/KNOWN_LIMITATIONS.md" },
              ]}
              asOf={<AsOfBadge asOf={FIGURES_AS_OF} />}
            />
          </p>
          <p data-entry="not-claimed" className="prose-console m-0 mt-3 text-sm leading-relaxed text-muted-foreground">
            Nothing on this site claims a dollar edge, ROI, bankroll result, forward track record,
            or execution quality; simulated fill counts are counts, not results.{" "}
            <EntryMeta
              links={[{ label: "docs/JOB_EVIDENCE_PACKET.md", path: "docs/JOB_EVIDENCE_PACKET.md" }]}
              asOf={<AsOfBadge asOf={FIGURES.paper_desk_fill_counts.as_of} />}
            />
          </p>
        </div>
      </Panel>
    </main>
  );
}
