# S87 -- in-game tick informativeness: dedup + held flags, and the S58/S80 re-quote

Date 2026-09-03 | lane S87 | tier RE-QUOTE (no charge, no seal, no prereg, no model recomputed)
Verdict **NOT VERIFIED** -- this memo is the lane's own report; the numbers below are reproduced
from artifacts on disk but no independent verifier has re-run them.
Calibration language only. Nothing here is a dollar, ROI or edge claim; every verdict re-quoted
below stays exactly where it was.

## 0. Premise reproduction (Q8) -- REPRODUCED EXACTLY

Store `data/cache/ingame_grade_joined/mlb`, 227 jsonl files read as written.
Artifact: `data/cache/eval_gate/s87_requote_2026-09-03_premise.json`.

| quantity | gap row S87 / L5 | measured this lane | verdict |
|---|---|---|---|
| rows | 78,986 | 78,986 | exact |
| games | 227 | 227 | exact |
| duplicate `(game_id, ts)` rows | 1,659 (2.10 pct) | 1,659 (2.10 pct) | exact |
| `market_prob` held from previous tick | 59,045 / 78,759 = 74.97 pct | 59,045 = 74.97 pct | exact |
| `model_prob` held from previous tick | 72,232 / 78,759 = 91.71 pct | 72,232 = 91.71 pct | exact |
| both held | 55,022 / 78,759 = 69.86 pct | 55,022 = 69.86 pct | exact |
| informative ticks | 23,964 (30.34 pct) | 23,964 | exact |

All four headline numbers reproduce to the row under the gapfinder's own rule (held = the float
is EXACTLY equal to the previous row of the same game; denominator 78,759 = 78,986 - 227
first-of-game rows, which are never held).

The shipped module uses a slightly stricter rule -- held iff the value is within eps = 1e-9 of
the previous tick, the complement of `ingame/quote_freshness.freshness_mask`'s FRESH test -- so
it counts 116 more market holds and 45 more model holds: 59,161 / 72,277 / both 55,172 /
informative 23,812 (30.15 pct). The two rules classify 152 of 78,986 rows (0.19 pct)
differently as informative, well inside the 1 pct premise tolerance. Both are in the premise artifact; the eps rule is the one
the code uses, because a 1e-12 wiggle in a re-derived probability is not new information.

Cross-check kept from L5: `state_summary` held on 34,848 / 78,759 = 44.25 pct -- reproduced
exactly, which confirms the row set read here is the row set the gapfinder read.

Clustered ESS on the same store (loss differential = market loss - model loss, cluster = game,
via `ingame/gap_effective_n.effective_sample_size`, NOT reimplemented):
all 78,986 rows -> rho 0.2709, deff 95.00, **n_eff 831.5**; informative 23,812 rows ->
rho 0.1934, deff 21.09, **n_eff 1,128.8**. Dropping 70 pct of the rows RAISES the effective
sample by 36 pct, because the redundant ticks are what inflate the intra-game correlation.

## 1. What was built

`scripts/platformkit/eval_gate/tick_informative.py` (231 lines, additive, no existing caller
touched; A5 sweep: `is_informative` / `tick_informative` appear nowhere else in
`scripts/`, `src/`, `kernel/`, `api/`).

- `flag_ticks(frame, ...) -> (frame + flags, summary)` -- pure (input frame untouched). Adds
  `is_dup` (a later row with a `(game, ts)` pair already seen), `is_held_market`,
  `is_held_model` (repeats the previous tick of the SAME game; the first tick of a game is
  never held), `is_informative` (`not is_dup` and market or model moved). Summary =
  `{n, n_dup, n_held_market, n_held_model, n_held_both, n_informative, n_games, n_eff_icc}`,
  where `n_eff_icc` is `gap_effective_n.effective_sample_size` on the informative subset and is
  `None` when no loss column is supplied (the module never invents a loss series).
- `requote(name)` + CLI -- re-quotes the three archived Q9 per-tick series. It recomputes NO
  model: it reads the archived paired losses as written and only changes the ROW SET.
- Test: `scripts/platformkit/eval_gate/test_tick_informative.py`, 7 passed
  (`python -m pytest scripts/platformkit/eval_gate/test_tick_informative.py -q`).

## 2. The re-quote (artifact `data/cache/eval_gate/s87_requote_2026-09-03.json`)

