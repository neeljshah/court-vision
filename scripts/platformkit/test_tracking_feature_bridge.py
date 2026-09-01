"""Leak-safety and skip-reporting tests for ``tracking_feature_bridge``.

Run: python -m pytest scripts/platformkit/test_tracking_feature_bridge.py -q
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from scripts.platformkit import tracking_feature_bridge as bridge

FAKE_MODULE = "fake_sport_feature_module"
GAME_DATES = {"g1": "2024-01-01", "g2": "2024-01-03",
              "g3": "2024-01-05", "g4": "2024-01-07"}
CUTOFF = pd.Timestamp("2024-01-05")


def _install_fake_module() -> None:
    """Register an in-memory feature module shaped like the real ones."""
    module = types.ModuleType(FAKE_MODULE)

    def game_features(path: str | Path) -> pd.DataFrame:
        rows = pd.read_csv(path)
        return pd.DataFrame([{"touch_count": float(len(rows)),
                              "mean_x": float(rows["x"].mean())}])

    module.game_features = game_features
    sys.modules[FAKE_MODULE] = module


def _write_corpus(root: Path, game_ids: list[str]) -> tuple[Path, Path]:
    """Write reports plus tracking CSVs; g4 gets a report but no tracking."""
    reports, tracking = root / "tracking_reports", root / "tracking"
    for index, game_id in enumerate(game_ids, start=1):
        for sport in ("fake", "tennis"):
            directory = reports / sport
            directory.mkdir(parents=True, exist_ok=True)
            (directory / ("%s.json" % game_id)).write_text(
                json.dumps({"sport": sport, "passed": True}), encoding="utf-8")
        if game_id == "g4":
            continue
        game_dir = tracking / game_id
        game_dir.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame({"frame": range(index + 1),
                              "x": [float(index)] * (index + 1)})
        frame.to_csv(game_dir / bridge.TRACKING_FILE, index=False)
    return reports, tracking


def _dates(game_ids: list[str]) -> pd.DataFrame:
    rows = [{"game_id": game_id, "date": GAME_DATES[game_id], "team": team}
            for game_id in game_ids for team in ("AAA", "BBB")]
    return pd.DataFrame(rows)


@pytest.fixture()
def collected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    _install_fake_module()
    monkeypatch.setitem(bridge.FEATURE_MODULES, "fake",
                        "%s:game_features" % FAKE_MODULE)
    monkeypatch.setitem(bridge.FEATURE_MODULES, "tennis",
                        "domains.tennis.tracking.no_such_module:game_features")
    reports, tracking = _write_corpus(tmp_path, list(GAME_DATES))
    return bridge.collect_game_features(reports, tracking)


def test_collection_finds_games_with_both_inputs(collected: pd.DataFrame) -> None:
    """Only games holding a report AND a tracking CSV become rows."""
    assert list(collected["game_id"]) == ["g1", "g2", "g3"]
    assert set(collected["sport"]) == {"fake"}
    assert list(collected["touch_count"]) == [2.0, 3.0, 4.0]
    assert collected.attrs["missing_tracking"] == ["g4", "g4"]
    assert collected.attrs["failed_games"] == []


def test_missing_module_sport_is_named_not_crashed(collected: pd.DataFrame) -> None:
    """A sport with no importable feature module is reported, not fatal."""
    assert collected.attrs["skipped_sports"] == {"tennis": 3}


def test_asof_drops_raw_and_starts_empty(collected: pd.DataFrame) -> None:
    """Raw same-game columns never survive; a team's first game has no history."""
    asof = bridge.to_asof_team_features(collected, _dates(["g1", "g2", "g3"]))
    bridge.assert_leak_contract(asof)
    assert "touch_count" not in asof.columns
    assert set(bridge.asof_columns(asof)) == {
        "touch_count_l5", "touch_count_asof", "mean_x_l5", "mean_x_asof"}
    first = asof.loc[asof["game_id"] == "g1"]
    assert first["touch_count_l5"].isna().all()
    second = asof.loc[asof["game_id"] == "g2", "touch_count_asof"]
    assert list(second) == [2.0, 2.0]


def test_truncation_invariance(collected: pd.DataFrame) -> None:
    """Rows before T are identical whether or not later games exist."""
    early = ["g1", "g2"]
    full = bridge.to_asof_team_features(collected, _dates(["g1", "g2", "g3"]))
    truncated = bridge.to_asof_team_features(
        collected.loc[collected["game_id"].isin(early)], _dates(early))
    full_before_t = full.loc[full["date"] < CUTOFF].reset_index(drop=True)
    assert not full_before_t.empty
    assert_frame_equal(full_before_t, truncated.reset_index(drop=True),
                       check_dtype=True)


def test_register_signals_uses_asof_columns(collected: pd.DataFrame) -> None:
    """Foundry specs point at as-of columns that exist in the frame."""
    asof = bridge.to_asof_team_features(collected, _dates(["g1", "g2", "g3"]))
    specs = bridge.register_signals(asof)
    assert specs and all(spec.compute in asof.columns for spec in specs)
    assert all(spec.sport == "fake" and spec.grain == "team_game" for spec in specs)
    assert specs == bridge.register_signals(asof)


def test_dates_must_carry_team(collected: pd.DataFrame) -> None:
    """A game-to-team map is required; the bridge never guesses it."""
    with pytest.raises(ValueError, match="team"):
        bridge.to_asof_team_features(
            collected, pd.DataFrame({"game_id": ["g1"], "date": ["2024-01-01"]}))


def test_leak_contract_rejects_raw_column() -> None:
    """A raw same-game column would be refused before registration."""
    with pytest.raises(ValueError, match="touch_count"):
        bridge.assert_leak_contract(pd.DataFrame(columns=["sport", "touch_count"]))
