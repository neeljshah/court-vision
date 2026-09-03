# S114 -- NESTED-selection ensemble of NBA in-game hypotheses, on the pod

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S114. S102 screened 564 NBA derived-state
hypotheses one at a time; S79 showed a family's top-k picked IN SAMPLE is worse than k=1 in
11 of 12 families. Nobody had combined in-game hypotheses with the SELECTION ITSELF inside
the walk-forward.

Verdict: **SCREEN_NULL -- no k clears the +0.004 bar, and every k is BEHIND the raw in-play
line.** Best arm k=5 at **-0.000400** Brier against the raw market (game-clustered DM 95 pct
CI `[-0.000934, +0.000133]`, crossing zero), which is 10x below the bar ON THE WRONG SIDE.
All four arms are also behind the S94 recalibration null. **No prereg DRAFT was written.**

Two findings the row asked for, both measured and both honest:

1. **S102's headline does not survive nested selection.** S102's best single hypothesis was
   `margin_over_sqrt_rem|raw` at +0.000248 over the recalibration null -- chosen after seeing
   all 564 out-of-sample results. When the choice is made on the TRAIN window only, the k=1
   arm is **-0.000125 BEHIND that same null**, and `margin_over_sqrt_rem|raw` is never picked
   in any fold. Exactly **1 of S102's top 10** (`tdm_h600|dprior`) is ever selected here.
2. **S79's "combining is worse than k=1" does NOT reproduce under nested selection.**
   k=5 beats k=1 by **+0.0000830**, CI `[+0.0000027, +0.0001634]`, p 0.0429 -- the one CI in
   this memo that excludes zero. Diversifying by DISTINCT source column adds a real but tiny
   amount. It is 48x below the bar and does not lift the arm back to the raw line.

