"""tests/test_R28_U1_played_games_backfill.py — R28_U1 played-games backfill tests.

Validates the post-backfill state of ``data/nba/linescores_all.json`` after
``scripts/backfill_linescores_played_games.py`` runs against the CDN
boxscore endpoint. Skips gracefully when the file or ``.bak_R28_U1`` sidecar
is absent.

Checks:
  1. schema_unchanged — every 2024-25/2025-26 row carries the legacy keys
     consumed by m2_family / OT / WinProb training (q1..q4, h1, h1_total,
     home_team_id).
  2. no_duplicates — JSON top-level dict has unique keys and every row is
     a single dict (sanity guard against accidental list conversion).
  3. real_quarters_for_new_rows — every row with source='cdn_boxscore' has
     non-zero quarter totals on both sides AND realistic per-team total
     (60..200).
  4. idempotent_no_regression — row count never DECREASES vs the
     .bak_R28_U1 sidecar, every pre-existing game_id still present.
  5. ot_handled — any row with had_ot=1 has positive OT points and a
     plausible regulation+OT total.
  6. older_seasons_untouched_outside_recent — counts for seasons OLDER
     than 2024-25 are unchanged (backfill only targets 2024-25/2025-26).
  7. stub_count_decreased_or_equal — number of stub rows (sum q1..q4 == 0)
     in 2025-26 is <= the count in the backup. Probes the actual job.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def _resolve_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else PROJECT_DIR


ROOT_DIR = _resolve_root()
LS_PATH = os.path.join(ROOT_DIR, "data", "nba", "linescores_all.json")
BAK_PATH = LS_PATH + ".bak_R28_U1"

_LEGACY_KEYS = {
    "home_q1", "home_q2", "home_q3", "home_q4",
    "away_q1", "away_q2", "away_q3", "away_q4",
    "home_h1", "away_h1", "h1_total", "home_team_id",
}


def _season_prefix(gid: str) -> str:
    """0022500001 -> '2025-26'."""
    try:
        yy = int(gid[3:5])
        return f"20{yy:02d}-{(yy + 1) % 100:02d}"
    except Exception:
        return "unk"


def _is_stub(row: dict) -> bool:
    """Stub if sum of all 8 quarter values == 0."""
    if not isinstance(row, dict):
        return True
    s = 0
    for side in ("home", "away"):
        for i in range(1, 5):
            try:
                s += int(row.get(f"{side}_q{i}", 0) or 0)
            except (TypeError, ValueError):
                pass
    return s == 0


def _load_or_skip(path: str, label: str) -> dict:
    if not os.path.exists(path):
        pytest.skip(f"{label} missing at {path} (backfill not run yet)")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        pytest.skip(f"{label} is not a dict payload")
    return d


def test_schema_unchanged():
    """Every 2024-25/2025-26 row carries the legacy keys."""
    d = _load_or_skip(LS_PATH, "linescores_all.json")
    rows = {k: v for k, v in d.items()
            if _season_prefix(k) in ("2024-25", "2025-26")}
    if not rows:
        pytest.skip("no recent-season rows present yet")
    missing = 0
    for gid, row in rows.items():
        if not isinstance(row, dict):
            pytest.fail(f"row {gid} is not a dict: {type(row).__name__}")
        if not _LEGACY_KEYS.issubset(row.keys()):
            missing += 1
    assert missing == 0, (
        f"{missing}/{len(rows)} 2024-25+2025-26 rows missing legacy keys"
    )


def test_no_duplicates():
    """JSON dict guarantees unique keys; verify each row is a single dict."""
    d = _load_or_skip(LS_PATH, "linescores_all.json")
    bad = [k for k, v in d.items() if not isinstance(v, dict)]
    assert not bad, f"{len(bad)} rows have non-dict shape (e.g. {bad[:3]})"
    assert len(set(d.keys())) == len(d.keys()), "duplicate keys somehow"


def test_real_quarters_for_new_rows():
    """Every cdn_boxscore-sourced row has non-zero quarter totals + plausible
    per-team totals (60..200 including any OT)."""
    d = _load_or_skip(LS_PATH, "linescores_all.json")
    new_rows = [(k, v) for k, v in d.items()
                if isinstance(v, dict) and v.get("source") == "cdn_boxscore"]
    if not new_rows:
        pytest.skip("no cdn_boxscore rows yet (backfill not run)")
    bad = []
    for gid, ls in new_rows:
        try:
            home = sum(int(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5))
            away = sum(int(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5))
            home += int(ls.get("home_pts_ot", 0) or 0)
            away += int(ls.get("away_pts_ot", 0) or 0)
        except (TypeError, ValueError):
            bad.append((gid, "parse-err"))
            continue
        if home == 0 or away == 0:
            bad.append((gid, f"zero side: {home}/{away}"))
            continue
        if not (60 <= home <= 200 and 60 <= away <= 200):
            bad.append((gid, f"implausible total: {home}/{away}"))
    assert not bad, f"{len(bad)} bad cdn_boxscore rows (e.g. {bad[:3]})"


def test_idempotent_no_regression():
    """Backfill never DELETES rows — post-count >= pre-count everywhere."""
    after = _load_or_skip(LS_PATH, "linescores_all.json")
    before = _load_or_skip(BAK_PATH, "linescores_all.json.bak_R28_U1")
    assert len(after) >= len(before), (
        f"row count regressed: after={len(after)} before={len(before)}"
    )
    missing = [gid for gid in before if gid not in after]
    assert not missing, (
        f"{len(missing)} pre-existing rows missing (e.g. {missing[:3]})"
    )


def test_ot_handled():
    """had_ot=1 rows have positive OT pts and plausible totals."""
    d = _load_or_skip(LS_PATH, "linescores_all.json")
    ot_rows = [(gid, v) for gid, v in d.items()
               if isinstance(v, dict) and int(v.get("had_ot", 0) or 0) == 1]
    if not ot_rows:
        pytest.skip("no OT rows tagged in linescores yet")
    for gid, ls in ot_rows:
        h_ot = int(ls.get("home_pts_ot", 0) or 0)
        a_ot = int(ls.get("away_pts_ot", 0) or 0)
        assert h_ot + a_ot > 0, f"{gid} had_ot=1 but zero OT pts"
        h_total = sum(int(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5)) + h_ot
        a_total = sum(int(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5)) + a_ot
        assert 80 <= h_total <= 200, f"{gid} home total {h_total} implausible"
        assert 80 <= a_total <= 200, f"{gid} away total {a_total} implausible"


def test_older_seasons_untouched_outside_recent():
    """Counts for seasons older than 2024-25 must match the backup exactly."""
    after = _load_or_skip(LS_PATH, "linescores_all.json")
    before = _load_or_skip(BAK_PATH, "linescores_all.json.bak_R28_U1")
    c_before = Counter(_season_prefix(k) for k in before.keys())
    c_after = Counter(_season_prefix(k) for k in after.keys())
    target_seasons = {"2024-25", "2025-26"}
    for season, n_before in c_before.items():
        if season in target_seasons:
            continue
        n_after = c_after.get(season, 0)
        assert n_after == n_before, (
            f"{season}: count changed from {n_before} to {n_after} "
            f"(backfill should only modify 2024-25/2025-26)"
        )


def test_stub_count_decreased_or_equal():
    """Stub count in 2025-26 should be <= backup (R28_U1 replaces stubs)."""
    after = _load_or_skip(LS_PATH, "linescores_all.json")
    before = _load_or_skip(BAK_PATH, "linescores_all.json.bak_R28_U1")
    s_after = sum(1 for gid, v in after.items()
                  if _season_prefix(gid) == "2025-26" and _is_stub(v))
    s_before = sum(1 for gid, v in before.items()
                   if _season_prefix(gid) == "2025-26" and _is_stub(v))
    assert s_after <= s_before, (
        f"2025-26 stub count grew: before={s_before} after={s_after}"
    )
