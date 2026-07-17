"""Per-file tests for mlb_injury_recency_claims (depth-wave-1, lane 2).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_injury_recency_claims.py -q

Acceptance criteria:
  1. build_snapshot computes days_since_latest vs the CORPUS max game_date
     (not today) and n_facts per subject.
  2. min_sample floor (n_facts) excludes below-floor subjects from both
     rankings, counted in n_excluded_below_floor, never dropped silently.
  3. both emitted claims independently re-verify via claims_validator.py
     (VERIFIED, zero mismatch) -- the real cross-module check.
  4. caveats are present and non-empty on every claim; edge_claimed False.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import mlb_injury_recency_claims as mirc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_facts() -> pd.DataFrame:
    # subject A: 3 facts, latest 2025-06-10 (most recent -> days_since_latest=0)
    # subject B: 2 facts, latest 2025-06-05 (5 days back)
    # subject C: 1 fact (below MIN_N_FACTS=2 floor)
    return pd.DataFrame({
        "fact_kind": ["lineup_status"] * 6,
        "sport": ["mlb"] * 6,
        "subject_id": ["A", "A", "A", "B", "B", "C"],
        "game_date": [
            "2025-06-01", "2025-06-08", "2025-06-10",
            "2025-06-01", "2025-06-05",
            "2025-06-09",
        ],
        "value_text": ["x"] * 6,
        "source": ["src"] * 6,
        "availability_ts": ["2025-06-10T00:00:00Z"] * 6,
        "confidence": [0.6] * 6,
    })


def test_build_snapshot_uses_corpus_max_not_today(tmp_path, monkeypatch):
    monkeypatch.setattr(mirc, "_SOURCE", tmp_path / "facts.parquet")
    monkeypatch.setattr(mirc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(mirc, "_SNAPSHOT_OUT", tmp_path / "snapshot.parquet")
    _fixture_facts().to_parquet(mirc._SOURCE)

    _, snapshot = mirc.build_snapshot()
    rows = dict(zip(snapshot["subject_id"], snapshot["days_since_latest"]))
    # corpus max game_date is 2025-06-10 (subject A's latest fact)
    assert rows["A"] == 0
    assert rows["B"] == 5
    counts = dict(zip(snapshot["subject_id"], snapshot["n_facts"]))
    assert counts == {"A": 3, "B": 2, "C": 1}


def test_min_sample_floor_excludes_single_fact_subject(tmp_path, monkeypatch):
    monkeypatch.setattr(mirc, "_SOURCE", tmp_path / "facts.parquet")
    monkeypatch.setattr(mirc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(mirc, "_SNAPSHOT_OUT", tmp_path / "snapshot.parquet")
    monkeypatch.setattr(mirc, "_CLAIMS_OUT", tmp_path / "claims.jsonl")
    monkeypatch.setattr(mirc, "REPO_ROOT", tmp_path.parent)
    _fixture_facts().to_parquet(mirc._SOURCE)

    claims = mirc.build_ranking_claims()
    for claim in claims:
        ranked_ids = {r["subject_id"] for r in claim["ranking"]}
        assert "C" not in ranked_ids  # n_facts=1 < floor 2
        assert ranked_ids == {"A", "B"}
        assert claim["n_excluded_below_floor"] == 1
        assert claim["n_considered"] == 3
        assert claim["edge_claimed"] is False
        assert len(claim["caveats"]) > 0


def test_recency_and_volume_ranking_order(tmp_path, monkeypatch):
    monkeypatch.setattr(mirc, "_SOURCE", tmp_path / "facts.parquet")
    monkeypatch.setattr(mirc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(mirc, "_SNAPSHOT_OUT", tmp_path / "snapshot.parquet")
    monkeypatch.setattr(mirc, "_CLAIMS_OUT", tmp_path / "claims.jsonl")
    monkeypatch.setattr(mirc, "REPO_ROOT", tmp_path.parent)
    _fixture_facts().to_parquet(mirc._SOURCE)

    recency_claim, volume_claim = mirc.build_ranking_claims()
    # recency: ascending days_since_latest -> A (0) ranks above B (5)
    assert [r["subject_id"] for r in recency_claim["ranking"]] == ["A", "B"]
    # volume: descending n_facts -> A (3) ranks above B (2)
    assert [r["subject_id"] for r in volume_claim["ranking"]] == ["A", "B"]


def test_real_claims_independently_verify():
    """Cross-module check against the REAL on-disk parquet -- proves the
    emitted rankings are independently reproducible by claims_validator,
    not just self-consistent."""
    claims = mirc.build_ranking_claims()
    assert len(claims) == 2
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", verdict.reason
