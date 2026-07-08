"""Fixture-based section tests -- no real corpus dependency. Each test builds a
tiny synthetic DataFrame/jsonl-row list and monkeypatches the matching
sources.* loader, so these run fast and never depend on data/ being present.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.gamebrief import honesty, sections_intel, sections_team, team_ids


def test_team_ids_roundtrip():
    assert team_ids.team_id_for("OKC") == 1610612760
    assert team_ids.TEAM_ID_TO_ABBR[1610612760] == "OKC"
    assert team_ids.fullname_for("DEN") == "Denver Nuggets"
    assert team_ids.is_known_abbr("den")
    assert not team_ids.is_known_abbr("ZZZ")


def test_honesty_label_single_verdict(monkeypatch):
    monkeypatch.setattr(honesty, "_by_family", lambda: {"nba_gravity_proxy_claims": ["UNTESTABLE"]})
    assert "UNTESTABLE" in honesty.label_for_family("nba_gravity_proxy_claims")
    assert honesty.label_for_family("no_such_family") == "NOT IN CLAIM LEDGER (untested by the gate)"


def test_honesty_label_mixed_verdicts(monkeypatch):
    monkeypatch.setattr(honesty, "_by_family", lambda: {"nba_shooting_claims": ["NULL", "NULL", "MATTERS_PROVISIONAL"]})
    label = honesty.label_for_family("nba_shooting_claims")
    assert "MIXED" in label and "NULL=2" in label and "MATTERS_PROVISIONAL=1" in label


def test_rest_and_schedule_found_and_missing():
    games_df = pd.DataFrame({
        "date": [pd.Timestamp("2026-02-27")], "home_team": ["OKC"], "away_team": ["DEN"],
        "rest_days_home": [2.0], "rest_days_away": [1.0], "home_b2b": [False], "away_b2b": [True],
    })
    ok = sections_team.rest_and_schedule(games_df, "OKC", "DEN", "2026-02-27")
    assert ok["status"] == "ok" and ok["rest_days_home"] == 2.0 and ok["away_b2b"] is True

    missing = sections_team.rest_and_schedule(games_df, "OKC", "DEN", "2026-03-01")
    assert missing["status"] == "not_available"

    assert sections_team.rest_and_schedule(None, "OKC", "DEN", "2026-02-27")["status"] == "not_available"


def test_top3_fga_is_leak_free():
    box = pd.DataFrame({
        "team": ["OKC", "OKC", "OKC", "OKC"],
        "date": ["2026-02-20", "2026-02-22", "2026-02-24", "2026-02-27"],
        "player_id": [1, 1, 2, 1],
        "player_name": ["A", "A", "B", "A"],
        "fga": [10, 10, 30, 999],  # the 999-FGA game is ON the target date -- must be excluded
    })
    top3 = sections_team.top3_fga(box, "OKC", "2026-02-27")
    names = {p["player_name"]: p["fga_season_to_date"] for p in top3}
    assert names["A"] == 20  # only the two prior games count
    assert names["B"] == 30


def test_injury_section_out_player_gets_usage_note(monkeypatch):
    rows = [{
        "team": "Oklahoma City Thunder", "player_name": "A", "status": "OUT",
        "detail": "ankle", "report_date": "2026-02-26",
    }]
    monkeypatch.setattr(sections_team.sources, "injury_rows", lambda: rows)
    ur = pd.DataFrame({
        "team_id": [1610612760, 1610612760], "player_id": [2, 3], "teammate_id": [1, 1],
        "fga_share_with": [0.10, 0.05], "fga_share_without": [0.25, 0.06],
        "efg_with": [0.50, 0.50], "efg_without": [0.55, 0.51],
        "player_name": ["B", "C"], "teammate_name": ["A", "A"],
    })
    monkeypatch.setattr(sections_team.sources, "usage_redistribution", lambda: ur)
    top3 = [{"player_id": 1, "player_name": "A", "fga_season_to_date": 100.0}]
    out = sections_team.injury_section("OKC", "2026-02-27", top3)
    assert out["status"] == "ok"
    rep = out["reports"][0]
    assert rep["is_top3_fga"] is True
    assert "B" in rep["usage_redistribution_note"]  # bigger share_gain (0.15 vs 0.01) sorts first


def test_injury_section_future_report_not_used(monkeypatch):
    rows = [{"team": "Oklahoma City Thunder", "player_name": "A", "status": "OUT",
             "detail": "x", "report_date": "2026-07-07"}]
    monkeypatch.setattr(sections_team.sources, "injury_rows", lambda: rows)
    out = sections_team.injury_section("OKC", "2026-02-27", [])
    assert out["status"] == "not_available"


def test_gravity_leaders(monkeypatch):
    df = pd.DataFrame({
        "team_id": [1610612760, 1610612760, 1610612743],
        "player_name": ["A", "B", "C"], "gravity_proxy": [0.05, 0.10, 0.20],
        "teammate_efg_on": [0.55, 0.60, 0.60], "teammate_efg_off": [0.50, 0.50, 0.40],
    })
    monkeypatch.setattr(sections_intel.sources, "gravity_proxy", lambda: df)
    out = sections_intel.gravity_leaders(1610612760, top_n=2)
    assert out["status"] == "ok"
    assert out["leaders"][0]["player_name"] == "B"  # highest gravity_proxy first

    assert sections_intel.gravity_leaders(None)["status"] == "not_available"


def test_concession_matchup_rank_and_diet_gap(monkeypatch):
    df = pd.DataFrame({
        "defense_team_id": [1610612760, 1610612743],
        "overall_efg_allowed": [0.50, 0.55], "rim_efg_allowed": [0.55, 0.60],
        "rim_share_allowed": [0.25, 0.30], "above_break_3_efg_allowed": [0.35, 0.36],
    })
    monkeypatch.setattr(sections_intel.sources, "concession", lambda: df)
    monkeypatch.setattr(sections_intel.sources, "shot_diet", lambda: None)
    out = sections_intel.concession_matchup("OKC", "DEN", 1610612760, 1610612743, "2026-02-27")
    assert out["status"] == "ok"
    assert out["sides"]["DEN"]["overall_efg_allowed_rank_worst_to_best"] == 1  # highest allowed = worst
    assert out["shot_diet"]["OKC"]["status"] == "not_available"  # no shot_diet parquet -> honest gap


def test_concession_matchup_diet_ranks_and_asof_leak_free(monkeypatch):
    conc = pd.DataFrame({
        "defense_team_id": [1610612760, 1610612743],
        "overall_efg_allowed": [0.50, 0.55], "rim_efg_allowed": [0.55, 0.60],
        "rim_share_allowed": [0.25, 0.30], "above_break_3_efg_allowed": [0.35, 0.36],
    })
    monkeypatch.setattr(sections_intel.sources, "concession", lambda: conc)

    zone_cols = {f"{z}_fga": 0 for z in ["rim", "paint", "mid", "corner3", "above_break_3"]}
    diet = pd.DataFrame([
        # OKC (1610612760): heavy rim diet, 3 prior games -- clears the floor.
        dict(zone_cols, game_id="g1", date=pd.Timestamp("2026-02-20"), team_id=1610612760,
             total_fga=40, rim_fga=20, corner3_fga=5, above_break_3_fga=10),
        dict(zone_cols, game_id="g2", date=pd.Timestamp("2026-02-22"), team_id=1610612760,
             total_fga=40, rim_fga=20, corner3_fga=5, above_break_3_fga=10),
        dict(zone_cols, game_id="g3", date=pd.Timestamp("2026-02-24"), team_id=1610612760,
             total_fga=40, rim_fga=20, corner3_fga=5, above_break_3_fga=10),
        # On the target date itself -- must be EXCLUDED from OKC's as-of diet.
        dict(zone_cols, game_id="g_target", date=pd.Timestamp("2026-02-27"), team_id=1610612760,
             total_fga=40, rim_fga=0, corner3_fga=0, above_break_3_fga=0),
        # DEN (1610612743): only 1 prior game -- below the 3-game honesty floor.
        dict(zone_cols, game_id="g4", date=pd.Timestamp("2026-02-20"), team_id=1610612743,
             total_fga=40, rim_fga=10, corner3_fga=10, above_break_3_fga=10),
    ])
    monkeypatch.setattr(sections_intel.sources, "shot_diet", lambda: diet)

    out = sections_intel.concession_matchup("OKC", "DEN", 1610612760, 1610612743, "2026-02-27")
    okc = out["shot_diet"]["OKC"]
    assert okc["status"] == "ok"
    assert okc["n_games"] == 3  # target-date game excluded (leak-free)
    assert abs(okc["rim_share"] - 0.5) < 1e-9  # 20/40, not diluted by the excluded 0-rim game
    assert okc["rim_share_rank_most_to_least"] == 1  # OKC's rim share (0.5) beats DEN's (0.25)
    assert okc["opp_rim_efg_allowed_rank_worst_to_best"] == out["sides"]["DEN"]["rim_efg_allowed_rank_worst_to_best"]
    assert out["shot_diet"]["DEN"]["status"] == "not_available"  # below the 3-game floor


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
