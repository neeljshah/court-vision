# Method excerpt: the two-corpus calibration acceptance rule

Source (private path, line range, as of 626fe42f0):
- `scripts/validate_calibration_multicorpus.py`, lines 62-63 (constants), 121-135
  (`_train_calibrator` train-before-eval cut), 306-363 (`apply_acceptance_rule`)
- Its tests: `tests/test_validate_calibration_multicorpus.py` (private)

The script trains a calibrator per stat on rows dated strictly before each corpus's evaluation
start, grades raw against calibrated at the blend weights in the loop below on each corpus, then
applies the rule below.

## Decisive lines (verbatim)

```python
MIN_TRAIN_ROWS = 500
MIN_CORPUS_N = 30  # minimum per-stat n in a corpus for it to count toward >=2

    train = df[(df["stat"] == stat) & (df["d"] < eval_start)].copy()

            n = cr["bets_by_stat"].get(stat, 0)
            if n < MIN_CORPUS_N:
                evidence.append(f"  {cr['name']}: n={n} < {MIN_CORPUS_N} (thin, not counted)")
                continue

            for a in (0.5, 1.0):
                ...
                    if calibrated_rank_metric > raw_rank_metric:  # identifiers renamed in this excerpt
                        cal_better_counts[a] += 1

        # Pick smallest a* that beats raw on >=2 corpora
        a_star = 0.0
        verdict = "RAW (calibration not robust -- stays disabled)"
        for a in (0.5, 1.0):
            if cal_better_counts[a] >= 2:
                a_star = a
```

(`...` marks elided lines inside the loop; the verdict string's `--` is a Unicode dash in the source.)

## The rule in words

- Must hold on at least two independent corpora: the calibrated output scores better than raw.
- Min-sample filter: a corpus with fewer than `MIN_CORPUS_N` rows for that stat is listed as thin
  and does not count toward the two; a stat with fewer than `MIN_TRAIN_ROWS` training rows is
  skipped.
- Least-intervention tie-break: the smallest blend weight that passes wins (the lower weight is
  tried first); if neither passes, the stat stays raw.
- Train-before-eval: calibrator training rows are filtered to `d < eval_start` per corpus.

The per-corpus comparison field is the script's graded-return column on the props corpora (the
script's graded-return ranking column, renamed in the excerpt above), used only to rank raw against calibrated. No
value of it is published here and none is claimed.

## Scope

This gate applies to calibrations, and the same two-corpus discipline is applied to candidate
signals by the signal scoreboards (every candidate was rejected; see JOB_EVIDENCE_PACKET.md). It
does not apply to every claim: the model-versus-market verdicts (pregame against the devigged close,
in-game against the live price) are each measured on a single corpus per sport and say so.

## What it guarantees / what it does not

Guarantees: a calibration is enabled only if it beats raw out of sample on two or more corpora that
each meet the sample floor, with the least intervention that passes, trained only on earlier rows.

Does not guarantee: that the corpora are independent beyond what the script's design notes assert;
that the comparison is a proper scoring rule (it is not a Brier score); or that a passed calibration
stays better on a later season. A pass is a gate result, not a performance claim.
