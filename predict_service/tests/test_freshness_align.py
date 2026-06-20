"""predict_service.tests.test_freshness_align -- per-file test for freshness_align.

BE-R5-3 acceptance criteria:
  B1. produce=fresh + freshness=stale for same stem -> aligned verdict = stale
      (monotone-DOWN; the worst-of wins).
  B2. fresh=null + age_sec >= sla -> stale (stale-never-ok even when null).
  B3. Both rows explicitly fresh -> aligned ok=True, aligned_fresh='fresh'.
  B4. Missing/None produce row -> aligned stale never green.
  B5. Missing/None freshness row -> aligned stale never green.
  B6. Both rows missing -> aligned stale (unavailable not green).
  B7. No $ field in any output.
  B8. align_stem NEVER raises on garbage inputs.
  B9. align_stems batch: any stale stem degrades overall off ok (monotone-DOWN).
  B10. align_stems empty stems -> overall='degraded' (not ok; absence never green).
  B11. sla_map per-stem override respected.
  B12. aligned_ok=True ONLY when aligned_fresh=='fresh'.
  B13. produce=fresh + freshness=down -> aligned down (worst of three levels).
  B14. coerce_produce_row: ok=True -> fresh='fresh'; ok=False+unavailable -> 'down'.
  B15. coerce_freshness_row: fresh=True -> 'fresh'; fresh=False+missing -> 'down'.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_freshness_align.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.freshness_align import (  # noqa: E402
    align_stem,
    align_stems,
    coerce_freshness_row,
    coerce_produce_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_ago(seconds: float) -> str:
    """ISO-8601 UTC timestamp for *seconds* seconds ago."""
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _produce_row(sport: str = "nba", ok: bool = True,
                 status: str = "ok", age_seconds: float = 60.0) -> dict:
    return {
        "sport": sport,
        "ok": ok,
        "status": status,
        "generated_at": _ts_ago(age_seconds),
        "age_seconds": age_seconds,
        "n_games": 3,
        "n_markets": 10,
        "reason": None,
    }


def _freshness_row(sport: str = "nba", fresh: object = True,
                   status: str = "fresh", age_seconds: float = 60.0) -> dict:
    return {
        "sport": sport,
        "status": status,
        "ok": bool(fresh is True),
        "fresh": fresh,
        "stale": not bool(fresh is True),
        "age_seconds": age_seconds,
        "source_ts": _ts_ago(age_seconds),
        "reason": None,
    }


def _has_dollar_key(d: object) -> bool:
    if isinstance(d, dict):
        for k, v in d.items():
            if "$" in str(k):
                return True
            if _has_dollar_key(v):
                return True
    if isinstance(d, list):
        return any(_has_dollar_key(i) for i in d)
    return False


# ---------------------------------------------------------------------------
# B1: produce=fresh + freshness=stale -> aligned stale (monotone-DOWN)
# ---------------------------------------------------------------------------

def test_b1_produce_fresh_freshness_stale_gives_stale():
    p_row = _produce_row(ok=True, status="ok", age_seconds=60)
    f_row = _freshness_row(fresh=False, status="stale", age_seconds=9999)
    result = align_stem("nba", p_row, f_row, sla_sec=300.0)
    assert result["aligned_fresh"] == "stale", (
        "B1: produce=fresh + freshness=stale must give aligned stale; got %r" % result
    )
    assert result["aligned_ok"] is False, "B1: aligned_ok must be False when stale"


# ---------------------------------------------------------------------------
# B2: fresh=null + age_sec >= sla -> stale (stale-never-ok)
# ---------------------------------------------------------------------------

def test_b2_null_fresh_old_age_gives_stale():
    # Produce row with ok=None and age_seconds well past sla=300.
    p_row = {
        "sport": "nba", "ok": None, "status": "unknown",
        "generated_at": _ts_ago(600), "age_seconds": 600.0,
        "n_games": 0, "n_markets": 0, "reason": None,
    }
    # Freshness row also with null fresh and large age.
    f_row = {
        "sport": "nba", "status": "stale", "ok": False,
        "fresh": None, "stale": True, "age_seconds": 600.0,
        "source_ts": _ts_ago(600), "reason": None,
    }
    result = align_stem("nba", p_row, f_row, sla_sec=300.0)
    assert result["aligned_fresh"] == "stale", "B2: null+age>=sla must be stale"
    assert result["aligned_ok"] is False


# ---------------------------------------------------------------------------
# B3: Both rows explicitly fresh -> aligned ok
# ---------------------------------------------------------------------------

def test_b3_both_fresh_gives_ok():
    p_row = _produce_row(ok=True, status="ok", age_seconds=30)
    f_row = _freshness_row(fresh=True, status="fresh", age_seconds=30)
    result = align_stem("nba", p_row, f_row, sla_sec=300.0)
    assert result["aligned_fresh"] == "fresh", (
        "B3: both fresh must give aligned fresh; got %r" % result
    )
    assert result["aligned_ok"] is True


# ---------------------------------------------------------------------------
# B4: Missing produce row -> stale (unavailable not green)
# ---------------------------------------------------------------------------

def test_b4_missing_produce_row_is_stale():
    f_row = _freshness_row(fresh=True, status="fresh", age_seconds=30)
    result = align_stem("nba", produce_row=None, freshness_row=f_row, sla_sec=300.0)
    assert result["aligned_fresh"] != "fresh", (
        "B4: missing produce row must degrade verdict; got %r" % result
    )
    assert result["aligned_ok"] is False


# ---------------------------------------------------------------------------
# B5: Missing freshness row -> stale (unavailable not green)
# ---------------------------------------------------------------------------

def test_b5_missing_freshness_row_is_stale():
    p_row = _produce_row(ok=True, status="ok", age_seconds=30)
    result = align_stem("nba", produce_row=p_row, freshness_row=None, sla_sec=300.0)
    assert result["aligned_fresh"] != "fresh", (
        "B5: missing freshness row must degrade verdict; got %r" % result
    )
    assert result["aligned_ok"] is False


# ---------------------------------------------------------------------------
# B6: Both rows missing -> stale (never green)
# ---------------------------------------------------------------------------

def test_b6_both_rows_missing_is_stale():
    result = align_stem("nba", produce_row=None, freshness_row=None, sla_sec=300.0)
    assert result["aligned_fresh"] != "fresh", "B6: both absent must not be green"
    assert result["aligned_ok"] is False


# ---------------------------------------------------------------------------
# B7: No $ field anywhere
# ---------------------------------------------------------------------------

def test_b7_no_dollar_key_single():
    p_row = _produce_row(ok=True, age_seconds=60)
    f_row = _freshness_row(fresh=True, age_seconds=60)
    result = align_stem("nba", p_row, f_row)
    assert not _has_dollar_key(result), "B7: no $ key in align_stem output"
    assert result.get("edge_claimed") is False


def test_b7_no_dollar_key_batch():
    stems = ["nba", "mlb"]
    result = align_stems(stems, {}, {}, sla_sec=300.0)
    assert not _has_dollar_key(result), "B7: no $ key in align_stems output"
    assert result.get("edge_claimed") is False


# ---------------------------------------------------------------------------
# B8: NEVER raises on garbage inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stem,p_row,f_row", [
    (None, None, None),
    ("", {}, {}),
    ("nba", {"fresh": object()}, {"fresh": object()}),
    ("nba", {"ok": "not-bool"}, {"fresh": 42}),
    ("nba", None, {"fresh": None, "age_seconds": "not-a-number"}),
])
def test_b8_never_raises(stem, p_row, f_row):
    try:
        result = align_stem(stem, p_row, f_row, sla_sec=300.0)
        assert result.get("aligned_ok") in (True, False)
    except Exception as exc:
        pytest.fail("B8: align_stem raised on garbage input: %s" % exc)


# ---------------------------------------------------------------------------
# B9: align_stems -- any stale stem degrades overall (monotone-DOWN)
# ---------------------------------------------------------------------------

def test_b9_batch_stale_stem_degrades_overall():
    p_rows = {
        "nba": _produce_row("nba", ok=True, age_seconds=30),
        "mlb": _produce_row("mlb", ok=False, status="stale", age_seconds=9999),
    }
    f_rows = {
        "nba": _freshness_row("nba", fresh=True, age_seconds=30),
        "mlb": _freshness_row("mlb", fresh=False, status="stale", age_seconds=9999),
    }
    result = align_stems(["nba", "mlb"], p_rows, f_rows, sla_sec=300.0)
    assert result["overall"] != "ok", (
        "B9: stale stem must degrade overall off ok; got %r" % result["overall"]
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# B10: align_stems empty -> overall degraded (never ok)
# ---------------------------------------------------------------------------

def test_b10_empty_stems_is_degraded():
    result = align_stems([], {}, {}, sla_sec=300.0)
    assert result["overall"] in ("degraded", "down"), (
        "B10: empty stems must be degraded; got %r" % result["overall"]
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# B11: sla_map per-stem override respected
# ---------------------------------------------------------------------------

def test_b11_sla_map_override():
    # Rows with ok=None (ambiguous freshness) so the SLA determines the verdict.
    # age=120s; default sla=300 -> fresh; tight sla=60 -> stale.
    p_rows = {
        "nba": {
            "sport": "nba", "ok": None, "status": "unknown",
            "generated_at": None, "age_seconds": 120.0,
            "n_games": 0, "n_markets": 0, "reason": None,
        }
    }
    f_rows = {
        "nba": {
            "sport": "nba", "status": "unknown", "ok": None,
            "fresh": None, "stale": None, "age_seconds": 120.0,
            "source_ts": None, "reason": None,
        }
    }
    # With default sla=300: age=120 < 300 -> fresh.
    result_default = align_stems(["nba"], p_rows, f_rows, sla_sec=300.0)
    nba_default = result_default["stems"][0]
    assert nba_default["aligned_fresh"] == "fresh", (
        "B11: age=120 < sla=300 should be fresh; got %r" % nba_default
    )
    # With tight sla=60: age=120 > 60 -> stale.
    result_tight = align_stems(["nba"], p_rows, f_rows, sla_sec=300.0,
                                sla_map={"nba": 60.0})
    nba_tight = result_tight["stems"][0]
    assert nba_tight["aligned_fresh"] == "stale", (
        "B11: age=120 >= sla=60 should be stale; got %r" % nba_tight
    )


# ---------------------------------------------------------------------------
# B12: aligned_ok=True ONLY when aligned_fresh=='fresh'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("produce_ok,f_fresh,expect_aligned_fresh", [
    (True, True, "fresh"),
    (True, False, "stale"),
    (False, True, "stale"),
    (False, False, "stale"),
])
def test_b12_aligned_ok_only_when_fresh(produce_ok, f_fresh, expect_aligned_fresh):
    p_row = _produce_row(ok=produce_ok, status="ok" if produce_ok else "stale",
                         age_seconds=30)
    f_row = _freshness_row(fresh=f_fresh, status="fresh" if f_fresh else "stale",
                           age_seconds=30)
    result = align_stem("nba", p_row, f_row, sla_sec=300.0)
    assert result["aligned_fresh"] == expect_aligned_fresh, (
        "B12: produce_ok=%s, f_fresh=%s -> expected %r, got %r" % (
            produce_ok, f_fresh, expect_aligned_fresh, result["aligned_fresh"])
    )
    assert result["aligned_ok"] == (result["aligned_fresh"] == "fresh"), (
        "B12: aligned_ok must match aligned_fresh=='fresh'"
    )


# ---------------------------------------------------------------------------
# B13: produce=fresh + freshness=down -> aligned down (worst of three)
# ---------------------------------------------------------------------------

def test_b13_produce_fresh_freshness_down_gives_down():
    p_row = _produce_row(ok=True, status="ok", age_seconds=30)
    f_row = {
        "sport": "nba", "status": "missing", "ok": False,
        "fresh": False, "stale": True, "age_seconds": None,
        "source_ts": None, "reason": "feed missing",
    }
    result = align_stem("nba", p_row, f_row, sla_sec=300.0)
    # freshness says 'missing' -> should degrade to at least stale or down.
    assert result["aligned_ok"] is False, "B13: down freshness must not be ok"
    assert result["aligned_fresh"] in ("stale", "down"), (
        "B13: produce=fresh + freshness=down must give stale or down; got %r" % result
    )


# ---------------------------------------------------------------------------
# B14: coerce_produce_row -- ok=True->fresh='fresh'; ok=False+unavailable->'down'
# ---------------------------------------------------------------------------

def test_b14_coerce_produce_row_ok_true():
    row = {"sport": "nba", "ok": True, "status": "ok", "age_seconds": 60.0,
           "generated_at": _ts_ago(60), "n_games": 2, "n_markets": 6, "reason": None}
    out = coerce_produce_row(row)
    assert out["fresh"] == "fresh", "B14: ok=True -> fresh='fresh'"
    assert out.get("age_sec") == 60.0, "B14: age_seconds renamed to age_sec"


def test_b14_coerce_produce_row_unavailable():
    row = {"sport": "mlb", "ok": False, "status": "unavailable",
           "age_seconds": None, "generated_at": None,
           "n_games": 0, "n_markets": 0, "reason": "read error"}
    out = coerce_produce_row(row)
    assert out["fresh"] == "down", "B14: ok=False+unavailable -> fresh='down'"


def test_b14_coerce_produce_row_stale():
    row = {"sport": "mlb", "ok": False, "status": "stale",
           "age_seconds": 9999.0, "generated_at": _ts_ago(9999),
           "n_games": 0, "n_markets": 0, "reason": None}
    out = coerce_produce_row(row)
    assert out["fresh"] == "stale", "B14: ok=False+stale -> fresh='stale'"


# ---------------------------------------------------------------------------
# B15: coerce_freshness_row -- fresh=True->'fresh'; fresh=False+missing->'down'
# ---------------------------------------------------------------------------

def test_b15_coerce_freshness_row_true():
    row = {"sport": "nba", "status": "fresh", "ok": True, "fresh": True,
           "stale": False, "age_seconds": 60.0, "source_ts": _ts_ago(60), "reason": None}
    out = coerce_freshness_row(row)
    assert out["fresh"] == "fresh", "B15: fresh=True -> 'fresh'"
    assert out.get("age_sec") == 60.0, "B15: age_seconds renamed"


def test_b15_coerce_freshness_row_false_missing():
    row = {"sport": "nba", "status": "missing", "ok": False, "fresh": False,
           "stale": True, "age_seconds": None, "source_ts": None,
           "reason": "feed missing"}
    out = coerce_freshness_row(row)
    assert out["fresh"] == "down", "B15: fresh=False+missing -> 'down'"


def test_b15_coerce_freshness_row_false_stale():
    row = {"sport": "nba", "status": "stale", "ok": False, "fresh": False,
           "stale": True, "age_seconds": 9999.0, "source_ts": _ts_ago(9999),
           "reason": None}
    out = coerce_freshness_row(row)
    assert out["fresh"] == "stale", "B15: fresh=False+stale -> 'stale'"


# ---------------------------------------------------------------------------
# Extra: align_stems all-fresh -> overall ok
# ---------------------------------------------------------------------------

def test_all_fresh_stems_gives_ok():
    p_rows = {
        "nba": _produce_row("nba", ok=True, age_seconds=30),
        "mlb": _produce_row("mlb", ok=True, age_seconds=30),
    }
    f_rows = {
        "nba": _freshness_row("nba", fresh=True, age_seconds=30),
        "mlb": _freshness_row("mlb", fresh=True, age_seconds=30),
    }
    result = align_stems(["nba", "mlb"], p_rows, f_rows, sla_sec=300.0)
    assert result["overall"] == "ok", (
        "All-fresh stems should give ok overall; got %r" % result["overall"]
    )
    assert result["n_fresh"] == 2
    assert result["n_stale"] == 0


# ---------------------------------------------------------------------------
# Extra: align_stems never raises on completely garbage input
# ---------------------------------------------------------------------------

def test_align_stems_never_raises_garbage():
    try:
        result = align_stems(None, None, None, sla_sec=300.0)  # type: ignore[arg-type]
        assert result.get("ok") in (True, False)
    except Exception as exc:
        pytest.fail("align_stems raised on None input: %s" % exc)
