"""Per-file test for the LIVE-EDGE evidence dossier generator (lane EVIDENCE)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.platformkit.live_edge.evidence.dossier import generate, scan_banned


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path
    le = root / "data/omni/live_edge"

    promote = le / "tail_calib/promote"
    promote.mkdir(parents=True)
    pd.DataFrame(
        {"claim_id": ["a", "b", "c"], "mean_pooled": [0.05, -0.02, 0.10], "survivor": [True, False, True]}
    ).to_parquet(promote / "promote_table.parquet")

    replay = le / "replay"
    (replay / "apex").mkdir(parents=True)
    pd.DataFrame(
        {"claim_id": ["x", "y"], "verdict": ["NULL", "IMPROVES_BOTH_CORPORA"]}
    ).to_parquet(replay / "full_ledger_results.parquet")
    pd.DataFrame(
        {"claim_id": ["p1", "p2"], "verdict": ["INSUFFICIENT_DATA", "IMPROVES_BOTH_CORPORA"]}
    ).to_parquet(replay / "apex/placebo_results.parquet")
    pd.DataFrame(
        {"grain": ["team", "player", "team"], "mde_binding": [1.2, 0.3, float("inf")]}
    ).to_parquet(replay / "apex/mde_report.parquet")

    (le / "compose").mkdir(parents=True)
    (le / "compose/COMPOSE_REPORT.md").write_text(
        "## fam_a\n\nverdict: **MODEL_FAMILY_ARTIFACT_ONLY**\n\ntext\n", encoding="utf-8"
    )

    (le / "combine/foul_minutes").mkdir(parents=True)
    (le / "combine/foul_minutes/report.md").write_text("null result\n", encoding="utf-8")

    (le / "shadow").mkdir(parents=True)
    (le / "shadow/2026-01-01.jsonl").write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")

    (le / "freshness").mkdir(parents=True)
    (le / "freshness/sla.jsonl").write_text('{"s": 1}\n', encoding="utf-8")

    (le / "autoloop").mkdir(parents=True)
    (le / "autoloop/cycle_log.jsonl").write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "picked_up": 5, "results_rows_total": 3, "tested": 1}) + "\n",
        encoding="utf-8",
    )

    (le / "bet_map").mkdir(parents=True)
    (le / "bet_map/COVERAGE_REPORT.md").write_text(
        "## Uncovered bet shapes (backlog)\n\n- shape_one\n- shape_two\n\n## Next section\n\nother\n",
        encoding="utf-8",
    )

    (le / "evidence").mkdir(parents=True)
    (le / "evidence/rulings.json").write_text(
        json.dumps({"rulings": [{
            "id": "width_correction_tier1",
            "ts": "2026-07-14T20:45:00Z",
            "ruled_by": "fable",
            "statement": "Width-correction class promoted TIER-1.",
            "evidence": [
                {"corpus": "nba_player_points", "artifact": "a.md",
                 "class_delta": 0.0321, "ci": [0.0224, 0.0418], "p": 2.2e-10,
                 "entities": "131/159", "commit": "49e1d184"},
                {"corpus": "mlb_team_runs", "artifact": "b.md",
                 "class_delta": 0.0391, "ci": [0.0334, 0.0447], "p": 1.5e-14,
                 "entities": "26/30", "commit": "c20ca67b"},
            ],
            "binding_caveats": ["calibration-vs-own-baseline, NOT edge-vs-market"],
        }]}),
        encoding="utf-8",
    )
    return root


def test_generate_is_deterministic(fixture_root: Path):
    out1 = generate(fixture_root)
    out2 = generate(fixture_root)
    assert out1 == out2
    assert scan_banned(out1) == []


def test_sections_present(fixture_root: Path):
    text = generate(fixture_root)
    for heading in [
        "(a) Validated findings",
        "(b) Honest nulls",
        "(c) Gate integrity",
        "(d) Machinery inventory",
        "(e) Live operations",
        "(f) NOT-YET-CLAIMABLE",
    ]:
        assert heading in text


def test_reads_real_fixture_numbers(fixture_root: Path):
    text = generate(fixture_root)
    assert "shape_one, shape_two" in text
    assert "shadow conditioner rows on disk: 2" in text


def test_ruling_renders_tier1_in_section_a(fixture_root: Path):
    text = generate(fixture_root)
    assert "TIER-1" in text
    assert "mlb_team_runs" in text and "+0.0391" in text
    assert "calibration-vs-own-baseline, NOT edge-vs-market" in text
    # tier-1 landed -> replication-missing line replaced by edge-vs-market line
    assert "Independent-corpus replication" not in text
    assert "Edge-vs-market" in text


def test_no_ruling_falls_back_to_tier2(fixture_root: Path):
    (fixture_root / "data/omni/live_edge/evidence/rulings.json").unlink()
    text = generate(fixture_root)
    assert "TIER-2 PROVISIONAL" in text
    assert "2/3 entities survive" in text
    assert "Independent-corpus replication" in text


def test_refuses_banned_tokens_directly():
    assert scan_banned("this text is clean") == []
    assert scan_banned("we have a real roi here") != []
    assert scan_banned("costs $5") != []
    assert scan_banned('"edge_claimed": true') != []
    assert scan_banned("the old +18.38 number") != []
