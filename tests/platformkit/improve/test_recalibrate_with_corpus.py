"""tests.platformkit.improve.test_recalibrate_with_corpus -- SI-CLV-CORPUS-WIRE.

Acceptance:
  (1) sentinel ABSENT: corpora==[] (inert)
  (2) sentinel ON + model-beats-close -> 1 CLV corpus appended
  (3) sentinel ON + shrink-toward-close -> corpora stays [] (no phantom)
  (4) base_build None -> None (NO_CANDIDATE)
  (5) inject raising -> candidate UNCHANGED (purity)
  (6) no $/roi/pnl/edge key; vs_close UNPROVEN; never raises
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import pipeline_flag as PF
from scripts.platformkit.improve.recalibrate_with_corpus import (
    recalibrate_with_corpus,
    make_recalibrate_fn,
)
from scripts.platformkit.improve.clv_corpus import CLV_CORPUS_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_candidate(corpora=None):
    return {
        "base_preds": [0.4, 0.6, 0.4, 0.6],
        "cand_preds": [0.38, 0.62, 0.38, 0.62],
        "y":          [0.0,  1.0,  0.0,  1.0],
        "corpora":    list(corpora) if corpora is not None else [],
        "fold_results": [{"delta": 0.01, "metric": "brier", "fold_id": 0}],
        "oos_improves": True,
        "vs_close": "UNPROVEN",
        "note": "calibration, not edge",
        "kind": "prob",
    }


def _clv_corpus():
    return {
        "corpus_id": CLV_CORPUS_ID,
        "folds": [{"fold_id": "clv_settled", "delta": 0.005, "metric": "brier"}],
        "all_positive": True,
        "significant": True,
        "dm_p": 0.03,
        "n": 20,
        "n_clusters": 4,
        "saw_proxy": False,
        "vs_close": "UNPROVEN",
        "note": "calibration, not edge; vs_close UNPROVEN; second corpus only",
        "units": "probability",
    }


def _settled():
    return [{"game_id": "G1", "outcome": 1.0, "model_p": 0.55,
             "close_p": 0.50, "is_true_close": True}]


def _enable(monkeypatch, tmp_path):
    s = tmp_path / "PIPELINE_ENABLED"
    s.write_text("armed", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", s)


def _disable(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            assert not any(t in kl for t in ("roi", "pnl", "dollar", "edge")), (
                "forbidden key: %r" % k)
            _walk_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_keys(v)


# ---------------------------------------------------------------------------
# (1) sentinel ABSENT: corpora==[], inject NOT called
# ---------------------------------------------------------------------------

def test_sentinel_absent_corpora_empty(monkeypatch, tmp_path):
    _disable(monkeypatch, tmp_path)
    base = _base_candidate()
    inject_called = []

    def _bb(name, settled):
        return dict(base)

    def _inj(c, s):
        inject_called.append(1)
        raise AssertionError("inject must NOT be called when sentinel absent")

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is not None
    assert r["corpora"] == []
    assert r["vs_close"] == "UNPROVEN"
    assert inject_called == []


def test_sentinel_absent_returns_same_object(monkeypatch, tmp_path):
    _disable(monkeypatch, tmp_path)
    base = _base_candidate()

    def _bb(name, settled):
        return base

    def _inj(c, s):
        return None

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is base


# ---------------------------------------------------------------------------
# (2) sentinel ON + model-beats-close -> exactly 1 CLV corpus appended
# ---------------------------------------------------------------------------

def test_sentinel_on_beats_close_appends_corpus(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    corpus = _clv_corpus()

    def _bb(name, settled):
        return _base_candidate()

    def _inj(candidate, settled):
        out = dict(candidate)
        existing = list(out.get("corpora") or [])
        if not any(isinstance(c, dict) and c.get(
                "corpus_id") == CLV_CORPUS_ID for c in existing):
            existing.append(corpus)
        out["corpora"] = existing
        out["clv_corpus_injected"] = True
        return out

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is not None
    assert len(r["corpora"]) == 1
    assert r["corpora"][0]["corpus_id"] == CLV_CORPUS_ID
    assert r.get("clv_corpus_injected") is True
    assert r["vs_close"] == "UNPROVEN"


def test_sentinel_on_inject_receives_settled(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    settled = _settled()
    received = []

    def _bb(name, s):
        return _base_candidate()

    def _inj(c, s):
        received.extend(s)
        out = dict(c)
        out["corpora"] = [_clv_corpus()]
        return out

    recalibrate_with_corpus("nba", settled, base_build=_bb, inject=_inj)
    assert received == settled


# ---------------------------------------------------------------------------
# (3) sentinel ON + shrink-toward-close -> corpora stays [] (no phantom)
# ---------------------------------------------------------------------------

def test_sentinel_on_shrink_no_phantom(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        return c  # inject returns unchanged -- no corpus added

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is not None
    assert r["corpora"] == []
    assert r["vs_close"] == "UNPROVEN"


def test_sentinel_on_all_proxy_corpora_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        return c

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r["corpora"] == []


# ---------------------------------------------------------------------------
# (4) base_build None -> None (NO_CANDIDATE)
# ---------------------------------------------------------------------------

def test_base_build_none_returns_none(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    inject_called = []

    def _bb(name, settled):
        return None

    def _inj(c, s):
        inject_called.append(1)
        return c

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is None
    assert inject_called == []


def test_base_build_raising_returns_none(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def _bb(name, settled):
        raise RuntimeError("boom")

    def _inj(c, s):
        raise AssertionError("should not be called")

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is None


# ---------------------------------------------------------------------------
# (5) inject raising -> candidate UNCHANGED (purity)
# ---------------------------------------------------------------------------

def test_inject_raising_returns_base_unchanged(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    base = _base_candidate()

    def _bb(name, settled):
        return base

    def _inj(c, s):
        raise ValueError("inject boom")

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is base
    assert r["corpora"] == []


def test_inject_none_fallback_to_base(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    base = _base_candidate()

    def _bb(name, settled):
        return base

    def _inj(c, s):
        return None

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r is base


# ---------------------------------------------------------------------------
# (6) no $/roi/pnl/edge; vs_close UNPROVEN; never raises
# ---------------------------------------------------------------------------

def test_no_dollar_keys_absent(monkeypatch, tmp_path):
    _disable(monkeypatch, tmp_path)

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        return c

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    _walk_keys(r)


def test_no_dollar_keys_with_corpus(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        out = dict(c)
        out["corpora"] = [_clv_corpus()]
        return out

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    _walk_keys(r)
    assert r["vs_close"] == "UNPROVEN"


def test_vs_close_stays_unproven_if_inject_stamps_proven(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        out = dict(c)
        out["corpora"] = [_clv_corpus()]
        out["vs_close"] = "PROVEN"  # violation -- compose must correct
        return out

    r = recalibrate_with_corpus(
        "nba", _settled(), base_build=_bb, inject=_inj)
    assert r["vs_close"] == "UNPROVEN"


def test_never_raises_malformed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        return c

    r = recalibrate_with_corpus(
        "nba", [None, 42, "broken"], base_build=_bb, inject=_inj)
    assert r is not None


# ---------------------------------------------------------------------------
# make_recalibrate_fn factory
# ---------------------------------------------------------------------------

def test_make_fn_sentinel_on(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        out = dict(c)
        out["corpora"] = [_clv_corpus()]
        return out

    fn = make_recalibrate_fn(base_build=_bb, inject=_inj)
    r = fn("nba", _settled())
    assert r is not None
    assert len(r["corpora"]) == 1
    assert r["corpora"][0]["corpus_id"] == CLV_CORPUS_ID


def test_make_fn_absent_inert(monkeypatch, tmp_path):
    _disable(monkeypatch, tmp_path)
    inject_called = []

    def _bb(name, settled):
        return _base_candidate()

    def _inj(c, s):
        inject_called.append(1)
        return c

    fn = make_recalibrate_fn(base_build=_bb, inject=_inj)
    r = fn("nba", _settled())
    assert r["corpora"] == []
    assert inject_called == []


# ---------------------------------------------------------------------------
# Integration smoke: real inject_corpus with no close_p
# ---------------------------------------------------------------------------

def test_real_inject_no_close_p_empty_corpora(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from scripts.platformkit.improve.clv_corpus_inject import inject_corpus

    def _bb(name, settled):
        return _base_candidate()

    r = recalibrate_with_corpus("nba",
        [{"game_id": "X1", "outcome": 1.0, "model_p": 0.55}],
        base_build=_bb, inject=inject_corpus)
    assert r is not None
    assert r["corpora"] == []
    assert r["vs_close"] == "UNPROVEN"
    _walk_keys(r)
