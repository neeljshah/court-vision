// app/evidence/retraction-story/page.tsx -- the self-refutation page.
//
// THE ONLY page in the site where the six retracted numbers render, and they
// render only here, inside explicit retraction framing that cites
// docs/JOB_EVIDENCE_PACKET.md (the single truth-source). Every retracted figure
// is struck through and paired with its honest, calibration-only replacement.
// No edge/ROI/bankroll language appears in any honest replacement. See
// .claude/rules/no-edge-claims.md.
//
// Header prose (title/lede/claim) is read from the staged evidence spine via the
// foundation reader (buildClaimPage), so a fresh clone with the .md absent still
// renders from the staged index. The six retraction rows are transcribed
// verbatim from JOB_EVIDENCE_PACKET s3/s4 -- the canonical retracted-vs-honest
// table -- so they stay correct even if a clone lacks docs/evidence/*.md.

import { buildClaimPage, RETRACTION_SLUG } from "@/lib/evidence.server";
import { RetractionCard } from "@/components/evidence/RetractionCard";
import { inline } from "@/components/evidence/ClaimPage";

export const metadata = {
  title: "The Retraction Story",
  description:
    "I built the instruments that refuted my own headline numbers. Six retracted " +
    "figures, each paired with its honest, calibration-only replacement.",
};

// Packet last amended 2026-07-23 (docs/JOB_EVIDENCE_PACKET.md).
const PACKET_ASOF = "2026-07-23";

// ponytail: the six rows are transcribed verbatim from JOB_EVIDENCE_PACKET
// s3/s4 (the canonical retracted-vs-honest table). Static and canonical, so a
// hardcoded const beats a fragile 4-column markdown parser -- update here if the
// packet's table ever changes. This is the ONLY place these numbers may appear.
const RETRACTIONS = [
  {
    retracted: "+18.38% pregame ROI on 1,535 walk-forward bets vs real closing lines",
    whatWasWrong:
      "Market-follow artifact, confirmed at the source-code level. The grader picked bet direction from the market's own devigged lean and never read the model (the eval CSV had no prediction column), priced at a flat -110 that real books do not offer, and tuned its filters in-sample on the same file.",
    proofArtifact: "JOB_EVIDENCE_PACKET s4 (model's own unfiltered number: -2.00%)",
    honestReplacement:
      "Roughly break-even-minus-vig vs real closing lines. Every candidate edge, including assists, was ultimately rejected or retracted by my own gates.",
  },
  {
    retracted: "0.119 end-of-Q3 in-play Brier, \"inside Pinnacle's range\"",
    whatWasWrong:
      "Leak-inflated and mis-sourced. Two features were computed from fourth-quarter data, so the model predicting Q4 was peeking at Q4; the cited file actually reported 0.1354, a different number.",
    proofArtifact: "JOB_EVIDENCE_PACKET s3 (leak-free re-run; controlled A/B ~4% relative inflation)",
    honestReplacement:
      "Leak-free walk-forward end-of-Q3 Brier ~0.141, after I removed a Q4 feature leak I found in my own pipeline. Framed as a leak I caught, not a competitive number.",
  },
  {
    retracted: "+54.57% ROI / 78.11% hit on 55,073 in-play bets",
    whatWasWrong:
      "Graded against an L5 line proxy, not real closing lines. A model-quality ceiling on a soft proxy, never a tradeable result.",
    proofArtifact: "JOB_EVIDENCE_PACKET s4",
    honestReplacement:
      "On a soft L5 proxy the in-play backtest reaches that ceiling. I treat it strictly as a model-quality ceiling, never as realized edge.",
  },
  {
    retracted: "Aggregate CLV +8.94pp",
    whatWasWrong:
      "Circular -- computed on the same model-unused, devig-direction corpus. No real Pinnacle-close CLV exists yet; a full-season backtest shows CLV about zero vs real closes.",
    proofArtifact: "JOB_EVIDENCE_PACKET s4 (full-season backtest: CLV ~= 0 vs real closes)",
    honestReplacement:
      "Real closing-line CLV cannot be measured yet. I built the methodology that will measure it; I do not quote a CLV figure until it can be.",
  },
  {
    retracted: "Steals/blocks prop grid search: training R^2 ~0.79",
    whatWasWrong:
      "Textbook leakage: the ~0.79 training R^2 collapsed to ~0.06 on a leak-free holdout.",
    proofArtifact: "src/prediction/prop_cv_split.py (documents the gap; hard-codes corrective regularization)",
    honestReplacement:
      "Caught and hard-corrected a leakage-driven overfit. The corrective regularization takes precedence over the stale tuned parameters, so the mistake cannot silently reappear.",
  },
  {
    retracted: "The assists ROI edge (the strongest surviving candidate)",
    whatWasWrong:
      "Regime-dependent -- it broke in the playoffs -- and retracted 2026-07-21. Under the no-edge rail, no dollar/ROI edge is claimed anywhere.",
    proofArtifact: "JOB_EVIDENCE_PACKET s3 (historical record only, in the gate artifacts)",
    honestReplacement:
      "No dollar or ROI edge is claimed anywhere. The historical measurement remains only as a record of the stress-testing methodology.",
  },
];

export default function RetractionStoryPage() {
  const page = buildClaimPage(RETRACTION_SLUG);
  const title =
    page?.title ??
    "The Retraction Story -- I built the instruments that refuted my own headline numbers";
  const lede =
    page?.lede ||
    "The most transparent sports forecaster you can audit: every number gated, including the ones that refuted me.";
  const claim =
    page?.claim ||
    "The same person who built this system also built the instruments that refuted his own flagship numbers, and documented the negative results in writing rather than quietly deleting them. The product is a calibrated predictor, not a betting-edge product. The strongest signal in the repo is not any metric; it is the self-refutation trail.";

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header className="prose-console">
        <p className="microlabel">evidence / retraction story</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{inline(lede)}</p>
        <p className="mt-3 text-sm leading-relaxed text-foreground">{inline(claim)}</p>
        <p className="mt-3 text-[11px] font-mono uppercase tracking-wide text-stale">
          The single truth-source for every figure below is docs/JOB_EVIDENCE_PACKET.md.
          The retracted numbers appear here, and only here, inside this retraction
          framing.
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <p className="microlabel">six headlines my own harnesses took apart</p>
        {RETRACTIONS.map((r) => (
          <RetractionCard key={r.retracted} asOf={PACKET_ASOF} {...r} />
        ))}
      </section>

      <p className="prose-console text-sm leading-relaxed text-muted-foreground">
        The through-line: against real closing lines the market is efficient, the
        model is break-even-minus-vig, and every candidate edge, including my
        strongest, was rejected or retracted by my own gates. That is the honest,
        correct result for an efficient market, and I have the harnesses that prove
        it.
      </p>
    </main>
  );
}
