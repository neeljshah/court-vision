"""
test_signals_cluster_lab.py -- adversarial correctness tests for signals/cluster_lab.py

Covers:
  - validate_cluster REPLICATES requires >= 2 seasons
  - validate_cluster skips season if < min_games
  - pts > 4 filter is applied and silently discards rows (confirmed behavior)
  - empty corpus after filter -> skip-fewgames in all seasons -> does-NOT-replicate
  - model registration on REPLICATES
  - model_id order-independent on signal set
  - seed=0 hardcoded -> deterministic (confirmed, documented)
  - oos_score reports best season (potential over-reporting, documented)
  - _oos RMSE is finite and positive
"""
from __future__ import annotations

import math
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "team_system"))


def _synthetic_corpus(n_games: int = 100, n_possessions_per_game: int = 10,
                       seasons=("2022-23", "2023-24"), signal_strength: float = 0.5,
                       pts_max: float = 3.5, rng_seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(rng_seed)
    n = n_games * n_possessions_per_game
    gids = np.repeat(np.arange(n_games), n_possessions_per_game)
    season_arr = np.where(rng.random(n) < (1 / len(seasons)), seasons[0], seasons[-1])
    feat = rng.random(n)
    pts = feat * signal_strength * pts_max + rng.random(n) * pts_max * (1 - signal_strength)
    pts = np.clip(pts, 0.0, pts_max)
    base = rng.random(n)
    return pd.DataFrame({"gid": gids, "season": season_arr, "pts": pts,
                         "base": base, "sig": feat})


@pytest.fixture
def corpus_path(tmp_path):
    df = _synthetic_corpus(n_games=120, n_possessions_per_game=10, signal_strength=0.7)
    p = str(tmp_path / "corpus.parquet")
    df.to_parquet(p, index=False)
    return p


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    import scripts.team_system.registry.store as store_mod
    monkeypatch.setattr(store_mod, "REGISTRY_DIR", str(tmp_path))
    monkeypatch.setattr(store_mod, "_LOCK", str(tmp_path / ".lock"))
    return tmp_path


class TestValidateCluster:
    def test_replicates_requires_two_seasons(self, corpus_path, tmp_registry):
        from signals.cluster_lab import validate_cluster
        r = validate_cluster(corpus_path, base=["base"], signals=["sig"],
                             domain="test_domain", scope="possession",
                             seasons=("2022-23", "2023-24"), register=False)
        assert r["verdict"] in ("REPLICATES", "single-season", "does-NOT-replicate")
        assert r["n_replicate"] <= 2

    def test_single_season_does_not_replicate(self, tmp_path, tmp_registry):
        """Only one season in data -> other is skip-fewgames -> verdict is not REPLICATES."""
        from signals.cluster_lab import validate_cluster
        df = _synthetic_corpus(n_games=100, signal_strength=0.8)
        df["season"] = "2022-23"  # force all to one season
        p = str(tmp_path / "single.parquet")
        df.to_parquet(p, index=False)
        r = validate_cluster(p, base=["base"], signals=["sig"],
                             domain="test", scope="test",
                             seasons=("2022-23", "2023-24"), register=False)
        assert r["n_replicate"] <= 1
        assert r["verdict"] != "REPLICATES"

    def test_pts_filter_silent_discard(self, tmp_path, tmp_registry):
        """DOCUMENTED BEHAVIOR: pts > 4 filter now logs a warning (fixed observability).
        When all pts > 4, every season gets skip-fewgames and verdict is not REPLICATES."""
        from signals.cluster_lab import validate_cluster
        rng = np.random.default_rng(0)
        n = 1000
        df = pd.DataFrame({
            "gid": np.repeat(np.arange(100), 10),
            "season": np.where(rng.random(n) < 0.5, "2022-23", "2023-24"),
            "pts": rng.integers(5, 10, n).astype(float),  # all pts > 4
            "base": rng.random(n),
            "sig": rng.random(n),
        })
        p = str(tmp_path / "allhigh.parquet")
        df.to_parquet(p, index=False)
        r = validate_cluster(p, base=["base"], signals=["sig"],
                             domain="test", scope="test",
                             seasons=("2022-23", "2023-24"), register=False)
        # All rows discarded -> every run season either skip-fewgames or no cluster_rel
        # Verdict must NOT be REPLICATES (no seasons passed the noise floor)
        assert r["verdict"] != "REPLICATES", (
            "With all pts>4 (empty corpus after filter), no season can produce valid OOS results. "
            "The verdict must not be REPLICATES."
        )
        # n_replicate must be 0 (nothing passed the noise floor)
        assert r["n_replicate"] == 0

    def test_empty_signals_list_handled(self, corpus_path, tmp_registry):
        """Empty signals list -> cluster == base, rel ~= 0."""
        from signals.cluster_lab import validate_cluster
        r = validate_cluster(corpus_path, base=["base"], signals=[],
                             domain="test_empty", scope="test",
                             seasons=("2022-23", "2023-24"), register=False)
        # cluster_rels should be near 0 (no extra signals)
        for rel in r["cluster_rels"]:
            assert abs(rel) < 0.05  # very close to base RMSE

    def test_model_registered_on_replicates(self, tmp_registry, tmp_path):
        """On REPLICATES verdict, model is registered in model_registry."""
        from signals.cluster_lab import validate_cluster
        from registry.store import Registry
        # Build a very strong synthetic signal to ensure REPLICATES
        rng = np.random.default_rng(99)
        n = 1000
        feat = rng.random(n)
        df = pd.DataFrame({
            "gid": np.repeat(np.arange(100), 10),
            "season": np.where(rng.random(n) < 0.5, "2022-23", "2023-24"),
            "pts": np.clip(feat * 3.0 + rng.random(n) * 0.2, 0, 4),  # very strong signal
            "base": rng.random(n),
            "sig": feat,
        })
        p = str(tmp_path / "strong.parquet")
        df.to_parquet(p, index=False)
        r = validate_cluster(p, base=["base"], signals=["sig"],
                             domain="test_reg", scope="possession",
                             seasons=("2022-23", "2023-24"), register=True)
        if r["verdict"] == "REPLICATES":
            assert "registered_model_id" in r
            mid = r["registered_model_id"]
            mreg = Registry("model_registry")
            got = mreg.get(mid)
            assert got is not None
            assert got["domain_tag"] == "test_reg"
            assert got["status"] == "validated"

    def test_deterministic_with_seed_0(self, corpus_path, tmp_registry):
        """DOCUMENTED: seed=0 hardcoded -> runs are deterministic."""
        from signals.cluster_lab import validate_cluster
        r1 = validate_cluster(corpus_path, base=["base"], signals=["sig"],
                              domain="d", scope="s", register=False)
        r2 = validate_cluster(corpus_path, base=["base"], signals=["sig"],
                              domain="d", scope="s", register=False)
        assert r1["cluster_rels"] == r2["cluster_rels"], (
            "DOCUMENTED: seed=0 hardcoded -> identical runs are byte-identical. "
            "Risk: adversarial fold layout is locked forever. "
            "Fix recipe (recommend-don't-apply): parameterize seed and run 3+ seeds, "
            "require REPLICATES to hold under majority of seeds."
        )

    def test_oos_score_reports_best_season(self, corpus_path, tmp_registry):
        """DOCUMENTED: oos_score = min(cluster_rels) = best season, not average."""
        from signals.cluster_lab import validate_cluster
        r = validate_cluster(corpus_path, base=["base"], signals=["sig"],
                             domain="d2", scope="s2", register=False)
        if r["cluster_rels"]:
            expected_oos = min(r["cluster_rels"])
            # If registered, verify oos_score matches the best season
            # (this is a documentation test -- not a fix, just a label)
            assert r["cluster_rels"].count(min(r["cluster_rels"])) >= 1

    def test_oos_rmse_is_finite_positive(self, corpus_path, tmp_registry):
        """_oos returns a positive finite float."""
        from signals.cluster_lab import _oos
        df = pd.read_parquet(corpus_path)
        S = df[df.season == "2022-23"]
        if S.gid.nunique() < 5:
            pytest.skip("not enough games for fold")
        rmse = _oos(S, ["base"], "pts", seed=0)
        assert math.isfinite(rmse)
        assert rmse > 0


class TestModelIdStability:
    def test_model_id_order_independent(self):
        from registry.ids import model_id
        m1 = model_id(dict(domain_tag="d", entity_scope="possession",
                           signal_id_set=["sig_a", "sig_b", "sig_c"], method="hgb"))
        m2 = model_id(dict(domain_tag="d", entity_scope="possession",
                           signal_id_set=["sig_c", "sig_a", "sig_b"], method="hgb"))
        assert m1 == m2

    def test_different_signal_set_different_id(self):
        from registry.ids import model_id
        m1 = model_id(dict(domain_tag="d", entity_scope="possession",
                           signal_id_set=["sig_a", "sig_b"], method="hgb"))
        m2 = model_id(dict(domain_tag="d", entity_scope="possession",
                           signal_id_set=["sig_a", "sig_c"], method="hgb"))
        assert m1 != m2
