"""Per-file pytest for replay_shipped_indices.py.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/reprocess/clients/test_replay_shipped_indices.py -q

NEVER run the full suite (freezes the box).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.reprocess.clients.replay_shipped_indices import (
    REGISTRY,
    ReprocessClient,
    run_all_clients,
    run_client,
)


def _synthetic_rows() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    eid = 0
    for corpus in ("corpusA", "corpusB"):
        for i in range(60):
            truth_p = rng.uniform(0.2, 0.8)
            outcome = int(rng.uniform() < truth_p)
            rows.append({
                "corpus_id": corpus,
                "fold_id": f"fold{i % 3}",
                "event_id": f"e{eid}",
                "p_variant": min(max(truth_p + rng.normal(0, 0.02), 0.01), 0.99),
                "p_base": min(max(truth_p + rng.normal(0, 0.10), 0.01), 0.99),
                "outcome": outcome,
            })
            eid += 1
    return pd.DataFrame(rows)


def test_real_registry_wnba_layer_is_unavailable():
    """The WNBA anchored blend must honestly report UNAVAILABLE -- its
    per-row scores were never persisted."""
    results = run_all_clients()
    assert len(results) == len(REGISTRY) == 7
    by_name = {r["client"]: r for r in results}
    r = by_name["wnba_anchored_linescore_blend"]
    assert r["status"] == "UNAVAILABLE"
    assert "re-running the gate" in r["reason"].lower() or "RE-RUNNING THE GATE" in r["reason"]


def test_registry_positional_weight_and_elo_refresh_replay_and_match():
    """The two schema-compatible wave-45 clients (rho per-fold, brier
    per-candidate-corpus) replay through the harness and match their
    committed verdicts within tolerance."""
    results = run_all_clients()
    by_name = {r["client"]: r for r in results}

    pw = by_name["nba_positional_weight"]
    assert pw["status"] == "RAN"
    assert pw["matched"] is True
    assert pw["max_abs_diff"] <= 1e-6

    elo = by_name["wnba_elo_refresh"]
    assert elo["status"] == "RAN"
    assert elo["matched"] is True
    assert elo["max_abs_diff"] <= 1e-6


def test_registry_umpire_totals_gate_replays_via_rmse_metric():
    """wave-47 gap closure: mlb_umpire_totals_gate now RUNS (was UNAVAILABLE)
    via the harness's new metric=rmse path -- column relabel + fold_id
    derived with the gate's own BURN_IN/N_FOLDS constants, no re-scoring,
    per-fold RMSE matches the committed verdict exactly."""
    results = run_all_clients()
    by_name = {r["client"]: r for r in results}
    ump = by_name["mlb_umpire_totals_gate"]
    assert ump["status"] == "RAN"
    assert ump["matched"] is True
    assert ump["max_abs_diff"] <= 1e-6
    assert set(ump["per_fold_diffs"]) == {"fold0", "fold1", "fold2"}


def test_registry_schema_mismatches_are_honest_unavailable():
    """The two ingame_hypothesis layers must never be coerced -- still
    UNAVAILABLE with a reason (re-checked wave-47: require re-running gate
    machinery to reach the committed per-row scores, not a field_paths
    rename), never a fabricated RAN result."""
    results = run_all_clients()
    by_name = {r["client"]: r for r in results}
    for name in (
        "nba_ingame_hypothesis_hot_night",
        "nba_ingame_hypothesis_scheme_fit",
    ):
        r = by_name[name]
        assert r["status"] == "UNAVAILABLE", f"{name} should be UNAVAILABLE, got {r}"
        assert r["reason"]


def test_registry_tennis_h3_playstyle_replays_and_matches():
    """wave-h3-h0-export gap closure: tennis_h3_playstyle now RUNS (was
    UNAVAILABLE) once the gate's export carries H0's own detail-model
    prediction as p_base -- per-fold Brier delta matches the committed
    verdict (data/frontend/ingame/playstyle_gate_verdict.json) within
    tolerance, never a fabricated match."""
    results = run_all_clients()
    by_name = {r["client"]: r for r in results}
    r = by_name["tennis_h3_playstyle"]
    assert r["status"] == "RAN"
    assert r["matched"] is True
    assert r["max_abs_diff"] <= 1e-6
    assert set(r["per_fold_diffs"]) == {"fold0", "fold1", "fold2"}


def test_synthetic_client_matches_committed_verdict(tmp_path):
    """A synthetic client with rows_source available replays through the
    harness and matches a committed verdict built from the identical rows."""
    from scripts.platformkit.reprocess.reprocess_harness import run_harness, verdict_to_dict

    df = _synthetic_rows()
    committed_verdict = verdict_to_dict(run_harness(df, metric="brier"))
    committed_path = tmp_path / "committed.json"
    committed_path.write_text(json.dumps(committed_verdict), encoding="ascii")

    client = ReprocessClient(
        name="synthetic_test_client",
        metric="brier",
        committed_verdict_path=committed_path,
        tolerance=1e-6,
        rows_source=lambda: _synthetic_rows(),
    )
    result = run_client(client)
    assert result["status"] == "RAN"
    assert result["matched"] is True
    assert result["max_abs_diff"] < 1e-6


def test_synthetic_client_missing_committed_path_is_unavailable(tmp_path):
    client = ReprocessClient(
        name="synthetic_missing_path",
        metric="brier",
        committed_verdict_path=tmp_path / "does_not_exist.json",
        tolerance=1e-6,
        rows_source=lambda: _synthetic_rows(),
    )
    result = run_client(client)
    assert result["status"] == "UNAVAILABLE"
    assert "committed verdict path missing" in result["reason"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
