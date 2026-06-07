"""Tests for the routed-ensemble EVAL harness pure helpers.

The harness itself is a heavy walk-forward script (data + GPU); these tests
cover its leak-free, deterministic glue logic WITHOUT touching data:
  * the extended grid is the canonical-7 PLUS early + late edge buckets, and the
    canonical points are preserved unchanged (so cells stay comparable to
    eval_curve_v2.json);
  * the routed blend redistributes a missing component's weight;
  * the SBS-where-it-wins HARD switch picks a single head (no blend);
  * brier/logloss are sane.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

import scripts.ingame.eval_routed_ensemble as H  # noqa: E402


def test_extended_grid_superset_of_canonical():
    canon = set(H.CANONICAL_GRID_SEC)
    ext = set(H.EXTENDED_GRID_SEC)
    # canonical 7 preserved exactly
    assert canon.issubset(ext)
    # edges actually added (early < first canonical, late > last canonical)
    assert any(s < min(canon) for s in ext), "no early-Q1 bucket added"
    assert any(s > max(canon) for s in ext), "no late-Q4 bucket added"
    # labels cover every grid sec and order is ascending
    assert set(H.EXTENDED_GRID_LABELS) == ext
    secs = [H.LABEL_TO_SEC[b] for b in H.GRID_ORDER]
    assert secs == sorted(secs)


def test_blend_redistributes_missing_component():
    # at the first canonical centre pts routes to v2 (weight 1.0); if v2 missing,
    # weight must redistribute to the remaining present heads, never project 0.
    sec = H.CANONICAL_GRID_SEC[0]
    comp_full = {"snapshot": 10.0, "v2": 12.0, "pregame_l5": 9.0}
    comp_no_v2 = {"snapshot": 10.0, "pregame_l5": 9.0}
    b_full = H._blend_from_components("pts", sec, comp_full)
    b_missing = H._blend_from_components("pts", sec, comp_no_v2)
    assert b_full > 0
    # with v2 gone the blend falls back to a convex combo of the present heads
    assert min(9.0, 10.0) <= b_missing <= max(9.0, 10.0)


def test_blend_all_missing_falls_back_to_snapshot():
    comp = {"snapshot": 7.5}
    assert H._blend_from_components("reb", 720, comp) == 7.5


def test_hard_switch_picks_single_head_no_blend():
    # the hard switch returns EXACTLY one component's value (the table winner at
    # the nearest canonical centre), never an interpolation between two heads.
    comp = {"snapshot": 10.0, "v2": 12.0, "pregame_l5": 9.0}
    for sec in H.EXTENDED_GRID_SEC:
        v = H._hard_switch_value("pts", sec, comp)
        assert v in set(comp.values()), f"switch blended at {sec}: {v}"


def test_brier_logloss_sane():
    assert H._brier(1.0, 1) == 0.0
    assert H._brier(0.0, 1) == 1.0
    # perfect confident-correct -> ~0 logloss; confident-wrong -> large
    assert H._logloss(1.0, 1) < 1e-6
    assert H._logloss(0.0, 1) > 10.0


def test_patch_grid_reverts():
    import scripts.ingame.eval_second_by_second as ESBS
    before_sec = list(ESBS.GRID_SEC)
    before_lab = dict(ESBS.GRID_LABELS)
    old_sec, old_labels = H._patch_grid()
    try:
        assert list(ESBS.GRID_SEC) == list(H.EXTENDED_GRID_SEC)
    finally:
        ESBS.GRID_SEC, ESBS.GRID_LABELS = old_sec, old_labels
    assert list(ESBS.GRID_SEC) == before_sec
    assert dict(ESBS.GRID_LABELS) == before_lab