Uncharged: no prereg seal, no ledger read, no ledger write, no K consumed;
`data/cache/eval_gate/backtest_fwer.jsonl` is **absent on the pod** (verified before and after)
and untouched locally at 18 rows, md5 `a4ae7c13995672e478d59770591b83ba`. **SINGLE-WINDOW**
(one corpus, the S86 SCREEN side, NBA 2024-10-22..2026-06-10); the 796-game VERDICT side was
never opened. `data/registry/` untouched, no flag flipped, no `--force`, no push, no git on
the pod, nothing read or written under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/`, `foundry/` or the S115/S116 lane files.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked in
section 8). Calibration measurement only -- no dollar, ROI, profit or edge language, and no
retracted figure appears. **No bar moved** (`BAR` is IMPORTED from `foundry/ingame_screen.py`
and is never assigned in this module; the per-file test asserts both).  ASCII only.

Module: `scripts/platformkit/eval_gate/s114_ingame_ensemble.py` (298 lines)
Test: `python -m pytest tests/platformkit/ingame/test_s114_ingame_ensemble.py -q` = **7 passed**
(2.09 s local / 4.34 s on the pod's Python)
Artifacts: `data/cache/eval_gate/s114_ingame_ensemble.json` (26,927 B, md5
`7b6c0dc2cc8b0eb013adeee0310d15bf`), `..._series.csv` (192,635 rows, md5
`134d945a592c3532aa5abdfded711f8e`), `..._screens.csv` (2,814 rows, md5
`b2869b91a9ae30d8c5285bedb3e4c919`), `..._ingame_ensemble.log`. All three byte-identical on
the pod and locally.

---

## 0. STEP 0 -- premise re-measured first (Q8), CONFIRMED

| the row says | measured 2026-09-03 | verdict |
|---|---|---|
| the S102 artifacts carry a screen p, an improvement, a source column, a transform and a conditioning per hypothesis | `data/cache/eval_gate/s102_nba_sweep.sqlite`, table `screen`: `hypothesis_id, label, feature, transform, params, phase, status, n_ticks, n_games, n_informative, n_eff, brier_market, brier_null, brier_candidate, improvement_vs_null, dm_stat, dm_p_raw, ci_lo, ci_hi, coverage, clears_bar, folds, seconds`. `feature` IS the source column, `phase` the conditioning | CONFIRMED |
| n hypotheses with a p-value | 576 rows; **564 SCREENED with a `dm_p_raw`**, 12 `UNSCORED` (the six `lead_changes\|dprior*` and the six `pace_ratio_p1\|*@p1`) | CONFIRMED (564) |
| no module combines in-game hypotheses with nested selection | `grep -niE "top_k\|select" scripts/platformkit/eval_gate/s1*.py` returns exactly **two** hits, both unrelated: `s108_features.py:75 frame.select_dtypes(include="number")` and `s112_rescore_vs_close.py:146` a literal SQL `"select h.family, ..."`. Widening to the foundry: `family_combo_screen.py` (S79) IS a top-k combiner but its picks come from the STORED screen improvement of a PREGAME family and are scored on the same screen partition -- its own memo calls that "an in-sample ceiling, not a verdict" -- and it never touches a `live_tick` hypothesis. `eval_gate/stacker.py` stacks OOF gap ARMS, not family members | CONFIRMED |

Premise HOLDS -- proceed. (Not FALSIFIED: no module performs nested selection over in-game
hypotheses.)

## 1. What was built

`scripts/platformkit/eval_gate/s114_ingame_ensemble.py`. Reused verbatim, not re-derived:
`ingame_screen._fit` (the two arms of every screen), `ingame_screen.BAR`,
`ingame_screen_nba.load_screen / causal_source / _dm_fast / _icc`,
`ingame_grammar_nba.build_grid / enumerate_hypotheses / conditioned`,
`screen_predictor._logistic / _logit / RIDGE`, `combo.fwer_budget.bh_within_family`,
`eval_gate.tick_informative.attach_informative_summary`. **No file outside this lane was
edited** -- `foundry/` (S113's tree) is imported, never written.

**The nesting, per OUTER fold:**

1. The outer TRAIN window is everything the S82 purge admits: a train game's LAST tick must
   precede the fold's first tick by at least 1 day (`train.ts.max() < test.ts.min()` and
   game-disjointness both asserted per fold, and re-asserted independently by the per-file
   test on a synthetic corpus).
2. That train window is split AGAIN by game-first date at 70 pct of its ticks, with the same
   settlement purge between the two inner sides. Whole games on both sides.
3. Every one of the 576 frozen hypotheses is screened on that inner split ONLY -- fit on the
   inner train, scored on the inner test, game-clustered DM p. Within-family BH at q = 0.05
   is computed over that fold's p-values and archived; BH is monotone in p so it changes the
   reported discovery COUNT, never the rank order.
4. Top-k by **DISTINCT SOURCE COLUMN** (`Hypothesis.feature`), best-p first, positive
   improvement only -- S79's pick rule, because a family's top-5 is otherwise one column at
   four `ew` halflives.
5. ONE L2 logistic (ridge = `screen_predictor.RIDGE`) is fit on the FULL outer train window
   over `[1, z(x_1..x_k)]` with **`logit(market)` as an OFFSET whose coefficient is FIXED at
   1**, and it scores the held-out fold. Missing != bad: a test tick with any selected
   feature NaN falls back to the recalibration null (S82's rule), and coverage is archived.

The outer test rows are never seen by steps 1-4. The per-file test asserts this directly
(`test_selection_rows_are_disjoint_from_and_earlier_than_the_scored_rows`): for every scored
fold, both inner sides are game-disjoint from the fold AND end strictly before it starts.

**Feature build is computed once over the whole corpus, and that is not a leak.** Every base
column is backward-only, and S102's own guard `ingame_screen.assert_tick_asof` was re-run on
the pod against `ingame_grammar_nba.build_grid` before this sweep: PASS at the 8 evenly
spaced probe rows **25,883 / 51,766 / 77,649 / 103,532 / 129,415 / 155,298 / 181,181 /
207,064** of 232,951 (A3, never a head slice). A tick's value therefore does not depend on
any later tick, so "built on the whole corpus" and "built on the train window" agree on every
train row by construction.

**Arms.** Raw in-play market line; the S94 global recalibration `[1, logit(market)]` fit on
the identical outer train rows (null 1); k=1 chosen by the identical nested rule (null 2);
k = 3, 5, 10.

## 2. Corpus and folds

`data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv`, the S86 SCREEN side -- 232,951
ticks / 797 games. Scored denominator after the walk-forward: **192,635 ticks / 673 games**,
identical to S102's, which is the cross-check that the fold layout was inherited and not
re-tuned.

| fold | embargo cut | test ticks | train ticks / games | inner train / inner test | screened | UNSCORED | BH discoveries on TRAIN | s |
|---|---|---|---|---|---|---|---|---|
| F1 | 2024-12-09T00:43:02Z | 38,179 | 38,966 / 119 | 26,544 / 11,614 | 558 | 18 | **0** | 9.7 |
| F2 | 2025-01-27T00:11:04Z | 38,838 | 78,495 / 262 | 54,527 / 23,019 | 564 | 12 | **0** | 17.3 |
| F3 | 2025-11-04T00:43:06Z | 38,628 | 116,246 / 381 | 80,925 / 33,851 | 564 | 12 | **0** | 25.4 |
| F4 | 2026-01-02T00:12:09Z | 38,280 | 155,961 / 522 | 108,507 / 46,654 | 564 | 12 | 7 | 32.2 |
| F5 | 2026-02-26T00:42:27Z | 38,710 | 193,353 / 654 | 134,668 / 57,105 | 564 | 12 | 22 | 39.4 |

2,814 inner screens in 124.0 s of fold work. The 12 UNSCORED are the SAME twelve S102 named
(`lead_changes|dprior` x6, `pace_ratio_p1|*@p1` x6); F1 adds the six `dmargin_k20|*@p1` whose
inner train has too few distinct values to fit -- reported per fold, never imputed.

**On three of five folds, not one hypothesis survives FDR on the train window.** The
selection in F1-F3 is therefore ranking noise, and that is the honest description of what a
nested selector has to work with here.

## 3. The per-k table (192,635 ticks / 673 games, 5 folds)

Pooled reference Briers: **raw market 0.078611**, S94 recalibration null **0.078969**
(i.e. recalibrating the line COSTS +0.000359 -- S94/S102 reproduced), S86 as-of model
0.084083.

| k | Brier | vs raw market | DM 95 pct CI | p | vs recal null | vs k=1 | CI (vs k=1) | n_eff | clears +0.004 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.079094 | **-0.000484** | [-0.001047, +0.000080] | 0.092 | -0.000125 | (self) | - | 1,997 | no |
| 3 | 0.079020 | -0.000410 | [-0.000944, +0.000125] | 0.133 | -0.000051 | +0.000074 | [-0.000006, +0.000154] | 2,260 | no |
| **5** | **0.079011** | **-0.000400** | [-0.000934, +0.000133] | 0.141 | -0.000042 | **+0.000083** | **[+0.000003, +0.000163]** | 2,369 | no |
| 10 | 0.079018 | -0.000407 | [-0.000975, +0.000161] | 0.160 | -0.000048 | +0.000077 | [-0.000016, +0.000169] | 2,243 | no |

- **Clearing the +0.004 bar with a CI excluding zero and beating both nulls: 0 of 4.** No
  prereg DRAFT (`any_prereg_draft: false` in the artifact).
- Every arm is behind the raw line AND behind the recalibration null. The nested ensemble
  does not recover the gap the recalibration itself opens.
- Game clustering is the reason the CIs are wide: ICC 0.28-0.33, so 192,635 ticks are worth
  about 2,000-2,400 independent observations.
- `n_informative` (S87) = **78,761 of 192,635** (40.9 pct) over 673 informative game clusters,
  `n_eff_icc` 1,233.5; the informative-only re-quote of the best arm is the same side of zero,
  -0.000838 with CI `[-0.001968, +0.000292]`, p 0.146. The headline CI is unchanged (S87 adds
  a second CI, it never replaces one).

### Per fold, improvement vs the raw market

| fold | k=1 | k=3 | k=5 | k=10 |
|---|---|---|---|---|
| F1 | -0.002130 | -0.002006 | -0.002030 | -0.002181 |
| F2 | -0.000010 | +0.000091 | +0.000091 | +0.000091 |
| F3 | -0.000457 | -0.000438 | -0.000419 | -0.000351 |
| F4 | +0.000118 | +0.000220 | +0.000251 | +0.000308 |
| F5 | +0.000044 | +0.000069 | +0.000088 | +0.000081 |

F1 -- the fold whose selection was made on 119 train games with ZERO FDR discoveries -- is
20x worse than any other fold and carries the pooled result. The three folds with the most
training data are all mildly positive and all two orders of magnitude below the bar.

## 4. Selection stability, and what actually gets picked

Jaccard between the sets selected on CONSECUTIVE folds:

| k | F1-F2 | F2-F3 | F3-F4 | F4-F5 | mean |
|---|---|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 | 0.000 | **0.000** |
| 3 | 0.200 | 0.000 | 0.200 | 0.500 | 0.225 |
| 5 | 0.111 | 0.111 | 0.429 | 0.429 | 0.270 |
| 10 | 0.053 | 0.111 | 0.429 | 1.000 | 0.398 |

**The single best hypothesis is a different one in every fold** (`run_len_signed|dprior` ->
`dmargin_k3|dprior@p3` -> `margin|dprior` -> `run_len_signed|dprior` -> `margin|dprior`), so
every consecutive pair is disjoint and k=1's stability is exactly 0. Stability rises
monotonically with k, which is the mechanical reason k>1 also scores better: a larger, more
diverse set is less sensitive to which noise term happened to rank first.

28 distinct labels are ever selected across all k and all folds; **20 of the 28 are
`|dprior` forms** (the change against the previous tick). The nested ranking prefers the
first difference of state, not the level.

**Only 1 of S102's top 10 is ever selected** (`tdm_h600|dprior`, and only at k=10 in F3).
S102's own best form, `margin_over_sqrt_rem|raw`, is never picked by any fold at any k.

## 5. PBO over k

CSCV (Bailey et al.) on the per-fold improvement-vs-market matrix, configs {1, 3, 5, 10}:
**PBO = 0.80** over 10 splits, median logit -0.405. Five folds do not split evenly, so each
2-fold in-sample subset is paired with its 3-fold complement -- an asymmetric split, stated
in the module docstring and here rather than hidden.

Read plainly: in 8 of 10 splits the k that looked best on the in-sample folds landed BELOW
the median on the held-out folds. Choosing k on this evidence would itself be overfitting,
which is why the memo reports all four and promotes none.

## 6. Deploy parity and timing (pod)

Deployed with `git -c core.autocrlf=false archive <staged tree> -- <paths> | ssh pod 'tar -x
--no-same-owner -C /workspace/nba-ai-system'`, then md5-verified per file.

