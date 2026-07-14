"""Tests for scripts.platformkit.omni.k_synergy_era_control (era-control test
for the 18 held with_without_teammate / star_sits synergy cells).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_synergy_era_control.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_synergy_era_control as kec


def _row(team, game_id, date, season, player_id, pts, minutes=30.0):
    return {"team": team, "game_id": game_id, "date": date, "season": season,
            "player_id": player_id, "player_name": f"P{player_id}", "min": minutes, "pts": pts}


def _seed_held_claim(base_dir, condition: str, entity_ids: list[int], parent_delta: float) -> str:
    scope = {"sport": "nba", "entity_type": "player_pair" if condition == "with_without_teammate" else "player",
              "entity_ids": entity_ids, "context": condition}
    claim = {
        "statement": f"NBA {condition} {entity_ids} :: stage-B re-mine", "type": "effect", "scope": scope,
        "topic": f"synergy.{condition}", "lifecycle": "replicated" if condition == "with_without_teammate" else "family_pass",
        "effect": {"verdict": "TESTED", "delta": parent_delta},
        "provenance": {"created_by_lane": "k_stage_b"},
    }
    return cl.add_claim(claim, base_dir=base_dir)


# -- short-vs-long absence run classification -------------------------------

def test_short_absent_run_bounded_both_sides_is_kept():
    sched = [f"g{i}" for i in range(10)]
    present = set(sched) - {"g4", "g5", "g6"}  # 3-game absent run, bounded
    short = kec._short_absent_games(sched, present, max_gap=15)
    assert short == {"g4", "g5", "g6"}


def test_long_absent_run_excluded():
    sched = [f"g{i}" for i in range(30)]
    present = set(sched) - {f"g{i}" for i in range(10, 25)}  # 15-game gap -> len 15, but test >15
    short = kec._short_absent_games(sched, present, max_gap=10)
    assert short == set()  # run length 15 > max_gap 10 -> excluded


def test_boundary_touching_run_never_short():
    sched = [f"g{i}" for i in range(10)]
    present = set(sched) - {"g0", "g1"}  # absent run touches the start boundary
    short = kec._short_absent_games(sched, present, max_gap=15)
    assert short == set()


# -- contiguous-window derivation on synthetic pair data --------------------

def _synergy_pair_frame(era_shift: bool) -> pd.DataFrame:
    """Players 1 & 2 share ATL roster across 40 games. Player 2 sits for a
    short 5-game stretch (rest/injury, bounded both sides) -- player 1 scores
    higher in that window regardless of era_shift. If era_shift, player 1 ALSO
    gets an unrelated long-run scoring bump for games 30-39 where player 2 has
    permanently left the roster (a trade/new-era, not synergy) -- the era
    control must exclude those games from "without"."""
    rows = []
    dates = pd.date_range("2023-11-01", periods=40, freq="1D")
    for i, d in enumerate(dates):
        short_sit = 15 <= i < 20  # bounded 5-game absence
        era_gone = era_shift and i >= 30  # unbounded (never returns) absence
        p2_present = not (short_sit or era_gone)
        p1_pts = 20.0
        if short_sit:
            p1_pts = 26.0  # real short-absence bump
        if era_gone:
            p1_pts = 30.0  # era-driven scoring jump, NOT synergy
        rows.append(_row("ATL", f"g{i}", d, "2023-24", 1, p1_pts))
        if p2_present:
            rows.append(_row("ATL", f"g{i}", d, "2023-24", 2, 10.0))
    return pd.DataFrame(rows)


def test_era_control_pair_isolates_short_window_effect():
    df = _synergy_pair_frame(era_shift=True)
    res = kec.era_control_pair(df, 1, 2)
    assert res is not None
    # without-side is ONLY the 5 short-sit games (26 pts), never the 10 era-gone games (30 pts)
    assert res["n_b"] == 5
    assert abs(res["delta"] - (-6.0)) < 1e-6  # with(20) - without(26)


def test_era_control_pair_not_testable_when_never_shared_roster():
    df = _synergy_pair_frame(era_shift=True)
    assert kec.era_control_pair(df, 1, 99) is None  # player 99 never on ATL roster


# -- boundary-only absence -> NOT_TESTABLE (no short window at all) --------

def test_era_control_pair_not_testable_when_only_era_boundary_absence():
    """A pair whose only absence is an unbounded (boundary-touching) run --
    e.g. b was traded away and never returns in this store -- has no short
    window at all; the effect is inseparable from era, honestly NOT_TESTABLE."""
    rows = []
    dates = pd.date_range("2023-11-01", periods=40, freq="1D")
    for i, d in enumerate(dates):
        era_gone = i >= 20  # unbounded absence from g20 onward (trade), no short window at all
        rows.append(_row("ATL", f"g{i}", d, "2023-24", 10, 15.0))
        if not era_gone:
            rows.append(_row("ATL", f"g{i}", d, "2023-24", 11, 10.0))
    df = pd.DataFrame(rows)
    assert kec.era_control_pair(df, 10, 11) is None


# -- confound-explained path -------------------------------------------------

def test_confound_explained_path_rejects_and_links_meta(tmp_path):
    """A held claim seeded with a large parent_delta (as if stage-B's
    un-controlled mining found a spurious effect) must die once era control
    shows no real short-window effect -- and the held claim flips to rejected
    linking the meta confound claim, never silently surviving."""
    rows = []
    dates = pd.date_range("2023-11-01", periods=40, freq="1D")
    pattern = [20.0, 22.0, 18.0, 21.0, 19.0]
    for i, d in enumerate(dates):
        short_sit = 15 <= i < 20  # bounded 5-game absence, but NO real scoring difference
        p2_present = not short_sit
        rows.append(_row("ATL", f"g{i}", d, "2023-24", 30, pattern[i % 5]))
        if p2_present:
            rows.append(_row("ATL", f"g{i}", d, "2023-24", 31, 10.0))
    df = pd.DataFrame(rows)
    claim_id = _seed_held_claim(tmp_path, "with_without_teammate", [30, 31], parent_delta=5.0)
    out = kec.run_era_control(base_dir=tmp_path, source=df)
    assert out["confound_explained"] == 1
    assert out["reserve_accepted"] == 0
    final = cl.query(sport="nba", base_dir=tmp_path)
    row = final[final["claim_id"] == claim_id].iloc[0]
    assert row["lifecycle"] == "rejected"


# -- idempotent rerun ---------------------------------------------------------

def test_run_era_control_idempotent(tmp_path):
    df = _synergy_pair_frame(era_shift=False)  # all dates 2023-11, well inside discovery
    claim_id = _seed_held_claim(tmp_path, "with_without_teammate", [1, 2], parent_delta=6.0)
    out1 = kec.run_era_control(base_dir=tmp_path, source=df)
    out2 = kec.run_era_control(base_dir=tmp_path, source=df)
    assert out1["held_total"] == 1
    # second run finds zero held cells left in {replicated, family_pass} (lifecycle already flipped)
    assert out2["held_total"] == 0
    final = cl.query(sport="nba", base_dir=tmp_path)
    assert (final.loc[final["claim_id"] == claim_id, "lifecycle"] != "replicated").all()
