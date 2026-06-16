"""tests.platform.test_proof_tennis_fixture -- the tennis proofs run on the committed fixture.

Sets the SHARED corpus-override contract ($PROOF_CORPUS_ROOT) to the tiny committed
fixture under tests/fixtures/proof/ and asserts both tennis proofs return status=='ok'
with a finite numeric gap, n_holdout>0, a computable verdict (beat-close), and the
leak guard (id-order symmetric, no winner-order in the model prob; Elo strictly
walk-forward). CALIBRATION/sharpness only -- markets efficient, no $ edge.

Run ONLY this file (full pytest freezes the box):
  python -m pytest tests/platform/test_proof_tennis_fixture.py -q
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = _REPO / "tests" / "fixtures" / "proof"
_TENNIS = _FIXTURE_ROOT / "tennis"


@pytest.fixture(scope="module")
def env_corpus():
    """Point the proofs at the committed fixture via the shared env contract."""
    prev = os.environ.get("PROOF_CORPUS_ROOT")
    os.environ["PROOF_CORPUS_ROOT"] = str(_FIXTURE_ROOT)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("PROOF_CORPUS_ROOT", None)
        else:
            os.environ["PROOF_CORPUS_ROOT"] = prev


def test_fixture_files_exist_and_schema():
    matches = pd.read_parquet(_TENNIS / "matches.parquet")
    odds = pd.read_parquet(_TENNIS / "odds.parquet")
    assert len(matches) > 100 and len(odds) > 100
    for c in ("event_id", "date", "surface", "best_of", "p1_id", "p2_id",
              "winner", "score", "retirement"):
        assert c in matches.columns, c
    for c in ("event_id", "ps_p1", "ps_p2"):
        assert c in odds.columns, c
    # LEAK GUARD: symmetric id-order p1_id < p2_id for 100% of rows (no winner-order)
    assert bool((matches["p1_id"] < matches["p2_id"]).all())
    # held-out (year>2022) window is non-empty
    yrs = pd.to_datetime(matches["date"]).dt.year
    assert int((yrs > 2022).sum()) > 0


def test_beat_the_close_ml_fixture(env_corpus):
    from scripts.platformkit.proof_tennis import beat_the_close_ml as bc

    rep = bc.run()  # no args -> picks up $PROOF_CORPUS_ROOT/tennis
    assert rep["status"] == "ok", rep
    assert rep["n"] > 0
    assert rep["n"] >= 60                       # held-out window large enough to score
    gap = rep["gap"]
    assert isinstance(gap, float) and math.isfinite(gap)
    assert math.isfinite(rep["model_metric"]) and math.isfinite(rep["close_metric"])
    # verdict classification is computable and one of the three honest classes
    assert isinstance(rep["verdict"], str) and rep["verdict"][:5] in (
        "BEATS", "MATCH", "BEHIN")
    # gap sign is consistent with the verdict class (no retracted $ number printed)
    if gap < -0.002:
        assert rep["verdict"].startswith("BEATS")
    elif gap <= 0.010:
        assert rep["verdict"].startswith("MATCH")
    else:
        assert rep["verdict"].startswith("BEHIND")
    # corr(model, close) is finite -> both forecasters are real, id-order aligned
    assert math.isfinite(rep["corr_model_close"])


def test_ingame_accuracy_fixture(env_corpus):
    from scripts.platformkit.proof_tennis import ingame_accuracy as ig

    rep = ig.run()  # no args -> picks up $PROOF_CORPUS_ROOT/tennis
    assert rep["status"] == "ok", rep
    assert rep["n_after_set1"] > 0 and rep["n_after_set1"] >= 60
    for k in ("brier_pregame_elo", "brier_score_only", "brier_combined",
              "ece_raw", "ece_recal", "combined_calib_brier_raw",
              "combined_calib_brier_recal"):
        assert math.isfinite(rep[k]), k
    # leak-free recal never worse than raw on the held-out EVAL half
    assert rep["recal_brier_not_worse"] is True
    assert rep["combined_calib_n_eval"] > 0
    # base rate is a real probability
    assert 0.0 <= rep["base_rate_set1_leader_wins"] <= 1.0
    # verdict text is computable
    assert isinstance(rep["verdict"], str) and "Brier" in rep["verdict"]


def test_leak_guard_elo_is_walk_forward(env_corpus):
    """Sanity: the as-of win prob for each held-out row uses ratings from strictly
    PRIOR matches only -- recomputing on a truncated (prior-only) corpus reproduces
    the same first held-out row's win_prob_p1 (no future leakage into the snapshot)."""
    from domains.tennis.elo_core import SURFACE_BLEND
    from domains.tennis.elo_tune import _walk_forward_blend

    matches = pd.read_parquet(_TENNIS / "matches.parquet")
    wf = _walk_forward_blend(matches, blend=SURFACE_BLEND).reset_index(drop=True)
    yrs = pd.to_datetime(wf["date"]).dt.year
    test_idx = int(np.where((yrs > 2022).to_numpy())[0][0])
    full_prob = float(wf["win_prob_p1"].iloc[test_idx])
    # truncate to everything strictly before that row, append the row itself, re-run
    prior = matches.iloc[: test_idx + 1].copy()
    wf2 = _walk_forward_blend(prior, blend=SURFACE_BLEND).reset_index(drop=True)
    trunc_prob = float(wf2["win_prob_p1"].iloc[-1])
    assert abs(full_prob - trunc_prob) < 1e-9   # snapshot depends only on the past


def test_default_path_unchanged_when_no_env():
    """With NO env + NO arg, run() must target the REAL data/domains path (not the
    fixture) -- default behavior is preserved. We don't require the real data to
    exist; we only assert the resolved path is the real one, never the fixture."""
    os.environ.pop("PROOF_CORPUS_ROOT", None)
    from scripts.platformkit.proof_tennis import beat_the_close_ml as bc
    from scripts.platformkit.proof_tennis import ingame_accuracy as ig

    assert bc._corpus_from_env() is None
    assert ig._corpus_from_env() is None
    # the module-level real paths point at data/domains/tennis, never the fixture
    assert bc._MATCHES == _REPO / "data/domains/tennis/matches.parquet"
    assert "fixtures" not in str(bc._MATCHES)
    assert "fixtures" not in str(ig._MATCHES)
