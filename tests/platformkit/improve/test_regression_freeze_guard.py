"""tests.platformkit.improve.test_regression_freeze_guard

Acceptance tests for the advisory regression-freeze guard (SIX-05).

Scenarios (per spec):
  (1) >=K consecutive Brier increases beyond tol -> freeze=True with honest reason
  (2) one-off regression then recovery -> freeze=False
  (3) monotone-improving -> freeze=False
  (4) <K cycles -> INSUFFICIENT_DATA, freeze=False
  (5) advisory: returns a recommendation, never mutates any ledger/ratchet_state/flag
  (6) no $/roi/pnl/profit/edge key; ASCII; never raises

Per-file test only (full pytest freezes the box).  stdlib only; ASCII.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve.regression_freeze_guard import (  # noqa: E402
    MIN_K,
    REGRESSION_TOL,
    check_all,
    check_freeze,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_RE = re.compile(r"(\$|roi|pnl|profit|edge)", re.IGNORECASE)


def _banned_keys(obj: Any) -> List[str]:
    """Collect any key matching the banned pattern (recursively)."""
    found: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _BANNED_RE.search(k):
                found.append(k)
            found.extend(_banned_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found.extend(_banned_keys(item))
    return found


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _write_ledger(rows: List[Dict[str, Any]]) -> Path:
    """Write a JSONL ledger to a temp file and return its Path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    for row in rows:
        tmp.write(json.dumps(row) + "\n")
    tmp.close()
    return Path(tmp.name)


def _ledger_rows(market: str, briers: List[float]) -> List[Dict[str, Any]]:
    """Build minimal ledger rows for a market with the given Brier sequence."""
    rows = []
    for i, b in enumerate(briers):
        rows.append({
            "market": market,
            "cycle": i,
            "status": "ok",
            "readout": {"raw_brier": b},
        })
    return rows


# ---------------------------------------------------------------------------
# (1) >=K consecutive regressions -> freeze=True
# ---------------------------------------------------------------------------

def test_k_consecutive_regressions_freeze_true():
    """K or more consecutive Brier increases beyond tol must produce freeze=True."""
    tol = REGRESSION_TOL
    # Build a sequence: improving, then K consecutive regressions of tol*2.
    briers = [0.300, 0.280, 0.260]              # improving run
    for _ in range(MIN_K):
        briers.append(briers[-1] + tol * 2.0)  # sustained regression

    ledger = _write_ledger(_ledger_rows("nba:moneyline", briers))
    rec = check_freeze("nba:moneyline", ledger_path=ledger, min_k=MIN_K)

    assert rec["freeze"] is True, (
        "K=%d consecutive regressions must produce freeze=True; got %s" % (MIN_K, rec)
    )
    assert "ADVISORY FREEZE" in rec["reason"], (
        "reason must mention ADVISORY FREEZE; got: %s" % rec["reason"]
    )
    assert rec["consecutive_regressions"] >= MIN_K
    assert rec["status"] == "ok"


def test_exactly_k_consecutive_regressions_is_freeze():
    """Exactly K consecutive regressions -- the boundary -- must still freeze."""
    tol = REGRESSION_TOL
    K = 3
    briers = [0.400]
    for _ in range(K):
        briers.append(briers[-1] + tol * 2.0)

    ledger = _write_ledger(_ledger_rows("nba:prop", briers))
    rec = check_freeze("nba:prop", ledger_path=ledger, min_k=K)

    assert rec["freeze"] is True
    assert rec["consecutive_regressions"] == K


# ---------------------------------------------------------------------------
# (2) One-off regression then recovery -> freeze=False
# ---------------------------------------------------------------------------

def test_one_off_regression_then_recovery_no_freeze():
    """A single regression spike followed by improvement must NOT freeze."""
    tol = REGRESSION_TOL
    briers = [
        0.300,
        0.310 + tol * 3,   # big one-off regression
        0.290,              # recovery
        0.280,              # continued improvement
        0.270,
    ]
    ledger = _write_ledger(_ledger_rows("mlb:moneyline", briers))
    rec = check_freeze("mlb:moneyline", ledger_path=ledger, min_k=MIN_K)

    assert rec["freeze"] is False, (
        "one-off regression followed by recovery must not freeze; got %s" % rec
    )
    assert rec["status"] == "ok"
    assert rec["consecutive_regressions"] < MIN_K


def test_alternating_regression_recovery_no_freeze():
    """Alternating up/down Briers never reach K consecutive -- no freeze."""
    tol = REGRESSION_TOL
    briers = [0.300]
    for i in range(8):
        if i % 2 == 0:
            briers.append(briers[-1] + tol * 2.0)   # regression
        else:
            briers.append(briers[-1] - tol * 3.0)   # recovery

    ledger = _write_ledger(_ledger_rows("nba:prop_ast", briers))
    rec = check_freeze("nba:prop_ast", ledger_path=ledger, min_k=MIN_K)

    assert rec["freeze"] is False
    assert rec["consecutive_regressions"] < MIN_K


