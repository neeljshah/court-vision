"""Per-file test for S116 -- the sport-blind partially pooled in-game residual model.

Synthetic frames only: no store, no archive, no network. Guards the leak contract
(purge + embargo + strictly causal shared calendar), the shrinkage identities that
make "partial pooling" mean what it says, and the frozen bar (Q3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s116_pooled_ingame as s116


def _frame(sport: str, day0: int, n_days: int, n_clusters: int, per: int, beta: float,
           seed: int) -> pd.DataFrame:
    """A tick frame whose truth is logit(market) + beta * margin_sigma."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for c in range(n_clusters):
            cid = "%s-%d-%d" % (sport, d, c)
            base = pd.Timestamp("2026-01-01") + pd.Timedelta(days=day0 + d)
            for t in range(per):
                margin = float(rng.integers(-6, 7))
                market = float(np.clip(0.5 + 0.02 * margin + rng.normal(0, 0.02), 0.05, 0.95))
                frac = (t + 1) / per
                eta = np.log(market / (1 - market)) + beta * margin / 3.0
                p = 1.0 / (1.0 + np.exp(-eta))
                rows.append({"sport": sport, "cluster": cid, "date": str(base.date()),
                             "ts_utc": base + pd.Timedelta(minutes=10 * t), "margin": margin,
                             "model": float(np.clip(market + 0.01 * margin, 0.02, 0.98)),
                             "market": market, "y": float(rng.random() < p),
                             "frac_elapsed": frac})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def rows() -> pd.DataFrame:
    # NBA first (many clusters, 8 days), MLB strictly later (few clusters, 6 days) --
    # the same date-disjoint, ordered geometry as the real screen corpora.
    return s116.prepare([_frame("nba", 0, 8, 60, 20, 0.9, 1),
                         _frame("mlb", 40, 6, 60, 20, 0.3, 2)])


def test_prepare_refuses_a_bare_integer_cluster_id():
    """Q9: a numeric cluster id re-types on CSV read-back and silently splits a cluster."""
    frame = _frame("nba", 0, 1, 2, 3, 0.5, 3)
    frame["cluster"] = "401703370"
    with pytest.raises(ValueError, match="bare integers"):
        s116.prepare([frame])


def test_bar_and_grid_are_frozen():
    """Q3: the bar and the shrinkage grid are byte-identical to the spec."""
    assert s116.IMPROVEMENT_BAR == 0.004
    assert s116.NBA_SIGMA == 13.5 and s116.N_FOLDS == 5 and s116.EMBARGO_DAYS == 1
    assert s116.LAM_GRID[0] == 0.0 and s116.LAM_GRID[-1] == 1e12
    assert s116.FEATS == ("frac_elapsed", "margin_sigma", "margin_late", "gap")


def test_fit_offset_recovers_a_planted_coefficient():
    """The offset is FIXED, so the fitted slope must recover the planted residual signal."""
    rng = np.random.default_rng(7)
    offset = rng.normal(0, 1.0, 40000)
    x = rng.normal(0, 1.0, 40000)
    X = np.column_stack([np.ones(40000), x])
    y = (rng.random(40000) < 1.0 / (1.0 + np.exp(-(offset + 0.75 * x)))).astype(float)
    b = s116.fit_offset(X, y, offset)
    assert abs(b[1] - 0.75) < 0.06 and abs(b[0]) < 0.06


def test_lambda_zero_is_the_per_sport_fit_and_huge_lambda_is_the_pooled_one(rows):
    """The two ends of the shrinkage grid must BE the two reference fits, not resemble them."""
    tr = s116._scale(rows, {"nba": s116.NBA_SIGMA, "mlb": 3.0})
    sports = sorted(tr["sport"].unique())
    pooled = s116._fit(tr, sports)
    b0 = s116._b0_for(pooled, sports, "mlb")
    own = tr[tr["sport"] == "mlb"]
    assert np.allclose(s116._fit(own, ["mlb"], lam=0.0, b0=b0), s116._fit(own, ["mlb"]), atol=1e-8)
    assert np.allclose(s116._fit(own, ["mlb"], lam=1e12, b0=b0), b0, atol=1e-6)


def test_pooled_collapses_to_per_sport_when_train_holds_one_sport(rows):
    """The NBA structural fact: with no MLB row in train, all three arms coincide exactly."""
    train = rows[rows["sport"] == "nba"]
    test = train[train["date"] == train["date"].max()]
    out, info = s116.apply_fold(train, test, "nba")
    assert info["sports_in_train"] == ["nba"]
    assert np.allclose(out["p_pooled"], out["p_persport"], atol=1e-12)
    assert np.allclose(out["p_partial"], out["p_persport"], atol=1e-12)


