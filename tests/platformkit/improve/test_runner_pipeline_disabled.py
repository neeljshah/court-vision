"""tests.platformkit.improve.test_runner_pipeline_disabled -- MF1 parity (defense-in-depth B).

With the PIPELINE_ENABLED sentinel ABSENT and recalibrator.py importable, the runner's
default recalibrate_fn must return None and a full cycle must decide NO_CANDIDATE,
byte-identical to the pre-recalibrator baseline. This proves the runner stays inert even
though a real recalibrator now exists on the import path.

Per-file test only (full pytest freezes the box). ASCII; stdlib + numpy deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import selfimprove_runner as R  # noqa: E402
from scripts.platformkit.improve import selfimprove_daemon as D  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


def _settled_game(i):
    return {"sport": "nba", "game_id": "G%02d" % i, "outcome": 1.0,
            "commence": "2026-06-%02d" % (i + 1),
            "states": [{"p0": 0.4, "outcome": 1.0}, {"p0": 0.4, "outcome": 1.0}]}


def test_real_sentinel_path_resolves_under_repo_root():
    """Guard the parents[3] root: the REAL (unpatched) SENTINEL_PATH must resolve under
    nba-ai-system/data/cache/improve/PIPELINE_ENABLED. A parents[4] regression points one
    level ABOVE the repo so the human-created kill-switch could never be turned ON. The
    parity tests below monkeypatch SENTINEL_PATH to a tmp path and so never exercise the
    real path -- this test inspects the module constant directly."""
    real = PF.SENTINEL_PATH.resolve()
    tail = ("nba-ai-system", "data", "cache", "improve", "PIPELINE_ENABLED")
    assert real.parts[-len(tail):] == tail, (
        "SENTINEL_PATH %s must resolve under nba-ai-system/data/cache/improve" % real)
    assert real == (PROJECT_DIR / "data" / "cache" / "improve" / "PIPELINE_ENABLED")


def test_default_recalibrate_fn_inert_when_sentinel_absent(monkeypatch, tmp_path):
    # Sentinel ABSENT (points at a nonexistent path) -- recalibrator.py IS importable.
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    assert PF.pipeline_enabled() is False
    # Sanity: recalibrator import succeeds (so we're really testing layer-B, not a missing module).
    from scripts.platformkit.improve import recalibrator as _rc  # noqa: F401
    settled = [_settled_game(i) for i in range(12)]
    out = R._default_recalibrate_fn("nba", settled, 12)
    assert out is None  # layer B: inert BEFORE the recalibrator import.


def test_cycle_is_no_candidate_when_sentinel_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    ckpt = str(tmp_path / "ckpt.json")
    feed = lambda n, since="", **kw: [_settled_game(i) for i in range(12)]
    res = D.run_cycle(
        name="nba",
        settled_games_fn=feed,
        recalibrate_fn=R._default_recalibrate_fn,
        gate_fn=lambda c: {"ship": True, "gate_results": {}, "reasons": []},
        store_root=str(tmp_path / "art"), ckpt_path=ckpt,
        proposals_path=tmp_path / "p.jsonl", reject_path=tmp_path / "r.jsonl",
        status_path=tmp_path / "s.jsonl", now=1000.0)
    # Byte-identical to the baseline: a non-empty batch yields NO_CANDIDATE, nothing ships.
    assert res.decision == D.NO_CANDIDATE
    assert res.shipped_version is None
    assert res.n_new == 12
