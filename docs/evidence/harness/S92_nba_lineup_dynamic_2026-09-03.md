# S92 -- NBA non-static lineup terms: premise CONFIRMED, corpus 2.3x wider, all three SCREEN_NULL

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S92 (signals-ingame), successor to S84.
Verdict: **SCREEN_NULL on all three terms, on both corpora.** Making the lineup term
NON-STATIC -- minutes-on-floor so far tonight, and the five-man unit's own prior on/off --
does not repair what S84's static PIE sum could not. No term clears +0.004 against the raw
market; none has a CI excluding zero against the incumbent; none beats the S94
recalibration null. **No prereg DRAFT was written.**
A SCREEN is a NON-FINDING: no seal, no charge, K never read, `backtest_fwer.jsonl` never
opened (`data/cache/eval_gate/backtest_fwer.jsonl`, 18 rows, md5
`a4ae7c13995672e478d59770591b83ba`, before and after).
Calibration language only (Q6); no dollar, ROI or edge claim anywhere.

Modules `scripts/platformkit/eval_gate/s92_nba_lineup_dynamic.py` (285 lines) and
`scripts/platformkit/eval_gate/s92_unit_ledger.py` (87 lines -- split out only to keep the
named module inside the 300-LOC bar; it has no other caller).
Test `tests/platformkit/ingame/test_s92_nba_lineup_dynamic.py` -- `4 passed in 9.72s`.
Artifacts `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_{all,rated}.{json,csv}`.
`scripts/platformkit/eval_gate/s84_nba_lineup_at_tick.py` is IMPORTED, never edited.

---

## STEP 0 -- premise (Q8): S84's coverage reproduced, and the clock is in the stream

Re-measured from S84's own module before any new work:

| step | S84 memo | reproduced 2026-09-03 |
|---|---|---|
| priced corpus (`traded == True`) | 1,593 games / 465,249 ticks | **1,593 / 465,249** |
| live clock (`game_clock_s > 0`) | 194,095 ticks | **194,095** |
| bridged to an NBA-Stats id (`build_crosswalk`) | 1,331 games | **1,331** |
| ... and a pbp file exists | 1,331 | **1,331** |
| ... and an as-of player rating exists | 577 | **577** |
| S84's screen ticks available / scored | 34,333 / 33,713 over 284 games | **34,333 / 33,713 / 284** |
| S84's incumbent Brier on that screen | 0.153324 | **0.153324** |

The **substitution stream carries the clock**: every `actionType == "substitution"` row
holds `clock` (`PT7M2.00S`) and `period`, which `S84.parse_clock` / `S84.elapsed_of` turn
into game-elapsed seconds -- 106 substitutions on the sample game `0022400001`, all with a
finite elapsed. So minutes-on-floor per player at a tick is computable from events strictly
before it, and **the on/off history within the SAME game is available for 1,331 of 1,331
games** (it is the same stream that produces the lineup: 0 games failed the exactly-five-
starters check, 30 of 160,321 ticks landed on a floor that was not 5v5 and were dropped).
PREMISE CONFIRMED. Lineup-at-tick could be rebuilt, so the row proceeded.

**The corpus is now 2.3x wider than S84's.** S84 required an as-of player rating and so
scored 577 games / 68,632 ticks. Fatigue needs no rating, so S92 builds the lineup for ALL
1,331 bridged games: **160,291 priced live-clock ticks at a full 5v5**, of which 80,174 are
on the screen side and 79,554 are scored.

## The three terms (each ONE extra logistic column on the S84 incumbent)

* `fatigue_min` -- for each of the ten players on the floor, seconds played SO FAR THIS GAME
  from substitutions strictly before the tick (starters enter at 0.0; a player subbed in
  accrues from his entry; a player on the floor accrues to the tick), summed over the home
  five minus the away five, in minutes.
* `fatigue_share` -- the same sum, each player weighted by his season as-of workload share.
  `asof_player_adv` carries **`possessions_asof`, not minutes**, so the share is a
  possessions share relative to that game's own rated mean; an unrated player weighs 1.0.
* `unit_onoff` -- the home five-man unit's net rating over its EARLIER games this season
  minus the away unit's. Built from the same pbp stream: each game is walked
  substitution-boundary to substitution-boundary and both units on the floor are booked the
  stint's seconds and its score delta (the actions carry cumulative `scoreHome`/`scoreAway`).
  Value = the n/(n+200)-shrunk per-100 net rating, which collapses to
  `100 * points / (possessions + 200)`. **Possessions are a pace-100 TIME proxy** (100 team
  possessions per 2,880 s) -- the feed carries no possession field.

**As-of contract.** `minutes_so_far` applies only events with `elapsed < tick_elapsed` and
re-runs S84's `assert_strictly_before` (raises `AsOfViolation`) on what it kept. The test
asserts the guard directly: appending a substitution AFTER a tick leaves that tick's
feature **byte-identical**, and a substitution at the tick itself is not applied.
`unit_history` snapshots every target game of a date BEFORE any game of that same date is
booked, so a game can never enter its own or a same-day sibling's history.

