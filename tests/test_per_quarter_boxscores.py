"""test_per_quarter_boxscores.py — cycle 91a (loop 5).

Pins the fetch + aggregate + Q1-rolling-join contracts for the new
per-quarter boxscore infra. Four cases:

1. Smoke fetch end-to-end (mocked nba_api) writes a cache file and
   the resulting JSON has the expected period/players keys.
2. Aggregation produces at most 4 rows per (game_id, player_id) and
   skips DNP/zero-minute entries.
3. The Q1 rolling join is a graceful NO-OP when the parquet is absent
   — every row dict still carries the q1_*_l5 keys with value None.
4. Rolling-Q1 features have no future leakage — the target game
   itself is NEVER included in the rolling-5 window.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Dict, List
from unittest.mock import patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.aggregate_quarter_boxscores import consolidate  # noqa: E402
from scripts.fetch_per_quarter_boxscores import fetch_quarter  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    _Q1_FEATURE_KEYS,
    _PlayerQuarterStats,
    build_pergame_dataset,
    build_player_quarter_stats,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_gamelog(tmp_path, pid: int, games: List[dict], season: str = "2024-25") -> None:
    (tmp_path / f"gamelog_{pid}_{season}.json").write_text(
        json.dumps(games), encoding="utf-8"
    )


def _default_games(pid_minutes: int = 30) -> List[dict]:
    """5 prior games + 1 target — all played with realistic stats."""
    base = [
        ("Oct 22, 2024", 18, 4, 5),
        ("Oct 25, 2024", 22, 6, 4),
        ("Oct 28, 2024", 25, 3, 7),
        ("Oct 30, 2024", 16, 5, 6),
        ("Nov 02, 2024", 28, 7, 3),
        ("Nov 05, 2024", 24, 4, 5),  # target
    ]
    return [
        {"GAME_DATE": gd, "MATCHUP": "LAL vs. GSW",
         "PTS": pts, "REB": reb, "AST": ast, "FG3M": 1,
         "STL": 1, "BLK": 0, "TOV": 2, "MIN": pid_minutes}
        for (gd, pts, reb, ast) in base
    ]


def _write_quarter_parquet(path: str, rows: List[Dict]) -> None:
    import pandas as pd
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_season_games(cache_dir, gid_to_date: Dict[str, str], season: str = "2024-25") -> None:
    rows = [{"game_id": gid, "game_date": d, "season": season}
            for gid, d in gid_to_date.items()]
    payload = {"v": 1, "rows": rows}
    (cache_dir / f"season_games_{season}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


# ── 1. SMOKE: fetch end-to-end with mocked nba_api ───────────────────────────

def test_smoke_fetch_writes_cache(tmp_path):
    """Mock the nba_api endpoint and verify fetch_quarter writes the cache."""
    cache_dir = str(tmp_path / "quarter_box")
    os.makedirs(cache_dir, exist_ok=True)

    class _FakeFrame:
        def __init__(self, records): self._records = records
        def to_dict(self, _orient): return self._records

    class _FakeBS:
        def __init__(self, *a, **kw): pass
        def get_data_frames(self):
            # v2-shaped columns (uppercase pre-lowering): PLAYER_ID, MIN,
            # PTS etc. The cache writer lowercases keys.
            return [
                _FakeFrame([{
                    "PLAYER_ID": 1234, "PLAYER_NAME": "Test Player",
                    "MIN": "12:00", "PTS": 8, "REB": 2,
                    "AST": 3, "FG3M": 1, "STL": 1,
                    "BLK": 0, "TO": 1, "PF": 2, "PLUS_MINUS": 4,
                }]),
                _FakeFrame([{"TEAM_ABBREVIATION": "LAL", "PTS": 28}]),
            ]

    with patch("nba_api.stats.endpoints.boxscoretraditionalv2."
               "BoxScoreTraditionalV2", _FakeBS):
        ok = fetch_quarter("0022400061", 1, cache_dir=cache_dir)

    assert ok is True
    out = os.path.join(cache_dir, "0022400061_q1.json")
    assert os.path.exists(out)
    with open(out, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["game_id"] == "0022400061"
    assert payload["period"] == 1
    assert isinstance(payload["players"], list) and len(payload["players"]) == 1
    assert payload["players"][0]["player_id"] == 1234

    # Idempotent re-run is a no-op.
    with patch("nba_api.stats.endpoints.boxscoretraditionalv2."
               "BoxScoreTraditionalV2", _FakeBS):
        ok2 = fetch_quarter("0022400061", 1, cache_dir=cache_dir)
    assert ok2 is False


# ── 2. aggregation: at most 4 rows per (game_id, player_id), skips DNPs ──────

def test_aggregation_caps_at_four_rows_per_pair(tmp_path):
    pyarrow = pytest.importorskip("pyarrow")  # noqa: F841
    pd = pytest.importorskip("pandas")  # noqa: F841

    cache_dir = str(tmp_path / "quarter_box")
    os.makedirs(cache_dir, exist_ok=True)
    game_id = "0022400999"

    # 4 quarters: pid 1234 played in Q1-Q3; sat out Q4 (min=None).
    # pid 5678 played only Q4. v2-shape lowercased keys.
    for period in (1, 2, 3, 4):
        players = []
        if period <= 3:
            players.append({
                "player_id": 1234, "min": "10:00",
                "pts": 5 + period, "reb": 2,
                "ast": 1, "fg3m": 1, "stl": 0,
                "blk": 0, "to": 1, "pf": 1,
                "plus_minus": 3,
            })
        if period == 4:
            players.append({
                "player_id": 5678, "min": "08:30",
                "pts": 4, "reb": 1, "ast": 0,
                "fg3m": 0, "stl": 1, "blk": 0,
                "to": 0, "pf": 0, "plus_minus": 1,
            })
        # Throw in a DNP row with min=None to confirm it's skipped.
        players.append({
            "player_id": 9999, "min": None, "pts": 0,
        })
        payload = {"game_id": game_id, "period": period, "players": players}
        with open(os.path.join(cache_dir, f"{game_id}_q{period}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(payload, f)

    parquet_path = str(tmp_path / "player_quarter_stats.parquet")
    n = consolidate(cache_dir=cache_dir, parquet_path=parquet_path)
    assert n == 4  # 3 (pid 1234) + 1 (pid 5678); DNP rows dropped

    import pandas as pd
    df = pd.read_parquet(parquet_path)
    counts = df.groupby(["game_id", "player_id"]).size()
    assert counts.max() <= 4
    assert (df["min"] > 0).all(), "DNPs must be filtered out"
    assert set(df["player_id"].unique()) == {1234, 5678}


# ── 3. join no-op when parquet absent ────────────────────────────────────────

def test_q1_rolling_noop_when_parquet_absent(tmp_path, monkeypatch):
    """No parquet → every row has q1_*_l5 keys with value None."""
    pid = 9991234
    _write_gamelog(tmp_path, pid, _default_games())
    missing = str(tmp_path / "does_not_exist.parquet")
    assert not os.path.exists(missing)
    monkeypatch.setattr(
        "src.prediction.prop_pergame._PLAYER_QUARTER_STATS_PATH", missing
    )

    rows, _cols = build_pergame_dataset(gamelog_dir=str(tmp_path), min_prior=0)
    assert rows, "build_pergame_dataset should still emit rows without the parquet"
    for r in rows:
        for k in _Q1_FEATURE_KEYS:
            assert k in r, f"back-compat: every row carries the key {k!r}"
            assert r[k] is None, (
                f"absent parquet → {k} must be None, got {r[k]!r}"
            )


# ── 4. no future leakage in rolling-Q1 features ──────────────────────────────

def test_q1_rolling_no_future_leakage(tmp_path, monkeypatch):
    """Rolling-Q1 features must EXCLUDE the target game itself.

    Construction:
      - 6 played games for one pid (2024-10-22 .. 2024-11-05).
      - Q1 data exists for ALL 6 in the parquet.
      - For the LAST row (2024-11-05), the rolling-Q1-prior-5 features
        must reflect ONLY the first 5 games. We embed a sentinel large
        value in game #6's Q1 stats to detect any leakage — if it shows
        up in the rolling mean, the join is leaking the future.
    """
    pyarrow = pytest.importorskip("pyarrow")  # noqa: F841

    pid = 9991234
    season = "2024-25"
    _write_gamelog(tmp_path, pid, _default_games(), season=season)

    # Build a season_games file pairing 6 game_ids to the 6 game dates.
    gid_to_date = {
        "0022400001": "2024-10-22",
        "0022400002": "2024-10-25",
        "0022400003": "2024-10-28",
        "0022400004": "2024-10-30",
        "0022400005": "2024-11-02",
        "0022400006": "2024-11-05",  # the target game
    }
    _write_season_games(tmp_path, gid_to_date, season=season)
    monkeypatch.setattr("src.prediction.prop_pergame._NBA_CACHE", str(tmp_path))

    # Q1 stats: first 5 games each give pts=4, reb=2, ast=1; LAST game
    # has a sentinel pts=1000 so any leakage is unmistakable.
    quarter_rows = []
    for i, (gid, gdate) in enumerate(gid_to_date.items()):
        pts = 1000.0 if gid == "0022400006" else 4.0
        quarter_rows.append({
            "game_id": gid, "player_id": pid, "period": 1,
            "min": 12.0, "pts": pts, "reb": 2.0, "ast": 1.0,
            "fg3m": 1.0, "stl": 1.0, "blk": 0.0, "tov": 1.0,
            "pf": 1.0, "plus_minus": 2.0,
        })
    parquet_path = str(tmp_path / "player_quarter_stats.parquet")
    _write_quarter_parquet(parquet_path, quarter_rows)
    monkeypatch.setattr(
        "src.prediction.prop_pergame._PLAYER_QUARTER_STATS_PATH", parquet_path
    )

    rows, _cols = build_pergame_dataset(gamelog_dir=str(tmp_path), min_prior=0)
    rows.sort(key=lambda r: r["date"])
    assert len(rows) == 6, f"expected one row per played game, got {len(rows)}"

    # First row (target = game 1) has zero prior games → all None.
    first = rows[0]
    for k in _Q1_FEATURE_KEYS:
        assert first[k] is None, (
            f"first row should have NO prior Q1 data, got {k}={first[k]}"
        )

    # Last row (target = game 6) must average ONLY the first 5 Q1 rows
    # (pts=4 each). Sentinel pts=1000 from game 6 itself MUST be absent.
    last = rows[-1]
    assert last["q1_pts_l5"] is not None
    assert last["q1_pts_l5"] == pytest.approx(4.0), (
        f"q1_pts_l5 leaked the future: expected 4.0, got {last['q1_pts_l5']}"
    )
    assert last["q1_reb_l5"] == pytest.approx(2.0)
    assert last["q1_ast_l5"] == pytest.approx(1.0)


# ── bonus: standalone wrapper smoke check ────────────────────────────────────

def test_wrapper_empty_when_path_missing(tmp_path):
    """build_player_quarter_stats returns an empty _PlayerQuarterStats
    when the parquet path doesn't exist — no crash, no warning."""
    w = build_player_quarter_stats(
        parquet_path=str(tmp_path / "missing.parquet"),
        season_games_dir=str(tmp_path),
    )
    assert isinstance(w, _PlayerQuarterStats)
    assert len(w) == 0
    assert w.quarter(1234, datetime(2024, 11, 5), 1) is None
    feats = w.rolling_q1_prior(1234, [datetime(2024, 10, 22)])
    assert all(v is None for v in feats.values())
