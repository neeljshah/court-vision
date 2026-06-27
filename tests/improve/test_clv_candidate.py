"""Per-file test for the CLV-vs-close candidate gate FAMILY (LANE Q clv_candidate).

Run ONLY this file (a bare pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && \
      python -m pytest tests/improve/test_clv_candidate.py -q

Covers the honesty invariants:
  * INERT: with the PIPELINE_ENABLED sentinel ABSENT, propose_clv_candidate
    returns None (byte-identical NO_CANDIDATE) regardless of the settled window.
  * BEATS-CLOSE ROUTING: a pure shrink-toward-close window yields NOTHING (the
    objective is model-BEATS-close-on-outcome, never closer-to-close).
  * a genuine beats-close window yields a candidate carrying the settled-CLV close
    corpus as the SECOND corpus, min_corpora>=2, vs_close STILL "UNPROVEN".
  * NO $/roi/pnl key anywhere in the proposed candidate.
"""
from __future__ import annotations

import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import clv_candidate as cdt  # noqa: E402
from scripts.platformkit.improve import clv_corpus as cc  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402

_MONEY_TOKENS = ("$", "dollar", "roi", "pnl", "profit", "bankroll")


# --------------------------------------------------------------------------- #
# fixtures: mirror the proven clv_corpus settled-window shapes.
# --------------------------------------------------------------------------- #
def _game(gid, rows, is_true=True):
    states = [
        {"model_p": m, "close_p": c, "outcome": y, "is_true_close": is_true}
        for (m, c, y) in rows
    ]
    return {"game_id": gid, "states": states}


def _beats_close_window():
    games = []
    for g in range(16):
        j = 0.04 * ((g % 5) - 2)
        rows = []
        for _ in range(4):
            rows.append((0.88 + j, 0.55, 1.0))
        for _ in range(4):
            rows.append((0.12 + j, 0.45, 0.0))
        games.append(_game("G%d" % g, rows))
    return games


def _shrink_toward_close_window():
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
# INERT when the sentinel is absent (byte-identical NO_CANDIDATE).
# --------------------------------------------------------------------------- #
def test_sentinel_absent_proposes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    out = cdt.propose_clv_candidate("nba", _beats_close_window(),
                                    require_enabled=True)
    assert out is None  # even a beats-close window proposes nothing while inert


def test_sentinel_absent_with_shrink_also_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    out = cdt.propose_clv_candidate("nba", _shrink_toward_close_window(),
                                    require_enabled=True)
    assert out is None


# --------------------------------------------------------------------------- #
# BEATS-CLOSE routing: a shrink candidate yields NOTHING (the keystone).
# --------------------------------------------------------------------------- #
def test_shrink_candidate_yields_nothing():
    # require_enabled=False exercises the routing without the live sentinel.
    out = cdt.propose_clv_candidate("nba", _shrink_toward_close_window(),
                                    require_enabled=False)
    assert out is None
    # sanity: the corpus builder itself rejects the shrink window.
    assert cc.build_close_corpus(_shrink_toward_close_window(),
                                 require_enabled=False) is None


def test_beats_close_window_yields_candidate():
    out = cdt.propose_clv_candidate("nba", _beats_close_window(),
                                    require_enabled=False)
    assert out is not None
    # routed through the beats-close gate: carries the settled-CLV close corpus.
    assert out["min_corpora"] >= 2
    assert len(out["corpora"]) == 1
    assert out["corpora"][0]["corpus_id"] == cc.CLV_CORPUS_ID
    # the proposed family never upgrades vs_close -- stays UNPROVEN (honest null).
    assert out["vs_close"] == "UNPROVEN"
    assert out["family"] == cdt.FAMILY_CLV_VS_CLOSE
    assert out["oos_improves"] is True


def test_empty_window_yields_nothing():
    assert cdt.propose_clv_candidate("nba", [], require_enabled=False) is None


# --------------------------------------------------------------------------- #
# NO money key anywhere.
# --------------------------------------------------------------------------- #
def test_no_dollar_key_anywhere():
    out = cdt.propose_clv_candidate("nba", _beats_close_window(),
                                    require_enabled=False)
    assert out is not None
    blob = repr(out).lower()
    for tok in _MONEY_TOKENS:
        assert tok not in blob, tok
    for k in out:
        kl = str(k).lower()
        assert not any(tok in kl for tok in ("$", "roi", "pnl", "dollar")), k


def test_never_raises_on_bad_input():
    # malformed settled rows must degrade to None, never raise.
    assert cdt.propose_clv_candidate("nba", [None, 5, {"x": 1}],
                                     require_enabled=False) is None
