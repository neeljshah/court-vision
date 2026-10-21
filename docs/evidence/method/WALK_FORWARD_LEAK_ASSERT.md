# Method excerpt: the walk-forward leak assertion

Source (private path, line range, as of 626fe42f0):
- `src/prediction/walk_forward_backtester.py`, lines 122-142 (`run_walk_forward`)
- `tests/test_walk_forward_backtester.py`, lines 69-79 (`test_folds_are_chronological`)
- Public counterpart: `scripts/platformkit/eval_gate/walkforward.py`, lines 1-9, 31-32, 47-52,
  124-148; its test `scripts/platformkit/eval_gate/test_gate.py::test_vintage_assertion_fires_on_leak`

The engine is private; the excerpts below are verbatim so the claim can be read without it.

## 1. Private per-fold assertion (verbatim)

```python
    n = len(y)
    fold_specs = _chronological_folds(n, n_folds)

    fold_results: List[dict] = []
    all_y_true: List[np.ndarray] = []
    all_y_pred: List[np.ndarray] = []

    for fold_idx, (train_idx, test_idx) in enumerate(fold_specs):
        # --- leakage guard ------------------------------------------------
        max_train_date = dates_arr[train_idx[-1]]
        min_test_date = dates_arr[test_idx[0]]
        assert max_train_date < min_test_date, (
            f"Fold {fold_idx}: leakage detected -- "
            f"max train date {max_train_date} >= min test date {min_test_date}"
        )

        # --- fit + predict ------------------------------------------------
        model = model_factory()
        model.fit(X[train_idx], y[train_idx])
        y_pred = model.predict(X[test_idx])
```

(The source message uses a Unicode em dash where `--` appears above; ASCII substituted.)

Test that exercises it: `test_folds_are_chronological` in `tests/test_walk_forward_backtester.py`
re-checks `fold["max_train_date"] < fold["min_test_date"]` on every returned fold, and
`test_no_data_overlap_between_folds` checks that `min_test_date` strictly increases across folds.

## 2. Public counterpart: eval_gate/walkforward.py (verbatim)

```python
PURGE_HOURS = 48
EMBARGO_DAYS = 3

class LeakError(AssertionError):
    """Assertion-compatible failure for every eval-gate leak contract violation."""

        for s in states[:i]:
            ts = datetime.fromisoformat(s["state_ts"])
            if ts >= t:                                   # never look ahead (tie-safe)
                continue
            if _same_matchup(s, test) and (t - ts) < timedelta(days=EMBARGO_DAYS):
                continue                                  # embargo same matchup near boundary
            if _same_team(s, test) and (t - ts) < timedelta(hours=PURGE_HOURS):
                continue                                  # purge same-team back-to-back
            train.append(s)
        assert_vintage(test)                              # defense in depth (schema also checks)
```

The window is expanding: test state `i` trains on `states[:i]` minus the purged and embargoed
rows. `assert_vintage` raises `LeakError` (message prefixed `LEAK`) when any feature's availability
time is not strictly before the prediction time. Public test, runnable on the public tree:
`python -m pytest scripts/platformkit/eval_gate/test_gate.py -q`
(`test_vintage_assertion_fires_on_leak` plants an availability equal to `state_ts` and requires
the `LEAK` error).

## What it guarantees / what it does not

Guarantees: in the private backtester, no fold trains on a row dated on or after the first test
row (fold-level, by date). In the public harness, every test state is predicted only from strictly
earlier states, after the purge and embargo above, and a feature known too late fails the run.

Does not guarantee: that features inside a training row were themselves leak-free (the private
assertion checks row dates, not feature vintage; the public harness checks vintage only where
`feature_avail` is declared). It says nothing about whether a model is good, only that its score
is out of sample. Ties on equal dates fail the private assert by design (strict `<`).