# ---------------------------------------------------------------------------
# (3) Monotone improving -> freeze=False
# ---------------------------------------------------------------------------

def test_monotone_improving_no_freeze():
    """Strictly improving Brier sequence must never trigger freeze."""
    briers = [0.400, 0.380, 0.360, 0.340, 0.320, 0.300]
    ledger = _write_ledger(_ledger_rows("tennis:moneyline", briers))
    rec = check_freeze("tennis:moneyline", ledger_path=ledger, min_k=MIN_K)

    assert rec["freeze"] is False
    assert rec["consecutive_regressions"] == 0
    assert rec["status"] == "ok"


def test_flat_brier_no_freeze():
    """Flat Brier (deltas within tol) is not a regression -- no freeze."""
    b = 0.300
    briers = [b] * (MIN_K + 2)   # no movement at all
    ledger = _write_ledger(_ledger_rows("soccer:ou", briers))
    rec = check_freeze("soccer:ou", ledger_path=ledger, min_k=MIN_K)

    assert rec["freeze"] is False


# ---------------------------------------------------------------------------
# (4) <K cycles -> INSUFFICIENT_DATA, freeze=False
# ---------------------------------------------------------------------------

def test_fewer_than_k_cycles_insufficient_data():
    """Fewer than K+1 brier-bearing cycles can't establish K consecutive deltas."""
    # K=3 needs >= 4 briers to form 3 consecutive deltas; supply only 3.
    K = 3
    briers = [0.300, 0.310, 0.320]   # 3 briers -> 2 deltas < K=3
    ledger = _write_ledger(_ledger_rows("nba:moneyline", briers))
    rec = check_freeze("nba:moneyline", ledger_path=ledger, min_k=K)

    assert rec["freeze"] is False, (
        "fewer than K+1 cycles must yield freeze=False; got %s" % rec
    )
    assert rec["status"] == "INSUFFICIENT_DATA"


def test_empty_ledger_is_insufficient_data():
    """An empty ledger (no rows) must yield INSUFFICIENT_DATA, freeze=False."""
    ledger = _write_ledger([])
    rec = check_freeze("nba:moneyline", ledger_path=ledger)

    assert rec["freeze"] is False
    assert rec["status"] == "INSUFFICIENT_DATA"


def test_single_cycle_is_insufficient_data():
    """A single data cycle (no deltas at all) must yield INSUFFICIENT_DATA."""
    ledger = _write_ledger(_ledger_rows("nba:prop_pts", [0.300]))
    rec = check_freeze("nba:prop_pts", ledger_path=ledger)

    assert rec["freeze"] is False
    assert rec["status"] == "INSUFFICIENT_DATA"


