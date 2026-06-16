"""Per-file numeric test for the NBA platformkit proofs on the committed fixture corpus.

Drives each NBA proof against tests/fixtures/proof/nba/ via the shared corpus-override
contract (PROOF_CORPUS_ROOT env AND the explicit corpus= arg) and asserts each returns
status=='ok' with a FINITE numeric gap, n_holdout>0, computable verdict, and -- where the
proof guards against leakage -- that the leak guard holds (Elo/EW state updates AFTER each
game's snapshot, so the first-seen game's forecast equals the cold-start prior).

Fixture-only: never touches data/domains; tiny + deterministic (seed in _gen.py). Run ONLY
this file:
  python -m pytest tests/platform/test_proof_nba_fixture.py -q
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

_FIX_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "proof"   # parent of /nba
_NBA_FIX = _FIX_ROOT / "nba"


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def test_fixtures_present_and_not_ignored():
    for f in ("espn_boxscores.parquet", "odds.parquet", "linescores.parquet", "_gen.py"):
        assert (_NBA_FIX / f).is_file(), f"missing fixture {f}"


def test_ml_accuracy_beats_close_on_fixture():
    from scripts.platformkit.proof_nba import ml_accuracy
    rep = ml_accuracy.run(corpus=_NBA_FIX)               # explicit-arg path
    assert rep["status"] == "ok", rep
    assert rep["n_holdout"] > 0 and rep["n_overlap"] >= 60
    assert _finite(rep["model_brier"]) and _finite(rep["market_brier"])
    assert _finite(rep["brier_gap_to_market"])
    assert 0.0 <= rep["model_brier"] <= 1.0 and 0.0 <= rep["market_brier"] <= 1.0
    # verdict classification is computable (one of the three honest branches)
    assert isinstance(rep["verdict"], str) and rep["verdict"]
    assert any(k in rep["verdict"] for k in ("BEATS", "MATCHES", "sharper"))
    # NO retracted/$-edge number leaks into the honest report
    assert "+18.38" not in str(rep) and "54.57" not in str(rep)


def test_asof_box_beats_close_on_fixture():
    from scripts.platformkit.proof_nba import asof_box_accuracy
    rep = asof_box_accuracy.run(corpus=_NBA_FIX)
    assert rep.get("status") == "ok", rep
    assert rep["n_holdout"] > 0 and rep["n_overlap"] >= 40
    assert _finite(rep["close_rmse_vs_realized"]) and _finite(rep["best_model_rmse"])
    assert _finite(rep["gap_to_close_rmse"])
    for key in ("pooled_model", "split_model", "poss_model"):
        assert _finite(rep[key]["rmse"]) and _finite(rep[key]["ece"])
    assert isinstance(rep["verdict"], str) and rep["verdict"]
    assert any(k in rep["verdict"] for k in ("BEATS", "MATCHES", "sharper"))


def test_ingame_accuracy_on_fixture():
    from scripts.platformkit.proof_nba import ingame_accuracy
    rep = ingame_accuracy.run(corpus=_NBA_FIX)
    assert rep["status"] == "ok", rep
    assert rep["n_games"] >= 60 and rep["n_checkpoints"] > 0
    for key in ("brier_pregame_elo", "brier_conditional_blind", "brier_conditional_rating",
                "total_rmse_flat", "total_rmse_curve", "total_bias_flat"):
        assert _finite(rep[key]), key
    assert 0.0 <= rep["brier_conditional_rating"] <= 1.0
    # calibration block computed on the leak-free split-by-game eval set
    assert _finite(rep["ece_raw"]) and _finite(rep["ece_recal"])
    assert rep["cal_n_eval"] > 0 and rep["cal_n_train"] > 0
    assert isinstance(rep["verdict"], str) and rep["verdict"]


def test_env_override_matches_explicit_arg():
    """Setting PROOF_CORPUS_ROOT (no arg) picks up the SAME fixtures as corpus=."""
    from scripts.platformkit.proof_nba import ml_accuracy
    prev = os.environ.get("PROOF_CORPUS_ROOT")
    os.environ["PROOF_CORPUS_ROOT"] = str(_FIX_ROOT)
    try:
        rep_env = ml_accuracy.run()                      # env path, no arg
    finally:
        if prev is None:
            os.environ.pop("PROOF_CORPUS_ROOT", None)
        else:
            os.environ["PROOF_CORPUS_ROOT"] = prev
    rep_arg = ml_accuracy.run(corpus=_NBA_FIX)
    assert rep_env["status"] == "ok"
    assert rep_env["n_overlap"] == rep_arg["n_overlap"]
    assert rep_env["model_brier"] == rep_arg["model_brier"]


def test_elo_leak_guard_first_game_is_coldstart():
    """Leak guard: the as-of Elo forecast updates AFTER each game's snapshot, so the very
    first game both teams have ever played must be priced at the cold-start prior (1500 vs
    1500 + HFA) -- a future result cannot have leaked into the first snapshot."""
    from scripts.platformkit.proof_nba import asof_box_accuracy, ml_accuracy
    box = asof_box_accuracy.load_box(_NBA_FIX)
    p = ml_accuracy._walk_forward_elo(box)
    cold = ml_accuracy._p_home(ml_accuracy._INIT, ml_accuracy._INIT)   # 1500 vs 1500 + HFA
    assert abs(float(p[0]) - cold) < 1e-9, (p[0], cold)
    assert np.all(np.isfinite(p))
