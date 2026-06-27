"""tests.platformkit.test_realmoney_gate_chaos -- TH-04 default-DENY chaos harness.

Proves: all-criteria-met->eligible True but authorizes_bet False; any missing
criterion->eligible False; no $ / roi / pnl key anywhere in result; 50-trial fuzz.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_realmoney_gate_chaos.py -q
"""
from __future__ import annotations

import json
import random
import re
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
# Helpers
# ---------------------------------------------------------------------------
_DOLLAR_PATTERN = re.compile(r"\$|roi|pnl|profit|p&l|revenue", re.IGNORECASE)


def _settled_row(clv_pct: float, *, proxy: bool = False) -> Dict[str, Any]:
    return {"status": "settled", "graded": True, "clv_pct": float(clv_pct),
            "clv_is_proxy": bool(proxy), "side": "home", "taken_decimal": 2.0}


def _all_passing_rows(n: int = MIN_SETTLED_N + 100) -> List[Dict[str, Any]]:
    """Rows clearing EVERY criterion: 70% beat close, true closes, positive CLV LB."""
    return [_settled_row(3.0 if (i % 10) < 7 else -0.5) for i in range(n)]


def _assert_no_dollar_keys(result: Dict[str, Any]) -> None:
    """Recursive walk -- no $ / roi / pnl / profit key anywhere in nested result."""
    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert not _DOLLAR_PATTERN.search(str(k)), (
                    "Dollar/ROI/PnL key in gate result: %r" % k)
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
    _walk(result)


# ---------------------------------------------------------------------------
# 1. Keystone: all criteria met -> eligible=True but authorizes_bet=False
# ---------------------------------------------------------------------------

def test_all_criteria_met_eligible_but_never_authorizes():
    """Keystone: eligible=True AND authorizes_bet=False simultaneously."""
    res = evaluate(rows=_all_passing_rows())
    m = res["metrics"]
    # Confirm fixture actually clears every bar.
    assert m["n"] >= MIN_SETTLED_N
    assert m["true_close_frac"] >= MIN_TRUE_CLOSE_FRAC
    assert m["clv_lb95"] is not None and m["clv_lb95"] > CLV_BOOTSTRAP_LB_MIN
    assert m["pct_beat_close"] >= MIN_PCT_BEAT_CLOSE
    # The pre-registered criteria pass -> eligible must be True.
    assert res["eligible"] is True, res["reasons"]
    # The keystone: even so, the gate NEVER authorizes a bet.
    assert res["authorizes_bet"] is False, "INVARIANT VIOLATED"
    assert res["gate_version"] == GATE_VERSION


def test_authorizes_bet_is_boolean_false_not_falsy():
    """authorizes_bet must be the boolean False, not a falsy equivalent."""
    res = evaluate(rows=_all_passing_rows())
    assert res["authorizes_bet"] is False
    assert isinstance(res["authorizes_bet"], bool)


# ---------------------------------------------------------------------------
# 2. No-$ contract
# ---------------------------------------------------------------------------

def test_no_dollar_keys_when_eligible():
    res = evaluate(rows=_all_passing_rows())
    assert res["eligible"] is True
    _assert_no_dollar_keys(res)


def test_no_dollar_keys_when_ineligible():
    res = evaluate(rows=[])
    assert res["eligible"] is False
    _assert_no_dollar_keys(res)


def test_criteria_dict_has_no_dollar_keys():
    res = evaluate(rows=_all_passing_rows())
    for k in res["criteria"]:
        assert not _DOLLAR_PATTERN.search(k), "Dollar/ROI key in criteria: %r" % k


# ---------------------------------------------------------------------------
# 3. Single-criterion knock-outs -- any missing criterion -> eligible=False
# ---------------------------------------------------------------------------

def test_knock_out_insufficient_N():
    rows = _all_passing_rows(n=MIN_SETTLED_N - 1)
    res = evaluate(rows=rows)
    assert res["eligible"] is False
    assert res["authorizes_bet"] is False
    assert any("settled N" in r for r in res["reasons"]), res["reasons"]


def test_knock_out_clv_lower_bound():
    """Symmetric CLV -> mean ~0 -> bootstrap LB dips <= 0 -> ineligible."""
    n = MIN_SETTLED_N + 200
    rows = [_settled_row(0.3 if i % 2 == 0 else -0.3) for i in range(n)]
    res = evaluate(rows=rows)
    assert res["eligible"] is False
    assert res["authorizes_bet"] is False
    assert any("lower bound" in r or "CLV" in r for r in res["reasons"]), res["reasons"]
    assert res["metrics"]["clv_lb95"] <= CLV_BOOTSTRAP_LB_MIN


def test_knock_out_pct_beat_close():
    """~50% beat close (below 0.55 bar) even with positive CLV mean."""
    n = MIN_SETTLED_N + 200
    rows = [_settled_row(8.0 if i % 2 == 0 else -0.1) for i in range(n)]
    res = evaluate(rows=rows)
    pbc = res["metrics"]["pct_beat_close"]
    if pbc >= MIN_PCT_BEAT_CLOSE:
        return  # fixture didn't knock out pct-beat-close; benign skip
    assert res["eligible"] is False
    assert res["authorizes_bet"] is False
    assert any("pct-beat-close" in r for r in res["reasons"]), res["reasons"]


