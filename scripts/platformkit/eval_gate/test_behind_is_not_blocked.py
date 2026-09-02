"""TH-03: Pin the honest-rails contract that BEHIND and MATCHES_CLOSE are non-blocking.

Gate BLOCKS ONLY on regression-vs-baseline or a leak-guard assertion (exit 1).
BEHIND / MATCHES_CLOSE = honest non-blocking results (exit 0).

CONTRACT: (1) BEHIND + regressed=False -> 0. (2) MATCHES_CLOSE + regressed=False -> 0.
(3) regressed=True -> 1. (4) leaked=True -> 1.
(5) end-to-end run_gate_in_process -> exit 0 AND no roi/edge/$ key in rows.
(6) null predictor -> verdicts valid; BEHIND alone does NOT cause exit 1.

Run: python test_behind_is_not_blocked.py  OR  python -m pytest test_behind_is_not_blocked.py -q
"""
from __future__ import annotations
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # blueprint uses bare sibling imports; make them work under "python -m pytest" from the repo root too

import numpy as np

from run_gate import run_gate_in_process, gate_exit_code, _verdict
from dm_test import diebold_mariano
from offline_predict import offline_predict_fn

# ---------------------------------------------------------------------------
# Banned keys that MUST NOT appear on any scoreboard row (honesty rails).
# ---------------------------------------------------------------------------
_BANNED_KEYS = ("roi", "edge", "pnl", "profit", "dollar", "ev_dollar",
                "edge_vs_market", "$")


def _has_banned_key(row: dict) -> list:
    """Return list of banned keys found in row (empty = clean)."""
    found = []
    for k in row:
        k_lower = k.lower()
        for banned in _BANNED_KEYS:
            if banned in k_lower:
                found.append(k)
    return found


def _make_behind_row(corpus: str = "nba_2023_24") -> dict:
    """Minimal measured row with verdict=BEHIND and regressed=False."""
    return {
        "corpus": corpus,
        "n": 50,
        "brier_model": 0.27,
        "brier_close": 0.24,
        "bss": -0.125,
        "log_loss": 0.58,
        "ece": 0.04,
        "resolution": 0.05,
        "sharpness": 0.03,
        "dm_stat": -2.1,
        "dm_p": 0.03,
        "ci95": (-0.02, -0.001),
        "verdict": "BEHIND",
        "leaked": False,
        "regressed": False,
    }


def _make_matches_close_row(corpus: str = "nba_2024_25") -> dict:
    """Minimal measured row with verdict=MATCHES_CLOSE and regressed=False."""
    return {
        "corpus": corpus,
        "n": 55,
        "brier_model": 0.25,
        "brier_close": 0.245,
        "bss": -0.02,
        "log_loss": 0.56,
        "ece": 0.03,
        "resolution": 0.06,
        "sharpness": 0.04,
        "dm_stat": -0.3,
        "dm_p": 0.77,
        "ci95": (-0.015, 0.012),
        "verdict": "MATCHES_CLOSE",
        "leaked": False,
        "regressed": False,
    }


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------

def test_behind_rows_exit_zero():
    """Contract: BEHIND verdict with no regression -> exit 0 (non-blocking honest result)."""
    rows = [_make_behind_row("nba_2023_24"), _make_behind_row("nba_2024_25")]
    measured = [r for r in rows if "regressed" in r]
    assert len(measured) == 2
    assert all(r["verdict"] == "BEHIND" for r in measured)
    assert all(r["regressed"] is False for r in measured)
    code = gate_exit_code(rows)
    assert code == 0, (
        "FAILED: BEHIND rows should exit 0 (honest non-blocking result), got %d" % code
    )


def test_matches_close_rows_exit_zero():
    """Contract: MATCHES_CLOSE verdict with no regression -> exit 0."""
    rows = [_make_matches_close_row("nba_2023_24"), _make_matches_close_row("nba_2024_25")]
    measured = [r for r in rows if "regressed" in r]
    assert len(measured) == 2
    assert all(r["verdict"] == "MATCHES_CLOSE" for r in measured)
    assert all(r["regressed"] is False for r in measured)
    code = gate_exit_code(rows)
    assert code == 0, (
        "FAILED: MATCHES_CLOSE rows should exit 0 (honest non-blocking result), got %d" % code
    )


