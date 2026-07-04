"""Per-file test for domains.basketball_nba.states_corpus_ondisk_runner.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_corpus_ondisk_runner.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.states_corpus_ondisk_runner import (
    _to_linescores_abbr,
    build_games_event_crosswalk,
    run_gate_with_crosswalk,
    write_gate,
)


def test_to_linescores_abbr_maps_known_mismatches():
    assert _to_linescores_abbr("GSW") == "GS"
    assert _to_linescores_abbr("NOP") == "NO"
    assert _to_linescores_abbr("NYK") == "NY"
    assert _to_linescores_abbr("SAS") == "SA"
    assert _to_linescores_abbr("UTA") == "UTAH"
    assert _to_linescores_abbr("WAS") == "WSH"


def test_to_linescores_abbr_passthrough_for_matching_codes():
    assert _to_linescores_abbr("BOS") == "BOS"
    assert _to_linescores_abbr("LAL") == "LAL"


def _games_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"game_id": "g1", "date": "2025-10-21", "season": "2025-26",
         "home_team": "GSW", "away_team": "LAL", "home_win": 1.0},
        {"game_id": "g2", "date": "2025-10-22", "season": "2025-26",
         "home_team": "BOS", "away_team": "MIA", "home_win": 0.0},
        {"game_id": "g3", "date": "2025-10-23", "season": "2025-26",
         "home_team": "ZZZ", "away_team": "YYY", "home_win": 1.0},  # unmatchable
    ])


def _linescores_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "e1", "date": "2025-10-21", "home_abbr": "GS", "away_abbr": "LAL",
         "home_q1": 25.0, "home_q2": 25.0, "home_q3": 25.0, "home_q4": 25.0,
         "away_q1": 20.0, "away_q2": 20.0, "away_q3": 20.0, "away_q4": 20.0},
        {"event_id": "e2", "date": "2025-10-22", "home_abbr": "BOS", "away_abbr": "MIA",
         "home_q1": 20.0, "home_q2": 20.0, "home_q3": 20.0, "home_q4": 20.0,
         "away_q1": 25.0, "away_q2": 25.0, "away_q3": 25.0, "away_q4": 25.0},
    ])


def test_build_games_event_crosswalk_matches_and_normalizes():
    cw = build_games_event_crosswalk(_games_df(), _linescores_df())
    assert len(cw) == 2  # g3 dropped (no linescores match), never fabricated
    assert set(cw["event_id"]) == {"e1", "e2"}


def _pbp_df() -> pd.DataFrame:
    traj = {2760.0: 1.0, 2640.0: -1.0, 2520.0: -2.0, 2400.0: 0.0, 2280.0: -1.0,
            2160.0: -3.0, 2040.0: -1.0, 1920.0: -2.0, 1800.0: -4.0, 1680.0: -1.0,
            1560.0: -5.0, 1440.0: -6.0, 1320.0: -12.0, 1200.0: -6.0, 1080.0: -6.0,
            960.0: -6.0, 840.0: 0.0, 720.0: -4.0, 600.0: -5.0}
    rows = []
    for eid in ("e1", "e2"):
        rows += [{"event_id": eid, "seconds_remaining": sr, "home_margin": m}
                  for sr, m in traj.items()]
    return pd.DataFrame(rows)


def test_run_gate_with_crosswalk_insufficient_below_floor():
    cw = build_games_event_crosswalk(_games_df(), _linescores_df())
    result = run_gate_with_crosswalk(cw, linescores_df=_linescores_df(), pbp_states_df=_pbp_df())
    assert result["edge_claimed"] is False
    assert result["provenance"] == "ondisk_espn_pbp_no_cdn"
    assert result["features_tested"] == ["run_last_3min"]
    assert result["features_unavailable"] == ["in_bonus"]
    assert result["n_rows_total"] == 6  # 2 games x 3 checkpoints
    # Tiny fixture n is below _MIN_N_PER_HALF -- every cell must be INSUFFICIENT,
    # never a spurious SHIP/REJECT on 2 games.
    for feature_results in result["crossfit_results"].values():
        for cell in feature_results:
            assert cell["verdict"] == "INSUFFICIENT"
    assert result["overall_verdict"] == "NO_FEATURE_SUPPORTED_V2__HONEST_NULL"


def test_write_gate_roundtrip(tmp_path):
    cw = build_games_event_crosswalk(_games_df(), _linescores_df())
    result = run_gate_with_crosswalk(cw, linescores_df=_linescores_df(), pbp_states_df=_pbp_df())
    out = write_gate(result, out_path=tmp_path / "out.json")
    assert out.exists()
    import json
    reloaded = json.loads(out.read_text())
    assert reloaded["overall_verdict"] == result["overall_verdict"]