## Protocol

Incumbent `scripts/platformkit/ingame/nba_mechanism_ladder.py` BASE (logistic on
standardized `[logit_p0, margin_s, z]`), unchanged from S84. **NULL arm** = S94's
recalibration null on identical rows: a logistic on `[logit(market_prob)]` fit on the same
TRAIN fold. Market line = `market_prob`. Game-first-date walk-forward, one fold per date,
train games asserted disjoint from test (purge) and a symmetric 1-day embargo asserted per
fold, `MIN_TRAIN_TICKS` 500, standardisation fit on TRAIN inside each fold.
Bars unmoved (B10/Q3): `IMPROVEMENT_BAR` 0.004, `MIN_TRAIN_TICKS` 500, both S84's.

**Partition (screen side only).** `partition_corpus` on game blocks, seed 0, run TWICE:
on the 577 rated games -- reproducing S84's split **byte-for-byte**, 289 screen / 288
verdict, screen sha256 `0e770bd263297b09c5f1d1da6153355a2da504a4d55f091dfdfe39e310adc07e`,
verdict sha256 `d7ad485bc6aa3d098d6742dbc34b079b1026bddf9f6fe07eb33bb835d7ef3ad5` -- and
SEPARATELY on the 754 unrated games, 377 screen / 377 verdict, screen sha256
`ca913d4cd28e188dbb820a2f2bec4d6735d3047c3e6ff0ad841aaaf2920bf67b`, verdict sha256
`11c03a29c7310738748ed7b4abcda00d8edb3e5c60ff65c0d43be94c9775b76a`. Because the rated split
is S84's own, **no S84 VERDICT game is ever read**, and neither verdict side was scored.

## Result -- corpus ALL (1,331 lineup games; 661 screen games, 79,554 ticks)

194 date folds, 191 scored, 3 INSUFFICIENT; 2024-10-25 .. 2026-04-06.

| arm | tick-weighted Brier |
|---|---|
| market line (`market_prob`) | **0.142877** |
| S94 recalibration null | **0.144293** |
| incumbent (ladder BASE) | **0.146850** |
| BASE + `fatigue_share` | 0.146948 |
| BASE + `fatigue_min` | 0.147061 |
| BASE + `unit_onoff` | 0.147247 |

| term | vs incumbent | DM p | 95 pct CI (game-clustered, 661 clusters) | vs market | vs null | verdict |
|---|---|---|---|---|---|---|
| `fatigue_min` | **-0.000212** | 0.4899 | [-0.000814, +0.000390] | -0.004185 | -0.002768 | SCREEN_NULL |
| `fatigue_share` | **-0.000098** | 0.7920 | [-0.000828, +0.000632] | -0.004071 | -0.002655 | SCREEN_NULL |
| `unit_onoff` | **-0.000397** | 0.2380 | [-0.001058, +0.000263] | -0.004370 | -0.002954 | SCREEN_NULL |

n / n_informative / n_eff (S87, `attach_informative_summary`): 79,554 / 72,555 / 3,185.1
(`fatigue_min`), 79,554 / 72,583 / 2,710.1 (`fatigue_share`), 79,554 / 72,546 / 2,348.0
(`unit_onoff`). The informative-only CIs sit on the same side of zero and still cross it:
[-0.000862, +0.000364], [-0.000870, +0.000631], [-0.001073, +0.000269].

## Result -- corpus RATED (S84's exact 577-game split; 284 screen games, 33,713 ticks)

83 date folds, 80 scored, 3 INSUFFICIENT; 2024-10-25 .. 2025-04-13. Incumbent 0.153324 and
market 0.144101 reproduce S84's headline exactly, so this table is directly comparable to
S84's static term (-0.000455, p 0.7960).

| arm | Brier | vs incumbent | DM p | 95 pct CI (284 clusters) | vs market | vs null | verdict |
|---|---|---|---|---|---|---|---|
| market | 0.144101 | -- | -- | -- | -- | -- | -- |
| S94 null | 0.146843 | -- | -- | -- | -- | -- | -- |
| incumbent | 0.153324 | -- | -- | -- | -- | -- | -- |
| `fatigue_min` | 0.152849 | **+0.000475** | 0.3755 | [-0.000579, +0.001530] | -0.008748 | -0.006006 | SCREEN_NULL |
| `fatigue_share` | 0.153149 | **+0.000175** | 0.8348 | [-0.001472, +0.001822] | -0.009049 | -0.006306 | SCREEN_NULL |
| `unit_onoff` | 0.154385 | **-0.001061** | 0.1691 | [-0.002577, +0.000454] | -0.010284 | -0.007542 | SCREEN_NULL |

n_informative / n_eff: 31,036 / 1,268.1, 31,062 / 1,170.7, 31,035 / 960.0.

**The fatigue sign is not stable across the two corpora** (+0.000475 on the rated 284 games,
-0.000212 on the wider 661), both far inside their CIs. That instability is itself the
result: the term is carrying noise, not a small real effect.

