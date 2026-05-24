"""tests/test_live_engine.py -- cycle 95c (loop 5).

Regression + integration tests for the consolidated live-prediction entry
point ``src.prediction.live_engine``.

The 5 tests below cover the spec from cycle 95c:

  1. project_from_snapshot returns rows matching predict_in_game.project_snapshot
     (regression -- same math, new entry).
  2. project_full_slate iterates every snapshot today.
  3. edge_vs_pregame attaches pregame_pred when the ledger exists.
  4. edge_vs_pregame omits pregame_pred gracefully when the ledger is absent.
  5. write_ledger appends rows in the cycle-88n schema.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig                       # noqa: E402
from src.prediction import live_engine               # noqa: E402


def _snapshot(period=3, clock="6:00", home_score=70, away_score=60,
              home_team="OKC", away_team="SAS", game_id="0022400123",
              players=None):
    return {
        "game_id": game_id,
        "captured_at": "2026-05-24T20:00:00",
        "game_status": "LIVE",
        "period": period, "clock": clock,
        "home_score": home_score, "away_score": away_score,
        "home_team": home_team, "away_team": away_team,
        "players": players if players is not None else [],
    }


def _player(name, team, pid, is_starter=True, **stats):
    base = {"name": name, "player_id": pid, "team": team,
            "is_starter": is_starter, "min": 22.0, "pf": 2,
            "pts": 15, "reb": 5, "ast": 4, "fg3m": 1, "stl": 1, "blk": 0, "tov": 2}
    base.update(stats)
    return base


# ── 1. project_from_snapshot is a thin wrapper -------------------------------

def test_project_from_snapshot_matches_predict_in_game():
    """Regression: same logic as scripts.predict_in_game.project_snapshot."""
    snap = _snapshot(players=[
        _player("Jokic", "OKC", 1),
        _player("Wembanyama", "SAS", 2),
    ])

    direct = pig.project_snapshot(dict(snap))
    via_engine = live_engine.project_from_snapshot(dict(snap))

    # Same row count.
    assert len(direct) == len(via_engine)

    # Every (player_id, stat) projected_final value matches exactly.
    direct_idx = {(r["player_id"], r["stat"]): r["projected_final"] for r in direct}
    engine_idx = {(r["player_id"], r["stat"]): r["projected_final"] for r in via_engine}
    assert direct_idx == engine_idx

    # The engine wrapper documents the snapshot context on every row.
    for r in via_engine:
        assert r["snapshot_period"] == snap["period"]
        assert r["snapshot_clock"] == snap["clock"]


# ── 2. project_full_slate iterates today's snapshots --------------------------

def test_project_full_slate_iterates_today_snapshots(tmp_path, monkeypatch):
    """Two snapshot files -> two game_id keys in the result dict."""
    # Write two snapshots to a fake data/live/ dir.
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    snap_a = _snapshot(game_id="0022400001",
                       players=[_player("Player A", "OKC", 11)])
    snap_b = _snapshot(game_id="0022400002",
                       players=[_player("Player B", "SAS", 22)])
    path_a = live_dir / "0022400001_1234567890.json"
    path_b = live_dir / "0022400002_1234567890.json"
    path_a.write_text(json.dumps(snap_a), encoding="utf-8")
    path_b.write_text(json.dumps(snap_b), encoding="utf-8")

    # Patch the loader helpers used by live_engine.project_full_slate.
    monkeypatch.setattr(
        live_engine, "list_today_snapshots",
        lambda date_iso: [str(path_a), str(path_b)],
    )
    monkeypatch.setattr(
        live_engine, "load_live_state",
        lambda path: json.loads(open(path, encoding="utf-8").read()),
    )

    out = live_engine.project_full_slate("2026-05-24")
    assert set(out.keys()) == {"0022400001", "0022400002"}
    # Each game projects 7 stats * 1 player = 7 rows.
    assert len(out["0022400001"]) == 7
    assert len(out["0022400002"]) == 7


# ── 3. edge_vs_pregame attaches pregame_pred from the ledger -----------------

def test_edge_vs_pregame_attaches_when_ledger_exists(tmp_path, monkeypatch):
    """Pre-game ledger exists -> rows get pregame_pred + delta."""
    snap = _snapshot(players=[_player("Star", "OKC", pid=99, pts=18, reb=6)])

    # Stand in pregame predictions: PTS=24.0, REB=10.0 for player 99.
    fake_pregame = {(99, "pts"): 24.0, (99, "reb"): 10.0}
    monkeypatch.setattr(
        "predict_in_game.load_pregame_predictions",
        lambda date_iso: fake_pregame,
    )

    rows = live_engine.edge_vs_pregame(snap, "2026-05-24")
    pts_row = next(r for r in rows if r["stat"] == "pts")
    reb_row = next(r for r in rows if r["stat"] == "reb")
    stl_row = next(r for r in rows if r["stat"] == "stl")

    assert pts_row["pregame_pred"] == 24.0
    assert reb_row["pregame_pred"] == 10.0
    assert "delta" in pts_row
    # PTS delta = projected_final - 24.0.
    assert pts_row["delta"] == pts_row["projected_final"] - 24.0
    # STL had no pregame entry -> no attachment.
    assert "pregame_pred" not in stl_row


# ── 4. edge_vs_pregame degrades gracefully when ledger is absent -------------

def test_edge_vs_pregame_omits_pregame_when_ledger_absent(monkeypatch):
    """No ledger -> no pregame_pred / delta keys, no crash."""
    snap = _snapshot(players=[_player("X", "OKC", pid=5)])

    monkeypatch.setattr(
        "predict_in_game.load_pregame_predictions",
        lambda date_iso: {},     # empty == ledger missing / unreadable
    )

    rows = live_engine.edge_vs_pregame(snap, "2026-05-24")
    assert len(rows) == 7
    for r in rows:
        assert "pregame_pred" not in r
        assert "delta" not in r


# ── 5. write_ledger writes the cycle-88n schema -------------------------------

def test_write_ledger_appends_in_cycle_88n_schema(tmp_path):
    """write_ledger appends one row per projection in the canonical schema."""
    snap = _snapshot(players=[_player("Ledger Star", "OKC", pid=42, pts=20)])
    rows = live_engine.project_from_snapshot(snap)
    # Stamp game_id onto rows so the ledger has the cross-link.
    for r in rows:
        r["game_id"] = snap["game_id"]

    out = tmp_path / "2026-05-24_inplay.csv"
    n = live_engine.write_ledger(rows, "2026-05-24", out_path=str(out))
    assert n == len(rows)

    # Reopen + verify schema + content.
    with open(out, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        records = list(reader)

    # The cycle-88n schema header MUST exactly match.
    expected_header = [
        "date", "game_id", "player_id", "player", "team", "opp", "venue",
        "stat", "pred", "lineup_status", "lineup_class", "play_pct",
        "injury_status", "pred_kind", "snapshot_period", "snapshot_clock",
        "current_stat",
    ]
    assert header == expected_header
    assert len(records) == n
    pts_record = next(r for r in records if r["stat"] == "pts")
    assert pts_record["player"] == "Ledger Star"
    assert pts_record["player_id"] == "42"
    assert pts_record["game_id"] == snap["game_id"]
    assert pts_record["pred_kind"].startswith("Q3_inplay")
    # current_stat formatted to 4 decimals per cycle-88n schema.
    assert pts_record["current_stat"] == "20.0000"
