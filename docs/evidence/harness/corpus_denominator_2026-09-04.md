# S181 Corpus-Denominator Instrumentation

## Scope and premise

This is additive corpus instrumentation for `coverage_report`; it is not a scored comparison. No trial record was opened, no registry path was written, and no feature flag was changed.

Before the code change, `coverage_report("soccer")` returned `denominator=16322`, `joined=16322`, `unjoined=0`, and `join_rate=1.0`. Its six existing `by_corpus_unit` rates were each `1.0`. The reproduced local corpus spine has 25,834 rows and 25,834 distinct `event_id` values. Its SHA-256 is `e0d2f13e7a53b3ed578e81e38db82f14bb6d3a71e31a9c7cb636d5b4c7e92bc6`.

The independent ID-set calculation reads each small parquet separately: corpus IDs minus odds IDs is 9,512; odds IDs minus corpus IDs is 0. Nothing in the corpus spine is filtered by date, match status, or corpus unit.

## Full return comparison

The complete post-change return dictionaries are committed as [soccer JSON](s181_coverage_report_soccer.json) and [tennis JSON](s181_coverage_report_tennis.json). The pre-change complete dictionaries were executed from `282b7a5a1^:scripts/platformkit/eval_gate/close_join.py`; current dictionaries with only the five new top-level fields removed compare equal to those historic dictionaries, including every nested year and corpus-unit value.

| Sport | Historic full return | Current full return after removing new fields | New fields |
|---|---:|---:|---|
| soccer | identical | identical | `corpus_denominator`, `corpus_joined`, `corpus_unjoined`, `corpus_join_rate`, `by_corpus_unit_spine` |
| tennis | identical | identical | `corpus_denominator`, `corpus_joined`, `corpus_unjoined`, `corpus_join_rate`, `by_corpus_unit_spine` |

The historical comparison command printed `{'soccer': True, 'tennis': True}`. Soccer therefore retains its existing odds-side values: denominator 16,322, joined 16,322, unjoined 0, and join rate 1.0. Tennis retains ATP 25,764/30,616 and WTA 8,002/11,270 in its existing `by_corpus_unit` output.

## Corpus-spine result

`coverage_report("soccer")` now reports corpus denominator 25,834, corpus joined 16,322, corpus unjoined 9,512, and corpus join rate `0.6318030502438646`.

| Corpus unit | Corpus denominator | Corpus joined | Corpus join rate |
|---|---:|---:|---:|
| D1 | 3,366 | 2,142 | 0.6363636363636364 |
| E0 | 4,180 | 2,660 | 0.6363636363636364 |
| E1 | 6,072 | 3,864 | 0.6363636363636364 |
| F1 | 3,856 | 2,336 | 0.6058091286307054 |
| I1 | 4,180 | 2,660 | 0.6363636363636364 |
| SP1 | 4,180 | 2,660 | 0.6363636363636364 |

For tennis, the new corpus-spine fields equal the existing spine-first values: 41,886 denominator, 33,766 joined, 8,120 unjoined, and `0.806140476531538` join rate. ATP and WTA fields in the tennis JSON equal their existing `by_corpus_unit` values.

## Guard construct and tests

The new test constructs a two-row odds-side result where both rows join, plus a three-row corpus spine. Unit A is complete while unit B has one missing corpus row. This has corpus unjoined greater than zero and a unit rate of 1.0, and `coverage_report("soccer")` raises `ValueError` with `by_corpus_unit_spine` in its message.

Executed one file at a time:

```
python -m pytest scripts/platformkit/eval_gate/test_close_join_corpus_denominator.py -q
2 passed
python -m pytest scripts/platformkit/eval_gate/test_close_join_soccer.py -q
4 passed
python -m pytest scripts/platformkit/eval_gate/test_close_join_tennis.py -q
9 passed
```

`close_join.py` is 270 physical lines after the additive change.

## A5 reader check

The tracked-reader grep for `coverage_report(` found one existing code reader of this module: `scripts/platformkit/eval_gate/test_close_join_tennis.py`. It was not edited and passed unchanged. Other grep hits are definitions, documentation, or unrelated functions sharing the name.

## Contract self-check

- A2 and Q8: premise and corpus-minus-odds calculation reproduced locally before the change.
- A3: not applicable to this S-row; reproduction replaces an eye check.
- A5: reader check above; the existing reader passed unchanged.
- B1: the denominator is every corpus-spine row, including all 9,512 rows absent from odds.
- B2 and B10: only new fields were added; historical returns compare exactly after those fields are removed.
- B3 through B9: no gate routing, claim loop, deployment, module move, rendering sample, fitted comparison, or recycled-unit construction was introduced.
- Q1, Q2, Q4, Q5, and Q9: not applicable; this is not a scored comparison or forward claim.
- Q3: no threshold was changed.
- Q6: calibration language only.

## NOT VERIFIED

- Why the 9,512 corpus IDs lack odds rows is not determined by this instrumentation.
- The semantic orientation of the soccer target is unchanged and was not re-evaluated.
- No deployment or downstream consumer behavior was exercised.
