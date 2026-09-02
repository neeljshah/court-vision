# S82 -- the signal factory's in-game screen tier (MLB ticks)

Date: 2026-09-03 | Area: signals-ingame | Verdict: **SCREEN_NULL -- 0 of 14 features clear the +0.004 bar**
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked below).
Calibration language only. An uncharged screen is a NON-FINDING; no prereg sealed, no K consumed.

---

## 0. Premise (Q8) -- re-measured first, CONFIRMED with one correction

**The row's claim:** the grammar's in-game families are refused by the pregame leak contract, so
in-game state features are never screened.

**Measured at HEAD** (`scripts/platformkit/eval_gate/family_bars.load_families` +
`scripts/platformkit/foundry/screen_predictor.check_feature_name`, no corpus columns supplied):

| family | sport | features | hypotheses |
|---|---|---|---|
| mlb_atbat_states | mlb | 10 | 90 |
| mlb_pitch_states | mlb | 16 | 144 |
| mlb_states | mlb | 8 | 72 |
| nba_pbp_foul_states | nba | 9 | 81 |
| nba_pbp_states | nba | 6 | 54 |
| nba_possession_states | nba | 13 | 117 |
| soccer_cardstates | soccer | 7 | 63 |
| soccer_shotstates | soccer | 5 | 45 |
| soccer_shotxgstates | soccer | 5 | 45 |
| soccer_states | soccer | 7 | 63 |
| tennis_states | tennis | 5 | 45 |
| **11 families** | | **91 (46 distinct columns)** | **819** |

**All 46 distinct member columns are refused, 46 of 46.** The exact refusal line, verbatim from
`ScreenRefused`, one example per shape:

```
outs                     leaky: outs is a same-game column
state_diff               leaky: state_diff is a same-game column
count_balls              leaky: count_balls is a same-game column
seconds_remaining        leaky: seconds_remaining is a same-game column
base_run_value           leaky: base_run_value is a same-game column
```

Every one is `leaky: <col> is a same-game column` -- the first branch of `check_feature_name`,
raised against `LEAKY_NAMES`, before any value is read. So **819 of the factory's 3,564
enumerated hypotheses (23.0 pct) are unscreenable by construction**, and the entire `live_tick`
horizon has zero screens. Premise CONFIRMED.

**Correction to the premise, in the row's own spirit:** an in-game screen exists ELSEWHERE --
`scripts/platformkit/eval_gate/s80_player_grain_screen.py` (S80) screens ONE player-grain
feature on these same ticks with its own as-of guard, purge and embargo. It screens no grammar
family member and is not a factory tier, so S82 is not FALSIFIED; but this row is **not** the
first in-game screen in the repo and does not claim to be. What did not exist, and now does, is
an in-game TIER of the factory that takes the grammar's own `live_tick` columns as hypotheses.

**Tick corpora on disk, per sport** (raw line counts read off `data/cache/ingame_grade*`):

| store / sport | rows | with settled outcome | with market in-play line | games | dates | usable? |
|---|---|---|---|---|---|---|
| `ingame_grade_joined/mlb` | 78,986 | 78,986 | 78,986 | 227 | 2026-06-20..07-12 | **YES** |
| `ingame_grade_joined/soccer_intl` | 9,003 | 9,003 | 9,003 | 51 | 2026-06-22..07-12 | line yes, state no |
| `ingame_grade/nba` | 2 | 0 | 1 | 2 | 2026-07-05..07-18 | no |
| `ingame_grade/tennis` | 1,255 | 0 | 18 | 1,238 | 2026-07-04..09-01 | no |
| `ingame_grade/wnba` | 280 | 0 | 280 | 3 | 2026-07-19 | no |

- **MLB**: after the canonical loader's de-duplication and state parse, 52,558 ticks / 178 games;
  after the incumbent `e4_gd` walk-forward, **47,104 scored ticks / 158 games** -- byte-identical
  to the S58 denominator `SCORED = (47104, 158)`, and `brier(e4_gd) = 0.206785778212713`
  reproduces `s58_clamp_family_trial.REPRO_INCUMBENT` to the last digit.
