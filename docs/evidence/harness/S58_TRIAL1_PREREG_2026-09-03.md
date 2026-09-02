# S58 trial 1 prereg (sealed 2026-09-03) -- MLB e2_regime leak-free vs e4_blend leak-free on e2's own covered slice

Sealed BEFORE any metric: this file is committed alone, its SHA-256 is pinned as
`PREREG_SHA256` in `scripts/platformkit/eval_gate/s58_e2_slice_trial.py`, verified by
`run_trial` before the ledger charge, and embedded in the trial JSON and the memo (Q1).
The charge -- `_charge_ledger(data/cache/eval_gate/backtest_fwer.jsonl,
"scripts.platformkit.eval_gate.s58_e2_slice_trial:mlb_e2_slice_v1", "mlb",
"2026-06-28", "2026-07-12", family="ingame_mlb_arms", tier="T2",
prereg_sha256=<seal>)` -- is the first statement after the seal check, and the appended
row's `k_cumulative` is the only K used anywhere (Q2). The ledger holds 14 rows at sealing
(md5 b1b1253821b06bbf501ecb8f19937c9c); this charge appends row 15, so launch K = 15 and the
global bar is raw DM p < 0.05/15 = 0.003333 (deflated_p(raw_p, 15) < 0.05).

## Path used and why

NOT the tiers.run_tier T2 path: `tiers._run_charged` scores `cpcv_evaluate` over pregame
STATES and pools ONE prediction per event (`_pooled_oof`), so a per-tick in-game comparison
cannot pass through it without collapsing 6,579 ticks to 157 game rows. The charge therefore
goes through `_charge_ledger` with the S13 keyword fields (family / tier / hypothesis_hash /
prereg_sha256) and `family_bars.dual_bar_verdict` is applied by hand (S59 dual bar).
Family `ingame_mlb_arms` is NOT in the frozen FWER_FAMILIES_SPEC (62702554f); under the
tiers rule it would be NOT_IN_FROZEN_FAMILIES and uncharged. Here the family bar is
computed honestly as a FAMILY OF ONE (BH over this trial's own raw p, no prior family
p-values exist in the results DB) and is labelled so in every artifact. That is the
loosest the family bar can be; it can only block, never help, relative to the global bar.

## Corpus (STEP 0 counts, measured 2026-09-03 before sealing; no Brier computed)

MLB window 1: 178 games / 52,558 ticks / 7,158 in-window, 2026-06-28..2026-07-12
(`hedge_trial_arms.load_corpus`, the S01-corrected store). Candidate series = the
game-first-date e2_regime variant `stacker.e2_gd_series` (per-fold game-disjoint assert);
incumbent series = the game-first-date e4_blend variant `stacker.e4_gd_series`
(`arm_b_prob`). Both are the S06/S36 leak-free builders, unchanged.

SLICE = every tick where e2_gd is finite AND market_prob is finite:
**6,579 ticks / 157 games**, all 6,579 in-window, game-first-dates 2026-06-30..2026-07-12
(13 dates; the 2026-06-28 first-date games are e2's walk-forward burn-in; 2026-06-29 does
not appear as a game-first-date on the slice -- the reason was not measured). Measured identities: (e2_gd & e4_gd & market) = (e2_gd & shipped e2 &
market) = 6,579 / 157 -- e4_gd is finite on every slice tick, so nothing is dropped by the
pairing. `main` asserts (6,579, 157) BEFORE the charge; any drift stops the trial uncharged.

Partition (FACTORY_TIERS_SPEC SF-1, iso_week basis): e2_regime has never been screened on
any row (its only prior appearances are the uncharged 2026-09-01 gap-arms/Hedge diagnostics
and the S06 masked arm), so no SCREEN side exists and the WHOLE slice is the VERDICT side.
The slice's ISO-week blocks are printed in the artifact; `screen_blocks` is empty.

## Incumbent

e4_gd scored on the SAME 6,579 ticks -- computed AFTER the charge, inside the trial.
0.206786 (0.206785778212713) is the 47,104-tick figure and is NOT the slice incumbent; it is
kept only as a Q4 reproduction target. Before (candidate, as recorded by S06 on this exact
slice): e2_gd 0.254350980569169 -- also a reproduction target, not a bar.

## Verdict rule (frozen; no bar moves, Q3)

Let d = loss(e4_gd) - loss(e2_gd) per tick (d > 0 = e2 better), clustered by game.
AHEAD iff ALL FOUR:
  (1) paired Brier improvement = Brier(e4_gd slice) - Brier(e2_gd slice) >= 0.004;
  (2) game-clustered Diebold-Mariano 95 pct CI of d excludes 0 with lower bound > 0;
  (3) deflated_p(raw DM p, K read at launch) < 0.05 (global Bonferroni bar);
  (4) the family bar passes (dual_bar_verdict family_pass, q = 0.05, fdr_bh rule, family of
      one as stated above; fdr_by printed beside it).
Else BEHIND iff Brier(e2_gd slice) > Brier(e4_gd slice); else NULL.
SINGLE-WINDOW is labelled in the artifact and the register row (one MLB window;
min_corpora_eff(1, K) printed at launch K). BEHIND / NULL are valid, expected outcomes.

## Q4 reproduction gates (asserted after the charge, before any verdict metric)

- e2_gd on the 6,579-tick intersection (e2_gd & shipped e2 & market): 0.254350980569169.
- e4_gd on the 47,104-tick S06 scored set (hedge-paired e4 & market): 0.206785778212713.
Any |delta| >= 1e-9 stops the trial with no verdict (the charge stands; K was consumed).

## Reported beside the verdict (always)

PBO via cscv_pbo over the configs [e2_gd, e4_gd, raw_model] on the slice (a 3-column
matrix; descriptive, not a bar); ESS of the SCORED differential d (ICC / design effect /
n_eff, labelled as this trial's own); both bars' full `render_bars` line; the raw_model
Brier on the slice; the per-tick series CSV for the verifier's recomputation.

Artifacts: data/cache/eval_gate/s58_trial1_e2_slice_2026-09-03.json (+ _series CSV),
memo docs/evidence/harness/S58_trial1_e2_slice_2026-09-03.md.
Must not move: BAR 0.004, ALPHA 0.05, q 0.05, deflated_p, min_corpora_eff, cscv_pbo, every
threshold under scripts/platformkit/eval_gate/, data/registry/** (never written).
Calibration language only.
