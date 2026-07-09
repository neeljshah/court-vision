"""Per-file test for scripts/backfill_ot_q0.py -- zero network (all HTTP
mocked via monkeypatch on `_get_json`).

Run:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest scripts/test_backfill_ot_q0.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import scripts.backfill_ot_q0 as m


def test_replace_regulation_files_moves_q1_q4_only(tmp_path):
    gid = "0000000001"
    for p in (1, 2, 3, 4):
        (tmp_path / f"{gid}_q{p}.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"{gid}_q0.json").write_text("{}", encoding="utf-8")  # untouched

    moved = m.replace_regulation_files(gid, cache_dir=tmp_path)

    assert moved == 4
    assert (tmp_path / f"{gid}_q0.json").exists()
    for p in (1, 2, 3, 4):
        assert not (tmp_path / f"{gid}_q{p}.json").exists()
        assert (tmp_path / f"{gid}_q{p}.json.bak").exists()


def test_target_games_excludes_already_q0_and_non_ot(tmp_path, monkeypatch):
    finals = pd.DataFrame([
        {"game_id": "1", "is_ot": True, "was_truncated": True, "season": "2024-25"},   # target
        {"game_id": "2", "is_ot": True, "was_truncated": True, "season": "2024-25"},   # already has q0
        {"game_id": "3", "is_ot": False, "was_truncated": True, "season": "2024-25"},  # not OT -- excluded
        {"game_id": "4", "is_ot": True, "was_truncated": False, "season": "2024-25"},  # not truncated -- excluded
    ])
    games = pd.DataFrame([
        {"game_id": "0000000001", "date": pd.Timestamp("2025-01-01"),
         "home_team": "BOS", "away_team": "LAL"},
        {"game_id": "0000000002", "date": pd.Timestamp("2025-01-02"),
         "home_team": "MIA", "away_team": "NYK"},
    ])
    finals_path = tmp_path / "finals.parquet"
    games_path = tmp_path / "games.parquet"
    finals.to_parquet(finals_path)
    games.to_parquet(games_path)
    monkeypatch.setattr(m, "_FINALS_PARQUET", finals_path)
    monkeypatch.setattr(m, "_GAMES_PARQUET", games_path)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "0000000002_q0.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(m, "_CACHE_DIR", cache_dir)

    out = m.target_games()

    assert out["game_id"].tolist() == ["0000000001"]


def test_run_writes_q0_and_supersedes_quarters(tmp_path, monkeypatch):
    gid = "0000000009"
    finals = pd.DataFrame([{"game_id": gid, "is_ot": True, "was_truncated": True,
                             "season": "2024-25"}])
    games = pd.DataFrame([{"game_id": gid, "date": pd.Timestamp("2025-02-01"),
                           "home_team": "BOS", "away_team": "LAL"}])
    finals_path = tmp_path / "finals.parquet"
    games_path = tmp_path / "games.parquet"
    finals.to_parquet(finals_path)
    games.to_parquet(games_path)
    monkeypatch.setattr(m, "_FINALS_PARQUET", finals_path)
    monkeypatch.setattr(m, "_GAMES_PARQUET", games_path)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    for p in (1, 2, 3, 4):
        (cache_dir / f"{gid}_q{p}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(m, "_CACHE_DIR", cache_dir)

    monkeypatch.setattr(m, "load_player_map", lambda: {})
    monkeypatch.setattr(m, "load_activity_windows", lambda: {})

    def fake_get_json(sess, url, sleep, tries=4):
        if "scoreboard" in url:
            return {"events": [{"id": "999", "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"abbreviation": "BOS"}},
                {"homeAway": "away", "team": {"abbreviation": "LAL"}},
            ]}]}]}
        return {
            "header": {"competitions": [{"status": {"type": {"name": "STATUS_FINAL"}}}]},
            "boxscore": {"players": [{
                "team": {"abbreviation": "BOS"},
                "statistics": [{"keys": ["points"], "athletes": [{
                    "athlete": {"id": "1", "displayName": "Test Player"},
                    "starter": True, "stats": ["10"],
                }]}],
            }]},
        }

    monkeypatch.setattr(m, "_get_json", fake_get_json)

    c = m.run(sleep=0.0)

    assert c["written"] == 1
    assert c["quarters_replaced"] == 4
    q0 = json.loads((cache_dir / f"{gid}_q0.json").read_text(encoding="utf-8"))
    assert q0["period"] == 0
    assert len(q0["players"]) == 1
    for p in (1, 2, 3, 4):
        assert not (cache_dir / f"{gid}_q{p}.json").exists()
        assert (cache_dir / f"{gid}_q{p}.json.bak").exists()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