| file | local | pod | parity |
|---|---|---|---|
| `scripts/platformkit/eval_gate/s114_ingame_ensemble.py` | `ccc55809ffc4f356e8bb2665ef736ba2` | same | MATCH |
| `tests/platformkit/ingame/test_s114_ingame_ensemble.py` | `2f195f932accec107135b923a7d943fb` | same | MATCH |
| `scripts/platformkit/eval_gate/tick_informative.py` (was ABSENT on the pod) | `d14c6853c99f9cd001551e2e2b2fc64d` | same | MATCH |

Seven further dependencies were verified already at parity and **not** re-shipped:
`foundry/{ingame_screen, ingame_screen_nba, ingame_grammar_nba, screen_predictor, grammar,
tiers}.py`, `eval_gate/dm_test.py`, `combo/fwer_budget.py`. One honest exception:
`scripts/platformkit/ingame/gap_effective_n.py` has a DIFFERENT md5 on the pod
(`a2e6815298adec75529a4923aa461c2a` vs HEAD `a06f1fe10d5dd45527cc4fdbe8c7ec55`) but is
byte-identical after stripping CR -- a CRLF artifact of an older deploy. It was deliberately
NOT overwritten, because other lanes' processes import it and Python is indifferent to the
line ending. The corpus CSV was already on the pod at md5 parity (S102, `9d01e63f...`).

