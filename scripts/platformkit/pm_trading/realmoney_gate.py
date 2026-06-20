"""scripts.platformkit.pm_trading.realmoney_gate -- the CONSERVATIVE real-money gate.

DECISION-ONLY. This module NEVER authorizes a bet and NEVER moves money. It reads
the PAPER CLV record and computes a single boolean: is the paper track record
strong enough that a human MAY consider flipping to real money? Even when it
returns eligible=True, a human flip is ALWAYS required downstream -- this gate is
advisory arithmetic, not an authorization.

WHY IT IS CONSERVATIVE (quant-grade, default INELIGIBLE):
  * The criteria are PRE-REGISTERED constants (below), fixed before the data, so
    the bar cannot be moved to fit a hot streak.
  * ROI is NEVER a criterion. CLV (did we lock a better number than the close?) is
    the only honest yardstick; ROI inflates from small-N variance.
  * The CLV record must be built on TRUE closes. A record dominated by last-price
    PROXY closes (clv_is_proxy=True) CANNOT authorize real money -- proxy CLV is a
    measurement convenience, not a settled-line truth.
  * The CLV lower bound is a bootstrap 95% LB on the settled clv_pct sample, not
    the point estimate -- we require the pessimistic case to clear zero.
  * DEFAULT / empty / insufficient -> eligible=False with a clear reason. We only
    return eligible=True when EVERY criterion strictly passes.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets;
no $-edge claim; never flips a flag; never places or authorizes a bet.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit import clv_ledger as _clv

# ---------------------------------------------------------------------------
# PRE-REGISTERED CRITERIA (fixed before the data; documented; ROI never appears).
# ---------------------------------------------------------------------------
GATE_VERSION = "realmoney_gate.v1"

#: Minimum number of SETTLED paper bets carrying a real clv_pct.
MIN_SETTLED_N = 500
#: The bootstrap 95% LOWER BOUND on clv_pct (in pct) must strictly EXCEED this.
CLV_BOOTSTRAP_LB_MIN = 0.0
#: Fraction of settled bets that must have BEAT the close (clv_pct > 0).
MIN_PCT_BEAT_CLOSE = 0.55
#: Fraction of the CLV record that must rest on TRUE (not proxy) closes.
MIN_TRUE_CLOSE_FRAC = 0.90
#: Bootstrap config for the CLV lower bound (deterministic via fixed seed).
BOOTSTRAP_ITERS = 2000
BOOTSTRAP_ALPHA = 0.05  # -> 95% two-sided; we read the 2.5th percentile as the LB
BOOTSTRAP_SEED = 1729

# Default location of the persisted paper grade summary (advisory; the honest
# metrics are recomputed from the settled ROWS, never trusted from this blob).
DEFAULT_SUMMARY_PATH = _clv.DEFAULT_LEDGER.parent / "grade_summary.json"


def _settled_clv_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Settled, graded rows that carry a real (non-None) clv_pct."""
    return [
        r for r in rows
        if r.get("status") == "settled"
        and r.get("clv_pct") is not None
        and r.get("graded", True)
    ]


def _bootstrap_lb(samples: Sequence[float]) -> Optional[float]:
    """Bootstrap lower bound (2.5th pct of resampled means) on clv_pct. Honest.

    Resamples the settled clv_pct sample with replacement BOOTSTRAP_ITERS times,
    takes each resample's mean, and returns the (alpha/2) percentile -- the
    pessimistic 95% lower bound. Deterministic via a fixed seed so the gate is
    reproducible. Empty sample -> None.
    """
    n = len(samples)
    if n == 0:
        return None
    rnd = random.Random(BOOTSTRAP_SEED)
    vals = [float(x) for x in samples]
    means: List[float] = []
    for _ in range(BOOTSTRAP_ITERS):
        s = 0.0
        for _ in range(n):
            s += vals[rnd.randrange(n)]
        means.append(s / n)
    means.sort()
    idx = int((BOOTSTRAP_ALPHA / 2.0) * len(means))
    idx = min(max(idx, 0), len(means) - 1)
    return means[idx]


def _load_rows(ledger_path: Optional[Path]) -> List[Dict[str, Any]]:
    path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    return _clv.load_ledger(path)


