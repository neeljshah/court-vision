# S58 in-game trial A prereg (sealed 2026-09-03) -- MLB market-anchor CLAMP family, config chosen INSIDE the folds

Sealed BEFORE any metric: this file is committed ALONE, its SHA-256 is pinned as
`PREREG_SHA256` in `scripts/platformkit/eval_gate/s58_clamp_family_trial.py`, verified by
`run_trial` before the ledger charge, and embedded in the trial JSON, the folds JSON and
the memo (Q1). The charge -- `_charge_ledger(data/cache/eval_gate/backtest_fwer.jsonl,
"scripts.platformkit.eval_gate.s58_clamp_family_trial:mlb_clamp_family_v1", "mlb",
"2026-06-28", "2026-07-12", family="ingame_mlb_clamp", tier="T2",
prereg_sha256=<seal>)` -- is the first statement after the seal check and the appended
row's `k_cumulative` is the only K used anywhere (Q2). The ledger holds 15 rows at sealing
(md5 b118ebd826026b7b9e59bdf89872ce16); this charge appends row 16, so launch K = 16 and the
global bar is raw DM p < 0.05/16 = 0.003125 (deflated_p(raw_p, 16) < 0.05). Exactly ONE
charge for the whole 9-config family: the family is ONE preregistered hypothesis.

## Hypothesis (why it could beat the incumbent, stated before looking)

E4_PROMOTION_RESULT section 1 (leaky tick-date series, descriptive PBO table) ordered the
clamp configs monotone in guard TIGHTNESS: d = 0.10 < 0.15 < 0.25 -- the closer the arm
sits to the market, the better its Brier -- and w_max barely mattered. The market Brier on
the same ticks is 0.195387 (below every arm), so a tighter clamp is the MARKET-PULL
direction: it buys calibration by borrowing the market's information, not by adding any.
S43 showed the guard's gain lives in the TAIL (share of loser games where the series ever
exceeded 0.8: raw 0.4198, e4 0.1605, market 0.1481). This trial asks the honest version of
that question: with the clamp width and weight cap chosen INSIDE leak-free folds, does the
family beat the incumbent e4_gd on the outer walk-forward? A YES is a calibration
improvement of the blend arm toward the anchor, never a claim against the market.

## Family (frozen order; 9 members; one charge)

`CONFIGS = [(1.0, 0.15), (0.5, 0.10), (1.0, 0.10), (2.0, 0.10), (0.5, 0.15), (2.0, 0.15),
(0.5, 0.25), (1.0, 0.25), (2.0, 0.25)]` as (w_max, max_abs_deviation). The first entry is the
incumbent config (gap_blend_arm defaults). Ties in the inner score resolve to the EARLIEST
entry in this order (the incumbent wins a tie).

## Corpus (STEP 0 counts, measured 2026-09-03 before sealing; no Brier computed)

MLB window 1: 178 games / 52,558 ticks / 7,158 in-window, 2026-06-28..2026-07-12
(`hedge_trial_arms.load_corpus`, the S01-corrected store). Every config is scored by
`gap_blend_arm._walk_forward` on GAME-FIRST-DATE folds (the S36 leak-free variant,
`stacker.e4_gd_series` generalised to (w_max, max_abs_deviation); per-fold game-disjoint
asserted). The scored row set of `_walk_forward` depends only on the date structure and
outcome variety of each train fold, never on (w, d), so all 9 configs are finite on
EXACTLY the same ticks -- asserted before the charge.

SCORED = every tick where the incumbent config's series is finite AND market_prob is
finite: **47,104 ticks / 158 games**, 13 outer game-first-dates 2026-06-30..2026-07-12
(2026-06-28 is the burn-in first date). Measured identity: this set EQUALS the S06/S58
hedge-paired 47,104-tick set (subset both ways, verified 2026-09-03). `main` asserts
(47,104, 158) and the 9-way finiteness identity BEFORE the charge; any drift stops the
trial uncharged.

## Candidate = the INNER-SELECTED series (Q4: the config is never chosen on an outer score)

For each outer fold date D (a game-first-date in 2026-06-30..2026-07-12):
1. train games = every game with first-date < D; test games = first-date == D; disjoint
   asserted.