Each row's published CI was FIRST reproduced from its own archived series -- all three came
back bit-for-bit (`published_ci_reproduced_from_series: true`), which is the Q9 blocking
condition for reading the informative-subset number beside it.

| artifact | published verdict | n | n_informative | n_eff before -> after | DM ci95 before | DM ci95 after | status |
|---|---|---|---|---|---|---|---|
| S58 trial A clamp (`s58_trialA_clamp_family_series_2026-09-03.csv`) | NULL / NOT AHEAD (blocked global+family) | 47,104 | 14,543 (30.9 pct) | 566.18 -> 1,098.24 | [-0.000364, +0.002096] | [-0.000475, +0.000537] | unchanged |
| S58 trial B NBA halftime (`s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv`) | BEHIND / NOT AHEAD (blocked global) | 1,593 | 1,593 (100 pct) | 1,593.00 -> 1,593.00 | [-0.011503, -0.001664] | [-0.011503, -0.001664] | unchanged |
| S80 player grain (`s80_player_grain_2026-09-03.csv`) | SCREEN_NULL | 2,267 | 1,106 (48.8 pct) | 79.25 -> 62.56 | [-0.026879, +0.034398] | [-0.032578, +0.036079] | unchanged |

Held / dup detail per artifact:
- trial A: dup 0, held market 33,998, held model 41,900, both held 32,561 of 47,104.
  Its scored tick set carries no duplicate `(game, timestamp)` pair at all.
- trial B: dup 0, held 0 -- ONE row per game at the halftime anchor, so no row can be held or
  duplicated. The flag pass is a no-op here by construction and the CI is byte-identical.
- S80: dup 5, held market 1,431, held model 1,385, both held 1,160 of 2,267.

Verdict status, stated per row:
- **S58 trial A -- unchanged (NULL stays NULL).** The CI still straddles zero. What the
  re-quote does show is that the mean paired loss differential collapses from 0.000866 to
  0.000031 (DM p 0.166 -> 0.904) once the redundant ticks are dropped: the whole apparent
  (already non-significant) separation lived in ticks where neither side had moved. n_eff
  nearly doubles (566 -> 1,098) on a third of the rows, so this is a sharper, not weaker, null.
- **S58 trial B -- unchanged (BEHIND stays BEHIND).** Per-game rows; the informative filter is
  structurally a no-op, the CI is identical, and the model still sits behind the market at the
  halftime anchor.
- **S80 -- unchanged (SCREEN_NULL stays SCREEN_NULL).** The mean differential halves
  (0.003759 -> 0.001751), the CI widens slightly and still straddles zero; n_eff falls
  79 -> 63, i.e. this screen has even less effective evidence than its raw 2,267 ticks suggest.

No verdict must be re-labelled. No multiplicity bar was recomputed: a verdict blocked by the
global/family bars stays blocked, and this pass neither reads nor charges K.

## 3. Guard rails observed

- No charge, no seal, no prereg: `_charge_ledger` never called. `data/cache/eval_gate/backtest_fwer.jsonl`
  is untouched at 18 rows, md5 a4ae7c13995672e478d59770591b83ba (checked after the run).
- `data/registry/` untouched; no feature flag flipped; no bar or threshold read or written
  (B10 / Q3); no `--force`.
- No archived artifact rewritten -- the two new files are
  `s87_requote_2026-09-03.json` and `s87_requote_2026-09-03_premise.json`.
- B2 additive: a new module with new column names, no rename, no existing reader affected.
- No edits to `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`, and none to the
  `ingame_grade_joined/mlb` writer that lane S83 owns -- this pass only READS that store.
- Q6: calibration language only; none of the retracted figures appears.

## 4. Honest limits (NOT VERIFIED)

- One store measured (`ingame_grade_joined/mlb`). The wider `ingame_grade` cross-check numbers
  in L5 (soccer_intl, and the `ingame_grade` mlb copy) were NOT re-measured here.
- The flags are computed, but nothing in the scoring path calls them yet: this pass does not
  make `n / n_informative / n_eff` mandatory on future in-game readouts. Wiring the triple into
  the verdict writers is the remaining half of the S87 bar and is not done.
- "Informative" is a market/model-movement definition only. A tick where the GAME state changed
  but neither probability moved is counted as redundant, which is the right call for a paired
  loss comparison and the wrong one for a state-feature screen.
- Only the three named artifacts were re-quoted; other in-game CIs on the books are still
  quoted on raw tick counts.
