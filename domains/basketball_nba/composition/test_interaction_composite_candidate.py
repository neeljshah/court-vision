"""Per-file test: interaction cross-term z(a)*z(b) composition math, as-of
no-leak, missing-attr-pair -> 0 (not a crash), and build_frame wiring
(composite_diff_interact matches an independently-computed diff of
load_player_interaction_composite). Synthetic fixtures only; no disk
corpora touched.
Run: python -m pytest domains/basketball_nba/composition/test_interaction_composite_candidate.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.composition import interaction_composite_candidate as m


def _profiles(tmp_path):
    """window season_2024_25: 3 players, halfcourt_efg and late_clock_efg
    co-move (1,-1,0) -> nonzero, symmetric interaction composite for the two
    extremes, zero for the mean player. zone_efg_rim is absent from this
    fixture entirely (exercises the missing-attr-pair -> 0 path). A
    season_2025_26 spike on player 100 must NOT leak into the 2024-25 query."""
    rows = []
    for pid, hc, lc in [(100, 1.0, 1.0), (101, -1.0, -1.0), (102, 0.0, 0.0)]:
        rows.append({"entity_id": pid, "window": "season_2024_25", "attribute": "halfcourt_efg", "raw_value": hc})
        rows.append({"entity_id": pid, "window": "season_2024_25", "attribute": "late_clock_efg", "raw_value": lc})
    rows.append({"entity_id": 100, "window": "season_2025_26", "attribute": "halfcourt_efg", "raw_value": 999.0})
    rows.append({"entity_id": 100, "window": "season_2025_26", "attribute": "late_clock_efg", "raw_value": 999.0})
    p = tmp_path / "players.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


def test_interaction_composite_math_and_asof_no_leak(tmp_path):
    pp = _profiles(tmp_path)
    icomp = m.load_player_interaction_composite("season_2024_25", pp)
    # halfcourt_efg and late_clock_efg co-move -> product is positive for
    # BOTH extremes (signs cancel), symmetric magnitude, zero at the mean.
    assert icomp[100] > 0 and icomp[101] > 0
    assert abs(icomp[100] - icomp[101]) < 1e-9
    assert abs(icomp.get(102, 0.0)) < 1e-9
    # as-of: the 2025-26 spike (999) must not leak into the 2024-25 query.
    assert icomp[100] < 10.0


def test_missing_attr_pair_contributes_zero(tmp_path):
    rows = [{"entity_id": 1, "window": "w", "attribute": "halfcourt_efg", "raw_value": 5.0},
            {"entity_id": 2, "window": "w", "attribute": "halfcourt_efg", "raw_value": -5.0}]
    p = tmp_path / "only_a.parquet"
    pd.DataFrame(rows).to_parquet(p)
    icomp = m.load_player_interaction_composite("w", p)
    assert all(v == 0.0 for v in icomp.values())


def test_pairs_are_the_replicated_ones():
    named = {(a, b) for a, b, _ in m.INTERACTION_PAIRS}
    assert ("halfcourt_efg", "late_clock_efg") in named
    assert ("halfcourt_efg", "zone_efg_rim") in named
    assert len(m.INTERACTION_PAIRS) == 2


def test_build_frame_wires_composite_diff_interact(tmp_path, monkeypatch):
    pp = _profiles(tmp_path)
    seg = pd.DataFrame([{
        "game_id": "G1", "team_id_a": 1, "team_id_b": 2,
        "lineup_key_a": "100", "lineup_key_b": "101",
        "overlap_s": 60.0, "pts_a": 4, "pts_b": 2,
        "abs_start": 0.0, "game_len": 2880.0,
        "score_margin_start": 0.0, "time_remaining": 2880.0,
    }])
    monkeypatch.setattr(m, "build_segments_exact", lambda *a, **k: seg)

    teams_rows = []
    for tid, nr in [(1, 0.0), (2, 0.0)]:
        for attr in ["net_rating_home", "net_rating_away"]:
            teams_rows.append({"entity_id": tid, "window": "season_2024_25", "attribute": attr, "raw_value": nr})
    tp = tmp_path / "teams.parquet"
    pd.DataFrame(teams_rows).to_parquet(tp)

    out = m.build_frame("2025_26", stints_df=pd.DataFrame(), player_path=pp, team_path=tp)
    icomp = m.load_player_interaction_composite("season_2024_25", pp)
    expected = icomp.get(100, 0.0) - icomp.get(101, 0.0)
    assert out is not None and len(out) == 1
    assert abs(out.iloc[0]["composite_diff_interact"] - expected) < 1e-9
    assert out.iloc[0]["strength_diff"] == 0.0


def test_excluded_season_returns_none():
    assert m.build_frame("2023_24") is None
