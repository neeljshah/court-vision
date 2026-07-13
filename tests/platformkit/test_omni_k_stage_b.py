"""Tests for scripts.platformkit.omni.k_stage_b (K stage-B family test +
reserve replication for K-NBA-1's full-store escalations).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_stage_b.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_stage_b as ksb
from scripts.platformkit.omni import k_sweep_nba as ksn

_COND = "b2b_vs_rest"


def _seed_escalated_claim(base_dir, player_id: int, parent_delta: float) -> str:
    scope = {"sport": "nba", "entity_type": "player", "entity_ids": [player_id], "context": _COND}
    claim = {
        "statement": f"NBA player {player_id} pts delta under {_COND}", "type": "conditional",
        "scope": scope, "topic": f"reactions.{_COND}", "lifecycle": "escalation_screened",
        "effect": {"verdict": "TESTED", "delta": parent_delta, "n_a": 50, "n_b": 50, "stat": "pts"},
        "provenance": {"created_by_lane": "k_sweep_nba_v1"},
    }
    return cl.add_claim(claim, base_dir=base_dir)


def _synthetic_two_slice_frame(bump_reserve: float) -> pd.DataFrame:
    """Player 1: clean b2b-vs-rest gap in BOTH discovery (2024-11) and
    reserve (2025-11); bump_reserve controls whether the reserve gap holds
    (replicates) or vanishes (fails)."""
    rows = []
    for season, start, bump in (("disc", "2024-11-01", 8.0), ("res", "2025-11-01", bump_reserve)):
        dates = pd.date_range(start, periods=40, freq="2D")
        for i, d in enumerate(dates):
            is_b2b = i % 3 == 0
            rows.append({
                "player_id": 1, "player_name": "Alpha", "game_id": f"{season}_{i}",
                "date": d - pd.Timedelta(days=1) if is_b2b else d,
                "is_home": float(i % 2), "pf": 1.0,
                "pts": 20.0 - bump if is_b2b else 20.0, "min": 30.0,
            })
    return pd.DataFrame(rows)


def test_leak_discovery_only_excludes_reserve(tmp_path):
    _seed_escalated_claim(tmp_path, 1, parent_delta=-8.0)
    df = _synthetic_two_slice_frame(bump_reserve=8.0)
    discovery, reserve = ksn.split_discovery_reserve(df)
    assert (discovery["date"] < pd.Timestamp(ksn.RESERVE_CUTOVER)).all()
    assert (reserve["date"] >= pd.Timestamp(ksn.RESERVE_CUTOVER)).all()
    assert len(discovery) > 0 and len(reserve) > 0


def test_prereg_precedes_reserve_read(tmp_path, monkeypatch):
    """Order test: every reserve-slice re-mine call must happen strictly
    after every phase-1 (discovery) pre-registration add_claim call."""
    _seed_escalated_claim(tmp_path, 1, parent_delta=-8.0)
    df = _synthetic_two_slice_frame(bump_reserve=8.0)
    call_order: list[str] = []

    real_add_claim = cl.add_claim
    real_remine = ksn.remine_player_cell
    remine_calls = {"n": 0}

    def spy_add_claim(claim, base_dir=None):
        if claim.get("lifecycle") == "family_pass":
            call_order.append("prereg")
        return real_add_claim(claim, base_dir=base_dir)

    def spy_remine(df_, player_id, condition):
        # First call per cell is always phase-1 discovery re-mine, second is
        # phase-2 reserve re-mine (run_stage_b's own two-phase loop order).
        remine_calls["n"] += 1
        tag = "discovery_mine" if remine_calls["n"] == 1 else "reserve_mine"
        call_order.append(tag)
        return real_remine(df_, player_id, condition)

    monkeypatch.setattr(cl, "add_claim", spy_add_claim)
    monkeypatch.setattr(ksn, "remine_player_cell", spy_remine)
    ksb.run_stage_b(base_dir=tmp_path, source=df)

    assert "prereg" in call_order and "reserve_mine" in call_order
    last_prereg = max(i for i, tag in enumerate(call_order) if tag == "prereg")
    first_reserve = min(i for i, tag in enumerate(call_order) if tag == "reserve_mine")
    assert last_prereg < first_reserve


def test_same_sign_replication_marks_replicated(tmp_path):
    _seed_escalated_claim(tmp_path, 1, parent_delta=-8.0)
    df = _synthetic_two_slice_frame(bump_reserve=8.0)  # reserve gap holds, same sign
    out = ksb.run_stage_b(base_dir=tmp_path, source=df)
    assert out["preregistered"] >= 1
    assert out["replicated"] >= 1
    assert out["failed_replication"] == 0

    claims = cl.query(sport="nba", base_dir=tmp_path)
    assert (claims["lifecycle"] == "replicated").any()


def test_opposite_sign_reserve_marks_failed_replication(tmp_path):
    _seed_escalated_claim(tmp_path, 1, parent_delta=-8.0)
    df = _synthetic_two_slice_frame(bump_reserve=-8.0)  # reserve flips sign -> fail
    out = ksb.run_stage_b(base_dir=tmp_path, source=df)
    assert out["preregistered"] >= 1
    assert out["replicated"] == 0
    assert out["failed_replication"] >= 1

    claims = cl.query(sport="nba", base_dir=tmp_path)
    assert (claims["lifecycle"] == "failed_replication").any()


def test_meta_claim_ledgered_and_idempotent(tmp_path):
    first_id = ksb.ledger_reserve_discipline_meta(base_dir=tmp_path)
    assert first_id is not None
    second_id = ksb.ledger_reserve_discipline_meta(base_dir=tmp_path)
    assert second_id is None  # already present -- no duplicate journal add
    claims = cl.query(sport="nba", base_dir=tmp_path)
    metas = claims[claims["claim_id"] == first_id]
    assert len(metas) == 1
    assert json.loads(metas.iloc[0]["review_json"]).get("judge") == "fable"


def test_idempotent_rerun_does_not_reprocess_already_screened_prereg(tmp_path):
    _seed_escalated_claim(tmp_path, 1, parent_delta=-8.0)
    df = _synthetic_two_slice_frame(bump_reserve=8.0)
    first = ksb.run_stage_b(base_dir=tmp_path, source=df)
    second = ksb.run_stage_b(base_dir=tmp_path, source=df)
    # Escalated cell is still found both runs (lifecycle stays escalation_screened
    # on the parent), so re-mining/pre-registration recurs -- but the ledger
    # itself never loses the first run's replicated/failed_replication marks.
    assert first["preregistered"] == second["preregistered"]
    claims = cl.query(sport="nba", base_dir=tmp_path)
    assert (claims["lifecycle"].isin(["replicated", "failed_replication"])).any()
