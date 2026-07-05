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
    validate_metric_matches_outcome,
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
_ELO_HARNESS_ROWS = _REPO_ROOT / "data" / "domains" / "wnba" / "elo_refresh_harness_rows.parquet"
_PW_ROWS = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "positional_weight_rows.parquet"


@pytest.mark.skipif(not _ELO_ROWS.exists(), reason="real wnba corpus not present in this checkout")
def test_elo_refresh_rows_is_not_harness_shaped():
    """elo_refresh_rows.parquet is (and remains) raw game rows -- a single
    flat p_home_elo, no per-candidate probabilities -- NOT the
    reprocess_harness pre-scored shape; load_rows correctly fails closed on
    it. This is EXPECTED and does not need fixing: the wave-33 gap is closed
    by a SEPARATE, correctly-harness-shaped export,
    elo_refresh_harness_rows.parquet (see
    test_elo_refresh_harness_rows_is_harness_shaped below and
    domains.basketball_wnba.elo_refresh_gate_io.build_harness_rows), not by
    reshaping this raw-rows file in place.
    """
    df = pd.read_parquet(_ELO_ROWS)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    assert missing, (
        "elo_refresh_rows.parquet unexpectedly gained harness columns -- "
        "re-run the selfcheck replay, do not assume this is still blocked"
    )
    with pytest.raises(SchemaError):
        load_rows(_ELO_ROWS)


@pytest.mark.skipif(not _ELO_HARNESS_ROWS.exists(),
                     reason="elo_refresh_harness_rows.parquet not present in this checkout -- "
                            "run domains.basketball_wnba.elo_refresh_gate_io.write_harness_rows first")
def test_elo_refresh_harness_rows_is_harness_shaped():
    """Closes the wave-33 gap: elo_refresh_harness_rows.parquet (built by
    elo_refresh_gate_io.build_harness_rows, reusing elo_refresh_gate's own
    _replay_candidate on the SAME cold-start fold construction) IS
    harness-shaped and loads/runs through metric=brier cleanly -- unlike
    elo_refresh_rows.parquet above. See selfcheck_elo.py /
    data/domains/wnba/reprocess_selfcheck_elo.json for the numeric match
    against the committed elo_refresh_verdict.json.
    """
    df = load_rows(_ELO_HARNESS_ROWS)
    assert set(REQUIRED_COLS).issubset(df.columns)
    assert set(df["outcome"].unique()).issubset({0.0, 1.0})
    v = run_harness(df, metric="brier")
    assert v.metric == "brier"
    assert len(v.per_corpus) == 3  # one per candidate (C1_mov/C2_neutral_hfa/C3_mov_neutral)


@pytest.mark.skipif(not _PW_ROWS.exists(), reason="real nba corpus not present in this checkout")
def test_positional_weight_rows_metric_brier_fails_closed():
    """positional_weight_rows.parquet's 'outcome' column is a continuous
    future-30d TS%-style value (range ~0.29-0.80), not a binary outcome --
    metric=brier (the default) must now fail closed rather than silently
    scoring Brier loss on a continuous target. Closes the wave-33 gap: the
    harness previously had no way to express this and would run brier
    unconditionally."""
    df = load_rows(_PW_ROWS)
    assert df["outcome"].min() >= 0.0 and df["outcome"].max() <= 1.0
    assert df["outcome"].nunique() > 50, "outcome looks binary -- re-check the continuous-outcome skip rationale"
    with pytest.raises(SchemaError):
        run_harness(df, metric="brier")


