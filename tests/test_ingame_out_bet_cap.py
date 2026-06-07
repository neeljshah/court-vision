"""tests/test_ingame_out_bet_cap.py — BUG-3 (CV_INGAME_OUT_BET_CAP).

The live BET-REGRADE path (slate `_build_slate` + parlay `_build_parlays`)
re-prices each in-play prop from the live engine projection blended with the
pregame q50. That blend never consulted the operator manual OUT list
(``data/cache/cv_fix/live_out_<date>.json``) — the file the box-card path uses
to cap a player who LEFT the game. So a star who walked to the locker room at
22 pts still regraded his OVER 22.5 bet near his full live projection (~24.8),
surfacing a phantom OVER edge.

This module guards the gated cap (``api._courtvision_out_cap``) used by both
regrade paths. Gated default-OFF; byte-identical when the flag is unset OR the
out-list is empty/absent.

Coverage:
  1. Flag OFF -> cap disabled, load_out_set is empty (byte-identical no-op).
  2. Flag ON + empty out-list file -> empty set -> literal no-op.
  3. Flag ON + absent out-list file -> empty set -> literal no-op.
  4. Flag ON + name present -> that name is OUT, others are not.
  5. cap_blended_value caps an OUT player's blend DOWN to current (edge gone).
  6. cap_blended_value leaves a NON-out player's blend unchanged.
  7. cap_blended_value is a no-op when current is None (no fabrication).
  8. Name normalization matches the box path (case/whitespace insensitive).
  9. End-to-end: a synthetic OUT bet (proj 24.8 > current 22, line 22.5) caps
     to 22 -> OVER edge removed; OFF leaves the OVER edge.
"""
from __future__ import annotations

import importlib
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Ensure the flag is OFF before importing the module under test.
os.environ.pop("CV_INGAME_OUT_BET_CAP", None)


def _oc():
    """Import (fresh) the out-cap helper. It reads os.environ per-call so a
    reload is not required, but import lazily so flag state set in a test is
    honoured immediately."""
    import api._courtvision_out_cap as oc
    importlib.reload(oc)
    return oc


def _set_flag(on: bool) -> None:
    if on:
        os.environ["CV_INGAME_OUT_BET_CAP"] = "1"
    else:
        os.environ.pop("CV_INGAME_OUT_BET_CAP", None)


def _write_out_list(date: str, names) -> "str":
    """Write a live_out_<date>.json into the real cv_fix dir; return the path.
    Caller is responsible for cleanup (the tests use a sentinel date)."""
    root = PROJECT_DIR
    d = os.path.join(root, "data", "cache", "cv_fix")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"live_out_{date}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(names, f)
    return p


# Sentinel date that will not collide with a real operator file.
_TEST_DATE = "1990-01-02"


def teardown_function(_):
    _set_flag(False)
    p = os.path.join(PROJECT_DIR, "data", "cache", "cv_fix",
                     f"live_out_{_TEST_DATE}.json")
    if os.path.exists(p):
        os.remove(p)


# ── 1. Flag OFF -> disabled, empty set (byte-identical no-op) ──────────────
def test_flag_off_disabled_and_empty():
    _set_flag(False)
    oc = _oc()
    assert oc.cap_enabled() is False
    # Even with a populated file on disk, OFF returns an empty set.
    _write_out_list(_TEST_DATE, ["Jalen Brunson"])
    assert oc.load_out_set(_TEST_DATE) == frozenset()
    # cap is a pure pass-through when the set is empty.
    assert oc.cap_blended_value(frozenset(), "Jalen Brunson", 24.8, 22.0) == 24.8


# ── 2. Flag ON + empty file -> literal no-op ───────────────────────────────
def test_flag_on_empty_file_noop():
    _set_flag(True)
    oc = _oc()
    _write_out_list(_TEST_DATE, [])
    assert oc.load_out_set(_TEST_DATE) == frozenset()


# ── 3. Flag ON + absent file -> literal no-op ──────────────────────────────
def test_flag_on_absent_file_noop():
    _set_flag(True)
    oc = _oc()
    assert oc.load_out_set("1234-12-31") == frozenset()


# ── 4. Flag ON + name present -> that name is OUT ──────────────────────────
def test_flag_on_loads_names():
    _set_flag(True)
    oc = _oc()
    _write_out_list(_TEST_DATE, ["Jalen Brunson", "OG Anunoby"])
    out = oc.load_out_set(_TEST_DATE)
    assert "jalen brunson" in out
    assert "og anunoby" in out
    assert oc.is_out(out, "Jalen Brunson") is True
    assert oc.is_out(out, "Karl-Anthony Towns") is False


# ── 5. cap caps an OUT player DOWN to current (edge removed) ───────────────
def test_cap_lowers_out_player_to_current():
    _set_flag(True)
    oc = _oc()
    out = frozenset({"jalen brunson"})
    # stale-high blend 24.8 -> capped to current 22.0
    assert oc.cap_blended_value(out, "Jalen Brunson", 24.8, 22.0) == 22.0


# ── 6. cap leaves a NON-out player unchanged ───────────────────────────────
def test_cap_leaves_normal_player():
    _set_flag(True)
    oc = _oc()
    out = frozenset({"jalen brunson"})
    assert oc.cap_blended_value(out, "Karl-Anthony Towns", 24.8, 22.0) == 24.8


# ── 7. cap is a no-op when current is None (no fabrication) ─────────────────
def test_cap_noop_when_current_none():
    _set_flag(True)
    oc = _oc()
    out = frozenset({"jalen brunson"})
    assert oc.cap_blended_value(out, "Jalen Brunson", 24.8, None) == 24.8


# ── 8. name normalization matches the box path ─────────────────────────────
def test_name_normalization():
    _set_flag(True)
    oc = _oc()
    _write_out_list(_TEST_DATE, ["  Jalen Brunson  "])  # padded
    out = oc.load_out_set(_TEST_DATE)
    assert oc.is_out(out, "JALEN BRUNSON") is True
    assert oc.is_out(out, "jalen brunson") is True
    assert oc.is_out(out, "  Jalen Brunson ") is True


# ── 9. end-to-end: phantom OVER edge removed by the cap ─────────────────────
def _grade_side(proj: float, line: float) -> str:
    """Tiny stand-in for the regrade side selection: OVER when proj >= line."""
    return "OVER" if proj >= line else "UNDER"


def test_end_to_end_phantom_over_edge_removed():
    """Brunson left at 22 pts; live engine still projects 24.8; line 22.5.

    OFF (or empty set): blend 24.8 -> side OVER (phantom edge over 22.5).
    ON  + name OUT: blend capped to current 22.0 -> side UNDER 22.5
    (the projection now equals his frozen total; no OVER edge)."""
    _set_flag(True)
    oc = _oc()
    out = frozenset({"jalen brunson"})
    blended, current, line = 24.8, 22.0, 22.5

    # OFF / empty-set behavior: no cap -> OVER edge present.
    off_proj = oc.cap_blended_value(frozenset(), "Jalen Brunson", blended, current)
    assert off_proj == 24.8
    assert _grade_side(off_proj, line) == "OVER"

    # ON + OUT: capped to current -> OVER edge gone (now UNDER side at 22 < 22.5).
    on_proj = oc.cap_blended_value(out, "Jalen Brunson", blended, current)
    assert on_proj == 22.0
    assert _grade_side(on_proj, line) == "UNDER"