- **soccer_intl**: 6,649 ticks / 41 games carry model, market and outcome, but the only state
  feature the loader can build is `score_diff` (3,639 parsed) -- and `score_diff` IS the e4
  blend's own signal. There is no ADDITIONAL in-game state feature to screen, so soccer is
  reported and skipped, not screened.
- **NBA / tennis / WNBA**: **no tick corpus with a settled outcome exists.** Tennis has 18 priced
  rows out of 1,255. Stated per sport as the row asked; the screen runs on MLB only.

---

## 1. The contract this tier enforces

Written as the module docstring of `scripts/platformkit/foundry/ingame_screen.py` and enforced
in code:

> A hypothesis is ONE state feature `x(g, t)` whose value at tick time `t` of game `g` is a
> function of events of `g` with timestamp `<= t` ONLY, plus pregame as-of tables. Reading any
> event later than the tick's own is a leak.

**Enforcement is truncation invariance, not an assertion.** `assert_tick_asof` rebuilds the whole
feature table from the causal prefix `src[:k+1]` and requires row `k` to equal row `k` of the
full build. A feature that peeks at a later tick changes under truncation and raises
`TickTimeLeak`. On the real corpus it passed at 8 EVENLY spaced probes (A3, never a head slice):
rows 5839, 11678, 17517, 23356, 29195, 35034, 40873, 46712 of 52,558.

This is the tier's leak rule, **tick-time as-of, not game as-of** -- which is exactly why the
pregame `check_feature_name` refusal does not apply here and is not weakened: nothing in
`screen_predictor.py` was edited, and `LEAKY_NAMES` is byte-identical to master (B2/B10).

**Purge and embargo.** Folds are GAME-FIRST-DATE (S36: arm series self-leak across UTC midnight,
so game-first-date variants only). The purge is on the game's **settlement**, not its first date:
this store quotes a Kalshi game market up to ~2 days before first pitch, so a game whose first
date is earlier can still be ticking during the fold (measured: `KXMLBGAME-26JUL021235PITPHI`
spans 2026-06-30T22:43Z .. 2026-07-02T19:28Z, 44.75 h). A train game must have produced its LAST
tick at least 1 day before the fold's first tick, and `train.ts.max() < test.ts.min()` is
asserted per fold. That is STRICTER than the incumbent's own fold rule, so the candidate always
trains on less than the incumbent did -- conservative, never the other way.

**The two arms differ only by the feature.** `[1, logit(p_e4_gd)]` alone re-calibrates the
incumbent, and that gain is not the feature's. So each fold fits BOTH `null = [1, logit(p_e4)]`
and `candidate = [1, logit(p_e4), z(x)]` on exactly the same rows, and **the bar is applied to
`improvement_vs_null`**. Scoring against raw `e4_gd` instead would have credited every one of the
14 features with the same ~+0.0065 recalibration gain -- the first run of this lane did exactly
that and is retained here as the cautionary note, not as a result.

**Partition (SF-1).** Ticks are not in the foundry hash partition, so this uses the spec's
game-first-date **ISO-week** rule via `tiers.partition_corpus(seed=0)`, basis `iso_week`, over
the 158 SCORED games. SCREEN side = 2026-W27, 72 games, 28,886 ticks, sha256
`79f90ff9eed18ae67929293ed50d474d099c2e19d7fbdd1a75f3cee710486269`. VERDICT side = 2026-W28,
86 games, sha256 `d8953537a6c8f91676170370954aa8a36afee48fd86b522e106eab69a0179e4e` -- **never
read by this lane.** Of the 28,886 screen ticks, 15,702 over 41 games are scored: the first two
screen dates have no settled+embargoed train set and are recorded `NO_TRAIN`, not scored.

---

## 2. Ranked table -- MLB, SCREEN side, n = 15,702 ticks / 41 games each

