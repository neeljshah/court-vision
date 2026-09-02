# S87b -- the n / n_informative / n_eff triple ENFORCED on the in-game verdict writers

Date 2026-09-03 | lane S87 second half | tier WIRING (no charge, no seal, no prereg, no model
recomputed, no verdict recomputed, no bar touched)
Verdict **NOT VERIFIED** -- this memo is the lane's own report; every number below is reproduced
from a run or a test in this session, but no independent verifier has re-run them.
Calibration language only. Nothing here is a dollar, ROI or edge claim. No verdict changes.

The first half of S87 (memo `S87_tick_informative_2026-09-03.md`) built `flag_ticks` and re-quoted
three archived CIs. Its own honest limit was: "nothing in the scoring path calls them yet". That is
the half closed here.

## 0. STEP 0 -- the in-game verdict WRITERS on disk

Enumerated from `grep -rln "dm_ci\|deflated_p\|\"verdict\"" scripts/platformkit/eval_gate
scripts/platformkit/ingame` (231 files matched: `"verdict"` matches every gate artifact in the
tree), then narrowed to the writers that actually publish a Brier/DM confidence interval computed
from a per-unit paired-loss series. The narrowing grep is
`grep -rln "diebold_mariano" scripts/platformkit/eval_gate scripts/platformkit/ingame`.