2. INNER selection over the train games only: one cpcv state per train game
   (`state_ts` = the game's last tick + 1 s, home/away parsed as in `stacker._states`,
   features = the game's tick rows (model_prob, market_prob, signal, outcome) with
   `feature_avail` = the last tick's timestamp), `cpcv_evaluate(n_groups=8, n_test_groups=2,
   embargo_days=1)` run once per config c with predictor_c: fit the E4 weight by
   `gap_blend_arm._fit_weight(purged inner-train ticks, w_max_c, d_c)` (cached by
   frozenset(train game_ids)), predict EVERY tick of the test game with
   `_guarded_prob(..., weight, d_c)`, stash (sum of squared loss, n_ticks) for that
   (split, game), return the mid tick's probability (the contract's single float). Inner
   score(c) = sum of stashed losses / sum of stashed ticks over all splits (tick-weighted,
   the same unit as the outer Brier). Selected c_D = argmin (ties -> earliest in CONFIGS).
   If the inner run is infeasible (< 1,000 train ticks or < 8 distinct state stamps) or a
   config's fit raises, c_D = the incumbent config -- logged as `fallback`.
3. OUTER prediction for every scored tick of the test games = config c_D's OWN outer
   game-first-date walk-forward series at that tick (weight fit on ALL ticks with
   first-date < D, by `_walk_forward`) -- the same value the config would have produced
   had it been the only config.
The candidate series is the per-date splice of step 3. It is scored ONCE. The per-fold
inner score table (9 configs x 13 folds) and the chosen c_D are archived (folds JSON).

## Incumbent

e4_gd = CONFIGS[0] = (1.0, 0.15) outer series, Brier 0.206785778212713 on the 47,104
scored ticks (S06 pre-flight / S43 / S58-1 reproduction target) -- asserted to 1e-9 AFTER
the charge and BEFORE any verdict metric. Any |delta| >= 1e-9 stops the trial with no
verdict (the charge stands; K was consumed).

## Verdict rule (frozen; no bar moves, Q3)

Let d = loss(incumbent) - loss(candidate) per tick (d > 0 = candidate better), clustered
by game. AHEAD iff ALL FOUR:
  (1) paired Brier improvement = Brier(incumbent) - Brier(candidate) >= 0.004;
  (2) game-clustered Diebold-Mariano 95 pct CI of d excludes 0 with lower bound > 0;
  (3) deflated_p(raw DM p, K read at launch) < 0.05 (global Bonferroni bar);
  (4) the family bar: `family_bars.dual_bar_verdict(raw_p, K, family_p_values, q=0.05,
      family=None)` where family_p_values = the 9 configs' own outer raw DM p-values
      against the incumbent (descriptive per-config outer comparisons; the incumbent
      config against itself has d == 0 everywhere and its p is set to 1.0) PLUS the
      candidate's raw p -- 10 values priced together; the family's 9 MEMBERS are the
      configs and the candidate is the composite being charged. `ingame_mlb_clamp` is NOT
      in the frozen FWER_FAMILIES_SPEC (62702554f), so it is labelled NOT FROZEN in every
      artifact; through tiers it would be NOT_IN_FROZEN_FAMILIES and uncharged.
Else BEHIND iff Brier(candidate) > Brier(incumbent); else NULL.
SINGLE-WINDOW is labelled in the artifact and the register row (one MLB window;
min_corpora_eff(1, K) printed at launch K). BEHIND / NULL are valid, expected outcomes.
The per-config outer Briers are REPORTED, never used to pick anything: the verdict is the
inner-selected candidate's, and only that.

## Reported beside the verdict (always)

PBO via cscv_pbo over the 9 config outer series (47,104 x 9 matrix; descriptive, not a
bar); per-config outer Brier and raw DM p vs the incumbent; the 13-fold selection table
with every inner score; ESS of the SCORED differential d (ICC / design effect / n_eff);
both bars' `render_bars` line (direction-blind, quoted verbatim -- see S58-1 caveat);
the market Brier on the scored ticks; the per-tick series CSV for the verifier (Q9:
tick_index, game, timestamp, y, candidate, incumbent, selected_config).

## Leak risks named

- Inner selection sees only games with first-date < D (game-disjoint), inside purged and
  embargoed CPCV; the inner stash counts every tick of a purged TEST game (not just the
  mid tick) -- still OOF. The outer weight fit uses only first-date < D ticks.
- Multi-tick games sharing a game-first-date with each other are in the same outer fold;
  no game's own outcome is ever in its fit window (S36 assert).
- Market pull: a tighter clamp converges on the market; an AHEAD here means the blend arm
  is better calibrated TOWARD the anchor, not that anything beats the anchor (market
  Brier 0.195387 stays the floor no config can pass by construction of the guard).

Artifacts: data/cache/eval_gate/s58_trialA_clamp_family_2026-09-03.json (+ _series CSV,
+ _folds JSON), memo docs/evidence/harness/S58_trialA_clamp_family_2026-09-03.md.
Must not move: BAR 0.004, ALPHA 0.05, q 0.05, gap_blend_arm._GRID_POINTS 201 and its
_fit_weight / _guarded_prob / _walk_forward, deflated_p, min_corpora_eff, cscv_pbo,
diebold_mariano, every threshold under scripts/platformkit/eval_gate/, the ledger
except the one appended row, data/registry/** (never written). Calibration language only.
