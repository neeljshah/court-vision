"""Per-file tests for intel_query.claims_coverage_report.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_claims_coverage_report.py -q

Acceptance criteria:
  1. build_coverage_report() groups VERIFIED claims by sport (leading
     claim_id token) then dimension (criteria.metric for ranking,
     gate_module for verdict), with rows/entities/floor/excluded/store/mtime
     per claim, matching wnba_claims/tennis_claims_v3's own on-disk shape.
  2. a MISMATCH claim never appears in any sport bucket (fixture-level).
  3. entities == n_considered - n_excluded_below_floor; rows == len(ranking)
     (may differ under a top-N cap -- both numbers must be present, never
     silently collapsed to one).
  4. grand_total sums every sport's totals exactly, and
     n_claim_source_pairs_discovered matches len(CLAIM_SOURCE_PAIRS).
  5. print_summary runs without raising on a real report (ASCII only).
  6. against the REAL repo claim stores (no monkeypatch): every sport this
     lane's wave-51 modules produced (mlb/nba/tennis/wnba/soccer) has at
     least one VERIFIED row, proving the automatic discovery actually
     covers the new stores end-to-end, not just a fixture.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_query import ask as ask_mod
from scripts.platformkit.intel_query import claims_coverage_report as ccr


def _ranking_claim(claim_id: str, metric: str, n_considered: int, n_excluded: int, ranking_len: int) -> dict:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "criteria": {"metric": metric, "min_sample": {"n": 10}},
        "ranking": [{"rank": i + 1, "player_name": f"P{i}", "value": 1.0, "n": 20} for i in range(ranking_len)],
        "source_files": ["data/fake/source.parquet"],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [],
    }


def _verdict_claim(claim_id: str, gate_module: str) -> dict:
    return {
        "claim_id": claim_id,
        "kind": "verdict",
        "gate_module": gate_module,
        "verdict": "REJECT",
        "computed_at": "2026-07-05T00:00:00+00:00",
    }


@pytest.fixture
def fixture_sources(tmp_path, monkeypatch):
    """Two sports (fixturesport_a, fixturesport_b) each with a VERIFIED
    ranking claim; fixturesport_a also has a top-N-capped ranking (rows <
    entities) plus a VERIFIED verdict claim; a MISMATCH ranking claim must
    never surface in any bucket."""
    claims_path = tmp_path / "claims.jsonl"
    validation_path = tmp_path / "validation.json"

    verified_full = _ranking_claim("fixturesport_a_full_metric", "full_metric", 100, 10, 90)
    verified_capped = _ranking_claim("fixturesport_a_capped_metric", "capped_metric", 200, 50, 50)
    verified_verdict = _verdict_claim("fixturesport_a_some_gate_verdict", "fixture gate module")
    verified_b = _ranking_claim("fixturesport_b_full_metric", "full_metric", 40, 0, 40)
    mismatch_row = _ranking_claim("fixturesport_a_mismatch_metric", "mismatch_metric", 10, 0, 10)

    with open(claims_path, "w", encoding="ascii") as f:
        for row in (verified_full, verified_capped, verified_verdict, verified_b, mismatch_row):
            f.write(json.dumps(row) + "\n")

    validation_summary = {
        "component": "fixture_validation",
        "n_claims": 5,
        "details": [
            {"claim_id": "fixturesport_a_full_metric", "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": "fixturesport_a_capped_metric", "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": "fixturesport_a_some_gate_verdict", "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": "fixturesport_b_full_metric", "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": "fixturesport_a_mismatch_metric", "verdict": "MISMATCH", "reason": "bad"},
        ],
    }
    validation_path.write_text(json.dumps(validation_summary), encoding="ascii")

    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))
    monkeypatch.setattr(ccr, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))
    return validation_path, claims_path


def test_groups_by_sport_then_dimension(fixture_sources):
    report = ccr.build_coverage_report()
    # sport = leading token before first "_" -> "fixturesport" for ALL fixture
    # claim_ids here (they share the prefix "fixturesport").
    assert set(report["sports"].keys()) == {"fixturesport"}
    assert "fixturesport" in report["sports"]
    dims = report["sports"]["fixturesport"]["dimensions"]
    assert "full_metric" in dims
    assert "capped_metric" in dims
    assert "fixture gate module" in dims


def test_mismatch_claim_never_appears(fixture_sources):
    report = ccr.build_coverage_report()
    all_claim_ids = {
        c["claim_id"]
        for sport in report["sports"].values()
        for dim in sport["dimensions"].values()
        for c in dim["claims"]
    }
    assert "fixturesport_a_mismatch_metric" not in all_claim_ids
    assert len(all_claim_ids) == 4


def test_rows_vs_entities_differ_under_topn_cap(fixture_sources):
    report = ccr.build_coverage_report()
    dims = report["sports"]["fixturesport"]["dimensions"]
    capped = dims["capped_metric"]["claims"][0]
    assert capped["entities"] == 200 - 50  # n_considered - n_excluded_below_floor
    assert capped["rows"] == 50  # top-N cap, rows < entities
    assert capped["entities"] > capped["rows"]

    full = dims["full_metric"]["claims"]
    a_full = next(c for c in full if c["claim_id"] == "fixturesport_a_full_metric")
    assert a_full["entities"] == a_full["rows"] == 90


def test_verdict_claim_has_no_rows_or_entities(fixture_sources):
    report = ccr.build_coverage_report()
    verdict_claim = report["sports"]["fixturesport"]["dimensions"]["fixture gate module"]["claims"][0]
    assert verdict_claim["kind"] == "verdict"
    assert verdict_claim["rows"] is None
    assert verdict_claim["entities"] is None
    assert verdict_claim["floor"] is None


def test_grand_total_sums_every_sport(fixture_sources):
    report = ccr.build_coverage_report()
    gt = report["grand_total"]
    manual_rows = sum(s["totals"]["rows"] for s in report["sports"].values())
    manual_entities = sum(s["totals"]["entities"] for s in report["sports"].values())
    assert gt["rows"] == manual_rows
    assert gt["entities"] == manual_entities
    assert gt["n_claims"] == 4
    assert gt["n_claim_source_pairs_discovered"] == len(ccr.CLAIM_SOURCE_PAIRS)


def test_print_summary_runs_without_raising(fixture_sources, capsys):
    report = ccr.build_coverage_report()
    ccr.print_summary(report)
    captured = capsys.readouterr()
    assert "GRAND TOTAL" in captured.out
    assert "fixturesport" in captured.out
    # ASCII-only stdout rail
    captured.out.encode("ascii")


def test_write_report_roundtrips_to_json(fixture_sources, tmp_path):
    report = ccr.build_coverage_report()
    output_path = tmp_path / "coverage_report.json"
    ccr.write_report(report, output_path)
    reloaded = json.loads(output_path.read_text(encoding="ascii"))
    assert reloaded["grand_total"] == report["grand_total"]


# --- against the REAL repo stores (no monkeypatch) --------------------------

def test_real_repo_stores_cover_every_wave51_sport():
    """Proves the automatic discovery in ask.CLAIM_SOURCE_PAIRS actually
    reaches every sport this lane's wave-51 modules produced, not just a
    fixture -- the acceptance bar for item (1)/(2) of this lane's brief."""
    report = ccr.build_coverage_report()
    for sport in ("mlb", "nba", "tennis", "wnba", "soccer"):
        assert sport in report["sports"], f"sport {sport!r} missing from real coverage report"
        assert report["sports"][sport]["totals"]["n_claims"] > 0

    gt = report["grand_total"]
    assert gt["n_claim_source_pairs_discovered"] >= 13  # every store this lane found on disk
    assert gt["n_claims"] > 0
