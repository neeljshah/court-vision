# S200 Regime Key OOF

Preregistration: `docs/evidence/harness/S200_regime_key_oof_prereg_2026-09-04.md`.
Its pre-seal SHA-256 is
`BCDF43B637B3735078033ED47D9A1A21B1612FBB45BE5C694B72AB64AB4B4AFC`.

## Premise and result

The premise held: the default `buckets()` call globally ranks all supplied rows
and assigns T1/T2/T3. The existing default path re-measured all four S05
post-calibration ECE values with maximum absolute difference exactly 0.0. Each
train-only score used only earlier rows to set the scored row's confidence
tercile; every valid input row stayed in its denominator.

| Sport | Scored / input | Default ECE after | Train-key ECE after | Train minus default | Changed labels |
|---|---:|---:|---:|---:|---:|
| nba | 1,814 / 1,814 | 0.024843 | 0.022224 | -0.002618 | 57 |
| mlb | 39,162 / 39,162 | 0.008077 | 0.009216 | +0.001139 | 1,818 |
| soccer | 25,834 / 25,834 | 0.009302 | 0.009702 | +0.000400 | 613 |
| tennis | 41,886 / 41,886 | 0.008403 | 0.008807 | +0.000404 | 908 |

All four dropped-row counts are 0. The two higher train-key ECE results are
published as measured; no denominator or threshold changed.

## Reproduction artifacts

- Summary and both ten-bin tables per sport:
  `docs/evidence/S200_regime_key_oof_2026-09-04.json`
- Per-row paired predictions and squared losses, including cluster identifier
  and timestamp when supplied by the corpus:
  `docs/evidence/S200_regime_key_oof_{nba,mlb,soccer,tennis}_paired_2026-09-04.json`

The summary embeds each bin table, its zero self-reproduction difference, each
label-change count, all denominators, and the preregistration seal. The paired
archives retain every scored row for independent recalculation.

## Verification

`python -m pytest scripts/platformkit/eval_gate/test_s200_regime_key_oof.py -q -p no:cacheprovider`

Result: `2 passed`.

## NOT VERIFIED

- Corpus chronology remains positional where a date field is not supplied.
- This row changes only confidence-key assignment; the established small-regime
  global fallback remains unchanged.
- A null timestamp is preserved where the input corpus does not supply one.

## ATTEMPT 2

The correction keeps the default calibration report unchanged and moves 114
unchanged report helpers into `calibration_report_helpers.py`. The train-only
pass stable-sorts every corpus by `(event_date, corpus_unit, event_id)`, asserts
monotone dates, assigns every same-date row before advancing the confidence-key
state, and routes local calibration only after support from earlier dates meets
the existing minimum. The train-only arms use the existing strict expanding
utility with a 20-row block refit; every refit is fitted before its scored block.

All four denominators remain complete and all dropped-row counts remain zero.
The default ECE values retain maximum absolute difference 0.0 from the landed
S05 JSON, and both train-bin reproductions are 0.0.

| Sport | N | Row-position key ECE after | Date-group key ECE after | Date minus row | Changed labels |
|---|---:|---:|---:|---:|---:|
| nba | 1,814 | 0.021270 | 0.019514 | -0.001756 | 56 |
| mlb | 39,162 | 0.009316 | 0.009282 | -0.000034 | 1,822 |
| soccer | 25,834 | 0.009758 | 0.009538 | -0.000220 | 613 |
| tennis | 41,886 | 0.016604 | 0.016937 | +0.000333 | 1,819 |

Future-support sensitivity retains the raw ECE before value in each routing and
changes only the support available to the local-versus-global selection.

| Sport | Full-sample support ECE before/after | Prior-date support ECE before/after |
|---|---:|---:|
| nba | 0.053328 / 0.018310 | 0.053328 / 0.019514 |
| mlb | 0.005918 / 0.009558 | 0.005918 / 0.009282 |
| soccer | 0.106927 / 0.009746 | 0.106927 / 0.009538 |
| tennis | 0.038691 / 0.016744 | 0.038691 / 0.016937 |

Line counts for the four S200-touched Python files are:

| File | Physical lines |
|---|---:|
| `scripts/platformkit/eval_gate/calibration_report.py` | 277 |
| `scripts/platformkit/eval_gate/calibration_report_helpers.py` | 114 |
| `scripts/platformkit/eval_gate/s200_regime_key_oof.py` | 292 |
| `scripts/platformkit/eval_gate/test_s200_regime_key_oof.py` | 66 |

The summary JSON and every paired-row archive were refreshed by the same
sequential scorer. The paired archives retain the source row index, cluster,
timestamp, outcome, both calibrated predictions, both squared losses, both
confidence labels, and the label-change flag.

### NOT VERIFIED

- The fixed default paired predictions are retained from the prior artifact;
  the default code path and its landed JSON are unchanged, but this attempt did
  not independently rerun the full default per-regime scorer on all four
  corpora.
- Calendar dates do not provide an intra-date event order. Same-date rows are
  intentionally scored from the strictly earlier-date key state.
- No serving path, external corpus source, threshold, ledger, or feature flag
  was changed or evaluated.

### Focused verification

`python -m pytest scripts/platformkit/eval_gate/test_s200_regime_key_oof.py -q -p no:cacheprovider` - 4 passed

`python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` - 1 passed

`python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q -p no:cacheprovider` - 10 passed
