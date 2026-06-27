"""tests.platformkit.improve.test_recalibrator -- the recal BRIDGE contract (MF1+MF2+MF3).

Asserts:
  (a) MF1 -- sentinel ABSENT -> build_candidate returns None even on a NON-EMPTY,
      foldable settled batch (the kill-switch is the first line; inert when absent).
  (b) MF3 -- a batch with an empty-states game + an all-zero-outcome game has BOTH
      EXCLUDED from the folded y (quarantined), never 0-filled into observations.
  (c) MF2 -- a no-op / collapse candidate -> None with a recorded degenerate reason.
  (d) no $/pnl/roi/edge key anywhere in the candidate dict; carries the calibration
      note + vs_close='UNPROVEN'.

The sentinel is monkeypatched via pipeline_flag.SENTINEL_PATH (never created on real disk).
Per-file test only (full pytest freezes the box). ASCII; stdlib + numpy deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import recalibrator as RC  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


# --------------------------------------------------------------------------- helpers
def _state(outcome, *, idx=0, p0=0.55):
    s = {"sport": "nba", "game_id": "g", "asof_idx": idx, "p0": p0}
    if outcome is not None:
        s["outcome"] = outcome
    return s


def _good_game(gid, *, label, p0):
    """A foldable game with a confirmed-positive somewhere when label==1.

    The audit (MF3) quarantines any game with NO confirmed-positive state, so a clean
    foldable game must carry at least one outcome==1 state. We attach a (p0, outcome)
    per-state observation: a win-state (1) and a loss-state (0) so the folded window
    carries BOTH classes while still passing the audit (the win state is the confirmed
    positive). p0 is the BASE probability the candidate must recalibrate.
    """
    return {"sport": "nba", "game_id": gid, "outcome": 1.0,
            "states": [_state(1.0, idx=0, p0=p0),
                       _state(0.0, idx=1, p0=1.0 - p0)]}


def _settled_batch():
    """A miscalibrated, well-formed batch with >= _MIN_OBS clean obs and BOTH classes,
    so a Platt fit is genuine (non-degenerate). Win-states sit at a low p0 and loss-states
    at the complementary high p0, so recalibration actually MOVES the predictions
    (not a no-op) and the audit folds every game (each has a confirmed-positive state)."""
    return [_good_game("G%d" % i, label=1, p0=0.35) for i in range(8)]


def _enable(monkeypatch, tmp_path):
    """Create the sentinel on a tmp path and point pipeline_flag at it (flag ON)."""
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)
    return sentinel


# ---------------------------------------------------------- path regression guard
def test_real_sentinel_path_resolves_under_repo_root():
    """Guard the parents[3] root: the REAL (unpatched) SENTINEL_PATH must resolve to
    the DOCUMENTED location under the repo, nba-ai-system/data/cache/improve/
    PIPELINE_ENABLED. A parents[4] regression points one level ABOVE the repo, so the
    human-created kill-switch sentinel would never be seen. The other MF1 tests
    monkeypatch SENTINEL_PATH to a tmp path and so cannot catch that defect -- this one
    inspects the real module constant directly."""
    real = PF.SENTINEL_PATH.resolve()
    tail = ("nba-ai-system", "data", "cache", "improve", "PIPELINE_ENABLED")
    assert real.parts[-len(tail):] == tail, (
        "SENTINEL_PATH %s must resolve under nba-ai-system/data/cache/improve" % real)
    # The sentinel must sit beside this test's repo root (parents[3] == repo root).
    assert real == (PROJECT_DIR / "data" / "cache" / "improve" / "PIPELINE_ENABLED")


# --------------------------------------------------------------------------- (a) MF1
def test_sentinel_absent_returns_none_even_with_nonempty_batch(monkeypatch, tmp_path):
    # Point the sentinel at a path that does NOT exist (flag OFF).
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    assert PF.pipeline_enabled() is False
    out = RC.build_candidate("nba", _settled_batch())
    assert out is None  # inert: kill-switch is the first line, even on a full batch.


# --------------------------------------------------------------------------- (b) MF3
def test_quarantined_games_excluded_from_folded_y(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    empty = {"sport": "nba", "game_id": "EMPTY", "outcome": 1.0, "states": []}
    allzero = {"sport": "nba", "game_id": "ALLZERO", "outcome": 0.0,
               "states": [_state(0.0, idx=0, p0=0.6), _state(0.0, idx=1, p0=0.6)]}
    # majority good so the feed is not degraded; the 2 bad games must be quarantined.
    batch = [empty, allzero] + _settled_batch()
    cand = RC.build_candidate("nba", batch)
    assert cand is not None
    # The quarantined games contributed NO observations: only clean p0=0.35/0.65 rows
    # are present. An empty-states game contributes nothing; an all-zero game (p0=0.6)
    # would show 0.6 -- assert that NEITHER quarantined signature leaked into the fold.
    base = cand["base_preds"]
    assert all(abs(b - 0.6) > 1e-9 for b in base)  # all-zero game's p0=0.6 never folded
    assert cand["n_quarantined"] == 2
    assert cand["n_clean"] == len(_settled_batch())
    # y is never 0-filled with the quarantined labels: count of clean obs only.
    assert len(cand["y"]) == len(base)


def test_degraded_feed_returns_none(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    # all-bad batch -> audit raises FeedDegradedError -> NO_CANDIDATE (never 0-fill).
    bad = [{"sport": "nba", "game_id": "E1", "outcome": 1.0, "states": []},
           {"sport": "nba", "game_id": "Z1", "outcome": 0.0,
            "states": [_state(0.0, p0=0.6)]}]
    assert RC.build_candidate("nba", bad) is None


# --------------------------------------------------------------------------- (c) MF2
def test_noop_candidate_rejected_with_degenerate_reason(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    # A perfectly-calibrated batch: p0 already equals the empirical rate, so a Platt
    # re-fit is (within noise) the identity -> degenerate no-op -> None.
    games = []
    for i in range(20):
        # half the p0=0.5 games win, half lose -> base already calibrated -> identity fit.
        games.append(_good_game("W%d" % i, label=(i % 2), p0=0.5))
    out = RC.build_candidate("nba", games)
    assert out is None  # MF2: a no-op / collapsed candidate is an honest REJECT.


def test_cold_start_too_few_obs_returns_none(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tiny = [_good_game("W0", label=1, p0=0.4)]  # 2 obs < _MIN_OBS
    assert RC.build_candidate("nba", tiny) is None


# --------------------------------------------------------------------------- (d) no $
def test_candidate_has_no_dollar_keys_and_carries_calibration_note(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cand = RC.build_candidate("nba", _settled_batch())
    assert cand is not None

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                assert not any(tok in kl for tok in ("roi", "pnl", "dollar", "edge", "$")), \
                    "forbidden $-edge key: %s" % k
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _walk(v)

    _walk(cand)
    assert cand["note"] == "calibration, not edge"
    assert cand["vs_close"] == "UNPROVEN"
    # shape the gate consumes is present.
    for key in ("base_preds", "cand_preds", "y", "fold_results", "stability_metric_fn",
                "artifact", "payload"):
        assert key in cand
