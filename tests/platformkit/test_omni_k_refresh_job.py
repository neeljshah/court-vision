"""Per-file test for scripts.platformkit.omni.k_refresh_job.

Acceptance criteria:
1. No rows dated "yesterday" (the current off-season common case) -> no-op,
   status "no_games", heartbeat row logged, no coverage/claim writes.
2. Rows dated "yesterday" exist for touched active players -> only THOSE
   players' cells recompute (an untouched active player's coverage row stays
   UNMINED); a claim is ledgered per tested cell.
3. Idempotent rerun of the same "yesterday" adds zero new claims.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_refresh_job.py -q
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_refresh_job as krj


def _active_players_stub():
    return pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Alpha", "Bravo", "Charlie"]})


def _synthetic_frame(yday: date) -> pd.DataFrame:
    """Player 1 and 2 played yesterday (enough history each side to clear
    MIN_SIDE_N); player 3 has history but nothing dated yesterday (untouched)."""
    rows = []
    dates = pd.date_range("2025-10-01", periods=24, freq="2D")
    for pid, bump in ((1, 0.0), (2, 3.0)):
        for i, d in enumerate(dates):
            is_b2b = i % 4 == 0
            rows.append({
                "player_id": pid, "player_name": f"P{pid}", "game_id": f"g{pid}_{i}",
                "date": pd.Timestamp(yday) if i == len(dates) - 1 else d,
                "is_home": float(i % 2), "pf": 4.0 if i % 5 == 0 else 1.0,
                "pts": 20.0 - bump if is_b2b else 20.0, "min": 30.0,
            })
    for i, d in enumerate(dates):
        rows.append({
            "player_id": 3, "player_name": "Charlie", "game_id": f"g3_{i}",
            "date": d, "is_home": float(i % 2), "pf": 1.0, "pts": 20.0, "min": 30.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _stub_archetypes(monkeypatch):
    from scripts.platformkit.omni import k_sweep_nba as ksn
    monkeypatch.setattr(ksn, "_archetype_map", lambda: {1: "Scoring Guard", 2: "Scoring Guard", 3: "Stretch Big"})


def test_no_games_night_is_a_noop_with_heartbeat(tmp_path):
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub())
    yday = date(2025, 11, 1)
    df = _synthetic_frame(date(2025, 1, 1))  # no row lands on yday
    hb = tmp_path / "heartbeat.jsonl"
    out = krj.run_k_refresh(base_dir=tmp_path, source=df, today=date(2025, 11, 2), heartbeat_path=hb)
    assert out["status"] == "no_games"
    assert out["touched_players"] == 0
    lines = hb.read_text(encoding="ascii").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == "no_games"
    matrix = kc.load_matrix(base_dir=tmp_path)
    assert (matrix["status"] == "UNMINED").all()


def test_only_touched_players_recompute(tmp_path):
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub())
    yday = date(2025, 11, 1)
    df = _synthetic_frame(yday)
    hb = tmp_path / "heartbeat.jsonl"
    out = krj.run_k_refresh(base_dir=tmp_path, source=df, today=date(2025, 11, 2), heartbeat_path=hb)
    assert out["status"] == "ran"
    assert out["touched_players"] == 2
    matrix = kc.load_matrix(base_dir=tmp_path)
    reactions = matrix[matrix["dimension"] == "reactions"].set_index("player_id")
    assert reactions.loc[1, "status"] != "UNMINED"
    assert reactions.loc[2, "status"] != "UNMINED"
    assert reactions.loc[3, "status"] == "UNMINED"  # untouched player never recomputed
    claims = cl.query(sport="nba", base_dir=tmp_path)
    assert len(claims) > 0


def test_idempotent_rerun_adds_zero_new_claims(tmp_path):
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub())
    yday = date(2025, 11, 1)
    df = _synthetic_frame(yday)
    hb = tmp_path / "heartbeat.jsonl"
    first = krj.run_k_refresh(base_dir=tmp_path, source=df, today=date(2025, 11, 2), heartbeat_path=hb)
    assert first["claims_added"] > 0
    second = krj.run_k_refresh(base_dir=tmp_path, source=df, today=date(2025, 11, 2), heartbeat_path=hb)
    assert second["claims_added"] == 0
