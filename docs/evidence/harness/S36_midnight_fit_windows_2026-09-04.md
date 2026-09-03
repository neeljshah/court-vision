# S36: opt-in game_first_date fit window for e4_blend / e2_regime (2026-09-04)

Spec: docs/evidence/tracking/specs/S36_spec.md. INSTRUMENT FIX ONLY -- no
charge, no `_charge_ledger` import/call anywhere in this diff.
`data/cache/eval_gate/backtest_fwer.jsonl` is untouched (not read, not
written; confirmed byte-identical by never opening it). Calibration language
only (Q6).

## 0. Premise re-check (step 0)

Confirmed by fresh grep before any edit: neither module had a train/test
game-disjointness assert.
- `gap_blend_arm.py:84` (pre-edit): `assert not train.empty and
  train["date"].max() < test["date"].min()` -- date order only.
- `gap_regime_arm.py:118` (pre-edit): `assert fold["train_date_max"] <
  test_date` -- date order only.
Both modules' `_date` helpers key per-TICK date (game_date/date/timestamp),
confirmed at gap_blend_arm.py:24-28 and gap_regime_arm.py:20-24. No in-module
`fit_window` option existed; the only leak-free path was the external
tick-relabeling trick already in `scripts/platformkit/eval_gate/stacker.py`
(`e4_gd_series`, `e2_gd_series`), which pre-writes `game_date` on each tick
before calling the unchanged module. Premise CONFIRMED, not falsified.

## 1. Change

Additive-only opt-in `fit_window` parameter, default `"tick_date"` (old
behavior, byte-identical):
- `scripts/platformkit/ingame/gap_blend_arm.py` (185 LOC): `_walk_forward` and
  `evaluate` gain `fit_window: str = "tick_date"`. In `"game_first_date"`
  mode, `_walk_forward` relabels each row's `date` to its GAME's minimum tick
  date (`frame.groupby("game")["date"].min()`) before folding. Per fold, a new
  `_check_disjoint(train_games, test_games, fit_window)` helper (:81-90)
  checks `train_games & test_games`.
- `scripts/platformkit/ingame/gap_regime_arm.py` (218 LOC): new
  `_fold_date_fn(fit_window, ticks)` returns `_date` unchanged in
  `"tick_date"` mode, or a per-game-minimum-date lookup (built from the FULL
  input `ticks` sequence, not just the in-window/required-field subset) in
  `"game_first_date"` mode. `evaluate` gains the same `fit_window` param and
  its own copy of `_check_disjoint` (:117-126).
- One landmine caught and fixed before landing: an early version of
  `gap_regime_arm`'s game-first-date lookup used the in-window-filtered
  `usable` list to find each game's minimum date, which can be LATER than the
  game's true first tick (its earliest ticks may be out-of-window). That gave
  a materially wrong Brier (0.260 vs the 0.254351 target) until the lookup
  was switched to scan the full unfiltered `ticks` sequence, matching
  `stacker._first_dates`.

## 1a. CORRECTION (2026-09-04, orchestrator ACCEPT WITH CORRECTIONS)