| writer | grain | line that writes the artifact | wired |
|---|---|---|---|
| `scripts/platformkit/eval_gate/s58_clamp_family_trial.py` | tick | `:254` `Path(out_path).write_text(json.dumps(res, ...))` (+ series `:253`) | YES -- full triple |
| `scripts/platformkit/eval_gate/s58_e2_slice_trial.py` | tick | `:110` `Path(out_path).write_text(json.dumps(res, ...))` (+ series `:108`) | YES -- full triple |
| `scripts/platformkit/eval_gate/s80_player_grain_screen.py` | tick | `:258` `(out_dir / "%s%s.json").write_text(json.dumps(summary, ...))` | YES -- full triple |
| `scripts/platformkit/eval_gate/s84_nba_lineup_at_tick.py` | tick | `:281` `(out_dir / "%s%s.json").write_text(json.dumps(summary, ...))` | YES -- full triple |
| `scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py` | EVENT (one row per game at the halftime anchor) | `:145` `Path(out_path).write_text(json.dumps(res, ...))` (+ per-game csv `:141`) | YES -- `n_events`, with the note |
| `scripts/platformkit/eval_gate/s58_t2_first_trial.py` | EVENT (one row per soccer match) | `:175` `Path(str(out) + ".json").write_text(json.dumps(trial, ...))` (+ per-event csv `:164`) | YES -- `n_events`, with the note |
| `scripts/platformkit/eval_gate/s86_nba_every_tick.py` | tick | (lane S86's file) | ALREADY COMPLIANT, NOT TOUCHED |
| `scripts/platformkit/foundry/ingame_screen.py` | tick | (lane S82's file) | NOT TOUCHED -- another lane owns it |
| `scripts/platformkit/ingame/forward_evidence_scoreboard.py` | n/a | `:248` `tmp.write_text(json.dumps(doc, ...))` | NO -- see below |
| `scripts/platformkit/ingame/arm_evaluation.py` | n/a | `:37` `print(json.dumps(evaluate(rows)))` | NO -- see below |
| `scripts/platformkit/eval_gate/calibration_report.py` | pregame corpus rows | (S05 calibration report) | NO -- not an in-game tick CI |

Honest exclusions, each with the reason:

- `forward_evidence_scoreboard.py` computes NO CI and holds no loss series. It COMPOSES rows out of
  other gates' verdict JSONs (`tail_*`, enrichment) whose unit is a forward GAME count
  (`n_forward_games`), and its own docstring says "from existing verdict artifacts only". There is
  no tick frame to flag; whatever triple the source artifact carries is the triple.
- `arm_evaluation.py` (42 lines) is a shadow-eligibility gate: it counts cache/manifest rows and
  returns `verdict(None, None, 0, None, False)` -- no probabilities, no losses, no CI. The task
  named `ingame_calibration_report.py`; no such file exists (`ls scripts/platformkit/ingame | grep
  -i calib` -> `bucket_recalibration.py`, `exec_calibration.py`). The nearest real module is
  `eval_gate/calibration_report.py`, which scores the PREGAME cached gate corpora (S05), not
  in-game ticks.
- `s86_nba_every_tick.py` (lane S86, landed today) ALREADY writes `n_informative` beside its
  `n_eff` and `dm_ci95` (`:89`, `:157`). It is NOT edited here -- both because lane S86 owns it and
  because it is already at the bar. One honest difference to record: S86's `informative` flag is
  MARKET-MOVEMENT-ONLY (`:89`, `|market_prob - prev| > EPS`), while `flag_ticks` requires that
  NEITHER the market NOR the model moved before it calls a tick redundant. S86's rule is the
  stricter filter (it drops ticks where only the model moved); the two are not interchangeable and
  neither is retro-applied to the other.
- `foundry/ingame_screen.py` is lane S82's file this session and is untouched.

## 1. The change -- one shared helper, a few lines per writer

`scripts/platformkit/eval_gate/tick_informative.py` gains ONE public function (module now 276
lines):

    attach_informative_summary(artifact, frame, loss_col, *, game_col="game", ts_col="timestamp",
                               market_col="market", model_col="model", eps=EPS,
                               key="tick_informative") -> artifact

- It calls the EXISTING `flag_ticks` (nothing reimplemented) and writes the summary
  (`n`, `n_dup`, `n_held_market`, `n_held_model`, `n_held_both`, `n_informative`, `n_games`,
  `n_eff_icc`) into `artifact["tick_informative"]`, plus `n_games_informative` and the SECOND CI,
  `ci95_informative` (with `dm_p_informative` and `mean_loss_differential_informative`).
- It stably sorts by `(game, ts)` first, so a writer that scored in some other order still gets the
  per-game tick order `flag_ticks` requires. The input frame is not mutated.
- `ci95_informative` is `None` (with `ci95_informative_absent_because`) when the informative subset
  has fewer than two game clusters, because `diebold_mariano` requires two.
- `n_eff_icc` is `ingame.gap_effective_n.effective_sample_size` on the informative subset -- the
  same primitive the artifacts already quote; the ESS is not reimplemented.

Per-writer diff (143 insertions, 5 deletions across 10 files, of which 73 lines are tests):

| file | diff |
|---|---|
| `tick_informative.py` | +45 (the helper only) |
| `s80_player_grain_screen.py` | +3 (import + a 2-line call at the end of `score()`) |
| `s84_nba_lineup_at_tick.py` | +3 (same, `ts_col="ts"`) |
| `s58_clamp_family_trial.py` | +6/-1 (import; `return {` -> `res = {`; return the attached dict) |
| `s58_e2_slice_trial.py` | +7/-1 (same shape) |
| `s58_nba_halftime_asof_trial.py` | +5/-1 (event block: `grain`, `n_events`, `n_informative`, `n_eff`, note) |
| `s58_t2_first_trial.py` | +5/-1 (same event block) |

B2 ADDITIVE: every change ADDS a key. No column, status value or field was renamed or removed; the
published `dm` / `pooled` / `dm_vs_incumbent` blocks are byte-identical in shape and value.
B10 / Q3: no bar, threshold or alpha is read or written by this diff. No verdict is recomputed:
`verdict_of` / `dual_bar_verdict` / `replication_fields` are called exactly where and how they were.

A5 reader sweep:
`grep -rn "s80_player_grain\|s84_nba_lineup\|s58_trialA_clamp\|s58_trialB_nba_halftime\|s58_t2_first\|s58_e2_slice" --include=*.py scripts kernel api tests`
returns NO reader outside the writers themselves and their own tests, so no consumer can break on
an added key.

Event-grain note, written into both event artifacts verbatim: "S87: event grain -- one row per
game/match, so no tick can repeat the previous quote; the informative-tick filter does not apply and
n_events IS n_informative." This matches what the S87 re-quote already measured for trial B (1,593
-> 1,593, CI byte-identical).

## 2. Evidence that the fields appear -- the UNCHARGED S80 screen, re-run

`python -m scripts.platformkit.eval_gate.s80_player_grain_screen --no-rejoin`
(SCREEN tier: `_charge_ledger` is not imported by this module -- `grep -c` = 0.)

    embargo=1 SCREEN_NULL | n_ticks 2262 n_games 13 | e4 0.248435 -> 0.244812 (impr +0.003623) |
      market 0.244957 | dm p 0.8008 ci95 [-0.026976, 0.034222] clusters 13
    embargo=0 SCREEN_NULL | n_ticks 3707 n_games 23 | e4 0.223702 -> 0.229411 (impr -0.005709) |
      market 0.221055 | dm p 0.1158 ci95 [-0.012940, 0.001522] clusters 23

`data/cache/eval_gate/s80_player_grain_2026-09-03_s83.json` -> `tick_informative`:

    {"n": 2262, "n_dup": 0, "n_games": 13, "n_held_market": 1426, "n_held_model": 1381,
     "n_held_both": 1156, "n_informative": 1106, "n_games_informative": 13,
     "n_eff_icc": 62.557218376843984,
     "ci95_informative": [-0.03257587236612572, 0.03608119060844829],
     "dm_p_informative": 0.9132647493078896,
     "mean_loss_differential_informative": 0.0017526591211612888}

and the headline it sits BESIDE is unchanged: `verdict SCREEN_NULL`, `n_ticks 2262`,
`dm.ci95 [-0.02697626, 0.03422180]`.

`..._embargo0_s83.json`: `SCREEN_NULL`, n 3707, n_informative 1957, n_eff_icc 354.3171,
`ci95_informative [-0.011927, 0.002179]` beside the headline `[-0.012940, 0.001522]`.

INDEPENDENT CROSS-CHECK of the S87 first-half number (A2 in spirit): the S87 memo's re-quote read
the ARCHIVED S80 csv through the `requote` CLI and reported n_informative 1,106, n_eff 62.56,
ci95 [-0.032578, +0.036079]. This lane's number comes from a DIFFERENT code path -- the live writer
calling the helper on the frame it just scored -- and lands on n_informative 1,106,
n_eff_icc 62.5572, ci95_informative [-0.032576, +0.036081]. The two agree to 5-6 decimals.
(The row counts differ, 2,262 here vs 2,267 archived, and dup 0 vs 5, because `--no-rejoin` reads
identity off the S83 joined store; that is the S83 difference, not an S87 one.)

No verdict moved: both embargo arms are SCREEN_NULL before and after, exactly as they were.

## 3. Guard rails observed

- NO CHARGE: `data/cache/eval_gate/backtest_fwer.jsonl` is 18 rows, md5
  `a4ae7c13995672e478d59770591b83ba`, verified IDENTICAL before and after the S80 run.
  `_charge_ledger` was never called by this lane; the four charged S58 trials were NOT re-run
  (re-running them would charge), only wired.
- `data/registry/` untouched. No feature flag flipped. No forced-overwrite flag. No push.
- No edit to `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`.
- No edit to another lane's files: `foundry/ingame_screen.py` (S82), `s86_nba_every_tick.py` (S86),
  `family_bars.py` (S89), `hist_mlb_outcome_resolver` (S91) are all untouched.
- Q6: calibration language only; none of the retracted figures appears anywhere in this memo.
- Q1/Q2/Q4/Q5/Q9 are not engaged: nothing was scored under a seal, no K was read, no OOS claim is
  made. The one thing run (S80) is an uncharged SCREEN that already archives its per-tick series.

## 4. Tests (per-file only)

- `python -m pytest scripts/platformkit/eval_gate/test_tick_informative.py -q` -> **11 passed**
  (7 pre-existing + 4 new): the helper adds the triple without touching the headline and without
  mutating the input frame; the helper is ROW-ORDER-INDEPENDENT (a shuffled frame gives the same
  n_informative and the same `ci95_informative`); a single-cluster frame reports the triple with
  `ci95_informative: None` and a stated reason; and the S80 writer's own `score()` on a synthetic
  8-tick / 2-game frame returns `n 8, n_informative 5, n_held_market 3, n_dup 0`, a non-None
  `n_eff_icc`, a 2-element `ci95_informative`, and a headline `dm.ci95` that differs from it.
- Writer regressions, all re-run in master after the diff:
  `tests/platformkit/eval_gate/test_s58_clamp_family_trial.py -q` -> 6 passed (its
  seal->charge->score test now ALSO asserts the artifact carries `tick_informative` with
  `n == len(idxs)`, `0 < n_informative <= n`, a non-None `n_eff_icc` and a 2-element
  `ci95_informative` -- on a tmp_path ledger, so no real charge);
  `test_s58_e2_slice_trial.py` 2 passed; `test_s58_nba_halftime_asof_trial.py` 3 passed;
  `test_s58_t2_first_trial.py` 3 passed; `tests/platformkit/ingame/test_s80_player_grain_screen.py`
  5 passed; `tests/platformkit/ingame/test_s84_nba_lineup_at_tick.py` 4 passed.
  The three S58 seal/charge/score tests execute `run_trial` end to end on a tmp ledger, so the new
  code path IS exercised on all three of those charged writers even though the real trials were not
  re-run.

## 5. Honest limits (NOT VERIFIED)

- The four CHARGED artifacts already on disk (S58 trial A, trial 1b/e2, trial B, T2 #1) do NOT gain
  the field retroactively -- their JSONs were written before this diff and re-running them would
  charge the ledger. Their re-quoted informative numbers live in the S87 first-half artifact
  `data/cache/eval_gate/s87_requote_2026-09-03.json` instead. The wiring binds the NEXT run.
- `s84_nba_lineup_at_tick.py` was wired but NOT re-run (its corpus build is expensive and it is a
  SCREEN whose artifact is already on disk); its call is identical in shape to S80's and is
  compile-checked plus covered by the file's own 4 passing tests. The field is therefore PROVEN on
  S80 and only WIRED on S84.
- Wiring `s84` puts that file at 303 lines, 3 over the 300-line convention (235 files under
  `scripts/platformkit/` already exceed it). Recorded rather than hidden.
- "Informative" remains a market/model-MOVEMENT definition. A tick where the game state changed but
  neither probability moved is still counted redundant -- right for a paired loss comparison, wrong
  for a state-feature screen. S86's market-only variant is a different rule and both now coexist;
  unifying them is not done here.
- The bar says "every in-game verdict artifact". What is enforced is every in-game verdict writer
  that computes a DM CI from a paired-loss series and is not owned by another live lane. A future
  writer can still omit the triple: nothing MECHANICALLY refuses an artifact without it (no schema
  gate), which is the residual and the obvious next row.
