"""Tests for snapshot_matchup_intel_enricher (CV_INGAME_MATCHUP_INTEL).

Covers: byte-identical OFF guarantee, pure corrector math + current-floor,
bias-table builder (min-games + game-level averaging), and ON-path mutation.
"""
import copy
import os

import pytest

from src.ingame import snapshot_matchup_intel_enricher as E


@pytest.fixture(autouse=True)
def _clear_flag():
    old = os.environ.get("CV_INGAME_MATCHUP_INTEL")
    os.environ.pop("CV_INGAME_MATCHUP_INTEL", None)
    yield
    if old is None:
        os.environ.pop("CV_INGAME_MATCHUP_INTEL", None)
    else:
        os.environ["CV_INGAME_MATCHUP_INTEL"] = old


def _rows():
    return [
        {"player_id": 100, "stat": "pts", "current": 6.0, "projected_final": 20.0},
        {"player_id": 100, "stat": "fg3m", "current": 1.0, "projected_final": 3.0},
        {"player_id": 100, "stat": "reb", "current": 2.0, "projected_final": 8.0},
        {"player_id": 200, "stat": "pts", "current": 4.0, "projected_final": 12.0},
    ]


def test_byte_identical_when_flag_off():
    rows = _rows()
    snap = {"game_id": "0022500001"}
    before = copy.deepcopy(rows)
    out = E.apply_matchup_intel(snap, rows, bias_table={100: {"pts": 5.0}})
    assert out is rows
    assert rows == before  # no mutation, no added keys


def test_correct_value_subtracts_shrunk_bias_and_floors():
    # positive bias -> projector over-projects -> lower the projection
    assert E.correct_value(20.0, 6.0, bias=5.0, shrink=0.4) == pytest.approx(18.0)
    # negative bias -> raise the projection
    assert E.correct_value(20.0, 6.0, bias=-5.0, shrink=0.4) == pytest.approx(22.0)
    # floor at current accumulation: a huge positive bias cannot drop below current
    assert E.correct_value(10.0, 8.0, bias=100.0, shrink=0.4) == 8.0


def test_on_path_corrects_only_scoring_stats_with_entries():
    os.environ["CV_INGAME_MATCHUP_INTEL"] = "1"
    rows = _rows()
    snap = {"game_id": "0022500001"}
    table = {100: {"pts": 5.0, "fg3m": 1.0}}  # pid 200 absent -> untouched
    out = E.apply_matchup_intel(snap, rows, bias_table=table, shrink=0.4)
    by = {(r["player_id"], r["stat"]): r for r in out}
    # pid 100 pts: 20 - 0.4*5 = 18
    assert by[(100, "pts")]["projected_final"] == pytest.approx(18.0)
    assert by[(100, "pts")]["scorer_bias_applied"] == pytest.approx(2.0)
    # pid 100 fg3m: 3 - 0.4*1 = 2.6
    assert by[(100, "fg3m")]["projected_final"] == pytest.approx(2.6)
    # reb is never touched (not a scoring stat)
    assert by[(100, "reb")]["projected_final"] == 8.0
    assert "scorer_bias_applied" not in by[(100, "reb")]
    # pid 200 has no table entry -> unchanged
    assert by[(200, "pts")]["projected_final"] == 12.0


def test_on_path_noop_when_table_empty():
    os.environ["CV_INGAME_MATCHUP_INTEL"] = "1"
    rows = _rows()
    before = copy.deepcopy(rows)
    out = E.apply_matchup_intel({"game_id": "x"}, rows, bias_table={})
    assert out == before


def test_build_bias_table_respects_min_games_and_game_averaging():
    # pid 1: 4 games (one with 2 rows that average) -> kept; pid 2: 2 games -> dropped
    rows = []
    for g in range(4):
        rows.append({"player_id": 1, "game_id": f"g{g}", "stat": "pts", "resid": 2.0})
    # add a second row in g0 so game-level averaging is exercised (still mean 2.0)
    rows.append({"player_id": 1, "game_id": "g0", "stat": "pts", "resid": 4.0})  # g0 mean=3
    for g in range(2):
        rows.append({"player_id": 2, "game_id": f"h{g}", "stat": "pts", "resid": 9.0})
    table = E.build_bias_table(rows, min_games=4)
    assert 2 not in table  # only 2 games -> below min
    # pid1 game means: g0=3, g1=2, g2=2, g3=2 -> mean = 2.25
    assert table[1]["pts"] == pytest.approx(2.25)


def test_load_bias_table_missing_file_returns_empty(tmp_path):
    assert E.load_bias_table(tmp_path / "nope.json") == {}
