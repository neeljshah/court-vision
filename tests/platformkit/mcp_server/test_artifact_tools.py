"""Fixture tests for read-only MCP artifact resolvers."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.mcp_server import artifact_tools as tools


def _write(root: Path, rel: str, value: object) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_strength_atlas_returns_artifact_and_descriptive_flag(tmp_path):
    _write(tmp_path, "scripts/platformkit/analytics_showcase/out/market_strength_atlas.json",
           {"as_of": "2026-09-01", "top": ["A"], "bottom": ["B"],
            "tracking_mae": 1.2, "DESCRIPTIVE_ONLY": True})
    env = tools.strength_atlas({}, tmp_path)
    assert env["status"] == "ok"
    assert env["DESCRIPTIVE_ONLY"] is True
    assert env["tracking_mae"] == 1.2


def test_mechanism_exposure_filters_game_and_preserves_ledger_fields(tmp_path):
    _write(tmp_path, "scripts/platformkit/analytics_showcase/out/mechanism_exposure.json",
           {"generated_at": "2026-09-01", "games": [{"game_id": "g1", "effect": 0.2,
                                                        "n": 12, "p": 0.04}]})
    env = tools.mechanism_exposure({"game_id": "g1"}, tmp_path)
    assert env["status"] == "ok"
    assert env["exposure_sheets"][0] == {"game_id": "g1", "effect": 0.2, "n": 12, "p": 0.04}


def test_missing_artifacts_fail_closed(tmp_path):
    for resolver in (tools.strength_atlas, tools.mechanism_exposure, tools.tracking_program_status,
                     tools.harness_health, tools.execution_status):
        env = resolver({}, tmp_path)
        assert env["status"] == "no_data"
        assert "source_artifact" in env and "as_of" in env


def test_tracking_harness_and_execution_artifacts_are_returned_verbatim(tmp_path):
    _write(tmp_path, "docs/evidence/tracking/nba_packet.json",
           {"as_of": "2026-09-01", "sport": "nba", "stage_table": [], "passes": 0})
    _write(tmp_path, "data/tracking_reports/tennis/latest.json",
           {"generated_at": "2026-09-01", "verdict": "empty"})
    _write(tmp_path, "data/frontend/analytics/harness_health.json",
           {"as_of": "2026-09-01", "golden": "FAIL", "retro_correction_survivors": "0/85", "K": 85})
    _write(tmp_path, "data/frontend/analytics/execution_status.json",
           {"as_of": "2026-09-01", "mlb_event_reactive": "recorded", "paper_units": 4})
    tracking = tools.tracking_program_status({}, tmp_path)
    assert tracking["status"] == "ok" and len(tracking["artifacts"]) == 2
    assert tools.harness_health({}, tmp_path)["multiplicity_ledger_K"] == 85
    execution = tools.execution_status({}, tmp_path)
    assert execution["paper_ledger_counts"]["paper_units"] == 4 and execution["units_only"] is True
