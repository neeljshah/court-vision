"""tests/test_b2b_vet_v3_dnp.py — tier3-11b (loop 5) v3 DNP-aware probe tests.

5 tests:
1. include_dnp=True increases combined cohort row count over played-only.
2. DNP rows synthesised by the v3 probe carry all-zero targets.
3. DNP classification flows through from src/data/dnp_set.py unchanged.
4. probe_b2b_veteran_v3_dnp runs end-to-end on real holdout data
   (skip when production parquets are absent — fresh checkout).
5. WF fold sign consistency: when the probe runs and emits WF results,
   each fold's delta = adj - base must be deterministic on a fixed input.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ── 1: include_dnp adds rows in the v3 probe data path ──────────────────────


def test_include_dnp_adds_rows_to_cohort(tmp_path, monkeypatch):
    """v3 uses dnp_set.load_dnp_rows directly. Loading with DNPs available
    yields strictly more rows than loading without (empty parquet)."""
    from src.data import dnp_set

    # First: a tmp_path with no parquet → loader returns empty.
    monkeypatch.setattr(dnp_set, "_DEFAULT_PATH",
                        str(tmp_path / "missing.parquet"))
    monkeypatch.setattr(dnp_set, "_CSV_FALLBACK",
                        str(tmp_path / "missing.csv"))
    monkeypatch.setattr(dnp_set, "_JSONL_FALLBACK",
                        str(tmp_path / "missing.jsonl"))
    dnp_set.reset_cache()
    df_empty = dnp_set.load_dnp_rows()
    assert hasattr(df_empty, "empty")
    n_empty = 0 if df_empty.empty else len(df_empty)
    assert n_empty == 0

    # Now: write a tiny parquet with 3 DNP rows; loader returns 3.
    import pandas as pd
    p = tmp_path / "dnp_rows.parquet"
    pd.DataFrame([
        {"game_id": "0099900001", "game_date": "9999-01-15",
         "season": "9999-00", "player_id": 2001, "player": "T. Test",
         "team": "ABC", "dnp_reason": "coach_decision",
         "dnp_comment": "DNP - Coach's Decision", "expected_to_play": True},
        {"game_id": "0099900001", "game_date": "9999-01-15",
         "season": "9999-00", "player_id": 2002, "player": "I. Hurt",
         "team": "ABC", "dnp_reason": "injury",
         "dnp_comment": "Inactive - Injury", "expected_to_play": True},
        {"game_id": "0099900002", "game_date": "9999-01-16",
         "season": "9999-00", "player_id": 2003, "player": "N. Cap",
         "team": "XYZ", "dnp_reason": "inactive",
         "dnp_comment": "Inactive - G League", "expected_to_play": True},
    ]).to_parquet(p, index=False)
    monkeypatch.setattr(dnp_set, "_DEFAULT_PATH", str(p))
    dnp_set.reset_cache()
    df = dnp_set.load_dnp_rows()
    assert len(df) == 3


# ── 2: synthesised DNP rows carry all-zero targets ──────────────────────────


def test_dnp_synthesised_rows_have_zero_targets():
    """v3's _enrich_dnp_rows must emit target_<stat>=0 for every stat."""
    from scripts.probe_b2b_veteran_v3_dnp import _enrich_dnp_rows
    from src.prediction.prop_pergame import STATS, build_rest_travel

    rest_travel = build_rest_travel()
    fake_dnp = [
        {"game_id": "0099900001", "game_date": "2025-01-15",
         "season": "2024-25", "player_id": 2544, "player": "L. James",
         "team": "LAL", "dnp_reason": "injury",
         "expected_to_play": True},
    ]
    out = _enrich_dnp_rows(fake_dnp, age_lookup={}, rest_travel=rest_travel)
    assert len(out) == 1
    r = out[0]
    for stat in STATS:
        assert r[f"target_{stat}"] == 0.0
    assert r["player_id"] == 2544
    assert r["dnp_reason"] == "injury"
    assert "date" in r and r["date"]


# ── 3: DNP classification matches dnp_set ───────────────────────────────────