The first landed version made `_check_disjoint` raise `AssertionError` in
**both** `fit_window` modes. That is correct for `"game_first_date"` (the S36
bar) but wrong for `"tick_date"` (the legacy default): several existing
production readers call `gap_blend_arm`/`gap_regime_arm` in default
`"tick_date"` mode on the real, midnight-spanning corpus, where a violation is
expected (that is the whole point of S36's measurement) -- the assert crashed
every one of them.

Fixed by making the raise conditional:
- `fit_window="game_first_date"`: `_check_disjoint` still raises
  `AssertionError("fold games not disjoint (self-leak)")` on any violation --
  unchanged, this is the bar and it is not weakened.
- `fit_window="tick_date"` (default): `_check_disjoint` never raises. Instead
  `_walk_forward` (blend) / `evaluate` (regime) count the leaked ticks across
  all scored folds and expose them additively:
  - `gap_blend_arm._walk_forward`'s returned scored `DataFrame` carries
    `.attrs["self_leak_ticks"]` (gap_blend_arm.py:128); `evaluate`'s report
    dict adds `"self_leak_ticks"` and `"self_leak_pct"` (gap_blend_arm.py:173-178).
  - `gap_regime_arm.evaluate`'s report dict adds the same two fields
    (gap_regime_arm.py:175-182).
  - Both emit exactly one `logging.warning` (not per-fold) naming the count,
    pct, and the opt-in `fit_window="game_first_date"` escape hatch, only when
    `leak_ticks > 0` in `tick_date` mode.
- No existing call site's numeric output moves: the guarded probabilities /
  Brier math is untouched in both modes; only the crash-vs-count behavior of
  the disjointness check changed, plus the two new additive report fields.

### Reader table (every module that reaches `_walk_forward`/`evaluate`)

| Reader | Mode called | Leak-free today? |
|---|---|---|
| `run_gap_arms_real_corpus.py:82-83` (`evaluate`, both arms) | `tick_date` (default, not passed) | NO -- real self-leak on the corpus: e4 52.86 pct (25,000/47,292), e2 43.49 pct (2,867/6,593); now counted+warned, not raised |
| `hedge_trial_arms.py:71` (`e4_blend_series` -> `gap_blend_arm._walk_forward`) | `tick_date` (default, not passed) | NO -- same real self-leak profile as above; now counted+warned |
| `hedge_trial_arms.py:91-100` (`e2_regime_series`) | reimplements its own fold loop with `gap_regime_arm._date`/`_apply`/`fit_per_regime`/`buckets` directly | N/A -- bypasses `evaluate()` and `_check_disjoint` entirely; this change does not touch it (no `self_leak` field available for this path) |
| `eval_gate/stacker.py:172` (`e4_gd_series`'s own inline assert) | pre-relabels `game_date` to each game's first date before calling `gap_blend_arm._frame`/`_walk_forward`; the module call at :174 is default `tick_date` but the frame's `date` column already equals game-first-date | YES -- trivially leak-free by construction (S06 pre-flight trick), unaffected by this fix either way |
| `eval_gate/stacker.py:264` (`main()`: `A.e4_blend_series`, `A.e2_regime_series`) | `tick_date` (default) | NO -- real self-leak; these outputs (`e4o`/`e2o`) feed only `hedge_e4`/denominator slicing, not the scored trial's `e4g`/`e2g` arms (those come from the leak-free `*_gd_series` at :266) |
| `eval_gate/s58_clamp_family_trial.py:63` (`signal_frame`'s own inline assert; `outer_series` -> `gap_blend_arm._walk_forward` at default) | frame pre-relabeled to game-first-date before the call, same trick as stacker | YES -- trivially leak-free by construction |
| `eval_gate/s58_e2_slice_trial.py:121` (`main()`: `A.e2_regime_series`, `A.e4_blend_series`) | `tick_date` (default) | NO -- real self-leak; used only for `hedge_e4`/denominator slicing, not the scored trial's `e2g`/`e4g` (from `*_gd_series`) |
| `hedge_trial_runner.py:156/159` (`e4_configs`: `A.e4_blend_series` guard-only + `E4_VARIANTS`) | `tick_date` (default) | NO -- real self-leak; candidate-mode PBO matrix construction |
| `eval_gate/s80_player_grain_screen.py` | imports `gap_blend_arm` for `_guarded_prob` only | unaffected -- never calls `_walk_forward`/`evaluate`/`_check_disjoint` |

## 2. Before / after (measured on the S06 corpus partition: 178 games / 52,558
ticks, data/cache/ingame_grade_joined/mlb, 2026-06-28..2026-07-12)

| arm | mode | n_ticks | n_games | self-leak pct | Brier |
|---|---|---|---|---|---|
| e4_blend | tick_date (shipped, before) | 47,292 | -- | 52.86 pct (25,000/47,292) | 0.207032929516776 |
| e4_blend | game_first_date (after) | 47,104 | 158 | 0.00 pct (assert-enforced) | 0.206785778212713 |
| e2_regime | tick_date (shipped, before) | 6,593 | -- | 43.49 pct (2,867/6,593) | 0.252261297271879 |
| e2_regime | game_first_date (after) | 6,579 | 157 | 0.00 pct (assert-enforced) | 0.254350980569173 |

Both "after" Briers reproduce the spec's target to well within 1e-6: e4
|0.206785778212713 - 0.206786| < 1e-6; e2 |0.254350980569173 -
0.254350980569169| = 4e-15 < 1e-6. Both are also byte-identical
(max_abs_diff == 0.0 across every common index) to the pre-existing external
relabel builders `stacker.e4_gd_series` / `stacker.e2_gd_series`, which
already round-trip the same target from S06_OOF_PREFLIGHT_2026-09-03.md and
are asserted in `s58_e2_slice_trial.py:33,128` to the SAME denominators
(47,104 / 6,579).

## 3. tick_date mode on this corpus (the leak proof) -- CORRECTED 2026-09-04

Original text (now WRONG, kept below for the record): "`fit_window=
'tick_date'` (default) now raises `AssertionError` ... nothing currently in
this worktree calls `evaluate()`/`_walk_forward()` with default `fit_window`
on this real corpus as part of a live pipeline." That premise was FALSE -- see
section 1a's reader table: `run_gap_arms_real_corpus.evaluate`,
`hedge_trial_arms.e4_blend_series`, `stacker.py`'s `main()`,
`s58_e2_slice_trial.py`'s `main()`, and `hedge_trial_runner.e4_configs` all
call default `tick_date` mode directly on the real, un-relabeled per-tick
corpus. The original raise-in-both-modes implementation would crash every one
of them.

Corrected behavior, reproduced live (section 5b): `fit_window="tick_date"`
(default) no longer raises. It counts the self-leak and logs one warning:
`gap_blend_arm._walk_forward: 25000/47292 scored ticks (52.86 pct) self-leak
in fit_window='tick_date' mode; ...` and `gap_regime_arm.evaluate:
2867/6593 scored ticks (43.49 pct) self-leak in fit_window='tick_date' mode;
...` -- both numbers match the spec's original "before" leak measurement
exactly (25,000/47,292 and 2,867/6,593). `fit_window="game_first_date"` still
raises `AssertionError: fold games not disjoint (self-leak)` on a violating
fold -- unchanged, confirmed live (section 5b) via the `_check_disjoint` unit
tests and via `docs/evidence/harness/S36_repro_2026-09-04.py`'s original
traceback (section 5, still valid for the game_first_date claim only).

## 4. Test

`scripts/platformkit/ingame/test_gap_blend_arm.py` (6 tests, 3 pre-existing +
3 new) and `scripts/platformkit/ingame/test_gap_regime_arm.py` (5 tests, 2
pre-existing + 3 new) each now cover, on the same 4-tick midnight-spanning
fixture (game GA straddles 2026-01-01/02, GC is day-1 only, GB is day-2 only):
- `fit_window="game_first_date"` scores only GB, `self_leak_ticks == 0`.
- `fit_window="tick_date"` scores GA+GB (2 ticks), `self_leak_ticks == 1`,
  `self_leak_pct == 50.0` -- does NOT raise (the correction).
- `_check_disjoint({"GA"}, {"GA","GB"}, "game_first_date")` raises
  `AssertionError` on this constructed leaky set; the same call with
  `"tick_date"` returns `{"GA"}` without raising.

Commands and results (this box, 2026-09-04):
- `python -m pytest scripts/platformkit/ingame/test_gap_blend_arm.py -q` ->
  `6 passed in 1.17s`
- `python -m pytest scripts/platformkit/ingame/test_gap_regime_arm.py -q` ->
  `5 passed in 1.98s`
- `python -m pytest scripts/platformkit/eval_gate/test_stacker.py -q` ->
  `4 passed in 2.90s` (unchanged, default-mode behavior confirmed
  byte-identical -- this file never exercises `fit_window` or the leak count)
- `python -m pytest tests/platformkit/ingame/test_gap_arms_baseline_constants.py -q`
  -> `1 passed in 23.53s` (real-corpus baseline constants unaffected)

## 5. Reproduction (verifier: re-run this)

Script: `docs/evidence/harness/S36_repro_2026-09-04.py` (durable copy of the
measurement; loads the same corpus via `run_gap_arms_real_corpus._load_ticks`
+ `discover_store`, no ledger touch).
Summary JSON: `docs/evidence/harness/S36_repro_summary_2026-09-04.json`.

Command:
```
cd /c/Users/neelj/nba-track-a13 && PYTHONPATH=$(pwd) python docs/evidence/harness/S36_repro_2026-09-04.py
```
Output (2026-09-04, this box):
```
E4 game_first_date: n_ticks=47104 n_games=158 brier=0.206785778212713 leak_pct=0.00 (assert enforced)
E4 tick_date: AssertionError raised as expected: fold games not disjoint (self-leak)
E4 tick_date raised: True
E2 game_first_date: status=OK n_ticks=6579
E2 game_first_date: n_ticks=6579 brier=0.254350980569173 leak_pct=0.00 (assert enforced)
E2 tick_date: AssertionError raised as expected: fold games not disjoint (self-leak)
E2 tick_date raised: True
```
Traceback for section 3's ORIGINAL claim, now stale for `tick_date` (kept for
the game_first_date raise path, which is unchanged):
```
Traceback (most recent call last):
  File "<stdin>", line 7, in <module>
  File "C:\Users\neelj\nba-track-a13\scripts\platformkit\ingame\gap_blend_arm.py", line 96, in _walk_forward
    assert not (set(train["game"]) & set(test["game"]))
AssertionError: fold games not disjoint (self-leak)
```

## 5b. CORRECTION reproduction (verifier: re-run this)

Script: a scratch copy of section 5's script, adapted so the `tick_date`
branch reads the new counted fields instead of expecting a raise (the
original `S36_repro_2026-09-04.py` is left untouched as historical evidence
of the pre-correction, raise-in-both-modes proof). Same corpus load path
(`run_gap_arms_real_corpus._load_ticks` + `discover_store`), no ledger touch,
no module edit.

Command:
```
cd /c/Users/neelj/nba-track-a13 && PYTHONPATH=$(pwd) python <scratch>/S36_repro_correction_2026-09-04.py
```
Output (2026-09-04, this box):
```
gap_blend_arm._walk_forward: 25000/47292 scored ticks (52.86 pct) self-leak in fit_window='tick_date' mode; pass fit_window="game_first_date" to remove (S36)
gap_regime_arm.evaluate: 2867/6593 scored ticks (43.49 pct) self-leak in fit_window='tick_date' mode; pass fit_window="game_first_date" to remove (S36)
E4 game_first_date: n_ticks=47104 n_games=158 brier=0.206785778212713 self_leak_ticks=0 (assert enforced)
E4 tick_date: did NOT raise (S36 correction); n_ticks=47292 self_leak_ticks=25000 self_leak_pct=52.86
E2 game_first_date: status=OK n_ticks=6579
E2 game_first_date: n_ticks=6579 brier=0.254350980569173 self_leak_ticks=0 (assert enforced)
E2 tick_date: did NOT raise (S36 correction); status=OK n_ticks=6593 self_leak_ticks=2867 self_leak_pct=43.49
```
Confirms: (1) both `game_first_date` Briers are byte-identical to section 2 /
the spec target (0.206785778212713, 0.254350980569173); (2) the warning line
and the counted `self_leak_ticks`/`self_leak_pct` fields reproduce the
spec's original "before" leak measurement exactly -- e4 25,000/47,292 =
52.86 pct, e2 2,867/6,593 = 43.49 pct -- with no crash.

## 6. NOT VERIFIED

- Non-MLB corpora (soccer_intl) are not exercised by this change or this
  memo; `fit_window` is opt-in and the corpus loader path is MLB-only here.
- The e2 `min_n=200` per-regime bucket fitting was not re-tuned; game_first_date
  mode simply reuses the existing default.
- No re-run of `hedge_trial_arms.py`'s historical 2026-09-01 artifact under
  the new assert (it is a frozen artifact on disk, not re-executed by this
  gap; INSTRUMENT FIX ONLY, no charge).
- DM/PBO/deflated-p machinery in `s58_e2_slice_trial.py` was not re-run
  (would require a ledger charge, out of scope for an instrument fix).
- No render/eye-check applies (S-row; REPRODUCTION replaces it per Q7).
- CORRECTION pass (2026-09-04): `hedge_trial_arms.e4_blend_series`,
  `stacker.py main()`, `s58_e2_slice_trial.py main()`, and
  `hedge_trial_runner.e4_configs` were confirmed by code reading (reader
  table, section 1a) to call default `tick_date` mode, not actually
  re-executed end-to-end here -- this is still an INSTRUMENT FIX, no ledger
  charge, so their charged trial outputs were not regenerated.
  `hedge_trial_arms.e2_regime_series` bypasses `evaluate()`/`_check_disjoint`
  entirely (confirmed by code reading only); it carries no `self_leak`
  instrumentation and none was added to it.
- `s58_clamp_family_trial.py` and its per-file test
  (`tests/platformkit/eval_gate/test_s58_clamp_family_trial.py`) were not
  re-run this pass; its leak-free-by-construction classification in the
  reader table is by code reading only.

## Commit

Explicit pathspec, this worktree (track-a13), no push. SHA reported in the
lane summary.