Pod validation before the sweep: `FOUNDRY_PORTABLE_CORPUS=1 python -m pytest
tests/platformkit/ingame/test_s114_ingame_ensemble.py -q` = **7 passed in 4.34 s** on the
pod's own Python (pandas 3.0.5 / numpy 2.1.2 / statsmodels 0.15.0), a different pandas major
than local 2.x. Then the as-of guard (section 1). Launch, exactly as run:

```
cd /workspace/nba-ai-system && FOUNDRY_PORTABLE_CORPUS=1 setsid nohup /usr/local/bin/python -u \
  -m scripts.platformkit.eval_gate.s114_ingame_ensemble > /workspace/s114_ensemble.log 2>&1 &
```

Timing: 124.0 s of fold work (2,814 inner screens + 20 ensemble fits + 5 null fits),
9.7 s on F1 rising to 39.4 s on F5 as the train window grows. The job ran as its own `setsid`
leader and exited on its own; artifacts stamped 01:13 on the pod.

**Pod health.** Protected pids 19236 (supervisor), 4035 (track daemon), 21620 / 21622 (mlb
capture) and 360964 (inplay capture): **all ALIVE** after the run. The foundry runner is
supervisor-managed and cycles pids -- the pid named in this lane's brief (536874) is gone and
the runner is alive under **547973, started 01:18:40**, i.e. AFTER this sweep exited at 01:13;
this lane issued no kill and no signal to any process. `backtest_fwer.jsonl` absent on the
pod before and after. No git on the pod.