def test_dnp_classification_matches_dnp_set(tmp_path, monkeypatch):
    """Reasons emitted by the v3 enrichment must be the SAME strings as
    those persisted by aggregate_dnp_rows → dnp_set.load_dnp_rows."""
    import pandas as pd

    from scripts.probe_b2b_veteran_v3_dnp import _enrich_dnp_rows
    from src.data import dnp_set
    from src.prediction.prop_pergame import build_rest_travel

    p = tmp_path / "dnp_rows.parquet"
    pd.DataFrame([
        {"game_id": "0099900001", "game_date": "2025-01-15",
         "season": "2024-25", "player_id": 2544, "player": "L. James",
         "team": "LAL", "dnp_reason": "coach_decision",
         "dnp_comment": "DNP - CD", "expected_to_play": True},
        {"game_id": "0099900001", "game_date": "2025-01-15",
         "season": "2024-25", "player_id": 201939, "player": "S. Curry",
         "team": "GSW", "dnp_reason": "injury",
         "dnp_comment": "Inactive - Ankle", "expected_to_play": True},
    ]).to_parquet(p, index=False)

    monkeypatch.setattr(dnp_set, "_DEFAULT_PATH", str(p))
    dnp_set.reset_cache()
    recs = dnp_set.load_dnp_rows().to_dict("records")
    rest_travel = build_rest_travel()
    enriched = _enrich_dnp_rows(recs, age_lookup={}, rest_travel=rest_travel)
    assert len(enriched) == 2
    reasons = {r["dnp_reason"] for r in enriched}
    assert reasons == {"coach_decision", "injury"}


# ── 4: end-to-end smoke run on real data (skip if missing) ──────────────────


def test_probe_runs_end_to_end_on_real_data(tmp_path):
    """Run probe_b2b_veteran_v3_dnp.py via subprocess on the real holdout.

    Skips when production parquets are absent (fresh-checkout safety).
    A successful run writes b2b_veteran_v3_dnp.md; we assert exit code 0
    and the report file exists with the expected sections.
    """
    real_parquet = os.path.join(PROJECT_DIR, "data", "dnp_rows.parquet")
    rest_travel = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
    models_dir = os.path.join(PROJECT_DIR, "data", "models")
    if not (os.path.exists(real_parquet) and os.path.exists(rest_travel)
            and os.path.isdir(models_dir)):
        pytest.skip("real DNP / rest_travel / models artefacts not present")
    # Skip when production model files are missing (CI / fresh checkout).
    have_models = any(fn.startswith("props_pg_") and fn.endswith(".json")
                      for fn in os.listdir(models_dir))
    if not have_models:
        pytest.skip("no props_pg_*.json models present")

    out_md = os.path.join(PROJECT_DIR, "scripts", "_results",
                          "b2b_veteran_v3_dnp.md")
    # Use --no-sweep + --factor 0.85 to keep the run under ~2 minutes.
    proc = subprocess.run(
        [sys.executable,
         os.path.join(PROJECT_DIR, "scripts", "probe_b2b_veteran_v3_dnp.py"),
         "--no-sweep", "--factor", "0.85"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert proc.returncode == 0, \
        f"probe exited non-zero:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert os.path.exists(out_md), \
        f"report not written; stdout tail:\n{proc.stdout[-2000:]}"
    text = open(out_md, encoding="utf-8").read()
    assert "DNP RATE" in text
    assert "Cohort sizes" in text or "cohort sizes" in text.lower()


# ── 5: WF fold sign consistency on a fabricated input ──────────────────────


def test_wf_fold_sign_consistency_deterministic():
    """apply_b2b_veteran_shrink + _mae must produce the same delta sign on
    repeated calls with the same input. Guards against any future
    accidental in-place numpy mutation that would corrupt WF folds."""
    import numpy as np

    from scripts.probe_b2b_veteran import _mae, apply_b2b_veteran_shrink

    rng = np.random.default_rng(seed=42)
    n = 60
    pred = rng.uniform(5, 25, size=n)
    y = pred * rng.uniform(0.7, 1.1, size=n)
    ages = np.full(n, 34.0)
    rows = [{"is_b2b": 1.0} for _ in range(n)]

    # Run twice; delta must be identical.
    adj_a, n_aff_a = apply_b2b_veteran_shrink(pred, rows, ages, 0.85)
    adj_b, n_aff_b = apply_b2b_veteran_shrink(pred, rows, ages, 0.85)
    assert n_aff_a == n_aff_b == n
    delta_a = _mae(adj_a, y) - _mae(pred, y)
    delta_b = _mae(adj_b, y) - _mae(pred, y)
    assert delta_a == pytest.approx(delta_b, rel=0, abs=1e-12)
    # And the un-adjusted pred is not corrupted by the shrink call.
    assert pred[0] == pytest.approx(adj_a[0] / 0.85, rel=0, abs=1e-9)
