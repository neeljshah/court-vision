"""tests.platformkit.improve.test_daemon_seen_ids_no_candidate -- SI-P0-03.

A NO_CANDIDATE / INERT cycle must NOT advance the cursor (neither seen_ids nor the
high-water the feed filters by). Otherwise, games consumed WHILE the recalibrator was
inert (flag-off) would be permanently skipped once the PIPELINE_ENABLED sentinel is
created -- they would never be re-considered. This test drives one NO_CANDIDATE cycle
(recalibrate_fn -> None) and asserts the checkpoint cursor is untouched, then a second
cycle re-surfaces the SAME games.

Per-file test only (full pytest freezes the box). ASCII; stdlib deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import selfimprove_daemon as D  # noqa: E402
from scripts.platformkit.improve.checkpoint import load_checkpoint  # noqa: E402


def _kid(i):
    return {"game_id": "G%02d" % i, "commence": "2026-06-%02d" % (i + 1),
            "key": "2026-06-%02d|G%02d" % (i + 1, i)}


def _keyed_feed(ids):
    games = [_kid(i) for i in ids]
    # honour `since` (older-style feed) so we can prove high_water was NOT advanced.
    return lambda n, since="", **kw: [g for g in games if g["key"] > (since or "")]


def _run_no_candidate(name, ckpt, tmp_path):
    return D.run_cycle(
        name=name,
        settled_games_fn=_keyed_feed([0, 1, 2]),
        recalibrate_fn=lambda n, settled, window: None,  # INERT / cold-start
        gate_fn=lambda c: {"ship": True, "gate_results": {}, "reasons": []},
        store_root=str(tmp_path / "art"), ckpt_path=ckpt,
        proposals_path=tmp_path / "p.jsonl", reject_path=tmp_path / "r.jsonl",
        status_path=tmp_path / "s.jsonl", now=1000.0)


def test_no_candidate_does_not_advance_seen_ids_or_high_water(tmp_path):
    ckpt = str(tmp_path / "ckpt.json")
    res = _run_no_candidate("nba", ckpt, tmp_path)
    assert res.decision == D.NO_CANDIDATE
    assert res.n_new == 3

    ck = load_checkpoint(ckpt)
    cur = ck.cursor("nba")
    # SI-P0-03: the inert cycle consumed nothing -> cursor untouched.
    assert list(cur.get("seen_ids", []) or []) == []
    assert str(cur.get("high_water", "") or "") == ""
    assert cur.get("last_decision") == D.NO_CANDIDATE


def test_inert_games_resurface_next_cycle(tmp_path):
    ckpt = str(tmp_path / "ckpt.json")
    _run_no_candidate("nba", ckpt, tmp_path)
    # Second cycle: the SAME 3 games must be re-surfaced (never permanently skipped).
    res2 = _run_no_candidate("nba", ckpt, tmp_path)
    assert res2.decision == D.NO_CANDIDATE
    assert res2.n_new == 3  # re-considered, not skipped.
