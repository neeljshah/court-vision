"""Multi-fold replication guard (Milestone-8 ratchet).

A lift is a REAL improvement only when it holds in k-fold walk-forward AND in
>= 2 independent corpora.  A single good fold of four is a selection artifact;
a single-corpus lift may be an in-sample fluke.  This module enforces both
requirements together so the ratchet can never promote an artifact that only
passes one guard.

``replicated`` is the single public entry point.  It is pure (no I/O, no raises)
and sport-blind.  The ``delta`` in each fold/corpus result is signed:
  positive -> model BETTER than reference on that proper score.
  negative -> model WORSE  (the candidate should REJECT on this metric).

Hard-learned invariants embedded here:
  - A win on one metric and a loss on another is a REJECT (all-proper-scores rule).
  - Single-fold lifts are artifacts: require min_folds consecutive wins.
  - Single-corpus evidence is insufficient: require min_corpora >= 2.
  - The function never raises; bad inputs return replicated=False + a reason.

stdlib + numpy only; ASCII output.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Type aliases (kept lightweight; no dataclass so the dict is JSON-round-trippable)
# ---------------------------------------------------------------------------

# Each fold result dict must contain:
#   "delta"   : float  -- improvement vs reference (positive = better)
#   "metric"  : str    -- the proper score this delta is for (e.g. "brier")
#   "fold_id" : int or str -- which fold
# Optional keys tolerated and passed through to per_fold output.

FoldResult = Dict[str, Any]

# Each corpus result dict must contain:
#   "corpus_id" : str or int
#   "folds"     : List[FoldResult]
# All folds within a corpus are validated for replication before the corpus
# counts toward min_corpora.

CorpusResult = Dict[str, Any]


def replicated(
    fold_results: Sequence[FoldResult],
    *,
    min_folds: int = 1,
    min_corpora: int = 2,
    corpus_results: Optional[Sequence[CorpusResult]] = None,
) -> Dict[str, Any]:
    """Return a replication verdict for a proposed calibration lift.

    Parameters
    ----------
    fold_results:
        Per-fold results from a single primary corpus (k-fold walk-forward).
        Each dict must contain "delta" (float) and optionally "metric" (str)
        and "fold_id".  delta > 0 means the candidate beats the reference on
        that fold.  To report multiple metrics per fold, include one dict per
        (fold, metric) pair.

    min_folds:
        Minimum number of fold results with delta > 0 required for the primary
        corpus to count as replicated across folds.  Defaults to 1 (every fold
        must show improvement when only one fold is provided, consistent with the
        "single-fold lift is an artifact" rule -- if there are k>1 folds, the
        caller sets this to k).

    min_corpora:
        Minimum number of independent corpora (including the primary) that must
        each show a replicated lift.  Must be >= 2; passing 1 is accepted but
        will be noted as a misconfiguration and the result forced to not-replicated.

    corpus_results:
        Optional list of additional independent corpora.  Each dict must contain
        "corpus_id" and "folds" (a list of FoldResult).  The primary fold_results
        count as corpus index 0.  If None, only the primary corpus is evaluated,
        which means min_corpora >= 2 is not satisfiable -> REJECT.

    Returns
    -------
    dict with keys:
        replicated  : bool   -- True iff all gate conditions are met
        n_folds     : int    -- number of fold results evaluated in primary corpus
        n_corpora   : int    -- number of corpora evaluated (primary + extras)
        per_fold    : list   -- list of {fold_id, delta, metric, passed} dicts
        reasons     : list   -- human-readable strings explaining any REJECT
    """
    reasons: List[str] = []
    per_fold: List[Dict[str, Any]] = []

    # -- Input validation (never raise, degrade gracefully) -------------------
    if not isinstance(fold_results, (list, tuple)):
        try:
            fold_results = list(fold_results)
        except Exception:  # noqa: BLE001
            return {
                "replicated": False,
                "n_folds": 0,
                "n_corpora": 0,
                "per_fold": [],
                "reasons": ["fold_results is not iterable"],
            }

    if not isinstance(min_folds, int) or min_folds < 1:
        reasons.append(
            "min_folds must be a positive int; got %r" % (min_folds,)
        )
        min_folds = max(1, int(min_folds)) if isinstance(min_folds, (int, float)) else 1

    if not isinstance(min_corpora, int) or min_corpora < 1:
        reasons.append(
            "min_corpora must be a positive int; got %r" % (min_corpora,)
        )
        min_corpora = max(1, int(min_corpora)) if isinstance(min_corpora, (int, float)) else 2

    if min_corpora < 2:
        reasons.append(
            "min_corpora=%d is < 2; single-corpus evidence is insufficient "
            "per the replication invariant" % min_corpora
        )
        # We do not override min_corpora here -- we note the misconfiguration
        # and let the count check below decide (if there are >= 2 corpora supplied
        # by the caller even when min_corpora=1, we still honour the count).

    # -- Evaluate primary corpus ----------------------------------------------
    primary_passed = _eval_corpus(fold_results, min_folds, per_fold, reasons,
                                  corpus_label="primary")

    # -- Evaluate extra corpora -----------------------------------------------
    extra_corpus_results: List[CorpusResult] = []
    if corpus_results is not None:
        try:
            extra_corpus_results = list(corpus_results)
        except Exception:  # noqa: BLE001
            reasons.append("corpus_results is not iterable; ignoring")

    n_corpora_passing = int(primary_passed)
    for cr in extra_corpus_results:
        if not isinstance(cr, dict):
            reasons.append("corpus entry is not a dict; skipped")
            continue
        cid = cr.get("corpus_id", "?")
        c_folds = cr.get("folds")
        if not isinstance(c_folds, (list, tuple)):
            reasons.append(
                "corpus %r: 'folds' missing or not a list; skipped" % (cid,)
            )
            continue
        c_per_fold: List[Dict[str, Any]] = []
        c_reasons: List[str] = []
        # For extra corpora, require ALL folds to be positive (every fold in the
        # corpus must show improvement). This enforces "the lift holds in this
        # corpus" without requiring it to have the same k as the primary.
        c_min_folds = max(1, len([f for f in c_folds if isinstance(f, dict)]))
        c_passed = _eval_corpus(
            c_folds, c_min_folds, c_per_fold, c_reasons,
            corpus_label="corpus:%s" % cid,
        )
        per_fold.extend(c_per_fold)
        reasons.extend(c_reasons)
        if c_passed:
            n_corpora_passing += 1

    n_corpora_total = 1 + len(extra_corpus_results)
    n_corpora_evaluated = n_corpora_total

    # -- Corpus-count gate ----------------------------------------------------
    if n_corpora_passing < min_corpora:
        reasons.append(
            "corpora with replicated lift: %d / %d evaluated, need >= %d"
            % (n_corpora_passing, n_corpora_evaluated, min_corpora)
        )

    ok = (not reasons)
    return {
        "replicated": ok,
        "n_folds": len(fold_results),
        "n_corpora": n_corpora_evaluated,
        "per_fold": per_fold,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _eval_corpus(
    folds: Sequence[FoldResult],
    min_folds: int,
    per_fold_out: List[Dict[str, Any]],
    reasons_out: List[str],
    corpus_label: str,
) -> bool:
    """Evaluate one corpus's folds; append to per_fold_out and reasons_out.

    Returns True iff at least min_folds fold entries have delta > 0 AND no fold
    entry has delta < 0 (a loss on any fold/metric is a hard REJECT, per the
    all-proper-scores rule).
    """
    n_passing = 0
    has_negative = False
    n_total = 0

    for entry in folds:
        if not isinstance(entry, dict):
            reasons_out.append(
                "[%s] fold entry is not a dict; skipped" % corpus_label
            )
            continue
        try:
            delta = float(entry["delta"])
        except (KeyError, TypeError, ValueError) as exc:
            reasons_out.append(
                "[%s] fold entry missing/invalid 'delta': %s" % (corpus_label, exc)
            )
            continue

        metric = str(entry.get("metric", "unknown"))
        fold_id = entry.get("fold_id", n_total)
        passed = delta > 0.0
        n_total += 1

        per_fold_out.append({
            "fold_id": fold_id,
            "metric": metric,
            "delta": delta,
            "corpus": corpus_label,
            "passed": passed,
        })

        if passed:
            n_passing += 1
        else:
            has_negative = True

    # A negative delta on any metric is a hard reject (all-proper-scores rule).
    if has_negative:
        reasons_out.append(
            "[%s] at least one fold/metric shows delta <= 0 (all-proper-scores rule)"
            % corpus_label
        )

    if n_total == 0:
        reasons_out.append(
            "[%s] no valid fold entries found" % corpus_label
        )
        return False

    if n_passing < min_folds:
        reasons_out.append(
            "[%s] folds with delta > 0: %d / %d, need >= %d"
            % (corpus_label, n_passing, n_total, min_folds)
        )

    return n_passing >= min_folds and not has_negative
