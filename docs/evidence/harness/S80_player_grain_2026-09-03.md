# S80 -- in-game PLAYER-GRAIN arm: corpus audit + one leak-free SCREEN (MLB)

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S80 (signals-ingame).
Verdict: **SCREEN_NULL**. The player-grain arm does not clear the +0.004 bar on the
SCREEN partition, and the wider-n companion fold set is negative. No prereg drafted.
A SCREEN is a NON-FINDING: no seal, no charge, K never read, `backtest_fwer.jsonl`
never opened. Calibration language only (Q6).

Module `scripts/platformkit/eval_gate/s80_player_grain_screen.py` (268 lines).
Test `tests/platformkit/ingame/test_s80_player_grain_screen.py` -- `5 passed in 2.43s`.
Artifacts `data/cache/eval_gate/s80_player_grain_2026-09-03{,_embargo0}.{json,csv}`.

---

## Q8 premise check (done first, at HEAD 277bfa90b)

The row says "no corpus audit says which in-game ticks carry player or lineup state".
**CONFIRMED, not falsified** -- and the audit below is the first one. Two facts it turned up
that the row did not anticipate:

1. MLB in-game ticks *do* carry batter/pitcher/on-deck/bullpen identity, on 8,384 of 79,566
   ticks (10.53 pct), from 2026-07-09 to 2026-07-27. Every one of them carries a market line.
2. The canonical **scored** store `data/cache/ingame_grade_joined/mlb` -- the store
   `ingame_replay_scoreboard.discover_store` resolves and every e4/S58 arm reads -- has
   **zero** player columns: the close-join step drops `mlb_pitcher_id` and its four siblings.
   The identity has to be re-joined from `data/cache/ingame_grade/mlb` on `(game_id, ts)`.
   8,309 scored ticks over 53 games survive that join (2026-07-09 .. 2026-07-12, the four days
   where the identity capture and the settled/close window overlap).

## STEP 0 -- in-game tick / state corpus audit

`n rows` and `n games` are counted by reading each file's own schema (jsonl line scan /
pyarrow), never from memory. (a) tick timestamp, (b) in-play market line AT that timestamp,
(c) player or lineup identity AT that timestamp, (d) pregame player as-of table joinable by
the same id.

### MLB

| path | n rows | n games/events | date range | (a) ts | (b) market line | (c) player id at tick | (d) as-of by id |
|---|---|---|---|---|---|---|---|
| `data/cache/ingame_grade/mlb` (405 files) | 79,566 | 401 | 2026-06-19 .. 2026-09-01 | YES | 79,170 (99.50 pct) | **8,384 (10.53 pct)** batter+pitcher+ondeck+bullpen | YES -- `data/domains/mlb/player_gamelogs.parquet` `player_id`, 99.14 pct of those ticks |
| `data/cache/ingame_grade_joined/mlb` (227 files) | 78,986 | 227 | 2026-06-20 .. 2026-07-12 | YES | 78,986 (100 pct) + `outcome` + `close_prob` | **0 (0.00 pct)** -- join drops the fields | n/a (no id to join) |
| the two joined on `(game_id, ts)` | **8,309** | **53** | 2026-07-09 .. 2026-07-12 | YES | YES | YES | YES |
| `data/cache/ingame/mlb_pitch_states__{2022..2026}` | 29,319 (2026) | pitch-level | 2026 season | YES (`asof_idx`) | NO (`p0` is a model prob) | NO -- `proxy_pitcher` only, no id | n/a |
| `data/cache/ingame/mlb_atbat_states__{2022,2023}`, `mlb_states__{2021..2024}` | 13,546 / 41,870 | at-bat / state | 2021-2024 | YES | NO | NO | n/a |
| `data/cache/inplay_odds/mlb_price_series.parquet` | 13,473,591 | 3,932 events | 2023-03-30 .. 2026-07-09 | YES | YES | NO (no state at all) | n/a |
| `data/cache/ingame_shadow_history/mlb` (9 files) | 19,460 | -- | 2026-07-05 .. | YES | `devigged_price` | NO | n/a |
| `data/domains/mlb/asof_inning.parquet` | 28,004 | 28,004 events | -- | pregame | -- | TEAM grain (`home_/away_` rates), no player id | -- |

### NBA / WNBA

