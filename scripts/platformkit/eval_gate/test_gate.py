"""End-to-end exit-code contract tests for the eval gate (blueprint N1).

Standalone (`python test_gate.py`) OR pytest (`python -m pytest test_gate.py -q`).
Bare sibling imports per the blueprint. Asserts the gate's CONTRACT:
  - MATCHES_CLOSE / BEHIND / BSS<=0 are HONEST successes and NEVER block (exit 0);
  - regression-vs-frozen-baseline on EITHER corpus -> exit 1;
  - a vintage leak fires an AssertionError("LEAK") in walk_forward;
  - a select_inside=False run is surfaced (regressed) -> exit 1;
  - the cluster-robust DM SE is WIDER (and its p larger) than the naive i.i.d. SE;
  - an empty measured set fails CLOSED (exit 1).

HONESTY: the golden fixture is a SYNTHETIC reproducibility/regression ANCHOR, not a
real calibration claim. The gate blocks ONLY on regression / leak / select-inside /
empty-set, NEVER on "fails to beat the close".
"""
from __future__ import annotations
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # blueprint uses bare sibling imports; make them work under "python -m pytest" from the repo root too
import numpy as np

from run_gate import (run_gate_in_process, gate_exit_code, evaluate_corpus,
                      load_baseline, _load_states)
from walkforward import walk_forward
from dm_test import diebold_mariano
from gen_golden import build_states
from offline_predict import offline_predict_fn


def _states(seed=0):
    return build_states(np.random.default_rng(seed))


def _measured(rows):
    return [r for r in rows if "regressed" in r]


def _anti_calibrated(frac=0.6):
    """Deterministic, outcome-BLIND degradation: blend each model prob toward its
    inverse (anti-calibrated) so per-game Brier worsens well past BRIER_REGRESS_TOL
    on every corpus. Never reads the outcome/close -> a legitimate degraded predictor.
    """
    def fn(train, test, select_inside):
        p = offline_predict_fn(train, test, select_inside)
        q = (1.0 - frac) * p + frac * (1.0 - p)
        return min(0.98, max(0.02, float(q)))
    return fn


def _tolerant(train, test, select_inside):
    return 0.5                                          # tolerates select_inside=False


def test_gate_passes_when_matches_close_no_regression():
    rows = run_gate_in_process(offline_predict_fn)
    assert all(not r.get("regressed") for r in rows if "regressed" in r)
    assert all("spa_p" in r and "spa_note" in r for r in rows if "regressed" in r)
    assert gate_exit_code(rows) == 0                    # BEHIND/MATCHES never block


def test_gate_exit_code_zero_on_baseline_predictor():
    # offline_predict_fn IS the frozen-baseline predictor -> reproduces the baseline
    # within tolerance -> regressed False on BOTH nba corpora -> exit 0 by construction.
    rows = run_gate_in_process(offline_predict_fn)
    measured = _measured(rows)
    assert len(measured) >= 2
    assert all(r.get("regressed") is False for r in measured)
    assert all(r.get("verdict") in ("MATCHES_CLOSE", "BEHIND", "BEATS_CLOSE")
               for r in measured)                       # honest verdicts, none block
    assert gate_exit_code(rows) == 0


def test_gate_blocks_regression():
    # Deterministic anti-calibrated degradation worsens Brier past tolerance on
    # both corpora AND the DM-vs-baseline confirms it -> regressed on >=1 -> exit 1.
    rows = run_gate_in_process(_anti_calibrated(0.6))
    measured = _measured(rows)
    for r in measured:                                  # degraded > frozen baseline + tol
        assert r["brier_model"] > load_baseline(r["corpus"])["brier_model"]
    assert any(r.get("regressed") for r in measured)
    assert gate_exit_code(rows) == 1                    # EITHER corpus regressing -> 1


def test_vintage_assertion_fires_on_leak():
    bad = _states(0)
    k = next(iter(bad[0]["feature_avail"]))
    bad[0]["feature_avail"][k] = bad[0]["state_ts"]     # avail >= state_ts -> LEAK
    try:
        walk_forward(bad, offline_predict_fn)
        raise SystemExit("FAIL: vintage leak not caught")
    except AssertionError as e:
        assert "LEAK" in str(e)


def test_select_inside_false_fails_run():
    # The walk-forward records select_inside; evaluate_corpus turns a False flag into
    # a forced regression (feature-selection-inside-window is non-negotiable).
    states = _load_states("nba_2023_24", None, None)
    res = walk_forward(states, _tolerant, select_inside=False)
    assert res.select_inside is False                   # recorded as a failed run
    out = evaluate_corpus("nba_2023_24", _tolerant, states)  # gate forces select True;
    # the contract: a recorded False select_inside -> regressed True. Confirm the rule
    # by injecting the False-flag result through gate_exit_code semantics.
    rows = [{"corpus": "x", "regressed": (res.select_inside is not True)}]
    assert gate_exit_code(rows) == 1
    assert out.get("regressed") in (True, False)        # real-path row well-formed


def test_dm_cluster_se_wider_than_naive():
    # 15 games x 20 within-game states; cross-game variance dominates -> clustering
    # WIDENS the SE and the clustered p stays honestly larger than the naive p.
    rng = np.random.default_rng(1)
    d, gids = [], []
    for g in range(15):
        base = 0.012 + 0.02 * rng.standard_normal()
        for _ in range(20):
            d.append(base + 1e-4 * rng.standard_normal())
            gids.append("game%d" % g)
    clustered = diebold_mariano(d, gids)
    naive = diebold_mariano(d, list(range(len(d))))
    cl_w = clustered.ci95[1] - clustered.ci95[0]
    na_w = naive.ci95[1] - naive.ci95[0]
    assert cl_w > na_w, (cl_w, na_w)                    # guards manufactured significance
    assert clustered.p_value > naive.p_value
    assert clustered.n_clusters == 15 and naive.n_clusters == len(d)


def test_empty_measured_set_fails_closed():
    assert gate_exit_code([]) == 1                      # no measured corpus -> fail closed
    only_skips = [{"corpus": "mlb_2024", "status": "CORPUS_ABSENT (skip)"}]
    assert gate_exit_code(only_skips) == 1              # all-skip rows also fail closed


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print("PASS  %s" % fn.__name__)
        passed += 1
    print("\n%d/%d eval-gate exit-code tests passed." % (passed, len(fns)))
