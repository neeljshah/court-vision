# S102 -- the NBA in-game hypothesis sweep, run on the pod

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S102. The 465,249-tick NBA corpus carries
only score / period / clock / margin / market per tick, so the S82 in-game screen tier had
never run on it and every NBA in-game arm so far was ONE hand-picked form.

Verdict: **SCREEN_NULL -- 0 of 564 scored hypotheses clear the +0.004 bar.** The largest
improvement over the recalibration null is **+0.000248**, sixteen times below the bar, and
its own game-clustered CI spans zero. Within-family BH at q=0.05 makes 29 discoveries, all
of them at effect sizes between +0.000001 and +0.000139 -- i.e. FDR control detects
that a handful of these terms are not exactly zero, at magnitudes 29x to 4,000x below the
bar the row set. **Nothing is AHEAD.** Uncharged: no prereg seal, no ledger read, no ledger
write, no K consumed; `backtest_fwer.jsonl` does not exist on the pod and is unchanged
locally. **SINGLE-WINDOW** (one corpus, the S86 SCREEN side, NBA 2024-10-22..2026-06-10).
The 796-game VERDICT side was never read.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked in
section 7). Calibration measurement only -- no dollar, ROI, profit or edge language, and
no retracted figure appears. **No bar moved** (`BAR = 0.004`, byte-identical to S82).
ASCII only.

Modules: `scripts/platformkit/foundry/ingame_grammar_nba.py` (253 LOC),
`scripts/platformkit/foundry/ingame_screen_nba.py` (278 LOC),
`scripts/platformkit/foundry/run_ingame_screen.py` (148 LOC, the CLI, `--sport nba`).
Tests: `python -m pytest tests/platformkit/foundry/test_ingame_grammar_nba.py -q` = **5 passed**;
`python -m pytest tests/platformkit/foundry/test_ingame_screen_nba.py -q` = **5 passed**;
`python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q` = **13 passed**
(12 before, +1 new); regressions re-run in master:
`tests/platformkit/foundry/test_ingame_screen.py -q` = **6 passed** (S82 untouched).
Artifacts: `data/cache/eval_gate/s102_nba_sweep.sqlite` (2,363,392 bytes, md5
`11bda9c0182e1a1db10c869c79dac241`, identical on pod and locally),
`..._report.json`, `..._top10_series.parquet` (1,926,350 rows), `..._sweep.log` (580 lines).

---

## 0. STEP 0 -- premise re-measured first (Q8), CONFIRMED

| the row says | measured 2026-09-03 | verdict |
|---|---|---|
| the S82 tier has never run on the NBA corpus | `run_ingame_screen.main` hard-wired `arms.load_corpus(..., "mlb")`; the tier's own report stamps `"sport": "mlb"`; the only artifacts on disk are `s82_ingame_screen_2026-09-03.json` / `..._series_...csv`; a scoped grep for `ingame_screen` over `scripts/`, `tests/`, `docs/evidence/` returns the module, its CLI, its one test and two S87b mentions, and nothing NBA | CONFIRMED |
| the NBA tick corpus carries only score / period / clock / margin / market | `data/cache/inplay_odds/nba_checkpoints_full.parquet` (465,249 x 13): `game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue`. No possessions, no lineups, no foul or free-throw state, no pregame total | CONFIRMED |
| the frozen family partition is at 39 families | `load_families()` -> `spec_version s89-families-v2`, pin `9d6cb98c43c74d04b7f995fe380e33705ffb7c0b`, **39 families / 407 features / 3575 hypotheses** (37 grids + 2 arms); the four NBA `live_tick` families are `ingame_arms_nba`, `nba_pbp_foul_states`, `nba_pbp_states`, `nba_possession_states` -- none of them a derived-state grid over these ticks | CONFIRMED |

Premise HOLDS -- proceed.

## 1. The frozen grammar (committed BEFORE any screen was run)

`scripts/platformkit/foundry/ingame_grammar_nba.py`. **16 base columns x 6 transforms x
6 conditionings = 576 hypotheses**, enumerated as `foundry.grammar.Hypothesis` values and
**deduped by `grammar.semantic_hash`**: 576 enumerated, 576 distinct hashes, 576 distinct
labels (asserted by the per-file test, so the grammar cannot silently double-count a form).

