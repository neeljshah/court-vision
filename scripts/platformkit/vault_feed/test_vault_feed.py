"""Per-file tests for vault_feed staging generators. Run with:
    python -m pytest scripts/platformkit/vault_feed/test_vault_feed.py -q
"""
import json
from pathlib import Path

import pytest

from scripts.platformkit.vault_feed.claims_dossier_gen import (
    CLAIM_ID_TO_FILE,
    CLAIMS_DIR,
    ENTITY_KEY_NAME_FIELD,
    _slugify,
    build_dossier_sections,
)
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


def test_slugify_strips_windows_illegal_characters():
    """Regression guard: a raw fallback id like nba_fit_ingredient_claims's
    team_posgroup value "ATL|BIG" previously crashed write_text with
    OSError (pipe is illegal in a Windows filename). _slugify must strip
    every Windows-illegal filename character, not just spaces/dots/quotes."""
    assert _slugify("ATL|BIG") == "atlbig"
    assert _slugify('Weird<>:"/\\|?*Name') == "weirdname"
    assert _slugify("Cal Raleigh") == "cal_raleigh"


def test_dossier_gen_full_population_no_top_n_cap(tmp_path):
    """FULL POPULATION: a fixture with 80 VERIFIED rows for one claim (well
    past any historical top-50 cap) must all appear as dossier lines --
    proves this generator applies no cap of its own."""
    validation = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "details": [{"claim_id": "nba_ts_pct_top50_2024-25", "verdict": "VERIFIED"}],
    }
    (tmp_path / "validation.json").write_text(json.dumps(validation), encoding="utf-8")
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    ranking = [
        {"rank": i, "player_id": i, "player_name": f"Player{i}", "value": 0.5}
        for i in range(1, 81)
    ]
    (claims_dir / "nba_shooting_claims.jsonl").write_text(
        json.dumps({
            "claim_id": "nba_ts_pct_top50_2024-25", "kind": "ranking",
            "criteria": {"metric": "ts_pct", "value_precision": 4, "entity_key": "player_id"},
            "source_files": ["data/x.parquet"],
            "ranking": ranking,
        }) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    counts = build_dossier_sections(
        validation_path=tmp_path / "validation.json",
        claims_dir=claims_dir,
        out_dir=out_dir,
    )
    assert len(counts) == 80
    assert all(n == 1 for n in counts.values())


def test_claim_id_to_file_prefixes_match_real_on_disk_claim_ids():
    """Registry-completeness guard: every prefix key in CLAIM_ID_TO_FILE must
    actually match at least one real claim_id inside the jsonl file it maps
    to (catches the exact starve-by-typo bug: "nba_shooting_" never matched
    any of nba_shooting_claims.jsonl's 20 per-dimension claim_ids, e.g.
    "nba_ts_pct_top50_2024-25", silently zeroing every NBA player dossier)."""
    if not CLAIMS_DIR.exists():
        pytest.skip("real intel_claims cache not present in this environment")
    fname_to_ids: dict[str, set[str]] = {}
    for fname in set(CLAIM_ID_TO_FILE.values()):
        fpath = CLAIMS_DIR / fname
        if not fpath.exists():
            continue
        ids = set()
        for line in fpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                ids.add(json.loads(line)["claim_id"])
        fname_to_ids[fname] = ids

    dead_prefixes = []
    for prefix, fname in CLAIM_ID_TO_FILE.items():
        ids = fname_to_ids.get(fname)
        if ids is None:
            continue  # file absent in this environment -- not a prefix bug
        if not any(cid.startswith(prefix) for cid in ids):
            dead_prefixes.append((prefix, fname))
    assert dead_prefixes == [], f"prefixes matching zero real claim_ids: {dead_prefixes}"


def test_new_entity_keys_registered_for_fullpop_sources():
    """PROGRAM v3 item 4: the basketball/wnba/fit claim stores introduce new
    entity_key values (official_id, pid, team_posgroup) -- they must be
    registered so their rows are not silently skipped by the
    `entity_key not in ENTITY_KEY_NAME_FIELD` guard."""
    for key in ("official_id", "pid", "team_posgroup", "player_id", "team"):
        assert key in ENTITY_KEY_NAME_FIELD


def test_dossier_gen_covers_new_entity_key_shapes(tmp_path):
    """End-to-end fixture covering the three new entity_key shapes
    (official_id / pid / team_posgroup) through build_dossier_sections,
    each with a raw-id fallback name (no *_name field) to exercise
    _slugify on a realistic team_posgroup-style value."""
    validation = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "details": [
            {"claim_id": "wnba_referee_crew_foul_rate_full_2026", "verdict": "VERIFIED"},
            {"claim_id": "nba_fit_archetype_profile_current", "verdict": "VERIFIED"},
            {"claim_id": "nba_fit_role_vacancy_by_team_posgroup_current", "verdict": "VERIFIED"},
        ],
    }
    (tmp_path / "validation.json").write_text(json.dumps(validation), encoding="utf-8")
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "wnba_claims.jsonl").write_text(
        json.dumps({
            "claim_id": "wnba_referee_crew_foul_rate_full_2026", "kind": "ranking",
            "criteria": {"metric": "fouls_per_game", "value_precision": 4, "entity_key": "official_id"},
            "source_files": ["data/x.parquet"],
            "ranking": [{"rank": 1, "official_id": "100", "official_name": "Vet Official", "value": 16.2}],
        }) + "\n",
        encoding="utf-8",
    )
    (claims_dir / "nba_fit_ingredient_claims.jsonl").write_text(
        json.dumps({
            "claim_id": "nba_fit_archetype_profile_current", "kind": "ranking",
            "criteria": {"metric": "usage_pct", "value_precision": 4, "entity_key": "pid"},
            "source_files": ["data/y.parquet"],
            "ranking": [{"rank": 1, "pid": 999, "player_name": "Test Archetype Player", "value": 0.3}],
        }) + "\n"
        + json.dumps({
            "claim_id": "nba_fit_role_vacancy_by_team_posgroup_current", "kind": "ranking",
            "criteria": {"metric": "vacancy_share", "value_precision": 4, "entity_key": "team_posgroup"},
            "source_files": ["data/z.parquet"],
            "ranking": [{"rank": 1, "team_posgroup": "ATL|BIG", "value": 0.85}],
        }) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    counts = build_dossier_sections(
        validation_path=tmp_path / "validation.json",
        claims_dir=claims_dir,
        out_dir=out_dir,
    )
    assert counts == {"vet_official": 1, "test_archetype_player": 1, "atlbig": 1}
    # the pipe-containing raw id must not crash the write and must sanitize cleanly
    assert (out_dir / "atlbig.md").exists()


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
