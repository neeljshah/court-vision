"""Regression guard for the cluster_lab pseudo-replication bug + fix.

BUG (found 2026-06-08 engines-area robustness sweep): validate_cluster loops over
`seasons` but, when the corpus has NO `season` column (or <2 of the requested
seasons present), every iteration scores the SAME rows. Two identical `cluster_rel`
values then fake "REPLICATES 2/2" from ONE dataset evaluated twice -- a leak/false
-positive that would auto-register a bogus model. The documented invariant is
"REPLICATES needs >=2 INDEPENDENT seasons".

FIX (gated, default-ON safe): a season-less / single-season corpus yields
verdict="insufficient-seasons" and never registers. CV_CLUSTER_ALLOW_PSEUDO=1
restores the legacy behavior. A real multi-season corpus is unaffected.

This file is OWNED by the engines-audit task (cluster_lab is in its editable set).
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))

from signals.cluster_lab import validate_cluster  # noqa: E402


def _season_less_corpus(path, n=6000, seed=0):
    """A corpus with a strong signal but NO `season` column (triggers the bug)."""
    rng = np.random.default_rng(seed)
    gid = rng.integers(0, 200, n)
    base1 = rng.normal(0, 1, n)
    good = rng.normal(0, 1, n)
    pts = (0.1 * base1 + 1.5 * good + rng.normal(0, 0.3, n)).clip(0, 4)
    pd.DataFrame(dict(gid=gid, period=base1, grem=rng.normal(0, 1, n),
                      strongsig=good, pts=pts)).to_parquet(path, index=False)


def test_season_less_corpus_does_not_falsely_replicate(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_CLUSTER_ALLOW_PSEUDO", raising=False)
    fp = str(tmp_path / "noseason.parquet")
    _season_less_corpus(fp)
    r = validate_cluster(fp, base=["period", "grem"], signals=["strongsig"],
                         domain="x", scope="y", register=False, min_games=50)
    assert r["verdict"] == "insufficient-seasons"
    assert r["pseudo_replication_blocked"] is True
    assert "registered_model_id" not in r  # must NOT auto-register a bogus model


def test_legacy_gate_restores_old_behavior(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_CLUSTER_ALLOW_PSEUDO", "1")
    fp = str(tmp_path / "noseason.parquet")
    _season_less_corpus(fp)
    r = validate_cluster(fp, base=["period", "grem"], signals=["strongsig"],
                         domain="x", scope="y", register=False, min_games=50)
    # legacy path: the strong signal makes both (duplicate) folds clear the floor
    assert r["pseudo_replication_blocked"] is False
    assert r["verdict"] == "REPLICATES"


def test_single_season_present_is_blocked(tmp_path, monkeypatch):
    """A corpus that HAS a season column but only ONE of the requested seasons is still pseudo."""
    monkeypatch.delenv("CV_CLUSTER_ALLOW_PSEUDO", raising=False)
    fp = str(tmp_path / "onesseason.parquet")
    rng = np.random.default_rng(1)
    n = 6000
    good = rng.normal(0, 1, n)
    pts = (1.5 * good + rng.normal(0, 0.3, n)).clip(0, 4)
    pd.DataFrame(dict(gid=rng.integers(0, 200, n), period=rng.normal(0, 1, n),
                      grem=rng.normal(0, 1, n), strongsig=good, pts=pts,
                      season=["2022-23"] * n)).to_parquet(fp, index=False)
    r = validate_cluster(fp, base=["period", "grem"], signals=["strongsig"],
                         domain="x", scope="y", register=False, min_games=50,
                         seasons=("2022-23", "2023-24"))
    assert r["pseudo_replication_blocked"] is True
    assert r["verdict"] == "insufficient-seasons"


@pytest.mark.skipif(
    not os.path.exists(os.path.join(ROOT, "data", "cache", "team_system", "legacy_possessions.parquet")),
    reason="legacy_possessions corpus not present")
def test_real_multiseason_corpus_unaffected(monkeypatch):
    """The real 4-season corpus must keep its prior behavior (>=2 independent seasons present)."""
    monkeypatch.delenv("CV_CLUSTER_ALLOW_PSEUDO", raising=False)
    fp = os.path.join(ROOT, "data", "cache", "team_system", "legacy_possessions.parquet")
    r = validate_cluster(fp, base=["period", "grem"],
                         signals=["poss_dur", "after_to", "dead_ball", "abs_margin", "had_oreb"],
                         domain="possession_origin", scope="possession", register=False)
    assert r["pseudo_replication_blocked"] is False
    assert len(r["independent_seasons"]) >= 2
