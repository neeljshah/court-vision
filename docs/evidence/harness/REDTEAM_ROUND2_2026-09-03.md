# S118 -- RED-TEAM ROUND 2 over the rows landed since S79 (2026-09-03)

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S118 (harness).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.
Calibration language only. A SCREEN is a NON-FINDING. **NOT VERIFIED** -- this is the lane's own
adversarial report; no independent verifier has re-run it.

READ-ONLY LANE. Nothing under `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/` was
opened for write. No code was edited. `data/registry/` untouched. The FWER ledger
`data/cache/eval_gate/backtest_fwer.jsonl` was never opened by this lane (18 rows, unchanged);
`family_bars.FAMILY_ALIASES` was mutated only IN PROCESS inside a scratch probe. No charge, no
seal, no flag flipped, no pod contact, no external fetch. Base commit `a93b0cc9e`.

Line citations are against the tree at the END of this lane. `foundry/ingame_screen.py` was edited
by a CONCURRENT lane while these probes ran (a `tick_partition.screen_side` import was added at
:37, shifting everything below it by one line); the citations here were re-checked afterwards and
none of the reproduced behaviour depends on that change.

Register numbers S131-S142 below are PROPOSALS, not claims on the file. The register grew to S122
while this lane ran (other lanes are appending), so the orchestrator should assign the next free
numbers when it writes these rows -- this lane did not touch
`docs/evidence/HARNESS_GAPS_2026-09-03.md`.

Probe scripts live under the session scratchpad
(`...\94ad507e-cbc9-47ac-9667-91146366346b\scratchpad\p1..p16.py`), never under the repo.

---

## VERDICT

**14 findings reproduced with running code; 10 adversarial probes ran and PASSED.**
Three carry real blast radius and are stated first. Nothing here was fixed.

The three that matter:

