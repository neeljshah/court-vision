"""tests/test_explanation_engine.py — explanation engine regression set."""
from __future__ import annotations

import time

import pytest

from src.live.explanation_engine import ExplanationEngine


def _bet(**over):
    base = {
        "game_id": "0042500315", "player_id": 1, "name": "Jokic",
        "stat": "pts", "side": "over", "line": 24.5, "book": "pin",
        "odds": -110, "projected_final": 32.0, "ev": 0.07, "kelly": 0.12,
    }
    base.update(over)
    return base


def _row(**over):
    base = {
        "player_id": 1, "stat": "pts",
        "projection_source": "endQ2_head+residual_head_endq2+defender_matchup",
        "foul_factor": 0.95, "blow_factor": 1.0,
        "heat_check_shrinkage": 0.85,
        "matchup_reason": "matchup_applied:Jokic vs AGordon (0.92x, 6.2 poss)",
    }
    base.update(over)
    return base


def _snap(**over):
    base = {
        "game_id": "0042500315", "game_status": "LIVE", "period": 4,
        "clock": "PT05M30S",
        "players": [{"player_id": 1, "name": "Jokic", "pf": 4, "min": 30}],
    }
    base.update(over)
    return base


def test_explain_returns_projection_path_section():
    eng = ExplanationEngine()
    out = eng.explain_bet(_bet(), snapshot=_snap(), projection_row=_row())
    kinds = [s["kind"] for s in out["sections"]]
    assert "projection_path" in kinds
    proj = next(s for s in out["sections"] if s["kind"] == "projection_path")
    # Should pretty-print the chain
    assert "endQ2 LightGBM head" in proj["body"]
    assert "endQ2 residual head" in proj["body"]
    assert "defender matchup" in proj["body"]


def test_explain_returns_pbp_context_after_ingest():
    eng = ExplanationEngine()
    for i in range(3):
        eng.ingest_pbp({
            "game_id": "0042500315", "topic": "pbp.foul",
            "period": 4, "clock": f"PT05M{i:02d}S",
            "description": "P.FOUL", "player_id": 1, "player_name": "Jokic",
            "ts": time.time(),
        })
    out = eng.explain_bet(_bet())
    kinds = [s["kind"] for s in out["sections"]]
    assert "pbp_context" in kinds
    body = next(s for s in out["sections"] if s["kind"] == "pbp_context")["body"]
    assert "Jokic" in body
    assert "foul" in body


def test_explain_returns_line_movement_section():
    eng = ExplanationEngine()
    for i, val in enumerate([26.5, 26.0, 25.5, 25.0, 24.5]):
        eng.ingest_line_tick(
            game_id="0042500315", player_id=1, stat="pts",
            book="pin", line=val, over_price=-110, under_price=-110,
            ts=time.time() - (5 - i) * 30,
        )
    eng.ingest_line_tick(
        game_id="0042500315", player_id=1, stat="pts",
        book="fd", line=26.5, over_price=-110, under_price=-110,
    )
    out = eng.explain_bet(_bet())
    kinds = [s["kind"] for s in out["sections"]]
    assert "line_movement" in kinds
    body = next(s for s in out["sections"] if s["kind"] == "line_movement")["body"]
    assert "pin" in body and "fd" in body
    assert "spread across books" in body   # >= 0.5 gap triggers callout


def test_explain_returns_foul_pressure_when_player_in_trouble():
    eng = ExplanationEngine()
    out = eng.explain_bet(_bet(), snapshot=_snap(), projection_row=_row())
    kinds = [s["kind"] for s in out["sections"]]
    assert "foul_pressure" in kinds
    body = next(s for s in out["sections"] if s["kind"] == "foul_pressure")["body"]
    assert "Jokic" in body
    assert "4 PF" in body or "foul" in body.lower()


def test_summary_includes_basic_bet_fields():
    eng = ExplanationEngine()
    out = eng.explain_bet(_bet())
    assert "Jokic" in out["summary"]
    assert "PTS OVER 24.5" in out["summary"]
    assert "pin" in out["summary"]
    assert "EV +7.0%" in out["summary"]


def test_pbp_buffer_is_bounded():
    eng = ExplanationEngine(pbp_window=3)
    for i in range(10):
        eng.ingest_pbp({
            "game_id": "g", "topic": "pbp.foul",
            "period": 4, "clock": f"x{i}", "description": "x",
            "player_id": 1, "player_name": "X",
        })
    out = eng.explain_bet(_bet(game_id="g"))
    body = next((s for s in out["sections"] if s["kind"] == "pbp_context"),
                {"body": ""})["body"]
    # Only 3 events should be retained.
    assert body.count("foul") <= 3


def test_missing_metadata_does_not_crash():
    eng = ExplanationEngine()
    out = eng.explain_bet({"game_id": "g", "stat": "pts", "side": "over",
                           "line": 0, "book": "pin", "odds": -110})
    assert "sections" in out
    assert "summary" in out
