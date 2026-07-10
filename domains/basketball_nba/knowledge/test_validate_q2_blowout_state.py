"""Per-file test for knowledge.validate_q2_blowout_state. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_q2_blowout_state.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge import validate_q2_blowout_state as vq2


def _synthetic_tg(n_games=600, seed=7, extension_pts=0.0) -> pd.DataFrame:
    """q1_margin ~ N(0, 8) (wide enough to cross LEAD_EDGE=15 often); q2_margin
    follows a fixed AR(1) slope of the SAME magnitude for every game, plus an
    extra `extension_pts` (signed toward the q1 lead direction) added ONLY
    for |q1_margin|>=LEAD_EDGE -- injects the exact tail-vs-population-AR gap
    hypothesis (a) tests for."""
    rng = np.random.default_rng(seed)
    q1 = rng.normal(0, 8, n_games)
    ar_slope = -0.05
    extra = np.where(np.abs(q1) >= vq2.LEAD_EDGE, extension_pts * np.sign(q1), 0.0)
    q2 = ar_slope * q1 + extra + rng.normal(0, 6, n_games)
    corpus = np.where(np.arange(n_games) % 2 == 0, "c1", "c2")
    dates = pd.Timestamp("2024-01-01") + pd.to_timedelta(np.arange(n_games), unit="D")
    return pd.DataFrame({"corpus": corpus, "q1_margin": q1, "q2_margin": q2, "date": dates})


def test_q2_lead_extension_beyond_ar_detects_injected_extension():
    tg = _synthetic_tg(n_games=3000, extension_pts=5.0)
    r = vq2.q2_lead_extension_beyond_ar(tg)
    assert set(r) >= {"hypothesis", "verdict", "per_corpus", "note"}
    assert r["verdict"] == "REPLICATED"
    for stats in r["per_corpus"].values():
        assert stats["signed_resid_mean"] > 0  # extension injected -> positive signed residual


def test_q2_lead_extension_beyond_ar_null_on_flat_synthetic_data():
    tg = _synthetic_tg(n_games=1200, extension_pts=0.0)
    r = vq2.q2_lead_extension_beyond_ar(tg)
    assert r["verdict"] in {"NULL", "NOT_TESTABLE"}


def test_q2_lead_extension_not_testable_when_thin():
    tg = _synthetic_tg(n_games=20, extension_pts=3.0)
    r = vq2.q2_lead_extension_beyond_ar(tg)
    assert r["verdict"] == "NOT_TESTABLE"


def test_verdict_replicated_helper():
    assert vq2._verdict_replicated({"a": True, "b": True}) == "REPLICATED"
    assert vq2._verdict_replicated({"a": True, "b": False}) == "PARTIAL"
    assert vq2._verdict_replicated({"a": False, "b": False}) == "NULL"
    assert vq2._verdict_replicated({"a": None, "b": None}) == "NOT_TESTABLE"


def _synthetic_bench_frame(n=400, seed=3, q1_coef=0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    abs_margin = rng.uniform(0, 40, n)
    q1_blowout = rng.uniform(0, 30, n)
    starter_minutes = 200.0 - 1.0 * abs_margin + q1_coef * q1_blowout + rng.normal(0, 10, n)
    dates = pd.Timestamp("2024-01-01") + pd.to_timedelta(np.arange(n), unit="D")
    return pd.DataFrame({"date": dates, "abs_margin": abs_margin, "q1_blowout": q1_blowout,
                          "starter_minutes": starter_minutes})


def test_q2_blowout_early_bench_deployment_detects_injected_negative_coef():
    d = _synthetic_bench_frame(n=800, q1_coef=-0.5)
    r = vq2.q2_blowout_early_bench_deployment(d)
    assert set(r) >= {"hypothesis", "verdict", "per_half", "note"}
    assert r["verdict"] == "REPLICATED"


def test_q2_blowout_early_bench_deployment_null_when_no_q1_effect():
    d = _synthetic_bench_frame(n=800, q1_coef=0.0)
    r = vq2.q2_blowout_early_bench_deployment(d)
    assert r["verdict"] in {"NULL", "PARTIAL"}


def test_q2_blowout_early_bench_deployment_not_testable_when_thin():
    d = _synthetic_bench_frame(n=10, q1_coef=-0.5)
    r = vq2.q2_blowout_early_bench_deployment(d)
    assert r["verdict"] == "NOT_TESTABLE"


def test_q2_foul_pace_state_interaction_not_testable():
    r = vq2.q2_foul_pace_state_interaction()
    assert r["verdict"] == "NOT_TESTABLE"
    assert "quarter" in r["note"].lower()


def test_run_writes_three_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    tg = _synthetic_tg(n_games=800, extension_pts=2.0)
    d = _synthetic_bench_frame(n=400, q1_coef=-0.5)
    monkeypatch.setattr(vq2, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vq2, "load_all_corpora", lambda: tg)
    monkeypatch.setattr(vq2, "_q1_lead_join_frame", lambda: d)
    rows = vq2.run()
    assert len(rows) == 3
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3
