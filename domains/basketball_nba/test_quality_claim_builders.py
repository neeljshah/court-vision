"""Per-file pytest for quality_claims_snapshot.py / quality_claim_builders.py
(the claims-provenance-contract fix: criteria.formula now recomputable).

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_quality_claim_builders.py -q

NEVER run the full suite (freezes the box).
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.quality_claim_builders import build_gate_claim, build_ranking_claim
from domains.basketball_nba.quality_claims_snapshot import build_pillar_formula, write_pillar_snapshot
from scripts.platformkit.intel_validation.safe_formula import evaluate_formula


def _synthetic_ranking_df() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [1, 2, 3],
        "player_name": ["A", "B", "C"],
        "games": [70, 65, 60],
        "coverage": [1.0, 1.0, 0.85],
        "pillar_EFFICIENCY": [0.9, 0.5, 0.7],
        "pillar_DIFFICULTY": [0.8, 0.4, 0.6],
        "shooter_quality_v1": [0.86, 0.46, 0.66],
    })


WEIGHTS = {"EFFICIENCY": 0.6, "DIFFICULTY": 0.4}


def test_build_pillar_formula_matches_manual_weighted_sum():
    formula = build_pillar_formula(WEIGHTS)
    assert formula == "0.6*pillar_EFFICIENCY + 0.4*pillar_DIFFICULTY"


def test_write_pillar_snapshot_then_validator_grammar_recomputes_exact_value(tmp_path, monkeypatch):
    """The real recomputability check: safe_formula.evaluate_formula (the
    SAME whitelist grammar claims_validator.py uses, zero import of this
    producer) must reproduce the claimed value exactly from the snapshot."""
    import domains.basketball_nba.quality_claims_snapshot as snap_mod
    monkeypatch.setattr(snap_mod, "_SNAPSHOT_DIR", tmp_path)

    df = _synthetic_ranking_df()
    path_str = write_pillar_snapshot(df, WEIGHTS, "shooter")
    written = pd.read_parquet(path_str)

    formula = build_pillar_formula(WEIGHTS)
    recomputed = evaluate_formula(formula, written)
    # coverage==1.0 rows (A, B): fixed-weight sum must equal the real score
    manual_full_coverage = 0.6 * df["pillar_EFFICIENCY"] + 0.4 * df["pillar_DIFFICULTY"]
    assert recomputed.iloc[0] == pytest.approx(manual_full_coverage.iloc[0])
    assert recomputed.iloc[1] == pytest.approx(manual_full_coverage.iloc[1])
    assert recomputed.iloc[0] == pytest.approx(df["shooter_quality_v1"].iloc[0])
    assert recomputed.iloc[1] == pytest.approx(df["shooter_quality_v1"].iloc[1])


def test_write_pillar_snapshot_only_carries_declared_columns(tmp_path, monkeypatch):
    """Snapshot must be a flat table with no leaked nested/atlas columns --
    exactly player_id/player_name/games/coverage + one pillar_<P> per weight."""
    import domains.basketball_nba.quality_claims_snapshot as snap_mod
    monkeypatch.setattr(snap_mod, "_SNAPSHOT_DIR", tmp_path)

    df = _synthetic_ranking_df()
    path_str = write_pillar_snapshot(df, WEIGHTS, "shooter")
    written = pd.read_parquet(path_str)
    assert set(written.columns) == {"player_id", "player_name", "games", "coverage",
                                     "pillar_EFFICIENCY", "pillar_DIFFICULTY"}


def test_build_ranking_claim_excludes_below_coverage_floor_honestly(tmp_path, monkeypatch):
    import domains.basketball_nba.quality_claims_snapshot as snap_mod
    monkeypatch.setattr(snap_mod, "_SNAPSHOT_DIR", tmp_path)

    df = _synthetic_ranking_df()
    claim = build_ranking_claim(
        "test_claim", "test question?", WEIGHTS, df, "shooter_quality_v1",
        ellis_rank=-1, curry_rank=1, n_qualifying=3, source_files=["dummy.parquet"],
        extra_caveat="test caveat", computed_at="2026-01-01T00:00:00+00:00",
        index_name="shooter", season="2024-25",
    )
    assert claim["criteria"]["min_sample"] == {"coverage": 1.0}
    # 1 of 3 synthetic rows has coverage=0.85 -- must be counted, never silently dropped
    assert claim["n_excluded_below_floor"] == 1
    assert claim["criteria"]["formula"] == "0.6*pillar_EFFICIENCY + 0.4*pillar_DIFFICULTY"
    assert claim["criteria"]["window"] == "2024-25"


class _FakeGate:
    verdict = "REJECT_NAIVE_STAYS_CANONICAL"
    mean_rho_shooter = 0.268
    mean_rho_naive = 0.4044
    bootstrap = {"mean_delta": -0.1354, "ci_lo": -0.2198, "ci_hi": -0.0566, "n_boot_effective": 2000}
    sign_holds_folds = 0
    n_folds = 3
    per_cutoff = []
    replication = None


def test_build_gate_claim_stays_unverifiable_by_construction_no_formula():
    """The gate claim must NEVER carry criteria.formula (there is no row-wise/
    aggregate expression for a paired-bootstrap CI) -- this is the documented,
    honest UNVERIFIABLE contract, not an oversight to silently patch over."""
    claim = build_gate_claim(_FakeGate(), "2026-01-01T00:00:00+00:00")
    assert "formula" not in claim["criteria"]
    assert claim["kind"] == "gate_verdict"
    assert "verdict_file" in claim
    assert any("PROVENANCE" in c for c in claim["caveats"])
    # underlying numbers must pass through verbatim, never altered by this lane
    assert claim["verdict"] == "REJECT_NAIVE_STAYS_CANONICAL"
    assert claim["mean_rho_shooter_quality_v1"] == 0.268
