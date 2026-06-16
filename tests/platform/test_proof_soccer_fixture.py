"""tests.platform.test_proof_soccer_fixture — soccer proofs reproduce on the tiny fixture.

Exercises the SHARED corpus-override contract for the two soccer proofs against the
committed deterministic fixture corpus at tests/fixtures/proof/soccer/ (regenerable
via tests/fixtures/proof/soccer/_gen.py). Asserts each proof returns status=='ok'
with a FINITE numeric gap, n_holdout>0, a computable verdict, and the leak guard.

Run ONLY this file (full pytest freezes the box):
    python -m pytest tests/platform/test_proof_soccer_fixture.py -q
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from scripts.platformkit.proof_soccer import beat_the_close_ou as bc
from scripts.platformkit.proof_soccer import ingame_ht_accuracy as ig

_REPO = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = _REPO / "tests" / "fixtures" / "proof"
_SOCCER = _FIXTURE_ROOT / "soccer"


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def test_fixtures_present_and_not_ignored():
    for fn in ("matches.parquet", "match_stats.parquet", "odds.parquet"):
        assert (_SOCCER / fn).is_file(), f"missing fixture {fn}"


# ---------------------------------------------------------------------------
# beat_the_close_ou
# ---------------------------------------------------------------------------

def test_beat_close_fixture_via_arg():
    rep = bc.run(corpus=_SOCCER)
    assert rep["status"] == "ok", rep
    assert rep["n"] >= 200
    assert rep["n_holdout"] > 0
    assert _finite(rep["gap"])
    assert _finite(rep["model_brier"]) and _finite(rep["close_brier"])
    assert 0.0 <= rep["base_rate_over25"] <= 1.0
    # The verdict classification must be computable (one of the three branches).
    assert isinstance(rep["verdict"], str) and rep["verdict"]
    gap = rep["gap"]
    if gap < -0.002:
        assert "BEATS" in rep["verdict"]
    elif gap <= 0.012:
        assert "MATCHES" in rep["verdict"]
    else:
        assert "sharper" in rep["verdict"] or "efficient" in rep["verdict"]


def test_beat_close_fixture_via_env(monkeypatch):
    # The scoreboard sets PROOF_CORPUS_ROOT then calls run() with NO args.
    monkeypatch.setenv("PROOF_CORPUS_ROOT", str(_FIXTURE_ROOT))
    rep = bc.run()
    assert rep["status"] == "ok", rep
    assert rep["n"] >= 200 and rep["n_holdout"] > 0
    assert _finite(rep["gap"])


# ---------------------------------------------------------------------------
# ingame_ht_accuracy
# ---------------------------------------------------------------------------

def test_ingame_fixture_via_arg():
    rep = ig.run(corpus=_SOCCER)
    assert rep["status"] == "ok", rep
    assert rep["n"] >= 200
    assert rep["n_holdout"] > 0
    for k in ("brier_1x2_static", "brier_1x2_conditional", "brier_1x2_delta",
              "brier_ou25_static", "brier_ou25_conditional", "brier_ou25_delta"):
        assert _finite(rep[k]), (k, rep.get(k))
    assert isinstance(rep["verdict"], str) and rep["verdict"]
    # LEAK GUARD: the proof drops any row where HT goals exceed FT goals (the
    # observed minute-45 state can never exceed the future full-time outcome).
    assert rep["n_dropped_ht_gt_ft"] == 0, "fixture must have HT<=FT for every match"
    # Conditioning on the realized HT score should mechanically sharpen both
    # markets (negative delta = HT-conditional Brier below the static surface).
    assert rep["conditional_beats_static"] is True
    assert rep["brier_1x2_delta"] < 0
    assert rep["brier_ou25_delta"] < 0


def test_ingame_fixture_via_env(monkeypatch):
    monkeypatch.setenv("PROOF_CORPUS_ROOT", str(_FIXTURE_ROOT))
    rep = ig.run()
    assert rep["status"] == "ok", rep
    assert rep["n"] >= 200 and rep["n_holdout"] > 0
    assert _finite(rep["brier_ou25_delta"])


# ---------------------------------------------------------------------------
# default behavior preserved (no env, no arg -> real data/domains path)
# ---------------------------------------------------------------------------

def test_default_paths_point_at_real_corpus(monkeypatch):
    monkeypatch.delenv("PROOF_CORPUS_ROOT", raising=False)
    bc_m, bc_s, bc_o = bc._paths(None)
    assert bc_m == bc._MATCHES and bc_o == bc._ODDS
    ig_m, ig_s = ig._paths(None)
    assert ig_m == ig._MATCHES and ig_s == ig._STATS


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