| group | base columns |
|---|---|
| raw state anchors | `margin`, `rem` (minutes remaining) |
| margin trajectory over k ticks | `dmargin_k3`, `dmargin_k5`, `dmargin_k10`, `dmargin_k20` |
| run length | `run_len_signed` (consecutive ticks of same-sign margin change, signed) |
| lead changes so far | `lead_changes`, `lead_change_rate` (per elapsed minute) |
| scoring pace | `pace_total` (points so far / elapsed), `pace_ratio_p1` (that pace over the game's OWN period-1 final pace) |
| time-decayed margin | `tdm_h60`, `tdm_h180`, `tdm_h600` (halflife in SECONDS, decayed on the real tick gap) |
| margin x time-remaining | `margin_x_rem`, `margin_over_sqrt_rem` |

- **transforms (6)**: `raw`, `ew(halflife = 3, 5, 10, 20 ticks)`, `delta_vs_prior`. These are
  the tick-grain subset of the frozen 9-transform alphabet. The other three
  (`rank_in_league`, `z_vs_league`, `ratio_to_opponent`) need league or opponent tables that
  do not exist at tick grain and are **NOT_ENUMERATED**, named in the module rather than
  quietly dropped.
- **conditionings (6)**: unconditional, and `phase=1..5` (5 = any overtime period). A
  conditioned hypothesis is the column masked to that phase; the tier's own "missing != bad"
  rule falls a masked tick back to the null on BOTH arms, so the denominator never moves.
- **NOT_SUPPLIED by this corpus**, named and never proxied: the pregame total (so "pace vs
  the pregame implied pace" is unavailable -- the game's own period-1 pace is used as the
  reference instead, and that substitution is stated here, not hidden), possessions,
  lineups, foul state, free-throw state, and any event grain below the poller's tick.

**Tick-time as-of, enforced not asserted.** `ingame_screen.assert_tick_asof` (S82's own
guard, unedited) rebuilds the whole 96-column grid from the causal prefix `src[:k+1]` and
requires row `k` to be unchanged. On the real corpus it passed at **8 EVENLY spaced probes**
(A3, never a head slice): rows **25,883 / 51,766 / 77,649 / 103,532 / 129,415 / 155,298 /
181,181 / 207,064** of 232,951. The per-file test plants a next-tick read
(`groupby(game).shift(-1)`) into the builder and asserts the guard RAISES `TickTimeLeak`.

## 2. The family, and the pin that moved once (S89's procedure)

`ingame_nba_tickgrid` is frozen in `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md`
**before** the sweep was launched, with a third `kind:` value, `tickgrid`, because its
members are BASE columns of a derived grammar rather than stored columns of a parquet, so
the 9-transform pregame rule does not apply and its closed construction rule lives in its
own block.

| | before (S89) | after (S102) |
|---|---|---|
| `spec_version` | `s89-families-v2` | `s102-families-v3` |
| `git hash-object` pin | `9d6cb98c43c74d04b7f995fe380e33705ffb7c0b` | `6e7878ae5978150246cef4c706b5a05ef5275591` |
| families | 39 (37 grid + 2 arm) | **40** (37 grid + 2 arm + 1 tickgrid) |
| features | 407 | 423 |
| hypotheses | 3575 | 4151 |

**No bar moved (Q3/B10).** `q_within_family` is still 0.05, `alpha_global` still 0.05,
`deflated_p` / `eps_eff` / `min_corpora_eff` / cumulative K untouched, every trial's
`BAR = 0.004` untouched, and nothing was removed. The pin CHANGING is the tamper-evidence
mechanism working: a verdict stamped `s89-families-v2` @ `9d6cb98c4` remains self-evidently
priced against the old partition. Condition (iii) still holds -- `dual_bar_verdict` takes
p-values as arguments and opens no ledger and no stored verdict, so no past verdict is
re-scored.

**A5 reader sweep for `Family.kind`.** The only reader outside `family_bars` itself is
`foundry/seed_queue.frozen_hypotheses`, whose guard is already intrinsic (`if family.kind
!= "grid": continue`), so a `tickgrid` family is skipped by construction. Measured after
the amendment: `sum(1 for _ in frozen_hypotheses()) == 3564`, unchanged.

`scripts/platformkit/eval_gate/test_family_bars.py` updated: the S14/S89 count test now
asserts 40 families / 423 features / 4151 hypotheses with the old pins recorded in its
docstring, plus a NEW test that the spec block and `ingame_grammar_nba.enumerate_hypotheses`
cannot drift apart (`members == BASE`, `features == 16`, `hypotheses == 576`).

## 3. The tier on the NBA corpus

**Reused from S82, verbatim and unedited**: `assert_tick_asof`, `walk_forward_feature` (the
purged, embargoed, game-disjoint walk-forward and its two fits) and `BAR = 0.004`. Nothing
in `foundry/ingame_screen.py` changed, and its own test still passes (6 passed), so the
published MLB screen is untouched (B2/B10).

**Corpus.** `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` -- the S86 SCREEN side,
**232,951 ticks / 797 games**, the side `foundry.tiers.partition_corpus(seed=0)` assigned to
SCREEN on game blocks (`screen_sha256 f105c609...`). Independent reproduction of S86 from
this loader: pooled market Brier **0.077065** and pooled as-of model Brier **0.081922**,
both matching the S86 memo to six decimals (A2). The VERDICT side is never opened by this
lane. `n_informative` over the corpus is **82,248** (35.31 pct), reproducing S86 exactly.

**Anchor and null.** The NBA corpus has no `e4`-style blend, so the incumbent is the IN-PLAY
MARKET LINE itself and the null arm is **S94's global recalibration `[1, logit(market)]`**,
fit walk-forward on exactly the candidate's rows. The candidate is
`sigmoid(a + b*logit(market) + c*z(x))`. The bar is applied to `improvement_vs_null`, so the
two arms differ ONLY by the feature term (the tier's `p_e4` column holds the market
probability, which is why `brier_e4 == brier_market` by construction here).

**Folds.** NBA has ~500 distinct game dates and one fold per date would refit 576 x 500
times, so folds are **6 contiguous blocks of game-FIRST dates** of roughly equal tick count
(F0 is the train-only seed). Every game sits in exactly one block (asserted). The S82 purge
is inherited unchanged: a train game must have produced its LAST tick at least **1 day**
before the fold's first tick, and `train.ts.max() < test.ts.min()` is asserted per fold.

| fold | dates | test ticks | train ticks | train games | embargo cut | feature coverage |
|---|---|---|---|---|---|---|
| F0 | 2024-10-22..2024-12-08 | (train-only seed, 40,316) | - | - | - | - |
| F1 | 2024-12-09..2025-01-25 | 38,179 | 38,966 | 119 | 2024-12-09T00:43:02Z | 1.0000 |
| F2 | 2025-01-27..2025-11-04 | 38,838 | 78,495 | 262 | 2025-01-27T00:11:04Z | 1.0000 |
| F3 | 2025-11-05..2025-12-26 | 38,628 | 116,246 | 381 | 2025-11-04T00:43:06Z | 1.0000 |
| F4 | 2026-01-02..2026-02-25 | 38,280 | 155,961 | 522 | 2026-01-02T00:12:09Z | 1.0000 |
| F5 | 2026-02-26..2026-06-10 | 38,710 | 193,353 | 654 | 2026-02-26T00:42:27Z | 1.0000 |

Scored denominator per hypothesis: **n = 192,635 ticks / 673 games / 68,925 informative**
(the six `dmargin_k20|*@p1` rows score 154,456 / 535 / 54,744 because their F1 train slice
has too few distinct values to fit and F1 is honestly recorded `UNFITTABLE`, not imputed).
`n_eff` (game-clustered ICC ESS of the paired-loss series): min **2,209.7**, median
**11,908.0**, max 192,635.

**DM.** 576 hypotheses x 233k ticks through `dm_test.diebold_mariano`'s per-cluster python
loop does not finish, so `_dm_fast` restates the SAME arithmetic with `np.bincount`
(cluster-sum variance, `G/(G-1)` correction, Student-t with `G-1` df for both the p-value
and the interval). The per-file test asserts the two agree to **1e-12** on real rows at two
effect scales, and that `score_fast` reproduces S82's own `score_feature` to 1e-12 on a real
150-game slice.

## 4. Deploy parity (pod)

Deployed with `git -c core.autocrlf=false archive HEAD -- <paths> | ssh pod 'tar -x
--no-same-owner -C /workspace/nba-ai-system'` from commit `0614b78c3`, then md5-verified per
file (local `git show HEAD:<f> | md5sum` vs pod `md5sum`).

| file | parity |
|---|---|
| `scripts/platformkit/foundry/ingame_screen.py` | MATCH |
| `scripts/platformkit/foundry/ingame_screen_nba.py` | MATCH |
| `scripts/platformkit/foundry/ingame_grammar_nba.py` | MATCH |
| `scripts/platformkit/foundry/run_ingame_screen.py` | MATCH |
| `scripts/platformkit/foundry/screen_predictor.py` | MATCH |
| `scripts/platformkit/foundry/tiers.py` | MATCH |
| `scripts/platformkit/foundry/grammar.py` | MATCH |
| `scripts/platformkit/eval_gate/dm_test.py` | MATCH |
| `scripts/platformkit/mlb_state_features.py` | MATCH |
| `tests/platformkit/foundry/test_ingame_grammar_nba.py` | MATCH |
| `tests/platformkit/foundry/test_ingame_screen_nba.py` | MATCH |
| `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` (corpus, shipped by tar) | MATCH, md5 `9d01e63f21dc0c304200ca942c86c7d0` |

11 of 11 code files at md5 parity, corpus at md5 parity. `nba_checkpoints_full.parquet` and
`games.parquet` were **not** shipped: the loader reads only the S86 archive, which already
carries the as-of model column, the phase buckets and the outcome, so shipping the raw
parquet would have added no input the run reads.

Pod validation before the sweep:
`FOUNDRY_PORTABLE_CORPUS=1 python -m pytest tests/platformkit/foundry/test_ingame_grammar_nba.py
tests/platformkit/foundry/test_ingame_screen_nba.py -q` = **10 passed in 9.97s** on the pod's
own Python (pandas 3.0.5 / numpy 2.1.2 / statsmodels 0.15.0), which is a different pandas
major than the local 2.x -- the tier is not silently pandas-2-only.

Launch, exactly as run:

```
cd /workspace/nba-ai-system && FOUNDRY_PORTABLE_CORPUS=1 setsid nohup /usr/local/bin/python -u \
  -m scripts.platformkit.foundry.run_ingame_screen --sport nba --grammar nba \
  --sqlite data/cache/eval_gate/s102_nba_sweep.sqlite > /workspace/s102_nba_sweep.log 2>&1 &
```

## 5. The sweep

**576 hypotheses in 634.8 s wall = 3,266.7 screens/hour** (mean 1.07 s, median 0.93 s,
max 1.96 s per screen), one committed sqlite row each so a killed job is readable and
restartable. **564 SCREENED, 12 UNSCORED**, every one named:

- `lead_changes|dprior` and its five phase variants (6): the first difference of a
  cumulative counter takes only the values 0 and 1, below the tier's 3-distinct-value fit
  floor, so every fold is `UNFITTABLE`. Reported, not imputed.
- `pace_ratio_p1|{raw,ew3,ew5,ew10,ew20,dprior}@p1` (6): `pace_ratio_p1` is NaN throughout
  period 1 by construction (there is no earlier period-1 pace to divide by), so conditioning
  it on phase 1 leaves nothing to fit. Reported, not imputed.

Scored split: 95 unconditional, 469 phase-conditioned (89 at phase 1, 95 at each of 2-5).

### The best 10 (SCREEN side, n = 192,635 ticks / 673 games unless noted)

`brier null` is the walk-forward recalibration `[1, logit(market)]` fit on the same rows;
`improvement` is against THAT, never against the raw line; the CI is the game-clustered
Diebold-Mariano 95 pct; `bh_adj_p` is within-family BH over all 564 screen p-values.

| rank | hypothesis | n_eff | brier null | brier candidate | improvement vs null | DM 95 pct CI | p raw | BH adj p |
|---|---|---|---|---|---|---|---|---|
| 1 | `margin_over_sqrt_rem\|raw` | 2,295.6 | 0.078969 | 0.078722 | **+0.000248** | [-0.000664, +0.001160] | 0.594 | 0.781 |
| 2 | `pace_total\|ew20` | 3,425.5 | 0.078969 | 0.078789 | +0.000181 | [-0.000065, +0.000426] | 0.149 | 0.662 |
| 3 | `margin_over_sqrt_rem\|raw@p4` | 7,512.2 | 0.079226 | 0.079052 | +0.000174 | [-0.000006, +0.000354] | 0.058 | 0.388 |
| 4 | `pace_total\|ew10` | 3,753.3 | 0.078969 | 0.078801 | +0.000168 | [-0.000064, +0.000401] | 0.156 | 0.689 |
| 5 | `pace_total\|ew5` | 3,986.0 | 0.078969 | 0.078814 | +0.000155 | [-0.000072, +0.000381] | 0.180 | 0.721 |
| 6 | `pace_total\|ew3` | 4,067.4 | 0.078969 | 0.078821 | +0.000148 | [-0.000078, +0.000374] | 0.198 | 0.748 |
| 7 | `pace_total\|raw` | 4,073.8 | 0.078969 | 0.078825 | +0.000144 | [-0.000084, +0.000373] | 0.216 | 0.748 |
| 8 | `tdm_h600\|dprior` | 26,658.3 | 0.078972 | 0.078832 | +0.000139 | [+0.000054, +0.000225] | 0.00143 | **0.031** |
| 9 | `margin_over_sqrt_rem\|raw@p3` | 6,626.8 | 0.079342 | 0.079209 | +0.000133 | [-0.000127, +0.000393] | 0.315 | 0.748 |
| 10 | `margin\|raw@p3` | 6,746.6 | 0.079342 | 0.079209 | +0.000133 | [-0.000114, +0.000379] | 0.292 | 0.748 |

**Bar: +0.004 (frozen, the S58/S82/S94 in-game bar; NOT moved -- B10/Q3). Clearing it:
0 of 564.** The best hypothesis in the whole 576-form grammar is **16.1x below** the bar.

### Within-family BH FDR (`combo/fwer_budget.bh_within_family`, q = 0.05)

- **29 discoveries** of 564, BH threshold p <= **0.002440**; 28 of the 29 have a positive
  improvement, one is negative.
- **Largest improvement among the discoveries: +0.000139** (`tdm_h600|dprior`), 29x below
  the bar. The smallest is +0.000001.
- **Surviving hypotheses that also clear the +0.004 improvement bar: 0.** That is the
  number the row asked for, and it is 0 as expected.
- Read honestly: with 192,635 ticks and 673 game clusters the instrument can resolve a
  Brier difference of ~1e-4, so FDR control is detecting that a few of these terms are not
  EXACTLY zero. A verdict needs BOTH bars plus the improvement bar, and the improvement bar
  is the one that decides here. Nothing is AHEAD.
- Priced read-only against the global bar as well (`deflated_p(raw_p, k_cumulative = 18)`,
  the ledger's current K read WITHOUT charging): the same 29 would pass the global bar. They
  still fail the improvement bar by one to three orders of magnitude, so this changes no
  verdict; it is recorded so nobody re-derives it and thinks a bar was skipped.

### Best per base column (the honest per-family-member view)

| base column | best form | improvement | DM CI95 | p raw |
|---|---|---|---|---|
| `margin_over_sqrt_rem` | `raw` | +0.000248 | [-0.000664, +0.001160] | 0.594 |
| `pace_total` | `ew20` | +0.000181 | [-0.000065, +0.000426] | 0.149 |
| `tdm_h600` | `dprior` | +0.000139 | [+0.000054, +0.000225] | 0.00143 |
| `margin` | `raw@p3` | +0.000133 | [-0.000114, +0.000379] | 0.292 |
| `tdm_h180` | `dprior` | +0.000121 | [+0.000071, +0.000172] | 3.23e-06 |
| `margin_x_rem` | `raw@p3` | +0.000113 | [-0.000074, +0.000299] | 0.236 |
| `tdm_h60` | `raw@p3` | +0.000110 | [-0.000124, +0.000343] | 0.357 |
| `dmargin_k5` | `raw` | +0.000080 | [+0.000045, +0.000114] | 6.69e-06 |
| `dmargin_k10` | `raw` | +0.000079 | [+0.000034, +0.000124] | 5.96e-04 |
| `dmargin_k3` | `raw` | +0.000070 | [+0.000044, +0.000096] | 2.06e-07 |
| `dmargin_k20` | `raw` | +0.000066 | [+0.000006, +0.000125] | 0.030 |
| `run_len_signed` | `ew5@p4` | +0.000064 | [-0.000005, +0.000133] | 0.069 |
| `rem` | `ew20@p5` | +0.000039 | [-0.000038, +0.000115] | 0.321 |
| `lead_changes` | `raw@p5` | +0.000019 | [-0.000148, +0.000186] | 0.823 |
| `lead_change_rate` | `raw@p5` | +0.000016 | [-0.000160, +0.000193] | 0.855 |
| `pace_ratio_p1` | `dprior@p5` | +0.00000001 | [-0.000004, +0.000004] | 0.994 |

Every one of the 16 frozen base columns, in its own best form, is at least **16x below the
bar**. Margin trajectory (`dmargin_k*`) and time-decayed margin are the terms whose CI most
often excludes zero -- and they are also the smallest in magnitude, which is what a
well-priced in-play line looks like from the inside.

### One more thing the run measures, stated plainly

**A walk-forward global recalibration of the in-play line is itself WORSE than the raw
line** on these rows: null 0.078969 vs market 0.078611, i.e. the recalibration costs
+0.000359 in Brier. That is the S94 result reproduced on a different fold layout, and it is
the honest frame for the whole table: the candidates above are improving on an arm that is
already behind the line, and even so none of them recovers the gap, let alone clears the
bar. The line is efficient here; the honest description is "we match it and do not beat it".

## 6. Reproduction (A2) and the Q9 differential

- The pod DB was copied back unchanged: md5 `11bda9c0182e1a1db10c869c79dac241` on the pod
  and locally.
- The **top 10 were recomputed from scratch on a DIFFERENT machine and a different pandas
  major** (local Windows / pandas 2.x vs pod Linux / pandas 3.0.5): all 10 reproduce
  `improvement_vs_null`, `brier_candidate`, `brier_null`, `dm_p_raw` and both CI bounds,
  **max absolute delta 6.77e-14 across all 60 comparisons**, well inside 1e-12.
- **Q9 differential.** `data/cache/eval_gate/s102_nba_sweep_top10_series.parquet` --
  1,926,350 rows (10 hypotheses x 192,635 ticks) with `hypothesis, game, timestamp, y,
  market, model_asof, p_null, p_candidate, x, fold, loss_null, loss_candidate, d`, so every
  CI in the table above recomputes from the artifact alone. For all 576, the sqlite `folds`
  column stores each fold's train size, train-game count, embargo cut, coefficients
  (`coef`, `coef_null`), `mu`, `sd` and test coverage, so any hypothesis's candidate and
  null series is reconstructible from the artifact plus the frozen grammar without re-fitting.
  A full 576-hypothesis per-tick CSV would be ~111M rows / ~16 GB and was deliberately not
  written; the choice and its consequence are stated here rather than left implicit.

## 7. Rails self-check (VERIFIER_CONTRACT B + Q)

- **B1** no circular metric -- no row is excluded after scoring; the two exclusion sets (12
  UNSCORED hypotheses, and the F0 seed block that is train-only for every hypothesis) are
  named with their counts and their cause.
- **B2** additive -- two new modules, two new tests, one new family block, one new `kind`
  value with a default; nothing renamed or removed; `ingame_screen.py` is byte-unchanged.
- **B3** no fall-through loss -- a tick with a NaN feature falls back to the null on BOTH
  arms (S82's rule, unchanged); missing is not treated as bad.
- **B5** no pre-verification deploy of an unverified artifact: the pod received only files
  already committed at `0614b78c3`, and the pod ran the per-file tests before the sweep.
- **B6** no orphans -- `run_ingame_screen`'s MLB path is preserved behind the default
  `--sport mlb` and S82's test still passes.
- **B7** no head slice -- every tick of every scored fold is scored; the as-of probes are 8
  EVENLY spaced rows spanning 11 pct to 89 pct of the corpus.
- **B8** no self-fit -- null and candidate are fit on the same TRAIN rows and scored on
  strictly later, game-disjoint, purged, embargoed TEST rows.
- **B9** denominator -- reported three ways on every hypothesis (n ticks, n_informative,
  game-clustered n_eff); the six short hypotheses carry their own smaller denominator.
- **B10 / Q3** no bar moved -- `BAR = 0.004`, `q_within_family = 0.05`, `alpha_global =
  0.05` all byte-identical; the family spec grew, no threshold changed.
- **Q1 / Q2** nothing is charged, so no prereg is sealed and no K is read for a verdict.
  `data/cache/eval_gate/backtest_fwer.jsonl` **does not exist on the pod** (verified before
  and after the run) and is untouched locally at 18 rows; the modules import nothing from
  `backtest_runner` and the per-file test asserts the module body contains none of
  `_charge_ledger / backtest_runner / backtest_fwer / prereg_sha256 / PREREG / charge_tier`.
  The one place `k_cumulative = 18` appears is the READ-ONLY global-bar note in section 5.
- **Q4** leak contract -- tick-time as-of by truncation invariance (8 probes, plus a planted
  leak that raises), game-first-date blocks, settlement purge, 1-day embargo, and
  `train.ts.max() < test.ts.min()` asserted per fold.
- **Q5** one corpus, one sport -> labelled **SINGLE-WINDOW** here and in the register row.
  No AHEAD is claimed, so `min_corpora_eff` is not engaged.
- **Q6** calibration language only; no dollar, ROI, profit or edge claim; none of the
  retracted figures appears.
- **Q7** every scored metric has n >= 30 (the smallest denominator is 154,456 ticks / 535
  games); the 576 enumeration is a CONSTRUCT and is exhaustive by the closed grammar.
- **Q8** premise re-measured first and CONFIRMED (section 0).
- **Q9** per-unit paired-loss series archived for the reported rows; per-fold fit state
  archived for all 576 (section 6).

## 8. Pod health after the run

- Protected pids **19236 (supervisor), 4035 (track daemon), 21620 / 21622 (mlb capture),
  254284 (foundry runner)**: all five ALIVE before and after. The sweep ran as its own
  `setsid` leader (pid 328528) and exited on its own.
- `data/cache/eval_gate/backtest_fwer.jsonl` **absent on the pod**, before and after.
- `data/registry/` untouched. No flag flipped on. No `--force`. No push. No git on the pod.
- No edit to `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`, or to the S98 /
  S99 / S100 / S101 lane files.

## NOT VERIFIED

- **SINGLE-WINDOW (Q5).** One sport, one corpus, one venue (Polymarket), 673 game clusters
  over 5 scored fold blocks. There is no second corpus and none is claimed. The screen would
  not survive as an AHEAD even if something had cleared.
- **The VERDICT side (796 games) was never read.** Nothing here may be promoted without it.
- **One hypothesis form only**: a single additive logistic term in `z(x)` on top of
  `logit(market)`. Multi-feature combinations, non-linear bases, interactions between two
  grammar members, and regime conditioning finer than the 5 phases are untouched. A feature
  that matters only inside a narrow regime would read as null here.
- **The pregame total is NOT SUPPLIED**, so the row's "scoring pace vs the pregame total"
  could not be built; `pace_ratio_p1` (pace vs the game's own period-1 pace) is a
  SUBSTITUTE, not the same hypothesis, and it is the weakest column in the table.
- **12 of 576 hypotheses are UNSCORED** (named in section 5), so the honest denominator is
  564, not 576.
- **The as-of model column is inherited from S86**, not re-derived here; S86's own
  NOT VERIFIED list (OT pricing artifact, one venue, tick-weighted reliability bins,
  `margin` sign unused) carries over unchanged.
- **The six `dmargin_k20|*@p1` hypotheses score on 154,456 ticks, not 192,635**, because
  their F1 fold is `UNFITTABLE`. Their improvements are therefore measured on a different
  (smaller) row set than the other 558 and are not directly comparable to them.
- **`_dm_fast` is a restatement, not the reference implementation.** It is asserted equal to
  `dm_test.diebold_mariano` to 1e-12 on real rows at two effect scales, but the 576 screen
  p-values themselves were produced by the restatement; only the top 10 were re-derived, and
  those were re-derived with `_dm_fast` too. A verifier wanting the reference DM on all 576
  must re-run with `score_feature`, which is what the equality test exists to make unnecessary.
- **Fold blocks are not calendar-uniform.** Block F2 spans 2025-01-27..2025-11-04 because
  the corpus has an off-season gap; blocks are equal in TICKS, not in days.
- No charge, no seal, no ledger row, no push. A SCREEN_NULL is an honest result.