@pytest.mark.skipif(not _PW_ROWS.exists(), reason="real nba corpus not present in this checkout")
def test_positional_weight_rows_metric_rho_is_deterministic():
    """positional_weight_rows.parquet IS harness-shaped and, with the
    declared metric=rho and cluster_col=player_id (matches
    positional_weight_verdict.json's own cluster-by-player bootstrap
    convention), replays through reprocess_harness deterministically.
    See test_reprocess_selfcheck_positional.py-equivalent self-check for the
    numeric match against positional_weight_verdict.json.
    """
    df = load_rows(_PW_ROWS)
    assert "cluster_id" in df.columns, "expected positional_weight_io to have added a cluster_id column"
    v1 = run_harness(df, metric="rho", cluster_col="cluster_id")
    v2 = run_harness(df, metric="rho", cluster_col="cluster_id")
    d1 = v1.per_corpus["nba_2024_25_boxscore"]["vs_base"]["delta"]
    d2 = v2.per_corpus["nba_2024_25_boxscore"]["vs_base"]["delta"]
    assert d1 == pytest.approx(d2, abs=1e-12)
    assert v1.metric == "rho"


def _synthetic_rho_df(n_per_corpus: int, seed: int, variant_better: bool,
                       corpora=("corpusA",), n_folds: int = 3, n_clusters: int = 20) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    eid = 0
    for corpus in corpora:
        for i in range(n_per_corpus):
            fold = f"fold{i % n_folds}"
            cluster = f"c{i % n_clusters}"
            truth = rng.uniform(0.2, 0.8)
            outcome = float(np.clip(truth + rng.normal(0, 0.05), 0.0, 1.0))
            if variant_better:
                p_variant = np.clip(truth + rng.normal(0, 0.05), 0.0, 1.0)
                p_base = np.clip(truth + rng.normal(0, 0.4), 0.0, 1.0)
            else:
                p_variant = np.clip(truth + rng.normal(0, 0.4), 0.0, 1.0)
                p_base = np.clip(truth + rng.normal(0, 0.05), 0.0, 1.0)
            rows.append({
                "corpus_id": corpus, "fold_id": fold, "event_id": f"e{eid}",
                "cluster_id": cluster,
                "p_variant": float(p_variant), "p_base": float(p_base), "outcome": outcome,
            })
            eid += 1
    return pd.DataFrame(rows)


def test_metric_never_inferred_default_is_brier_explicit_string():
    """metric always defaults to the explicit string 'brier', never inferred
    from the data -- calling run_harness with no metric arg on a rho-shaped
    df must still fail closed (proves default isn't silently adaptive)."""
    df = _synthetic_rho_df(n_per_corpus=60, seed=100, variant_better=True)
    with pytest.raises(SchemaError):
        run_harness(df)  # default metric="brier" on continuous outcome -> fail closed


def test_validate_metric_matches_outcome_rejects_rho_on_binary():
    df = _synthetic_df(n_per_corpus=50, seed=101, variant_better=True)
    with pytest.raises(SchemaError):
        validate_metric_matches_outcome(df, "rho")


def test_validate_metric_matches_outcome_rejects_unknown_metric():
    df = _synthetic_df(n_per_corpus=50, seed=102, variant_better=True)
    with pytest.raises(SchemaError):
        validate_metric_matches_outcome(df, "spearman")  # not a declared METRICS value


def test_rho_metric_requires_declared_cluster_col_present():
    df = _synthetic_rho_df(n_per_corpus=60, seed=103, variant_better=True).drop(columns=["cluster_id"])
    with pytest.raises(SchemaError):
        run_harness(df, metric="rho", cluster_col="cluster_id")


def test_rho_metric_variant_better_shows_positive_delta_and_ci_excludes_zero():
    df = _synthetic_rho_df(n_per_corpus=300, seed=104, variant_better=True, n_clusters=30)
    v = run_harness(df, metric="rho", cluster_col="cluster_id")
    assert v.metric == "rho"
    pooled = v.pooled_diagnostic["vs_base"]
    assert pooled["delta"] > 0
    assert pooled["ci_lo"] > 0
    for corpus_id, block in v.per_corpus.items():
        assert block["vs_base"]["delta"] > 0


