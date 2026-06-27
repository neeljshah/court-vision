"""tests.platformkit.test_realmoney_gate -- the CONSERVATIVE real-money gate.

Asserts the DECISION-ONLY contract of scripts.platformkit.pm_trading.realmoney_gate:

  * cold / empty record  -> eligible=False (default INELIGIBLE) with a clear reason.
  * a fixture clearing EVERY pre-registered criterion -> eligible=True.
  * each SINGLE failing criterion -> eligible=False with the right-shaped reason:
      - low settled N
      - CLV bootstrap 95% lower bound not above 0
      - pct-beat-close below 0.55
      - mostly-proxy CLV (true_close_frac too low)
  * the gate NEVER authorizes a bet (authorizes_bet is always False), even when
    eligible=True -- a human flip is always required downstream.
  * ROI is never a criterion (no roi key drives the decision).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_realmoney_gate.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List

from scripts.platformkit.pm_trading.realmoney_gate import (
    CLV_BOOTSTRAP_LB_MIN,
    GATE_VERSION,
    MIN_PCT_BEAT_CLOSE,
    MIN_SETTLED_N,
    MIN_TRUE_CLOSE_FRAC,
    evaluate,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _row(clv_pct: float, *, proxy: bool = False) -> Dict[str, Any]:
    """One settled, graded CLV row with a real clv_pct."""
    return {
        "status": "settled",
        "graded": True,
        "clv_pct": float(clv_pct),
        "clv_is_proxy": bool(proxy),
        "side": "home",
        "taken_decimal": 2.0,
    }


def _passing_rows(n: int = MIN_SETTLED_N + 20) -> List[Dict[str, Any]]:
    """A record that clears EVERY criterion: large N, true closes, strong + CLV.

    ~62% beat the close and the CLV values are solidly positive so the bootstrap
    95% lower bound stays well above zero.
    """
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        # ~62% positive (>= 0.55), comfortable margin; all true closes.
        clv = 2.0 if (i % 8) < 5 else -0.5
        rows.append(_row(clv, proxy=False))
    return rows


# ---------------------------------------------------------------------------
# Cold / empty -> ineligible
# ---------------------------------------------------------------------------
def test_cold_empty_is_ineligible():
    res = evaluate(rows=[])
    assert res["eligible"] is False
    assert res["authorizes_bet"] is False
    assert res["gate_version"] == GATE_VERSION
    assert res["metrics"]["n"] == 0
    # The N criterion must be cited on an empty record.
    assert any("settled N" in r for r in res["reasons"])


def test_default_no_rows_is_ineligible(tmp_path):
    # Point at a non-existent ledger; default must be INELIGIBLE, never crash.
    missing = tmp_path / "no_such_ledger.jsonl"
    res = evaluate(ledger_path=missing)
    assert res["eligible"] is False
    assert res["metrics"]["n"] == 0


# ---------------------------------------------------------------------------
# Full pass -> eligible
# ---------------------------------------------------------------------------
def test_all_criteria_pass_is_eligible():
    res = evaluate(rows=_passing_rows())
    assert res["eligible"] is True, res["reasons"]
    assert res["reasons"] == []
    m = res["metrics"]
    assert m["n"] >= MIN_SETTLED_N
    assert m["true_close_frac"] >= MIN_TRUE_CLOSE_FRAC
    assert m["clv_lb95"] > CLV_BOOTSTRAP_LB_MIN
    assert m["pct_beat_close"] >= MIN_PCT_BEAT_CLOSE
    # Even when eligible, the gate authorizes nothing.
    assert res["authorizes_bet"] is False


def test_eligible_never_authorizes_a_bet():
    res = evaluate(rows=_passing_rows())
    assert res["eligible"] is True
    # The keystone invariant -- decision-only, a human flip is still required.
    assert res["authorizes_bet"] is False


# ---------------------------------------------------------------------------
# Each single failing criterion -> ineligible with the right reason
# ---------------------------------------------------------------------------
def test_low_settled_n_is_ineligible():
    rows = _passing_rows(n=MIN_SETTLED_N - 1)  # everything else strong
    res = evaluate(rows=rows)
    assert res["eligible"] is False
    assert any("settled N" in r for r in res["reasons"])
    # The OTHER criteria still pass, so N is the binding failure.
    assert res["metrics"]["true_close_frac"] >= MIN_TRUE_CLOSE_FRAC


def test_clv_lower_bound_not_above_zero_is_ineligible():
    # Large N, all true closes, but CLV centered at ~0 so the bootstrap LB <= 0.
    rows = [_row(0.5 if (i % 2 == 0) else -0.5, proxy=False)
            for i in range(MIN_SETTLED_N + 20)]
    res = evaluate(rows=rows)
    assert res["eligible"] is False
    assert any("lower bound" in r for r in res["reasons"])
    assert res["metrics"]["clv_lb95"] <= CLV_BOOTSTRAP_LB_MIN


def test_pct_beat_close_below_bar_is_ineligible():
    # Build a record whose CLV mean/LB is positive but < 55% of bets beat the
    # close: a few big winners, many small losers.
    rows: List[Dict[str, Any]] = []
    n = MIN_SETTLED_N + 20
    for i in range(n):
        # ~50% positive -> below the 0.55 bar; large positive magnitude keeps the
        # bootstrap LB above zero so pct-beat-close is the BINDING failure.
        clv = 5.0 if (i % 2 == 0) else -0.1
        rows.append(_row(clv, proxy=False))
    res = evaluate(rows=rows)
    assert res["eligible"] is False
    assert any("pct-beat-close" in r for r in res["reasons"])
    assert res["metrics"]["pct_beat_close"] < MIN_PCT_BEAT_CLOSE
    # The CLV lower bound itself is fine; the only failure is pct-beat-close.
    assert res["metrics"]["clv_lb95"] > CLV_BOOTSTRAP_LB_MIN


def test_mostly_proxy_is_ineligible():
    # Strong CLV, big N, but the record rests on last-price PROXY closes.
    base = _passing_rows()
    rows = [dict(r, clv_is_proxy=True) for r in base]
    res = evaluate(rows=rows)
    assert res["eligible"] is False
    assert any("true closes" in r for r in res["reasons"])
    assert res["metrics"]["true_close_frac"] < MIN_TRUE_CLOSE_FRAC


# ---------------------------------------------------------------------------
# A stale / hand-edited summary blob must NOT spoof the decision
# ---------------------------------------------------------------------------
def test_injected_summary_does_not_override_rows():
    # A glowing summary blob claiming success, but the rows are empty.
    fake_summary = {"n": 9999, "pct_beat_close": 99.0, "mean_clv_pct": 50.0,
                    "paper_roi": 999.0}
    res = evaluate(summary=fake_summary, rows=[])
    assert res["eligible"] is False
    assert res["metrics"]["n"] == 0
    assert res["summary_seen"] is True


def test_roi_is_never_a_criterion():
    # ROI is not part of the contract; criteria dict must not mention it.
    res = evaluate(rows=_passing_rows())
    crit = res["criteria"]
    assert not any("roi" in k.lower() for k in crit)