## 7. Reproduction (A2) and the Q9 differential

- The three artifacts were copied back unchanged (md5 identical on pod and locally, listed at
  the top of this memo).
- **Every headline recomputed from `s114_ingame_ensemble_series.csv` ALONE, on a different
  machine and a different pandas major, using the REFERENCE `dm_test.diebold_mariano` rather
  than the vectorised `_dm_fast` that produced the artifact**: all four Briers, all 11
  improvement/CI/p triples reproduce with **max absolute delta 1.30e-18** across every
  comparison. `_dm_fast` is therefore not load-bearing for anything in section 3.
- **Q9 differential.** `..._series.csv` -- 192,635 rows, one per scored tick, columns
  `game, ts, y, market, model, informative, fold, p_null, p_k1, p_k3, p_k5, p_k10`, no
  duplicate `(game, ts)`, cluster id = `game`. Every CI above recomputes from it.
  `..._screens.csv` -- 2,814 rows (`fold, label, source, improvement, p_raw, bh_adj_p`) is
  the complete per-fold ranking the selector saw, so the selected sets are reconstructible
  without re-fitting. The JSON's `fits` block stores each fold's per-k coefficients, `mu`,
  `sd`, `n_fit` and test coverage, and `folds` stores each fold's embargo cut and sizes.

## 8. Rails self-check (VERIFIER_CONTRACT B + Q)

- **B1** no circular metric -- nothing is excluded after scoring; the two exclusion sets (the
  UNSCORED hypotheses per fold, named with counts and cause in section 2, and the F0 seed
  block that is train-only for every arm) are named.
- **B2** additive -- one new module, one new test, three new artifacts; nothing renamed,
  removed or edited. `foundry/` is imported and unwritten (S113 owns it); S115's and S116's
  files were not opened.
- **B3** no fall-through loss -- a tick with any selected feature missing falls back to the
  null on BOTH arms and stays in the denominator; coverage is archived per fold.
- **B5** no pre-verification deploy -- the pod received only the two new files (plus a
  missing dependency at HEAD parity), and ran the per-file test and the as-of guard before
  the sweep.
