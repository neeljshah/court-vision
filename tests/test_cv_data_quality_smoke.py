"""
tests/test_cv_data_quality_smoke.py — CV data-quality smoke tests.

Verifies five invariants against the live cv_features SQLite table after
Bug 2 + Bug 18 + Bug 33 fixes in backfill_cv_features.py,
cv_feature_registry.py, and tracking_feature_extractor.py.

Run:
    python -m pytest tests/test_cv_data_quality_smoke.py -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
_DB_CANDIDATES = [
    ROOT / "data" / "local.db",
    ROOT / "data" / "nba.db",
    ROOT / "data" / "nba_ai.db",
]


def _get_con() -> sqlite3.Connection:
    for path in _DB_CANDIDATES:
        if path.exists():
            con = sqlite3.connect(str(path))
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "cv_features" in tables:
                return con
            con.close()
    pytest.skip("No SQLite database with cv_features table found")


# ── Invariant 1: Ghost-slot guard ─────────────────────────────────────────────

def test_no_ghost_slots() -> None:
    """No row should have touches_per_game=0 AND n_shots_tracked=0 simultaneously.

    Ghost slots indicate the guard in backfill_cv_features.py didn't fire.
    Bug 2 fix should have eliminated these rows.
    """
    con = _get_con()
    rows = con.execute("""
        SELECT t.game_id, t.player_id
        FROM cv_features t
        JOIN cv_features s
          ON t.game_id = s.game_id AND t.player_id = s.player_id
        WHERE t.feature_name = 'touches_per_game' AND t.feature_value = 0
          AND s.feature_name = 'n_shots_tracked' AND s.feature_value = 0
        LIMIT 5
    """).fetchall()
    con.close()

    if rows:
        print(f"\n[FAIL] Ghost slots found ({len(rows)} shown): {rows}")
    else:
        print("\n[PASS] No ghost slots detected.")

    assert len(rows) == 0, (
        f"Bug 2 guard inactive — {len(rows)} ghost (game_id, player_id) pairs found: {rows}"
    )


# ── Invariant 2: INSERT OR REPLACE (no duplicate unique keys) ─────────────────

def test_no_duplicate_feature_rows() -> None:
    """Each (game_id, player_id, feature_name) triple must appear at most once.

    The UNIQUE constraint + INSERT OR REPLACE should prevent duplicates.
    """
    con = _get_con()
    dups = con.execute("""
        SELECT game_id, player_id, feature_name, COUNT(*) AS cnt
        FROM cv_features
        GROUP BY game_id, player_id, feature_name
        HAVING cnt > 1
        LIMIT 5
    """).fetchall()
    con.close()

    if dups:
        print(f"\n[FAIL] Duplicate keys found: {dups}")
    else:
        print("\n[PASS] No duplicate (game_id, player_id, feature_name) rows.")

    assert len(dups) == 0, (
        f"INSERT OR REPLACE not active — {len(dups)} duplicate key groups found: {dups}"
    )


# ── Invariant 3: Bug 18 NaN guard (shot_clock != 0 when shots exist) ──────────

def test_no_zero_shot_clock_with_shots() -> None:
    """When n_shots_tracked > 0, avg_shot_clock_at_shot must NOT be 0.

    Valid states: value in (0.01, 24.0] OR column absent (None/not inserted).
    A value of exactly 0 with shots present signals the Bug 18 sentinel leak.
    """
    con = _get_con()
    violations = con.execute("""
        SELECT sc.game_id, sc.player_id,
               sc.feature_value AS shot_clock,
               ns.feature_value AS n_shots
        FROM cv_features sc
        JOIN cv_features ns
          ON sc.game_id = ns.game_id AND sc.player_id = ns.player_id
        WHERE sc.feature_name = 'avg_shot_clock_at_shot'
          AND sc.feature_value = 0
          AND ns.feature_name  = 'n_shots_tracked'
          AND ns.feature_value > 0
        LIMIT 5
    """).fetchall()
    con.close()

    if violations:
        print(f"\n[FAIL] Bug 18 violations (shot_clock=0, n_shots>0): {violations}")
    else:
        print("\n[PASS] No zero shot_clock rows with tracked shots.")

    assert len(violations) == 0, (
        f"Bug 18 NaN guard inactive — {len(violations)} rows have "
        f"avg_shot_clock_at_shot=0 with n_shots_tracked>0: {violations}"
    )


# ── Invariant 4: Bug 33 strict-count drop (≤16 high-zero players) ─────────────

def test_high_zero_fraction_player_count() -> None:
    """Players with n_games>=3 and zero_fraction>=0.80 must number ≤16.

    Pre-fix: 21 such players.  Post-fix target: 15.  Allow 1-unit jitter → max 16.
    """
    con = _get_con()
    rows = con.execute("""
        SELECT player_id,
               COUNT(DISTINCT game_id) AS n_games,
               SUM(CASE WHEN feature_value = 0 THEN 1 ELSE 0 END) * 1.0
                   / COUNT(*) AS zero_frac
        FROM cv_features
        GROUP BY player_id
        HAVING n_games >= 3 AND zero_frac >= 0.80
    """).fetchall()
    con.close()

    count = len(rows)
    print(f"\n[INFO] High-zero-fraction players (n_games>=3, zero_frac>=0.80): {count}")
    if rows:
        for pid, ng, zf in rows[:5]:
            print(f"       player_id={pid}  n_games={ng}  zero_frac={zf:.3f}")

    assert count <= 16, (
        f"Bug 33 strict-count not dropped — {count} high-zero players found (max allowed: 16)"
    )


# ── Invariant 5: Curry sanity (player_id=201939 has ≥1 nonzero feature) ───────

def test_curry_has_nonzero_features() -> None:
    """Stephen Curry (player_id=201939) must have at least 1 cv_features row
    with a nonzero feature_value.

    Was completely zero in worst-case games before the backfill fix.
    """
    con = _get_con()
    total = con.execute(
        "SELECT COUNT(*) FROM cv_features WHERE player_id = 201939"
    ).fetchone()[0]

    nonzero = con.execute(
        "SELECT COUNT(*) FROM cv_features WHERE player_id = 201939 AND feature_value != 0"
    ).fetchone()[0]
    con.close()

    print(f"\n[INFO] Curry rows: total={total}, nonzero={nonzero}")

    assert total >= 1, "Curry (201939) has zero cv_features rows — data missing entirely"
    assert nonzero >= 1, (
        f"Curry (201939) has {total} rows but ALL feature_values are zero — backfill produced ghost data"
    )
