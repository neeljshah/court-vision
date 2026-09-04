# S207 in-game gap decomposition: FALSIFIED

## Verdict

FALSIFIED at step 0. S207 required stopping if an NBA or WNBA evidence
artifact already carried a Murphy decomposition or a per-path max-loser-WP
statistic. The named NBA artifact below carries both. No data store was opened,
no reporter or test was added, and no existing artifact was changed.

## Input inventory

All opened inputs were local JSON or Markdown artifacts; resolution is not
applicable.

| Path | Bytes | Resolution |
|---|---:|---|
| `docs/evidence/calibration-decomposition.md` | 7,605 | n/a (Markdown) |
| `scripts/platformkit/analytics_showcase/out/murphy_decomposition.json` | 8,382 | n/a (JSON) |
| `scripts/platformkit/analytics_showcase/out/state_conditioned_calibration.json` | 27,230 | n/a (JSON) |
| `docs/evidence/calibration/nba_ingame_baseline_2026-09-03.json` | 147,507 | n/a (JSON) |

## Re-measured published rows

The existing Murphy artifact reproduces the two stated rows from its stored
values. The gaps below are model minus market.

| Sport | n | Model Brier | Market Brier | Brier gap | Reliability gap | Resolution gap |
|---|---:|---:|---:|---:|---:|---:|
| mlb | 78,986 | 0.237684 | 0.206653 | +0.031031 | +0.006640 | -0.023496 |
| soccer_intl | 9,003 | 0.227887 | 0.142726 | +0.085161 | +0.039414 | -0.044576 |

The state-conditioned artifact's stored n-weighted ECE values also reproduce
from its per-bucket `n * calibration_error / sum(n)` calculation.

| Sport | n records | Model ECE | Recomputed model ECE | Market ECE | Recomputed market ECE |
|---|---:|---:|---:|---:|---:|
| mlb | 78,986 | 0.0790 | 0.0790 | 0.0591 | 0.0591 |
| soccer_intl | 9,003 | 0.3609 | 0.3609 | 0.2511 | 0.2511 |

## Named grep falsifier

Targeted command:

```text
git grep -n -i -E "murphy|max[-_ ]loser" -- 'docs/evidence/calibration/*nba*'
```

The searched calibration artifact store contains 14 files totaling 963,758
bytes. The command found `max_loser_wp` in
`docs/evidence/calibration/nba_ingame_baseline_2026-09-03.json` at line 46 and
`murphy` at line 1268 (with additional series occurrences later in the same
file).

Direct structural inspection of that 147,507-byte artifact found:

- `sport` is `nba` and `corpora.all` records 661 games and 79,554 ticks.
- `corpora.all.series.ladder_base.murphy` contains reliability, resolution, and
  uncertainty terms.
- `corpora.all.series.ladder_base.max_loser_wp` records 301 losing game paths,
  counts above 0.8 and 0.9, shares above those thresholds, and a `per_game`
  list of `{game, max_loser_wp}` values.
- The market and recalibration series in the same corpus carry the same Murphy
  and per-game max-loser-WP structure.

This is sufficient to falsify the premise's universal absence claim for NBA.
It does not assert that the existing artifact satisfies S207's requested
four-corpus reporter, tick-age axis, or all-four-corpus presentation.

## Stop record

Per S207 step 0, work stopped after the premise was falsified. There is no
test run because the specified reporter and its per-file test were not added.
The two existing landed showcase JSON files were not regenerated or modified.

## NOT VERIFIED

- The four-corpus reporter was not built or run after the step-0 stop.
- The tick-age axis was not built or run after the step-0 stop.
- The WNBA decomposition was not built or run after the step-0 stop.
- The specified per-file test was not built or run after the step-0 stop.

## Verifier self-check

- B1: ECE uses the named state-bearing subsets: MLB 52,646 of 78,986 raw
  records (26,340 skipped without state); soccer_intl 3,658 of 9,003 raw
  records (5,345 skipped without state).
- B2-B6, B8-B10: No implementation, schema, reader, deployment, or threshold
  change was made.
- Q1-Q5 and Q7-Q9: No new scored comparison was made; the premise result is a
  step-0 falsification.
- Q6: Calibration language only.
