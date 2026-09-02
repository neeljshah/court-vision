# S106 -- the MLB in-game `game_id` holds more than one real game (PREMISE CONFIRMED, cause named, headline CIs re-quoted)

**NOT VERIFIED.** Written by the S106 lane, not by a verifier. Every number below is
reproducible from the modules and the on-disk stores named beside it; nothing here has been
re-derived by a second party. Calibration language only: no model was recomputed, no arm was
run, no prereg was sealed, no ledger row was charged, no K was read, no bar was moved, no
archived artifact was rewritten.

- Modules added (both new, additive, nothing edited):
  `scripts/platformkit/eval_gate/real_game_split.py` (182 lines),
  `scripts/platformkit/eval_gate/s106_requote.py` (165 lines).
- Test (per file only): `scripts/platformkit/eval_gate/test_real_game_split.py` -- **10 passed**.
- New artifact: `data/cache/eval_gate/s106_requote_2026-09-03.json` (gitignored, local).
- Nothing under `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/` or
  `data/registry/` was read or written. `backtest_fwer.jsonl` was never opened. Nothing was
  copied to the pod. The live joined store was NOT rebuilt.

## Verdict

**PREMISE CONFIRMED (Q8). The cause is CAPTURE-SIDE TICKER KEYING, not the join.** The
corrected cluster unit is built and the four headline CIs are re-quoted on it: **every
verdict is unchanged (NULL stays NULL, SCREENED stays SCREENED, none clears any bar), and
every CI moves.** The join-side column named in the register bar was **NOT** added -- see
"What was deliberately not done".

---

## STEP 0 -- premise, reproduced

| claim in the row | reproduced | value |
|---|---|---|
| 227 scored `game_id`s in `data/cache/ingame_grade_joined/mlb` | yes | 227 files |
| 78,986 scored ticks | yes | 78,986 |
| 144 of 227 span more than 6 h | yes | **144** |
| `KXMLBGAME-26JUL061915NYMATL` carries 07-05 / 07-06 / 07-07 ticks | yes | 497 / 35 / 151 |
| ... including inning 2 at 3-5 on 07-05 and inning 10 at 6-7 on 07-07 | yes | `2026-07-05T18:58:09Z home_score=3.0 away_score=5.0 inning=2`; `2026-07-07T02:56:46Z home_score=6.0 away_score=7.0 inning=10` |

The innings are **not** monotone and the span is **not** pre-game quoting of one game: that
ticker holds three separate first-pitch-to-final sequences (table below). The row is NOT
falsified.

## STEP 0 -- the cause: the ticker file itself, not the join

`ticker_settlement_join.join_ticker_file` is strictly **1:1** -- one raw ticker file in, one
joined file out, `_write_full` overwriting that one ticker's path (`ticker_settlement_join.py:167-222`).
It never merges two raw files. The defect is already present upstream in
`data/cache/ingame_grade/mlb/KXMLBGAME-26JUL061915NYMATL.jsonl`: **684 raw rows spanning
2026-07-05T00:22:38Z .. 2026-07-09T22:34:08Z**, the same three dates.

Of the raw MLB store, 235 files are ticker-keyed and 170 are ESPN-numeric-keyed;
**227 of the 231 non-empty ticker files span more than 6 h.**

The mechanism is named in the capture loop's own code: `inplay_capture_loop._process_game`
falls back to `_scan_live_by_legs(sport, legs, gid=gid, ...)` with the comment
`gid is a Kalshi ticker, not an ESPN id -> bridge to the live game by team`
(`scripts/platformkit/ingame/inplay_capture_loop.py:794-798`). The bridge matches on the
**team pair with no date check**, so any live NYM@ATL game is written under whichever
NYM@ATL ticker the market listing returned -- which S105 already measured as being 1-2 days
ahead for 79 pct of captured rows. **A ticker is not re-used by Kalshi; the capture re-uses
it.**

### Raw-store spans and inning sequences, 5 examples (evenly spaced over the >6 h set, A3)

| ticker | span | n | inning decreases | the decrease |
|---|---|---|---|---|
| `KXMLBGAME-26JUL011310TEXCLE` | 215.9 h | 558 | 1 | `07-01T00:11:09Z inn=7 sc=(2,3)` -> `07-01T17:09:16Z inn=1 sc=(0,0)` |
| `KXMLBGAME-26JUL052130BOSLAA` | 116.9 h | 218 | 1 | `07-05T04:08:36Z inn=9 sc=(1,8)` -> `07-06T01:34:56Z inn=1 sc=(0,0)` |
| `KXMLBGAME-26JUL102015ATLSTL` | 25.7 h | 205 | 0 | none -- one game plus trailing no-state quoting |
| `KXMLBGAME-26JUN251845PHIWSH` | 359.8 h | 871 | 0 | none -- 4 distinct states, almost all rows carry no inning at all |
| `KXMLBGAME-26JUN302140SFAZ` | 212.9 h | 190 | 0 | none -- one game plus trailing no-state quoting |

