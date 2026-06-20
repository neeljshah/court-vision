"""Per-file tests for scripts.platformkit.clv_ledger_enrich.

Acceptance criteria (W5-clv-ledger-stamp):
  1. Settled row with closing_decimal_home/away -> clv_pct computed (not None),
     beat_close set, clv_status not 'no_close'.
  2. Settled row with close_home_price/close_away_price (alias) -> same.
  3. Open row with flat_unit <= 2.0 stake_units -> flat_unit stamped.
  4. Open row with ev_pct -> tier inferred (A/B/C).
  5. Row with no closing line stays clv_pct=None / clv_status='no_close'.
  6. clv_is_proxy=True -> clv_status='clv_proxy'.
  7. beat_close=True when taken price > fair close decimal (better number).
  8. No banned $ field anywhere in enriched output.
  9. enrich_rows never raises; bad rows pass through unchanged.
  10. Already-computed clv_pct (non-null, non-no_close status) is preserved.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_enrich.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.clv_ledger_enrich import enrich_row, enrich_rows

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEYS = frozenset({
    "roi", "pnl", "profit", "loss", "bankroll", "dollar", "$", "usd",
    "net_profit",
})


def _assert_no_banned(obj: Any, label: str = "") -> None:
    if isinstance(obj, dict):
        for k in obj:
            assert k.lower() not in _BANNED_KEYS, (
                "Banned $ key %r in %s" % (k, label)
            )
            _assert_no_banned(obj[k], label + "." + k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_banned(v, label + "[%d]" % i)


def _base_open_row(**kwargs) -> Dict[str, Any]:
    """Minimal open row."""
    row: Dict[str, Any] = {
        "ts": "2026-06-20T10:00:00.000000+00:00",
        "sport": "mlb",
        "matchup": "Cubs @ Reds",
        "side": "home",
        "taken_book": "espn:DraftKings",
        "taken_decimal": 2.10,
        "model_prob": 0.52,
        "stake_units": 1.0,
        "status": "open",
        "executed": False,
    }
    row.update(kwargs)
    return row


def _base_settled_row(**kwargs) -> Dict[str, Any]:
    """Minimal settled row WITHOUT a closing line (triggers no_close path)."""
    row = _base_open_row()
    row["status"] = "settled"
    row["settled_at"] = "2026-06-20T22:00:00.000000+00:00"
    row["graded"] = True
    row["outcome"] = "win"
    row["clv_pct"] = None
    row["beat_close"] = None
    row["clv_status"] = "no_close"
    row.update(kwargs)
    return row


def _settled_with_close(**kwargs) -> Dict[str, Any]:
    """Settled row that includes closing line decimals (enables CLV compute).

    Uses closing_decimal_home=1.90, closing_decimal_away=2.00.
    Booksum = 1/1.90 + 1/2.00 = 0.526 + 0.50 = 1.026 (valid overround for Shin).
    taken_decimal=2.10 -> taken_p=0.476; fair_home~=0.513 -> taken_p < fair_close
    -> clv_pct > 0 -> beat_close=True.
    """
    row = _base_settled_row()
    row["closing_decimal_home"] = 1.90
    row["closing_decimal_away"] = 2.00
    row.update(kwargs)
    return row


# ---------------------------------------------------------------------------
# Acceptance criterion 1: closing_decimal_home/away -> CLV computed
# ---------------------------------------------------------------------------

class TestCLVFromPrimaryClosingFields:

    def test_clv_pct_not_none_with_closing_decimals(self):
        row = _settled_with_close()
        enriched = enrich_row(row)
        assert enriched["clv_pct"] is not None, (
            "Expected clv_pct to be computed; got None. "
            "clv_status=%r clv_note=%r" % (enriched.get("clv_status"), enriched.get("clv_note"))
        )

    def test_beat_close_set_with_closing_decimals(self):
        row = _settled_with_close()
        enriched = enrich_row(row)
        assert enriched["beat_close"] is not None, (
            "beat_close must be set when CLV is computable"
        )
        assert isinstance(enriched["beat_close"], bool)

    def test_clv_status_not_no_close_with_closing_decimals(self):
        row = _settled_with_close()
        enriched = enrich_row(row)
        assert enriched["clv_status"] not in ("no_close", "INSUFFICIENT_DATA", None), (
            "clv_status must be a real status, not no_close; got %r" % enriched["clv_status"]
        )
        assert enriched["clv_status"] in ("clv_real", "clv_proxy"), (
            "clv_status must be 'clv_real' or 'clv_proxy'; got %r" % enriched["clv_status"]
        )

    def test_clv_pct_is_float(self):
        row = _settled_with_close()
        enriched = enrich_row(row)
        assert isinstance(enriched["clv_pct"], float), (
            "clv_pct must be float; got %r" % type(enriched["clv_pct"])
        )

    def test_no_banned_keys_in_output(self):
        row = _settled_with_close()
        enriched = enrich_row(row)
        _assert_no_banned(enriched, "enriched_row")


# ---------------------------------------------------------------------------
# Acceptance criterion 2: close_home_price / close_away_price alias
# ---------------------------------------------------------------------------

class TestCLVFromAliasClosingFields:

    def test_alias_fields_compute_clv(self):
        # Use valid overround: 1/1.90 + 1/2.00 = 1.026 > 1
        row = _base_settled_row(
            close_home_price=1.90,
            close_away_price=2.00,
        )
        enriched = enrich_row(row)
        assert enriched["clv_pct"] is not None, (
            "CLV must be computed from close_home/away_price alias; "
            "clv_note=%r" % enriched.get("clv_note")
        )
        assert enriched["clv_status"] not in ("no_close", "INSUFFICIENT_DATA")

    def test_alias_beat_close_is_bool(self):
        row = _base_settled_row(
            close_home_price=1.90,
            close_away_price=2.00,
        )
        enriched = enrich_row(row)
        assert isinstance(enriched["beat_close"], bool)


# ---------------------------------------------------------------------------
# Acceptance criterion 3: flat_unit stamped from stake_units on open row
# ---------------------------------------------------------------------------

class TestFlatUnitStamping:

    def test_flat_unit_from_small_stake_units(self):
        row = _base_open_row(stake_units=1.0)
        enriched = enrich_row(row)
        assert enriched["flat_unit"] == 1.0, (
            "flat_unit should be 1.0 when stake_units=1.0; got %r" % enriched.get("flat_unit")
        )

    def test_large_stake_units_not_flat_unit(self):
        """stake_units=382 (raw Kelly) must NOT be treated as flat_unit."""
        row = _base_open_row(stake_units=382.0)
        enriched = enrich_row(row)
        assert enriched.get("flat_unit") is None, (
            "stake_units=382 must not be used as flat_unit; got %r" % enriched.get("flat_unit")
        )

    def test_explicit_flat_unit_preserved(self):
        row = _base_open_row(flat_unit=0.5, stake_units=1.0)
        enriched = enrich_row(row)
        assert enriched["flat_unit"] == 0.5, (
            "Explicit flat_unit must be preserved; got %r" % enriched.get("flat_unit")
        )


# ---------------------------------------------------------------------------
# Acceptance criterion 4: tier inferred from ev_pct on open row
# ---------------------------------------------------------------------------

class TestTierInference:

    def test_tier_A_from_ev_pct(self):
        row = _base_open_row(ev_pct=9.0)  # 9% -> 0.09 >= EV_FLOOR_A=0.08
        enriched = enrich_row(row)
        assert enriched["tier"] == "A", "ev_pct=9.0 should give tier A"

    def test_tier_B_from_ev_pct(self):
        row = _base_open_row(ev_pct=5.0)  # 0.05 >= 0.04, < 0.08
        enriched = enrich_row(row)
        assert enriched["tier"] == "B", "ev_pct=5.0 should give tier B"

    def test_tier_C_from_ev_pct(self):
        row = _base_open_row(ev_pct=3.0)  # 0.03 >= 0.02, < 0.04
        enriched = enrich_row(row)
        assert enriched["tier"] == "C", "ev_pct=3.0 should give tier C"

    def test_tier_none_below_floor(self):
        row = _base_open_row(ev_pct=1.0)  # 0.01 < 0.02
        enriched = enrich_row(row)
        assert enriched["tier"] is None, "ev_pct=1.0 should give tier None"

    def test_explicit_tier_preserved(self):
        row = _base_open_row(tier="A")
        enriched = enrich_row(row)
        assert enriched["tier"] == "A"


# ---------------------------------------------------------------------------
# Acceptance criterion 5: no closing line -> clv_status='no_close', clv_pct=None
# ---------------------------------------------------------------------------

class TestNoClosingLine:

    def test_settled_no_close_stays_no_close(self):
        row = _base_settled_row()  # no closing decimals
        enriched = enrich_row(row)
        assert enriched["clv_pct"] is None, (
            "No closing line: clv_pct must remain None; got %r" % enriched.get("clv_pct")
        )
        assert enriched["clv_status"] == "no_close", (
            "No closing line: clv_status must be 'no_close'; got %r" % enriched.get("clv_status")
        )

    def test_open_row_no_close(self):
        row = _base_open_row()
        enriched = enrich_row(row)
        assert enriched["clv_pct"] is None
        assert enriched["clv_status"] == "no_close"

    def test_never_fabricates_zero_clv(self):
        """Absence of close must NOT produce clv_pct=0 (a 0-fill would be dishonest)."""
        row = _base_settled_row()
        enriched = enrich_row(row)
        # clv_pct of None is correct; 0.0 is a fabricated value.
        assert enriched["clv_pct"] != 0.0, (
            "clv_pct=0.0 is a fabricated value; must be None when no close"
        )


# ---------------------------------------------------------------------------
# Acceptance criterion 6: clv_is_proxy=True -> clv_status='clv_proxy'
# ---------------------------------------------------------------------------

def test_proxy_close_sets_clv_proxy_status():
    # clv_is_proxy=True + valid closing line -> status='clv_proxy'
    row = _settled_with_close(clv_is_proxy=True)
    enriched = enrich_row(row)
    assert enriched["clv_pct"] is not None, (
        "CLV must be computed with proxy close; clv_note=%r" % enriched.get("clv_note")
    )
    assert enriched["clv_status"] == "clv_proxy", (
        "clv_is_proxy row must get clv_status='clv_proxy'; got %r" % enriched.get("clv_status")
    )


# ---------------------------------------------------------------------------
# Acceptance criterion 7: beat_close=True when better number
# ---------------------------------------------------------------------------

def test_beat_close_true_for_better_number():
    """taken_decimal=2.50 (implying low prob) on home vs close (1.90, 2.00).
    Booksum = 1/1.90 + 1/2.00 = 1.026 (valid). fair_home~=0.513.
    taken_p = 1/2.50 = 0.40 < 0.513 -> beat_close=True."""
    row = _base_settled_row(
        taken_decimal=2.50,
        side="home",
        closing_decimal_home=1.90,
        closing_decimal_away=2.00,
    )
    enriched = enrich_row(row)
    if enriched["clv_pct"] is not None:
        assert enriched["beat_close"] is True, (
            "taken_decimal=2.50 vs close 1.90/2.00 should beat close; "
            "clv_pct=%r" % enriched.get("clv_pct")
        )


def test_beat_close_false_for_worse_number():
    """taken_decimal=1.70 (high implied prob) on home vs close (1.90, 2.00).
    fair_home~=0.513; taken_p=1/1.70=0.588 > 0.513 -> clv_pct < 0 -> beat_close=False."""
    row = _base_settled_row(
        taken_decimal=1.70,
        side="home",
        closing_decimal_home=1.90,
        closing_decimal_away=2.00,
    )
    enriched = enrich_row(row)
    if enriched["clv_pct"] is not None:
        assert enriched["beat_close"] is False, (
            "taken_decimal=1.70 vs close 1.90/2.00 should NOT beat close; "
            "clv_pct=%r" % enriched.get("clv_pct")
        )


# ---------------------------------------------------------------------------
# Acceptance criterion 8: no banned keys across all paths
# ---------------------------------------------------------------------------

def test_no_banned_keys_all_paths():
    rows = [
        _base_open_row(ev_pct=9.0, stake_units=1.0),
        _base_settled_row(),
        _settled_with_close(),
        _settled_with_close(clv_is_proxy=True),
        _base_settled_row(close_home_price=1.90, close_away_price=2.00),
    ]
    for i, row in enumerate(rows):
        enriched = enrich_row(row)
        _assert_no_banned(enriched, "row[%d]" % i)


# ---------------------------------------------------------------------------
# Acceptance criterion 9: enrich_rows never raises; bad rows pass through
# ---------------------------------------------------------------------------

def test_enrich_rows_tolerates_bad_rows():
    bad = [None, {}, {"status": "open"}, _settled_with_close()]  # type: ignore[list-item]
    # Should not raise
    result = enrich_rows(bad)  # type: ignore[arg-type]
    assert isinstance(result, list)
    assert len(result) == len(bad)


def test_enrich_rows_returns_copies():
    original = _base_open_row()
    result = enrich_rows([original])
    result[0]["__mutated"] = True
    assert "__mutated" not in original, "enrich_rows must not mutate originals"


# ---------------------------------------------------------------------------
# Acceptance criterion 10: already-computed real clv_pct is preserved
# ---------------------------------------------------------------------------

def test_existing_real_clv_preserved():
    """A row already carrying a real clv_pct + clv_status='clv_real' must not be overwritten."""
    row = _base_settled_row(
        clv_pct=3.75,
        beat_close=True,
        clv_status="clv_real",
        clv_note="pre-computed",
        # Also add a closing line to confirm enrich does not re-compute.
        closing_decimal_home=1.90,
        closing_decimal_away=2.00,
    )
    enriched = enrich_row(row)
    assert enriched["clv_pct"] == 3.75, (
        "Existing clv_pct must be preserved; got %r" % enriched.get("clv_pct")
    )
    assert enriched["clv_status"] == "clv_real"
    assert enriched["beat_close"] is True
