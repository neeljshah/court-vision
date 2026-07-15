"""scripts.platformkit.execution.expected_clv_gate -- pure expected-CLV placement gate.

PAPER / UNITS only. Answers one question at placement time: does the price we are
about to take clear the devigged fair by at least a pre-registered margin? This is
NOT a realized-CLV measurement (that is clv_ledger's job downstream) -- it is a
pre-trade estimate using the fair probability available at signal time.

Stdlib-only, no file/network IO, no globals. Never raises.
"""
from __future__ import annotations

from typing import Tuple


def devig_two_way(imp_a: float, imp_b: float) -> Tuple[float, float]:
    """Proportional devig of two implied probabilities (imp_a + imp_b > 1 typically).

    Returns (fair_a, fair_b) normalized to sum to 1.0. Degenerate input (either prob
    <= 0, or the pair summing to <= 0) returns (0.5, 0.5) -- a neutral, non-fabricated
    fallback; callers that need to detect degeneracy should validate inputs themselves
    (gate() below does this for the placement path).
    """
    a, b = float(imp_a), float(imp_b)
    total = a + b
    if a <= 0.0 or b <= 0.0 or total <= 0.0:
        return 0.5, 0.5
    return a / total, b / total


def expected_clv_pct(taken_decimal: float, fair_prob: float) -> float:
    """Percent by which the taken decimal price clears the devigged fair probability.

    (taken_decimal * fair_prob - 1) * 100 -- e.g. taken_decimal=2.10, fair_prob=0.50
    -> (2.10*0.50 - 1)*100 = 5.0 (taken price is 5% better than fair). UNITS/percent
    only, never a dollar figure.
    """
    return (float(taken_decimal) * float(fair_prob) - 1.0) * 100.0


def gate(taken_decimal: float, fair_prob: float, threshold_pct: float) -> dict:
    """Gate a placement: passed iff expected_clv_pct >= threshold_pct.

    Degenerate inputs (fair_prob <= 0 or >= 1, taken_decimal <= 1) fail closed with
    passed=False and reason="degenerate" -- never fabricates a pass on bad data.
    """
    try:
        fp = float(fair_prob)
        td = float(taken_decimal)
    except (TypeError, ValueError):
        return {"passed": False, "expected_clv_pct": None, "threshold_pct": threshold_pct,
                "fair_prob": fair_prob, "taken_decimal": taken_decimal, "reason": "degenerate"}
    if fp <= 0.0 or fp >= 1.0 or td <= 1.0:
        return {"passed": False, "expected_clv_pct": None, "threshold_pct": threshold_pct,
                "fair_prob": fp, "taken_decimal": td, "reason": "degenerate"}
    ecp = expected_clv_pct(td, fp)
    return {"passed": ecp >= float(threshold_pct), "expected_clv_pct": ecp,
            "threshold_pct": float(threshold_pct), "fair_prob": fp, "taken_decimal": td}


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    fa, fb = devig_two_way(0.60, 0.45)
    assert abs(fa + fb - 1.0) < 1e-9
    assert 0.50 < fa < 0.60
    assert devig_two_way(0.0, 0.5) == (0.5, 0.5)  # degenerate -> neutral
    g_ok = gate(taken_decimal=2.0, fair_prob=0.55, threshold_pct=1.0)
    assert g_ok["passed"] is True  # (2.0*0.55-1)*100 = 10.0 >= 1.0
    g_bad = gate(taken_decimal=1.0, fair_prob=0.55, threshold_pct=1.0)
    assert g_bad["passed"] is False and g_bad["reason"] == "degenerate"
    print("expected_clv_gate self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["devig_two_way", "expected_clv_pct", "gate"]