| path | n rows | n games | date range | (a) ts | (b) market line | (c) player id at tick | (d) as-of by id |
|---|---|---|---|---|---|---|---|
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 465,249 | 1,593 | 2024-10-22 .. 2026-06-13 | YES | YES + `outcome_home_win` | **0 (0.00 pct)** -- score/clock only | `asof_player_adv.parquet` 77,728 rows keyed `player_id`+`game_id`, but nothing at the tick to join it to |
| `data/cache/ingame_eval_cache.parquet` | 2,476,544 | 1,987 (707 players) | 2022-12-29 .. 2025-10-24 | YES (`t`, `period`, `elapsed`) | **NO market column at all** | **YES (100 pct)** `player_id` + `stat` | YES |
| `data/cache/inplay_odds/nba_price_series.parquet` | 8,399,632 | -- | -- | YES | YES | NO | -- |
| `data/cache/ingame_grade/nba` | 2 | 2 | 2026-07-05 .. 2026-07-18 | YES | 1 row | NO | -- |
| `data/cache/ingame_grade/wnba` | 280 | 3 | 2026-07-19 | YES | 280 | fields present, **all null** | -- |
| `data/domains/basketball_nba/boxdetail_asof.parquet` | 1,810 | 1,810 | -- | pregame | -- | TEAM grain | -- |

NBA is the sharp case: it has the largest market-linked in-game tick corpus in the repo
(465k checkpoints) and a 2.5M-row player-grain in-game corpus, and **they do not intersect** --
the checkpoints carry no lineup, the eval cache carries no price.

### Soccer

| path | n rows | n games | date range | (a) ts | (b) market line | (c) player id at tick | (d) as-of by id |
|---|---|---|---|---|---|---|---|
| `data/cache/ingame_grade/soccer_intl` | 9,183 | 69 | 2026-06-22 .. 2026-08-31 | YES | 9,126 (99.38 pct) | fields present on 534 rows, **all null (0.00 pct)** | -- |
| `data/cache/ingame_grade_joined/soccer_intl` | 9,003 | 51 | 2026-06-22 .. 2026-07-12 | YES | YES + outcome | **0 (0.00 pct)** | -- |
| `data/cache/inplay_odds/soccer_price_series.parquet` | 204,435 | -- | -- | YES | YES | NO | -- |
| `data/domains/soccer/odds.parquet` | 16,322 | -- | -- | pregame | open+close (totals) | NO player column | -- |

### Tennis

| path | n rows | n matches | date range | (a) ts | (b) market line | (c) server at tick | (d) as-of by id |
|---|---|---|---|---|---|---|---|
| `data/cache/ingame_grade/tennis` | 1,255 | 1,238 | 2026-07-04 .. 2026-09-01 | YES | **18 rows, 1 match** | **0 (0.00 pct)** -- 1,237 rows are a single `state_summary=FINAL`; the 18 priced rows read `home_score=0 away_score=0` with no server/game/set field | -- |
| `data/cache/inplay_odds/tennis_price_series.parquet` | 1,854,100 | 986 events | 2026-05-24 .. 2026-07-08 | YES | YES | NO state, no player column | -- |
| `data/cache/ingame_shadow_history/tennis` (13 files) | 3,706 | -- | 2026-07-05 .. | YES | shadow probs | NO | -- |
| `data/domains/tennis/asof_hold.parquet` / `asof_return` / `asof_setdetail` | 30,616 each | 30,616 events | -- | pregame | -- | player-grain BY CONSTRUCTION (`p1_*`/`p2_*`) but there is no tick to attach it to | -- |

### Headline -- share of in-game ticks that carry player/lineup state

| sport | ticks with a market line | of those, ticks with player identity | share |
|---|---|---|---|
| **MLB** | 79,170 | 8,384 | **10.53 pct** (100 pct within the 53-game 2026-07-09..12 window) |
| NBA | 465,249 (checkpoints) + 8.4M (price series) | 0 | **0.00 pct** |
| soccer | 9,126 | 0 | **0.00 pct** |
| tennis | 18 | 0 | **0.00 pct** |
| WNBA | 280 | 0 | **0.00 pct** |

MLB is the only sport where a player-grain in-game arm can be scored at all today. That is
why the screen below is MLB-only, exactly as the row's "MLB first" instruction anticipated,
and why no second sport was attempted: no other sport's ticks carry both a market line and
player identity, so the S80 arm is not merely unmeasured elsewhere, it is unmeasurABLE
without new capture.

