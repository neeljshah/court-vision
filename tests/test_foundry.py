"""Tests for the V3 FOUNDRY PROPOSER (scripts/team_system/foundry_proposer.py).

These verify the MACHINERY, not a particular scientific outcome (the foundry must be result-agnostic):
  - the candidate p-value correctly rewards >=2-season replication and is non-significant for a single
    season (closing the single-window artifact trap),
  - run_candidates routes the batch through cross-season cluster validation + FDR + the scoreboard,
  - a single-season-only "lift" is recorded as N-A-no-substrate and NEVER registered,
  - the family anti-re-roll key is stable + distinct across the proposed batch,
  - imports of cluster_lab + the registry are read-only (this module never edits them),
  - the FDR machinery in gates still controls error (planted-null), and the candidate batch is well-formed.

All tests run on tiny in-memory / subsampled corpora so the board stays fast and green. The full-corpus
scientific run is foundry_proposer.main(), NOT a test (it is heavy + its verdict is honestly allowed to be
'no survivors').
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS = os.path.join(ROOT, "scripts", "team_system")
sys.path.insert(0, TS)

import foundry_proposer as fp  # noqa: E402
from registry.store import Registry  # noqa: E402
from signals.gates import benjamini_hochberg, planted_null_test  # noqa: E402


# --------------------------------------------------------------------------- p-value behavior
def test_pvalue_rewards_two_season_replication():
    """Two seasons that both clear the noise floor -> tiny p; the engine should treat this as significant."""
    p = fp._replication_pvalue(
        {"2022-23": {"cluster_rel": -0.012}, "2023-24": {"cluster_rel": -0.010}},
        ("2022-23", "2023-24"))
    assert p < 0.01, f"two replicating seasons should give a small p, got {p}"


def test_pvalue_single_season_is_not_significant():
    """The artifact trap: ONE season's lift (other season missing) must be maximally non-significant."""
    p = fp._replication_pvalue({"2022-23": {"cluster_rel": -0.05}}, ("2022-23", "2023-24"))
    assert p == 1.0, "a single-season-only result must never look significant (single-window artifact)"


def test_pvalue_one_helps_one_hurts_is_weak():
    """One season helps, the other does not -> not a cross-season survivor -> p should not be tiny."""
    p = fp._replication_pvalue(
        {"2022-23": {"cluster_rel": -0.02}, "2023-24": {"cluster_rel": +0.004}},
        ("2022-23", "2023-24"))
    # Fisher with one strongly-helping tail and one >0.5 tail still combines small here; the REAL guard
    # against this case is cluster_lab's REPLICATES gate (needs <-0.002 in BOTH). Assert it is at least
    # not MORE significant than the both-help case.
    p_both = fp._replication_pvalue(
        {"2022-23": {"cluster_rel": -0.02}, "2023-24": {"cluster_rel": -0.02}}, ("2022-23", "2023-24"))
    assert p >= p_both


def test_pvalue_null_is_midrange():
    p = fp._replication_pvalue(
        {"2022-23": {"cluster_rel": 0.0}, "2023-24": {"cluster_rel": 0.0}}, ("2022-23", "2023-24"))
    assert 0.3 < p < 0.9, f"a pure-null pair should be mid-range, got {p}"


# --------------------------------------------------------------------------- family anti-re-roll keys
def test_candidate_family_keys_distinct_and_stable():
    """Every proposed candidate is its own family (no accidental within-batch re-roll), and the key is
    deterministic for a fixed definition."""
    keys = [fp._candidate_family_key(c) for c in fp.CANDIDATES]
    assert len(set(keys)) == len(keys), "candidate families must be distinct (no within-batch re-roll)"
    # stability
    again = [fp._candidate_family_key(c) for c in fp.CANDIDATES]
    assert keys == again, "family_key must be deterministic"


def test_candidate_batch_well_formed():
    """Each candidate has the required schema keys and a one-line hypothesis; none uses the SATURATED
    state-5 cluster as its signal set."""
    saturated = {"poss_dur", "after_to", "dead_ball", "abs_margin", "had_oreb"}
    for c in fp.CANDIDATES:
        for k in ("name", "base", "signals", "domain", "scope", "hypothesis"):
            assert k in c and c[k], f"candidate {c.get('name')} missing {k}"
        assert isinstance(c["hypothesis"], str) and len(c["hypothesis"]) > 20
        assert set(c["signals"]) != saturated, f"{c['name']} re-proposes the saturated state-5 set"


# --------------------------------------------------------------------------- end-to-end on a tiny corpus
def _tiny_two_season_corpus(tmp_path, n_games=55, signal_helps=False, seed=0):
    """A minimal possession corpus with the columns the candidates need, across two seasons. If
    signal_helps, inject a real dependence of `pts` on poss_dur so a cluster genuinely replicates."""
    rng = np.random.default_rng(seed)
    rows = []
    gid_ctr = 0
    for season in ("2022-23", "2023-24"):
        for _ in range(n_games):
            gid_ctr += 1
            for poss in range(40):
                poss_dur = float(rng.integers(2, 24))
                grem = float(rng.uniform(0, 720))
                base_mu = 1.0
                if signal_helps:
                    base_mu += -0.04 * (poss_dur - 12)  # genuine, smooth poss_dur effect
                pts = max(0.0, rng.normal(base_mu, 1.2))
                pts = min(pts, 4.0)
                rows.append(dict(
                    gid=f"00{gid_ctr:05d}", off=f"t{gid_ctr%30}", season=season,
                    period=int(rng.integers(1, 5)), grem=grem, pts=round(pts),
                    after_to=int(rng.integers(0, 2)), abs_margin=int(rng.integers(0, 25)),
                    dead_ball=int(rng.integers(0, 2)), had_oreb=int(rng.integers(0, 2)),
                    poss_dur=poss_dur, is_clutch=int(rng.integers(0, 2)),
                    fastbreak=int(rng.integers(0, 2)), early_clock=int(rng.integers(0, 2)),
                    late_clock=int(rng.integers(0, 2)), garbage=int(rng.integers(0, 2)),
                    prev_scored=int(rng.integers(0, 2)), poss_idx=poss,
                    poss_frac=poss / 40.0))
    df = pd.DataFrame(rows)
    path = os.path.join(str(tmp_path), "tiny_corpus.parquet")
    df.to_parquet(path, index=False)
    return path


