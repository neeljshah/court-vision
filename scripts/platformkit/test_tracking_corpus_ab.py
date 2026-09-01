from scripts.platformkit.tracking_corpus_ab import baseline_diff, render_table


def test_diff_names_per_game_regressions():
    baseline = {"game_a": {"game_id": "game_a", "status": "completed", "passed": True,
                           "coverage_pct": 0.9, "oob_pct": 0.1, "jump_p95": 2.0,
                           "rows": 20, "ball_valid_pct": 0.8, "median_track_len": 10}}
    current = [{"game_id": "game_a", "status": "completed", "passed": False,
                "coverage_pct": 0.7, "oob_pct": 0.2, "jump_p95": 3.0,
                "rows": 10, "ball_valid_pct": 0.5, "median_track_len": 5}]

    lines = baseline_diff(baseline, current)

    assert "game_a WORSE:" in lines[1]
    assert "coverage_pct 0.900->0.700" in lines[1]
    assert "oob_pct 0.100->0.200" in lines[1]
    assert "verdict PASS->FAIL" in lines[1]


def test_table_reports_incomplete_and_capped_clips():
    table = render_table([{"game_id": "bad_clip", "status": "timeout", "rows": None,
                           "detail": "exceeded 20 seconds"}], requested=1, capped=2)

    assert "TIMEOUT: exceeded 20 seconds" in table
    assert "completed=0 incomplete=1 capped=2" in table
    assert "CAP: 2 corpus clips were not run" in table
