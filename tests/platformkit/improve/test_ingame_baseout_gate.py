"""Tests for the in-game base-out anticipation trigger gate.

Covers: deep/shallow state parsing, leak-free close+resid construction, the honest
INSUFFICIENT floor, a REJECT on noise-only residuals, a SHIP_REVIEW when deep state
genuinely predicts the residual in both corpora, and the no-dollar-field rail.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from scripts.platformkit.improve import ingame_baseout_gate as G


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def test_parse_state_deep():
    s = ("home_score=7 away_score=1 inning=5 half=bottom outs=2 base=3 bos=11 "
         "re=0.908 count=2-1 pitch_count=80 tto=2")
    f = G.parse_state(s)
    assert f is not None
    assert f["outs"] == 2.0 and f["base"] == 3.0 and f["re"] == 0.908
    assert f["score_diff"] == 6.0 and f["balls"] == 2.0 and f["strikes"] == 1.0
    assert f["pitch_count"] == 80.0 and f["tto"] == 2.0


def test_parse_state_shallow_returns_none():
    # pre-id-fix tick: no re/base/outs -> not gate-able
    assert G.parse_state("home_score=7 away_score=1 inning=5 half=bottom") is None


def test_parse_state_malformed_count_ok():
    f = G.parse_state("outs=0 base=0 re=0.1 count=garbage inning=1")
    assert f is not None and f["balls"] == 0.0 and f["strikes"] == 0.0


# --------------------------------------------------------------------------- #
# helpers to synthesize a captured grade dir
# --------------------------------------------------------------------------- #
def _write_game(sdir, gid, ticks):
    fp = sdir / ("%s.jsonl" % gid)
    with fp.open("w", encoding="utf-8") as fh:
        for t in ticks:
            fh.write(json.dumps(t) + "\n")


def _state(outs, base=0, re=0.5, inning=3, hs=0, aw=0, count="0-0", pc=40, tto=1):
    return ("home_score=%d away_score=%d inning=%d half=top outs=%d base=%d bos=%d "
            "re=%.3f count=%s pitch_count=%d tto=%d"
            % (hs, aw, inning, outs, base, base + outs * 3, re, count, pc, tto))


def _make_corpus(tmp_path, n_games, n_ticks, resid_fn, close=0.6, seed=0):
    """Emit n_games jsonl games; non-last tick model_prob = close - resid_fn(i,outs).
    The gate derives close from the last market tick, so resid == resid_fn by design."""
    rng = np.random.default_rng(seed)
    sdir = tmp_path / "mlb"
    sdir.mkdir(parents=True, exist_ok=True)
    for g in range(n_games):
        ticks = []
        for i in range(n_ticks):
            outs = i % 3
            r = resid_fn(i, outs, rng)
            mp = float(np.clip(close - r, 0.01, 0.99))
            ticks.append({
                "sport": "mlb", "game_id": "G%02d" % g, "side": "home",
                "ts": "2026-06-27T%02d:%02d:%02dZ" % (g, i // 60, i % 60),
                "market_prob": 0.5, "model_prob": mp,
                "state_summary": _state(outs, re=0.3 + 0.2 * outs),
            })
        # final (close) tick fixes the in-play close for this game
        ticks.append({
            "sport": "mlb", "game_id": "G%02d" % g, "side": "home",
            "ts": "2026-06-27T%02d:59:59Z" % g, "market_prob": close,
            "model_prob": close, "state_summary": _state(2, re=0.9),
        })
        _write_game(sdir, "G%02d" % g, ticks)
    return tmp_path


# --------------------------------------------------------------------------- #
# gate behaviour
# --------------------------------------------------------------------------- #
def test_gate_insufficient_when_thin(tmp_path):
    _make_corpus(tmp_path, n_games=3, n_ticks=20, resid_fn=lambda i, o, r: 0.0)
    out = G.gate("mlb", grade_dir=tmp_path, write=False)
    assert out["verdict"] == "INSUFFICIENT"
    assert out["edge_claimed"] is False
    assert out["n_games"] == 3


def test_gate_reject_on_noise(tmp_path):
    # residual is pure noise, uncorrelated with features -> cannot beat baseline OOS
    _make_corpus(tmp_path, n_games=16, n_ticks=60,
                 resid_fn=lambda i, o, r: float(r.normal(0, 0.05)))
    out = G.gate("mlb", grade_dir=tmp_path, min_ticks=400, min_games=8, write=False)
    assert out["verdict"] == "REJECT"
    assert "already priced" in out["msg"] or "does NOT beat" in out["msg"]


def test_gate_ship_review_on_real_signal(tmp_path):
    # residual is a clean linear function of outs -> deep state predicts it OOS
    _make_corpus(tmp_path, n_games=16, n_ticks=60,
                 resid_fn=lambda i, o, r: 0.12 * (o - 1) + float(r.normal(0, 0.005)))
    out = G.gate("mlb", grade_dir=tmp_path, min_ticks=400, min_games=8, write=False)
    assert out["verdict"] == "SHIP_REVIEW"
    assert out["null_collapses"] is True
    assert out["corpus_a"]["rmse_delta"] < 0 and out["corpus_b"]["rmse_delta"] < 0


def test_gate_writes_verdict_and_is_clean(tmp_path, monkeypatch):
    vp = tmp_path / "verdict.json"
    monkeypatch.setattr(G, "VERDICT_PATH", vp)
    _make_corpus(tmp_path, n_games=2, n_ticks=10, resid_fn=lambda i, o, r: 0.0)
    out = G.gate("mlb", grade_dir=tmp_path, write=True)
    assert vp.exists()
    disk = json.loads(vp.read_text(encoding="ascii"))
    assert disk["verdict"] == out["verdict"]
    # no dollar/roi/pnl field may ever appear on the verdict
    for k in disk:
        assert not any(b in k.lower() for b in ("roi", "pnl", "profit", "bankroll"))


def test_assert_clean_rejects_banned_key():
    with pytest.raises(ValueError):
        G._assert_clean({"roi": 1.0})


def test_load_deep_ticks_drops_close_and_attaches_resid(tmp_path):
    _make_corpus(tmp_path, n_games=1, n_ticks=5, resid_fn=lambda i, o, r: 0.1)
    rows = G.load_deep_ticks("mlb", grade_dir=tmp_path)
    assert len(rows) == 5            # 5 non-close ticks (6th is the close, dropped)
    assert all(abs(r["resid"] - 0.1) < 1e-9 for r in rows)
    assert all(len(r["feats"]) == len(G._FEATS) for r in rows)