## The chosen feature and its as-of definition

**Chosen:** the current pitcher's as-of run-prevention residual through his previous
appearance. **Not chosen:** the batter's platoon wOBA vs the pitcher hand -- the only platoon
table in the repo, `data/domains/mlb/platoon_split_index.parquet`, has 394 batters from
seasons `2022_2023` at a single `as_of`, covering **50.6 pct** of the player ticks, and would
additionally need a pitcher-hand join. The pitcher table covers **99.14 pct** of the player
ticks and **97.26 pct** have at least five prior appearances. Coverage decided it.

For a tick in a game whose game-first-date is `D`, with `mlb_pitcher_id = j`:

```
prior   = player_gamelogs[is_pitcher & player_id == j & date < D]      # STRICTLY before D
IP      = sum(outs)/3 ;  RA9 = 9*sum(earnedRuns)/IP
league  = the same aggregate over every pitcher row with date < D
resid   = (league_RA9 - RA9) / 9                       # runs per inning, + = better
z_raw   = resid * IP/(IP + 30)                         # shrink; unknown or IP < 1 -> 0.0
z       = z_raw * (+1 if half == "top" else -1 if half == "bottom" else 0)
```

`half=top` means the away side is batting, so the home side is pitching; the sign therefore
points the feature at the home team, which is the side `model_prob` / `market_prob` /
`outcome` are all quoted for (`side == "home"` on 8,309 of 8,309 rows). 4 of 8,309 ticks carry
no `half=` token and take z = 0. z is standardised with the TRAIN fold's own mean and sd.

**Tick-time leak guard, in code and tested:** `assert_asof(source_dates, as_of, label)` raises
`AsOfLeak` if any source row is dated at or after the tick's own game date; it is called
inside `pitcher_residuals` on the already-filtered window, so it validates the filter rather
than trusting it. Tested by `test_leak_guard_raises_on_a_same_tick_read` and
`test_pitcher_residuals_uses_only_strictly_prior_appearances`. Independently of the guard, the
gamelog table ends 2026-07-02 and the earliest scored tick is 2026-07-09, so every as-of
aggregate here is at least 7 days stale -- safe, and a stated limit on the feature's freshness.

## The arm

Candidate and incumbent are the SAME function of the SAME fitted blend weight and differ only
by the added term (the gate-baseline-comparability rule):

```
incumbent = gap_blend_arm._guarded_prob(model, market, signal,               w,   0.15)
candidate = gap_blend_arm._guarded_prob(model, market, w*signal + beta*z,    1.0, 0.15)
```

With `beta = 0` these are arithmetically identical; every fold asserts
`allclose(p_incumbent, p_zero_beta, atol=1e-12)` at run time. `w` is fitted by the incumbent's
own `gap_blend_arm._fit_weight` (private helpers are called, never re-implemented) and is
IDENTICAL in both arms; `beta` is then grid-searched on the same train rows over
`linspace(-1, 1, 201)`, ties resolving toward 0. Market guard `max_abs_deviation = 0.15`
unchanged.

Leak contract: game-first-date walk-forward (the S36 variant, "game-first-date variants only"),
train games purged (asserted disjoint from the test games), symmetric 1-day embargo asserted
per fold (`train_date_max < test_date - 1 day`), minimum 200 train ticks.

SCREEN partition: `foundry.tiers.partition_corpus` on game blocks, seed 0 -> 27 SCREEN games /
26 VERDICT games. Only SCREEN games are scored AND only SCREEN games are trained on, so the
VERDICT side is untouched by this row.

## Result

Headline is the 1-day-embargo run, declared before the numbers were read (the row's own
instruction). The 0-day companion is purge-by-game only and is reported because MLB games
settle same-day, which makes the extra embargo day cost two thirds of the folds.

| run | n_ticks | n_games | Brier e4 | Brier e4+player | Brier market | improvement | DM p | DM 95 pct CI | clusters | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **headline, embargo 1d** | 2,267 | 13 | 0.248462357 | 0.244702891 | 0.244971471 | **+0.003759** | 0.7937 | [-0.026879, +0.034398] | 13 | **SCREEN_NULL** |
| companion, embargo 0d | 3,717 | 23 | 0.223745857 | 0.229515382 | 0.221051803 | **-0.005770** | 0.1114 | [-0.012984, +0.001445] | 23 | **SCREEN_NULL** |

