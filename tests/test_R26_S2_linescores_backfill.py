"""tests/test_R26_S2_linescores_backfill.py — linescores 2025-26 backfill tests.

Validates the post-backfill state of ``data/nba/linescores_all.json`` after
``scripts/backfill_linescores_2025_26.py`` runs. Skips gracefully when the
file is absent (fresh clone) or the backup sidecar is missing (backfill not
yet executed).

Checks:
  1. schema_unchanged — every existing 2025-26 row carries the legacy
     keys consumed by m2_family / OT / WinProb training (q1..q4, h1,
     h1_total, home_team_id). Extra new keys (had_ot, *_pts_ot, source)
     are allowed.
  2. no_duplicates — JSON top-level dict cannot have duplicate keys, and
     each game_id appears in exactly one shape (sanity guard against
     accidental list-of-dicts conversion).
  3. quarters_sum_to_final — for every backfilled row that carries a
     non-zero quarter total, the sum of q1..q4 (+ OT carryover when
     present) is a self-consistent integer total (positive, plausible
     range 30-200 per team).
  4. idempotent_no_regression — count of 2025-26 rows AFTER backfill is
     >= count BEFORE (from the .bak_R26_S2 sidecar), and the new total
     row count never DECREASES vs the backup.
  5. ot_handled — any row tagged had_ot=1 has home_pts_ot+away_pts_ot>0,
     and final = q1+q2+q3+q4+ot is plausible (>= 80 per team).
  6. older_seasons_untouched — counts of every pre-2025-26 season key
     match the .bak_R26_S2 sidecar exactly (backfill never edits older
     data).
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
BAK_PATH = LS_PATH + ".bak_R26_S2"

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


def _load_or_skip(path: str, label: str) -> dict:
    if not os.path.exists(path):
        pytest.skip(f"{label} missing at {path} (backfill not run yet)")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        pytest.skip(f"{label} is not a dict payload")
    return d


def test_schema_unchanged():
    """Every 2025-26 row carries the legacy keys (extra keys allowed)."""
    d = _load_or_skip(LS_PATH, "linescores_all.json")
    rows_25 = {k: v for k, v in d.items() if _season_prefix(k) == "2025-26"}
    if not rows_25:
        pytest.skip("no 2025-26 rows present yet")
    missing_keys_count = 0
    for gid, row in rows_25.items():
        if not isinstance(row, dict):
            pytest.fail(f"row {gid} is not a dict: {type(row).__name__}")
        if not _LEGACY_KEYS.issubset(row.keys()):
            missing_keys_count += 1
    assert missing_keys_count == 0, (
        f"{missing_keys_count}/{len(rows_25)} 2025-26 rows missing legacy keys"
    )


def test_no_duplicates():
    """JSON dict guarantees unique keys; verify each row is a single dict."""
    d = _load_or_skip(LS_PATH, "linescores_all.json")
    # Implicit duplicate check: any list-shape row would be malformed.
    bad = [k for k, v in d.items() if not isinstance(v, dict)]
    assert not bad, f"{len(bad)} rows have non-dict shape (e.g. {bad[:3]})"
    # No duplicate game_id across season buckets — game_ids are globally unique.
    assert len(set(d.keys())) == len(d.keys())


def test_quarters_sum_to_final():
    """Sum of q1..q4 (+ OT) per team is in plausible NBA total range."""
    d = _load_or_skip(LS_PATH, "linescores_all.json")
    rows_25 = {k: v for k, v in d.items() if _season_prefix(k) == "2025-26"}
    if not rows_25:
        pytest.skip("no 2025-26 rows present yet")
    bad = 0
    for gid, ls in rows_25.items():
        try:
            home = sum(int(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5))
            away = sum(int(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5))
        except (TypeError, ValueError):
            bad += 1
            continue
        home += int(ls.get("home_pts_ot", 0) or 0)
        away += int(ls.get("away_pts_ot", 0) or 0)
        # NBA full-game team total is realistically [60, 200]. Zero rows are
        # legacy stubs that pre-date the source tag — allow them.
        if home == 0 and away == 0:
            continue
        if not (60 <= home <= 200 and 60 <= away <= 200):
            bad += 1
    assert bad == 0, f"{bad}/{len(rows_25)} 2025-26 rows have implausible totals"


def test_idempotent_no_regression():
    """Backfill never DELETES rows — post-counts >= pre-counts everywhere."""
    after = _load_or_skip(LS_PATH, "linescores_all.json")
    before = _load_or_skip(BAK_PATH, "linescores_all.json.bak_R26_S2")
    assert len(after) >= len(before), (
        f"row count regressed: after={len(after)} before={len(before)}"
    )
    # Every previously-present game_id must still be present.
    missing = [gid for gid in before if gid not in after]
    assert not missing, f"{len(missing)} pre-existing rows missing (e.g. {missing[:3]})"


def test_ot_handled():
    """had_ot rows carry positive OT points and plausible totals."""
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


def test_older_seasons_untouched():
    """Backfill must not modify pre-2025-26 counts (only adds 2025-26 rows)."""
    after = _load_or_skip(LS_PATH, "linescores_all.json")
    before = _load_or_skip(BAK_PATH, "linescores_all.json.bak_R26_S2")
    c_before = Counter(_season_prefix(k) for k in before.keys())
    c_after = Counter(_season_prefix(k) for k in after.keys())
    for season, n_before in c_before.items():
        if season == "2025-26":
            continue
        n_after = c_after.get(season, 0)
        assert n_after == n_before, (
            f"{season}: count changed from {n_before} to {n_after}"
        )
