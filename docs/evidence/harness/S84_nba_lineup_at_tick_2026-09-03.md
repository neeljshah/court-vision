# S84 -- NBA lineup-at-tick: premise FALSIFIED, lineup BUILT another way, one SCREEN = NULL

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S84 (signals-ingame).
Verdict: **SCREEN_NULL** (the lineup-strength term does not clear the +0.004 bar; it is
slightly negative). The row's own premise -- "NBA player grain is one join away, the two
stores never intersect" -- is **FALSIFIED on both halves**: they cannot be joined at all in
any useful volume, and the lineup did not need them. No prereg drafted.
A SCREEN is a NON-FINDING: no seal, no charge, K never read, `backtest_fwer.jsonl` never
opened (18 rows, md5 `a4ae7c13995672e478d59770591b83ba`, before and after).
Calibration language only (Q6); no dollar, ROI or edge claim anywhere.

Module `scripts/platformkit/eval_gate/s84_nba_lineup_at_tick.py` (300 lines).
Test `tests/platformkit/ingame/test_s84_nba_lineup_at_tick.py` -- `4 passed in 2.01s`.
Artifacts `data/cache/eval_gate/s84_nba_lineup_2026-09-03{,_embargo0}.{json,csv}`.

---

## STEP 0 -- premise: the two stores' schemas, and whether they can be aligned

Exact paths, from the S80 memo (its "NBA" rows) and confirmed on disk:

| store | rows | key column | schema (pyarrow) |
|---|---|---|---|
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 465,249 ticks / 1,593 games | `game_id: int64` = the **ESPN event id** (401704627) | `game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue` |
| `data/cache/ingame_eval_cache.parquet` | 2,476,544 rows / 1,987 games / 707 players | `game_id: string` = the **NBA-Stats game id** (`0022200523`) | `game_id, game_date, fold, t, bucket, player_id, team, stat, cur, routed, snapshot, v2, l5, truth, pf, cur_min, period, elapsed_sec_in_period, game_remaining_sec, game_elapsed_sec, home_score, away_score` |

First rows: the priced corpus opens `401704627 / 2024-10-22 / period 1 / game_clock_s 720.0 /
0-0 / market_prob 0.655 / market_ticker nba-nyk-bos-2024-10-22`. The eval cache opens
`0022200523 / 2022-12-29 / t=120 / bucket 02min(earlyQ1) / player_id 203486 / CHA / pts /
cur 2.0 / truth 14.0`, i.e. **one row is ONE player's ONE projected stat at one of 11 fixed
elapsed buckets** (t in {120, 240, 360, 720, 1080, 1440, 1800, 2160, 2520, 2640, 2760};
seven stats: pts reb ast fg3m stl blk tov). It is a prop-projection eval cache. It carries
no on-floor flag, no minutes, no substitution -- **it cannot yield a five-man lineup**, only
the set of players whose projections were being scored.

**Clock: alignable.** Both carry period plus a clock. The priced corpus has `game_clock_s`
(seconds remaining in the period) which maps to elapsed by `(period-1)*720 + (720-clock)`
(OT periods 300s); the eval cache stores `game_elapsed_sec` directly on that 11-point grid.
So a tick can be placed to within its own ~60s capture cadence -- inside one possession.

**Identity: NOT alignable in useful volume.** The two `game_id` namespaces are disjoint:
raw intersection 0, zero-stripped 0, zero-padded 0. A real bridge exists --
`data/domains/basketball_nba/espn_nba_game_bridge.parquet` (1,299 exact rows), and more
generally `market_ticker` = `nba-{away}-{home}-{date}` joined to
`data/domains/basketball_nba/games.parquet` on (date, unordered team pair). That bridge maps
**1,280 of the 1,593** priced games to NBA-Stats ids. But the corpora barely overlap in TIME:
the eval cache is 708 games of 2022-23 + 1,230 of 2023-24 + 45 of 2024-25 + 4 of 2025-26,
while the priced corpus starts 2024-10-22. After the bridge, **32 games intersect** -- far
below any screen. This is the falsification: the join is not "one join away", it is one
bridge plus a season overlap that does not exist, onto a store that has no lineup anyway.

