// app/methodology/page.tsx -- how every number on this site is earned, and
// what it is forbidden to claim. Static export: reads the staged check_all
// proof-harness report off disk at build time (the /receipts pattern) so the
// "N/N modules pass" count is measured, never hand-typed. No client fetch.
//
// This page is the anchor target for every receipt chip's "what does verified
// mean" link (#verified) and the do-not-claim rail (#do-not-claim).

import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { HonestBanner } from "@/components/showcase/HonestBanner";
import { ReproduceBlock } from "@/components/showcase/ReproduceBlock";

export const metadata = {
  title: "Methodology",
  description:
    "The discipline behind every number: leak-free, walk-forward, " +
    "truncation-invariant, two or more corpora -- plus the one-command proof " +
    "harness and the do-not-claim rail.",
};

type CheckRow = { module: string; status: string; as_of?: string };

// ponytail: read the staged proof report straight off disk at build time --
// static export, so there is no server later. Missing on a fresh clone -> the
// count renders as pending rather than a fabricated green.
function loadCheckAll(): { pass: number; total: number; asOf: string | null } | null {
  try {
    const raw = readFileSync(
      join(process.cwd(), "public/data/showcase/check_all_report.json"),
      "utf-8"
    );
    const rows = JSON.parse(raw) as CheckRow[];
    if (!Array.isArray(rows) || rows.length === 0) return null;
    const pass = rows.filter((r) => r.status === "PASS").length;
    const asOf = rows
      .map((r) => r.as_of)
      .filter((s): s is string => Boolean(s))
      .sort()
      .pop();
    return { pass, total: rows.length, asOf: asOf ? asOf.slice(0, 10) : null };
  } catch {
    return null;
  }
}

const DISCIPLINE = [
  {
    term: "Leak-free",
    body:
      "No feature sees anything the market could not see at decision time. " +
      "As-of joins only; a future-leak fails the gate closed.",
  },
  {
    term: "Walk-forward",
    body:
      "Every score is out-of-sample and forward in time: fit on the past, " +
      "measure on the strictly later fold. No in-sample lift is ever reported.",
  },
  {
    term: "Truncation-invariant",
    body:
      "The result must hold when the sample is truncated at either end. A number " +
      "that only appears at one cut point is a measurement artifact, not a signal.",
  },
  {
    term: "Two or more corpora",
    body:
      "A claim must reproduce across at least two independent corpora. A single- " +
      "fold lift is treated as noise until a second corpus confirms it.",
  },
];

