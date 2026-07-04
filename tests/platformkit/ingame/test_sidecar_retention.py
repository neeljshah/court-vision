"""Per-file test for ingame.sidecar_retention (offline, fake clock, tmp dir).

Proves the enrichment-sidecar retention policy (LANE 3):
  * age policy: files strictly older than max_age_days are ARCHIVED, not deleted.
  * MIN_ACTIVE_DAYS floor stops an absurdly-low max_age_days from over-archiving.
  * byte-budget policy: oldest-mtime files are pushed to archive until under budget.
  * ARCHIVE not delete: the file lands at <dir>/_archive/<relpath>, original data intact.
  * _archive/ is never re-swept (no double move, no infinite growth of the walk).
  * idempotent (re-run after archiving is a clean no-op) + per-tree isolation in enforce_all.
  * dry_run plans without moving anything.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_sidecar_retention.py -q
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.ingame import sidecar_retention as ret

NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


def _mk(path: Path, body: str = '{"a":1}\n', age_days: float = 0.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if age_days:
        stamp = NOW.timestamp() - age_days * 86400.0
        os.utime(path, (stamp, stamp))
    return path


def test_age_policy_archives_old_keeps_recent(tmp_path):
    sd = tmp_path / "gumbo_live"
    fresh = _mk(sd / "823120.jsonl", age_days=5)
    old = _mk(sd / "800001.jsonl", age_days=45)
    pol = ret.SidecarPolicy("gumbo_live", sd, max_age_days=30, max_bytes=None)

    res = ret.enforce_dir(pol, now=NOW)

    assert res["kept"] == 1 and res["archived"] == 1 and res["errors"] == 0
    assert fresh.exists(), "recent file stays in place"
    assert not old.exists(), "old file moved out of active tree"
    dest = sd / "_archive" / "800001.jsonl"
    assert dest.exists(), "old file archived, not deleted"
    assert dest.read_text(encoding="utf-8") == '{"a":1}\n'


def test_min_active_days_floor(tmp_path):
    sd = tmp_path / "espn_wp"
    d2 = _mk(sd / "recent.jsonl", age_days=2)
    old = _mk(sd / "old.jsonl", age_days=10)
    # max_age_days=1 must be clamped up to MIN_ACTIVE_DAYS=7, so a 2-day-old file
    # is NOT archive-eligible even though 1 < 2.
    pol = ret.SidecarPolicy("espn_wp", sd, max_age_days=1, max_bytes=None)
    res = ret.enforce_dir(pol, now=NOW)
    assert d2.exists(), "clamped floor keeps a 2-day-old file"
    assert not old.exists()
    assert res["archived"] == 1


def test_byte_budget_pushes_oldest_first(tmp_path):
    sd = tmp_path / "book_depth"
    # 3 files of 100 bytes each, all within age window; budget=150 forces 1 archived
    # (the oldest by mtime), leaving 2 active (200 > 150 is still over after removing
    # only the oldest? No: after removing oldest (100), remaining=200, still > 150 ->
    # remove next oldest too, remaining=100 <= 150, stop). So 2 archived, 1 kept.
    body = "x" * 100
    a = _mk(sd / "a.jsonl", body=body, age_days=3)  # oldest
    b = _mk(sd / "b.jsonl", body=body, age_days=2)
    c = _mk(sd / "c.jsonl", body=body, age_days=1)  # newest
    pol = ret.SidecarPolicy("book_depth", sd, max_age_days=30, max_bytes=150)

    res = ret.enforce_dir(pol, now=NOW)

    assert not a.exists() and not b.exists(), "two oldest archived to clear budget"
    assert c.exists(), "newest kept"
    assert res["kept"] == 1 and res["archived"] == 2


def test_archive_dir_never_reswept(tmp_path):
    sd = tmp_path / "fotmob_live"
    old = _mk(sd / "old.jsonl", age_days=45)
    pol = ret.SidecarPolicy("fotmob_live", sd, max_age_days=30, max_bytes=None)

    r1 = ret.enforce_dir(pol, now=NOW)
    assert r1["archived"] == 1
    # A second run must be a clean no-op: the archived file is under _archive/ and the
    # walk excludes it, so it can never be re-planned/re-moved.
    r2 = ret.enforce_dir(pol, now=NOW)
    assert r2["archived"] == 0 and r2["errors"] == 0
    assert (sd / "_archive" / "old.jsonl").exists()


def test_dry_run_plans_without_moving(tmp_path):
    sd = tmp_path / "cdn_live"
    old = _mk(sd / "g1.jsonl", age_days=45)
    pol = ret.SidecarPolicy("cdn_live", sd, max_age_days=30, max_bytes=None)

    dry = ret.enforce_dir(pol, now=NOW, dry_run=True)
    assert dry["archived"] == 1
    assert old.exists(), "dry_run never moves anything"
    assert not (sd / "_archive" / "g1.jsonl").exists()


def test_plan_dir_is_pure_and_side_effect_free(tmp_path):
    sd = tmp_path / "gumbo_live"
    old = _mk(sd / "old.jsonl", age_days=45)
    pol = ret.SidecarPolicy("gumbo_live", sd, max_age_days=30, max_bytes=None)
    plan = ret.plan_dir(pol, now=NOW)
    assert old.exists(), "plan_dir never moves/deletes"
    assert plan["stale"] == [old]
    assert plan["active"] == []


def test_enforce_all_per_tree_isolated(tmp_path):
    d1 = tmp_path / "t1"
    d2 = tmp_path / "t2"
    old1 = _mk(d1 / "old.jsonl", age_days=45)
    old2 = _mk(d2 / "old.jsonl", age_days=45)
    pols = [
        ret.SidecarPolicy("t1", d1, max_age_days=30, max_bytes=None),
        ret.SidecarPolicy("t2", d2, max_age_days=30, max_bytes=None),
    ]
    res = ret.enforce_all(pols, now=NOW)
    assert res["total_archived"] == 2 and res["total_errors"] == 0
    assert len(res["trees"]) == 2
    assert not old1.exists() and not old2.exists()


def test_missing_dir_is_a_noop(tmp_path):
    pol = ret.SidecarPolicy("ghost", tmp_path / "does_not_exist", max_age_days=30)
    res = ret.enforce_dir(pol, now=NOW)
    assert res["kept"] == 0 and res["archived"] == 0 and res["errors"] == 0


def test_default_policy_covers_five_named_trees():
    names = {p.name for p in ret.DEFAULT_POLICY}
    assert names == {"fotmob_live", "gumbo_live", "book_depth", "espn_wp_mlb", "cdn_live_wnba"}
    for p in ret.DEFAULT_POLICY:
        assert p.max_age_days == 30
        assert p.max_bytes is not None and p.max_bytes > 0
