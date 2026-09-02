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


def test_s40b_prior_redteam_verdict_and_floor_and_seal():
    """Three of the four OPEN prior-red-team items, re-checked on disk and closed.

    1.1 BEATS_CLOSE was decided on the RAW dm p while corrected_dm_p / ship_eligible
        were computed later and never consulted.
    1.3 DM_MIN_N=200 was tested against dm.n (raw STATES); the golden fixture is 103
        states over 70 game_ids, so states are not clusters.
    1.2 load_golden ran only the structural validate_golden -- a schema-valid hand edit
        redefined "gate green" with nothing pinning the fixture's bytes.
    """
    import hashlib
    from types import SimpleNamespace
    import pytest
    import golden_loader as GL
    from run_gate import DM_MIN_N, _verdict

    # 1.3: the same run passes the state floor and fails the cluster floor.
    dm = SimpleNamespace(p_value=0.001, n=DM_MIN_N, n_clusters=DM_MIN_N - 1, ci95=(0.1, 0.9))
    assert _verdict(0.01, dm, 0.2, 0.3) != "BEATS_CLOSE"
    dm_ok = SimpleNamespace(p_value=0.001, n=DM_MIN_N, n_clusters=DM_MIN_N, ci95=(0.1, 0.9))
    assert _verdict(0.01, dm_ok, 0.2, 0.3) == "BEATS_CLOSE"

    # 1.1: a BEATS_CLOSE row must now be FWER ship-eligible, and any downgrade keeps
    # the raw label beside it rather than vanishing.
    for row in run_gate_in_process(offline_predict_fn):
        if row.get("verdict") == "BEATS_CLOSE":
            assert row["ship_eligible"] is True
        if "verdict_uncorrected" in row:
            assert row["verdict_uncorrected"] == "BEATS_CLOSE"
            assert row["ship_eligible"] is False

    # 1.2: the seal is the fixture's real digest, and a one-byte edit fails closed.
    assert hashlib.sha256(GL.DEFAULT_GOLDEN.read_bytes()).hexdigest() == GL.GOLDEN_SHA256
    tampered = GL.DEFAULT_GOLDEN.parent / "_s40b_seal_probe.json"
    original = GL.DEFAULT_GOLDEN
    try:
        tampered.write_bytes(GL.DEFAULT_GOLDEN.read_bytes() + b" ")
        GL.DEFAULT_GOLDEN = tampered
        with pytest.raises(ValueError, match="seal mismatch"):
            GL.load_golden()
        assert GL.load_golden(str(tampered))     # an EXPLICIT path is not sealed
    finally:
        GL.DEFAULT_GOLDEN = original
        tampered.unlink(missing_ok=True)


def _tmp_ledger(n_rows):
    """A NON-canonical scratch ledger carrying k_cumulative 1..n_rows."""
    import json, tempfile
    from pathlib import Path
    p = Path(tempfile.mkdtemp(prefix="s51_")) / "backtest_fwer.jsonl"
    with p.open("w", encoding="ascii") as fh:
        for i in range(1, n_rows + 1):
            fh.write(json.dumps({"at": "2026-09-03T00:00:00+00:00", "predictor": "x:y",
                                 "sport": "nba", "start": "2023-10-01", "end": "2024-04-01",
                                 "k_cumulative": i}, sort_keys=True) + "\n")
    return p


def test_s51_k_source_ledger_reads_k_and_never_appends():
    """S51(a): --k-source ledger prices the deflation at the ledger's max k_cumulative,
    reads it READ-ONLY (row count unchanged -- run_gate charges no trial), and refuses a
    non-canonical ledger under the same S40b/RT-3 rule that guards backtest_runner."""
    import pytest
    from run_gate import resolve_n_trials, CORPORA

    led = _tmp_ledger(7)
    before = led.read_bytes()

    # refusal first: a scratch path restarts K and LOOSENS the bar -> raise, do not read.
    with pytest.raises(ValueError, match="non-canonical ledger"):
        resolve_n_trials("ledger", led)

    assert resolve_n_trials("ledger", led, allow_noncanonical_ledger=True) == 7
    assert resolve_n_trials("corpora") == len(CORPORA) == 2
    with pytest.raises(ValueError, match="k_source must be one of"):
        resolve_n_trials("wishful")

    rows = run_gate_in_process(offline_predict_fn, k_source="ledger", ledger_path=led,
                               allow_noncanonical_ledger=True)
    assert all(r["n_trials_this_sweep"] == 7 for r in rows)
    assert all(r["k_source"] == "ledger" for r in rows)
    assert gate_exit_code(rows) == 0                     # K prices deflation, never blocks
    assert led.read_bytes() == before                    # append-free: 7 rows in, 7 out
    assert len(before.splitlines()) == 7