def _load_summary(summary_path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Best-effort read of the persisted grade summary. Never raises."""
    path = Path(summary_path) if summary_path else DEFAULT_SUMMARY_PATH
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _metrics(settled: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Honest metrics recomputed from the settled rows (NOT from any summary blob)."""
    n = len(settled)
    if n == 0:
        return {"n": 0, "clv_mean": None, "clv_lb95": None,
                "pct_beat_close": None, "true_close_frac": None}
    clvs = [float(r["clv_pct"]) for r in settled]
    beats = sum(1 for c in clvs if c > 0.0)
    # A row counts as TRUE-close unless it is explicitly flagged proxy.
    n_true = sum(1 for r in settled if not bool(r.get("clv_is_proxy", False)))
    return {
        "n": n,
        "clv_mean": round(sum(clvs) / n, 6),
        "clv_lb95": _bootstrap_lb(clvs),
        "pct_beat_close": round(beats / n, 6),
        "true_close_frac": round(n_true / n, 6),
    }


def evaluate(
    *,
    summary: Optional[Dict[str, Any]] = None,
    rows: Optional[Sequence[Dict[str, Any]]] = None,
    ledger_path: Optional[Path] = None,
    summary_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compute real-money ELIGIBILITY from the paper CLV record. Decision-only.

    Sources (in honesty order):
      * *rows*    -- explicit settled/ledger rows (tests + callers that already hold
                     the ledger). The honest metrics are computed from these.
      * else the append-only CLV ledger is loaded (*ledger_path* or default).
    *summary* / *summary_path* are advisory only: they are read for context but the
    eligibility metrics (N, bootstrap CLV LB, pct-beat-close, true-close frac) are
    ALWAYS recomputed from the settled ROWS so the decision can never be spoofed by
    a stale or hand-edited summary blob.

    Returns:
      {
        "eligible": bool,            # DEFAULT False; True only if ALL criteria pass
        "reasons": [str, ...],       # why ineligible (empty iff eligible)
        "metrics": {n, clv_mean, clv_lb95, pct_beat_close, true_close_frac},
        "criteria": {...},           # the pre-registered thresholds, echoed
        "gate_version": GATE_VERSION,
        "authorizes_bet": False,     # ALWAYS False -- a human flip is still required
      }
    """
    if rows is None:
        rows = _load_rows(ledger_path)
    # summary is advisory; load it only so callers/logs can see it, never trusted.
    summary_blob = summary if summary is not None else _load_summary(summary_path)

    settled = _settled_clv_rows(list(rows))
    metrics = _metrics(settled)

    reasons: List[str] = []

    n = metrics["n"]
    if n < MIN_SETTLED_N:
        reasons.append(
            "insufficient settled N: have %d, need >= %d" % (n, MIN_SETTLED_N))

    # All remaining checks need a non-empty sample; if n == 0 the N reason stands
    # alone and we still emit explicit reasons for the missing metrics.
    tcf = metrics["true_close_frac"]
    if tcf is None or tcf < MIN_TRUE_CLOSE_FRAC:
        reasons.append(
            "CLV record not on true closes: true_close_frac=%s, need >= %.2f "
            "(proxy CLV cannot authorize real money)"
            % (("n/a" if tcf is None else "%.4f" % tcf), MIN_TRUE_CLOSE_FRAC))

    lb = metrics["clv_lb95"]
    if lb is None or lb <= CLV_BOOTSTRAP_LB_MIN:
        reasons.append(
            "CLV 95%% lower bound not above %.2f: clv_lb95=%s"
            % (CLV_BOOTSTRAP_LB_MIN, ("n/a" if lb is None else "%.6f" % lb)))

    pbc = metrics["pct_beat_close"]
    if pbc is None or pbc < MIN_PCT_BEAT_CLOSE:
        reasons.append(
            "pct-beat-close below bar: pct_beat_close=%s, need >= %.2f"
            % (("n/a" if pbc is None else "%.4f" % pbc), MIN_PCT_BEAT_CLOSE))

    eligible = (len(reasons) == 0)

    return {
        "eligible": bool(eligible),
        "reasons": reasons,
        "metrics": metrics,
        "criteria": {
            "min_settled_n": MIN_SETTLED_N,
            "clv_bootstrap_lb_min": CLV_BOOTSTRAP_LB_MIN,
            "min_pct_beat_close": MIN_PCT_BEAT_CLOSE,
            "min_true_close_frac": MIN_TRUE_CLOSE_FRAC,
            "bootstrap_iters": BOOTSTRAP_ITERS,
            "bootstrap_alpha": BOOTSTRAP_ALPHA,
        },
        "summary_seen": (summary_blob is not None),
        "gate_version": GATE_VERSION,
        # The keystone invariant: this gate NEVER authorizes a bet. Eligibility is
        # a measurement; a human must still flip to real money downstream.
        "authorizes_bet": False,
        "honest_note": ("Decision-only paper CLV gate. eligible=True means the "
                        "paper record clears the pre-registered bar; it does NOT "
                        "authorize any real bet. A human flip is always required. "
                        "ROI is never a criterion; CLV on TRUE closes is."),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Decision-only real-money eligibility gate (paper CLV record).")
    ap.add_argument("--ledger", default=None, help="path to the CLV ledger JSONL")
    ap.add_argument("--summary", default=None, help="path to grade_summary.json")
    a = ap.parse_args(argv)
    res = evaluate(
        ledger_path=Path(a.ledger) if a.ledger else None,
        summary_path=Path(a.summary) if a.summary else None,
    )
    print("REAL-MONEY GATE (%s) -- decision-only, authorizes_bet=%s"
          % (res["gate_version"], res["authorizes_bet"]))
    print("  eligible=%s" % res["eligible"])
    print("  metrics=%s" % json.dumps(res["metrics"], default=str))
    if res["reasons"]:
        for r in res["reasons"]:
            print("  INELIGIBLE: %s" % r)
    print("  " + res["honest_note"])
    return 0


__all__ = [
    "evaluate",
    "GATE_VERSION",
    "MIN_SETTLED_N",
    "CLV_BOOTSTRAP_LB_MIN",
    "MIN_PCT_BEAT_CLOSE",
    "MIN_TRUE_CLOSE_FRAC",
]


if __name__ == "__main__":
    raise SystemExit(_main())
