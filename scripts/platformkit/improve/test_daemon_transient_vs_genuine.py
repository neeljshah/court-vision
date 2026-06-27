"""tests for the wave-2 cursor-advance fix (audit 2.3): in the self-improve daemon an
ARMED NO_CANDIDATE must ADVANCE the cursor ONLY on a GENUINE evaluated decline, and must
PRESERVE the cursor (so the settled games retry next cycle) on a TRANSIENT failure that
bailed BEFORE a real evaluation (FeedDegradedError / a recalibrate_fn raise / a recalibrator
that reports transient=True). The earlier code conflated both Nones and SILENTLY SKIPPED the
transient batch forever.

Asserts:
  (1) ARMED + GENUINE evaluated-no-candidate (report transient=False) -> cursor ADVANCES.
  (1b) ARMED + the REAL build_candidate on a well-calibrated batch (degenerate no-op decline)
       -> cursor ADVANCES (the honest market-efficiency REJECT path still works).
  (2) ARMED + TRANSIENT report (transient=True) -> cursor PRESERVED + games retried next cycle.
  (2b) ARMED + the REAL build_candidate on a degraded all-bad batch (FeedDegradedError)
       -> cursor PRESERVED + games retried.
  (3) ARMED + recalibrate_fn RAISES -> cursor PRESERVED + games retried.
  (4) INERT (sentinel ABSENT) -> seen_ids/high_water preserved (no regression).
  (5) A planted-null candidate still REJECTS through the gate (gate NOT weakened).

Per-file test only (full pytest freezes the box). ASCII; stdlib + numpy deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import selfimprove_daemon as D  # noqa: E402
from scripts.platformkit.improve import recalibrator as RC  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402
from scripts.platformkit.improve.checkpoint import load_checkpoint  # noqa: E402


# --------------------------------------------------------------------------- helpers
def _kid(i):
    return {"game_id": "G%02d" % i, "commence": "2026-06-%02d" % (i + 1),
            "key": "2026-06-%02d|G%02d" % (i + 1, i)}


def _keyed_feed(ids):
    games = [_kid(i) for i in ids]
    # seen_ids-aware: re-surface any game whose id is not yet folded (so a PRESERVED
    # cursor re-serves the SAME games next cycle, exactly like the live provider).
    def _feed(n, since="", seen_ids=None, **kw):
        seen = set(seen_ids or ())
        return [g for g in games if g["game_id"] not in seen]
    return _feed


def _arm(monkeypatch, tmp_path):
    """Create the sentinel on a tmp path so _pipeline_armed() / recalibrator see ARMED."""
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)
    return sentinel


def _disarm(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")


def _state(outcome, *, idx=0, p0=0.55):
    s = {"sport": "nba", "game_id": "g", "asof_idx": idx, "p0": p0}
    if outcome is not None:
        s["outcome"] = outcome
    return s


def _good_game(gid, *, label, p0):
    return {"sport": "nba", "game_id": gid, "outcome": 1.0,
            "states": [_state(1.0, idx=0, p0=p0), _state(0.0, idx=1, p0=1.0 - p0)]}


def _gate(c):  # neutral gate; only relevant to the planted-null test
    return {"ship": True, "gate_results": {}, "reasons": []}


def _run(name, ckpt, tmp_path, recalibrate_fn, ids=(0, 1, 2), gate_fn=_gate, now=1000.0):
    return D.run_cycle(
        name=name, settled_games_fn=_keyed_feed(list(ids)),
        recalibrate_fn=recalibrate_fn, gate_fn=gate_fn,
        store_root=str(tmp_path / "art"), ckpt_path=ckpt,
        proposals_path=tmp_path / "p.jsonl", reject_path=tmp_path / "r.jsonl",
        status_path=tmp_path / "s.jsonl", now=now)


# --- recalibrate_fn fakes that thread the out-of-band report (daemon passes report=) ---
def _genuine_none(n, settled, window, report=None):
    if isinstance(report, dict):
        report["reason"], report["transient"] = "cold_start", False
    return None


def _transient_none(n, settled, window, report=None):
    if isinstance(report, dict):
        report["reason"], report["transient"] = "feed_degraded", True
    return None


def _raises(n, settled, window, report=None):
    raise RuntimeError("parquet hiccup")  # a transient IO failure


# --------------------------------------------------------------------------- (1) genuine
def test_armed_genuine_no_candidate_advances_cursor(monkeypatch, tmp_path):
    _arm(monkeypatch, tmp_path)
    ckpt = str(tmp_path / "ck.json")
    res = _run("nba", ckpt, tmp_path, _genuine_none)
    assert res.decision == D.NO_CANDIDATE
    cur = load_checkpoint(ckpt).cursor("nba")
    # GENUINE evaluated decline under arm -> the processed batch is consumed (advance).
    assert set(cur.get("seen_ids", [])) == {"G00", "G01", "G02"}
    assert cur.get("high_water", "")  # high-water moved forward


def test_armed_genuine_real_recalibrator_advances(monkeypatch, tmp_path):
    """The REAL build_candidate on a perfectly-calibrated batch declines as a no-op (MF2,
    report reason='degenerate_base', transient=False) -> the honest REJECT path ADVANCES."""
    _arm(monkeypatch, tmp_path)
    ckpt = str(tmp_path / "ck.json")
    # 20 already-calibrated games -> Platt re-fit is the identity -> degenerate decline.
    calibrated = [_good_game("G%02d" % i, label=(i % 2), p0=0.5) for i in range(20)]
    feed = lambda n, since="", seen_ids=None, **kw: [
        g for g in calibrated if g["game_id"] not in set(seen_ids or ())]
    res = D.run_cycle(
        name="nba", settled_games_fn=feed,
        recalibrate_fn=RC.build_candidate, gate_fn=_gate,
        store_root=str(tmp_path / "art"), ckpt_path=ckpt,
        proposals_path=tmp_path / "p.jsonl", reject_path=tmp_path / "r.jsonl",
        status_path=tmp_path / "s.jsonl", now=1000.0)
    assert res.decision == D.NO_CANDIDATE
    cur = load_checkpoint(ckpt).cursor("nba")
    assert len(cur.get("seen_ids", [])) == 20  # evaluated decline -> advanced


# --------------------------------------------------------------------------- (2) transient
def test_armed_transient_report_does_not_advance_and_retries(monkeypatch, tmp_path):
    _arm(monkeypatch, tmp_path)
    ckpt = str(tmp_path / "ck.json")
    res1 = _run("nba", ckpt, tmp_path, _transient_none, now=1.0)
    assert res1.decision == D.NO_CANDIDATE
    cur = load_checkpoint(ckpt).cursor("nba")
    # TRANSIENT bail -> cursor PRESERVED (never silent-skip the settled games).
    assert list(cur.get("seen_ids", []) or []) == []
    assert str(cur.get("high_water", "") or "") == ""
    # next cycle RE-SURFACES the same 3 games (retried, not permanently dropped).
    res2 = _run("nba", ckpt, tmp_path, _transient_none, now=2.0)
    assert res2.n_new == 3


def test_armed_real_feed_degraded_does_not_advance(monkeypatch, tmp_path):
    """The REAL build_candidate on an all-bad batch raises FeedDegradedError internally ->
    returns None with report transient=True -> the daemon PRESERVES the cursor."""
    _arm(monkeypatch, tmp_path)
    ckpt = str(tmp_path / "ck.json")
    bad = [{"sport": "nba", "game_id": "B1", "outcome": 1.0, "states": []},
           {"sport": "nba", "game_id": "B2", "outcome": 0.0,
            "states": [_state(0.0, p0=0.6)]}]
    feed = lambda n, since="", seen_ids=None, **kw: [
        g for g in bad if g["game_id"] not in set(seen_ids or ())]
    res = D.run_cycle(
        name="nba", settled_games_fn=feed, recalibrate_fn=RC.build_candidate,
        gate_fn=_gate, store_root=str(tmp_path / "art"), ckpt_path=ckpt,
        proposals_path=tmp_path / "p.jsonl", reject_path=tmp_path / "r.jsonl",
        status_path=tmp_path / "s.jsonl", now=1.0)
    assert res.decision == D.NO_CANDIDATE
    cur = load_checkpoint(ckpt).cursor("nba")
    assert list(cur.get("seen_ids", []) or []) == []  # degraded feed -> preserved


def test_armed_recalibrate_raise_does_not_advance_and_retries(monkeypatch, tmp_path):
    _arm(monkeypatch, tmp_path)
    ckpt = str(tmp_path / "ck.json")
    res1 = _run("nba", ckpt, tmp_path, _raises, now=1.0)
    assert res1.decision == D.ERROR
    cur = load_checkpoint(ckpt).cursor("nba")
    assert list(cur.get("seen_ids", []) or []) == []  # raise -> preserved (transient)
    res2 = _run("nba", ckpt, tmp_path, _raises, now=2.0)
    assert res2.n_new == 3  # retried


# --------------------------------------------------------------------------- (4) inert
def test_inert_sentinel_absent_preserves_seen_ids(monkeypatch, tmp_path):
    _disarm(monkeypatch, tmp_path)
    ckpt = str(tmp_path / "ck.json")
    # Even a report claiming transient=False must NOT advance when inert (flag-off):
    # the games were never folded, so they must re-surface once armed.
    res = _run("nba", ckpt, tmp_path, _genuine_none)
    assert res.decision == D.NO_CANDIDATE
    cur = load_checkpoint(ckpt).cursor("nba")
    assert list(cur.get("seen_ids", []) or []) == []
    assert str(cur.get("high_water", "") or "") == ""


# --------------------------------------------------------------------------- (5) gate intact
def test_planted_null_still_rejects_through_gate(monkeypatch, tmp_path):
    """The fix must not weaken the gate: a candidate carrying a PLANTED-NULL (no real OOS
    lift, base==cand) must still be REJECTED by the real 5-gate via the daemon's SHIP rule
    (oos_improves False / 0 replicated corpora -> REJECT, never SHIP)."""
    _arm(monkeypatch, tmp_path)
    ckpt = str(tmp_path / "ck.json")
    null_cand = {
        "base_preds": [0.5, 0.5, 0.5, 0.5], "cand_preds": [0.5, 0.5, 0.5, 0.5],
        "y": [0, 1, 0, 1], "kind": "prob",
        "fold_results": [{"delta": 0.0, "metric": "brier", "fold_id": 0}],
        "corpora": [], "primary_corpus_id": "p",
        "stability_metric_fn": lambda a, b: 0.0, "stability_data": [],
        "train_features": {"x": 1.0}, "infer_features": {"x": 1.0},
        "artifact": None, "artifact_meta": {"n_features_in": 1},
        "oos_improves": False, "min_corpora": 2,
        "payload": {"note": "calibration, not edge"},
    }
    res = _run("nba", ckpt, tmp_path, lambda n, s, w, report=None: null_cand)
    assert res.decision == D.REJECT  # planted null is rejected; gate NOT weakened
    assert res.shipped_version is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
