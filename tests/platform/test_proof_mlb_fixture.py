"""tests.platform.test_proof_mlb_fixture -- MLB proofs reproduce on the committed fixture.

Verifies the SHARED corpus-override contract for the three MLB proofs:
  - setting $PROOF_CORPUS_ROOT (or passing corpus=) makes run() read the tiny committed
    fixture at tests/fixtures/proof/mlb/ instead of the real data/domains corpus;
  - each proof returns status=='ok' with a FINITE numeric gap and n_holdout/n_checkpoints>0;
  - the beat-the-close verdict classification is computable (non-empty string);
  - default behavior (no env, no arg) still resolves to the real data/domains path.

Leak guard: the Elo / run-rate snapshot is recorded BEFORE the rating update, so the
held-out forecasts never see their own outcome -- asserted structurally here by requiring a
finite (not degenerate) Brier/RMSE on a held-out second half with both classes present.

Per-file run (NEVER full pytest -- freezes the box):
    python -m pytest tests/platform/test_proof_mlb_fixture.py -q
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = _REPO / "tests" / "fixtures" / "proof"
_MLB = _FIXTURE_ROOT / "mlb"


def _ensure_fixture() -> None:
    """Regenerate the fixture if a parquet is missing (deterministic, committed too)."""
    if not (_MLB / "games.parquet").is_file():
        from tests.fixtures.proof.mlb import _gen
        _gen.build()


@pytest.fixture(autouse=True)
def _clean_env():
    prev = os.environ.pop("PROOF_CORPUS_ROOT", None)
    _ensure_fixture()
    yield
    if prev is not None:
        os.environ["PROOF_CORPUS_ROOT"] = prev
    else:
        os.environ.pop("PROOF_CORPUS_ROOT", None)


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def test_fixture_files_present_and_committed():
    for f in ("games.parquet", "odds.parquet", "pitchers.parquet"):
        p = _MLB / f
        assert p.is_file(), f"missing fixture {p}"
        assert p.stat().st_size < 200_000, f"fixture {f} too big (<200KB required)"


def test_beat_the_close_ml_fixture_env_and_arg():
    from scripts.platformkit.proof_mlb import beat_the_close_ml as ml

    # via explicit corpus= arg
    r_arg = ml.run(corpus=_MLB)
    # via $PROOF_CORPUS_ROOT env (scoreboard sets this, calls run() with no args)
    os.environ["PROOF_CORPUS_ROOT"] = str(_FIXTURE_ROOT)
    try:
        r_env = ml.run()
    finally:
        os.environ.pop("PROOF_CORPUS_ROOT", None)

    for r in (r_arg, r_env):
        assert r["status"] == "ok", r
        assert r["n_holdout"] > 0
        assert _finite(r["gap"]), r["gap"]
        assert _finite(r["model_brier"]) and _finite(r["close_brier"])
        # verdict classification is computable + one of the three honest buckets
        assert isinstance(r["verdict"], str) and r["verdict"]
        assert r["verdict"].split(":")[0] in {"BEATS", "MATCH", "BEHIND"}
        # base home-win rate present -> both classes occur in the held-out half (leak-safe eval)
        assert 0.0 < r["base_home_rate"] < 1.0
    # env and arg routes must agree exactly (same fixture)
    assert r_arg["gap"] == r_env["gap"]
    assert r_arg["model_brier"] == r_env["model_brier"]


def test_beat_the_close_total_fixture():
    from scripts.platformkit.proof_mlb import beat_the_close_total as tot

    os.environ["PROOF_CORPUS_ROOT"] = str(_FIXTURE_ROOT)
    try:
        r = tot.run()
    finally:
        os.environ.pop("PROOF_CORPUS_ROOT", None)

    assert r["status"] == "ok", r
    assert r["n_holdout"] > 0
    assert _finite(r["gap"]) and _finite(r["model_total_rmse"]) and _finite(r["close_total_rmse"])
    assert r["model_total_rmse"] > 0 and r["close_total_rmse"] > 0
    assert isinstance(r["verdict"], str) and r["verdict"]
    assert r["verdict"].split(":")[0] in {"OUR run-rate totals model BEATS the close on RMSE",
                                          "MATCH", "BEHIND"}


def test_ingame_accuracy_fixture_and_leak_guard():
    from scripts.platformkit.proof_mlb import ingame_accuracy as ig

    r = ig.run(corpus=_MLB)
    assert r["status"] == "ok", r
    assert r["n_checkpoints"] > 0 and r["n_games"] > 0
    # three forecasters all produce finite Brier on the held-out (or full) checkpoints
    for k in ("brier_pregame", "brier_scoreonly", "brier_combined"):
        assert _finite(r[k]) and 0.0 < r[k] < 1.0, (k, r[k])
    # calibration block computed (leak-free: recal fit on TRAIN only) -> finite ECE
    assert _finite(r["ece_raw"]) and _finite(r["ece_recal"])
    assert _finite(r["reliability_slope"])
    # LEAK GUARD: score-only (neutral prior + realized runs) must beat the pregame-only
    # forecaster -- if the snapshot leaked the final score the pregame Brier would be ~0.
    assert r["brier_scoreonly"] < r["brier_pregame"], (
        "score-only should be sharper than pregame-only on a leak-free state")
    assert isinstance(r["verdict"], str) and r["verdict"]


def test_default_no_env_resolves_real_corpus():
    """No arg + no env -> the three proofs target the REAL data/domains path (unchanged)."""
    from scripts.platformkit.proof_mlb import (
        beat_the_close_ml as ml, beat_the_close_total as tot, ingame_accuracy as ig)

    assert "PROOF_CORPUS_ROOT" not in os.environ
    assert ml._corpus_from_env() is None
    assert ig._corpus_from_env() is None
    gp, op = tot._resolve(None)
    assert gp.as_posix().endswith("data/domains/mlb/games.parquet")
    assert op.as_posix().endswith("data/domains/mlb/odds.parquet")
    assert ml._GAMES.as_posix().endswith("data/domains/mlb/games.parquet")
    assert ig._GAMES.as_posix().endswith("data/domains/mlb/games.parquet")
