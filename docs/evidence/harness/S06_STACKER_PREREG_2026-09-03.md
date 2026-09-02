# S06 stacker charged-trial prereg (sealed 2026-09-03)

Sealed BEFORE any metric: the SHA-256 of this exact file is verified by
`scripts.platformkit.eval_gate.stacker.run_stacker_trial` before the ledger
charge, is embedded in the trial JSON as `prereg_sha256`, and this file is
committed before the trial runs (Q1). The charge
(`_charge_ledger(data/cache/eval_gate/backtest_fwer.jsonl,
"scripts.platformkit.eval_gate.stacker:mlb_stack_v1", "mlb", "2026-06-28",
"2026-07-12")`) is the first statement after the seal check, and the appended
row's `k_cumulative` is the only K used anywhere (Q2).

## PREREG (verbatim from the dispatch spec)

"One charged trial. Corpus: MLB 178-game / 52,558-tick window
2026-06-28..2026-07-12; scored after burn-in and pairing = 158 games / 47,104
ticks. Incumbent: e4_blend alone at in-window Brier 0.207033 on those ticks.
AHEAD iff (i) paired Brier improvement >= 0.004, (ii) game-clustered DM 95 pct
CI excludes 0, (iii) deflated p < 0.05 at the ledger K READ AT LAUNCH (K=13 at
2026-09-01T23:39:17Z; at K=14 raw p < 0.05/14 = 0.00357). Reported beside the
verdict always: PBO via cscv_pbo, the UNIFORM-weight arm's Brier, the
guard-only arm's Brier -- if the advantage over guard-only is under the bar
the memo names the GUARD. BEHIND is valid and expected; the module is kept
either way. SINGLE-WINDOW is labelled in the artifact and the register row;
min_corpora_eff printed at launch K."

## Pre-flight corrections (binding; S06_OOF_PREFLIGHT_2026-09-03.md, GO WITH CORRECTIONS)

1. Incumbent wording: "in-window Brier 0.207033" is corrected to the PAIRED
   ALL-TICKS Brier. The before is e4_blend alone at paired all-ticks Brier
   0.207033 (0.2070329295167757) on the 47,104 paired ticks / 158 games. The
   per-tick DM pairing series is the game-first-date (leak-free) e4 variant,
   Brier 0.206785778212713 -- a stricter comparator by 0.000247; the bar is
   still measured against 0.207033 exactly as preregistered.
2. Arms: raw_model and e1_offset enter AS-IS (provably OOF). e4_blend and
   e2_regime enter ONLY as GAME-FIRST-DATE recomputed variants with a per-fold
   train/test game-disjoint assert; the shipped tick-date series are DROPPED
   (self-leak shares 52.86 pct and 43.49 pct of their scored ticks). Date
   order does not give game disjointness (124/178 games span UTC dates); every
   arm series entering fit_meta uses game-first-date folds.
3. Q4 1e-9 arm-reproduction targets, asserted inside the trial after the
   charge and before any verdict metric: raw_model 0.236682901513263 (on the
   47,104 paired ticks); e4 leak-free 0.206785778212713 (same 47,104);
   e1_offset 0.281762477954033 (the 6,579 hedge-artifact intersection);
   e2 leak-free 0.254350980569169 (its 6,579 intersection). Any mismatch stops
   the trial with no verdict.
4. raw_model provenance named: domains/mlb/predictor.py MLBPredictor
   .predict_live via inplay_capture_loop._default_model_fn, captured
   as-of-tick (forward capture; no fit window exists).
5. Launch K is read AT CHARGE TIME from the appended ledger row's
   k_cumulative. The ledger holds 13 rows at sealing; this trial's charge
   appends row 14, so launch K = 14 and raw p < 0.05/14 = 0.00357 applies
   exactly as preregistered.

## Protocol constants (fixed here, before any metric)

- Meta: logit-ridge logistic (combo.stack_fit.fit_logistic, ridge 1e-4);
  weights per regime key = inning bucket (early_1_3 / mid_4_6 / late_7plus /
  unknown) and per availability pattern -- an absent arm is a MASK, never a
  0.5 imputation.
- Inner: cpcv_evaluate(n_groups=8, n_test_groups=2, embargo_days=1) over
  outer-train game states; per-fold fits keyed by the explicit content fold id
  frozenset(train game_ids) (never id(train), RT-2), averaged across folds.
- Outer: expanding game-first-date walk-forward with a per-fold train/test
  game-disjoint assert. MIN_TRAIN=1000 ticks, MIN_REGIME=200, MIN_PATTERN=200;
  an outer fold with under MIN_TRAIN ticks or under 8 distinct inner state
  timestamps (the inner engine's n_groups) uses the fallback arm.
- Fallback arm: the game-first-date e4_blend variant; where it is absent at a
  tick, raw_model (present at every tick).
- Scored set: the e4-promotion paired denominator (orig-e4 hedge pairing AND
  market_prob present) = 47,104 ticks / 158 games, asserted before the trial;
  dropped ticks are counted and named in the artifact (no post-hoc exclusion).

Calibration language only. BEHIND / NULL is a valid, expected result; the
module lands either way. The +0.004 bar never moves (Q3).
