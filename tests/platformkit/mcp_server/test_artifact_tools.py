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
    # Real writer shape (scripts/platformkit/analytics_showcase/market_strength_atlas.py):
    # per-sport nesting under "sports", not top-level top/bottom/tracking_mae keys.
    _write(tmp_path, "scripts/platformkit/analytics_showcase/out/market_strength_atlas.json",
           {"as_of": "2026-09-01", "label": "DESCRIPTIVE_ONLY",
            "sports": {"basketball_nba": {
                "top_5": [{"team": "OKC", "rating": 1728.1}],
                "bottom_5": [{"team": "WAS", "rating": 1274.3}],
                "eval_scores": {"mean_absolute_tracking_error": 0.0917}}}})
    env = tools.strength_atlas({}, tmp_path)
    assert env["status"] == "ok"
    assert env["DESCRIPTIVE_ONLY"] == "DESCRIPTIVE_ONLY"
    assert env["tracking_mae"] == {"basketball_nba": 0.0917}
    assert env["top_ratings"]["basketball_nba"][0]["team"] == "OKC"
    assert env["bottom_ratings"]["basketball_nba"][0]["team"] == "WAS"


def test_strength_atlas_fails_closed_when_sports_data_absent(tmp_path):
    # Artifact present and parseable but missing the required per-sport payload
    # must never come back status=ok with null fields (the bug this guards).
    _write(tmp_path, "scripts/platformkit/analytics_showcase/out/market_strength_atlas.json",
           {"as_of": "2026-09-01", "label": "DESCRIPTIVE_ONLY"})
    env = tools.strength_atlas({}, tmp_path)
    assert env["status"] == "no_data"
    assert "top_ratings" not in env and "note" in env


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


def test_mechanism_exposure_reads_game_sheets_key(tmp_path):
    # S71/F2: the real producer writes the per-game list under "game_sheets";
    # reading only games/rows made all 1,317 sheets unaddressable by game_id.
    _write(tmp_path, "scripts/platformkit/analytics_showcase/out/mechanism_exposure.json",
           {"as_of": "2026-05-24",
            "game_sheets": [{"game_id": "2025-10-21-GSW-LAL-0", "exposures": [{"n": 3}]}]})
    env = tools.mechanism_exposure({"game_id": "2025-10-21-GSW-LAL-0"}, tmp_path)
    assert env["status"] == "ok"
    assert env["exposure_sheets"][0]["exposures"] == [{"n": 3}]
    assert tools.mechanism_exposure({"game_id": "nope"}, tmp_path)["status"] == "no_data"


def test_execution_status_passes_the_artifacts_own_status_through(tmp_path):
    # S71/F3: an execution readout over an empty ledger writes status no_data /
    # verdict INSUFFICIENT -- serving that as ok invented a health it lacks.
    _write(tmp_path, "data/frontend/analytics/execution_status.json",
           {"as_of": "2026-09-02T14:10:16+00:00", "status": "no_data",
            "verdict": "INSUFFICIENT", "n_records": 20, "n_open": 18})
    env = tools.execution_status({}, tmp_path)
    assert env["status"] == "no_data"
    assert "INSUFFICIENT" in env["note"]
    _write(tmp_path, "data/frontend/analytics/execution_status.json",
           {"as_of": "2026-09-02T14:10:16+00:00", "status": "ok", "n_records": 20})
    assert tools.execution_status({}, tmp_path)["status"] == "ok"


def test_finalize_stamps_staleness_only_on_ok_envelopes_naming_a_real_file(tmp_path):
    # S71/F1: the shared finaliser every handler passes through.
    _write(tmp_path, "a.json", {"x": 1})
    ok = tools.finalize({"status": "ok", "source_artifact": "a.json",
                         "as_of": "2020-01-01T00:00:00+00:00"}, tmp_path)
    assert ok["staleness_days"] > 2000 and ok["staleness_days_source"] == "as_of"
    mtime = tools.finalize({"status": "ok", "source_artifact": "a.json",
                            "as_of": "2026-09-02T14:10:16+00:00 (no rows)"}, tmp_path)
    assert mtime["staleness_days_source"] == "source_artifact_mtime"
    for env in ({"status": "refused", "source_artifact": "a.json"},
                {"status": "not_supported", "source_artifact": "a.json"},
                {"status": "ok", "source_artifact": "absent.json", "as_of": "2020-01-01"}):
        assert "staleness_days" not in tools.finalize(dict(env), tmp_path)
