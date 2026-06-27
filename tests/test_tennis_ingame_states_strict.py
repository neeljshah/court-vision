"""Per-file test: domains.tennis.ingest_ingame_states stricter live-only filters.

Locks the robustness re-check (2026-06-19): after the settled-row drop, two MORE
conservative cuts let us re-test the in-game verdict on genuinely-live states only.
PURE unit tests on build_snapshots (no I/O, no parquet, no network):
  * frac_max prunes near-terminal-by-elapsed rows and never adds rows.
  * drop_near_terminal prunes best-of-5 two-set-lead (2-0/0-2) states only; it is a
    no-op for best-of-3 (a two-set lead there is already terminal).
  * leak-free orientation + outcome unchanged by the new cuts.
calibration != edge. Run: python -m pytest tests/test_tennis_ingame_states_strict.py -q
"""
from __future__ import annotations

from domains.tennis.ingest_ingame_states import build_snapshots

# A best-of-5 match: winner (player1) wins 6-4 6-4 in the FIRST two sets is terminal in
# bo3 but NOT in bo5; to exercise the bo5 two-set-lead state we need a 3-set bo5 win.
# Sackmann score is WINNER-first. p1 wins: "6-4 6-4 6-4" (straight-sets bo5).
_BO5_STRAIGHT = [(6, 4), (6, 4), (6, 4)]   # p1 wins 3-0 (a 2-0 state exists pre-terminal)
# A best-of-3 straight-sets p1 win: only one pre-terminal boundary (1-0).
_BO3_STRAIGHT = [(6, 4), (6, 4)]


def _snaps(sets, winner=1, best_of=3, **kw):
    return build_snapshots("g1", sets, winner, 0.6, "Hard", best_of=best_of, **kw)


def test_default_drops_only_terminal_set():
    """Default: terminal set boundary dropped; live boundaries kept."""
    s = _snaps(_BO5_STRAIGHT, best_of=5)
    fracs = [r["frac_elapsed"] for r in s]
    assert all(f < 1.0 for f in fracs)           # no settled rows
    # bo5 straight 3-0: boundaries after set1 (1-0) and set2 (2-0); set3 terminal dropped
    set_scores = [r["set_score"] for r in s]
    assert "1-0" in set_scores and "2-0" in set_scores


def test_drop_near_terminal_removes_bo5_two_set_lead():
    """drop_near_terminal removes the 2-0 (one-set-from-match) state in bo5."""
    full = _snaps(_BO5_STRAIGHT, best_of=5)
    strict = _snaps(_BO5_STRAIGHT, best_of=5, drop_near_terminal=True)
    assert len(strict) < len(full)               # pruned, never added
    assert all(r["set_score"] != "2-0" for r in strict)
    assert all(r["set_score"] != "0-2" for r in strict)
    # the genuinely-live 1-0 state survives
    assert any(r["set_score"] == "1-0" for r in strict)


def test_drop_near_terminal_noop_for_bo3():
    """In best-of-3 a two-set lead is itself terminal -> the cut bites nothing."""
    full = _snaps(_BO3_STRAIGHT, best_of=3)
    strict = _snaps(_BO3_STRAIGHT, best_of=3, drop_near_terminal=True)
    assert [r["set_score"] for r in full] == [r["set_score"] for r in strict]


def test_frac_max_prunes_and_never_adds():
    """frac_max <= 1.0 can only remove rows; frac_max=1.0 is a strict no-op."""
    base = _snaps(_BO5_STRAIGHT, best_of=5)
    noop = _snaps(_BO5_STRAIGHT, best_of=5, frac_max=1.0)
    assert len(noop) == len(base)
    tight = _snaps(_BO5_STRAIGHT, best_of=5, frac_max=0.5)
    assert len(tight) <= len(base)
    assert all(r["frac_elapsed"] <= 0.5 for r in tight)


def test_strict_filters_preserve_leak_free_orientation():
    """Cuts must not change outcome/orientation: p2 wins -> outcome 0, state_diff signs hold.

    p2 wins 3-0 (Sackmann winner-first: '6-4 6-4 6-4' but winner==2). After the p1-
    orientation swap, p1 is the trailer so each kept state's state_diff is negative.
    """
    s = _snaps(_BO5_STRAIGHT, winner=2, best_of=5, drop_near_terminal=True, frac_max=0.95)
    assert all(r["outcome"] == 0 for r in s)             # p1 lost
    assert all(r["state_diff"] < 0 for r in s)           # p1 trailing throughout
    assert all(r["set_score"] not in ("2-0", "0-2") for r in s)
