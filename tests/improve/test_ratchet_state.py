"""Per-file test for the Milestone-8 self-improvement FSM (improve.ratchet_state).

Run ONLY this file (a bare pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && \
      conda run -n <env> python -m pytest tests/improve/test_ratchet_state.py -q

Covers the ratchet honesty invariant + FSM idempotency:
  - ALL gates pass -> SHIP and the artifact is promoted to CURRENT,
  - ANY single gate failing -> REJECT (parametrized per gate; a partial pass is
    NEVER a ship),
  - checkpoint resume is idempotent: a decided fingerprint is not re-evaluated,
    so SHIP never double-promotes and REJECT honors its backoff.
"""
from __future__ import annotations

import sys
import pathlib

import numpy as np
import pytest

# Import via the `improve.` package path so the CalibArtifact the test builds is
# byte-identical to the one registry.py / ratchet_state.py import (a sys.path
# inject of improve/ would create a second module object and break isinstance).
_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from improve.calib_artifact import CalibArtifact  # noqa: E402
from improve import ratchet_state as rs  # noqa: E402
from improve import registry  # noqa: E402


# --------------------------------------------------------------------------
# Builders for a fully-passing candidate. Base predictions are deliberately bad
# and the candidate strictly better on every proper score, so proper_score,
# seed_stability and multifold all pass; parity + integrity are constructed clean.
# --------------------------------------------------------------------------

def _passing_kwargs(n_features=4, root=None, declare_meta=True):
    rng = np.random.default_rng(0)
    n = 400
    y = (rng.random(n) < 0.5).astype(float)
    # base: uninformative 0.5; cand: confidently correct -> strictly better Brier+logloss
    base = np.full(n, 0.5)
    cand = np.where(y > 0.5, 0.9, 0.1)

    # multifold: every fold/metric strictly positive in primary + one extra corpus
    folds = [{"fold_id": i, "metric": "brier", "delta": 0.05} for i in range(4)]
    folds += [{"fold_id": i, "metric": "logloss", "delta": 0.04} for i in range(4)]
    corpora = [{"corpus_id": "B",
                "folds": [{"fold_id": j, "metric": "brier", "delta": 0.03}
                          for j in range(3)]}]

    # seed_stability: metric_fn returns a positive improvement regardless of split
    def metric_fn(train_rows, test_rows):
        return 0.02  # baseline_score - candidate_score > 0 everywhere -> p10 >= 0

    meta = {"corpora": ["A", "B"], "kfold": 4}
    if declare_meta:
        meta["n_features_in"] = n_features
    art = CalibArtifact(
        version=1, created_at="2026-06-18T00:00:00+00:00",
        kind="unit_ratchet", n_features_in=n_features,
        params={"w": [0.1] * n_features}, meta=meta,
    )
    feats = {"f%d" % i: float(i + 1) for i in range(n_features)}
    return dict(
        base_preds=base, cand_preds=cand, y=y, kind="prob",
        corpora=corpora, fold_results=folds,
        stability_metric_fn=metric_fn, stability_data=list(range(50)),
        train_features=dict(feats), infer_features=dict(feats),
        artifact=art, min_folds=4, min_corpora=2, n_boot=20,
        registry_root=root,
    )


def test_all_gates_pass_ships_and_promotes(tmp_path):
    kw = _passing_kwargs(root=str(tmp_path))
    res = rs.evaluate_candidate(**kw)
    assert res["ship"] is True, res["reasons"]
    gr = res["gate_results"]
    assert gr["proper_score"]["ship"] is True
    assert gr["seed_stability"].stable is True
    assert gr["multifold"]["replicated"] is True
    assert gr["parity"]["ok"] is True
    assert gr["integrity"] is True
    # promoted to CURRENT
    assert res["shipped_version"] is not None
    live = registry.current("unit_ratchet", root=str(tmp_path))
    assert live is not None and live.version == res["shipped_version"]