const VERIFIED_ROWS: { badge: string; tone: string; meaning: string }[] = [
  {
    badge: "edge_claimed:false",
    tone: "text-info border-info/50",
    meaning:
      "Measured, out-of-sample, and NOT a dollar-edge claim. This is the default " +
      "and the point: calibration and sharpness only.",
  },
  {
    badge: "descriptive_only",
    tone: "text-info border-info/50",
    meaning:
      "A descriptive summary of past data (atlas cards). Not a prediction, not a " +
      "claim of future performance.",
  },
  {
    badge: "MODEL_SHARPER_PROVISIONAL",
    tone: "text-success border-success/50",
    meaning:
      "The model's calibration beat the devigged close on this fold, provisionally. " +
      "Shown at the same size as a loss.",
  },
  {
    badge: "MARKET_SHARPER_PROVISIONAL",
    tone: "text-danger border-danger/50",
    meaning:
      "The market was sharper than the model here. An honest loss, rendered red, " +
      "never hidden or softened.",
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

const DO_NOT_CLAIM = [
  "+18.38%  (a pregame market-follow artifact, not the model)",
  "0.119    (an end-of-Q3 win-prob figure with a Q4 leak)",
  "+54%     (an in-play L5-proxy ceiling, not realized performance)",
  "78.11    (the same L5-proxy ceiling as an accuracy figure)",
  "8.94  /  54.57  (retracted inflated figures)",
];

export default function MethodologyPage() {
  const check = loadCheckAll();
  const countLabel = check ? `${check.pass}/${check.total}` : "pending";

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header className="prose-console">
        <p className="microlabel">methodology</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          How every number here is earned
        </h1>
        <p className="text-sm leading-relaxed text-muted-foreground">
          The market is efficient. The honest, defensible win is a calibrated
          predictor that matches the devigged close within noise, plus a measured
          in-game conditioning improvement. Accuracy is not an edge, and a recorded
          null is a success. Every figure on this site carries a receipt chip that
          links back here to define what its verification badge means.
        </p>
      </header>

      <HonestBanner kind="no_edge" />

      <Panel>
        <PanelHead title="the discipline behind every claim" />
        <dl className="prose-console m-0 grid gap-4 p-4">
          {DISCIPLINE.map((d) => (
            <div key={d.term} className="grid gap-1">
              <dt className="font-data text-sm font-semibold text-foreground">
                {d.term}
              </dt>
              <dd className="m-0 text-sm leading-relaxed text-muted-foreground">
                {d.body}
              </dd>
            </div>
          ))}
        </dl>
      </Panel>

      <Panel>
        <PanelHead
          title="one-command proof harness"
          asOf={check?.asOf ?? undefined}
          stale={!check}
        />
        <div className="flex flex-col gap-3 p-4">
          <p className="prose-console m-0 text-sm leading-relaxed text-muted-foreground">
            Every showcase module ships a self-check. One command runs them all and
            prints a pass ledger. On the measured run staged into this build,{" "}
            <span className="font-data font-semibold text-foreground">
              {countLabel}
            </span>{" "}
            modules pass. The number above is read from the staged report at build
            time, not hand-typed.
          </p>
          <ReproduceBlock
            command="python -m scripts.platformkit.analytics_showcase.check_all"
            note={
              "Fresh clone: data-dependent modules fall back to a recorded artifact " +
              "so the harness stays green on a bare checkout. CI runs the same " +
              "command on every push; a red run is disclosed, never hidden."
            }
          />
        </div>
      </Panel>

      <Panel>
        <PanelHead title="what 'verified' means" />
        <div id="verified" className="scroll-mt-20 p-4">
          <p className="prose-console m-0 mb-4 text-sm leading-relaxed text-muted-foreground">
            Each receipt chip carries one of these badges. Color is meaning: blue is
            a measured, no-edge result; green is a provisional model win; red is an
            honest loss shown at full size; amber is pending or stale. Green is never
            the default.
          </p>
          <dl className="m-0 grid gap-3">
            {VERIFIED_ROWS.map((r) => (
              <div
                key={r.badge}
                className="grid gap-1.5 sm:grid-cols-[minmax(0,220px)_1fr] sm:items-start sm:gap-4"
              >
                <dt>
                  <span
                    className={`inline-block border px-1.5 py-px font-data text-[11px] ${r.tone}`}
                  >
                    {r.badge}
                  </span>
                </dt>
                <dd className="m-0 text-sm leading-relaxed text-muted-foreground">
                  {r.meaning}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </Panel>

      <Panel className="border-stale/40">
        <PanelHead title="do-not-claim rail" />
        <div id="do-not-claim" className="scroll-mt-20 p-4">
          <p className="prose-console m-0 mb-3 text-sm leading-relaxed text-muted-foreground">
            These figures were measured, then retracted as artifacts. They are listed
            here so they can never quietly reappear as live results. Each is a
            documented measurement artifact, cited in{" "}
            <span className="font-data text-foreground">
              docs/JOB_EVIDENCE_PACKET.md
            </span>
            , and appears on this site only inside retraction framing.
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
            The full retracted-vs-honest story lives on the{" "}
            <Link
              href="/evidence/retraction-story"
              className="text-primary underline-offset-2 hover:underline"
            >
              retraction page
            </Link>
            . Nothing on this site claims a dollar edge, ROI, or bankroll result.
          </p>
        </div>
      </Panel>
    </main>
  );
}