1. **F1 -- the NBA "close" is an in-play quote.** 43.5 pct of the `first_inplay_tick` closes
   already have points on the board, and no consumer applies `close_within_30s`. Every
   "vs the close" verdict on NBA (S112 rescore, S113's 147 vanishing promotions) is quoted
   against a partly post-tip reference. Direction: **false NULL**.
2. **F7 -- `asof_supply`'s `prior` rule leaks the event's own season on soccer.** 51.78 pct of
   soccer matches sit in the calendar year AFTER their own season label, so
   `merge_asof(allow_exact_matches=False)` on `dt.year` serves that match's OWN season
   aggregate. Measured: served `-0.221968` where the honest prior is `-0.275744`.
   Direction: **false AHEAD** on the `soccer_style_fingerprints` family.
3. **F4 -- `real_game_split` manufactures real games.** 32 of 165 boundaries on the live MLB
   store fire less than 10 minutes (mostly 1-13 SECONDS) after the previous tick, on a
   1-inning feed regression. `n_real_games` 392 should be about 360; every clustered CI on
   MLB in-game is about 4.2 pct too narrow. Direction: **false AHEAD** + wrong n.

---

## 1. THE IN-GAME TIER (`foundry/ingame_screen.py`, `foundry/ingame_screen_nba.py`)

### F2 -- the truncation-invariance guard cannot see a SAME-TICK leak, and a same-tick feature clears the bar

`assert_tick_asof` (ingame_screen.py:88) rebuilds the table from `src[:k+1]` and requires row k to
match. A feature that reads its OWN tick's label is invariant under that truncation, so it passes.

Probe (`p2_tier.py`, `p3_tier.py`), 28 synthetic games x 60 ticks, `MIN_TRAIN=60`:

```
assert_tick_asof on a builder that serves the tick's OWN LABEL -> PASSES, probes [133, 266, ... 1064]
control: a builder that reads the NEXT tick  -> correctly raises TickTimeLeak

feature      n_ticks  improvement_vs_null   ci95                  clears_bar
label_now       1500        +0.273411       [+0.23409,+0.31274]      True     <-- the leak
noise           1500        -0.000680       [-0.00294,+0.00158]      False
```

The guard is honest about what it guards (a LATER tick) and the docstring says so; the defect is
that the module presents it as "ENFORCED, not asserted" leak protection for the whole contract,
and `run()` accepts an arbitrary `features=` mapping with no second gate. Note the one accidental
brake: a strictly binary same-tick column is refused by `_fit`'s `MIN_UNIQUE = 3`
(ingame_screen.py:143) -- add 5 pct jitter and it scores.
Blast radius: **false AHEAD**, unbounded magnitude.

Register-row candidate:
`| S131 | harness | THE TICK-TIME AS-OF GUARD IS TRUNCATION-ONLY AND PASSES A SAME-TICK LEAK: assert_tick_asof (ingame_screen.py:88) rebuilds from src[:k+1], so a feature reading its OWN tick's label is invariant and passes; measured, that feature then scores improvement_vs_null +0.273411 with CI [+0.234,+0.313] and clears_bar True. Fix: a SECOND guard in run()/sweep() that refuses any candidate column whose per-game variance is zero AND whose per-game value tracks the game's label, plus an assertion that every served column name is a member of the frozen grammar. Bar: the guard raises on the reproduced probe and leaves the 564 S102 hypotheses byte-identical | S118 | OPEN (new 2026-09-03) |`

### F3 -- the 1-day settlement embargo silently voids on a non-ISO-Z timestamp string

`walk_forward_feature` builds `cut` with `strftime("%Y-%m-%dT%H:%M:%SZ")` (ingame_screen.py:175)
and then compares tick strings to it with `<` (:177). Both asserts (:181, :182) use the same string
ordering, so a format mismatch passes them too. `s114_ingame_ensemble.purge` (:56-61) is a verbatim
copy and inherits it.

Probe (`p4_embargo.py`): one train game whose LAST tick is 2 h before the fold's first tick, so the
1-day embargo MUST exclude it.

```
ISO-Z   (the format s102 writes)      cut=2026-07-05T01:00:00Z  status=NO_TRAIN   n_train=0   correct
SPACE   (pandas/parquet default str)  --                        status=UNFITTABLE n_train=8   WRONG
OFFSET  (Timestamp.isoformat())       cut=2026-07-05T01:00:00Z  status=NO_TRAIN   n_train=0   correct
```

`' '` (0x20) sorts before `'T'` (0x54), so every same-day tick reads as earlier than the cut.
LATENT on the two live corpora: `ingame_grade_joined/mlb` writes `2026-06-30T22:42:03Z` and
`ingame_screen_nba.load_screen` re-formats to `%Y-%m-%dT%H:%M:%SZ`. It is a contract defect on a
shared helper that any new corpus can trip.
Blast radius: **false AHEAD** (training on near-contemporaneous ticks), silent.

Register-row candidate:
`| S132 | harness | THE IN-GAME PURGE COMPARES TIMESTAMPS AS STRINGS AND VOIDS ON ANY NON-ISO-Z FORMAT: ingame_screen.walk_forward_feature:175-177 builds cut with strftime(...Z) and compares tick strings with <; with a space-separated stamp a train game settling 2 h before the fold is admitted (n_train=8 where 0 is correct) and BOTH asserts (:181,:182) pass because they share the broken ordering; s114_ingame_ensemble.purge:56-61 is a verbatim copy. Fix: parse once (pd.to_datetime) at the top of walk_forward_feature and compare Timestamps, asserting the parsed dtype is datetime64. Bar: the reproduced probe yields NO_TRAIN on all three formats and the s102/s114 fold tables reproduce byte-identically | S118 | OPEN (new 2026-09-03) |`

### F13 -- S114's null arm is fit on a different row set than the candidate arms

The tier's own contract (`ingame_screen._fit`, :135-144) fits null and candidate on ONE row set so
the arms differ only by the candidate term. `s114_ingame_ensemble.run` breaks it: `p_null =
recal_null(train, ...)` (:171) uses the FULL outer train window, while `ensemble_fold` fits on
`keep = np.isfinite(stack).all(axis=1)` (:131) -- the rows finite across ALL k columns.

Read out of the SHIPPED artifact `data/cache/eval_gate/s114_ingame_ensemble.json` (`p11.py`), fold F1:

```
n_train (rows the NULL is fit on)  38847
k1  n_fit 38847   test_coverage 0.996
k3  n_fit 25722   test_coverage 0.612
k5  n_fit 25722   test_coverage 0.612
```

So the k>=3 arms train on 66.2 pct of the null's rows and natively score 61.2 pct of the fold's
ticks (the rest fall back to the null, delta 0). The published k ladder
(k1 -0.000484, k3 -0.000410, k5 -0.000400, k10 -0.000407 vs the market) therefore compares arms
that differ in TRAINING ROWS and in SCORED ROWS, not only in k. The headline verdict is still a
NULL (no arm beats the market), so this is not a false AHEAD -- it is that **the k-ranking the row
asked for is not measurable from this artifact**.
Blast radius: wrong n; an uninterpretable k comparison.

Register-row candidate:
`| S133 | harness | S114'S NULL AND CANDIDATE ARMS ARE FIT ON DIFFERENT ROWS, SO THE k LADDER IS NOT A k COMPARISON: recal_null (s114_ingame_ensemble.py:171) fits on the whole outer train window while ensemble_fold (:131) fits on the all-k-finite subset -- measured on the shipped artifact, fold F1 null 38,847 rows vs k3/k5 25,722 (66.2 pct) with test_coverage 0.996 (k1) vs 0.612 (k3+). Fix: restrict BOTH arms to the same keep mask per k, report improvement on those rows only, and publish n_fit/n_scored per arm beside every k. Bar: a re-run whose per-k rows are identical across arms; expect the NULL to stand and say so | S114 S118 | OPEN (new 2026-09-03) |`

### F14 -- S116's MLB side is 63 clusters over 2 calendar dates, not "392 real games"

The S116 register row names "MLB (392 real games after S106)". The shipped series
`data/cache/eval_gate/s116_pooled_ingame_2026-09-03.csv` scores MLB on two folds:

```
sport fold      n     clusters  distinct dates
mlb    3      7972       52          1
mlb    4      1697       11          1
nba   1..5  ~38.5k each 123-140    36-59
```

The pooled-vs-per-sport conclusion on "the low-n sport" rests on 63 MLB clusters across 2 calendar
days. Blast radius: wrong n / a conclusion that does not generalise.

Register-row candidate:
`| S134 | harness | THE S116 POOLED-BLEND VERDICT RESTS ON 63 MLB CLUSTERS OVER 2 CALENDAR DATES: s116_pooled_ingame_2026-09-03.csv scores mlb only on folds 3 (7,972 ticks / 52 clusters / 1 date) and 4 (1,697 / 11 / 1) against 673 NBA game-clusters over 18 months, while the S116 row cites "392 real games". Fix: publish n_clusters and n_dates per sport per fold in the artifact header, and either extend the MLB screen window or re-label the verdict as a 2-date readout. Bar: the artifact carries the per-sport fold table and the memo's headline names 63 clusters | S116 S118 | OPEN (new 2026-09-03) |`

---

## 2. THE AS-OF SUPPLY REGISTRY (`foundry/asof_supply.py`)

### F7 -- the `prior` rule serves the event's OWN season whenever a season spans two calendar years

`_prior_rule` (:255, :262-263) keys a `grain="season"` family by
`pd.to_datetime(context["date"]).dt.year` against the source's integer `season`, then relies on
`allow_exact_matches=False` (:246).

Measured on `data/domains/soccer/matches.parquet` (`p8b.py`):

```
season label -> calendar years of its matches
2023  2023..2024   2024  2024..2025   2025  2025..2026
seasons spanning TWO calendar years: 11 of 11
share of matches whose calendar year != its own season label: 0.5178
```

End-to-end through `asof_supply.supply` (`p8c.py`), two matches of the SAME season 2025:

```
20250808-E1-birmingham-ipswich  2025-08-08  served ppg (home-away) -0.075960   (honest, <=2024)
20260101-E0-brentford-tottenham 2026-01-01  served ppg (home-away) -0.221968

  Brentford  season-2024 ppg 1.473684 | season-2025 ppg 1.394737  (its OWN season)
  Tottenham  season-2024 ppg 1.000000 | season-2025 ppg 1.078947  (its OWN season)

expected (honest prior, seasons <= 2024)          -0.275744
expected if the OWN season 2025 is included       -0.221968
SERVED                                            -0.221968   <-- the own-season value
```

The module docstring says "the event's own row is unreachable" under `prior`. For 51.78 pct of
soccer events it is reachable, on all 8 `_STYLE` columns.
Blast radius: **false AHEAD** on `soccer_style_fingerprints`.

Register-row candidate:
`| S135 | harness | THE prior RULE LEAKS THE EVENT'S OWN SEASON ON SOCCER: asof_supply._prior_rule:262-263 maps the event to dt.year while the source keys an integer season, and 51.78 pct of matches (11 of 11 seasons span two calendar years) fall in the year AFTER their own season label -- measured, the 2026-01-01 Brentford-Tottenham match is served -0.221968, exactly the expanding mean INCLUDING its own 2025 season, where the honest <=2024 prior is -0.275744. Fix: derive the event's season from the corpus's own season column (matches.parquet carries it) rather than from dt.year, and refuse a season-grain family on a corpus with no season column. Bar: the served value for that event becomes -0.275744, every other family's served values byte-identical, and the S85/S111 screen table re-run with the count of moved rows | S85 S111 S118 | OPEN (new 2026-09-03) |`

### F17 -- the `side` rule has NO as-of guard; its honesty is entirely the producer's promise

`_side_rule` (:220-237) keys on `(event_id, side)` and serves the event's own row verbatim.
Probe (`p14.py`) registers a side-rule family whose column equals the event outcome:

```
side rule served: [9.0, 9.0, -9.0]   -- straight off the event's own row
```

This is documented ("Legal ONLY for a column settled BEFORE the event") but nothing enforces it,
and 3 registry families use it (`nba_player_value_features`, `tennis_schedule_density`,
`tennis_travel_scouting`).
PARTIAL MITIGATION MEASURED (`p16.py`): `tennis_schedule_density.matches_last_7d` was audited
against both conventions over 400 players -- **0.0000 of rows match a count that includes the
match itself**, so that particular column is not self-inclusive. The rule is a standing hazard,
not a live leak on the column checked.
Blast radius: potential **false AHEAD**; currently unexercised on the one column audited.

Register-row candidate:
`| S136 | harness | THE side RULE IN asof_supply HAS NO AS-OF GUARD AT ALL: _side_rule:220-237 serves the event's own row verbatim (reproduced: a planted side column equal to the outcome is served as [9.0, 9.0, -9.0]); 3 registry families use it and only tennis_schedule_density.matches_last_7d has been audited (0.0000 of 400 players' rows include the match itself). Bar: a per-column self-inclusion audit for all 9 side-served columns, recomputing each from its own source under a strictly-prior convention and reporting the share of rows that differ; any column that differs is demoted to prior or dropped | S85 S118 | OPEN (new 2026-09-03) |`

---

## 3. THE INFORMATIVE-TICK TRIPLE (`eval_gate/tick_informative.py`)

### F5 -- `is_dup` misses a duplicate written in a different timestamp spelling

`out.duplicated(subset=[game_col, ts_col])` (:75) compares raw strings.
Probe (`p6_tick.py`): four ticks of one game, rows 0 and 1 the SAME instant written
`...T00:00:00Z` and `...T00:00:00+00:00`, rows 2 and 3 an exact string repeat.

```
n_dup = 1   (correct: 2)
```

Blast radius: `n_informative` overstated, so the second published CI (`ci95_informative`) is quoted
on a row set that still holds duplicates. Wrong n, mildly **false AHEAD**.

### F6 -- `flag_ticks` is order-dependent and `requote()` does not sort

`_held` (:33-42) uses a groupby-`shift(1)` on the frame's existing row order.
`attach_informative_summary` sorts first (:127); `requote` does NOT (:229).
Probe (`p6_tick.py`), the same six rows in tick order and in store order:

```
flag_ticks(tick order  )  n_informative = 6   n_held_market = 0
flag_ticks(out of order)  n_informative = 2   n_held_market = 4
```

LATENT on the three archived artifacts: `s80_player_grain_2026-09-03.csv` is NOT globally sorted by
(game, ts) but IS monotonic in ts within each game, which is what `groupby.shift` needs, so the
published S87 re-quote is unaffected. Contract defect on the read path.

Register-row candidate:
`| S137 | harness | THE INFORMATIVE-TICK FLAGS ARE STRING-EXACT AND ORDER-DEPENDENT: tick_informative.flag_ticks:75 flags a duplicate by raw (game, ts) string so the same instant spelled ...Z and ...+00:00 reads as two ticks (measured n_dup 1 where 2 is correct), and _held:33-42 shifts on the frame's row order while requote:229 -- unlike attach_informative_summary:127 -- never sorts (measured n_informative 6 vs 2 on the same six rows). Fix: normalise ts with pd.to_datetime(utc=True) before duplicated(), and sort by (game, ts) inside flag_ticks itself rather than in one of its two callers. Bar: the two reproduced probes agree, and the three archived S87 re-quotes reproduce their published CIs unchanged | S87 S118 | OPEN (new 2026-09-03) |`

---

## 4. THE REAL-GAME SPLIT (`eval_gate/real_game_split.py`)

### F4 -- a 1-inning feed regression manufactures an extra "real game"

`_boundary` (:84) opens a new real game on ANY inning decrease, with no minimum time gap and no
minimum drop. Run over the LIVE store (`p5_split.py`, `p5b.py`, 227 tickers / 78,986 ticks):

```
published: n_game_ids 227  n_real_games 392  n_multi 122
           boundary_reasons {"inning_decrease": 156, "score_reset": 6, "ts_gap": 3}

boundaries fired: 165
boundaries whose PREVIOUS tick is < 10 minutes earlier: 32   (all with an inning drop <= 2)

  KXMLBGAME-26JUL011335DETNYY   gap  0.02 min   inning 5 -> 4
  KXMLBGAME-26JUL011840PITPHI   gap  0.53 min   inning 7 -> 7   (score_reset)
  KXMLBGAME-26JUL012140SFAZ     gap  0.15 min   inning 6 -> 5
  KXMLBGAME-26JUL021940TBKC     gap  0.07 min   inning 8 -> 7
  KXMLBGAME-26JUL032138BOSLAA   gap  0.20 min   inning 4 -> 3
  ... 27 more

n_real_games as published 392 ; without the < 10-minute false splits 360
DM CI half-width scales ~ 1/sqrt(G): 360 -> 392 clusters narrows every interval by 4.2 pct
```

A new real game cannot begin 1-13 seconds after the previous one's last tick. The genuine
doubleheader / next-night splits (the >5 h ones, e.g. DETNYY seq 1 ending 01:38 and seq 2 starting
17:39) are correct; the near-instant ones are scoreboard regressions.
Blast radius: **false AHEAD** (every MLB in-game CI 4.2 pct too narrow) + wrong n (392 vs ~360).

### F18 -- the `ts_gap` rule silently disables itself on an epoch-seconds timestamp

`_ts` (:66-77) parses only ISO strings and returns None on anything else. With a numeric `ts`
column -- the shape `nba_checkpoints_full.parquet` and the NBA in-play stores use -- every stamp is
None, so the gap rule can never fire and `sort_values([game, _ts_parsed])` degenerates to input
order. Silent: `boundary_reasons` simply contains no `ts_gap` key.

Register-row candidate:
`| S138 | harness | real_game_split SPLITS ONE REAL GAME ON A 1-INNING FEED REGRESSION: _boundary:84 opens a new real game on ANY inning decrease with no minimum gap -- measured on the live 227-ticker store, 32 of 165 boundaries fire less than 10 minutes (mostly 1-13 SECONDS) after the previous tick, inflating n_real_games from ~360 to the published 392 and narrowing every MLB in-game clustered CI by 4.2 pct; separately _ts:66-77 returns None on an epoch-seconds ts, silently disabling the ts_gap rule. Fix: require BOTH an inning decrease AND a minimum inter-tick gap (>= 20 min) before opening a segment, and raise when no ts in the frame parses. Bar: the 32 near-instant boundaries disappear, the 3 genuine >5 h splits survive, and S106/S116 re-quote their CIs on the corrected cluster count | S106 S118 | OPEN (new 2026-09-03) |`

---

## 5. THE CLOSE INCUMBENTS (`eval_gate/close_join_nba_mlb.py`)

### F1 -- the NBA `first_inplay_tick` "close" already knows the opening possession, and nothing filters it

The row asked directly whether a tick 21 s after tip is contaminated. Measured on
`nba_checkpoints_full.parquet` (`p1_close.py`, `p1c.py`), 1,591 first traded period-1 ticks:

```
close_sec_after_tip: median 21.0  mean 22.7  p90 45.0  p99 60.0  max 391.0
share <= 30 s: 0.6771     (so 32.3 pct of the "closes" are 30-391 s of live play after tip)

SCORE ALREADY ON THE BOARD AT THE 'CLOSE' TICK
  share with any points scored        0.4349
  share with margin != 0              0.3953
  |margin| mean 0.908   max 6
  points on board  mean 1.29   p90 4   max 37
  among ticks <= 30 s after tip, share with points on board   0.2836
```

So the 30-second window is not a fix: 28.4 pct of the ticks INSIDE it already carry a score.

Head-to-head on the 328 games where a genuine pregame close and the in-play tick BOTH exist
(`p1b.py`):

```
Brier pregame_last_tick_before_commence  0.185063
Brier first_inplay_tick                  0.184340
delta (pregame - inplay)                +0.000722   DM p=0.5019 ci95 [-0.001392, +0.002837]

  <= 30 s  n=219  brier_pregame 0.190792  brier_inplay 0.191469  delta -0.000676
  >  30 s  n=109  brier_pregame 0.173550  brier_inplay 0.170017  delta +0.003533
```

Pooled, the in-play tick is NOT measurably sharper (an honest null at n=328). Split by elapsed
time it is, exactly where contamination predicts: on the >30 s subset it beats the true pregame
close by +0.0035. And `close_within_30s` -- the escape hatch the module says "the reader applies" --
is referenced by NO consumer: `grep -rn close_within_30s` outside `close_join_nba_mlb.py` hits only
the S112 memo prose. S113 (`s112_rescore_vs_close.py:65-68`) reads `p_close` with no filter at all.
Blast radius: **false NULL** -- the reference is sharper than a real close, so a model is measured
against a bar that partly contains the answer.

Register-row candidate:
`| S139 | harness | THE NBA "CLOSE" IS A POST-TIP IN-PLAY QUOTE AND NOTHING FILTERS IT: 43.5 pct of first_inplay_tick closes already have points on the board (|margin| up to 6, up to 37 points, close_sec_after_tip up to 391 s) and 28.4 pct of the <=30 s subset does too; on the 328 games where both closes exist the in-play tick beats the genuine pregame close by +0.0035 Brier on the >30 s subset (pooled +0.000722, CI straddles zero); close_within_30s is read by NO consumer -- s112_rescore_vs_close.py:65-68 takes p_close unfiltered. Fix: default every close consumer to close_source == pregame_last_tick_before_commence, make the in-play fallback opt-in and labelled in the artifact, and add close_score_on_board to CLOSE_COLUMNS. Bar: S113's promotion-survival table re-run on the pregame-only subset with the n it costs stated honestly | S112 S113 S118 | OPEN (new 2026-09-03) |`

### F12 -- the 0.500 placeholder rule deletes genuine MLB pick'em closes

`_drop_placeholder` (:67-71) is applied to the DEVIGGED MLB value (:212), where 0.500 is the
honest answer for any symmetric two-sided quote -- not only for an untraded listing.
Probe (`p12.py`) through the real `cjm._devig`:

```
prob_home 0.52 prob_away 0.52 -> p_close 0.500000   <-- DROPPED as placeholder_half
prob_home 0.55 prob_away 0.48 -> p_close 0.533981       kept
prob_home 0.50 prob_away 0.50 -> p_close 0.500000   <-- DROPPED as placeholder_half
```

Live count: `mlb_close()` reports `placeholder_half: 19` real events dropped out of 894 kept.
Blast radius: wrong n, and the close-covered corpus is biased AWAY from toss-ups, which is where a
model and a market are most likely to differ.

### F16 -- an ambiguous pregame close silently downgrades a game to the in-play tick

`_drop_ambiguous` (:74-78) removes BOTH rows of a duplicated `event_id` inside
`nba_pregame_close`, and `nba_close` then falls through to the in-play source with no flag
(`p12.py`):

```
G1's pregame close was ambiguous (2 venue rows) ->
   G2  pregame_last_tick_before_commence  0.70
   G1  first_inplay_tick                  0.58    <-- no field records that its pregame close was dropped
```

Register-row candidate:
`| S140 | harness | THE CLOSE ATTACH DROPS GENUINE PICK'EM QUOTES AND SILENTLY DOWNGRADES AMBIGUOUS ONES: _drop_placeholder (close_join_nba_mlb.py:67) is applied AFTER the MLB devig (:212), where 0.500 is the honest value of any symmetric two-sided quote -- reproduced through cjm._devig (0.52/0.52 -> 0.500 DROPPED), 19 live MLB events lost of 894 kept, biasing the close-covered corpus away from toss-ups; and _drop_ambiguous (:74) removing a duplicated pregame close makes nba_close fall through to first_inplay_tick with no field recording it. Fix: apply the placeholder rule to the RAW one-sided quote only (never post-devig) and add a close_downgraded_from column. Bar: the 19 MLB rows return, the by_source counts move, and no verdict in S112/S113 changes sign | S112 S118 | OPEN (new 2026-09-03) |`

---

## 6. FAMILY ALIASES AND K ACCOUNTING (`eval_gate/ledger.py`, `eval_gate/family_bars.py`)

Probe `p9_alias.py`, over a 3-row synthetic ledger (the real 18-row ledger was never opened):

```
A. baseline  next_k_family("ingame_arms_mlb")                              = 3   correct
B. a RENAME to "ingame_arms_mlb_v2" with no alias added                    = 1   K RE-ZEROED
C. add alias ingame_arms_mlb -> ingame_arms_mlb_v2 (a 2-hop chain):
     resolve("ingame_mlb_arms")  = ingame_arms_mlb        (stops at hop 1)
     resolve("ingame_arms_mlb")  = ingame_arms_mlb_v2
     next_k_family("ingame_arms_mlb_v2")                                   = 1   correct 3
D. a pre-S13 row (family set, k_family absent)  next_k_family("soccer_gate") = 2  correct 3
```

* **F8** -- `resolve_family` (family_bars.py:114-116) is a single `dict.get`, so a rename with no
  alias re-zeroes the family's K to 1. That is the exact hazard S89 was written to close.
* **F9** -- alias chains are NOT transitive. The S89 design is "rename, then add an alias"; doing
  that a second time silently ORPHANS the first hop's historical charges. Worse than F8, because
  it looks like the fix was applied.
* **F10** -- `next_k_family` (ledger.py:155) skips rows with `k_family is None`, and `load_fwer`
  fills that field with None for every pre-S13 row (`FWER_OPTIONAL_FIELDS`, :121). A historical
  charge that recorded a family but not a k_family is not counted. Note `family_bars.k_family`
  (:126-131), the READ path, does NOT have this filter -- so the two K counters disagree on such a
  row.

Blast radius: an undercounted within-family K means a **too-lenient BH bar** -> **false AHEAD**.

Register-row candidate:
`| S141 | harness | A FAMILY RENAME STILL RE-ZEROES K, ALIAS CHAINS ARE NOT TRANSITIVE, AND THE TWO K COUNTERS DISAGREE: reproduced on a synthetic ledger -- next_k_family = 1 instead of 3 after a rename with no alias, = 1 instead of 3 when a second alias hop is added (resolve_family, family_bars.py:114-116, is a single dict.get), and = 2 instead of 3 when a pre-S13 row carries family but k_family None (ledger.py:155 filters on it; family_bars.k_family:126-131 does not). Fix: resolve aliases to a fixed point (loop until stable, refusing a cycle), count on family is not None rather than k_family is not None, and add a test that the two counters agree on every ledger row. Bar: the three probes return 3, and k_family over the unmodified 18-row ledger is unchanged for all 39 frozen families | S89 S13 S118 | OPEN (new 2026-09-03) |`

---

## 7. THE POD RUNNER'S CLAIM AND LEASES (`foundry/results_db.py`)

Probe `p10b.py`, two `ResultsDB` handles on one scratch sqlite file:

```
runner A claims                                        : 3 rows   (LEASE_SECONDS = 900, no renew API)
runner B claims while A holds the lease                : 0 rows   correct -- BEGIN IMMEDIATE works
runner B claims 901 s later while A is STILL running   : 3 rows   BOTH runners now own the same rows

legacy hypothesis row with sport NULL:
  claim(tier="T0", sport="mlb") -> 0      claim(tier="T0", sport=None) -> 1
```

* **F11** -- there is no renew/extend API (`dir(results_db)` has none). The lease is a fixed 900 s
  from the claim, and `reap_expired` is called inside every `claim` (:288) and reaps GLOBALLY --
  across sports and tiers. Any pass that outruns 900 s is silently double-claimed by the next
  runner of any sport. The S16 memo's own timing (0.46 s per 800-row screen, batch 50 ~= 23 s)
  keeps the pregame runner inside the lease today, but `walk_forward` is O(n^2) in rows and
  `--screen-rows` is the exposed knob.
* **F12b** -- a hypothesis whose stored `sport` is NULL is unreachable to any sport-bound runner
  and reachable only to an unbound one; `results_db.py:112` records that reconstruction previously
  lost this field. Such rows sit queued forever. Wrong n, not a false verdict.

The mutual-exclusion probe **PASSED**: within the lease, `BEGIN IMMEDIATE` genuinely prevents two
claimers from taking the same row.

Register-row candidate:
`| S142 | harness | THE SCREEN QUEUE'S 900-S LEASE HAS NO RENEWAL AND reap_expired IS GLOBAL: reproduced -- runner B claims the same 3 hypotheses 901 s in while runner A is still working (results_db.py:264-300, LEASE_SECONDS:55, no renew/extend API), and a hypothesis stored with sport NULL is claimable only by an UNBOUND runner (claim(sport="mlb") -> 0, claim(sport=None) -> 1), so a sport-bound pod runner can never drain it. Fix: a renew(hashes) that pushes lease_until forward, called once per batch inside the pass, and a startup assertion that no queued hypothesis has a NULL sport. Bar: the double-claim probe returns 0 rows for runner B, and the pod queue reports 0 sport-NULL queued rows | S16 S66 S75 S118 | OPEN (new 2026-09-03) |`

---

## 8. PROBES THAT RAN AND PASSED (no finding)

Recorded so the bar is honest about coverage, not only about hits.

| # | Probe | Result |
|---|-------|--------|
| P-a | `assert_tick_asof` against a builder that reads the NEXT tick (`p2_tier.py`) | correctly raises `TickTimeLeak` |
| P-b | the embargo on ISO-Z and on `+00:00` stamps (`p4_embargo.py`) | correct `NO_TRAIN` on both; the live MLB store and `s102`'s re-format are both ISO-Z |
| P-c | `n_eff` -- `gap_effective_n.intraclass_correlation` vs `ingame_screen_nba._icc` on an unbalanced design (40 x 2 + 5 x 400 ticks) (`p7_neff.py`) | rho 0.996921 vs 0.996309, n_eff 45.14 vs 45.16 (1.00x) -- the two implementations agree; both land on the cluster count |
| P-d | `n_eff` when every game has ONE tick (`p6_tick.py`) | rho forced to 0, `n_eff = n = n_games = 50` -- correct, not inflated |
| P-e | S116's "the two screen corpora are date-disjoint" claim (`p11.py`) | HOLDS: nba 2024-12-09..2026-06-10, mlb 2026-07-04..2026-07-05 |
| P-f | S114's nested selection -- is it actually nested? (source read) | YES: `inner_split` splits the OUTER TRAIN window by game-first date and re-purges (`s114:69-77`); the outer test is never screened |
| P-g | leakage through S114's FDR step | NONE: the `bh_within_family` result only decorates `screen_records` (`s114:168-170`); `select_topk` ranks on the raw inner p, never on the adjusted one |
| P-h | `context.attrs` survival through `[cols]`, `concat`, `reset_index`, `merge` (`p14.py`) | attrs survive all four in this pandas build, so the MLB alias key and the `served_rows` window are not silently lost |
| P-i | `tennis_schedule_density.matches_last_7d` self-inclusion, 400 players (`p16.py`) | 0.0000 of rows include the match itself |
| P-j | `results_db.claim` mutual exclusion inside the lease (`p10b.py`) | `BEGIN IMMEDIATE` holds: runner B gets 0 rows |

One partial: `_refuse_all_nan` (`asof_supply.py:276-284`) treats `served_rows = 0` as "no window
declared" and falls back to the whole index (`if not rows`), and the window is the LAST N rows of
the supplied index, which assumes the index is date-sorted. Neither produced a wrong verdict on the
live binder (`ScreenBinder` sets `served_rows` to a positive `rows` and builds `frame` in date
order, `screen_predictor.py:238-241`), so it is filed as a note, not a finding.

---

## 9. SELF-CHECK (contract sections B and Q)

* B2 -- nothing was rewritten; this lane is read-only and added exactly one file.
* B4/B10 -- no bar moved, no seed changed, no artifact regenerated.
* Q3 -- `BAR = 0.004` was read, never redefined.
* Q6 -- calibration language only; the memo was token-scanned and carries no currency, return-rate, stake-size or edge vocabulary.
* Q8 -- every finding is stated as a REPRODUCTION with its input and its wrong output, and the ten
  probes that found nothing are listed with the same weight.
* None of the six retracted figures listed in `.claude/rules/no-edge-claims.md` appears here (the
  file was scanned for each; zero hits outside this sentence).
* The FWER ledger was not opened; `family_bars.FAMILY_ALIASES` was mutated only inside a probe
  process and restored within it.

Count: **14 reproduced findings, 10 probes passed, 1 note. 12 register-row candidates
(S131-S142).** Nothing was fixed.
