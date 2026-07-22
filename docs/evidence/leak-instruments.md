# Leakage-Catching Instruments -- the harnesses built to refute my own results

> Leakage is the default failure mode of sports ML. Every result in this repo passes through
> purpose-built instruments designed to *refute* it, not confirm it. The single truth-source
> for any figure is [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) (sections 2C and
> 2E). For what these instruments actually caught -- the retracted headline numbers -- see
> [the retraction story](retraction-story.md).

---

## The claim

In sports forecasting, a good-looking number is almost always a leak until proven otherwise:
a feature that peeks at the future, a grader that reads the market instead of the model, a
grid search that memorizes its holdout, a single lucky calendar window. So the machinery that
matters is not any metric -- it is the set of instruments that assume every result is wrong and
try to break it. This page documents those instruments and the exact committed path for each.
What they caught is told in [retraction-story.md](retraction-story.md); this page is the how.

---

## The instruments

**Walk-forward CV with an assertion-level per-fold leak guard.** Catches lookahead across the
train/test boundary -- the leak where any test-window information reaches training. The
expanding-window backtester asserts `max_train_date < min_test_date` on *every* fold, so a
temporal leak raises rather than silently inflating the score. Path:
`src/prediction/walk_forward_backtester.py`.

**Overfit-gap CI gate.** Catches the train-beats-test overfit that a single reported number
hides. `scripts/run_walk_forward.py --gate` compares train and out-of-sample performance and
exits nonzero when the gap exceeds tolerance, so an overfit fails the build instead of shipping.

**Truncation-invariance test for streaming features.** Catches in-game lookahead: a feature
computed at time T that accidentally depends on events after T. The test re-featurizes a
truncated event stream and asserts the past rows are byte-identical with or without the future
events present -- a property no leaking feature can satisfy. Path:
`tests/test_ingame_leak_free.py`.

**Multi-corpus calibration acceptance gate.** Catches single-window overfit masquerading as a
durable gain -- a calibration that beats raw on one lucky corpus but not in general. A candidate
calibration only ships if it beats raw on at least two independent out-of-sample corpora, with a
minimum-sample filter, a least-intervention tie-break, and a strict train-before-eval guard.
Path: `scripts/validate_calibration_multicorpus.py`.

**Hard-coded corrective regularization in the prop CV split.** Catches the leaky-grid-search
overfit at its source and makes the correction permanent. The module documents the measured
train-vs-holdout collapse on the steals/blocks models and applies regularization that takes
precedence over the stale tuned parameters, so the mistake cannot silently reappear. Path:
`src/prediction/prop_cv_split.py`.

**Append-only shadow logger + settlement.** Catches survivorship bias -- the distortion from
only ever scoring the bets you took. The shadow logger records every evaluation, passed *and*
blocked, and the settlement engine later scores them against final box scores, so thresholds
are calibrated against a counterfactual dataset rather than a filtered one. Paths:
`src/prediction/shadow_logger.py`, `src/prediction/settlement.py`.

**The ship gate built to refute, not confirm.** Catches the false-positive signal -- a
candidate that looks predictive by chance. Before any signal ships, `src/loop/gate.py` runs an
expanding walk-forward (all folds must improve), a null-shuffle permutation control requiring
z >= 3, an ablation against the full model, train-median imputation, and a Benjamini-Hochberg
FDR correction for multiple comparisons. Most candidates correctly get rejected.

---

## Receipts

| Instrument | Leak class it catches | Committed path |
|---|---|---|
| Walk-forward CV + per-fold assertion | Temporal leak across train/test boundary | `src/prediction/walk_forward_backtester.py` |
| Overfit-gap CI gate | Train-beats-test overfit shipping silently | `scripts/run_walk_forward.py --gate` |
| Truncation-invariance test | In-game lookahead in streaming features | `tests/test_ingame_leak_free.py` |
| Multi-corpus calibration gate | Single-window overfit as false durability | `scripts/validate_calibration_multicorpus.py` |
| Corrective regularization | Leaky grid-search overfit reappearing | `src/prediction/prop_cv_split.py` |
| Shadow logger + settlement | Survivorship bias from scored-only bets | `src/prediction/shadow_logger.py`, `src/prediction/settlement.py` |
| Ship gate (permutation + ablation + FDR) | False-positive signal by chance | `src/loop/gate.py` |

---

## Reproduce (per-file only)

Run individual test files -- never the full suite.

```
# Truncation-invariance leak test for streaming features
python -m pytest tests/test_ingame_leak_free.py -q

# Multi-corpus calibration acceptance gate (its tests)
python -m pytest scripts/validate_calibration_multicorpus.py -q

# Walk-forward CI gate: exits nonzero on overfit
python scripts/run_walk_forward.py --gate
```

On a fresh clone the private corpora are absent, so the gated scripts print a pending state and
fall back to their recorded tables rather than fabricating a number.

---

## What they caught

These instruments are not decoration: they took apart four of this system's own headline
numbers -- a market-follow pregame ROI, a Q4-leaking win-probability Brier, a train-vs-holdout
prop overfit, and a regime-dependent assists edge. The full account, each catch traced to its
proof artifact, is in [the retraction story](retraction-story.md). The honest result they leave
standing is an efficient market and a break-even-minus-vig model -- which is exactly what a
validation framework built to refute is supposed to find.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