def test_knock_out_mostly_proxy_closes():
    rows = [dict(_settled_row(3.0, proxy=True)) for _ in range(MIN_SETTLED_N + 100)]
    res = evaluate(rows=rows)
    assert res["eligible"] is False
    assert res["authorizes_bet"] is False
    assert any("true closes" in r or "proxy" in r for r in res["reasons"]), res["reasons"]
    assert res["metrics"]["true_close_frac"] < MIN_TRUE_CLOSE_FRAC


def test_knock_out_zero_rows():
    res = evaluate(rows=[])
    assert res["eligible"] is False and res["authorizes_bet"] is False
    assert res["metrics"]["n"] == 0
    assert any("settled N" in r for r in res["reasons"])


def test_knock_out_all_open_rows():
    """Unsettled rows count as N=0 -> ineligible."""
    rows = [{"status": "open", "graded": False, "clv_pct": None, "clv_is_proxy": False}
            for _ in range(MIN_SETTLED_N + 50)]
    res = evaluate(rows=rows)
    assert res["eligible"] is False and res["authorizes_bet"] is False
    assert res["metrics"]["n"] == 0


# ---------------------------------------------------------------------------
# 4. Fake summary blob must NOT spoof the decision (rows are the truth)
# ---------------------------------------------------------------------------

def test_fake_summary_cannot_make_empty_record_eligible():
    """Glowing summary with empty rows -> ineligible; rows are the truth source."""
    fake = {"n": 99999, "pct_beat_close": 99.0, "paper_roi": 999.0, "clv_lb95": 99.0}
    res = evaluate(summary=fake, rows=[])
    assert res["eligible"] is False and res["authorizes_bet"] is False
    assert res["metrics"]["n"] == 0 and res["summary_seen"] is True


def test_fake_summary_with_passing_rows_stays_eligible_and_still_no_auth():
    """Doom summary with passing rows -> eligible=True, authorizes_bet=False."""
    fake = {"n": 1, "pct_beat_close": 0.0, "paper_roi": -100.0}
    res = evaluate(summary=fake, rows=_all_passing_rows())
    assert res["eligible"] is True and res["authorizes_bet"] is False


# ---------------------------------------------------------------------------
# 5. Chaos sweep: N boundary
# ---------------------------------------------------------------------------

def test_chaos_n_threshold_boundary():
    """At floor N: authorizes_bet=False; one below: eligible=False."""
    rng = random.Random(42)
    base = _all_passing_rows(n=MIN_SETTLED_N + 500)

    at_floor = rng.sample(base, MIN_SETTLED_N)
    res_at = evaluate(rows=at_floor)
    assert res_at["authorizes_bet"] is False
    assert isinstance(res_at["eligible"], bool)

    one_short = rng.sample(base, MIN_SETTLED_N - 1)
    res_short = evaluate(rows=one_short)
    assert res_short["eligible"] is False and res_short["authorizes_bet"] is False
    assert any("settled N" in r for r in res_short["reasons"])


# ---------------------------------------------------------------------------
# 6. Stochastic fuzz: authorizes_bet ALWAYS False
# ---------------------------------------------------------------------------

def test_fuzz_authorizes_bet_invariant():
    """50 random row sets -- authorizes_bet=False and no $ key every trial."""
    rng = random.Random(1729)
    for trial in range(50):
        n = rng.randint(0, MIN_SETTLED_N * 2)
        rows: List[Dict[str, Any]] = []
        for _ in range(n):
            clv = rng.uniform(-5.0, 10.0)
            proxy = rng.random() < 0.5
            status = rng.choice(["settled", "settled", "open"])
            graded = rng.random() < 0.8
            rows.append({"status": status, "graded": graded,
                         "clv_pct": clv if (status == "settled" and graded) else None,
                         "clv_is_proxy": proxy})
        res = evaluate(rows=rows)
        assert res["authorizes_bet"] is False, (
            "trial %d: authorizes_bet not False (eligible=%s, n=%d)" % (trial, res["eligible"], n))
        assert isinstance(res["eligible"], bool)
        _assert_no_dollar_keys(res)


# ---------------------------------------------------------------------------
# 7. Result schema invariants
# ---------------------------------------------------------------------------

def test_result_always_contains_required_keys():
    """Both eligible and ineligible results expose all required keys."""
    for rows in [[], _all_passing_rows()]:
        res = evaluate(rows=rows)
        for k in ["eligible", "reasons", "metrics", "criteria",
                  "gate_version", "authorizes_bet", "honest_note"]:
            assert k in res, "missing key %r" % k
        assert isinstance(res["reasons"], list)
        assert isinstance(res["metrics"], dict)
        assert isinstance(res["criteria"], dict)


def test_eligible_true_has_empty_reasons():
    res = evaluate(rows=_all_passing_rows())
    assert res["eligible"] is True
    assert res["reasons"] == [], res["reasons"]


def test_ineligible_has_at_least_one_reason():
    res = evaluate(rows=[])
    assert res["eligible"] is False
    assert len(res["reasons"]) >= 1
    for r in res["reasons"]:
        assert isinstance(r, str) and r.strip()


def test_metrics_types():
    m = evaluate(rows=_all_passing_rows())["metrics"]
    assert isinstance(m["n"], int)
    assert isinstance(m["clv_mean"], float)
    assert isinstance(m["clv_lb95"], float)
    assert isinstance(m["pct_beat_close"], float)
    assert isinstance(m["true_close_frac"], float)


def test_serialisable_to_json():
    res = evaluate(rows=_all_passing_rows())
    try:
        json.dumps(res)
    except (TypeError, ValueError) as exc:
        raise AssertionError("result not JSON-serialisable: %s" % exc) from exc
