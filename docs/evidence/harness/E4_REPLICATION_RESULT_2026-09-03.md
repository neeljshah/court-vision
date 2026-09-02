# E4 replication on a disjoint MLB corpus -- INSUFFICIENT (step 0 stopped the lane)

Lane R (main repo), 2026-09-03. Verdict: **INSUFFICIENT -- no charged trial ran.**
Nothing was charged: `data/cache/eval_gate/backtest_fwer.jsonl` still has 14 rows
(k_cumulative 14, last row `scripts.platformkit.eval_gate.stacker:mlb_stack_v1`
at 2026-09-02T05:42:37Z). No prereg was sealed, no module was written, no bar was
moved. Pod was read-only throughout (ssh reads + one `tar -cz` pull; nothing
killed, started, or written there). Calibration language only.

The lane's own STOP rule fired: the prereg n rule requires a disjoint scored set
of >= 30 games. The measured disjoint scored set is **0 games**.

## Q8 premise re-measure: the launch premise is FALSIFIED

The row was dispatched on the premise "the pod has been capturing live MLB ticks
since 2026-08-31 ... paired rows only since 05:28Z 2026-09-02 -- the S32 fix".
Measured today: **the S32 blocker is still in force and no paired row has ever
been written.** Pod heartbeat `data/cache/ingame_grade/_capture_heartbeat.json`
as_of 2026-09-02T14:44:43Z reads `n_live: 0, n_pairs: 0, n_settled: 0` with
`grade_write_fail_by_reason: {"no_live_state": 95}` -- 95 of 95 scheduled games
(24 mlb, 66 tennis, 5 kbo) failed to write a graded row. The capture runner is
alive (`/usr/local/bin/python -u -m scripts.platformkit.ingame.inplay_capture_runner`,
pid 19598, 36m uptime at read time) -- it is running and producing nothing pairable,
which is exactly the S32 diagnosis (`docs/evidence/harness/S32_pairing_bridge_2026-09-03.md`:
`data/domains/mlb/games.parquet` absent on the pod -> `MLBPredictor.__init__`
raises -> `active_sports() == []` -> no `latest.json` -> `p0=None` -> `_process_game`
exits before `capture_pair_once`).

A falsified premise is a valid result (contract Q8). The row closes on the
measurement, not on a fix.

## Inventory (every count reproduced on this box today)

Store shape required by `scripts/platformkit/ingame/run_gap_arms_real_corpus.py
_load_ticks` -> `wp_diag_series.load_records` -> `ingame_replay_scoreboard._normalise`:
a row is usable only with a model probability, a settled binary `outcome`
(`_OUTCOME_KEYS = outcome | settled_outcome | result | label`), a game id and a
timestamp; "paired" additionally needs `market_prob`.

| store | rows | usable (model + settled outcome) | paired (+market) | games | date range |
|---|---|---|---|---|---|
| `data/cache/ingame_grade_joined/mlb` (window 1) | 78,986 | 78,986 | 78,986 | 227 | 2026-06-20..2026-07-12 |
| `data/cache/ingame_grade_joined/mlb_clean` (clone) | 78,986 | 78,986 | 78,986 | 227 | 2026-06-20..2026-07-12 |
| pod `data/cache/ingame_grade_joined/mlb` | 78,986 | 78,986 | 78,986 | 227 | 2026-06-20..2026-07-12 |
| local `data/cache/ingame_grade/mlb` (raw capture) | 79,566 | **0** | **0** | 401 | 2026-06-19..2026-09-01 |
| pod `data/cache/ingame_grade/mlb` (pulled today) | **27** | **0** | **0** | 27 | 2026-09-01..2026-09-02 |
| `data/cache/ingame_grade/_quarantine_wrongdate` | 324 | 0 | 0 | 9 | 2026-07-10 |

Window 1 as scored by `_load_ticks` (after dedupe on `(game, timestamp)` and
`drop_unparsed`): 178 games / 52,558 ticks / 2026-06-28..2026-07-12 -- the S06
pre-flight figure, unchanged.

The pod's joined store is scope-identical to the local one (227 games, same date
range): the pod holds **no** MLB material outside window 1.

All 27 pod rows are single-line settlement stubs of the form
`{"sport":"mlb","game_id":"401878657","ts":"2026-09-01T00:33:52Z","settled":true,
"home_win":0.0,"state_summary":"FINAL", ...}` -- one row per game,
no model probability, no market probability, no in-game state, and `home_win` is
not an `_OUTCOME_KEYS` name. They are settle labels with nothing to label.

### The disjoint candidate set, game by game

Games in the local raw store whose FIRST tick date is after 2026-07-12 (the
window-1 end, so disjointness is guaranteed by construction): **33**.

- with any paired (model + market) tick: **4**
- with >= 20 paired ticks: **4**
- with >= 20 paired ticks carrying full state (`outs=`/`base=` present, i.e.
  parseable by `mlb_state_features`): **4**
- **with a settled outcome: 0**
- total paired ticks across all 33: 180

First-date histogram of the 33: 2026-07-15 (2), 07-17 (1), 07-18 (11), 07-19 (6),
07-27 (1), 09-01 (12). The 12 on 09-01 are the settlement stubs above.

**Disjoint scored set = 0 games / 0 ticks.** 0 < 30, so the trial is INSUFFICIENT
by the prereg's own n rule. Even if an outcome join from ESPN box scores were run
(the mechanism window 1 used, `close_source: ingame_outcome_label:espn_boxscores_parquet`),
the ceiling is the 4 games that carry paired ticks -- still 0 < 4 < 30.

## When the count reaches 30

**At the observed accrual rate it never does.** Between the capture runner's boot
(2026-08-31T19:53:47Z, per the S32 boot-beat) and the pod heartbeat
(2026-09-02T14:44:43Z) -- 1.79 days -- the disjoint scored set accrued
**0 games**, an observed rate of **0.00 games/day**. No finite date exists at that
rate; quoting one would be a fabrication.

The honest conditional, stated as such: window 1 accrued 178 scored games over
2026-06-28..2026-07-12 (15 days) = 11.87 scored games/day while the model ->
capture -> settle chain was intact. If the named blocker (`data/domains/mlb/games.parquet`
absent on the pod) clears on date D and that historical rate resumes, the 30-game
floor is reached at **D + 2.53 days, i.e. D + 3 days**, plus one settle-label pass.
This is a projection conditional on a fix that has not happened, not a forecast.

## What this does and does not say about e4_blend

Nothing changes for e4_blend. Its verdict stays exactly as the S06 result left it:
**SINGLE-WINDOW** (contract Q5), because the second corpus does not exist yet. The
leak-free GAME-FIRST-DATE variant's window-1 figure (Brier 0.206785778212713 on
47,104 paired ticks, S06 pre-flight section 3) is untouched and is not re-quoted
here as anything new. No AHEAD, no TWO-CORPORA label, no promotion.

## NOT VERIFIED

- Whether an ESPN box-score outcome join would in fact settle the 4 paired-tick
  games (not attempted; the ceiling of 4 makes it moot for the n rule).
- Any pod store other than `ingame_grade/mlb`, `ingame_grade_joined/mlb` and the
  cache root listing (`ingame_books`, `inplay_history`, `line_history` were not
  inventoried for MLB paired ticks).
- Soccer/tennis/kbo corpora as alternative second corpora for e4 (out of scope:
  e4_blend's arm is MLB-specific).
- The 09-01/09-02 settlement stubs' correctness as labels (they were not joined
  to anything).
- No DM CI, deflated p, ESS or replication_verdict was computed -- there was no
  scored set to compute them on.