Both patterns are real and they are different failures: a long span is sometimes a second
real game (rows 1-2) and sometimes only stateless out-of-play quoting (rows 3-5). **The
6-hour span test over-counts.** That is why the split is done on state, not on span.

---

## The split (`real_game_split.assign_real_game_seq`, pure, no I/O)

Within one `game_id`, in tick order, a new real game starts at
(a) an **inning decrease** -- a return to inning 1 after inning >= 2 IS this case, so no
separate rule is reachable and none is implemented (the previous in-play tick of a segment
always carries the higher inning); (b) a **ts gap > 5 h** between consecutive in-play ticks;
(c) a **score reset to 0-0** after a non-zero score. A tick with no parsed inning never opens
or closes a segment -- it inherits the current `real_game_seq` (contract B3: missing is not
bad). Returns the frame plus `{n_game_ids, n_real_games, n_multi, n_ticks,
n_ticks_reassigned, gap_hours, boundary_reasons}`.

### On the whole joined MLB store

| quantity | value |
|---|---|
| `game_id`s | 227 |
| **real games** | **392** |
| `game_id`s holding more than one real game | **122** |
| ticks | 78,986 |
| ticks reassigned (landing in seq >= 2) | **22,768 (28.8 pct)** |
| boundary reasons | `inning_decrease` 156, `score_reset` 6, `ts_gap` 3 |

Real games per `game_id`: 1 -> 105, 2 -> 86, 3 -> 30, 4 -> 5, 5 -> 1.

**The 6-hour span and the split disagree in both directions, and the split is the honest
number:** 144 span > 6 h, 122 are multi; 31 span > 6 h but hold one real game (trailing
stateless quoting), and 9 hold two real games inside 6 h (a day/night doubleheader).

`KXMLBGAME-26JUL061915NYMATL`, 683 joined ticks, splits into three:

| seq | first tick | last tick | ticks |
|---|---|---|---|
| 1 | 2026-07-05T00:22:38Z | 2026-07-05T03:15:00Z | 157 |
| 2 | 2026-07-05T16:22:53Z | 2026-07-05T21:22:19Z | 340 |
| 3 | 2026-07-06T23:15:09Z | 2026-07-07T02:57:55Z | 186 |

Seq 3 opens at 23:15Z = **19:15 ET, exactly the first pitch the ticker name encodes**. Only
186 of 683 ticks (27.2 pct) under that `game_id` belong to the game it names.

---

## RE-QUOTE on corrected clusters (no model recomputed)

`s106_requote.py` reads the archived per-tick series as written, attaches `real_game_seq` by
`(game_id, ts)` from the joined store, and re-runs the **same** quote S87 published --
`dm_test.diebold_mariano` + `gap_effective_n.effective_sample_size` via
`tick_informative._quote` -- with `cluster = game_id#real_game_seq` instead of `game_id`.
Only the cluster label changes: `n`, `y`, and every probability column are untouched, and
`mean_loss_differential` is therefore **identical before and after** in all four rows (it is
the same rows, differently grouped). Join coverage: **0 unmatched ticks** in all four series.

Each published CI is reproduced from its own series CSV to < 1e-9 **before** the new CI is
read: `published_ci_reproduced_from_series = true` in all four.

| artifact | n | n_games before -> after | rho | n_eff before -> after | DM CI95 before | DM CI95 after | published verdict | changes? |
|---|---|---|---|---|---|---|---|---|
| S82 `tick_index_in_game` | 15,702 | **41 -> 88** | 0.189 -> 0.727 | 214.83 -> **120.72** | [-0.001971, 0.008636] | [-0.003705, 0.010370] | SCREENED, bar 0.004 not cleared | **no** |
| S82 `leverage_proxy` | 15,702 | **41 -> 88** | 0.093 -> 0.212 | 432.01 -> **406.68** | [-0.000106, 0.002403] | [-0.000219, 0.002515] | SCREENED, not cleared | **no** |
| S82 `times_through_order` | 15,702 | **41 -> 88** | 0.035 -> 0.058 | 1081.97 -> **1399.76** | [-0.000770, 0.002897] | [-0.000728, 0.002854] | SCREENED, not cleared | **no** |
| S87 trial A `s58_trialA_clamp` | 47,104 | **158 -> 315** | 0.277 -> 0.550 | 566.18 -> **569.67** | [-0.000364, 0.002096] | [-0.000212, 0.001944] | NULL | **no** |

DM p: 0.2115 -> 0.3492, 0.0718 -> 0.0987, 0.2482 -> 0.2414, 0.1662 -> 0.1149. **Every CI
still contains zero on both sides.** No verdict flips; NULL stays NULL and no SCREENED
feature reaches its 0.004 bar under either clustering.

Two things are worth saying plainly:

1. **The corrected game count is roughly double** (S82 41 -> 88 real games, S87 trial A
   158 -> 315). Every published MLB in-game "n games" is understated by about 2x, which is
   the honest correction this row was opened for.