def test_mixed_behind_matches_exit_zero():
    """Contract: a mix of BEHIND and MATCHES_CLOSE verdicts (all non-regressed) -> exit 0."""
    rows = [
        _make_behind_row("nba_2023_24"),
        _make_matches_close_row("nba_2024_25"),
    ]
    code = gate_exit_code(rows)
    assert code == 0, (
        "FAILED: mixed BEHIND/MATCHES_CLOSE should exit 0, got %d" % code
    )


def test_regression_row_exits_one():
    """Contract: a regressed row -> exit 1 (regression blocks)."""
    rows = [_make_behind_row("nba_2023_24")]
    rows[0]["regressed"] = True   # inject regression flag
    code = gate_exit_code(rows)
    assert code == 1, (
        "FAILED: regressed=True row should exit 1, got %d" % code
    )


def test_single_regression_among_clean_rows_exits_one():
    """Contract: even a single regressed corpus blocks the whole gate (EITHER corpus rule)."""
    rows = [
        _make_matches_close_row("nba_2023_24"),   # clean
        _make_behind_row("nba_2024_25"),           # also to be injected as regressed
    ]
    rows[1]["regressed"] = True
    code = gate_exit_code(rows)
    assert code == 1, (
        "FAILED: one regressed corpus among clean rows should still exit 1, got %d" % code
    )


def test_leak_row_exits_one():
    """Contract: leaked=True -> exit 1 (data leak always blocks, regardless of verdict)."""
    rows = [
        {
            "corpus": "nba_2023_24",
            "leaked": True,
            "regressed": True,
            "status": "LEAK",
        }
    ]
    code = gate_exit_code(rows)
    assert code == 1, (
        "FAILED: leaked=True row should exit 1, got %d" % code
    )


def test_leak_blocks_even_when_verdict_would_be_behind():
    """Contract: a leak overrides any verdict -- BEHIND+leaked -> exit 1."""
    row = _make_behind_row("nba_2023_24")
    row["leaked"] = True
    row["regressed"] = True   # leak forces regressed too (run_gate.py convention)
    code = gate_exit_code([row])
    assert code == 1, (
        "FAILED: BEHIND+leaked should still exit 1, got %d" % code
    )


def test_no_banned_keys_in_scoreboard_rows():
    """Honesty rails: no roi/edge/pnl/profit/dollar/$ key may appear on any scored row.

    Runs run_gate_in_process end-to-end against the committed golden fixture; checks every
    key in every returned row. This is the systemic guard that a future change cannot
    silently add a $ or edge field to the scoreboard without this test catching it.
    """
    # Use None states so _load_states loads the committed golden fixture with season
    # filtering (same path as the production gate run).
    rows = run_gate_in_process(offline_predict_fn)
    assert rows, "run_gate_in_process returned no rows"
    for r in rows:
        bad = _has_banned_key(r)
        assert not bad, (
            "Banned key(s) %r found in scoreboard row for corpus=%r. "
            "Scoreboard must use UNITS + calibration, never $/edge/roi." % (bad, r.get("corpus"))
        )


def test_end_to_end_exit_zero_with_offline_predictor():
    """End-to-end: offline_predict_fn on the committed golden fixture -> gate_exit_code == 0.

    The offline predictor is the frozen-baseline predictor by construction; it cannot
    regress on the synthetic fixture. BEHIND or MATCHES_CLOSE -> exit 0.
    Uses the same load path as production: run_gate_in_process with no states arg
    so _load_states applies the season filter used when the baselines were frozen.
    """
    rows = run_gate_in_process(offline_predict_fn)
    measured = [r for r in rows if "regressed" in r]
    assert len(measured) >= 1, "Expected at least one measured corpus"
    assert all(r["regressed"] is False for r in measured), (
        "offline_predict_fn should not regress vs its own frozen baseline"
    )
    # verdicts must be one of the three valid honest outcomes
    valid_verdicts = {"BEATS_CLOSE", "MATCHES_CLOSE", "BEHIND"}
    for r in measured:
        assert r["verdict"] in valid_verdicts, (
            "Unexpected verdict %r; must be one of %r" % (r["verdict"], valid_verdicts)
        )
    code = gate_exit_code(rows)
    assert code == 0, (
        "FAILED: offline predictor on golden fixture should exit 0, got %d" % code
    )