def test_rho_metric_variant_worse_shows_negative_delta():
    df = _synthetic_rho_df(n_per_corpus=300, seed=105, variant_better=False, n_clusters=30)
    v = run_harness(df, metric="rho", cluster_col="cluster_id")
    pooled = v.pooled_diagnostic["vs_base"]
    assert pooled["delta"] < 0


def test_rho_metric_corpora_never_pooled_and_edge_never_claimed():
    df = _synthetic_rho_df(n_per_corpus=150, seed=106, variant_better=True,
                            corpora=("A", "B"), n_clusters=25)
    v = run_harness(df, metric="rho", cluster_col="cluster_id")
    assert set(v.per_corpus.keys()) == {"A", "B"}
    d = verdict_to_dict(v)
    assert d["edge_claimed"] is False
    assert "never an edge" in d["honest_note"]


def test_rho_metric_custom_cluster_col_name():
    df = _synthetic_rho_df(n_per_corpus=100, seed=107, variant_better=True, n_clusters=15)
    df = df.rename(columns={"cluster_id": "player_id"})
    v = run_harness(df, metric="rho", cluster_col="player_id")
    assert v.pooled_diagnostic["vs_base"]["n_clusters"] == 15


# --------------------------------------------------------------------------- metric=rmse

def _synthetic_rmse_df(n_per_corpus: int, seed: int, variant_better: bool,
                        corpora=("corpusA",), n_folds: int = 3, n_clusters: int = 10) -> pd.DataFrame:
    """Continuous PREDICTIONS (p_variant/p_base) vs a continuous TARGET
    (outcome) -- the rmse-metric contract (predictions, not probabilities)."""
    rng = np.random.default_rng(seed)
    rows = []
    eid = 0
    for corpus in corpora:
        for i in range(n_per_corpus):
            fold = f"fold{i % n_folds}"
            cluster = f"c{i % n_clusters}"
            truth = rng.uniform(2.0, 12.0)  # e.g. runs-like continuous target
            outcome = float(truth + rng.normal(0, 1.0))
            if variant_better:
                p_variant = float(truth + rng.normal(0, 0.3))
                p_base = float(truth + rng.normal(0, 2.0))
            else:
                p_variant = float(truth + rng.normal(0, 2.0))
                p_base = float(truth + rng.normal(0, 0.3))
            rows.append({
                "corpus_id": corpus, "fold_id": fold, "event_id": f"e{eid}",
                "cluster_id": cluster,
                "p_variant": p_variant, "p_base": p_base, "outcome": outcome,
            })
            eid += 1
    return pd.DataFrame(rows)


def test_rmse_metric_requires_continuous_outcome_fails_closed_on_binary():
    df = _synthetic_df(n_per_corpus=50, seed=200, variant_better=True)  # binary outcome
    with pytest.raises(SchemaError):
        run_harness(df, metric="rmse")


def test_rmse_metric_variant_better_shows_positive_delta():
    df = _synthetic_rmse_df(n_per_corpus=300, seed=201, variant_better=True, n_clusters=20)
    v = run_harness(df, metric="rmse", cluster_col="cluster_id")
    assert v.metric == "rmse"
    pooled = v.pooled_diagnostic["vs_base"]
    assert pooled["delta"] > 0  # rmse_base - rmse_variant > 0 => variant improves
    assert pooled["ci_lo"] > 0  # bootstrap CI on the delta excludes 0
    for corpus_id, block in v.per_corpus.items():
        assert block["vs_base"]["delta"] > 0


def test_rmse_metric_variant_worse_shows_negative_delta():
    df = _synthetic_rmse_df(n_per_corpus=300, seed=202, variant_better=False, n_clusters=20)
    v = run_harness(df, metric="rmse", cluster_col="cluster_id")
    pooled = v.pooled_diagnostic["vs_base"]
    assert pooled["delta"] < 0


def test_rmse_metric_cluster_col_declared_but_missing_fails_closed():
    df = _synthetic_rmse_df(n_per_corpus=60, seed=203, variant_better=True).drop(columns=["cluster_id"])
    with pytest.raises(SchemaError):
        run_harness(df, metric="rmse", cluster_col="cluster_id")


