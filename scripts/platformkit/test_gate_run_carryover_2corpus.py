"""Per-file test for scripts.platformkit.gate_run_carryover_2corpus.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_gate_run_carryover_2corpus.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit import gate_run_carryover_2corpus as G
from scripts.platformkit.interaction_factory import runner as IFR


def _fit(effect, p, n=500):
    return {"effect": effect, "p": p, "n": n, "term": "fa:fb"}


def test_combined_verdict_rule():
    # same sign, both clear the bar -> SURVIVES_BOTH_CORPORA
    assert G.combined_verdict(_fit(0.02, 0.001), _fit(0.03, 0.002)) == "SURVIVES_BOTH_CORPORA"
    # only one clears the bar -> SURVIVES_ONE_CORPUS (single-fold lift, not a ship)
    assert G.combined_verdict(_fit(0.02, 0.001), _fit(0.01, 0.60)) == "SURVIVES_ONE_CORPUS"
    # sign flip, even if both nominally significant -> not a true replication
    assert G.combined_verdict(_fit(0.02, 0.001), _fit(-0.02, 0.001)) == "SURVIVES_ONE_CORPUS"
    # neither clears the bar -> NULL_BOTH (the expected, honest result)
    assert G.combined_verdict(_fit(0.01, 0.6), _fit(-0.01, 0.7)) == "NULL_BOTH"
    # either corpus unbuildable -> NOT_TESTABLE
    assert G.combined_verdict(None, _fit(0.02, 0.001)) == "NOT_TESTABLE"
    assert G.combined_verdict(_fit(0.02, 0.001), None) == "NOT_TESTABLE"


def test_alpha_is_flat_bonferroni_k1():
    assert G.K_DECLARED == 1
    assert abs(G.ALPHA - 0.05) < 1e-12  # eps_eff(0.05, 1) == 0.05, a single declared test


def _synthetic_nba_asof(season: str, n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "game_id": [f"G{season}_{i:04d}" for i in range(n)],
        "season": season,
        "heavy_min_load_diff_asof": rng.normal(0, 20, n),
        "rest_days_diff_asof": rng.normal(0, 1, n),
        "home_win": rng.integers(0, 2, n).astype(float),
    })


def test_gate_sport_runs_real_fit_and_writes_idempotent_ledger_rows(tmp_path, monkeypatch):
    """Uses the REAL runner._fit_candidate (no reimplemented fit) on two tiny
    synthetic corpora, monkeypatching only the games.parquet + Elo merge that
    build_nba_boxdetail_frame pulls in (so the test needs no real on-disk data)."""
    import domains.basketball_nba.asof_ast_rate_eval as EVAL

    def fake_build_candidate_frame(games=None, asof=None, feat_col=None):
        rng = np.random.default_rng(0)
        out = asof[["game_id", feat_col, "home_win"]].copy()
        out["p_base"] = np.clip(rng.normal(0.5, 0.1, len(out)), 0.05, 0.95)  # needs real variance, not a constant
        out["date"] = pd.RangeIndex(len(out))
        return out.sort_values("date").reset_index(drop=True)

    monkeypatch.setattr(EVAL, "build_candidate_frame", fake_build_candidate_frame)

    ledger = tmp_path / "ledger.jsonl"
    build_a = G.IFR.build_nba_boxdetail_frame
    frame_a = {"frame": build_a(G.NBA_ATTRS, _synthetic_nba_asof("2023-24", seed=1)),
               "cluster": "game_id", "corpus": "carryover_asof[2023-24]", "kind": "logit", "covariate": "p_base"}
    frame_b = {"frame": build_a(G.NBA_ATTRS, _synthetic_nba_asof("2024-25", seed=2)),
               "cluster": "game_id", "corpus": "carryover_asof[2024-25]", "kind": "logit", "covariate": "p_base"}

    res = G.gate_sport(G.NBA_TEMPLATE, "2023-24", frame_a, "2024-25", frame_b, ledger_path=ledger)
    assert res["verdict"] in ("SURVIVES_BOTH_CORPORA", "SURVIVES_ONE_CORPUS", "NULL_BOTH")
    rows = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert len(rows) == 2
    assert {r["corpus"] for r in rows} == {"2023-24", "2024-25"}
    assert all(r["candidate_id"].startswith(G.NBA_TEMPLATE) for r in rows)

    # re-run with the SAME corpora -> idempotent, no duplicate rows appended.
    G.gate_sport(G.NBA_TEMPLATE, "2023-24", frame_a, "2024-25", frame_b, ledger_path=ledger)
    rows_after = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert len(rows_after) == 2


def test_unbuildable_corpus_is_not_testable_never_crashes(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    res = G.gate_sport(G.MLB_TEMPLATE, "2023", None, "2024", None, ledger_path=ledger)
    assert res["verdict"] == "NOT_TESTABLE"
    rows = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert all(r["verdict"] == IFR.NOT_TESTABLE for r in rows)
    assert all(r["n"] == 0 and r["effect"] is None for r in rows)