def _break_proper_score(kw):
    # candidate WORSE than base on Brier+logloss -> dissent
    kw["base_preds"] = np.where(kw["y"] > 0.5, 0.9, 0.1)
    kw["cand_preds"] = np.full(len(kw["y"]), 0.5)


def _break_seed_stability(kw):
    kw["stability_metric_fn"] = lambda a, b: -0.02  # negative improvement -> p10 < 0


def _break_multifold(kw):
    kw["corpora"] = []  # only primary corpus -> < 2 corpora -> not replicated


def _break_parity(kw):
    infer = dict(kw["infer_features"])
    first = sorted(infer)[0]
    infer[first] = 0.0  # zero-read against a non-zero train value
    kw["infer_features"] = infer


def _break_integrity(kw):
    # artifact claims n_features_in=4 but its meta declares 7 -> integrity REJECT
    art = kw["artifact"]
    bad_meta = dict(art.meta)
    bad_meta["n_features_in"] = art.n_features_in + 3
    kw["artifact"] = CalibArtifact(
        version=art.version, created_at=art.created_at, kind=art.kind,
        n_features_in=art.n_features_in, params=art.params, meta=bad_meta)


@pytest.mark.parametrize("breaker,gate_key", [
    (_break_proper_score, "proper_score"),
    (_break_seed_stability, "seed_stability"),
    (_break_multifold, "multifold"),
    (_break_parity, "parity"),
    (_break_integrity, "integrity"),
])
def test_any_single_gate_failure_rejects(tmp_path, breaker, gate_key):
    kw = _passing_kwargs(root=str(tmp_path))
    breaker(kw)
    res = rs.evaluate_candidate(**kw)
    assert res["ship"] is False, "a partial pass must never ship (%s)" % gate_key
    assert res["shipped_version"] is None
    # nothing went live
    assert registry.current("unit_ratchet", root=str(tmp_path)) is None
    # the failing gate is named in the honest reasons
    assert any(gate_key.split("_")[0] in r for r in res["reasons"]), res["reasons"]


def test_checkpoint_resume_is_idempotent_no_double_promote(tmp_path):
    ckpt = str(tmp_path / "state.json")
    root = str(tmp_path / "calib")
    fp = "cand-abc123"
    kw = _passing_kwargs(root=root)

    r1 = rs.run_cycle(fp, kw, ckpt=ckpt)
    assert r1["status"] == "decided" and r1["ship"] is True
    v1 = r1["shipped_version"]
    assert v1 is not None
    assert registry.list_versions("unit_ratchet", root=root) == [v1]

    # Re-present the SAME fingerprint (simulated restart): must NOT re-evaluate
    # or re-promote -> no second version saved, current unchanged.
    kw2 = _passing_kwargs(root=root)
    r2 = rs.run_cycle(fp, kw2, ckpt=ckpt)
    assert r2["status"] == "skipped_already_decided"
    assert r2["ship"] is True and r2["shipped_version"] == v1
    assert registry.list_versions("unit_ratchet", root=root) == [v1]
    assert registry.current("unit_ratchet", root=root).version == v1


def test_rejected_candidate_held_under_backoff(tmp_path):
    ckpt = str(tmp_path / "state.json")
    root = str(tmp_path / "calib")
    fp = "cand-bad"
    kw = _passing_kwargs(root=root)
    _break_multifold(kw)

    r1 = rs.run_cycle(fp, kw, ckpt=ckpt, backoff_sec=1000.0, now=100.0)
    assert r1["status"] == "decided" and r1["ship"] is False

    # Inside the backoff window -> skipped_backoff (not re-evaluated every tick).
    r2 = rs.run_cycle(fp, kw, ckpt=ckpt, backoff_sec=1000.0, now=500.0)
    assert r2["status"] == "skipped_backoff"

    # After the window -> still recognized as already-decided (no re-promote risk).
    r3 = rs.run_cycle(fp, kw, ckpt=ckpt, backoff_sec=1000.0, now=2000.0)
    assert r3["status"] == "skipped_already_decided"
    assert registry.current("unit_ratchet", root=root) is None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