def test_rmse_metric_cluster_col_none_omits_bootstrap_without_raising():
    df = _synthetic_rmse_df(n_per_corpus=60, seed=204, variant_better=True).drop(columns=["cluster_id"])
    v = run_harness(df, metric="rmse", cluster_col=None)
    assert v.metric == "rmse"
    pooled = v.pooled_diagnostic["vs_base"]
    assert pooled["n_clusters"] == 0
    assert pooled["ci_lo"] != pooled["ci_lo"]  # nan != nan


def test_rmse_metric_corpora_never_pooled_and_edge_never_claimed():
    df = _synthetic_rmse_df(n_per_corpus=150, seed=205, variant_better=True,
                             corpora=("A", "B"), n_clusters=15)
    v = run_harness(df, metric="rmse", cluster_col="cluster_id")
    assert set(v.per_corpus.keys()) == {"A", "B"}
    d = verdict_to_dict(v)
    assert d["edge_claimed"] is False
    assert "never an edge" in d["honest_note"]


def test_rmse_metric_per_fold_signs_reported():
    df = _synthetic_rmse_df(n_per_corpus=300, seed=206, variant_better=True, n_folds=3, n_clusters=20)
    v = run_harness(df, metric="rmse", cluster_col="cluster_id")
    for corpus_id, block in v.per_corpus.items():
        signs = block["per_fold_signs_vs_base"]
        assert len(signs) == 3
        assert all(s["sign"] in ("variant", "base", "tie") for s in signs)


def test_rmse_metric_deterministic_across_runs():
    df = _synthetic_rmse_df(n_per_corpus=200, seed=207, variant_better=True, n_clusters=15)
    v1 = run_harness(df, metric="rmse", cluster_col="cluster_id")
    v2 = run_harness(df, metric="rmse", cluster_col="cluster_id")
    d1 = v1.pooled_diagnostic["vs_base"]["delta"]
    d2 = v2.pooled_diagnostic["vs_base"]["delta"]
    assert d1 == pytest.approx(d2, abs=1e-12)


# --------------------------------------------------------------------------- real umpire corpus (rmse)

_UMPIRE_ROWS = _REPO_ROOT / "data" / "domains" / "mlb" / "umpire_totals_gate_rows.parquet"


@pytest.mark.skipif(not _UMPIRE_ROWS.exists(), reason="real mlb umpire corpus not present in this checkout")
def test_umpire_rows_relabeled_replay_matches_committed_folds():
    """Closes the wave-47 gap: umpire_totals_gate_rows.parquet's own columns
    (game_pk/date/hp_umpire_id/total_runs/baseline_pred/candidate_pred),
    relabeled into the harness's rmse contract (p_base=baseline_pred,
    p_variant=candidate_pred, outcome=total_runs, one corpus_id, fold_id via
    the SAME BURN_IN=300/N_FOLDS=3/np.array_split construction the gate
    itself uses), replays the committed per-fold RMSE within 1e-6. See
    scripts/platformkit/reprocess/clients/replay_shipped_indices_io.py
    umpire_totals_rows() for the production relabeling used by the client."""
    from scripts.platformkit.reprocess.clients.replay_shipped_indices_io import (
        umpire_totals_committed_fold_deltas,
        umpire_totals_rows,
    )
    df = umpire_totals_rows()
    v = run_harness(df, metric="rmse", cluster_col=None)
    corpus_id = df["corpus_id"].iloc[0]
    replayed_folds = {
        f["fold_id"]: (f["mean_delta"])
        for f in v.per_corpus[str(corpus_id)]["per_fold_signs_vs_base"]
    }
    committed_folds = umpire_totals_committed_fold_deltas()
    assert set(replayed_folds) == set(committed_folds)
    max_abs_diff = max(abs(replayed_folds[k] - committed_folds[k]) for k in replayed_folds)
    assert max_abs_diff <= 1e-6
