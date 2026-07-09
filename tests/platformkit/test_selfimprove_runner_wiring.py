"""Offline test for the SUPERVISED self-improve runner's default settled-games fn.

FIX A: the default fn now wires to the RICHER, STATE-BEARING provider
scripts.platformkit.improve.settled_ingest.settled_games_fn (which fetches+classifies the
keyless-ESPN boards, runs the MF3 anti-0-fill audit, AND reconstructs leak-free
{p0, outcome} state rows per final). The earlier default delegated to the bare
settled_finals.settled_since, which returned STATELESS games -> the audit quarantined every
one as empty_states -> FeedDegradedError -> recalibrator None -> perpetual NO_CANDIDATE.

ZERO network: we monkeypatch settled_ingest.settled_games_fn to a canned provider and
assert the runner's default fn calls IT and forwards since + seen_ids (the primary dedup
guard). A dead provider must still degrade to [] (NO_CANDIDATE), never raise.
"""
from __future__ import annotations

import sys
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import selfimprove_runner as RN  # noqa: E402
from scripts.platformkit.improve import settled_ingest as SI  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402
from scripts.platformkit.improve import recalibrator as RC  # noqa: E402
from scripts.platformkit.improve import clv_corpus_inject as CCI  # noqa: E402


def test_default_settled_fn_wires_to_state_bearing_ingest(monkeypatch):
    """The default fn delegates to settled_ingest.settled_games_fn (FIX A) + forwards keys."""
    captured = {}

    def fake_settled_games_fn(sport, *, since="", seen_ids=None, **_kw):
        captured["sport"] = sport
        captured["since"] = since
        captured["seen_ids"] = seen_ids
        return [{"game_id": "G1", "key": "2026-06-10|G1",
                 "states": [{"p0": 0.55, "outcome": 1.0}], "outcome": 1.0}]

    monkeypatch.setattr(SI, "settled_games_fn", fake_settled_games_fn)
    out = RN._default_settled_games_fn("mlb", since="2026-06-09|G0", seen_ids=["G0"])
    assert len(out) == 1 and out[0]["game_id"] == "G1"
    # the game is STATE-BEARING (the whole point of FIX A) -- not a bare dict
    assert out[0]["states"][0]["p0"] == 0.55
    assert out[0]["states"][0]["outcome"] == 1.0
    assert captured["sport"] == "mlb"
    assert captured["since"] == "2026-06-09|G0"
    assert captured["seen_ids"] == ["G0"]  # seen_ids threaded through (primary dedup)


def test_default_settled_fn_degrades_to_empty_on_dead_provider(monkeypatch):
    """REGRESSION: a raising provider degrades to [] (NO_CANDIDATE), never crashes."""
    assert hasattr(SI, "settled_games_fn")

    def boom(*a, **k):
        raise RuntimeError("feed down")

    monkeypatch.setattr(SI, "settled_games_fn", boom)
    # selfimprove_runner wraps the call; a raising provider must surface [] safely.
    assert RN._default_settled_games_fn("mlb", since="", seen_ids=[]) == []


# ------------------------------------- FIX b593966d: CLV corpus wiring call site
# (b593966d wired _default_recalibrate_fn -> recalibrate_with_corpus.recalibrate_with_corpus
# so a real settled-CLV close corpus reaches candidate['corpora'] instead of every
# candidate staying REPLICATION_PENDING forever. Heavy IO (recalibrator.build_candidate's
# own Platt fit, clv_corpus_inject's on-disk grade read) is MOCKED here -- only the
# WIRING (does the corpus reach the candidate? does `report` propagate?) is under test.

def test_recalibrate_fn_inert_when_sentinel_absent(monkeypatch):
    """Sentinel OFF -> None with reason='inert', BEFORE any recalibrator/CLV import."""
    monkeypatch.setattr(PF, "pipeline_enabled", lambda: False)
    report: dict = {}
    out = RN._default_recalibrate_fn("nba", [{"game_id": "G1"}], report=report)
    assert out is None
    assert report["reason"] == "inert" and report["transient"] is False


def test_recalibrate_fn_empty_batch_returns_none(monkeypatch):
    """Empty settled batch -> None with reason='empty_batch' (never reaches the flag)."""
    report: dict = {}
    out = RN._default_recalibrate_fn("nba", [], report=report)
    assert out is None
    assert report["reason"] == "empty_batch" and report["transient"] is False


def test_recalibrate_fn_stays_replication_pending_without_a_real_corpus(monkeypatch):
    """Sentinel ON, base candidate built, but inject_corpus honestly finds no real
    settled-CLV close window -> candidate['corpora'] stays [] (unchanged)."""
    monkeypatch.setattr(PF, "pipeline_enabled", lambda: True)

    def fake_build(name, settled, report=None, **_kw):
        if isinstance(report, dict):
            report["reason"], report["transient"] = "evaluated", False
        return {"corpora": [], "vs_close": "UNPROVEN", "note": "calibration, not edge"}

    def fake_inject_unchanged(candidate, settled, **_kw):
        return candidate  # honest: no real corpus found -> unchanged

    monkeypatch.setattr(RC, "build_candidate", fake_build)
    monkeypatch.setattr(CCI, "inject_corpus", fake_inject_unchanged)

    report: dict = {}
    out = RN._default_recalibrate_fn("nba", [{"game_id": "G1"}], report=report)
    assert out is not None
    assert out["corpora"] == []  # REPLICATION_PENDING baseline preserved
    assert report["reason"] == "evaluated"  # build_candidate's own note propagated


def test_recalibrate_fn_no_longer_replication_pending_when_a_real_corpus_exists(
    monkeypatch,
):
    """Sentinel ON + a genuine 2nd corpus exists -> candidate['corpora'] is no longer
    [] -- the exact wiring b593966d fixed (candidate stops being permanently
    REPLICATION_PENDING once a real model-beats-close window is present)."""
    monkeypatch.setattr(PF, "pipeline_enabled", lambda: True)

    def fake_build(name, settled, report=None, **_kw):
        if isinstance(report, dict):
            report["reason"], report["transient"] = "evaluated", False
        return {"corpora": [], "vs_close": "UNPROVEN", "note": "calibration, not edge"}

    real_corpus = {"corpus_id": "clv_settled_close", "all_positive": True}

    def fake_inject_appends(candidate, settled, **_kw):
        out = dict(candidate)
        out["corpora"] = list(candidate.get("corpora") or []) + [real_corpus]
        out["vs_close"] = "UNPROVEN"  # never self-stamped, even with a 2nd corpus
        return out

    monkeypatch.setattr(RC, "build_candidate", fake_build)
    monkeypatch.setattr(CCI, "inject_corpus", fake_inject_appends)

    out = RN._default_recalibrate_fn("nba", [{"game_id": "G1"}], report={})
    assert out is not None
    assert out["corpora"] == [real_corpus]  # no longer REPLICATION_PENDING
    assert out["vs_close"] == "UNPROVEN"


def test_recalibrate_fn_returns_none_when_base_build_is_none(monkeypatch):
    """base_build (recalibrator) itself declines -> None, inject never even attempted."""
    monkeypatch.setattr(PF, "pipeline_enabled", lambda: True)
    called = {"inject": False}

    monkeypatch.setattr(RC, "build_candidate", lambda *a, **k: None)

    def fake_inject(*a, **k):
        called["inject"] = True
        return {}

    monkeypatch.setattr(CCI, "inject_corpus", fake_inject)
    out = RN._default_recalibrate_fn("nba", [{"game_id": "G1"}], report={})
    assert out is None
    assert called["inject"] is False  # NO_CANDIDATE short-circuits before inject


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
