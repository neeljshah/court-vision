// MethodEntries.tsx -- the method entries of /methodology/ (review
// docs/research/site/OPUS_I_METHODOLOGY_2026-10-21.md, P1-P10). Each entry is two or
// three sentences, links the public artifact that backs it, and says what it is as of.
// Numbers print only through FigureValue (lib/figures.ts); calibration language only.
// Entries 8 and 9 (retractions, not claimed) live in the page's do-not-claim rail.
import type { ReactNode } from "react";
import Link from "next/link";
import { FigureValue } from "@/components/evidence";
import { AsOfBadge } from "@/components/evidence/AsOfBadge";
import { blobUrl } from "@/components/evidence/kit";
import { FIGURES } from "@/lib/figures";

export type ArtifactLink = { label: string; path?: string; route?: string };
export type MethodEntry = { id: string; term: string; body: ReactNode; links: ArtifactLink[]; asOf: ReactNode };

const LINK = "text-primary underline-offset-2 hover:underline";
const EXCERPT_AS_OF = "excerpt pinned at commit 626fe42f0";

/** The artifact links and the as-of line under an entry. */
export function EntryMeta({ links, asOf }: { links: ArtifactLink[]; asOf: ReactNode }) {
  return (
    <span className="block text-xs leading-relaxed text-faint">
      artifact:{" "}
      {links.map((l, i) => (
        <span key={l.label}>
          {i ? ", " : ""}
          {l.route ? (
            <Link href={l.route} className={LINK}>{l.label}</Link>
          ) : (
            <a href={blobUrl(l.path!)} className={`${LINK} font-data`}>{l.label}</a>
          )}
        </span>
      ))}
      {" "}| as of {asOf}
    </span>
  );
}