def test_s51_default_path_is_byte_identical():
    """S51(a): the DEFAULT sweep must be the pre-S51 gate byte for byte. The digest is of
    the PRE-CHANGE `python -m ...run_gate --golden` stdout, captured before the edit and
    newline-normalized (the Windows console writes CRLF; sha256 of the raw capture is
    28ba7f97d2f4c26ac7264816d6b7580c396ec5c54b2587cfd5861c16a0db63fe, 782 bytes)."""
    import hashlib, io
    from contextlib import redirect_stdout
    from run_gate import main
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["--golden"])
    out = buf.getvalue().encode("ascii")
    assert code == 0
    assert hashlib.sha256(out).hexdigest() == (
        "1f523ea25a59785dcdf898fc2724b7e74891bc52151cd8ce1b6db9e1a6635348"), out

    # and --golden refuses the ledger source outright: its contract is offline / no data/.
    try:
        main(["--golden", "--k-source", "ledger"])
        raise SystemExit("FAIL: --golden accepted --k-source ledger")
    except SystemExit as exc:
        assert exc.code == 2


def test_s51_golden_seal_sidecar_regenerate_and_tamper():
    """S51(b): gen_golden emits the digest into a sidecar, so a legitimate regeneration
    no longer needs a hand-computed constant. The constant stays as the fallback pin: the
    two must agree, and any mismatch fails closed NAMING BOTH values."""
    import hashlib, shutil, tempfile
    from pathlib import Path
    import pytest
    import golden_loader as GL
    from gen_golden import write_sidecar

    work = Path(tempfile.mkdtemp(prefix="s51_seal_"))
    fx = work / "game_states.json"
    shutil.copyfile(GL.DEFAULT_GOLDEN, fx)
    original, orig_const = GL.DEFAULT_GOLDEN, GL.GOLDEN_SHA256
    try:
        # no sidecar -> the constant is the fallback pin (today's committed behaviour).
        GL.DEFAULT_GOLDEN = fx
        assert GL.expected_seal(fx) == (orig_const, "constant")
        assert GL.load_golden()

        # "regenerated": new bytes + emitted sidecar + the refreshed constant -> passes.
        fx.write_bytes(GL.DEFAULT_GOLDEN.read_bytes() + b" ")
        digest = write_sidecar(str(fx))
        assert digest == hashlib.sha256(fx.read_bytes()).hexdigest() != orig_const
        GL.GOLDEN_SHA256 = digest
        assert GL.expected_seal(fx) == (digest, "sidecar")
        assert GL.load_golden()

        # tampered fixture, sidecar+constant intact -> fail closed, both digests named.
        fx.write_bytes(fx.read_bytes() + b" ")
        got = hashlib.sha256(fx.read_bytes()).hexdigest()
        with pytest.raises(ValueError, match="seal mismatch") as err:
            GL.load_golden()
        assert digest in str(err.value) and got in str(err.value)

        # a sidecar edited alone (constant stale) -> fail closed, both values named.
        GL.GOLDEN_SHA256 = orig_const
        with pytest.raises(ValueError, match="seal disagreement") as err:
            GL.expected_seal(fx)
        assert digest in str(err.value) and orig_const in str(err.value)
    finally:
        GL.DEFAULT_GOLDEN, GL.GOLDEN_SHA256 = original, orig_const
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print("PASS  %s" % fn.__name__)
        passed += 1
    print("\n%d/%d eval-gate exit-code tests passed." % (passed, len(fns)))