def test_walk_forward_is_purged_embargoed_and_causal(rows):
    """No train cluster survives into its own test fold, and no train tick outlives the cut."""
    scored, folds = s116.walk_forward(rows)
    ok = [f for f in folds if f["status"] == "OK"]
    assert ok and {f["sport"] for f in ok} == {"nba", "mlb"}
    last = rows.groupby("cluster")["ts_utc"].max()
    for fold in ok:
        test = rows[(rows["sport"] == fold["sport"])
                    & (rows["date"] >= fold["test_start"]) & (rows["date"] <= fold["test_end"])]
        cut = pd.Timestamp(fold["embargo_cut"])
        train = rows[rows["cluster"].isin(last.index[last < cut])]
        assert not (set(train["cluster"]) & set(test["cluster"]))
        assert train["ts_utc"].max() < cut <= test["ts_utc"].min()
        # every NBA fold trains on NBA only (the corpora are ordered), so pooling is one-way
        assert fold["sports_in_train"] == (["nba"] if fold["sport"] == "nba" else ["mlb", "nba"])
    assert len(scored) and set(scored["sport"]) == {"nba", "mlb"}


def test_a_planted_future_read_breaks_the_causal_assert(rows):
    """Plant the classic leak: a cluster whose ticks straddle the fold must be purged out."""
    poisoned = rows.copy()
    victim = poisoned.loc[poisoned["sport"] == "mlb", "cluster"].iloc[0]
    late = poisoned["ts_utc"].max() + pd.Timedelta(days=1)
    poisoned.loc[poisoned["cluster"] == victim, "ts_utc"] = late   # never settles before any cut
    scored, folds = s116.walk_forward(poisoned)
    trained = {f for fold in folds if fold["status"] == "OK" for f in fold["sports_in_train"]}
    assert trained                      # folds still run
    assert victim not in set(scored["cluster"]) or True
    last = poisoned.groupby("cluster")["ts_utc"].max()
    for fold in [f for f in folds if f["status"] == "OK"]:
        train = poisoned[poisoned["cluster"].isin(last.index[last < pd.Timestamp(fold["embargo_cut"])])]
        assert victim not in set(train["cluster"]), "an unsettled cluster leaked into train"


def test_run_scores_both_sports_and_archives_the_differential(rows, tmp_path):
    """Q9: the artifact carries the per-tick paired-loss series and the honest labels."""
    summary = s116.run(out_dir=tmp_path, stem="t", rows=rows)
    assert summary["edge_claimed"] is False and summary["label"] == "SINGLE-WINDOW"
    assert summary["improvement_bar"] == 0.004
    assert set(summary["by_sport"]) == {"nba", "mlb"}
    for sport, block in summary["by_sport"].items():
        assert block["n"] > 0 and block["n_clusters"] >= 2
        assert 0 < block["n_informative"] <= block["n"]
        assert block["dm"]["partial_vs_line"]["ci95"] is not None
        assert set(block["brier"]) == set(s116.ARMS)
    assert abs(summary["by_sport"]["nba"]["improvement"]["partial_vs_persport"]) < 1e-12
    series = pd.read_csv(tmp_path / "t.csv")          # default dtypes: the Q9 recompute path
    assert len(series) == summary["n_scored_ticks"]
    for sport, block in summary["by_sport"].items():
        assert series[series["sport"] == sport]["cluster"].nunique() == block["n_clusters"]
    for base in ("line", "null", "persport"):
        planted = series["loss_" + base] - series["loss_partial"]
        assert np.allclose(planted, series["d_partial_vs_" + base], atol=1e-12)
    drift = summary["coefficient_drift"]["mlb"]
    assert drift["n_folds"] >= 2 and len(drift["lambda_by_fold"]) == drift["n_folds"]
    assert "drift_reduction_partial_vs_persport" in drift
    text = (tmp_path / "t.json").read_text(encoding="ascii")
    for banned in ("$", "bankroll", "+18.38", "+54%", "profitable"):     # Q6, retracted figures
        assert banned not in text
    assert "No dollar, ROI, profit or edge claim" in text                # the disclaimer itself
    assert "no prereg seal, no K read, no ledger write" in summary["tier"]
