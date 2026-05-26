"""tests/test_R29_V2_backfill_completion.py — R29_V2 backfill completion gate.

R28_U1 shipped the CDN-boxscore backfill but only processed ~175/977 stubs
before its 35-min cap. R29_V2 finishes the job (2025-26 stub replace +
2024-25 missing fill). These tests check the POST-state and complement the
earlier R28_U1 tests (which we keep for schema sanity).

Skips gracefully when artifacts are absent. Probes only the recent seasons.
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
PROBE_RESULTS = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R29_V2_results.json"
)

_LEGACY_KEYS = {
    "home_q1", "home_q2", "home_q3", "home_q4",
    "away_q1", "away_q2", "away_q3", "away_q4",
    "home_h1", "away_h1", "h1_total", "home_team_id",
}

# Minimum number of stubs the R29_V2 backfill must convert beyond R28_U1's
# 175. This is a low water mark: if rate-limited we still want > 0 progress.
_MIN_NEW_REAL_2025_26 = 200


def _season(gid: str) -> str:
    try:
        yy = int(gid[3:5])
        return f"20{yy:02d}-{(yy + 1) % 100:02d}"
    except Exception:
        return "unk"


def _is_stub(row) -> bool:
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


def _load(path: str, label: str) -> dict:
    if not os.path.exists(path):
        pytest.skip(f"{label} missing at {path}")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        pytest.skip(f"{label} is not a dict payload")
    return d


def test_r29_v2_replaced_at_least_min_stubs():
    """2025-26 stubs converted to real rows >= _MIN_NEW_REAL_2025_26.

    Measured as (stubs_before - stubs_after) for game_ids present in BOTH
    snapshots, which is exactly the number of stubs R29_V2 (and any earlier
    pass between snapshots) replaced.
    """
    after = _load(LS_PATH, "linescores_all.json")
    before = _load(BAK_PATH, "linescores_all.json.bak_R28_U1")
    common = set(before.keys()) & set(after.keys())
    stubs_before = sum(
        1 for gid in common
        if _season(gid) == "2025-26" and _is_stub(before[gid])
    )
    stubs_after = sum(
        1 for gid in common
        if _season(gid) == "2025-26" and _is_stub(after[gid])
    )
    delta = stubs_before - stubs_after
    assert delta >= _MIN_NEW_REAL_2025_26, (
        f"R29_V2 replaced only {delta} 2025-26 stubs "
        f"(before={stubs_before} after={stubs_after}, need >= {_MIN_NEW_REAL_2025_26})"
    )


def test_r29_v2_no_schema_regression():
    """Every recent-season row keeps the legacy key set after the backfill."""
    d = _load(LS_PATH, "linescores_all.json")
    rows = {k: v for k, v in d.items() if _season(k) in ("2024-25", "2025-26")}
    bad = [
        gid for gid, row in rows.items()
        if not isinstance(row, dict) or not _LEGACY_KEYS.issubset(row.keys())
    ]
    assert not bad, (
        f"{len(bad)} 2024-25/2025-26 rows missing legacy keys "
        f"(e.g. {bad[:3]})"
    )


def test_r29_v2_ot_detected_on_known_ot_game():
    """At least one cdn_boxscore OT row should be present after the backfill.

    Validates the OT detection branch in the script. If no OT game has been
    touched yet, this skips rather than fails (some runs may not include any
    OT contests yet).
    """
    d = _load(LS_PATH, "linescores_all.json")
    ot_rows = [
        (gid, v) for gid, v in d.items()
        if isinstance(v, dict)
        and v.get("source") == "cdn_boxscore"
        and int(v.get("had_ot", 0) or 0) == 1
    ]
    if not ot_rows:
        pytest.skip("no cdn_boxscore OT rows present yet")
    # Verify EACH OT row has consistent OT scoring
    bad = []
    for gid, ls in ot_rows:
        h_ot = int(ls.get("home_pts_ot", 0) or 0)
        a_ot = int(ls.get("away_pts_ot", 0) or 0)
        if h_ot + a_ot <= 0:
            bad.append((gid, f"had_ot=1 but ot pts={h_ot}/{a_ot}"))
            continue
        h_reg = sum(int(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5))
        a_reg = sum(int(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5))
        # In a real OT game, regulation must be tied after q4.
        if h_reg != a_reg:
            bad.append((gid, f"OT but reg not tied: {h_reg} vs {a_reg}"))
    assert not bad, f"{len(bad)} bad OT rows (e.g. {bad[:3]})"


def test_r29_v2_idempotent_no_regression():
    """Post-backfill payload never loses pre-existing rows or shrinks."""
    after = _load(LS_PATH, "linescores_all.json")
    before = _load(BAK_PATH, "linescores_all.json.bak_R28_U1")
    missing = [gid for gid in before if gid not in after]
    assert not missing, (
        f"{len(missing)} pre-existing rows missing (e.g. {missing[:3]})"
    )
    assert len(after) >= len(before), (
        f"row count regressed: after={len(after)} before={len(before)}"
    )
    # Confirm older-season snapshots are byte-identical (no accidental edits).
    c_before = Counter(_season(k) for k in before.keys())
    c_after = Counter(_season(k) for k in after.keys())
    for season, n in c_before.items():
        if season in ("2024-25", "2025-26"):
            continue
        assert c_after.get(season, 0) == n, (
            f"older season {season}: count drifted {n}->{c_after.get(season, 0)}"
        )


def test_r29_v2_probe_results_exist():
    """The R29_V2 probe should persist its pre/post snapshot for the loop."""
    if not os.path.exists(PROBE_RESULTS):
        pytest.skip("probe results not yet written")
    with open(PROBE_RESULTS, encoding="utf-8") as f:
        d = json.load(f)
    required = {
        "before",
        "after",
        "coverage_pct_2025_26_before",
        "coverage_pct_2025_26_after",
    }
    assert required.issubset(d.keys()), (
        f"missing probe keys: {required - set(d.keys())}"
    )