`brier_market` = the in-play market line at tick time = **0.195704** for every row (same rows).
`brier_e4` = the incumbent `e4_gd` = **0.208211**. `improvement` is vs the null (the same
walk-forward fit without the feature term); the CI is the game-clustered Diebold-Mariano 95 pct.

| rank | feature (tick corpus) | grammar member | n_ticks | n_games | brier e4 | brier null | brier e4+feature | brier market | improvement vs null | DM 95 pct CI | p | coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | tick_index_in_game | asof_idx | 15,702 | 41 | 0.208211 | 0.201650 | 0.198318 | 0.195704 | +0.003332 | [-0.001971, +0.008636] | 0.211 | 1.000 |
| 2 | leverage_proxy | leverage_state | 15,702 | 41 | 0.208211 | 0.201733 | 0.200585 | 0.195704 | +0.001148 | [-0.000106, +0.002403] | 0.072 | 0.979 |
| 3 | times_through_order | times_through_order | 15,702 | 41 | 0.208211 | 0.201485 | 0.200422 | 0.195704 | +0.001063 | [-0.000770, +0.002897] | 0.248 | 0.869 |
| 4 | pitch_tempo_seconds | pitch_tempo | 15,702 | 41 | 0.208211 | 0.201650 | 0.200999 | 0.195704 | +0.000651 | [-0.001025, +0.002327] | 0.437 | 1.000 |
| 5 | pitch_count | sp_pitch_count_prior | 15,702 | 41 | 0.208211 | 0.201485 | 0.200873 | 0.195704 | +0.000612 | [-0.000550, +0.001773] | 0.293 | 0.869 |
| 6 | balls | count_balls | 15,702 | 41 | 0.208211 | 0.201671 | 0.201468 | 0.195704 | +0.000203 | [-0.000218, +0.000624] | 0.336 | 0.998 |
| 7 | strikes | count_strikes | 15,702 | 41 | 0.208211 | 0.201671 | 0.201666 | 0.195704 | +0.000005 | [-0.000228, +0.000238] | 0.968 | 0.998 |
| 8 | outs | outs | 15,702 | 41 | 0.208211 | 0.201671 | 0.201681 | 0.195704 | -0.000010 | [-0.000251, +0.000231] | 0.932 | 0.998 |
| 9 | score_change_recency | score_change_recency | 15,702 | 41 | 0.208211 | 0.201650 | 0.201891 | 0.195704 | -0.000241 | [-0.000540, +0.000058] | 0.112 | 1.000 |
| 10 | inning_progress | frac_elapsed | 15,702 | 41 | 0.208211 | 0.201733 | 0.202002 | 0.195704 | -0.000268 | [-0.001334, +0.000798] | 0.614 | 0.979 |
| 11 | base_out_state | base_out_known | 15,702 | 41 | 0.208211 | 0.201671 | 0.201985 | 0.195704 | -0.000315 | [-0.000977, +0.000348] | 0.343 | 0.998 |
| 12 | run_expectancy | base_run_value | 15,702 | 41 | 0.208211 | 0.201671 | 0.202109 | 0.195704 | -0.000438 | [-0.001269, +0.000392] | 0.293 | 0.998 |
| 13 | base_state | runners | 15,702 | 41 | 0.208211 | 0.201671 | 0.202149 | 0.195704 | -0.000479 | [-0.001229, +0.000272] | 0.205 | 0.998 |
| 14 | score_diff | state_diff | 15,702 | 41 | 0.208211 | 0.201650 | 0.219657 | 0.195704 | -0.018007 | [-0.039827, +0.003814] | 0.103 | 1.000 |

**Bar: +0.004 (frozen, the S58 in-game bar; not moved -- B10/Q3). Clearing it: 0 of 14.**
No feature has a CI whose lower end is above 0 either.

