"""Per-file pytest for reprocess_harness.py.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/reprocess/test_reprocess_harness.py -q

NEVER run the full suite (freezes the box). All synthetic fixtures -- no
network, no real corpora (see reprocess_selfcheck.json / this task's report
for the real-data self-check attempt against the wave-30 composition gate).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.reprocess.reprocess_harness import (
    REQUIRED_COLS,
    SchemaError,
    load_rows,
    run_harness,
    verdict_to_dict,
    write_verdict,
)


def _synthetic_df(n_per_corpus: int, seed: int, variant_better: bool,
                   corpora=("corpusA", "corpusB"), n_folds: int = 3,
                   with_close: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    eid = 0
    for corpus in corpora:
        for i in range(n_per_corpus):
            fold = f"fold{i % n_folds}"
            truth_p = rng.uniform(0.2, 0.8)
            outcome = int(rng.uniform() < truth_p)
            if variant_better:
                p_variant = np.clip(truth_p + rng.normal(0, 0.05), 0.01, 0.99)
                p_base = np.clip(truth_p + rng.normal(0, 0.25), 0.01, 0.99)
            else:
                p_variant = np.clip(truth_p + rng.normal(0, 0.25), 0.01, 0.99)
                p_base = np.clip(truth_p + rng.normal(0, 0.05), 0.01, 0.99)
            row = {
                "corpus_id": corpus, "fold_id": fold, "event_id": f"e{eid}",
                "p_variant": float(p_variant), "p_base": float(p_base), "outcome": outcome,
            }
            if with_close:
                row["p_close"] = float(np.clip(truth_p + rng.normal(0, 0.1), 0.01, 0.99))
            rows.append(row)
            eid += 1
    return pd.DataFrame(rows)


def test_required_cols_constant_matches_contract():
    assert set(REQUIRED_COLS) == {"corpus_id", "fold_id", "event_id", "p_variant", "p_base", "outcome"}


def test_load_rows_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_rows(__import__("pathlib").Path("does_not_exist_xyz.parquet"))


def test_run_harness_fails_closed_on_missing_column():
    df = pd.DataFrame({"corpus_id": ["a"], "fold_id": ["f0"], "event_id": ["e0"]})
    with pytest.raises(SchemaError):
        run_harness(df)


def test_variant_clearly_better_shows_positive_delta_and_significant_dm():
    df = _synthetic_df(n_per_corpus=400, seed=1, variant_better=True)
    v = run_harness(df)
    pooled = v.pooled_diagnostic["vs_base"]
    assert pooled["delta"] > 0
    assert pooled["dm_p"] < 0.05
    for corpus_id, block in v.per_corpus.items():
        assert block["vs_base"]["delta"] > 0


def test_variant_clearly_worse_shows_negative_delta():
    df = _synthetic_df(n_per_corpus=400, seed=2, variant_better=False)
    v = run_harness(df)
    pooled = v.pooled_diagnostic["vs_base"]
    assert pooled["delta"] < 0


def test_corpora_are_never_pooled_for_per_corpus_verdict():
    df = _synthetic_df(n_per_corpus=200, seed=3, variant_better=True, corpora=("A", "B", "C"))
    v = run_harness(df)
    assert set(v.per_corpus.keys()) == {"A", "B", "C"}
    # pooled block exists only as a diagnostic, separate from per-corpus verdicts
    assert "DIAGNOSTIC ONLY" in v.pooled_diagnostic["note"]


def test_per_fold_signs_reported_per_corpus():
    df = _synthetic_df(n_per_corpus=300, seed=4, variant_better=True, n_folds=3)
    v = run_harness(df)
    for corpus_id, block in v.per_corpus.items():
        signs = block["per_fold_signs_vs_base"]
        assert len(signs) == 3
        assert all(s["sign"] in ("variant", "base", "tie") for s in signs)


def test_p_close_present_yields_calibration_label_not_edge():
    df = _synthetic_df(n_per_corpus=200, seed=5, variant_better=True, with_close=True)
    v = run_harness(df)
    assert v.has_close
    for corpus_id, block in v.per_corpus.items():
        assert "vs_close_calibration" in block
        assert block["vs_close_calibration"]["label"] == "CALIBRATION-vs-close, never an edge"
    assert "vs_close_calibration" in v.pooled_diagnostic


def test_p_close_absent_no_close_block():
    df = _synthetic_df(n_per_corpus=100, seed=6, variant_better=True, with_close=False)
    v = run_harness(df)
    assert not v.has_close
    for corpus_id, block in v.per_corpus.items():
        assert "vs_close_calibration" not in block


def test_edge_claimed_always_false_in_verdict_dict():
    df = _synthetic_df(n_per_corpus=100, seed=7, variant_better=True)
    v = run_harness(df)
    d = verdict_to_dict(v)
    assert d["edge_claimed"] is False


def test_load_rows_jsonl_roundtrip(tmp_path):
    df = _synthetic_df(n_per_corpus=20, seed=8, variant_better=True)
    p = tmp_path / "rows.jsonl"
    with open(p, "w", encoding="ascii") as f:
        for _, row in df.iterrows():
            f.write(json.dumps(row.to_dict()) + "\n")
    loaded = load_rows(p)
    assert len(loaded) == len(df)
    assert set(REQUIRED_COLS).issubset(loaded.columns)


def test_load_rows_parquet_roundtrip(tmp_path):
    df = _synthetic_df(n_per_corpus=20, seed=9, variant_better=True)
    p = tmp_path / "rows.parquet"
    df.to_parquet(p)
    loaded = load_rows(p)
    assert len(loaded) == len(df)


def test_load_rows_missing_required_column_raises(tmp_path):
    df = _synthetic_df(n_per_corpus=10, seed=10, variant_better=True).drop(columns=["outcome"])
    p = tmp_path / "bad.parquet"
    df.to_parquet(p)
    with pytest.raises(SchemaError):
        load_rows(p)


def test_write_verdict_round_trips_to_disk(tmp_path):
    df = _synthetic_df(n_per_corpus=50, seed=11, variant_better=True)
    v = run_harness(df)
    out = tmp_path / "verdict.json"
    payload = write_verdict(v, out)
    assert out.exists()
    reloaded = json.loads(out.read_text(encoding="ascii"))
    assert reloaded == payload
    assert reloaded["edge_claimed"] is False
    assert reloaded["component"] == "reprocess_harness"


def test_perfect_tie_delta_near_zero():
    rng = np.random.default_rng(42)
    n = 300
    outcome = rng.integers(0, 2, n)
    p = np.clip(rng.uniform(0.3, 0.7, n), 0.01, 0.99)
    df = pd.DataFrame({
        "corpus_id": ["A"] * n, "fold_id": [f"f{i % 3}" for i in range(n)],
        "event_id": [f"e{i}" for i in range(n)],
        "p_variant": p, "p_base": p, "outcome": outcome,
    })
    v = run_harness(df)
    assert v.per_corpus["A"]["vs_base"]["delta"] == pytest.approx(0.0, abs=1e-12)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_ELO_ROWS = _REPO_ROOT / "data" / "domains" / "wnba" / "elo_refresh_rows.parquet"
_PW_ROWS = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "positional_weight_rows.parquet"


@pytest.mark.skipif(not _ELO_ROWS.exists(), reason="real wnba corpus not present in this checkout")
def test_elo_refresh_rows_is_not_harness_shaped():
    """Pins the wave-32-selfcheck finding: elo_refresh_rows.parquet is raw
    game rows (single flat p_home_elo, no per-candidate probabilities), NOT
    the reprocess_harness pre-scored shape -- load_rows must fail closed
    rather than silently accept it. See
    data/domains/wnba/reprocess_selfcheck_elo.json for the full blocked note.
    """
    df = pd.read_parquet(_ELO_ROWS)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    assert missing, (
        "elo_refresh_rows.parquet unexpectedly gained harness columns -- "
        "re-run the selfcheck replay, do not assume this is still blocked"
    )
    with pytest.raises(SchemaError):
        load_rows(_ELO_ROWS)


@pytest.mark.skipif(not _PW_ROWS.exists(), reason="real nba corpus not present in this checkout")
def test_positional_weight_rows_replay_is_deterministic():
    """positional_weight_rows.parquet IS harness-shaped and replays through
    reprocess_harness mechanically, but its 'outcome' column is a continuous
    future-30d TS%-style value (range ~0.29-0.80), not a binary outcome --
    positional_weight_verdict.json's own verdict is rank-correlation (rho)
    based, not Brier. This test pins that the harness still runs and is
    deterministic on this real file; it deliberately does NOT assert equality
    against positional_weight_verdict.json's rho numbers since the harness
    computes a different (Brier-on-continuous-outcome) statistic -- see
    reprocess_selfcheck_elo.json for the documented skip rationale.
    """
    df = load_rows(_PW_ROWS)
    assert df["outcome"].min() >= 0.0 and df["outcome"].max() <= 1.0
    assert df["outcome"].nunique() > 50, "outcome looks binary -- re-check the continuous-outcome skip rationale"
    v1 = run_harness(df)
    v2 = run_harness(df)
    d1 = v1.per_corpus["nba_2024_25_boxscore"]["vs_base"]["delta"]
    d2 = v2.per_corpus["nba_2024_25_boxscore"]["vs_base"]["delta"]
    assert d1 == pytest.approx(d2, abs=1e-12)
