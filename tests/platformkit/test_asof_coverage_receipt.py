"""Per-file test for scripts.platformkit.asof_coverage_receipt (tmp_path only, no real data).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_asof_coverage_receipt.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit import asof_coverage_receipt as acr


def _games_df():
    return pd.DataFrame({
        "game_id": ["001", "002", "003", "004"],
        "date": pd.to_datetime(["2024-10-20", "2024-11-01", "2025-10-22", "2025-11-05"]),
        "season": ["2024-25", "2024-25", "2025-26", "2025-26"],
    })


def _write(df, path):
    df.to_parquet(path, index=False)
    return path


def test_load_games(tmp_path):
    games_path = _write(_games_df(), tmp_path / "games.parquet")
    gid_season, ranges, counts = acr.load_games(str(games_path))
    assert gid_season == {"001": "2024-25", "002": "2024-25", "003": "2025-26", "004": "2025-26"}
    assert counts == {"2024-25": 2, "2025-26": 2}
    lo, hi = ranges["2025-26"]
    assert lo == pd.Timestamp("2025-10-22") and hi == pd.Timestamp("2025-11-05")


def test_table_coverage_via_season_column(tmp_path):
    gid_season, ranges, _ = acr.load_games(str(_write(_games_df(), tmp_path / "games.parquet")))
    df = pd.DataFrame({"season": ["2025-26", "2025-26", "2024-25"], "x": [1, 2, 3]})
    cov = acr.table_coverage(str(_write(df, tmp_path / "t_season.parquet")), gid_season, ranges)
    assert cov["2025-26"]["rows"] == 2
    assert cov["2025-26"]["games"] is None  # no game_id column to count
    assert cov["2024-25"]["rows"] == 1


def test_table_coverage_via_game_id(tmp_path):
    gid_season, ranges, _ = acr.load_games(str(_write(_games_df(), tmp_path / "games.parquet")))
    df = pd.DataFrame({"game_id": ["003", "004", "004"]})
    cov = acr.table_coverage(str(_write(df, tmp_path / "t_gid.parquet")), gid_season, ranges)
    assert cov["2025-26"]["rows"] == 3
    assert cov["2025-26"]["games"] == 2  # 003, 004 distinct


def test_table_coverage_via_date_bucket(tmp_path):
    gid_season, ranges, _ = acr.load_games(str(_write(_games_df(), tmp_path / "games.parquet")))
    df = pd.DataFrame({"date": pd.to_datetime(["2025-10-25", "2025-10-25", "2024-10-21"])})
    cov = acr.table_coverage(str(_write(df, tmp_path / "t_date.parquet")), gid_season, ranges)
    assert cov["2025-26"]["rows"] == 2
    assert cov["2024-25"]["rows"] == 1
    assert cov["2025-26"]["max_date"] == "2025-10-25"


def test_table_coverage_unmapped_is_unknown(tmp_path):
    gid_season, ranges, _ = acr.load_games(str(_write(_games_df(), tmp_path / "games.parquet")))
    df = pd.DataFrame({"x": [1, 2]})
    cov = acr.table_coverage(str(_write(df, tmp_path / "t_none.parquet")), gid_season, ranges)
    assert cov["unknown"]["rows"] == 2


def test_check_coverage_pct_and_missing_table():
    receipt = {
        "season_game_counts": {"2025-26": 100},
        "tables": {
            "good": {"2025-26": {"rows": 96, "games": 96}},
            "bad": {"2025-26": {"rows": 80, "games": 80}},
            "no_game_id": {"2025-26": {"rows": 95, "games": None}},
        },
    }
    assert acr.check_coverage(receipt, "good", "2025-26") == pytest.approx(0.96)
    assert acr.check_coverage(receipt, "bad", "2025-26") == pytest.approx(0.80)
    assert acr.check_coverage(receipt, "no_game_id", "2025-26") == pytest.approx(0.95)
    assert acr.check_coverage(receipt, "missing_table", "2025-26") == 0.0


def test_cli_check_exits_3_when_under_95_pct(tmp_path, monkeypatch):
    games_path = _write(_games_df(), tmp_path / "games.parquet")
    thin = _write(pd.DataFrame({"game_id": ["003"]}), tmp_path / "asof_thin.parquet")  # 1/2 games
    monkeypatch.setattr(acr, "_GAMES", str(games_path))
    monkeypatch.setattr(acr, "_table_paths", lambda: [str(thin)])
    monkeypatch.setattr("sys.argv", [
        "asof_coverage_receipt.py", "--out", str(tmp_path / "coverage.json"),
        "--check", "asof_thin", "--season", "2025-26",
    ])
    with pytest.raises(SystemExit) as exc:
        acr.main()
    assert exc.value.code == 3


def test_cli_check_passes_when_full_coverage(tmp_path, monkeypatch, capsys):
    games_path = _write(_games_df(), tmp_path / "games.parquet")
    full = _write(pd.DataFrame({"game_id": ["003", "004"]}), tmp_path / "asof_full.parquet")
    monkeypatch.setattr(acr, "_GAMES", str(games_path))
    monkeypatch.setattr(acr, "_table_paths", lambda: [str(full)])
    monkeypatch.setattr("sys.argv", [
        "asof_coverage_receipt.py", "--out", str(tmp_path / "coverage.json"),
        "--check", "asof_full", "--season", "2025-26",
    ])
    acr.main()  # must NOT raise SystemExit — 2/2 games is 100% coverage
    assert "100.0%" in capsys.readouterr().out