**Phase coverage of the scored screen ticks** (inning bucket, so the result is not a slice of one
game phase): inning 1: 2,498 | 2: 1,864 | 3: 2,162 | 4: 1,733 | 5: 1,639 | 6: 1,620 | 7: 1,718 |
8: 1,395 | 9: 670 | 10: 20.

**Fold table** (identical across features; `n_train` is the settled+embargoed train set):

| fold date | status | n_train ticks | n_train games | n_test ticks | feature coverage on test |
|---|---|---|---|---|---|
| 2026-07-01 | NO_TRAIN | 0 | - | - | - |
| 2026-07-02 | NO_TRAIN | 0 | - | - | - |
| 2026-07-03 | OK | 6,064 | 18 | 6,033 | 0.9985 |
| 2026-07-04 | OK | 11,636 | 28 | 7,972 | 0.9981 |
| 2026-07-05 | OK | 14,106 | 34 | 1,697 | 0.9965 |

**Member accounting.** The 11 `live_tick` families name **46 distinct columns**. **17** of them
belong to the three MLB families; **10 of those 17 are screened above** (`asof_idx`,
`base_out_known`, `base_run_value`, `count_balls`, `count_strikes`, `frac_elapsed`, `outs`,
`runners`, `sp_pitch_count_prior`, `state_diff`). The other **7 MLB members are NOT SUPPLIED** by
this tick corpus, named and never silently dropped: `pitch_velocity`, `pitch_loc_x`,
`pitch_loc_y`, `velo_decline_vs_early`, `atbat_pitch_number` (Statcast pitch grain -- the store
carries the starter's cumulative count, not the at-bat pitch number), `p0` (the pregame prior,
already inside `model_prob`) and `outcome` (the label, never a feature). The remaining **29
columns belong to the NBA / soccer / tennis families**, whose sports have no scorable tick
corpus (section 0).

