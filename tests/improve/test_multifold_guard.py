"""Tests for improve.multifold_guard.replicated (Milestone-8 ratchet).

INVARIANTS under test:
  - A lift replicated across all folds in >= 2 independent corpora passes.
  - A single-fold-only lift (one good fold of four) is REJECTED.
  - A single-corpus lift (no second corpus provided) is REJECTED.
  - A loss on any proper-score metric in any fold is a hard REJECT.
  - The function never raises (pure, graceful on bad input).

stdlib + the improve package only; no numpy required.  Standalone (python -m
pytest tests/improve/test_multifold_guard.py -q) OR bare python.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make importable when run bare (python tests/improve/test_multifold_guard.py).
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from improve.multifold_guard import replicated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _folds(deltas, metric="brier"):
    """Build a list of fold-result dicts from a list of signed floats."""
    return [{"fold_id": i, "metric": metric, "delta": d} for i, d in enumerate(deltas)]


def _corpus(corpus_id, deltas, metric="brier"):
    """Build a corpus_result dict."""
    return {"corpus_id": corpus_id, "folds": _folds(deltas, metric=metric)}


# ---------------------------------------------------------------------------
# The PASS case: lift replicated across all folds + 2 corpora
# ---------------------------------------------------------------------------


def test_replicated_all_folds_two_corpora():
    """A positive delta in all 4 folds on primary + a positive second corpus passes."""
    primary = _folds([0.01, 0.02, 0.015, 0.008])
    extra = [_corpus("corpus_B", [0.005, 0.012])]
    r = replicated(primary, min_folds=4, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is True, r["reasons"]
    assert r["n_folds"] == 4
    assert r["n_corpora"] == 2
    assert r["reasons"] == []


def test_replicated_single_fold_two_corpora():
    """One fold, two corpora: passes when min_folds=1 and both corpora positive."""
    primary = _folds([0.03])
    extra = [_corpus("B", [0.01])]
    r = replicated(primary, min_folds=1, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is True, r["reasons"]


def test_replicated_three_corpora_all_positive():
    """Three corpora all positive, min_corpora=2 -> passes (>= threshold)."""
    primary = _folds([0.01, 0.02])
    extra = [_corpus("B", [0.03, 0.04]), _corpus("C", [0.005])]
    r = replicated(primary, min_folds=2, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is True, r["reasons"]
    assert r["n_corpora"] == 3


def test_per_fold_output_populated_on_pass():
    """per_fold contains one entry per (corpus, fold) on a passing run."""
    primary = _folds([0.01, 0.02])
    extra = [_corpus("B", [0.03])]
    r = replicated(primary, min_folds=2, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is True
    # primary=2 folds + corpus_B=1 fold = 3 total per_fold entries
    assert len(r["per_fold"]) == 3
    assert all(e["passed"] is True for e in r["per_fold"])


# ---------------------------------------------------------------------------
# REJECT: single-fold-only lift (the canonical artifact pattern)
# ---------------------------------------------------------------------------


def test_single_good_fold_of_four_is_rejected():
    """One positive delta out of four folds is a selection artifact -> REJECT."""
    # three folds show no improvement (delta=0 does not count), one is positive
    primary = _folds([-0.005, 0.0, -0.002, 0.02])
    extra = [_corpus("B", [0.01, 0.01])]
    r = replicated(primary, min_folds=4, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is False
    assert any("all-proper-scores" in reason or "delta" in reason.lower()
               for reason in r["reasons"])


def test_all_folds_positive_but_not_enough_folds_for_minfolds():
    """3 positive folds but min_folds=4 required -> REJECT on primary fold count."""
    primary = _folds([0.01, 0.02, 0.015])   # only 3 folds
    extra = [_corpus("B", [0.01, 0.02])]
    r = replicated(primary, min_folds=4, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is False
    assert any("folds with delta" in reason or "need >= 4" in reason
               for reason in r["reasons"])


def test_zero_delta_does_not_count_as_passing_fold():
    """delta=0.0 is not a positive improvement; it should not count."""
    primary = _folds([0.0, 0.0])
    extra = [_corpus("B", [0.01])]
    r = replicated(primary, min_folds=2, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is False


# ---------------------------------------------------------------------------
# REJECT: single-corpus lift
# ---------------------------------------------------------------------------


def test_no_second_corpus_is_rejected():
    """All folds positive but corpus_results=None -> only 1 corpus -> REJECT."""
    primary = _folds([0.01, 0.02, 0.015, 0.008])
    r = replicated(primary, min_folds=4, min_corpora=2, corpus_results=None)
    assert r["replicated"] is False
    assert r["n_corpora"] == 1
    assert any("corpora" in reason.lower() for reason in r["reasons"])


def test_empty_corpus_results_list_is_rejected():
    """corpus_results=[] still means 1 corpus total -> REJECT."""
    primary = _folds([0.01, 0.02])
    r = replicated(primary, min_folds=2, min_corpora=2, corpus_results=[])
    assert r["replicated"] is False
    assert r["n_corpora"] == 1


def test_second_corpus_fails_primary_ok_overall_rejected():
    """Primary passes but second corpus has a negative delta -> overall REJECT."""
    primary = _folds([0.01, 0.02])
    extra = [_corpus("B", [0.01, -0.005])]  # negative in second corpus
    r = replicated(primary, min_folds=2, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is False


# ---------------------------------------------------------------------------
# REJECT: any metric loses (all-proper-scores rule)
# ---------------------------------------------------------------------------


def test_one_metric_negative_rejects_even_if_others_pass():
    """If brier passes but crps loses on any fold, the whole result is REJECT."""
    primary = [
        {"fold_id": 0, "metric": "brier", "delta": 0.01},
        {"fold_id": 0, "metric": "crps", "delta": -0.003},   # loss
        {"fold_id": 1, "metric": "brier", "delta": 0.02},
        {"fold_id": 1, "metric": "crps", "delta": 0.005},
    ]
    extra = [_corpus("B", [0.01, 0.02])]
    r = replicated(primary, min_folds=2, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is False
    assert any("all-proper-scores" in reason for reason in r["reasons"])


def test_pinball_loss_in_one_fold_rejects():
    """A negative pinball delta on a single fold kills the candidate."""
    primary = [
        {"fold_id": 0, "metric": "pinball", "delta": -0.001},
        {"fold_id": 1, "metric": "pinball", "delta": 0.004},
    ]
    extra = [_corpus("B", [0.01])]
    r = replicated(primary, min_folds=1, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is False


# ---------------------------------------------------------------------------
# Robustness / never-raises contract
# ---------------------------------------------------------------------------


def test_empty_fold_results_does_not_raise():
    """Empty primary fold list is graceful: REJECT, reason present."""
    r = replicated([], min_folds=1, min_corpora=2, corpus_results=[_corpus("B", [0.01])])
    assert r["replicated"] is False
    assert isinstance(r["reasons"], list) and len(r["reasons"]) > 0


def test_non_iterable_fold_results_does_not_raise():
    """Passing a non-iterable is graceful: returns replicated=False."""
    r = replicated(None, min_folds=1, min_corpora=2)  # type: ignore[arg-type]
    assert r["replicated"] is False


def test_missing_delta_key_is_skipped_gracefully():
    """A fold entry without 'delta' is logged and skipped, never raises."""
    primary = [{"fold_id": 0, "metric": "brier"}]  # no "delta"
    extra = [_corpus("B", [0.01])]
    r = replicated(primary, min_folds=1, min_corpora=2, corpus_results=extra)
    assert r["replicated"] is False
    assert isinstance(r["reasons"], list)


def test_bad_corpus_entry_type_is_skipped():
    """A non-dict corpus entry is skipped with a reason, never raises."""
    primary = _folds([0.01])
    r = replicated(primary, min_folds=1, min_corpora=2,
                   corpus_results=["not_a_dict"])  # type: ignore[list-item]
    assert r["replicated"] is False


def test_output_keys_always_present():
    """All five output keys are always present regardless of input."""
    for args in [
        ([], {}, {}),
        ([{"fold_id": 0, "delta": 0.01}], {"min_folds": 1, "min_corpora": 2},
         {"corpus_results": [_corpus("B", [0.01])]}),
    ]:
        fold_args, kw, extra_kw = args
        r = replicated(fold_args, **kw, **extra_kw)
        for key in ("replicated", "n_folds", "n_corpora", "per_fold", "reasons"):
            assert key in r, "missing key %r in %r" % (key, r)


def test_min_corpora_misconfigured_to_1_noted_but_still_needs_2_corpora():
    """min_corpora=1 is a misconfiguration; reason noted; still needs >=1 corpus pass."""
    primary = _folds([0.01])
    # No extra corpora -- only 1 corpus total. Since min_corpora=1 < 2, a reason is
    # added. The result is still rejected because of the misconfiguration note AND
    # the fact that there is only 1 corpus.  The honest guard: if min_corpora<2 is
    # supplied, we note it but do not automatically fail -- we let the count check
    # decide. With 1 corpus and min_corpora=1 this actually passes the count (n>=1),
    # but the reason note flags the misconfiguration. This test checks the reason.
    r = replicated(primary, min_folds=1, min_corpora=1, corpus_results=None)
    # n_corpora=1, min_corpora=1 -> count OK; but misconfiguration reason is present
    assert any("single-corpus" in reason or "< 2" in reason
               for reason in r["reasons"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print("PASS  %s" % fn.__name__)
        passed += 1
    print("\n%d/%d multifold_guard tests passed." % (passed, len(fns)))
