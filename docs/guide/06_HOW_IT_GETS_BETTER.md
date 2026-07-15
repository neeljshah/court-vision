# 06 - How the AI Gets Better

This is the honest story of how the predictor improves over time. The short
version: it learns from **real, settled game outcomes**, proposes a recalibrated
forecaster, and ships it **only** when a panel of strict validation gates agrees
it is genuinely better -- otherwise it honestly reports "no candidate" and holds
the current model. Most cycles ship nothing. That is by design.

Throughout: **calibration is not edge.** A lower Brier score means our
probabilities are better-calibrated, **not** that we beat the closing line or
make money. No dollars are claimed anywhere. Everything here is paper-only, and
the self-improve loop runs in **measurement-only** mode until a human flips it on.

---

## The loop in one picture

```
  settled games (real outcomes)
            |
            v
  [ ingest ]  classify feed: STALE / IDLE / FRESH_NEW   (a dead feed never reads "green")
            |
            v
  [ readout ]  honest Brier / ECE / BSS-vs-close on real results
            |
            v
  [ recalibrate ]  leak-free walk-forward isotonic map (game N uses ONLY games < N)
            |
            v
  [ eval-gate ]  5 do-no-harm gates  +  CLV second-corpus guard
            |
   +--------+-----------------------------+
   |        |              |               |
  SHIP     HOLD          REJECT     INSUFFICIENT_DATA
 (rare)  (no gain)   (regressed/leak)   (cold start)
            |
            v
  append-only improve_ledger.jsonl  -->  /models page
```

Source of the cycle: `scripts/platformkit/self_improve.py` (`improve_cycle`).

---

## Step 1 - Ingest only real, settled games

The loop only learns from games that have actually finished. The hard part is
honesty about the data feed itself. `scripts/platformkit/improve/settled_ingest.py`
classifies every fetch into one of three states, because a dead feed and a quiet
offseason both return an empty list and would otherwise look identical:

- **STALE** -- the board failed to fetch/parse. The feed is dead, so the loop
  **freezes** its progress clock and marks itself `DEGRADED`. It never reads green
  off a broken feed.
- **IDLE** -- boards parsed fine but produced no new finals (offseason / already
  folded). Honest idle, not a failure.
- **FRESH_NEW** -- at least one clean, unseen final to fold in.

A per-sport high-water mark guarantees the loop **never skips and never
double-counts** a game, and a degraded batch downgrades rather than zero-filling a
missing outcome.

## Step 2 - Honest readout

Before changing anything, the loop scores the current model on the real settled
results: Brier, ECE (calibration error), sharpness, and -- where a de-vigged
closing price exists -- a Brier Skill Score versus that close. This answers "is
the model actually any good?" It is a **diagnostic, not an edge claim**
(`honest_readout` in `self_improve.py`).

## Step 3 - Build a recalibration candidate (leak-free)

The candidate is a **walk-forward isotonic recalibration**
(`scripts/platformkit/recalibration.py::walk_forward_recalibrate`). For game N,
the calibration map is fit on **only** games `0 .. N-1` -- strictly the past.
Games before a warmup window pass through raw. This is the same leak-free
expanding-window discipline used across the system, so a candidate can never peek
at the outcome it is being scored on.

If there is not enough real settled data to fit a map (cold start), or the feed is
dead, the builder honestly returns **`NO_CANDIDATE`** rather than fabricate one.

## Step 4 - The eval-gate ratchet (5 gates, do-no-harm)

A candidate ships only if it survives the gate, which is built to **refute**, not
confirm. The honest ship gate lives in `src/loop/gate.py`; for the recalibration
ratchet the do-no-harm comparison is in `self_improve.py::improve_cycle`. The five
criteria:

1. **Walk-forward** -- expanding folds; **every** fold's holdout score must improve
   (one bad fold fails the whole thing).
2. **Null-shuffle control** -- the real improvement must beat a shuffled-label null
   distribution by a wide margin (z >= 3), so a lucky alignment cannot pass.
3. **Ablation vs full model** -- the candidate is added to the **full** production
   feature matrix and must move the holdout on the margin; it is never scored in
   isolation.
4. **Calibration** -- reliability / coverage (binned ECE for win-prob targets,
   interval coverage for variance targets) must stay within tolerance.
5. **CLV** -- closing-line value versus the sharpest line. Where no liquid closing
   prices exist yet, CLV is **non-blocking and recorded as pending** -- never
   faked as a pass.

A **Benjamini-Hochberg FDR correction** runs across all tested candidates so we do
not get fooled by multiple comparisons. The ratchet's no-regression rule
(`improve_cycle`) is the do-no-harm core: the recalibrated forecaster is compared
game-for-game against the **frozen** raw model with a cluster-robust
Diebold-Mariano test, and it can only ratchet forward.

### The four verdicts

- **SHIP** -- gates pass with no regression/leak **and** Brier improves past a
  pre-registered tolerance (~0.005). Only here do we move forward. Rare.
- **HOLD** -- gates pass but there is no meaningful improvement (already
  well-calibrated). Honest, not a failure.
