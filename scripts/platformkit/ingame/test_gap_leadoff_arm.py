from scripts.platformkit.ingame.gap_leadoff_arm import attach_conditioner, fit_table


def _half(game_id, season, resolution, runs):
    return [
        {"game_id": game_id, "season": season, "asof_idx": 0, "half_inning_label": "top1",
         "runners": 0, "outs": 0, "state_diff": 0},
        {"game_id": game_id, "season": season, "asof_idx": 1, "half_inning_label": "top1",
         "runners": resolution[0], "outs": resolution[1], "state_diff": 0},
        {"game_id": game_id, "season": season, "asof_idx": 2, "half_inning_label": "bottom1",
         "runners": 0, "outs": 0, "state_diff": -runs},
    ]


def test_table_is_monotonic_for_synthetic_leadoff_states():
    rows = _half("on", 2022, (1, 0), 3) + _half("out", 2022, (0, 1), 0)
    table = fit_table(rows)
    assert table["on_base"] > table["out"]
    assert table["monotonic"] is True


def test_fit_table_excludes_rows_after_cutoff():
    rows = _half("old", 2022, (1, 0), 3) + _half("new", 2024, (1, 0), 0)
    table = fit_table(rows, cutoff_season=2023)
    assert table["counts"]["on_base"] == 1
    assert table["hits"]["on_base"] == 1
    assert table["source_seasons"] == [2022]


def test_conditioner_decays_at_half_inning_end():
    table = {"on_base": 0.12, "out": 0.03}
    condition = {"game_id": "game", "half_inning_label": "top1", "kind": "on_base"}
    assert attach_conditioner({"game_id": "game", "half_inning_label": "top1"}, condition, table) == 0.12
    assert attach_conditioner({"game_id": "game", "half_inning_label": "bottom1"}, condition, table) is None