**So the lineup came from events instead**, which is what the row actually asked for
("derived only from events with clock strictly before the tick"):
`data/cache/team_system/pbp*/<nba_game_id>.json` -- 3,652 games (1,230 in `pbp_2023_24`,
1,254 in `pbp_2024_25`, 1,192 in `pbp`), each an action stream with
`clock, period, teamTricode, personId, actionType, subType`, including ~100-150
`actionType == "substitution"` rows per game with `subType` `in`/`out`.
**All 1,280 bridged priced games have a pbp file.**

## Alignment rule (the as-of contract)

* tick elapsed = `(period-1)*720 + (720 - game_clock_s)`, OT = `2880 + (period-5)*300 + (300 - clock)`.
* event elapsed = the same function of the action's `PT<M>M<S>S` clock and period.
* `lineup_at(subs, starters, tick_elapsed)` applies **only** events with
  `event_elapsed < tick_elapsed`, and `assert_strictly_before` raises `AsOfViolation` on any
  event at or after the tick. Tested on a same-tick event and on a later one.
* Starters are inferred, not read: a player is a starter if his FIRST appearance in the
  stream is a non-substitution action, or a substitution he is leaving on (`subType out`) --
  both are only possible for a player already on the floor.
* Only **live-clock** ticks are used (`game_clock_s > 0`). 58.3 pct of the priced corpus has
  `game_clock_s == 0` (81.2 pct of its period-4 rows): those are dead-ball / intermission /
  post-final ticks with a frozen score, where there is no lineup and the outcome is already
  known. 194,095 of 465,249 ticks survive that filter.

## Coverage (both a line and a full 5v5 lineup)

| step | games | ticks |
|---|---|---|
| priced corpus (`traded == True`, all rows) | 1,593 | 465,249 |
| live clock (`game_clock_s > 0`) | 1,593 | 194,095 |
| bridged to an NBA-Stats id (`build_crosswalk`, orientation-confirmed) | 1,331 | -- |
| ... and a pbp file exists | 1,331 | -- |
| ... and an as-of player table exists for that game | **577** | -- |
| **line + full 5v5 lineup at the tick** | **577** | **68,632** |

Lineup-derivation quality on those 577 games: **0** games failed the exactly-five-starters
check, and **26 of 68,658** ticks (0.038 pct) landed on a floor that was not 5v5 and were
dropped. The feature is not a per-game constant: the scored set carries a median of **15**
distinct home five-man units per game (min 8, max 28), so the term varies within a game.

The binding limit is the ratings table, not the lineup: `asof_player_adv.parquet` (77,728
rows, 3,685 games) covers game-id prefixes 00222/00223/00224 only -- 1,225 games of 2024-25
and **none of 2025-26** -- so the 2025-26 half of the priced corpus has a lineup but no
as-of rating and is out of the screen.

## The screen

* **Incumbent**: `scripts/platformkit/ingame/nba_mechanism_ladder.py` BASE, the only NBA
  in-game model fitted on this tick corpus -- a logistic on standardized
  `[logit_p0 (first traded price), signed margin, margin/sqrt(rem_frac)]` (`_BASE_COLS`,
  `_fit_predict`). The two named candidates in the row, `gate_run_nba_possession.py` and
  `ingame_crossval_nba.py`, both run on the linescore end-of-quarter corpora, not on ticks.
  The incumbent probability column is `p_incumbent`; the **market line is `market_prob`**
  (the Polymarket in-play price on the same tick).
* **Candidate**: the identical base plus ONE term, `lineup_strength` = the five home
  players' `pie_asof` minus the five away players', each centred on that game's own rated
  players (an unrated player contributes 0.0, i.e. an average player). Both arms see the
  same ticks and the same base columns; standardisation (mu, sd) is fit on TRAIN inside each
  fold and applied to TEST.
* **Protocol**: SCREEN side only of `foundry.tiers.partition_corpus` on game blocks, seed 0
  (289 SCREEN / 288 VERDICT games; screen sha256 `0e770bd263297b09c5f1d1da6153355a2da504a4d55f091dfdfe39e310adc07e`,
  verdict sha256 `d7ad485bc6aa3d098d6742dbc34b079b1026bddf9f6fe07eb33bb835d7ef3ad5`; the
  verdict side was never read). Game-first-date walk-forward, one fold per date; train games
  purged (asserted disjoint from test games); symmetric 1-day embargo asserted per fold;
  MIN_TRAIN_TICKS 500. 83 date folds, 80 scored, 3 INSUFFICIENT.

