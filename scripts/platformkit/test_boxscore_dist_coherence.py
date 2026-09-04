from math import isclose

from scripts.platformkit.boxscore_dist_coherence import (
    check_team_coherence,
    summarize_stat_deviations,
)


def test_constructed_thirty_game_q50_coherence_inventory() -> None:
    team_games = []
    for game_number in range(1, 31):
        minutes = 49.0 if game_number in (1, 2) else 48.0
        target_pts = None if game_number == 30 else 100.0
        team_games.append(
            {
                "game_id": f"construct-{game_number:02d}",
                "team_id": "TST",
                "overtime_periods": 1 if game_number == 2 else 0,
                "players": [
                    {"player_id": f"p{player}", "q50": {
                        "minutes": minutes, "pts": 20.0, "reb": 10.0, "ast": 5.0,
                    }}
                    for player in range(1, 6)
                ],
                "team_total_targets": {
                    "pts": {"value": target_pts, "source_file": "fixture", "source_field": "pts"},
                    "reb": {"value": 55.0, "source_file": "fixture", "source_field": "reb"},
                    "ast": {"value": 20.0, "source_file": "fixture", "source_field": "ast"},
                },
            }
        )

    results = check_team_coherence(team_games)
    summary = summarize_stat_deviations(results)

    assert len(results) == 30
    assert results[0]["minutes_flagged"] is True
    assert results[0]["minutes_excess"] == 5.0
    assert results[1]["minutes_flagged"] is False
    assert results[1]["minutes_budget"] == 245.0
    assert results[-1]["stat_sums"]["pts"]["status"] == "EXCLUDED_MISSING_TARGET"
    assert summary["pts"] == {
        "n": 29, "excluded_missing_target": 1, "excluded_zero_target": 0, "total": 30,
        "mean_abs_pct_deviation": 0.0,
    }
    assert isclose(summary["reb"]["mean_abs_pct_deviation"], 5.0 / 55.0)
    assert summary["ast"]["mean_abs_pct_deviation"] == 0.25
