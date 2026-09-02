# S06 step-0 pre-flight: which arm series are out-of-fold (2026-09-03)

Purpose: PLAN_HARNESS_EXECUTION_2026-09-03.md S06 step-0 requires this proof IN
WRITING before the stacker trial may charge. Read-only work: nothing charged, no
ledger write, no module edited. All numbers measured on this box today from
data/cache/ingame_grade_joined/mlb (178 games / 52,558 ticks / 7,158 in-window,
2026-06-28..2026-07-12; reproduced by scripts.platformkit.ingame.
run_gap_arms_real_corpus._load_ticks). Calibration language only.

## 1. Per-arm OOF verdicts (evidence: file:line + measured counts)

Boundary fact both leaks rest on: 124/178 games (69.7 pct) span more than one
UTC date (evening starts cross midnight), so tick-date folds put a game's
earlier-date ticks -- each carrying its FINAL outcome -- into the fit window
that scores the same game's later ticks. Date-ordering asserts cannot see this.

- raw_model: OOF BY CONSTRUCTION (forward capture). model_prob is computed
  as-of-tick by the live daemon: inplay_capture_loop.py:288 _default_model_fn
  routes predict_live through the resolved predictor chain; the model is
  domains/mlb/predictor.py:78 MLBPredictor, predict_live :237 (repricer-coherent
  lambdas). Header rail inplay_capture_loop.py:32: "LEAK-FREE: p0 is pregame;
  model_prob is as-of-tick". At each capture timestamp the outcome did not yet
  exist; no fit window exists at all. PROVABLY OOF.
- e1_offset: OOF (asserted game-disjoint prior-date folds).
  gap_offset_arm.py:137 _walk_forward keys folds by GAME first date
  (wp_diag_oos.py:44 _game_dates = min tick date per game), so all of a game's
  ticks land in one fold; asserts :153-154 (max fit / calibration game date <
  eval_date) and :112 (fit and calibration games disjoint). A game's own ticks
  are never in its fit window. Caveat (named, not disqualifying): a fit game
  whose first date is d-1 can end after an eval game's first ticks on date d
  (cross-GAME concurrency at the UTC boundary, other-game outcome only, no
  self-leak); the stacker's inner CPCV embargo covers this at the meta level.
- e4_blend: LEAKY AS COMPUTED. hedge_trial_arms.py:60 e4_blend_series ->
  gap_blend_arm.py:79 _walk_forward; the only assert is :84 (train non-empty +
  max train date < min test date) -- date ordering, NOT game disjointness.
  _fit_weight :69 consumes train outcomes. Measured: 25,000/47,292 scored ticks
  (52.86 pct, 124 games) sit in a fold whose fit window contains the same
  game's earlier-date ticks with its final outcome, undetermined at the scored
  tick's timestamp. Counterfactual with game-first-date folds (self-leak
  removed, identical 47,104-tick paired denominator): Brier 0.206785778212713
  vs leaky 0.207032929516776; delta -0.000247151 -- the leak did NOT flatter
  the incumbent (leak-free is slightly better). The one assert that would prove
  OOF: per fold in _walk_forward, assert not (set(train["game"]) &
  set(test["game"])) -- it FAILS today and passes when each tick carries
  game_date = its game's first date (gap_blend_arm._date :24 already prefers
  game_date; no module edit needed, only tick preparation).
- e2_regime: LEAKY AS COMPUTED. The plan's claim is CONFIRMED: hedge_trial_
  arms.py:97 asserts max(train date) < test_date, and the module's own evaluate
  has the same assert at gap_regime_arm.py:118 -- but both prove date ordering
  only. Measured: 2,867/6,593 scored ticks (43.49 pct, 103 games) self-leak.
  Counterfactual game-first-date folds (6,579-tick intersection): leak-free
  Brier 0.254350980569169 vs leaky 0.252261297271879; delta +0.002089683 --
  the leak FLATTERED e2 by half the +0.004 bar. Same proving assert applies
  (present in my counterfactual run; absent in the shipped series).

## 2. Reproduction of each arm's reported Brier from the store (target 1e-9)

Scripts (read-only, this box): scratchpad s06_preflight.py / s06_gamedisjoint.py.
Coverage reproduced exactly: raw 52,558 / e4 47,292 / e1 47,104 / e2 6,593.

E4 promotion artifact (e4_promotion_trial_2026-09-01.json, primary block,
47,104 paired ticks / 158 games -- denominator reproduced exactly):
- e4_blend  reproduced 0.207032929516776  vs 0.2070329295167757  |delta| = 0.0
- raw_model reproduced 0.236682901513263  vs 0.23668290151326293 |delta| = 0.0
- market    reproduced 0.195386957583225  vs 0.19538695758322486 |delta| = 0.0

