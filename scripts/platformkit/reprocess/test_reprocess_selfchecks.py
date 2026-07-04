"""Per-file pytest for selfcheck_elo.py / selfcheck_positional.py (mission
spine 2, wave-33 gap closure PART C).

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/reprocess/test_reprocess_selfchecks.py -q

Skips if the real committed data files are not present in this checkout
(these self-checks are inherently real-data-only -- no synthetic fixture
would prove anything about a REAL match).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.platformkit.reprocess import selfcheck_elo, selfcheck_positional

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ELO_VERDICT = _REPO_ROOT / "data" / "domains" / "wnba" / "elo_refresh_verdict.json"
_ELO_SCOREBOARD = _REPO_ROOT / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
_PW_VERDICT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "positional_weight_verdict.json"
_PW_ROWS = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "positional_weight_rows.parquet"


@pytest.mark.skipif(not (_ELO_VERDICT.exists() and _ELO_SCOREBOARD.exists()),
                     reason="real wnba elo corpus not present in this checkout")
def test_selfcheck_elo_matches_committed_verdict_within_tolerance():
    """Closes the wave-33 BLOCKED_SCHEMA_MISMATCH gap: elo_refresh_gate_io
    now exports true harness-schema rows via the SAME cold-start replay
    paths the committed gate used, and replaying them through the harness
    reproduces elo_refresh_verdict.json's brier_base/brier_cand within 1e-6."""
    payload = selfcheck_elo.run_selfcheck()
    assert payload["status"] == "MATCHED"
    assert payload["matched"] is True
    assert payload["max_abs_diff"] <= selfcheck_elo.TOL
    assert len(payload["fields_compared"]) > 0
    assert payload["edge_claimed"] is False


@pytest.mark.skipif(not (_PW_VERDICT.exists() and _PW_ROWS.exists()),
                     reason="real nba positional-weight corpus not present in this checkout")
def test_selfcheck_positional_matches_committed_verdict_within_tolerance():
    """positional_weight_rows.parquet's p_variant is now scored with each
    fold's own leave-one-fold-out weights (reused from the gate's own
    per_fold output, not re-fit), so replaying through reprocess_harness
    metric=rho reproduces per_fold[i].overall.rho_positional/rho_naive
    within 1e-6."""
    payload = selfcheck_positional.run_selfcheck()
    assert payload["status"] == "MATCHED"
    assert payload["matched"] is True
    assert payload["naive_matched"] is True
    assert payload["positional_matched"] is True
    assert payload["max_abs_diff_naive"] <= selfcheck_positional.TOL
    assert payload["max_abs_diff_positional"] <= selfcheck_positional.TOL
    assert payload["edge_claimed"] is False


@pytest.mark.skipif(not (_PW_VERDICT.exists() and _PW_ROWS.exists()),
                     reason="real nba positional-weight corpus not present in this checkout")
def test_selfcheck_positional_cluster_id_present_in_rows():
    """positional_weight_rows.parquet must carry cluster_id (=player_id) for
    the harness's rho-metric paired cluster bootstrap."""
    import pandas as pd
    df = pd.read_parquet(_PW_ROWS)
    assert "cluster_id" in df.columns
    assert df["cluster_id"].notna().all()