### Result (embargo 1 day -- the headline)

| arm | tick-weighted Brier |
|---|---|
| incumbent (ladder BASE) | **0.153324** |
| candidate (BASE + lineup_strength) | **0.153779** |
| market line (`market_prob`) | **0.144101** |

n = **33,713 ticks / 284 games** (34,333 screen ticks available), 2024-10-25 .. 2025-04-13.
improvement vs incumbent **-0.000455** (the candidate lost MORE), DM p **0.7960**,
game-clustered 95 pct CI **[-0.003920, +0.003009]**, 284 clusters -> **SCREEN_NULL**,
far below the +0.004 bar, so **no prereg draft was written**.
Candidate vs market: **-0.009679**, DM p 0.0172, CI [-0.017630, -0.001727] -- the model side
still trails the live in-play price, and the lineup term does not close that.

### Companion (embargo 0 days, purge by game only)

n = 33,821 ticks / 285 games; incumbent 0.150973 -> candidate 0.151859, improvement
**-0.000886**, DM p 0.5906, CI [-0.004125, +0.002352] -> **SCREEN_NULL and negative**.
Both runs agree in sign, so +0.000455 of "loss" is not an embargo artifact.

### Reproduction (A2)

Recomputed from the archived CSV alone, with no reference to the JSON:
incumbent 0.153324, candidate 0.153779, market 0.144101, improvement -0.000455,
DM p 0.7960, CI [-0.003920, +0.003009], 284 clusters -- identical.

### Q9 differential archived

`data/cache/eval_gate/s84_nba_lineup_2026-09-03.csv` (33,713 rows) and
`..._embargo0.csv` (33,821 rows), columns: `game, nba_game_id, ts, date, period, elapsed,
outcome_home_win, home_five, away_five, lineup_strength, p_incumbent, p_candidate,
market_prob, loss_incumbent, loss_candidate, loss_market, loss_differential, cluster_id`.
The as-of state itself is archived: `home_five` / `away_five` carry the ten player ids that
produced the term at that tick, so every number is recomputable from the artifact alone.

## Verdict

**SCREEN_NULL. SINGLE-WINDOW.** Two things are now measured that were not before:
NBA in-game lineup-at-tick coverage is **577 games / 68,632 priced live-clock ticks at a
full 5v5**, not the 0.00 pct S80 recorded; and the first player-grain term built on it does
not help the NBA in-game incumbent.

## NOT VERIFIED

* **SINGLE-WINDOW (Q5)**: one sport, one season (2024-25), one partition side, one feature.
  "Lineup does not help in-game NBA" is NOT established -- only that *this* construction, a
  static sum of pregame season-to-date PIE, does not on this window.
* The term is **pregame-static per player**: it changes within a game only through
  substitutions, and carries nothing about fatigue, foul trouble, minutes played tonight,
  matchup or on/off. The row's live-state ambition is untouched.
* `pie_asof` is a single all-in-one impact number and was chosen because it is the one as-of
  player column with 99.6 pct non-null on 2024-25; `offensiverating_asof` /
  `defensiverating_asof` / `usagepercentage_asof` were NOT screened.
* Starters are **inferred from the action stream**, not read from a boxscore starters field.
  The inference reproduced exactly five per side on all 577 games and 20 evenly-spaced
  sampled games were checked by hand, but a game where a starter records no action and is
  never subbed out would silently be missed.
* The pbp stream is `source: espn_derived`; a substitution the feed omits shifts a lineup
  until the next event for that team. The 0.038 pct not-5v5 rate bounds how often the floor
  visibly breaks, not how often it is quietly wrong.
* 754 bridged priced games (chiefly 2025-26) have a lineup but **no as-of rating** and were
  never scored; 262 priced games do not bridge at all (the crosswalk requires an
  orientation-confirmed date+team-pair match in `games.parquet`).
* Dead-clock ticks (58.3 pct of the corpus, mostly post-final period-4 rows) are excluded by
  construction, so these Brier values are NOT comparable to any figure computed over the
  whole 465,249-tick corpus.
* The VERDICT side of the partition was deliberately not scored; nothing here is a charged
  claim. `data/registry/` untouched, no flag flipped on, no bar moved (B10/Q3),
  `_charge_ledger` never called, K never read.
