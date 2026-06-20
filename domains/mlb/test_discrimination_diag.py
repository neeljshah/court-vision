"""domains.mlb.test_discrimination_diag -- Per-file tests for discrimination_diag.py.

Acceptance criteria (WORKSTREAM MLB-DISCRIM-DIAG):
  A1. 12 cards with only 4 unique probs -> status NOT_DISCRIMINATING + n_unique_probs=4.
  A2. Well-spread probs (each unique) -> status OK.
  A3. Fewer than min_games probs -> status INSUFFICIENT_DATA.
  A4. None / empty input -> status UNAVAILABLE.
  A5. All-same probs (n_unique=1) -> NOT_DISCRIMINATING regardless of n_games.
  A6. No $ / roi / pnl field in any output.
  A7. Never raises on any input.
  A8. from_recal_result convenience wrapper works on a synthetic RecalResult.
  A9. from_market_surfaces convenience wrapper reads moneyline.home correctly.
  A10. reason string is non-empty ASCII; note contains 'calibration'.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_discrimination_diag.py -q
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from domains.mlb.discrimination_diag import (
    MIN_DISCRIMINATION_RATIO,
    MIN_GAMES,
    STATUS_INSUFFICIENT_DATA,
    STATUS_NOT_DISCRIMINATING,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    from_market_surfaces,
    from_recal_result,
    scan_moneyline_probs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "stake", "usd", "dollar",
    "edge_dollars", "expected_value_dollars",
})


def _no_forbidden(result: Dict[str, Any]) -> bool:
    """Recursively check no forbidden key appears in result."""
    for k, v in result.items():
        if str(k).lower() in _FORBIDDEN_KEYS:
            return False
        if isinstance(v, dict) and not _no_forbidden(v):
            return False
    return True


def _spread_probs(n: int) -> List[float]:
    """Return n distinct evenly-spaced probs in (0.30, 0.70)."""
    step = 0.40 / max(n - 1, 1)
    return [round(0.30 + i * step, 6) for i in range(n)]


@dataclass
class _FakeRecalResult:
    """Minimal stub matching RecalResult shape consumed by from_recal_result."""
    recal_probs: Any
    note: str = "calibration, not edge"
    vs_close: str = "UNPROVEN"


# ---------------------------------------------------------------------------
# A1: 12 cards, 4 unique probs -> NOT_DISCRIMINATING
# ---------------------------------------------------------------------------

class TestNotDiscriminating:

    def test_12_cards_4_unique_probs(self):
        """Task spec: 12 cards, 4 unique model_probs -> NOT_DISCRIMINATING, n_unique=4."""
        # Replicate the live QA finding: 7 x 0.4655, 3 x 0.5345, 1 x 0.4800, 1 x 0.5200
        probs = [0.4655] * 7 + [0.5345] * 3 + [0.4800, 0.5200]
        assert len(probs) == 12
        assert len(set(round(p, 6) for p in probs)) == 4

        result = scan_moneyline_probs(probs)

        assert result["status"] == STATUS_NOT_DISCRIMINATING
        assert result["n_games"] == 12
        assert result["n_unique_probs"] == 4
        assert result["n_dominant"] == 7
        assert abs(result["dominant_prob"] - 0.4655) < 1e-6
        assert result["discrimination_ratio"] == pytest.approx(4 / 12, abs=1e-6)
        assert _no_forbidden(result)

    def test_all_same_probs(self):
        """A5: all 10 cards share one prob -> n_unique=1, NOT_DISCRIMINATING."""
        probs = [0.4655] * 10
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_NOT_DISCRIMINATING
        assert result["n_unique_probs"] == 1
        assert result["discrimination_ratio"] == pytest.approx(1 / 10, abs=1e-6)

    def test_ratio_just_below_threshold(self):
        """4 unique values in 9 games: 4/9 = 0.444 < 0.5 -> NOT_DISCRIMINATING."""
        probs = [0.40] * 3 + [0.45] * 2 + [0.50] * 2 + [0.55] * 2
        assert len(probs) == 9
        assert len(set(probs)) == 4
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_NOT_DISCRIMINATING
        assert result["n_unique_probs"] == 4

    def test_n_unique_reported_in_output(self):
        """n_unique_probs must equal the actual count of distinct values."""
        probs = [0.4655] * 7 + [0.5345] * 3 + [0.4800, 0.5200]
        result = scan_moneyline_probs(probs)
        actual_unique = len(set(round(p, 6) for p in probs))
        assert result["n_unique_probs"] == actual_unique

    def test_dominant_prob_is_most_frequent(self):
        """dominant_prob must be the value appearing most often."""
        probs = [0.5345] * 5 + [0.4655] * 4 + [0.60, 0.65]
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_NOT_DISCRIMINATING
        assert abs(result["dominant_prob"] - 0.5345) < 1e-6
        assert result["n_dominant"] == 5

    def test_reason_ascii_non_empty(self):
        """reason field is non-empty ASCII for NOT_DISCRIMINATING."""
        probs = [0.4655] * 8 + [0.5, 0.6]
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_NOT_DISCRIMINATING
        reason = result["reason"]
        assert isinstance(reason, str) and reason
        reason.encode("ascii")  # raises if non-ASCII

    def test_note_mentions_calibration(self):
        """note must mention 'calibration'."""
        probs = [0.4655] * 8 + [0.5, 0.6]
        result = scan_moneyline_probs(probs)
        assert "calibration" in result["note"].lower()

    def test_no_dollar_keys(self):
        """NOT_DISCRIMINATING output must not contain any forbidden $ key."""
        probs = [0.4655] * 7 + [0.5345] * 3 + [0.4800, 0.5200]
        result = scan_moneyline_probs(probs)
        assert _no_forbidden(result)

    def test_std_dev_is_float_not_discriminating(self):
        """std_dev field is a float (spread measure) even when NOT_DISCRIMINATING."""
        probs = [0.4655] * 7 + [0.5345] * 3 + [0.4800, 0.5200]
        result = scan_moneyline_probs(probs)
        assert isinstance(result["std_dev"], float)


# ---------------------------------------------------------------------------
# A2: Well-spread probs -> OK
# ---------------------------------------------------------------------------

class TestOK:

    def test_all_unique_well_spread(self):
        """A2: 12 fully distinct probs -> OK."""
        probs = _spread_probs(12)
        assert len(set(probs)) == 12
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_OK
        assert result["n_unique_probs"] == 12
        assert result["discrimination_ratio"] == pytest.approx(1.0, abs=1e-6)
        assert _no_forbidden(result)

    def test_ratio_at_boundary_is_ok(self):
        """6 games, 3 unique (ratio=0.5 == threshold) -> OK (boundary inclusive)."""
        probs = [0.40, 0.40, 0.50, 0.50, 0.60, 0.60]
        assert len(probs) == 6
        assert len(set(probs)) == 3
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_OK

    def test_20_distinct_probs(self):
        """Large well-spread slate -> OK."""
        probs = _spread_probs(20)
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_OK
        assert result["n_unique_probs"] == 20

    def test_ok_std_dev_populated(self):
        """OK result includes std_dev as a non-negative float."""
        probs = _spread_probs(10)
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_OK
        assert isinstance(result["std_dev"], float)
        assert result["std_dev"] >= 0.0

    def test_ok_no_forbidden_keys(self):
        """OK output contains no forbidden $ keys."""
        result = scan_moneyline_probs(_spread_probs(10))
        assert _no_forbidden(result)

    def test_ok_reason_ascii(self):
        """OK reason is a non-empty ASCII string."""
        result = scan_moneyline_probs(_spread_probs(10))
        reason = result["reason"]
        assert isinstance(reason, str) and reason
        reason.encode("ascii")

    def test_custom_min_ratio_respected(self):
        """Custom min_ratio=0.8 turns a 10/10 board OK but 7/10 NOT_DISCRIMINATING."""
        probs_ok = _spread_probs(10)  # ratio 1.0 >= 0.8
        assert scan_moneyline_probs(probs_ok, min_ratio=0.8)["status"] == STATUS_OK

        # 7 unique out of 10 -> ratio 0.7 < 0.8
        probs_nd = [round(0.30 + i * 0.05, 4) for i in range(7)] + [0.55, 0.55, 0.55]
        assert len(probs_nd) == 10
        result_nd = scan_moneyline_probs(probs_nd, min_ratio=0.8)
        assert result_nd["status"] == STATUS_NOT_DISCRIMINATING


# ---------------------------------------------------------------------------
# A3: Fewer than min_games -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestInsufficientData:

    def test_fewer_than_min_games(self):
        """A3: 3 valid probs when min_games=5 -> INSUFFICIENT_DATA."""
        probs = [0.40, 0.50, 0.60]
        result = scan_moneyline_probs(probs, min_games=5)
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        assert result["n_games"] == 3
        assert result["discrimination_ratio"] is None
        assert _no_forbidden(result)

    def test_custom_min_games_respected(self):
        """min_games=2 with 3 valid probs -> NOT limited by min_games threshold."""
        probs = [0.40, 0.40, 0.40]  # 3 games, 1 unique -> NOT_DISCRIMINATING
        result = scan_moneyline_probs(probs, min_games=2)
        assert result["status"] == STATUS_NOT_DISCRIMINATING

    def test_insufficient_data_reason_ascii(self):
        """INSUFFICIENT_DATA reason is a non-empty ASCII string."""
        result = scan_moneyline_probs([0.40, 0.50])
        assert result["status"] == STATUS_INSUFFICIENT_DATA
        reason = result["reason"]
        assert isinstance(reason, str) and reason
        reason.encode("ascii")

    def test_insufficient_data_no_forbidden_keys(self):
        """INSUFFICIENT_DATA output has no forbidden keys."""
        result = scan_moneyline_probs([0.40, 0.50, 0.60])
        assert _no_forbidden(result)


# ---------------------------------------------------------------------------
# A4: None / empty -> UNAVAILABLE
# ---------------------------------------------------------------------------

class TestUnavailable:

    def test_none_input(self):
        """A4: None probs -> UNAVAILABLE."""
        result = scan_moneyline_probs(None)
        assert result["status"] == STATUS_UNAVAILABLE
        assert result["n_games"] == 0
        assert _no_forbidden(result)

    def test_empty_list(self):
        """Empty list -> UNAVAILABLE."""
        result = scan_moneyline_probs([])
        assert result["status"] == STATUS_UNAVAILABLE

    def test_all_invalid_values(self):
        """List of None/NaN/string values -> all filtered -> UNAVAILABLE."""
        result = scan_moneyline_probs([None, float("nan"), float("inf"), "bad", -0.5, 1.5])
        assert result["status"] == STATUS_UNAVAILABLE

    def test_unavailable_reason_ascii(self):
        """UNAVAILABLE reason is a non-empty ASCII string."""
        result = scan_moneyline_probs(None)
        reason = result["reason"]
        assert isinstance(reason, str) and reason
        reason.encode("ascii")

    def test_unavailable_no_forbidden_keys(self):
        """UNAVAILABLE output has no forbidden keys."""
        assert _no_forbidden(scan_moneyline_probs(None))
        assert _no_forbidden(scan_moneyline_probs([]))


# ---------------------------------------------------------------------------
# A6/A7: No $ field; never raises
# ---------------------------------------------------------------------------

class TestHonestyAndRobustness:

    @pytest.mark.parametrize("inp", [
        None, [], [None, None], [float("nan")], {}, 42, "bad",
        [None, 0.5, "x", float("inf"), 0.4],
    ])
    def test_never_raises(self, inp):
        """A7: scan_moneyline_probs never raises regardless of input type."""
        result = scan_moneyline_probs(inp)  # type: ignore[arg-type]
        assert isinstance(result, dict)

    def test_mixed_invalid_valid_probs(self):
        """Invalid entries are skipped; valid ones assessed correctly."""
        probs = [None, float("nan"), 0.40, 0.50, 0.60, 0.70, 0.80]
        result = scan_moneyline_probs(probs)
        # 5 valid and distinct -> OK
        assert result["status"] == STATUS_OK
        assert result["n_games"] == 5

    def test_numpy_array_input(self):
        """numpy arrays (RecalResult.recal_probs) are accepted transparently."""
        probs = np.array([0.40, 0.50, 0.60, 0.70, 0.80])
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_OK
        assert result["n_games"] == 5

    def test_numpy_uniform_array(self):
        """Uniform numpy array -> NOT_DISCRIMINATING."""
        probs = np.full(10, 0.4655)
        result = scan_moneyline_probs(probs)
        assert result["status"] == STATUS_NOT_DISCRIMINATING

    def test_output_keys_complete_not_discriminating(self):
        """NOT_DISCRIMINATING output always has all required keys."""
        required = {
            "status", "n_games", "n_unique_probs", "discrimination_ratio",
            "dominant_prob", "n_dominant", "std_dev", "reason", "note",
        }
        probs = [0.4655] * 7 + [0.5345] * 3 + [0.4800, 0.5200]
        result = scan_moneyline_probs(probs)
        assert required.issubset(result.keys())

    def test_output_keys_complete_ok(self):
        """OK output always has all required keys."""
        required = {
            "status", "n_games", "n_unique_probs", "discrimination_ratio",
            "dominant_prob", "n_dominant", "std_dev", "reason", "note",
        }
        result = scan_moneyline_probs(_spread_probs(10))
        assert required.issubset(result.keys())

    def test_no_forbidden_keys_all_statuses(self):
        """A6: no forbidden $ key in any status path."""
        cases = [
            scan_moneyline_probs([0.4655] * 7 + [0.5345] * 3 + [0.4800, 0.5200]),
            scan_moneyline_probs(_spread_probs(10)),
            scan_moneyline_probs([0.40, 0.50, 0.60]),
            scan_moneyline_probs(None),
        ]
        for result in cases:
            assert _no_forbidden(result), f"Forbidden key in: {result}"


# ---------------------------------------------------------------------------
# A8: from_recal_result wrapper
# ---------------------------------------------------------------------------

class TestFromRecalResult:

    def test_from_recal_result_uniform(self):
        """A8: RecalResult with uniform recal_probs -> NOT_DISCRIMINATING."""
        recal = _FakeRecalResult(recal_probs=np.full(10, 0.4655))
        result = from_recal_result(recal)
        assert result["status"] == STATUS_NOT_DISCRIMINATING
        assert _no_forbidden(result)

    def test_from_recal_result_spread(self):
        """RecalResult with spread recal_probs -> OK."""
        recal = _FakeRecalResult(recal_probs=np.array(_spread_probs(12)))
        result = from_recal_result(recal)
        assert result["status"] == STATUS_OK

    def test_from_recal_result_none(self):
        """None recal_result -> UNAVAILABLE, no raise."""
        result = from_recal_result(None)
        assert result["status"] == STATUS_UNAVAILABLE

    def test_from_recal_result_missing_attr(self):
        """Object with no recal_probs attr -> UNAVAILABLE, no raise."""

        class _NoProbs:
            pass

        result = from_recal_result(_NoProbs())
        assert result["status"] == STATUS_UNAVAILABLE

    def test_from_recal_result_fewer_than_min_games(self):
        """RecalResult with 3 probs -> INSUFFICIENT_DATA."""
        recal = _FakeRecalResult(recal_probs=np.array([0.40, 0.50, 0.60]))
        result = from_recal_result(recal)
        assert result["status"] == STATUS_INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# A9: from_market_surfaces wrapper
# ---------------------------------------------------------------------------

class TestFromMarketSurfaces:

    def _make_surface(self, home_prob: float) -> dict:
        """Build a minimal full_market_surface-shaped dict."""
        return {
            "moneyline": {"home": home_prob, "away": round(1.0 - home_prob, 4)},
            "honest_note": "test",
        }

    def test_from_market_surfaces_not_discriminating(self):
        """A9: surfaces with 4 unique probs -> NOT_DISCRIMINATING."""
        probs = [0.4655] * 7 + [0.5345] * 3 + [0.4800, 0.5200]
        surfaces = [self._make_surface(p) for p in probs]
        result = from_market_surfaces(surfaces)
        assert result["status"] == STATUS_NOT_DISCRIMINATING
        assert result["n_unique_probs"] == 4
        assert _no_forbidden(result)

    def test_from_market_surfaces_ok(self):
        """Surfaces with distinct probs -> OK."""
        probs = _spread_probs(12)
        surfaces = [self._make_surface(p) for p in probs]
        result = from_market_surfaces(surfaces)
        assert result["status"] == STATUS_OK

    def test_from_market_surfaces_empty(self):
        """Empty surface list -> UNAVAILABLE."""
        result = from_market_surfaces([])
        assert result["status"] == STATUS_UNAVAILABLE

    def test_from_market_surfaces_none(self):
        """None -> UNAVAILABLE, no raise."""
        result = from_market_surfaces(None)
        assert result["status"] == STATUS_UNAVAILABLE

    def test_from_market_surfaces_missing_moneyline(self):
        """Surfaces missing moneyline key -> those entries yield None -> filtered."""
        surfaces = [{"run_line": {}}, {"run_line": {}}]  # no moneyline key
        result = from_market_surfaces(surfaces)
        # All None after extraction -> UNAVAILABLE
        assert result["status"] == STATUS_UNAVAILABLE

    def test_from_market_surfaces_never_raises(self):
        """from_market_surfaces never raises on malformed input."""
        for inp in [None, [], [None], [{"bad": 1}], 42, "garbage"]:
            r = from_market_surfaces(inp)  # type: ignore[arg-type]
            assert isinstance(r, dict)