Four of the fourteen rows are NOT grammar members but state columns the S82 row asked for by
name, supplied by the tick corpus and screened alongside: `leverage_proxy` (the "leverage-index-
like state"), `times_through_order`, `pitch_tempo_seconds` and `score_change_recency`. They are
labelled in the table's `grammar member` column with their own names, not borrowed ones. The
row's `bullpen usage as-of` ask has **no column in this corpus at all** and is reported as
NOT_SUPPLIED rather than proxied.

---

## 3. Honest verdict

**SCREEN_NULL.** Zero of the fourteen in-game state features the MLB tick corpus can supply adds
a measurable calibration improvement to the e4 blend once the arms are made to differ only by
the feature. The largest, `tick_index_in_game` at +0.003332, is below the +0.004 bar and its
95 pct CI spans zero. The second, `leverage_proxy` at +0.001148 (p 0.072), is the only row whose
CI comes close to excluding zero and it is a quarter of the bar.

Three things this measures that are worth stating plainly:

1. **The e4 blend already contains the score state.** `score_diff` -- e4's own signal -- is the
   worst feature at -0.018007 when re-added as a second, unguarded logistic term. That is a
   sanity anchor: the instrument can detect a degenerate hypothesis.
2. **A pure walk-forward recalibration of the incumbent is worth more than any of the features**:
   null vs raw `e4_gd` is +0.006540, CI [-0.008751, +0.021831], p 0.392. It is not statistically
   separated either, and it is a recalibration, not a signal -- named here so nobody reads the
   `improvement_vs_e4` column as a feature result.
3. **The in-play market line is still ahead of both.** Market 0.195704 vs null 0.201671: the null
   trails the line by 0.005966, CI [-0.036891, +0.024958], p 0.699. Matching the in-play line
   within noise is the honest description; nothing here beats it.

**No prereg draft is written.** The row conditions a draft on the best feature clearing +0.004;
nothing does, so drafting one would be a bar moved by another name.

---

## 4. Artifacts and reproduction

- Code: `scripts/platformkit/foundry/ingame_screen.py` (286 LOC),
  `scripts/platformkit/foundry/run_ingame_screen.py` (45 LOC, the CLI; split out only to keep the
  first file under the 300-LOC rail).
- Run: `python -m scripts.platformkit.foundry.run_ingame_screen`
- Summary: `data/cache/eval_gate/s82_ingame_screen_2026-09-03.json` (41,521 bytes) -- per-feature
  metrics, every fold's coefficients / mu / sd, both partition sha256s, the not-supplied list.
- **Q9 differential**: `data/cache/eval_gate/s82_ingame_screen_series_2026-09-03.csv`
  (33,376,960 bytes; 14 features x 15,702 ticks = 219,828 rows) with `feature, tick_index, game,
  timestamp, y, p_e4, p_null, p_candidate, market, x`. Every summary row was recomputed from this
  CSV alone and reproduces the JSON to **1e-12** on `brier_e4`, `brier_candidate`,
  `improvement_vs_null` and the DM CI bounds (A2).
- Test: `python -m pytest tests/platformkit/foundry/test_ingame_screen.py -q` = **6 passed in
  2.39s** -- the as-of guard passes on the real builder and RAISES on a planted feature that
  reads the next tick; the settlement purge drops a game still ticking during the fold
  (`n_train_games == 1`, not 2) while game-first-date alone would have kept it; a fold with no
  settled train set is recorded `NO_TRAIN` and left unscored; the archived paired-loss series
  length equals `n_ticks` on the screen side and the summary recomputes from it; and the module
  body contains none of `_charge_ledger / backtest_runner / backtest_fwer / charge_tier /
  prereg_sha256 / PREREG`, with the real ledger bytes asserted unchanged across a run.

**Uncharged (Q1/Q2).** `data/cache/eval_gate/backtest_fwer.jsonl` is byte-identical before and
after the real run: md5 `a4ae7c13995672e478d59770591b83ba`, 18 rows, never opened. No prereg
sealed. K never read. `data/registry/` untouched. No flag flipped on. No `--force`.

---

## 5. NOT VERIFIED

- **SINGLE-WINDOW (Q5).** One sport, one corpus, 41 game clusters over 3 scored fold dates
  (2026-07-03..07-05). There is no second corpus and none is claimed; the verdict is a screen on
  one window and would not survive as an AHEAD even if it had cleared.
- Only **10 of the 46** distinct grammar `live_tick` columns are testable at all (plus 4
  non-grammar state columns the row asked for): 7 MLB members are NOT_SUPPLIED and 29 belong to
  sports with no scorable tick corpus. "In-game state features do not help" is NOT established;
  what is established is that these 14 columns, in this single-term form, on this window, do
  not.
- Only **one hypothesis form** was screened: a single additive logistic term in `z(x)`.
  Interactions, regime conditioning, non-linear bases, and multi-feature combinations are
  untouched. A feature that matters only inside a regime would read as null here.
- **The 24 base-out dummies were collapsed** to one ordinal `base_out_state` plus `outs` and
  `base_state`; an ordinal encoding of a categorical is a weak single term, so base-out is the
  weakest-tested of the fourteen.
- `batters_faced_continuous` is `pitch_count / 3.8`, a monotone duplicate of `pitch_count`, and
  was deliberately not screened as a separate hypothesis.
- **13,184 of the 28,886 screen ticks are unscored** (the two `NO_TRAIN` fold dates). The
  settlement purge is what costs them; a looser purge would have scored more and been less
  honest. The unscored set is named here, not hidden.
- The **VERDICT side (86 games, 2026-W28) was never read**, by design. Nothing in this memo is a
  verdict-side number.
- The incumbent `e4_gd` series is taken as given from `stacker.e4_gd_series`; it was reproduced
  (0.206785778212713) but not re-derived, and its own game-first-date fold rule -- which does NOT
  apply the settlement purge -- is unchanged by this lane.
- MLB tick timestamps are the CAPTURE time, not the event time; the state parsed at a tick is
  whatever the poller saw. Poller latency is not measured here and would blur, never sharpen, a
  real state effect.
- No pod contact, no deploy, no push.