## The terms are not degenerate (B9)

Median **15** distinct home five-man units per scored game (unchanged from S84). Over the
scored ALL corpus: `fatigue_min` mean +0.387, sd 16.70, range [-147.52, +148.98], non-zero
on 90.96 pct of ticks; `fatigue_share` sd 23.37, non-zero on 94.88 pct; `unit_onoff` mean
-0.146, sd 5.196, range [-30.53, +44.64], non-zero on 78.56 pct (the remaining 21.44 pct are
units with no earlier appearance this season, which take the shrinkage default 0.0).
1,299 of 1,331 target games received a non-empty unit history.

## Secondary measurement -- the incumbent is behind a plain recalibration of the line

Not a term result, but it falls out of the null arm on identical rows and is worth
recording: the S94-style recalibration null (a logistic on `logit(market_prob)` alone)
beats the NBA in-game incumbent on **both** corpora -- 0.144293 vs 0.146850 (ALL) and
0.146843 vs 0.153324 (RATED). The raw line in turn beats that recalibration
(0.142877 and 0.144101), i.e. the in-play price is already well calibrated at this grain and
re-fitting it costs a little. Calibration statement only; nothing is claimed about value.

## Reproduction (A2)

Recomputed from the archived per-tick CSVs alone, with no reference to the JSON summaries:
every Brier, every improvement, every DM p and CI bound and every cluster count above
reproduces identically (ALL: incumbent 0.146850, null 0.144293, market 0.142877, 661
clusters; RATED: 0.153324 / 0.146843 / 0.144101, 284 clusters). The partition shas were
checked against S84's recorded values inside the run itself
(`reproduces_s84_screen_sha256: true` in both artifacts).

## Q9 differential archived

`data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv` (79,554 rows) and
`..._rated.csv` (33,713 rows), columns: `game, nba_game_id, ts, date, period, elapsed,
outcome_home_win, home_five, away_five, market_prob, p_incumbent, p_null, fatigue_min,
fatigue_share, unit_onoff, loss_incumbent, loss_null, loss_market, p_<term>, loss_<term>,
d_<term> (3 terms), cluster_id`. The as-of state is archived with the row: `home_five` /
`away_five` carry the ten player ids on the floor and the three term values are stored
beside the probabilities, so every number is recomputable from the artifact alone.

## Verdict

**SCREEN_NULL on all three terms, both corpora. SINGLE-WINDOW.** Three things are now
measured that were not before: NBA lineup-at-tick coverage is **1,331 games / 160,291
priced live-clock ticks at a full 5v5** (S84 measured 577 / 68,632 because it required a
player rating); the non-static successors S84's NOT VERIFIED section proposed -- fatigue and
five-man unit on/off -- do not help the NBA in-game incumbent either; and on these rows that
incumbent is itself behind a plain recalibration of the live line.

## NOT VERIFIED

* **SINGLE-WINDOW (Q5)**: one sport, one in-play price source, one partition side. The ALL
  corpus spans two NBA seasons (2024-25 and 2025-26) but it is one capture window of one
  venue, so no AHEAD is claimed and no second corpus_unit is named.
* **Possessions are a pace-100 TIME proxy**, not counted possessions -- the pbp feed has no
  possession field and its `actionType` vocabulary (`other` absorbs rebounds and turnovers)
  cannot support a possession count. The shrinkage denominator is therefore stint time.
* `unit_onoff` is 0.0 on 21.44 pct of scored ticks (a unit with no earlier appearance this
  season). The column is a mixture of a measurement and a shrinkage default, and the split
  between those two populations was not screened separately.
* Unit stints come from the `espn_derived` pbp stream: a substitution the feed omits both
  mis-books the stint's seconds and mis-labels the unit that earned the score delta. The
  0.019 pct visibly-not-5v5 tick rate bounds how often the floor breaks openly, not how
  often it is quietly wrong.
* **Starters are inferred** from the action stream (S84's rule, imported unchanged) and
  inherit its blind spot: a starter who records no action and is never subbed out is missed.
* `fatigue_share` uses `possessions_asof` because the store carries no minutes column, and
  an unrated player weighs 1.0 -- so on the 754 unrated games it degenerates to
  `fatigue_min`. Its separate signal exists only on the 577 rated games.
* Fatigue is entered as a raw home-minus-away minutes difference with no interaction
  (period, remaining time, margin, rest days, back-to-back). A conditioned form was NOT
  screened; only this construction is refuted.
* Dead-clock ticks (58.3 pct of the corpus) are excluded by construction, so these Brier
  values are NOT comparable to any figure computed over the whole 465,249-tick corpus.
* 262 priced games do not bridge to an NBA-Stats id at all and were never in scope.
* Both VERDICT sides were deliberately not scored. `data/registry/` untouched, no flag
  flipped on, no bar moved (B10/Q3), `_charge_ledger` never called, K never read, no pod
  contact, no push.
* Lane's own report; no verifier re-run.
