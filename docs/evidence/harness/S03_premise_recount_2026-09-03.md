# S03 tennis close join - FALSIFIED

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

Status: FALSIFIED at Q8 premise measurement. No harness change was made.

S34 label: `vintage: SYNTHETIC`. A real odds timestamp is not present in this
local check. No states or coverage-report JSON were produced because the
premise stop rule applied before implementation.

## Premise reproduction

The raw `event_id` merge used each tour's full winner-present match spine and
the local `data/domains/tennis/odds.parquet` file. It measured:

| corpus_unit | required joined / denominator | observed joined / denominator | observed join rate |
|---|---:|---:|---:|
| ATP | 25,831 / 30,616 | 25,898 / 30,616 | 84.40504514 pct |
| WTA | 8,028 / 11,270 | 8,054 / 11,270 | 71.29957507 pct |

Both observed numerators differ from the stated premise, so this pass stops as
FALSIFIED. The row-0 orientation check did reproduce the stated de-leaked
mapping: `b365w == b365_p2 == 2.62` and `b365l == b365_p1 == 1.44`.

## Commands and output

```text
python -
ODDS_ROWS 33952
ATP SPINE 30616 JOINED 25898 RATE 0.8440504514
WTA SPINE 11270 JOINED 8054 RATE 0.7129957507
ROW0 {"b365w": "2.62", "b365l": "1.44", "b365_p1": "1.44", "b365_p2": "2.62"}
ORIENTATION True True
```

The `python -` program read the three local parquet files, filtered each match
spine to `winner.notna()`, cast `event_id` to string on both sides, and used a
left merge with its merge indicator. It did not write data or cache files.

## Limit and coverage

The observed raw rates remain above the stated rate limits, but the premise
numerators are different. Under the prescribed premise-first rule, no
implementation, coverage report, per-year table, close-drop count, or test
execution follows this FALSIFIED result.

## NOT VERIFIED

- Tennis `JoinSpec`, de-leaked close selection, and the `close_column` suffix
  guard were not added.
- The S35 full-spine `by_corpus_unit` denominator correction was not applied.
- `gate_corpus_states` does not yet emit the S34 synthetic vintage field.
- `coverage_report("tennis")`, including its per-year table and price-drop
  counts, is unavailable because tennis is not yet a supported join sport.
- Neither requested pytest file was run, because no test file was added after
  the required premise stop.
- No deployment, charged trial, ledger write, scoring comparison, or prereg
  claim occurred.

## Contract self-check

- B1-B10: no production or harness code changed; no rows were excluded from a
  reported metric; no schema, reader, threshold, or deployment changed.
- Q1-Q2: no scored comparison or charged trial occurred.
- Q3: no bar was moved; this result is FALSIFIED rather than a changed target.
- Q4-Q5: no OOS comparison or AHEAD finding is asserted.
- Q6: this memo reports only join-coverage reproduction and contains no
  financial-performance claim.
- Q7: this is a deterministic full-spine reproduction, not sampled scoring.
- Q8: the premise was re-measured before implementation and the differing
  numerators are recorded above.
