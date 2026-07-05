"""Per-file tests for tennis_claims_v4 (lane tennis-persist, program v3).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_claims_v4.py -q

Acceptance criteria:
  1. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED for a real on-disk metric.
  2. FULL POPULATION: no top-N truncation -- ranked count == qualifying count.
  3. Below-floor players are counted in n_excluded_below_floor, never
     silently dropped.
  4. Every claim carries the CLOSED-CLASS guard caveat (playstyle/surface
     predictive gates stay closed; this module never re-opens them).
  5. build_all_claims honestly reports a missing surface as
     dims_corpus_absent, never silently omitted.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import tennis_claims_v4 as tcv4
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_surface_splits() -> pd.DataFrame:
    """4 players, Hard + Clay only (Grass absent), varying n_matches so the
    floor (30) both includes and excludes rows."""
    return pd.DataFrame({
        "player_id": [1, 2, 3, 4, 1, 2],
        "surface": ["Hard", "Hard", "Hard", "Hard", "Clay", "Clay"],
        "n_matches": [50, 40, 29, 100, 35, 10],  # player 3 (Hard) and player 2 (Clay) below floor=30
        "ace_rate": [0.15, 0.12, 0.30, 0.08, 0.20, 0.25],
        "first_serve_in_pct": [0.60, 0.62, 0.70, 0.55, 0.65, 0.68],
        "double_fault_rate": [0.04, 0.03, 0.02, 0.06, 0.05, 0.01],
        "as_of": ["2025-12-17"] * 6,
        "corpus_id": ["sackmann_atp_matches_parquet"] * 6,
    })


def test_build_ranking_claim_full_population_no_top_n_cap(tmp_path, monkeypatch):
    # Isolate snapshot writes: build_ranking_claim -> build_surface_snapshot
    # writes a parquet under out_dir, and the claim's source_files path is
    # made repo-relative via _rel(REPO_ROOT). Route BOTH to tmp_path so this
    # fixture run never touches the real data/cache/intel_claims/ snapshots
    # that claims_validator re-reads from disk on every validation run.
    monkeypatch.setattr(tcv4, "REPO_ROOT", tmp_path.parent)
    df = _fixture_surface_splits()
    metric = tcv4.METRICS[0]  # ace_rate
    claim = tcv4.build_ranking_claim(df, metric, "Hard", out_dir=tmp_path)

    # 4 Hard rows considered, player 3 (n_matches=29) excluded below floor=30.
    assert claim["n_considered"] == 4
    assert claim["n_excluded_below_floor"] == 1
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying == 3
    # Top ranked by ace_rate desc among qualifiers {1: 0.15, 2: 0.12, 4: 0.08} -> player 1.
    assert claim["ranking"][0]["player_id"] == 1
    assert claim["ranking"][0]["value"] == 0.15


def test_build_ranking_claim_below_floor_excluded_not_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(tcv4, "REPO_ROOT", tmp_path.parent)
    df = _fixture_surface_splits()
    metric = tcv4.METRICS[0]  # ace_rate
    claim = tcv4.build_ranking_claim(df, metric, "Clay", out_dir=tmp_path)

    # 2 Clay rows considered, player 2 (n_matches=10) excluded below floor=30.
    assert claim["n_considered"] == 2
    assert claim["n_excluded_below_floor"] == 1
    assert len(claim["ranking"]) == 1
    assert claim["ranking"][0]["player_id"] == 1


def test_every_claim_carries_closed_class_guard_caveat(tmp_path, monkeypatch):
    monkeypatch.setattr(tcv4, "REPO_ROOT", tmp_path.parent)
    df = _fixture_surface_splits()
    metric = tcv4.METRICS[0]
    claim = tcv4.build_ranking_claim(df, metric, "Hard", out_dir=tmp_path)
    assert any("CLOSED-CLASS GUARD" in c for c in claim["caveats"])
    assert any("does NOT re-open" in c for c in claim["caveats"])


def test_build_all_claims_reports_missing_surface_as_corpus_absent(tmp_path, monkeypatch):
    """Grass has zero rows in the fixture -- must appear in dims_corpus_absent
    for every metric, never silently omitted with no trace."""
    # build_all_claims -> build_ranking_claim also writes snapshots; route
    # explicitly to tmp_path (out_dir=) so this fixture run never touches the
    # real data/cache/intel_claims/ snapshots.
    monkeypatch.setattr(tcv4, "REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr(tcv4, "_load_surface_splits", lambda: _fixture_surface_splits())
    claims, absent = tcv4.build_all_claims(out_dir=tmp_path)

    for metric in tcv4.METRICS:
        assert f"{metric.column}.grass" in absent
    # Hard + Clay both present for every metric -> 3 metrics x 2 surfaces = 6 claims.
    assert len(claims) == 6
    assert len(absent) == 3


def test_real_ace_rate_hard_claim_independently_verifies_against_real_corpus():
    """Cross-module check against the REAL on-disk surface_splits.parquet --
    proves the emitted ranking is independently reproducible by
    claims_validator AND covers the full qualifying population (no top-N cap).
    Requires data/cache/tennis_atlas/surface_splits.parquet to exist on disk
    (built by domains/tennis/atlas_persist_layers.persist_surface_splits)."""
    if not tcv4._SURFACE_SPLITS_SRC.exists():
        import pytest
        pytest.skip("surface_splits.parquet not yet built on disk in this environment")

    df = tcv4._load_surface_splits()
    metric = tcv4.METRICS[0]  # ace_rate
    claim = tcv4.build_ranking_claim(df, metric, "Hard")
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