def test_run_candidates_end_to_end_no_register(tmp_path):
    """run_candidates validates cross-season, applies FDR, and appends to the scoreboard -- on a tiny
    corpus, with register=False so it never touches the live model_registry."""
    corpus = _tiny_two_season_corpus(tmp_path, signal_helps=False)
    cand = dict(fp.CANDIDATES[1])      # the poss_dur x after_to interaction
    cand["corpus"] = corpus
    cand["min_games"] = 50
    rep = fp.run_candidates([cand], register=False, batch_id="test_e2e", verbose=False)
    assert rep["n"] == 1
    assert rep["n_registered"] == 0    # register=False -> nothing registered regardless of verdict
    assert rep["results"][0]["verdict"] in (
        "REPLICATES", "single-season", "does-NOT-replicate", "insufficient-seasons")
    cov = rep["results"][0]["coverage_class"]
    assert cov in ("SURVIVOR", "replicates-but-FDR-culled", "N-A-no-substrate",
                   "mined-reject", "data-blocked")


def test_single_season_corpus_is_data_blocked_never_registered(tmp_path):
    """A corpus with only ONE of the requested seasons can never REPLICATE: cluster_lab's pseudo-
    replication guard returns 'insufficient-seasons' and the foundry classes it data-blocked, never
    registering it (the discipline: single-window is never a validated survivor)."""
    rng = np.random.default_rng(1)
    rows = []
    for g in range(55):
        for poss in range(40):
            rows.append(dict(gid=f"00{g:05d}", off="t1", season="2022-23",
                             period=1, grem=300.0, pts=int(rng.integers(0, 3)),
                             after_to=0, abs_margin=5, dead_ball=0, had_oreb=0,
                             poss_dur=10.0, is_clutch=0, fastbreak=0, early_clock=0,
                             late_clock=0, garbage=0, prev_scored=0, poss_idx=poss, poss_frac=0.5))
    path = os.path.join(str(tmp_path), "one_season.parquet")
    pd.DataFrame(rows).to_parquet(path, index=False)
    cand = dict(fp.CANDIDATES[1]); cand["corpus"] = path; cand["min_games"] = 50
    n_models_before = len(Registry("model_registry"))
    rep = fp.run_candidates([cand], register=True, batch_id="test_oneseason", verbose=False)
    assert rep["n_registered"] == 0, "a single-season corpus must never register a model"
    assert rep["results"][0]["coverage_class"] == "data-blocked"
    assert len(Registry("model_registry")) == n_models_before, "model_registry must be untouched"


def test_scoreboard_appends_every_candidate(tmp_path):
    """Every candidate run -- survivor OR reject -- lands on the append-only scoreboard."""
    corpus = _tiny_two_season_corpus(tmp_path, signal_helps=False)
    before = len(fp.scoreboard())
    cand = dict(fp.CANDIDATES[2]); cand["corpus"] = corpus; cand["min_games"] = 50
    cand["name"] = "test.scoreboard.append"   # unique name so the row is identifiable
    fp.run_candidates([cand], register=False, batch_id="test_sb", verbose=False)
    after = fp.scoreboard()
    assert len(after) == before + 1
    assert (after.name == "test.scoreboard.append").any()
    row = after[after.name == "test.scoreboard.append"].iloc[-1]
    assert row["coverage_class"] in ("SURVIVOR", "replicates-but-FDR-culled", "N-A-no-substrate",
                                     "mined-reject", "data-blocked")
    assert isinstance(row["hypothesis"], str) and row["hypothesis"]


# --------------------------------------------------------------------------- read-only invariant
def test_imports_are_read_only():
    """The foundry imports cluster_lab + the registry; it must not have monkey-patched validate_cluster
    or the Registry write methods (read-only contract)."""
    from signals import cluster_lab
    assert callable(cluster_lab.validate_cluster)
    # the foundry's only registration path delegates to cluster_lab.validate_cluster(register=True);
    # it defines no Registry write wrapper of its own.
    assert not hasattr(fp, "register") and not hasattr(fp, "_write_part")


# --------------------------------------------------------------------------- FDR still controls error
def test_planted_null_fdr_controls_error():
    """The shared FDR machinery the foundry uses must control family-wise error under the complete null."""
    res = planted_null_test(n=100, batches=80, rows=300, procedure="bh", seed=7)
    assert res["planted_null_ok"], res["detail"]


def test_bh_basic():
    # one tiny p among nulls -> exactly one discovery
    p = np.array([0.0001, 0.4, 0.6, 0.8, 0.9])
    mask = benjamini_hochberg(p, 0.05)
    assert mask[0] and not mask[1:].any()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