- **REJECT** -- the candidate regresses versus the frozen baseline, or the leak
  guard fires.
- **INSUFFICIENT_DATA** -- too few real settled games (cold start). Logged
  honestly; never a fabricated win.

Every verdict is appended to `data/frontend/improve_ledger.jsonl`.

## Step 5 - The CLV second-corpus do-no-harm guard

To ever ship, the ratchet wants **two independent corpora** agreeing. The second
one is built from settled games in `scripts/platformkit/improve/clv_corpus.py`,
and the honesty crux is this: a close-corpus fold passes **only** if the candidate
**beats the close on out-of-sample outcome Brier** -- never merely by sitting
"closer to the close." A pure shrink-toward-the-market candidate (divergence
collapsed, outcome Brier flat) yields **no corpus at all**. CLV here is a
**do-no-harm guard, not a ship-maximizer**; the ship objective stays held-out
outcome Brier, and `vs_close` stays **UNPROVEN** on every path until real closing
lines land. This whole layer is **inert** unless a human creates the
`PIPELINE_ENABLED` sentinel (`scripts/platformkit/improve/recalibrate_with_corpus.py`).

---

## What is actually happening right now (the honest status)

This is the part most projects hide. The live ledger
(`data/frontend/improve_ledger.jsonl`) has grown to **4,132 cycles**, and as of
2026-07-15 it holds **504 `SHIP` verdicts** (the first landed 2026-06-21), with the
rest split across `HOLD`, `REJECT`, and `INSUFFICIENT_DATA`. Each `SHIP` is a
leak-free calibration ratchet -- a Brier improvement over the frozen baseline that
survived every gate -- **not** a dollar edge or a betting result. The
recalibration/CLV pipeline is built and tested but remains **measurement-only /
flag-OFF** until a human enables it.

That is the intended behavior: a `SHIP` verdict only fires when every gate agrees
the candidate is genuinely better on held-out calibration; `HOLD` and
`INSUFFICIENT_DATA` cycles are still common and are a success, not a bug.

---

## How to monitor improvement on the /models page

The `/models` page (`webapp/app/models/page.tsx`, titled "how the AI is getting
better") is the dashboard for all of this. It reads the append-only ledgers; it
never recomputes. Panels to watch:

- **Self-improve + ratchet FSM** -- the current state (cold start / hold / ship)
  and the verdict stream.
- **Per-sport Brier / ECE / BSS delta chart** -- cycle-over-cycle calibration
  deltas for NBA / MLB / soccer / tennis; the trend logic is
  `scripts/platformkit/improve/improvement_trend.py` (`monotone_improving`,
  `regression_flag`, or `INSUFFICIENT_DATA` when there are fewer than two
  data-bearing cycles).
- **Candidate / ship / rollback timeline** and **gate-verdict ledger** -- every
  SHIP / HOLD / REJECT / INSUFFICIENT_DATA decision with its reason.
- **CLV second-corpus panel** -- shows `REPLICATION_PENDING` / `UNPROVEN` until
  real closing lines populate.

The page's rails banner (`webapp/app/models/page.tsx`) still reads `n_promoted = 0`
/ "Currently 0 ships" -- text written before the ledger grew its 504 `SHIP`
verdicts and not yet refreshed to match. Until that copy is updated, treat the
ledger file itself as the source of truth for ship counts, not the banner text.
The rest of the banner's framing still holds: measurement-only, paper-only, and
**no `$` field anywhere**.

To run a cycle yourself and watch the ledger grow:

```
python -m scripts.platformkit.self_improve
```

---

## Where to look in the repo

- `scripts/platformkit/self_improve.py` -- the one-cycle ratchet (ingest ->
  readout -> recalibrate -> gate -> SHIP/HOLD/REJECT/INSUFFICIENT_DATA).
- `scripts/platformkit/recalibration.py` -- leak-free walk-forward isotonic
  recalibration (`walk_forward_recalibrate`).
- `src/loop/gate.py` -- the 5-criterion ship gate (walk-forward, null-shuffle,
  ablation-vs-full, calibration, CLV) + Benjamini-Hochberg FDR.
- `scripts/platformkit/improve/settled_ingest.py` -- STALE / IDLE / FRESH_NEW
  settled-game ingestion with a never-skip / never-double-count high-water mark.
- `scripts/platformkit/improve/clv_corpus.py` + `clv_corpus_inject.py` +
  `recalibrate_with_corpus.py` -- the CLV second-corpus do-no-harm guard (inert
  until `PIPELINE_ENABLED`).
- `scripts/platformkit/improve/improvement_trend.py` -- the cycle-over-cycle delta
  series powering the trend panel.
- `scripts/platformkit/eval_gate/` -- the eval-gate reference core (walkforward,
  scoring, dm_test, ledger) the ratchet reuses.
- `webapp/app/models/page.tsx` + `webapp/components/models/` -- the `/models`
  monitoring dashboard.
- `data/frontend/improve_ledger.jsonl` -- the append-only verdict ledger (local).
- `docs/JOB_EVIDENCE_PACKET.md` -- the truth source for any claim in this doc.

---
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