- **B6** no orphans -- nothing moved or retired.
- **B7** no head slice -- every tick of every scored fold is scored; the as-of probes are 8
  EVENLY spaced rows spanning 11 pct to 89 pct of the corpus.
- **B8** no self-fit -- selection, standardisation and both fits happen on rows strictly
  earlier than, and game-disjoint from, the rows scored; asserted per fold and by the test.
- **B9** denominator -- reported three ways (192,635 ticks, 78,761 informative, game-clustered
  n_eff 1,997-2,369), and per fold.
- **B10 / Q3** no bar moved -- `BAR` is imported, never assigned in this module (the test
  asserts `"\nBAR = "` does not appear in the source and that `s114.BAR == 0.004`);
  `q_within_family` 0.05 unchanged; `K_VALUES` and `INNER_FRAC` are new knobs of a new
  module, not thresholds of an existing one.
- **Q1 / Q2** nothing is charged, so no prereg is sealed and no K is read. The per-file test
  asserts the module body contains none of `_charge_ledger / backtest_runner /
  backtest_fwer / prereg_sha256 / charge_tier / data/registry`.
- **Q4** leak contract -- tick-time as-of by truncation invariance (8 probes, the S102 guard
  unedited), game-first-date blocks, settlement purge, 1-day embargo, `train.ts.max() <
  test.ts.min()` asserted per fold, and the SELECTION nested inside the same walk-forward.
- **Q5** one corpus, one sport -> **SINGLE-WINDOW**, stated here and in the register row. No
  AHEAD is claimed, so `min_corpora_eff` is not engaged.
- **Q6** calibration language only; no dollar, ROI, profit or edge claim; no retracted figure.
- **Q7** every scored metric has n >= 30 (smallest denominator 192,635 ticks / 673 clusters);
  the 576 enumeration is S102's frozen CONSTRUCT and is unchanged.
- **Q8** premise re-measured first and CONFIRMED (section 0).
- **Q9** per-tick paired-loss series archived for every arm, plus the complete per-fold
  ranking and per-fold fit state (section 7).

## NOT VERIFIED

- **This is the lane's own report. No verifier has re-run it.**
- **SINGLE-WINDOW (Q5).** One sport, one corpus, one venue, 673 game clusters over 5 folds.
  There is no second corpus and none is claimed.
- **The VERDICT side (796 games) was never read.** Nothing here may be promoted without it.
- **F1 dominates the pooled number.** Its -0.002130 is 20x the next-worst fold and comes from
  a selection made on 119 train games with zero FDR discoveries. A different first fold would
  move the headline; the per-fold table is published so that is visible, but the pooled CI is
  not a robust estimate of a 5-fold-average effect.
- **The +0.0000830 k=5-over-k=1 CI excludes zero at n_eff 2,369 and p 0.0429.** It is ONE
  comparison on ONE corpus at a magnitude 48x below the bar; it is reported because the row
  asked whether combining helps, not as a finding. It has had no multiplicity correction of
  its own across the four k values.
- **The inner split is a single 70/30 cut, not an inner walk-forward.** A hypothesis whose
  value is concentrated in the earliest part of a train window is under-ranked by it.
- **The ensemble arm cannot rescale the line.** `logit(market)` enters with coefficient fixed
  at 1 (the row's specification), while the recalibration null fits both intercept and slope.
  The two nulls therefore differ in more than the feature term, and "behind the recal null"
  mixes the feature's contribution with the loss of the fitted slope. Only the k-vs-k
  comparisons hold everything but the feature set constant.
- **The as-of model column is inherited from S86**, not re-derived; S86's own NOT VERIFIED
  list carries over. S102's carries over too for the grammar and the fold layout.
- **PBO is computed on 5 folds with an asymmetric 2/3 split** and 4 configs. With 10 splits
  the estimate 0.80 has a coarse resolution (multiples of 0.1).
- **`gap_effective_n.py` on the pod is CRLF, not LF.** Content-identical, but it is a drift
  this lane chose to leave rather than clobber a file other running lanes import.
- No charge, no seal, no ledger row, no push. A SCREEN_NULL is an honest result.
