# S228 Pregame Prop Close Upset

## Verdict

SCORABLE.  This read-only calibration evaluation follows
`docs/evidence/tracking/specs/S228_spec.md` and self-checks sections B and Q
of `docs/evidence/tracking/VERIFIER_CONTRACT.md`.  The sealed preregistration
is `S228_pregame_prop_close_upset_2026-09-04_attempt2_prereg.md`; its
sealed-text SHA-256 is `83115c8892c0d7a4e0fb511aea16b8670ccd8dab8e059c2ebf19003ffb249617`.
The same seal is embedded in the census and both paired-loss archives.
The route was run locally because both declared stores are local and read-only.

## Inputs and reproduction

| Input | Full path | Bytes | Read method |
|---|---|---:|---|
| Close payloads | `C:/Users/neelj/nba-track-a13/data/cache/cv_fix/closing_props` | 6,491,336 total | 77 JSON files, one at a time |
| Player boxscores | `C:/Users/neelj/nba-track-a13/data/domains/basketball_nba/player_boxscores.parquet` | 1,118,538 | selected columns after payload census |

No source over 300 MB was opened.  Nothing was written under `data/`; the
close payloads and boxscore source remain read-only.  Reproduce with:

```text
python -m scripts.platformkit.s228_pregame_prop_close_upset
```

The tidy table is
`S228_pregame_prop_close_upset_2026-09-04_tidy.csv` (3,876,106 bytes).  Its
schema is `game, commence_time, home_team, away_team, player, stat, line,
over_price, under_price, book, capture_ts, source_file`.

## Complete census

| Measure | Count |
|---|---:|
| Files discovered and parsed | 77 / 77 |
| Unparsed files | 0 |
| Game clusters | 77 |
| Distinct players | 357 |
| Distinct stats | 3 |
| Priced player-stat rows | 24,247 |
| Rows settled by exact game and normalized-player boxscore match | 21,052 |
| Settled game clusters | 65 |

Every source file has an explicit `parsed`, `row_count`, and `error` entry in
`S228_pregame_prop_close_upset_2026-09-04_census.json`; none is skipped.
The 65 settled clusters exceed the unchanged 30-cluster requirement.

## Calibration losses

The scored player-stat set has 14,231 rows.  It selects the closest-to-even
line per game, player, stat, and book from 16,399 canonical quotes; model and
devigged-market losses use the same 14,231 rows.  The paired archive is
`S228_pregame_prop_close_upset_2026-09-04_paired.csv` (3,779,778 bytes).
Values in brackets are deterministic 500-resample game-cluster intervals.

| Metric | Prior-only player distribution | Devigged close representation |
|---|---:|---:|
| CRPS | 2.436377 [2.340853, 2.553932] | 2.820141 [2.708352, 2.963321] |
| Pinball | 1.736526 [1.667927, 1.819625] | 1.524313 [1.464330, 1.593884] |
| Brier, P(Over closing line) | 0.277149 [0.269525, 0.283912] | 0.249064 [0.247501, 0.250643] |

The census JSON retains ten fixed reliability bins for each Brier probability
series, including zero-count bins.  The model distribution is strictly the
named player's boxscore values before the game's UTC date.  The close
representation uses the devigged Over probability on the two integer outcomes
adjacent to its half-point line.  These are calibration-loss descriptions only.

## Tail target

For every named player other than a game's pregame favourite scorer, the route
scores whether the named player outscores that favourite.  The favourite is the
highest closest-to-even player-points line.  The same 893 tail rows are used by
the prior-only empirical comparison and the sequential observed-base-rate
comparator.  The paired archive is
`S228_pregame_prop_close_upset_2026-09-04_tail_paired.csv` (168,878 bytes).

| Metric | Prior-only comparison | Observed-base-rate comparator |
|---|---:|---:|
| Log loss | 0.337126 [0.270485, 0.405764] | 0.464262 [0.386814, 0.553809] |

## Attempt 2 correction

The fresh process used the attempt-2 seal named above. It scores one whole
game cluster per chronological fold with a one-distinct-game-date-block
symmetric embargo. The route-specific helper is
`scripts/platformkit/s228_oos.py`; it routes every whole-game test fold through
the shared `cpcv_evaluate` evaluator, then retains only strict-past permitted
clusters for each as-of prior and its one-time paired-loss archive.

| Item | Rejected route | Attempt 2 route |
|---|---|---|
| Player-stat prior | Direct strictly-prior-date filter | Whole-game walk-forward fold; scored cluster purged and one date block on each side embargoed |
| Tail base rate | Updated after each row inside a game | Built only from eligible prior game clusters after their full clusters are complete |
| Q4 guard | No route assertion | Assertions reject embargoed training rows and a scored cluster in its own prior |
| CRPS model loss | 2.393644 | 2.436377 |
| Pinball model loss | 1.717132 | 1.736526 |
| Brier model loss | 0.272157 | 0.277149 |
| Tail model log loss | 0.333307 | 0.337126 |

## Contract self-check

- B1, B7, B9 and Q7: the census is exhaustive across all 77 files and reports
  all complete price pairs before settlement or scoring; game filename stem is
  the cluster unit.
- B2-B6: this is additive code and evidence with no callers, schema rename,
  gate, deployment, claim loop, or retired module.
- B8 and Q4: `walk_forward_folds` scores whole game clusters chronologically,
  purges the scored cluster, applies a symmetric one-date-block embargo, and
  asserts both the embargo and cluster-delayed-prior conditions. Player-history
  values are strictly prior, outside that embargo, and exclude the scored game.
- B10 and Q3: the only eligibility threshold is the unchanged 30 settled-game
  clusters.
- Q1: the preregistration seal above predates the final scoring run.  Q2 does
  not apply because this is an uncharged read-only comparison and no ledger was
  changed.  Q5 does not apply because this memo makes no cross-corpus claim.
- Q6: this memo uses calibration language only.  Q9: both paired-loss files
  preserve loss values, game cluster, target date, and as-of history counts;
  the sealed route reconstructs the distributions from the named source.

## Tests

```text
python -m pytest tests/platformkit/test_s228_pregame_prop_close_upset.py -q -p no:cacheprovider
2 passed
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed
```

## NOT VERIFIED

An independent verifier has not rerun this attempt-2 route from the committed
artifact set. This memo reports the local fresh-process result only.
