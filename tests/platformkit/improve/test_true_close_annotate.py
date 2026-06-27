"""Per-file tests for scripts.platformkit.improve.true_close_annotate.

Acceptance criteria (from BACKLOG.md SIX-03):
  (1) genuine closing snapshot -> is_true_close=True, p_close populated
  (2) L5/pregame-proxy-only   -> is_true_close=False (REPLICATION_PENDING stays)
  (3) no close (None)         -> is_true_close=False, p_close=None
  (4) batch over mixed rows   -> only genuine-close rows flip True
  (5) pure: never fabricates a p_close (proxy or missing -> None always)
  (6) no $/roi/pnl/profit/edge key in any output; ASCII; never raises

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/improve/test_true_close_annotate.py -q
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pytest

from scripts.platformkit.improve.true_close_annotate import (
    annotate_batch,
    annotate_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit|edge)", re.IGNORECASE)


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(str(k))
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(obj: Any, context: str = "") -> None:
    for k in _all_keys(obj):
        assert not _BANNED_KEY_RE.search(k), (
            "Banned key '%s' found in output%s" % (k, (" (%s)" % context) if context else "")
        )


def _ascii_only(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


# ---------------------------------------------------------------------------
# Stub snapshot functions (no network, no line_store disk access)
# ---------------------------------------------------------------------------

# Decimal odds for a typical NBA game: home -150, away +130
# decimal: home = 1 + 100/150 = 1.667, away = 1 + 130/100 = 2.30
_HOME_ODDS = 1.6667   # ~-150 US
_AWAY_ODDS = 2.30     # +130 US

_GENUINE_QUOTES: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("moneyline", "home"): {"odds": _HOME_ODDS, "book": "pinnacle", "side": "home"},
    ("moneyline", "away"): {"odds": _AWAY_ODDS, "book": "pinnacle", "side": "away"},
}


def _snap_genuine(game_id: str) -> Optional[Tuple[Dict, bool]]:
    """Returns a genuine close snapshot (is_true_close=True) for any game_id."""
    return (_GENUINE_QUOTES, True)


def _snap_proxy(game_id: str) -> Optional[Tuple[Dict, bool]]:
    """Returns a proxy snapshot (is_true_close=False, last-seen fallback)."""
    return (_GENUINE_QUOTES, False)  # same quotes, but NOT a true close


def _snap_none(game_id: str) -> Optional[Tuple[Dict, bool]]:
    """Returns None: no closing snapshot in the store."""
    return None


def _snap_bad_odds(game_id: str) -> Optional[Tuple[Dict, bool]]:
    """Returns a true-close snapshot but with invalid decimal odds (can't devig)."""
    bad_quotes: Dict[Tuple[str, str], Dict[str, Any]] = {
        ("moneyline", "home"): {"odds": 0.5},   # <= 1.0 -- invalid
        ("moneyline", "away"): {"odds": 2.30},
    }
    return (bad_quotes, True)


def _snap_missing_moneyline(game_id: str) -> Optional[Tuple[Dict, bool]]:
    """Returns a true-close snapshot but with no moneyline market at all."""
    quotes: Dict[Tuple[str, str], Dict[str, Any]] = {
        ("spread", "home"): {"odds": 1.909},
        ("spread", "away"): {"odds": 1.909},
    }
    return (quotes, True)


def _snap_raises(game_id: str) -> Optional[Tuple[Dict, bool]]:
    """Simulates a snapshot_fn that raises (e.g. network timeout). Pure fn must survive."""
    raise RuntimeError("simulated timeout")


def _snap_by_id(genuine_ids: frozenset) -> Any:
    """Factory: returns a snap fn that is genuine for listed ids, proxy otherwise."""
    def _fn(game_id: str) -> Optional[Tuple[Dict, bool]]:
        if game_id in genuine_ids:
            return (_GENUINE_QUOTES, True)
        return (_GENUINE_QUOTES, False)
    return _fn


# ---------------------------------------------------------------------------
# Minimal settled row factory
# ---------------------------------------------------------------------------

def _row(game_id: str = "g001", p_raw: float = 0.52, y: float = 1.0) -> Dict[str, Any]:
    return {
        "game_id": game_id,
        "p_raw": p_raw,
        "y": y,
        "outcome": y,
        "sport": "nba",
    }


# ---------------------------------------------------------------------------
# Test (1): genuine closing snapshot -> is_true_close=True, p_close populated
# ---------------------------------------------------------------------------

class TestGenuineClose:
    def test_is_true_close_flag(self) -> None:
        row = _row("g001")
        out = annotate_row(row, _snap_genuine)
        assert out["is_true_close"] is True, "genuine snapshot must set is_true_close=True"

    def test_p_close_is_float_in_range(self) -> None:
        row = _row("g001")
        out = annotate_row(row, _snap_genuine)
        p = out["p_close"]
        assert isinstance(p, float), "p_close must be float"
        assert 0.0 < p < 1.0, "p_close must be a valid probability"

    def test_p_close_reasonable_for_favorite(self) -> None:
        # home at -150 decimal 1.667, away +130 decimal 2.30 ->
        # devigged home prob should be roughly 0.56-0.62
        row = _row("g001")
        out = annotate_row(row, _snap_genuine)
        assert out["p_close"] > 0.50, (
            "home favorite at -150 should devig above 0.50, got %s" % out["p_close"]
        )

    def test_original_fields_unchanged(self) -> None:
        row = _row("g001", p_raw=0.58, y=1.0)
        out = annotate_row(row, _snap_genuine)
        assert out["p_raw"] == 0.58, "annotator must not modify p_raw"
        assert out["y"] == 1.0, "annotator must not modify y"
        assert out["game_id"] == "g001"
        assert out["sport"] == "nba"

    def test_vs_close_unproven(self) -> None:
        # The annotator stamps vs_close=UNPROVEN; it does NOT claim a win.
        out = annotate_row(_row(), _snap_genuine)
        assert out.get("vs_close") == "UNPROVEN"

    def test_no_banned_keys(self) -> None:
        out = annotate_row(_row(), _snap_genuine)
        _assert_no_banned_keys(out, "genuine close row")

    def test_output_ascii(self) -> None:
        out = annotate_row(_row(), _snap_genuine)
        for v in out.values():
            if isinstance(v, str):
                assert _ascii_only(v), "non-ASCII value: %r" % v


# ---------------------------------------------------------------------------
# Test (2): L5/pregame-proxy-only -> is_true_close=False (REPLICATION_PENDING)
# ---------------------------------------------------------------------------

class TestProxyClose:
    def test_is_true_close_false(self) -> None:
        out = annotate_row(_row(), _snap_proxy)
        assert out["is_true_close"] is False, (
            "proxy snapshot must keep is_true_close=False (REPLICATION_PENDING)"
        )

    def test_p_close_none_for_proxy(self) -> None:
        out = annotate_row(_row(), _snap_proxy)
        assert out["p_close"] is None, (
            "proxy snapshot must NOT populate p_close (never fabricate)"
        )

    def test_original_fields_unchanged(self) -> None:
        row = _row("g999", p_raw=0.45, y=0.0)
        out = annotate_row(row, _snap_proxy)
        assert out["p_raw"] == 0.45
        assert out["y"] == 0.0
        assert out["game_id"] == "g999"

    def test_no_banned_keys(self) -> None:
        out = annotate_row(_row(), _snap_proxy)
        _assert_no_banned_keys(out, "proxy close row")


# ---------------------------------------------------------------------------
# Test (3): no close (snapshot_fn returns None) -> is_true_close=False, p_close=None
# ---------------------------------------------------------------------------

class TestNoClose:
    def test_is_true_close_false(self) -> None:
        out = annotate_row(_row(), _snap_none)
        assert out["is_true_close"] is False

    def test_p_close_none(self) -> None:
        out = annotate_row(_row(), _snap_none)
        assert out["p_close"] is None

    def test_original_fields_unchanged(self) -> None:
        row = _row("g002", p_raw=0.60, y=1.0)
        out = annotate_row(row, _snap_none)
        assert out["p_raw"] == 0.60
        assert out["y"] == 1.0

    def test_no_banned_keys(self) -> None:
        out = annotate_row(_row(), _snap_none)
        _assert_no_banned_keys(out, "no-close row")


# ---------------------------------------------------------------------------
# Test (4): batch over mixed rows -> only genuine-close rows flip True
# ---------------------------------------------------------------------------

class TestBatch:
    def test_only_genuine_rows_flip(self) -> None:
        genuine_ids = frozenset({"g_real_1", "g_real_2"})
        rows = [
            _row("g_real_1"),   # -> genuine
            _row("g_proxy_1"),  # -> proxy
            _row("g_real_2"),   # -> genuine
            _row("g_proxy_2"),  # -> proxy
            _row("g_real_3"),   # -> proxy (not in genuine_ids)
        ]
        snap = _snap_by_id(genuine_ids)
        annotated = annotate_batch(rows, snap)
        assert len(annotated) == 5

        assert annotated[0]["is_true_close"] is True,  "g_real_1 should be true close"
        assert annotated[1]["is_true_close"] is False, "g_proxy_1 should stay False"
        assert annotated[2]["is_true_close"] is True,  "g_real_2 should be true close"
        assert annotated[3]["is_true_close"] is False, "g_proxy_2 should stay False"
        assert annotated[4]["is_true_close"] is False, "g_real_3 (proxy) should stay False"

    def test_genuine_rows_have_p_close(self) -> None:
        genuine_ids = frozenset({"g_real_1"})
        rows = [_row("g_real_1"), _row("g_proxy_1")]
        snap = _snap_by_id(genuine_ids)
        out = annotate_batch(rows, snap)
        assert out[0]["p_close"] is not None and 0 < out[0]["p_close"] < 1
        assert out[1]["p_close"] is None

    def test_proxy_rows_have_no_p_close(self) -> None:
        rows = [_row("g001"), _row("g002")]
        out = annotate_batch(rows, _snap_proxy)
        for r in out:
            assert r["p_close"] is None, "proxy batch must never populate p_close"

    def test_empty_batch_returns_empty(self) -> None:
        out = annotate_batch([], _snap_genuine)
        assert out == []

    def test_no_banned_keys_in_batch(self) -> None:
        rows = [_row("g001"), _row("g002"), _row("g003")]
        snap = _snap_by_id(frozenset({"g001"}))
        out = annotate_batch(rows, snap)
        _assert_no_banned_keys(out, "batch output")

    def test_order_preserved(self) -> None:
        ids = ["z", "a", "m", "b"]
        rows = [_row(i) for i in ids]
        out = annotate_batch(rows, _snap_genuine)
        out_ids = [r["game_id"] for r in out]
        assert out_ids == ids, "annotate_batch must preserve row order"


# ---------------------------------------------------------------------------
# Test (5): pure -- never fabricates a p_close
# ---------------------------------------------------------------------------

class TestPureNeverFabricates:
    def test_proxy_never_populates_p_close(self) -> None:
        for _ in range(10):
            out = annotate_row(_row(), _snap_proxy)
            assert out["p_close"] is None, "proxy must never populate p_close"

    def test_none_snapshot_never_populates(self) -> None:
        out = annotate_row(_row(), _snap_none)
        assert out["p_close"] is None

    def test_bad_odds_never_populates(self) -> None:
        # Genuine snapshot (is_true_close=True from store) but devigging fails.
        out = annotate_row(_row(), _snap_bad_odds)
        assert out["is_true_close"] is False, (
            "bad odds in genuine snapshot -> devig fails -> is_true_close stays False"
        )
        assert out["p_close"] is None, "bad odds must not produce a fabricated p_close"

    def test_missing_moneyline_never_populates(self) -> None:
        # Genuine close but only spread market available -- cannot devig moneyline.
        out = annotate_row(_row(), _snap_missing_moneyline)
        assert out["p_close"] is None
        assert out["is_true_close"] is False

    def test_raising_snapshot_fn_never_raises(self) -> None:
        # Pure fn must not propagate exceptions from snapshot_fn.
        try:
            out = annotate_row(_row(), _snap_raises)
        except Exception as exc:
            pytest.fail("annotate_row raised on a failing snapshot_fn: %s" % exc)
        assert out["is_true_close"] is False
        assert out["p_close"] is None

    def test_raising_snapshot_fn_in_batch_never_raises(self) -> None:
        rows = [_row("g001"), _row("g002")]
        try:
            out = annotate_batch(rows, _snap_raises)
        except Exception as exc:
            pytest.fail("annotate_batch raised on a failing snapshot_fn: %s" % exc)
        for r in out:
            assert r["is_true_close"] is False
            assert r["p_close"] is None

    def test_no_game_id_never_raises(self) -> None:
        row = {"p_raw": 0.5, "y": 1.0}   # no game_id
        try:
            out = annotate_row(row, _snap_genuine)
        except Exception as exc:
            pytest.fail("annotate_row raised on a row with no game_id: %s" % exc)
        assert out["is_true_close"] is False
        assert out["p_close"] is None

    def test_idempotent_genuine(self) -> None:
        # A row already annotated as is_true_close=True must be returned unchanged.
        row = _row("g001")
        first = annotate_row(row, _snap_genuine)
        assert first["is_true_close"] is True
        p_first = first["p_close"]
        second = annotate_row(first, _snap_none)  # second pass with no snapshot
        assert second["is_true_close"] is True, "idempotent: already-true row must stay True"
        assert second["p_close"] == p_first, "idempotent: p_close must not change"


# ---------------------------------------------------------------------------
# Test (6): no $/roi/pnl/profit/edge key; ASCII; never raises
# ---------------------------------------------------------------------------

class TestHonestyConstraints:
    def test_no_banned_keys_genuine(self) -> None:
        out = annotate_row(_row(), _snap_genuine)
        _assert_no_banned_keys(out, "genuine row output")

    def test_no_banned_keys_proxy(self) -> None:
        out = annotate_row(_row(), _snap_proxy)
        _assert_no_banned_keys(out, "proxy row output")

    def test_no_banned_keys_none(self) -> None:
        out = annotate_row(_row(), _snap_none)
        _assert_no_banned_keys(out, "none snapshot output")

    def test_no_banned_keys_batch(self) -> None:
        rows = [_row("g%d" % i) for i in range(5)]
        out = annotate_batch(rows, _snap_genuine)
        _assert_no_banned_keys(out, "batch output")

    def test_all_string_values_ascii(self) -> None:
        out = annotate_row(_row(), _snap_genuine)
        for k, v in out.items():
            assert _ascii_only(str(k)), "key not ASCII: %r" % k
            if isinstance(v, str):
                assert _ascii_only(v), "value not ASCII: %r" % v

    def test_never_raises_on_none_row_fields(self) -> None:
        row = {"game_id": None, "p_raw": None, "y": None}
        try:
            out = annotate_row(row, _snap_genuine)
        except Exception as exc:
            pytest.fail("annotate_row raised on None fields: %s" % exc)
        assert out["is_true_close"] is False

    def test_never_raises_on_completely_empty_row(self) -> None:
        try:
            out = annotate_row({}, _snap_genuine)
        except Exception as exc:
            pytest.fail("annotate_row raised on empty row: %s" % exc)
        assert out["is_true_close"] is False
        assert out["p_close"] is None

    def test_never_raises_on_malformed_snapshot_return(self) -> None:
        def _bad_snap(_gid: str) -> Any:
            return "not a tuple"  # unexpected shape
        try:
            out = annotate_row(_row(), _bad_snap)  # type: ignore[arg-type]
        except Exception as exc:
            pytest.fail("annotate_row raised on malformed snapshot return: %s" % exc)
        assert out["is_true_close"] is False
        assert out["p_close"] is None

    def test_vs_close_unproven_not_claimed(self) -> None:
        # Even for a genuine close, vs_close must be UNPROVEN (calibration gate decides)
        out = annotate_row(_row(), _snap_genuine)
        vc = out.get("vs_close")
        assert vc == "UNPROVEN", (
            "annotator must never claim a CLV win; vs_close must be UNPROVEN, got %r" % vc
        )

    def test_note_says_calibration_not_edge(self) -> None:
        out = annotate_row(_row(), _snap_genuine)
        note = out.get("note", "")
        assert "calibration" in note.lower(), (
            "note must contain 'calibration' framing, got %r" % note
        )
        assert "edge" not in note.lower() or "not edge" in note.lower(), (
            "note must not claim an edge, got %r" % note
        )