export const METHOD_ENTRIES: MethodEntry[] = [
  {
    id: "devig",
    term: "De-vig and the close",
    body: (
      <>
        The close is the last pregame price each public archive records: the closing moneyline in
        the sportsbookreviewsonline MLB archive, Pinnacle&apos;s closing over/under 2.5 via
        football-data.co.uk, and for NBA the ESPN odds endpoint, whose cached price carries no
        snapshot timestamp, so it is not established that it is the closing price. Primary rows use
        proportional de-vig; Shin&apos;s insider-share model is the sensitivity check and changes no
        verdict.
      </>
    ),
    links: [
      { label: "DEVIG_METHODS.md", path: "docs/evidence/method/DEVIG_METHODS.md" },
      { label: "PREGAME_VS_CLOSE_2026.md", path: "docs/papers/PREGAME_VS_CLOSE_2026.md" },
      { label: "eval_gate/shin.py", path: "scripts/platformkit/eval_gate/shin.py" },
    ],
    asOf: <AsOfBadge asOf={FIGURES.mlb_ml_pregame_vs_close.as_of} />,
  },
  {
    id: "walk-forward",
    term: "Walk-forward, leak-free",
    body: (
      <>
        Every score is out of sample and forward in time. The public gate harness walks an
        expanding window: each test game is predicted only from strictly earlier games, after
        dropping same-team games within <FigureValue asOf={false} k="walkforward_purge_hours" /> hours
        of it and the same matchup within <FigureValue asOf={false} k="walkforward_embargo_days" /> days
        of the fold boundary, and a feature whose availability time is not strictly before the
        prediction time raises a LEAK error that fails the run. The private engine adds a per-fold
        assertion that the last training date precedes the first test date, published as a verbatim
        excerpt.
      </>
    ),
    links: [
      { label: "eval_gate/walkforward.py", path: "scripts/platformkit/eval_gate/walkforward.py" },
      { label: "eval_gate/test_gate.py", path: "scripts/platformkit/eval_gate/test_gate.py" },
      { label: "WALK_FORWARD_LEAK_ASSERT.md", path: "docs/evidence/method/WALK_FORWARD_LEAK_ASSERT.md" },
    ],
    asOf: <AsOfBadge asOf={FIGURES.walkforward_purge_hours.as_of} />,
  },
  {
    id: "truncation",
    term: "Truncation-invariant",
    body: (
      <>
        A private test featurizes one game&apos;s play-by-play, re-featurizes only the first half of
        its events, and requires the row at that one mid-game cut to equal the full-stream row field
        by field, minus the exempt fields (value equality, not byte identity). It is one cut on one game, and it skips when no
        local game is present, so a skip is not a pass.
      </>
    ),
    links: [{ label: "TRUNCATION_INVARIANCE.md", path: "docs/evidence/method/TRUNCATION_INVARIANCE.md" }],
    asOf: EXCERPT_AS_OF,
  },
  {
    id: "two-corpus",
    term: "Two corpora (acceptance rule)",
    body: (
      <>
        A calibration is enabled, and a candidate signal is shipped, only if it scores better than
        the uncalibrated baseline out of sample on at least two independent corpora that each meet a
        sample floor; a one-corpus lift stays provisional. The rule covers calibrations and signals
        only: the model-versus-market verdicts on this site are each measured on a single corpus per
        sport and say so.
      </>
    ),
    links: [{ label: "MULTICORPUS_ACCEPTANCE.md", path: "docs/evidence/method/MULTICORPUS_ACCEPTANCE.md" }],
    asOf: EXCERPT_AS_OF,
  },
  {
    id: "paired",
    term: "Paired comparison",
    body: (
      <>
        Model and devigged close are scored on the same held-out games; the gap is mean Brier, model
        minus close, tested with Diebold-Mariano and a game-clustered 95% interval, and each row
        records its minimum detectable effect (MDE). On NBA moneyline, at n ={" "}
        <FigureValue asOf={false} k="nba_ml_pregame_vs_close_shin" field="n" /> with an MDE of{" "}
        <FigureValue asOf={false} k="nba_ml_pregame_vs_close_shin" field="mde" /> Brier, the verdict
        is cannot tell (interval includes zero; underpowered).
      </>
    ),
    links: [
      { label: "DM_RECOMPUTE_2026-09-24.md", path: "docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md" },
      { label: "eval_gate/dm_test.py", path: "scripts/platformkit/eval_gate/dm_test.py" },
      { label: "eval_gate/dm_recompute_pregame.py", path: "scripts/platformkit/eval_gate/dm_recompute_pregame.py" },
    ],
    asOf: <AsOfBadge asOf={FIGURES.nba_ml_pregame_vs_close_shin.as_of} />,
  },
  {
    id: "in-game",
    term: "In-game reference",
    body: (
      <>
        In play, the reference is the contemporaneous Kalshi in-play price on the same tick, never a
        close; model and price are scored on identical ticks with a game-clustered interval, and the
        lag of our copy of the book is measured, because a stale copy is not a fair reference. Both
        Gate A-0 corpora later failed the join-integrity check: the MLB verdict survived two repairs,
        and the soccer verdict has not been re-established.
      </>
    ),
    links: [
      { label: "GATE_A0_2026-09-14.md", path: "docs/evidence/ingame/GATE_A0_2026-09-14.md" },
      { label: "INGAME_VS_MARKET_2026.md", path: "docs/papers/INGAME_VS_MARKET_2026.md" },
      { label: "check_ingame_join_integrity.py", path: "scripts/platformkit/check_ingame_join_integrity.py" },
    ],
    asOf: <AsOfBadge asOf={FIGURES.mlb_ingame_vs_kalshi_mid.as_of} />,
  },
  {
    id: "forward",
    term: "Forward paper protocol",
    body: (
      <>
        Paper only; no order has been placed. Games are named on a schedule written before they
        start, and each night is scored under a sealed preregistration (sha256 recorded) whose scoring
        identity stays frozen until a cell reaches{" "}
        <FigureValue asOf={false} k="forward_cell_floor_games" /> games; below that floor a cell reads
        INSUFFICIENT, as every pooled cell did through the latest counted window. It reports counts
        only: an operations and calibration record, not a verdict on the model.
      </>
    ),
    links: [
      { label: "PREREG_2026-09-24.json", path: "docs/evidence/forward/scoreboard/PREREG_2026-09-24.json" },
      { label: "PREREG_2026-10-07.json", path: "docs/evidence/forward/scoreboard/PREREG_2026-10-07.json" },
      { label: "packet section 5", path: "docs/JOB_EVIDENCE_PACKET.md" },
      { label: "the record", route: "/desk/" },
    ],
    asOf: <AsOfBadge asOf={FIGURES.forward_window_counts.as_of} />,
  },
];

export function MethodList() {
  return (
    <dl className="prose-console m-0 grid gap-4 p-4">
      {METHOD_ENTRIES.map((d) => (
        <div key={d.id} id={d.id} className="grid scroll-mt-20 gap-1">
          <dt className="font-data text-sm font-semibold text-foreground">{d.term}</dt>
          <dd className="m-0 grid gap-1 text-sm leading-relaxed text-muted-foreground">
            <span>{d.body}</span>
            <EntryMeta links={d.links} asOf={d.asOf} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
