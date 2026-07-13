"""Per-file test for interaction_factory.builders_soccer_setpiece. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_soccer_setpiece.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.interaction_factory import builders_soccer_setpiece as b


def test_norm_strips_accents_and_case():
    assert b._norm("Atlético Madrid") == "atletico madrid"
    assert b._norm("Málaga") == "malaga"


def test_fd_key_applies_alias_after_normalizing():
    assert b._fd_key("Manchester United") == "man united"
    assert b._fd_key("AFC Bournemouth") == "bournemouth"
    # accent-only difference resolved by _norm alone, no alias entry needed
    assert b._fd_key("Sporting Gijón") == "sp gijon"
    # pass-through (identical both sides after normalizing)
    assert b._fd_key("Arsenal") == "arsenal"


def _shot(team, xg, pattern):
    return {"type": {"name": "Shot"}, "team": {"name": team},
            "shot": {"statsbomb_xg": xg}, "play_pattern": {"name": pattern}}


def test_match_xg_breakdown_buckets_corner_and_freekick_into_setpiece():
    events = [
        _shot("Home", 0.10, "From Corner"),
        _shot("Home", 0.20, "From Free Kick"),
        _shot("Home", 0.30, "Regular Play"),
        _shot("Away", 0.05, "From Throw In"),
        {"type": {"name": "Pass"}, "team": {"name": "Home"}},  # non-shot, ignored
    ]
    xg = b._match_xg_breakdown(events)
    assert xg["Home"]["total"] == pytest.approx(0.60)
    assert xg["Home"]["corner"] == pytest.approx(0.10)
    assert xg["Home"]["setpiece"] == pytest.approx(0.30)  # corner + free kick
    assert xg["Away"]["total"] == pytest.approx(0.05)
    assert xg["Away"]["setpiece"] == pytest.approx(0.0)  # throw-in is open play


def _synthetic_spine():
    # TeamA plays home in match 1, away in match 3 -- state must carry across slots.
    return pd.DataFrame({
        "event_id": ["m1", "m2", "m3"],
        "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
        "home_team": ["teama", "teamb", "teamc"],
        "away_team": ["teamb", "teamc", "teama"],
        "home_setpiece_share": [0.4, 0.1, 0.9],
        "away_setpiece_share": [0.2, 0.3, 0.5],
        "home_corner_xg": [0.1, 0.2, 0.3],
        "away_corner_xg": [0.05, 0.15, 0.25],
        "home_openplay_xg": [1.0, 1.1, 1.2],
        "away_openplay_xg": [0.9, 0.8, 0.7],
    })


def test_build_soccer_setpiece_asof_debut_rows_are_nan_never_leaked():
    asof = b.build_soccer_setpiece_asof(_synthetic_spine())
    assert list(asof["event_id"]) == ["m1", "m2", "m3"]
    # m1: both teama (home) and teamb (away) are debuts -> diff is NaN, not m1's own values.
    assert asof.loc[0, "setpiece_xg_share_asof"] != asof.loc[0, "setpiece_xg_share_asof"]  # NaN
    # m3: home=teamc (1 prior appearance, as AWAY in m2) vs away=teama (1 prior,
    # as HOME in m1) -- trailing values must equal each team's OWN prior
    # observation (never m3's own), diffed home-minus-away.
    row = asof.iloc[2]
    assert row["setpiece_xg_share_asof"] == pytest.approx(0.3 - 0.4)  # teamc's m2 away_share - teama's m1 home_share
    assert row["corner_xg_asof"] == pytest.approx(0.15 - 0.1)
    assert row["openplay_xg_asof"] == pytest.approx(0.8 - 1.0)


def test_build_soccer_setpiece_asof_empty_spine_returns_empty_typed_frame():
    out = b.build_soccer_setpiece_asof(pd.DataFrame())
    assert list(out.columns) == ["event_id", "setpiece_xg_share_asof", "corner_xg_asof", "openplay_xg_asof"]
    assert len(out) == 0


def test_build_soccer_setpiece_match_frame_derives_home_win_and_nans_unbridged():
    matches = pd.DataFrame({"event_id": ["m1", "m2", "m3", "unbridged"],
                             "div": ["E0"] * 4, "fthg": [2, 0, 1, 1], "ftag": [1, 3, 1, 1]})
    spine = _synthetic_spine()
    out = b.build_soccer_setpiece_match_frame(matches, spine, ["setpiece_xg_share_asof", "corner_xg_asof"])
    assert list(out["y"]) == [1.0, 0.0, 0.0, 0.0]
    assert "asof__setpiece_xg_share_asof" in out.columns
    # the match absent from the bridge (spine) is an honest NaN, never fabricated.
    unb = out.loc[out["event_id"] == "unbridged", "asof__setpiece_xg_share_asof"].iloc[0]
    assert unb != unb  # NaN


def test_spine_bridges_real_statsbomb_cache_to_matches_parquet():
    """Integration proof against the REAL on-disk caches (bounded cap so the
    per-file test stays fast) -- proves the team-name join key + (date, div)
    bridge produces actual rows, not just a plumbing no-op."""
    if not (b._MATCH_META_FULL.exists() and b._SOCCER_MATCHES.exists() and b._EVENTS_DIR.exists()):
        pytest.skip("statsbomb cache / matches.parquet not present on this checkout")
    match_meta = pd.read_parquet(b._MATCH_META_FULL)
    matches = pd.read_parquet(b._SOCCER_MATCHES,
                               columns=["event_id", "date", "div", "season", "home_team", "away_team", "fthg", "ftag"])
    spine = b.build_soccer_setpiece_spine(match_meta, matches[matches["season"] == 2015], b._EVENTS_DIR, cap=25)
    assert len(spine) > 0, "0 bridged matches out of a 25-row cap -- bridge broken, not just under-covered"
    assert spine["event_id"].is_unique
    asof = b.build_soccer_setpiece_asof(spine)  # walk_forward_asof's own assert_no_future_leak must not raise
    assert set(m for m, _h, _a in b._METRICS) <= set(asof.columns)