Bar for a prereg draft: improvement >= +0.004. Headline is +0.003759, i.e. **below the bar**,
and the companion with 64 pct more ticks and 77 pct more clusters is NEGATIVE. **No prereg
draft is written.** Both DM intervals contain zero by a wide margin; on 13 and 23 game
clusters this screen cannot separate the arms either way.

The fitted `beta` is at the grid BOUNDARY (1.0) in one fold of each run
(headline `{07-11: 1.0, 07-12: -0.06}`, companion `{07-10: 1.0, 07-11: -0.06, 07-12: +0.19}`)
and flips sign between adjacent folds. That is the signature of a coefficient fitted on a few
hundred ticks from a handful of games, not of a stable player-grain effect, and it is the
single strongest reason to read the +0.003759 as noise rather than as a near-miss.

Both arms sit at or above the market Brier in the headline run (market 0.244971 vs candidate
0.244703 -- a 0.000268 difference on 13 clusters) and clearly behind it in the companion
(0.221052 vs 0.229515). The market is efficient here; nothing in this row changes that.

Q9 differential archived: `data/cache/eval_gate/s80_player_grain_2026-09-03.csv` (2,267 rows)
and `..._embargo0.csv` (3,717 rows), each carrying `game`, `timestamp`, `date`, `outcome`,
`pitcher_id`, `z`, `z_std`, `beta`, `weight`, `p_incumbent`, `p_candidate`, `market_prob`,
`loss_incumbent`, `loss_candidate`, `loss_differential`, `cluster_id`. Both Brier columns and
the improvement were recomputed from the CSV alone and reproduce the JSON to 1e-9.

## Honest verdict

**SCREEN_NULL, SINGLE-WINDOW.** The player-grain in-game arm is now MEASURED rather than
unmeasured, on the only corpus in the repo that can carry it, and it does not beat the e4
blend. The gap S80 named is closed as a measurement; what replaces it is a capture gap: 10.53
pct of MLB ticks and 0.00 pct of every other sport's ticks carry the state the lane needs.

## NOT VERIFIED

- **No second corpus (Q5).** One sport, one 4-day window, 53 games, 27 of them on the SCREEN
  side. Labelled SINGLE-WINDOW in the artifact and in the register row. Nothing here is an
  AHEAD and nothing was charged, so the two-corpora rule is not being evaded, it is simply
  unsatisfiable at this corpus size.
- **The VERDICT side (26 games) was never scored or read** -- deliberately, so a later charged
  trial still has an unseen side. Its sha256 is recorded in the artifact.
- **13 and 23 game clusters** are far below any threshold at which a DM interval on tick-level
  losses is informative. The n >= 30 sampling rail (Q7) is NOT met on clusters; it is met on
  ticks. This is a SCREEN, so no bar was moved to accommodate it -- the +0.004 bar was applied
  as written and was not met.
- **Only ONE feature was screened.** The batter-platoon alternative was rejected on coverage
  (50.6 pct) and never run, so "player grain does not help" is not established -- only
  "this pitcher-residual construction does not help on this window".
- **The feature is 7 to 25 days stale** at every tick (gamelogs end 2026-07-02, ticks run
  2026-07-09..12). A same-season, through-yesterday version was not built and might behave
  differently; that is a capture limit, not a result.
- **`beta` hits the grid boundary** in one fold per run; a wider or regularised grid was not tried.
- **Nothing was deployed, sealed, charged or promoted.** `data/cache/eval_gate/backtest_fwer.jsonl`
  was not opened, `_charge_ledger` was not called, K was never read, `data/registry/` was not
  touched, no flag was flipped on, no bar or threshold differs from master (B10/Q3).
- **The 10.53 pct MLB share is a share of ticks in `ingame_grade/mlb` as it stands today**; the
  capture that produced the player fields ran 2026-07-09..2026-07-27 only, and why it started
  and stopped there was not investigated.
- **The joined-store field drop was observed, not traced.** Which module writes
  `ingame_grade_joined` and why it omits the five `mlb_*` player columns was not read; the
  screen re-joins from the raw store instead. Restoring those columns in the join would be the
  cheapest way to widen this arm and is left as a named follow-up, not done here.
