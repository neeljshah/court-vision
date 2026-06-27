"""Per-file test for the settled-CLV SECOND CORPUS (Inc2 core).

Run ONLY this file (a bare pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && \
      python -m pytest tests/improve/test_clv_corpus.py -q

Covers the honesty invariants of clv_corpus.build_close_corpus +
clv_corpus_inject:
  P1 (keystone): a pure shrink-toward-close candidate (model == close) yields
                 NO corpus -- not an all-positive one.
  P1 (positive): a genuine model-beats-close window DOES yield a corpus whose
                 single fold has delta > 0.
  P3:            an all-proxy (is_true_close=False) window -> None.
  P5:            per-game (clustered) loss vectors are emitted on a real corpus.
  inert:         sentinel absent -> build returns None; inject leaves the
                 candidate byte-identical (corpora unchanged).
  P2:            inject NEVER self-stamps a vs_close upgrade; the upgrade verdict
                 is emitted only after gate_ship AND n_rep>=2 AND DM p<0.05.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import clv_corpus as cc  # noqa: E402
from scripts.platformkit.improve import clv_corpus_inject as ci  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures: settled windows as (model_p, close_p, outcome) state rows.
# --------------------------------------------------------------------------- #
def _game(gid, rows, is_true=True):
    states = [
        {"model_p": m, "close_p": c, "outcome": y, "is_true_close": is_true}
        for (m, c, y) in rows
    ]
    return {"game_id": gid, "states": states}


def _beats_close_window():
    """Model is consistently RIGHT where the close hedges -> beats close on outcome.

    Many games/states so the cluster-robust DM binds; per-game confidence VARIES
    (jitter) so the between-cluster variance is non-zero and the DM SE is real
    (identical games would give a degenerate 0 variance / p=1.0).
    """
    games = []
    for g in range(16):
        j = 0.04 * ((g % 5) - 2)  # per-game jitter in [-0.08, 0.08]
        rows = []
        # winners: model confident-right (~0.88), close timid (~0.55)
        for _ in range(4):
            rows.append((0.88 + j, 0.55, 1.0))
        # losers: model confident-right (~0.12), close timid (~0.45)
        for _ in range(4):
            rows.append((0.12 + j, 0.45, 0.0))
        games.append(_game("G%d" % g, rows))
    return games


def _shrink_toward_close_window():
    """Pure shrink-toward-close: model == close EXACTLY on every state.

    Outcome-Brier is identical to the close (delta 0, not > 0) and the divergence
    has collapsed -- the P1 reject. Must yield NO corpus.
    """
    games = []
    for g in range(12):
        rows = []
        for _ in range(4):
            rows.append((0.55, 0.55, 1.0))
        for _ in range(4):
            rows.append((0.45, 0.45, 0.0))
        games.append(_game("G%d" % g, rows))
    return games


# --------------------------------------------------------------------------- #
# P1 keystone: shrink-toward-close -> NO corpus.
# --------------------------------------------------------------------------- #
def test_shrink_toward_close_yields_no_corpus():
    out = cc.build_close_corpus(_shrink_toward_close_window(),
                                require_enabled=False)
    assert out is None, "a pure shrink-toward-close candidate must yield NO corpus"


def test_model_beats_close_yields_positive_corpus():
    out = cc.build_close_corpus(_beats_close_window(), require_enabled=False)
    assert out is not None, "a genuine model-beats-close window must yield a corpus"
    assert out["corpus_id"] == cc.CLV_CORPUS_ID
    assert len(out["folds"]) == 1
    assert out["folds"][0]["delta"] > 0.0, "the fold must beat close on OUTCOME"
    assert out["all_positive"] is True
    # vs_close never advances in the builder.
    assert out["vs_close"] == "UNPROVEN"
    # no dollar field anywhere
    assert not any(k in out for k in ("roi", "pnl", "bankroll", "stake", "dollars"))


# --------------------------------------------------------------------------- #
# P3: all-proxy window -> None.
# --------------------------------------------------------------------------- #
def test_all_proxy_window_returns_none():
    games = [_game("G%d" % g, [(0.9, 0.55, 1.0), (0.1, 0.45, 0.0)] * 4,
                   is_true=False)
             for g in range(12)]
    out = cc.build_close_corpus(games, require_enabled=False)
    assert out is None, "a window of only PROXY closes must return None (P3)"


# --------------------------------------------------------------------------- #
# P5: per-game clustered loss vectors are emitted.
# --------------------------------------------------------------------------- #
def test_per_game_loss_vectors_present():
    out = cc.build_close_corpus(_beats_close_window(), require_enabled=False)
    assert out is not None
    pg = out["per_game_losses"]
    assert isinstance(pg, list) and len(pg) >= cc._MIN_CLUSTERS
    for entry in pg:
        assert "game_id" in entry and isinstance(entry["d"], list) and entry["d"]
    # n_clusters reflects distinct games (16 here)
    assert out["n_clusters"] == 16


# --------------------------------------------------------------------------- #
# inert: sentinel absent -> build None and inject leaves candidate unchanged.
# --------------------------------------------------------------------------- #
def test_sentinel_absent_build_is_inert(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    out = cc.build_close_corpus(_beats_close_window(), require_enabled=True)
    assert out is None, "sentinel absent -> no corpus (inert)"


def test_sentinel_absent_inject_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    candidate = {"corpora": [], "vs_close": "UNPROVEN"}
    out = ci.inject_corpus(candidate, _beats_close_window(), require_enabled=True)
    # byte-identical corpora: still empty, vs_close still UNPROVEN
    assert out["corpora"] == []
    assert out["vs_close"] == "UNPROVEN"


def test_inject_appends_corpus_when_window_beats_close():
    candidate = {"corpora": [{"corpus_id": "recal_primary", "folds": [{"delta": 0.01}]}],
                 "vs_close": "UNPROVEN"}
    out = ci.inject_corpus(candidate, _beats_close_window(), require_enabled=False)
    ids = [c["corpus_id"] for c in out["corpora"]]
    assert cc.CLV_CORPUS_ID in ids and "recal_primary" in ids
    assert out["vs_close"] == "UNPROVEN", "inject must NOT advance vs_close (P2)"


def test_inject_no_corpus_when_shrink(monkeypatch):
    candidate = {"corpora": [], "vs_close": "UNPROVEN"}
    out = ci.inject_corpus(candidate, _shrink_toward_close_window(),
                           require_enabled=False)
    assert out["corpora"] == [], "shrink-toward-close -> no corpus appended"


# --------------------------------------------------------------------------- #
# P2: no self-stamped vs_close upgrade; gated on ship + replication + DM p.
# --------------------------------------------------------------------------- #
def test_no_upgrade_without_ship():
    corpus = cc.build_close_corpus(_beats_close_window(), require_enabled=False)
    assert ci.maybe_vs_close_upgrade(gate_ship=False, n_rep=2,
                                     close_corpus=corpus) is None


def test_no_upgrade_without_replication():
    corpus = cc.build_close_corpus(_beats_close_window(), require_enabled=False)
    assert ci.maybe_vs_close_upgrade(gate_ship=True, n_rep=1,
                                     close_corpus=corpus) is None


def test_upgrade_only_when_all_conditions_hold():
    corpus = cc.build_close_corpus(_beats_close_window(), require_enabled=False)
    # the beats-close window is constructed to be significant (DM p < 0.05)
    assert corpus is not None and corpus["dm_p"] < 0.05
    up = ci.maybe_vs_close_upgrade(gate_ship=True, n_rep=2, close_corpus=corpus)
    assert up is not None and up["vs_close"] == "PROVEN"
    assert up["note"].startswith("verdict only")


def test_no_upgrade_when_dm_insignificant():
    corpus = cc.build_close_corpus(_beats_close_window(), require_enabled=False)
    corpus = dict(corpus)
    corpus["dm_p"] = 0.20  # force non-significant
    assert ci.maybe_vs_close_upgrade(gate_ship=True, n_rep=2,
                                     close_corpus=corpus) is None
