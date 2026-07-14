"""Tests for scripts.platformkit.omni.k_minutes_rescore (K minutes-mediation
decomposition of the accepted high_foul_vs_low_foul family).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_minutes_rescore.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_minutes_rescore as kmr

_COND = "high_foul_vs_low_foul"


def _seed_parent(base_dir, player_id: int, parent_delta: float) -> str:
    scope = {"sport": "nba", "entity_type": "player", "entity_ids": [player_id], "context": _COND}
    claim = {
        "statement": f"NBA player {player_id} pts delta under {_COND} :: stage-B discovery re-mine",
        "type": "effect", "scope": scope, "topic": f"reactions.{_COND}", "lifecycle": "accepted",
        "effect": {"verdict": "TESTED", "delta": parent_delta, "n_a": 30, "n_b": 30, "stat": "pts"},
        "provenance": {"created_by_lane": "k_stage_b"},
    }
    return cl.add_claim(claim, base_dir=base_dir)


def _seed_meta(base_dir, parent_claim_ids: list[str]) -> None:
    claim = {
        "claim_id": kmr._META_CLAIM_ID, "statement": "family meta", "type": "meta",
        "scope": {"sport": "nba", "entity_type": "mechanism_family", "entity_ids": ["high_foul_reaction"]},
        "topic": "reactions.high_foul_vs_low_foul", "lifecycle": "accepted",
        "links": {"parent_claims": parent_claim_ids},
    }
    cl.add_claim(claim, base_dir=base_dir)


def _player_rows(player_id: int, min_a: float, min_b: float, ppm_a: float, ppm_b: float,
                  season_start: str, n: int = 15) -> list[dict]:
    """side a = high_foul (pf=4), side b = low_foul (pf=1); small deterministic
    jitter keeps Welch variance nonzero without needing randomness."""
    dates = pd.date_range(season_start, periods=2 * n, freq="1D")
    rows = []
    for i in range(n):
        jitter = (i % 3 - 1) * 0.4
        m = min_a + jitter
        rows.append({
            "player_id": player_id, "player_name": "P", "game_id": f"{player_id}_{season_start}_a{i}",
            "date": dates[2 * i], "is_home": 1.0, "pf": 4.0, "min": m,
            "pts": round((ppm_a + (i % 3 - 1) * 0.01) * m, 3),
        })
    for i in range(n):
        jitter = (i % 3 - 1) * 0.4
        m = min_b + jitter
        rows.append({
            "player_id": player_id, "player_name": "P", "game_id": f"{player_id}_{season_start}_b{i}",
            "date": dates[2 * i + 1], "is_home": 0.0, "pf": 1.0, "min": m,
            "pts": round((ppm_b + (i % 3 - 1) * 0.01) * m, 3),
        })
    return rows


def _two_slice_frame(player_id: int, min_a: float, min_b: float, ppm_a: float, ppm_b: float) -> pd.DataFrame:
    rows = _player_rows(player_id, min_a, min_b, ppm_a, ppm_b, "2024-11-01")
    rows += _player_rows(player_id, min_a, min_b, ppm_a, ppm_b, "2025-11-01")
    return pd.DataFrame(rows)


def test_blocked_without_meta_claim(tmp_path):
    out = kmr.run_k_minutes_rescore(base_dir=tmp_path, source=pd.DataFrame())
    assert out["blocked"] is True


def test_pure_minutes_mediated_frame_yields_minutes_mediated(tmp_path):
    parent_id = _seed_parent(tmp_path, 1, parent_delta=-8.0)
    _seed_meta(tmp_path, [parent_id])
    # minutes swing big (32 -> 18), efficiency (pts/min) held constant.
    df = _two_slice_frame(1, min_a=18.0, min_b=32.0, ppm_a=0.6, ppm_b=0.6)
    out = kmr.run_k_minutes_rescore(base_dir=tmp_path, source=df)
    assert out["verdicts"][1] == "MINUTES_MEDIATED"


def test_pure_efficiency_frame_yields_efficiency_component(tmp_path):
    parent_id = _seed_parent(tmp_path, 2, parent_delta=-9.0)
    _seed_meta(tmp_path, [parent_id])
    # minutes held constant (30 -> 30), efficiency swings big (0.8 -> 0.5).
    df = _two_slice_frame(2, min_a=30.0, min_b=30.0, ppm_a=0.5, ppm_b=0.8)
    out = kmr.run_k_minutes_rescore(base_dir=tmp_path, source=df)
    assert out["verdicts"][2] == "EFFICIENCY_COMPONENT"


def test_claims_ledgered_with_parent_link_and_market_families(tmp_path):
    parent_id = _seed_parent(tmp_path, 1, parent_delta=-8.0)
    _seed_meta(tmp_path, [parent_id])
    df = _two_slice_frame(1, min_a=18.0, min_b=32.0, ppm_a=0.6, ppm_b=0.6)
    kmr.run_k_minutes_rescore(base_dir=tmp_path, source=df)
    claims = cl.query(sport="nba", base_dir=tmp_path)
    minutes_claims = claims[claims["statement"].str.contains("minutes-mediation decomposition")]
    assert len(minutes_claims) >= 2  # min + pts_per_min claims for player 1
    import json
    links = json.loads(minutes_claims.iloc[0]["links_json"])
    assert links["parent_claims"] == [parent_id]
    assert links["market_families"] == ["ingame.props.minutes", "ingame.props.pts"]


def test_idempotent_rerun_does_not_duplicate_claims(tmp_path):
    parent_id = _seed_parent(tmp_path, 1, parent_delta=-8.0)
    _seed_meta(tmp_path, [parent_id])
    df = _two_slice_frame(1, min_a=18.0, min_b=32.0, ppm_a=0.6, ppm_b=0.6)
    first = kmr.run_k_minutes_rescore(base_dir=tmp_path, source=df)
    second = kmr.run_k_minutes_rescore(base_dir=tmp_path, source=df)
    assert second["claims_added"] == 0
    assert first["verdicts"] == second["verdicts"]
