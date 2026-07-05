"""Per-file tests for vault_feed staging generators. Run with:
    python -m pytest scripts/platformkit/vault_feed/test_vault_feed.py -q
"""
import json
from pathlib import Path

import pytest

from scripts.platformkit.vault_feed.claims_dossier_gen import build_dossier_sections
from scripts.platformkit.vault_feed.atlas_graph_gen import build_atlas_hubs

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_dossier_gen_fail_open_on_missing_validation(tmp_path):
    counts = build_dossier_sections(
        validation_path=tmp_path / "missing.json",
        claims_dir=tmp_path,
        out_dir=tmp_path / "out",
    )
    assert counts == {}
    assert not (tmp_path / "out").exists()


def test_dossier_gen_excludes_non_verified_and_non_ranking(tmp_path):
    validation = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "details": [
            {"claim_id": "nba_shooting_x", "verdict": "VERIFIED"},
            {"claim_id": "nba_shooting_y", "verdict": "MISMATCH"},
            {"claim_id": "nba_quality_gate", "verdict": "VERIFIED"},
        ],
    }
    (tmp_path / "validation.json").write_text(json.dumps(validation), encoding="utf-8")
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "nba_shooting_claims.jsonl").write_text(
        json.dumps({
            "claim_id": "nba_shooting_x", "kind": "ranking",
            "criteria": {"metric": "ts_pct", "value_precision": 3, "entity_key": "player_id"},
            "source_files": ["data/x.parquet"],
            "ranking": [{"rank": 1, "player_name": "Test Player", "value": 0.611}],
        }) + "\n"
        + json.dumps({
            "claim_id": "nba_shooting_y", "kind": "ranking",
            "criteria": {"metric": "efg_pct", "value_precision": 3, "entity_key": "player_id"},
            "source_files": ["data/x.parquet"],
            "ranking": [{"rank": 1, "player_name": "Should Not Appear", "value": 0.5}],
        }) + "\n",
        encoding="utf-8",
    )
    (claims_dir / "nba_quality_claims.jsonl").write_text(
        json.dumps({"claim_id": "nba_quality_gate", "kind": "gate_verdict"}) + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    counts = build_dossier_sections(
        validation_path=tmp_path / "validation.json",
        claims_dir=claims_dir,
        out_dir=out_dir,
    )
    assert counts == {"test_player": 1}
    body = (out_dir / "test_player.md").read_text(encoding="utf-8")
    assert "nba_shooting_x" in body
    assert "validator=VERIFIED @ 2026-01-01T00:00:00+00:00" in body
    assert not (out_dir / "should_not_appear.md").exists()


def test_dossier_gen_renders_caveats_verbatim(tmp_path):
    caveat_text = "ooz_strike_rate is confounded by BATTER chase/whiff behavior."
    validation = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "details": [
            {"claim_id": "mlb_catcher_framing_top50_2022_2023", "verdict": "VERIFIED"},
        ],
    }
    (tmp_path / "validation.json").write_text(json.dumps(validation), encoding="utf-8")
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "catcher_framing_claims.jsonl").write_text(
        json.dumps({
            "claim_id": "mlb_catcher_framing_top50_2022_2023", "kind": "ranking",
            "criteria": {"metric": "ooz_strike_rate", "value_precision": 4, "entity_key": "catcher_id"},
            "source_files": ["data/cache/intel_claims/catcher_framing_snapshot.parquet"],
            "ranking": [{"rank": 1, "catcher_id": 663728, "catcher_name": "Cal Raleigh", "value": 0.3198}],
            "caveats": [caveat_text, "another caveat line"],
        }) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    counts = build_dossier_sections(
        validation_path=tmp_path / "validation.json",
        claims_dir=claims_dir,
        out_dir=out_dir,
    )
    assert counts == {"cal_raleigh": 1}
    body = (out_dir / "cal_raleigh.md").read_text(encoding="utf-8")
    assert caveat_text in body
    assert "another caveat line" in body
    assert "**Caveats:**" in body


def test_dossier_gen_idempotent_on_real_inputs():
    if not (REPO_ROOT / "data/frontend/ops/intel_claims_validation.json").exists():
        pytest.skip("real validation artifact not present in this environment")
    c1 = build_dossier_sections()
    c2 = build_dossier_sections()
    assert c1 == c2


def test_atlas_hub_basketball_and_generic_schema_both_parse(tmp_path):
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    (spec_dir / "basketball_truth_spec.json").write_text(json.dumps({
        "factors": [{"factor": "ts_pct", "pillar": "EFFICIENCY", "file": "x.parquet", "column": "c"}],
        "fallback_only_factors": [],
    }), encoding="utf-8")
    (spec_dir / "mlb_truth_spec.json").write_text(json.dumps({
        "dimensions": [
            {"name": "sp_ra", "aspect_group": "pitching_starter",
             "source_file": "y.parquet", "source_column": "c", "coverage": "100%"},
            {"name": "sp_tto", "aspect_group": "pitching_starter",
             "gap_source": "derivable elsewhere"},
        ],
    }), encoding="utf-8")

    out_dir = tmp_path / "out"
    counts = build_atlas_hubs(spec_dir=spec_dir, out_dir=out_dir)
    assert counts == {
        "basketball_nba_efficiency.md": 1,
        "mlb_pitching_starter.md": 2,
    }
    body = (out_dir / "mlb_pitching_starter.md").read_text(encoding="utf-8")
    assert "[[sp_ra]] `REAL`" in body
    assert "[[sp_tto]] `GAP`" in body


def test_atlas_hub_gen_fail_open_when_specs_absent(tmp_path):
    counts = build_atlas_hubs(spec_dir=tmp_path / "missing", out_dir=tmp_path / "out")
    assert counts == {}
    assert not (tmp_path / "out").exists()


def test_atlas_hub_gen_idempotent_on_real_inputs():
    if not (REPO_ROOT / "docs/research/intel-layer/basketball_truth_spec.json").exists():
        pytest.skip("real truth-spec docs not present in this environment")
    c1 = build_atlas_hubs()
    c2 = build_atlas_hubs()
    assert c1 == c2