2. **More clusters did not buy precision.** The within-cluster correlation *rises* on the
   two rows whose clusters actually split a real boundary (0.189 -> 0.727, 0.277 -> 0.550),
   because the corrected clusters are shorter and more internally homogeneous, so `n_eff`
   *falls* for `tick_index_in_game` (214.8 -> 120.7) and its CI **widens**. The corrected
   number is the smaller effective sample, not the larger one. Nothing here makes any
   in-game comparison look better than it was published as.

---

## What was deliberately not done

- **`ticker_settlement_join` was NOT given a `real_game_seq` column.** The build step was
  conditioned on the cause being in the join; it is not -- the join is a faithful 1:1 copy
  and the defect is capture-side. Adding the column there would also push that file past the
  300-LOC cap (it is exactly 300 lines today). Consumers that need the corrected unit should
  call `real_game_split.assign_real_game_seq`, which is what `s106_requote.py` does.
- **The live store was NOT rebuilt** and the capture path was NOT changed. The durable fix
  is a date check in the ticker bridge (`inplay_capture_loop._scan_live_by_legs`) so a live
  game cannot be written under a ticker whose encoded first pitch is a different day -- a
  capture-side change, a separate row, and one that cannot repair the 22,768 ticks already
  on disk.
- **No bar was re-run.** S82's 0.004 screen bar and every multiplicity bar are quoted from
  the archived artifacts unchanged; a blocked verdict stays blocked.

## Contract self-check (B and Q)

- **B1** no circular metric: the re-quote uses **every** row of each archived series (n
  identical before and after, 15,702 / 47,104); nothing is excluded, so no row set can be
  chosen to make a CI pass. The one set that is named and counted rather than dropped is
  ticks with no parsed inning -- they inherit their segment, never their own cluster.
- **B2** additive schema: two NEW modules; no existing column, status value or field was
  renamed or removed and no existing file was edited. A5 sweep on `real_game_seq`: `grep -rn
  "real_game_seq" scripts/ docs/` returns only the two new modules, their test and this memo
  -- zero pre-existing readers to break.
- **B3** no fall-through loss: an unparseable state, an unparseable timestamp and a series
  row absent from the joined store are all KEPT (seq 1, own cluster), never quarantined.
- **B5** no pre-verification deploy: nothing was copied to the pod; no pod command was run at
  all in this lane.
- **B6** no orphans: nothing was moved or retired.
- **B7** no head slices: the split walks all 227 joined files and all 78,986 ticks; the raw
  5-example table is sampled evenly across the sorted >6 h set (indices 0, n/4, n/2, 3n/4,
  n-1), not from the head; the re-quote uses every row of every series.
- **B8** no self-fit as independent: nothing is fit here at all -- the archived probabilities
  are read as written.
- **B9** no degenerate denominator: both the tick count and the cluster count are printed for
  every cell, and `rho` / `design_effect` / `n_eff` are printed beside them so a cluster
  count cannot be read as an effective sample size. The corrected unit is *smaller* in
  effective terms for two of the four rows, and that is reported.
- **B10** no bar moved: S82's 0.004 bar, the 5 h gap default and every published CI are
  byte-identical to master; the split's `gap_hours` is a keyword argument with the row's own
  5 h default, and the test asserts it is a knob, not a silently changed constant.
- **Q1/Q2** no seal, no charge, no K read -- this is an uncharged re-quote of already-published
  CIs. `data/cache/eval_gate/backtest_fwer.jsonl` was never opened; `_charge_ledger` was never
  called.
- **Q3** no threshold moved; the 0.004 screen bar is quoted unchanged and reported as not
  cleared under either clustering.
- **Q4** leak contract untouched: no model, fold, embargo or walk-forward was recomputed --
  the archived per-tick paired losses are the input, and only the grouping label changes.
- **Q5** no AHEAD is claimed; every row here is NULL / SCREENED-not-cleared, single-corpus
  (one venue, one sport, `ingame_grade_joined/mlb`), and labelled as such.
- **Q6** calibration language only: no dollar, ROI, profit or edge language; no retracted
  figure appears anywhere in this memo or in `s106_requote_2026-09-03.json`.
- **Q7** the split rules are a CONSTRUCT enumeration (three boundary rules, exhaustive over
  the state fields the store carries), and the re-quote is a REPRODUCTION (A2): every
  published CI is reproduced to < 1e-9 before its replacement is read.
- **Q8** premise re-measured first and CONFIRMED, with the row's own two candidate causes
  discriminated: it is the ticker keying in the raw capture store, not the join.
- **Q9** the differential is archived: `s106_requote_2026-09-03.json` carries, per artifact,
  the full before/after quote (n, n_games, rho, design_effect, n_eff, mean_loss_differential,
  dm_stat, dm_p, dm_ci95), the series CSV it was computed from, the published CI and whether
  it reproduced -- so both CIs are recomputable from the artifact and the archived series
  alone.

## Reproduce

```
python -m pytest scripts/platformkit/eval_gate/test_real_game_split.py -q
python -m scripts.platformkit.eval_gate.real_game_split          # demo self-check
python -m scripts.platformkit.eval_gate.s106_requote             # writes s106_requote_2026-09-03.json
```
