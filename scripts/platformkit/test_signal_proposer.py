"""Synthetic coverage for the mechanical as-of signal proposer."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit import signal_foundry as foundry
from scripts.platformkit import signal_proposer as proposer


def _matrix() -> pd.DataFrame:
    rows = []
    for game in range(18):
        for player, team in ((1, 10), (2, 10), (3, 20), (4, 20)):
            value = float(game + player)
            rows.append({"gameDate": pd.Timestamp("2024-01-01") + pd.Timedelta(days=game), "gameId": game,
                         "personId": player, "teamId": team, "minutes_l5": value,
                         "cum_distance_7d": value * 2, "raw_same_game": value * 9,
                         "target": value + (player % 2)})
    return pd.DataFrame(rows)


def _folds(frame: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    dates = frame["gameDate"].drop_duplicates().to_numpy(); blocks = np.array_split(dates, 4)
    return [(np.flatnonzero(frame.gameDate.isin(np.concatenate(blocks[:i]))), np.flatnonzero(frame.gameDate.isin(blocks[i]))) for i in range(1, 4)]


def test_grammar_materializes_asof_columns_and_battery_is_capped(tmp_path, monkeypatch) -> None:
    ledger = tmp_path / "foundry.jsonl"
    ledger.write_text(json.dumps({"candidate_interactions": [{"pair": ["minutes_l5", "cum_distance_7d"], "score": 1.0}]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(foundry, "LEDGER_PATH", ledger); monkeypatch.setattr(foundry, "PERMUTATIONS", 2)
    foundry.REGISTRY.clear(); frame = _matrix()
    work, specs = proposer.propose(frame, "target", max_new=20)
    names = {spec.name for spec in specs}
    assert {"prop_interaction_minutes_l5_x_cum_distance_7d", "prop_zscore_minutes_l5",
            "prop_delta_l10_minutes_l5", "prop_team_mean_minutes_l5"} <= names
    assert "raw_same_game" not in proposer.asof_columns(frame, "target")
    assert all(name in work for name in names)
    foundry.REGISTRY.clear()
    truncated, truncated_specs = proposer.propose(frame.iloc[:48], "target", max_new=20, ledger_path=ledger)
    common = [spec.name for spec in truncated_specs]
    pd.testing.assert_frame_equal(work.loc[:47, common], truncated.loc[:, common], check_dtype=False)
    foundry.REGISTRY.clear()
    report = proposer.propose_and_battery(frame, "target", _folds(frame), max_new=2, ledger_path=ledger)
    assert 0 < len(report["specs"]) <= 2 and len(report["results"]) == len(report["specs"])
    assert len(ledger.read_text(encoding="utf-8").splitlines()) >= 1 + len(report["results"])
