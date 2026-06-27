"""Per-file test for odds_provider.inplay_retention (offline, fake clock, tmp dir).

Proves the CONSERVATIVE in-play history retention sweep:
  * keeps the last keep_days UTC day-buckets, prunes STRICTLY-older dated files;
  * NEVER deletes today's (active) file or a future-dated file (clock skew);
  * NEVER touches the _freshness.json sidecar or any non-dated / legacy file;
  * MIN_KEEP_DAYS floor stops a 0/negative keep_days from wiping recent history;
  * sweep is idempotent (re-run is a no-op) and per-sport isolated;
  * dry_run plans without deleting.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_retention.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.odds_provider import inplay_retention as ret

NOW = datetime(2026, 6, 21, 5, 30, tzinfo=timezone.utc)  # "today" = 2026-06-21 UTC


def _mk(sport_dir, name, body="{}\n"):
    sport_dir.mkdir(parents=True, exist_ok=True)
    p = sport_dir / name
    p.write_text(body, encoding="utf-8")
    return p


def test_keeps_recent_prunes_old(tmp_path):
    sd = tmp_path / "soccer_intl"
    today = _mk(sd, "2026-06-21.jsonl")          # day 0 -- ACTIVE, must stay
    yest = _mk(sd, "2026-06-20.jsonl")           # day 1 -- within 7
    edge = _mk(sd, "2026-06-15.jsonl")           # day 6 -- oldest kept (keep_days=7)
    old1 = _mk(sd, "2026-06-14.jsonl")           # day 7 -- pruned
    old2 = _mk(sd, "2026-05-01.jsonl")           # ancient -- pruned
    fresh = _mk(sd, "_freshness.json", '{"last_capture_ts":"x"}')

    res = ret.sweep_sport(sd, keep_days=7, now=NOW)

    assert today.exists() and yest.exists() and edge.exists(), "recent kept"
    assert not old1.exists() and not old2.exists(), "old pruned"
    assert fresh.exists(), "freshness sidecar never touched"
    assert res["pruned"] == 2 and res["errors"] == 0
    assert res["cutoff"] == "2026-06-15"          # today - (7-1) days


def test_never_deletes_today_or_future(tmp_path):
    sd = tmp_path / "mlb"
    today = _mk(sd, "2026-06-21.jsonl")
    future = _mk(sd, "2026-06-25.jsonl")          # clock-skew guard
    # Even with the minimum window, today + future survive.
    res = ret.sweep_sport(sd, keep_days=ret.MIN_KEEP_DAYS, now=NOW)
    assert today.exists() and future.exists()
    assert res["pruned"] == 0


def test_min_keep_days_floor(tmp_path):
    sd = tmp_path / "nba"
    today = _mk(sd, "2026-06-21.jsonl")
    d2 = _mk(sd, "2026-06-20.jsonl")              # within MIN_KEEP_DAYS=3
    d3 = _mk(sd, "2026-06-19.jsonl")              # within MIN_KEEP_DAYS=3
    old = _mk(sd, "2026-06-10.jsonl")
    # keep_days=0 must be clamped up to MIN_KEEP_DAYS, NOT wipe everything.
    res = ret.sweep_sport(sd, keep_days=0, now=NOW)
    assert today.exists() and d2.exists() and d3.exists()
    assert not old.exists()
    assert res["cutoff"] == "2026-06-19"          # today - (3-1)


def test_skips_non_dated_and_subdirs(tmp_path):
    sd = tmp_path / "tennis"
    legacy = _mk(sd, "2026-06-19_mlb_TORCHC_kalshi.json")  # odd legacy name
    notjson = _mk(sd, "README.txt")
    (sd / "subdir").mkdir(parents=True, exist_ok=True)
    plan = ret.plan_sport_sweep(sd, keep_days=3, now=NOW)
    assert plan["prune"] == [], "non-dated files are never pruned"
    assert legacy.exists() and notjson.exists()


def test_idempotent_and_dry_run(tmp_path):
    sd = tmp_path / "soccer"
    keep = _mk(sd, "2026-06-21.jsonl")
    old = _mk(sd, "2026-06-01.jsonl")
    # dry_run: plans the prune but deletes nothing.
    dry = ret.sweep_sport(sd, keep_days=7, now=NOW, dry_run=True)
    assert dry["pruned"] == 1 and old.exists()
    # real sweep removes it; a second sweep is a clean no-op.
    r1 = ret.sweep_sport(sd, keep_days=7, now=NOW)
    r2 = ret.sweep_sport(sd, keep_days=7, now=NOW)
    assert r1["pruned"] == 1 and not old.exists()
    assert r2["pruned"] == 0 and r2["errors"] == 0
    assert keep.exists()


def test_sweep_all_per_sport_isolated(tmp_path):
    base = tmp_path / "inplay_history"
    _mk(base / "mlb", "2026-06-21.jsonl")
    _mk(base / "mlb", "2026-06-01.jsonl")
    _mk(base / "soccer_intl", "2026-06-20.jsonl")
    _mk(base / "soccer_intl", "2026-05-15.jsonl")
    # A loose file at the ROOT (not a sport dir) must never be touched.
    loose = base / "2026-06-19_mlb_TORCHC_kalshi.json"
    base.mkdir(parents=True, exist_ok=True)
    loose.write_text("{}", encoding="utf-8")

    res = ret.sweep_all(base, keep_days=7, now=NOW)
    assert res["total_pruned"] == 2
    assert loose.exists(), "root-level loose file never pruned"
    assert (base / "mlb" / "2026-06-21.jsonl").exists()
    assert not (base / "mlb" / "2026-06-01.jsonl").exists()
    assert not (base / "soccer_intl" / "2026-05-15.jsonl").exists()