Hedge artifact (hedge_trial_2026-09-01.json, pbo.config_brier, n_obs 6,579 =
all-configs-finite intersection -- n_obs reproduced exactly):
- raw_model  reproduced 0.242038924145072 vs artifact same |delta| = 0.0
- e4_blend   reproduced 0.206626955278589 vs artifact same |delta| = 0.0
- e1_offset  reproduced 0.281762477954033 vs artifact same |delta| = 0.0
- e2_regime  reproduced 0.252261297271879 vs artifact same |delta| = 0.0
All eight comparisons: |delta| = 0.0 < 1e-9 (bitwise at printed precision).
Wall time ~4 minutes locally (e1's XGBoost folds dominate).

## 3. DROP list for the S06 stacker (Q4: OOF-provable series only)

ENTER as-is:
- raw_model (forward capture, no fit window).
- e1_offset (asserted game-disjoint folds; reproduction target for the Q4
  1e-9 assert: 0.281762477954033 on the 6,579 intersection).
ENTER ONLY AS THE GAME-FIRST-DATE VARIANT (as-computed series DROPPED):
- e4_blend: leak-free series, Brier 0.206785778212713 on the same 47,104
  paired ticks (this becomes its Q4 reproduction target).
- e2_regime: leak-free series, Brier 0.254350980569169 on 6,579; coverage is
  6,593/52,558 ticks (12.5 pct, in-window only) so under spec rule (3) it is
  MASKED at ~87 pct of ticks -- entering it is permissible, not load-bearing.
DROPPED and named: the shipped tick-date e4_blend and e2_regime series
(self-leak shares 52.86 pct and 43.49 pct of their scored ticks).

## 4. Prereg-consistency check (S06 block vs artifacts and ledger)

- Incumbent 0.207033: CONFIRMED = e4 promotion artifact primary hedge_brier
  0.2070329295167757, reproduced to 0.0. WORDING DRIFT: the plan calls it
  "in-window Brier"; it is the paired ALL-TICKS Brier (the in-window slice is
  a different, smaller denominator). Correction quoted in section 5.
- Scored 158 games / 47,104 ticks: CONFIRMED (artifact primary n_games/n_ticks;
  reproduced independently from the store).
- Corpus 178 games / 52,558 ticks, 2026-06-28..2026-07-12: CONFIRMED (artifact
  corpus block; reproduced). S01's constants fix (52558/7158) is on disk and
  matches the loader counts.
- Ledger: backtest_fwer.jsonl has exactly 13 rows; row 13 k_cumulative=13 at
  2026-09-01T23:39:17.271881+00:00, predictor hedge_trial_runner:e4_promotion
  -- matches "K=13 at 2026-09-01T23:39:17Z" verbatim. S06's own charge will
  append row 14, so launch K = 14; the prereg's "at K=14 raw p < 0.05/14 =
  0.00357" arithmetic checks (0.003571). Charge-before-metric pattern
  confirmed in code: hedge_trial_runner.py:172 (LEDGER :37).
- No other drift found. No S06 prereg file exists on disk yet (the text lives
  in the plan block and is sealed at dispatch) -- corrections can still enter.

## 5. GO / NO-GO

GO WITH CORRECTIONS: dispatch S06 only after amending the spec/prereg text
(before sealing) as follows; with them the trial is honestly specified.
1. Step-0 sentence "e2_regime has its own max(train date) < test date assert"
   -- true but insufficient; replace the implied conclusion with: "date order
   does not give game disjointness (124/178 games span UTC dates); every arm
   series entering fit_meta uses game-first-date folds".
2. "Incumbent: e4_blend alone at in-window Brier 0.207033 on those ticks" ->
   "Incumbent: e4_blend alone at paired all-ticks Brier 0.207033 on those
   ticks; the pairing series is the game-first-date (leak-free) e4 variant,
   Brier 0.206785778212713 -- a stricter comparator by 0.000247".
3. Q4 1e-9 arm-reproduction targets: raw_model 0.236682901513263 (47,104),
   e1_offset 0.281762477954033 (6,579 intersection), e4_gd 0.206785778212713
   (47,104), e2_gd 0.254350980569169 (6,579).
4. "raw_model inherits the in-game model's discipline (name it)" -- named:
   domains/mlb/predictor.py MLBPredictor.predict_live via
   inplay_capture_loop._default_model_fn, captured as-of-tick.

NOT VERIFIED here: DM CIs, deflated p, PBO splits and CPCV path counts of the
two 2026-09-01 artifacts (Briers only were recomputed); the e1 cross-game
concurrency share at the UTC boundary (other-game, not self); soccer_intl.
