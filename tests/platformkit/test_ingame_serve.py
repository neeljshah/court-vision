"""Offline tests for scripts.platformkit.ingame.ingame_serve.

Asserts the persist->serve round-trip and the HONESTY rules:
  * a PROVEN sport applies the +prior layer (model 'base+prior(proven)');
  * a REJECT sport (MLB) serves BASE only -- NEVER an unproven prior;
  * a PARTIAL sport marks the prior experimental;
  * missing live state degrades to p0;
  * the served result carries NO $ field.
No network; corpora are tiny synthetic pools written to a tmp model dir.
"""
from __future__ import annotations

import json
import os

import pytest

from scripts.platformkit.ingame import ingame_serve as srv


def _toy_pool(n_games=50, ticks=6):
    """Synthetic states where a positive state_diff genuinely predicts outcome=1."""
    pool = []
    for g in range(n_games):
        win = 1 if g % 2 == 0 else 0
        for t in range(ticks):
            frac = (t + 1) / ticks
            diff = (3.0 if win else -3.0) * frac  # lead grows with the eventual winner
            pool.append({"game_id": g, "state_diff": diff, "frac_elapsed": frac,
                         "p0": 0.55 if win else 0.45, "outcome": win})
    return pool


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    """Point the model dir at tmp and stub the pool + verdict per sport."""
    monkeypatch.setattr(srv, "_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(srv, "_load_pool", lambda sport: _toy_pool())
    verdicts = {"nba": "REPLICATED", "tennis": "REPLICATED",
                "soccer": "PARTIAL", "mlb": "REJECT"}
    monkeypatch.setattr(srv, "_gate_verdict", lambda sport: verdicts.get(sport, "UNKNOWN"))
    return tmp_path


def test_fit_persists_versioned_artifact(patched):
    art = srv.fit_servable("nba")
    path = os.path.join(str(patched), "nba_ingame.json")
    assert os.path.exists(path)
    on_disk = json.load(open(path, encoding="ascii"))
    assert on_disk["version"] == srv._VERSION
    assert on_disk["verdict"] == "REPLICATED"
    assert on_disk["prior_status"] == "proven"
    assert on_disk["base_slope"] is not None
    assert on_disk["weight_surface"] is not None
    assert art["fit_ok"] is True


def test_proven_sport_applies_prior(patched):
    srv.fit_servable("nba")
    out = srv.serve_ingame("nba", state_diff=4.0, frac_elapsed=0.8, p0=0.55)
    assert out["model"] == "base+prior(proven)"
    assert 0.0 <= out["p_win"] <= 1.0


def test_mlb_reject_serves_base_only(patched):
    srv.fit_servable("mlb")
    out = srv.serve_ingame("mlb", state_diff=2.0, frac_elapsed=0.6, p0=0.5)
    # an UNPROVEN prior is NEVER applied as proven -> BASE only
    assert out["model"] == "base"
    assert "proven" not in out["model"]
    assert any("NOT served" in p for p in out["provenance"])


def test_partial_sport_marks_experimental(patched):
    srv.fit_servable("soccer")
    out = srv.serve_ingame("soccer", state_diff=1.0, frac_elapsed=0.7, p0=0.45)
    assert out["model"] == "base+prior(experimental)"


def test_missing_state_degrades_to_p0(patched):
    srv.fit_servable("nba")
    out = srv.serve_ingame("nba", state_diff=None, frac_elapsed=None, p0=0.61)
    assert out["model"] == "p0"
    assert out["p_win"] == pytest.approx(0.61)


def test_missing_artifact_degrades_to_p0(patched):
    # no fit_servable called for tennis -> no artifact
    out = srv.serve_ingame("tennis", state_diff=3.0, frac_elapsed=0.5, p0=0.7)
    assert out["model"] == "p0"
    assert out["p_win"] == pytest.approx(0.7)


def test_no_dollar_field_anywhere(patched):
    srv.fit_servable("nba")
    out = srv.serve_ingame("nba", state_diff=4.0, frac_elapsed=0.8, p0=0.55)
    blob = json.dumps(out).lower()
    for bad in ("$", "roi", "dollar", "profit", "stake", "payout", "bankroll"):
        assert bad not in blob
    assert out["vs_close"].startswith("UNPROVEN")


def test_no_p0_serves_base_for_proven(patched):
    srv.fit_servable("nba")
    out = srv.serve_ingame("nba", state_diff=4.0, frac_elapsed=0.8, p0=None)
    # cannot blend without p0 -> BASE only, still honest
    assert out["model"] == "base"