def test_two_cycles_below_k_is_insufficient_data():
    """Two cycles -> one delta -> below K=3 threshold -> INSUFFICIENT_DATA."""
    briers = [0.300, 0.320]  # 1 delta
    ledger = _write_ledger(_ledger_rows("nba:moneyline", briers))
    rec = check_freeze("nba:moneyline", ledger_path=ledger, min_k=3)

    assert rec["freeze"] is False
    assert rec["status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# (5) Advisory: returns recommendation, never mutates any external state
# ---------------------------------------------------------------------------

def test_advisory_only_returns_dict_not_mutating():
    """check_freeze must return a plain dict -- never mutates ledger or ratchet."""
    briers = [0.300, 0.290, 0.280, 0.270, 0.260]
    ledger = _write_ledger(_ledger_rows("nba:moneyline", briers))

    # Read the ledger content before and after the call.
    before = ledger.read_text(encoding="utf-8")
    rec = check_freeze("nba:moneyline", ledger_path=ledger)
    after = ledger.read_text(encoding="utf-8")

    assert before == after, "check_freeze must NOT write to the ledger"
    assert isinstance(rec, dict), "result must be a plain dict"
    # No ratchet_state key and no flag key in the result
    forbidden_state_keys = {"ratchet_state", "daemon", "flag", "ship", "reject"}
    assert not (forbidden_state_keys & set(rec.keys())), (
        "advisory result must not carry ratchet/daemon/flag/ship/reject keys"
    )


def test_advisory_default_freeze_false():
    """Default (no data) must always return freeze=False (do-no-harm)."""
    ledger = _write_ledger([])
    rec = check_freeze("nonexistent:market", ledger_path=ledger)
    assert rec["freeze"] is False


def test_check_all_advisory_only():
    """check_all must return a dict of recommendations, never mutate any file."""
    rows: List[Dict[str, Any]] = []
    rows += _ledger_rows("nba:moneyline", [0.300, 0.290, 0.280])
    rows += _ledger_rows("mlb:moneyline", [0.250, 0.260, 0.270])
    ledger = _write_ledger(rows)

    before = ledger.read_text(encoding="utf-8")
    all_recs = check_all(ledger_path=ledger)
    after = ledger.read_text(encoding="utf-8")

    assert before == after, "check_all must NOT write to the ledger"
    assert isinstance(all_recs, dict)
    for mkt, rec in all_recs.items():
        assert isinstance(rec, dict)
        assert "freeze" in rec
        assert isinstance(rec["freeze"], bool)


# ---------------------------------------------------------------------------
# (6) No $/roi/pnl/profit/edge keys; ASCII; never raises
# ---------------------------------------------------------------------------

def test_no_banned_keys_in_result():
    """Result must never contain $/roi/pnl/profit/edge keys."""
    # Test with improving data
    ledger1 = _write_ledger(_ledger_rows("nba:moneyline", [0.30, 0.28, 0.26]))
    rec1 = check_freeze("nba:moneyline", ledger_path=ledger1)
    assert not _banned_keys(rec1), "banned keys found: %s" % _banned_keys(rec1)

    # Test with regressing data
    tol = REGRESSION_TOL
    briers = [0.30] + [0.30 + tol * 2 * (i + 1) for i in range(MIN_K + 1)]
    ledger2 = _write_ledger(_ledger_rows("nba:moneyline", briers))
    rec2 = check_freeze("nba:moneyline", ledger_path=ledger2)
    assert not _banned_keys(rec2), "banned keys found: %s" % _banned_keys(rec2)


def test_no_banned_keys_in_check_all():
    """check_all must not emit any banned keys across any market."""
    tol = REGRESSION_TOL
    rows: List[Dict[str, Any]] = []
    rows += _ledger_rows("nba:moneyline", [0.30, 0.28, 0.26, 0.24])
    rows += _ledger_rows("mlb:moneyline",
                         [0.30] + [0.30 + tol * 2 * (i + 1) for i in range(MIN_K + 1)])
    ledger = _write_ledger(rows)
    all_recs = check_all(ledger_path=ledger)
    for mkt, rec in all_recs.items():
        bk = _banned_keys(rec)
        assert not bk, "banned keys %s found in market %s" % (bk, mkt)


def test_result_is_ascii_only():
    """All string fields in the result must be ASCII-encodable."""
    tol = REGRESSION_TOL
    briers = [0.30] + [0.30 + tol * 2 * (i + 1) for i in range(MIN_K + 1)]
    ledger = _write_ledger(_ledger_rows("nba:moneyline", briers))
    rec = check_freeze("nba:moneyline", ledger_path=ledger)

    for k, v in rec.items():
        assert _is_ascii(k), "key '%s' is not ASCII" % k
        if isinstance(v, str):
            assert _is_ascii(v), "value for key '%s' is not ASCII: %r" % (k, v)


def test_never_raises_on_malformed_input():
    """check_freeze must never raise on any malformed/missing input."""
    # Bad market name
    rec1 = check_freeze("")
    assert isinstance(rec1, dict)
    assert rec1["freeze"] is False

    # Nonexistent ledger path
    rec2 = check_freeze("nba:moneyline", ledger_path=Path("/nonexistent/path.jsonl"))
    assert isinstance(rec2, dict)
    assert rec2["freeze"] is False

    # None ledger_path with a market not in default ledger -> at most INSUFFICIENT_DATA
    try:
        rec3 = check_freeze("ghost:market:that:does:not:exist")
        assert isinstance(rec3, dict)
        assert rec3["freeze"] is False
    except Exception as exc:
        raise AssertionError("check_freeze raised: %s" % exc) from exc


def test_never_raises_on_ledger_with_missing_brier():
    """Ledger rows without a raw_brier field must not cause a crash."""
    rows = [
        {"market": "nba:moneyline", "cycle": 0, "status": "ok", "readout": {}},
        {"market": "nba:moneyline", "cycle": 1, "status": "ok", "readout": {}},
    ]
    ledger = _write_ledger(rows)
    rec = check_freeze("nba:moneyline", ledger_path=ledger)
    assert isinstance(rec, dict)
    assert rec["freeze"] is False


# ---------------------------------------------------------------------------
# Edge-case: consecutive run spans more than exactly K
# ---------------------------------------------------------------------------

def test_longer_run_still_freezes():
    """A run of 2*K consecutive regressions must also produce freeze=True."""
    tol = REGRESSION_TOL
    briers = [0.300]
    for _ in range(MIN_K * 2):
        briers.append(briers[-1] + tol * 2.0)

    ledger = _write_ledger(_ledger_rows("nba:moneyline", briers))
    rec = check_freeze("nba:moneyline", ledger_path=ledger, min_k=MIN_K)

    assert rec["freeze"] is True
    assert rec["consecutive_regressions"] >= MIN_K * 2


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