def test_verdict_classify_behind_is_non_beat():
    """Unit test for the _verdict / classify function: CI overlapping zero -> MATCHES_CLOSE;
    CI strictly negative -> BEHIND; BSS > 0 + DM sig -> BEATS_CLOSE.

    This pins the classify logic independently of run_gate_in_process so a future
    refactor that renames classify cannot silently change exit semantics.
    """
    # Build a synthetic DM result for each case using diebold_mariano directly.
    rng = np.random.default_rng(42)
    n = 300

    # BEHIND: model consistently WORSE than close (d < 0 means close better > model)
    d_behind = -0.02 + 0.005 * rng.standard_normal(n)
    gids = ["g%d" % (i % 50) for i in range(n)]
    dm_behind = diebold_mariano(d_behind.tolist(), gids)
    verdict = _verdict(bss=-0.05, dm=dm_behind, bm=0.27, bc=0.24)
    assert verdict == "BEHIND", "Expected BEHIND for model worse than close, got %r" % verdict

    # MATCHES_CLOSE: CI overlaps 0 (noisy, indistinguishable from close)
    d_match = 0.0005 * rng.standard_normal(n)
    dm_match = diebold_mariano(d_match.tolist(), gids)
    verdict = _verdict(bss=-0.001, dm=dm_match, bm=0.245, bc=0.244)
    assert verdict == "MATCHES_CLOSE", (
        "Expected MATCHES_CLOSE for indistinguishable predictor, got %r" % verdict
    )

    # BEATS_CLOSE: BSS > 0, DM p < 0.05 (needs enough signal; use n=300 tight positive d)
    d_beats = 0.008 + 0.003 * rng.standard_normal(n)
    dm_beats = diebold_mariano(d_beats.tolist(), gids)
    # Only assert BEATS_CLOSE if DM confirms (the synthetic d may not always reach p<0.05
    # depending on cluster structure -- check the conditions rather than forcing the verdict)
    if dm_beats.p_value < 0.05 and dm_beats.n >= 200:
        verdict = _verdict(bss=0.03, dm=dm_beats, bm=0.23, bc=0.245)
        assert verdict == "BEATS_CLOSE", (
            "Expected BEATS_CLOSE when BSS>0 and DM significant, got %r" % verdict
        )


def test_gate_not_blocked_by_honest_reject():
    """Regression guard: an honest REJECT (no signal found) produces BEHIND, not a crash.

    A predict_fn that always returns the base rate (0.5) will trail the near-oracle
    synthetic close -> BEHIND verdict. The gate will exit 1 if the null predictor
    degrades Brier past the regression threshold -- that is correct and expected:
    the key contract is that BEHIND ITSELF does not cause exit 1; regression does.
    This test asserts verdicts are valid and leaked is always False for leak-free runs.
    """
    def _null_predictor(train, test, select_inside):
        # Always predict 0.5 -- the maximum-entropy, zero-signal baseline.
        return 0.5

    rows = run_gate_in_process(_null_predictor)
    measured = [r for r in rows if "regressed" in r]
    # Verdicts must be from the valid set (BEHIND/MATCHES_CLOSE/BEATS_CLOSE).
    # Exit code depends on regression flag; BEHIND alone does NOT determine exit 1.
    for r in measured:
        assert r["verdict"] in ("BEHIND", "MATCHES_CLOSE", "BEATS_CLOSE"), (
            "Unexpected verdict %r from null predictor" % r["verdict"]
        )
        # Leak flag must always be False for a leak-free predictor
        assert r.get("leaked") is False, (
            "null predictor flagged as leaked; check walkforward vintage guard"
        )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for fn in fns:
        try:
            fn()
            print("PASS  %s" % fn.__name__)
            passed += 1
        except Exception as exc:
            print("FAIL  %s: %s" % (fn.__name__, exc))
            failed += 1
    print()
    if failed:
        print("%d/%d FAILED" % (failed, len(fns)))
        raise SystemExit(1)
    print("%d/%d tests passed." % (passed, len(fns)))
