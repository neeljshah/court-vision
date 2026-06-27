"""tests.platformkit.test_asof_bullpen -- Task-4b game_pk<->event_id bridge + honest DEFER.

The bullpen ERA-proxy feature is DEFERRED (SP-identity source is era-disjoint from
player_gamelogs -- see domains/mlb/asof_bullpen_DEFER.md). These tests therefore lock the
PROVABLE artifact (the game_pk -> event_id bridge) and the honest DEFER verdict:

  * synthetic golden : a tiny hand-built corpus with one clean game, one doubleheader,
    one unmatched game_pk, and one team-dialect mismatch -> exact expected mapping;
  * leak-free        : the bridge is invariant to dropping outcome columns (game-identity
    only) and never maps to an event_id absent from games_current;
  * real-data smoke  : guarded on the real parquets -- DEFER verdict + >=95%% resolved.

Per-file run:
  python -m pytest tests/platformkit/test_asof_bullpen.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from domains.mlb.game_pk_bridge import (
    build_game_pk_bridge,
    resolve_event_id,
    GC_TO_PG_TEAM,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PG = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_GC = _REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet"


def _synthetic():
    """Tiny corpus: clean game, doubleheader, unmatched pk, dialect-mismatch game."""
    # player_gamelogs: two rows per game_pk (one per team), pg dialect team codes.
    pg = pd.DataFrame({
        "game_pk": [1, 1, 2, 2, 3, 3, 4, 4],
        "date": pd.to_datetime(
            ["2026-04-01"] * 2 + ["2026-04-02"] * 2 + ["2026-04-03"] * 2 + ["2026-04-04"] * 2),
        "team": ["NYY", "BOS",       # game 1 -> clean unique match
                 "AZ", "SD",         # game 2 -> dialect mismatch (ARI/SDG in gc)
                 "LAD", "SF",        # game 3 -> doubleheader (two gc events) -> ambiguous
                 "CHC", "STL"],      # game 4 -> unmatched (no gc key)
    })
    # games_current: event_id + gc-dialect team codes + outcome columns (leaky).
    gc = pd.DataFrame({
        "event_id": ["2026-04-01-NYY-BOS-1",
                     "2026-04-02-AZ-SD-1",        # uses gc dialect ARI/SDG below
                     "2026-04-03-LAD-SF-1", "2026-04-03-LAD-SF-2"],
        "date": pd.to_datetime(
            ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-03"]),
        "home_team": ["NYY", "ARI", "LAD", "LAD"],
        "away_team": ["BOS", "SDG", "SFO", "SFO"],
        "home_runs": [5, 3, 4, 2],
        "away_runs": [3, 4, 1, 6],
        "target_home_win": [1, 0, 1, 0],
    })
    return pg, gc


def test_synthetic_golden_bridge():
    pg, gc = _synthetic()
    b = build_game_pk_bridge(pg, gc)
    # game 1: clean unique match
    assert b.mapping[1] == "2026-04-01-NYY-BOS-1"
    # game 2: dialect mismatch resolved (AZ/SD <-> ARI/SDG)
    assert b.mapping[2] == "2026-04-02-AZ-SD-1"
    # game 3: doubleheader -> ambiguous, never guessed
    assert 3 not in b.mapping
    # game 4: no gc key -> unmatched
    assert 4 not in b.mapping
    assert b.n_game_pks == 4
    assert b.n_resolved == 2
    assert b.n_ambiguous == 1
    assert b.n_unmatched == 1
    assert resolve_event_id(2, b) == "2026-04-02-AZ-SD-1"
    assert resolve_event_id(3, b) is None


def test_dialect_table_covers_known_mismatches():
    # The eight known divergent codes must all be present in the dialect map.
    for gc_code in ("ARI", "SDG", "TAM", "KAN", "SFO", "WAS", "OAK", "CUB"):
        assert gc_code in GC_TO_PG_TEAM


def test_leak_free_invariant_to_outcome_columns():
    """Bridge is game-identity only: dropping score/outcome columns must not change it."""
    pg, gc = _synthetic()
    full = build_game_pk_bridge(pg, gc)
    stripped = build_game_pk_bridge(
        pg, gc.drop(columns=["home_runs", "away_runs", "target_home_win"]))
    assert stripped.mapping == full.mapping


def test_no_mapping_to_nonexistent_event():
    pg, gc = _synthetic()
    b = build_game_pk_bridge(pg, gc)
    valid = set(gc["event_id"].astype(str))
    assert all(ev in valid for ev in b.mapping.values())


@pytest.mark.skipif(not (_PG.exists() and _GC.exists()),
                    reason="real MLB parquets absent (clean clone)")
def test_real_data_smoke_defer_and_coverage():
    from scripts.platformkit.proof_mlb.gate_test_bullpen import verify_join
    row = verify_join()
    # Honest DEFER for the un-buildable bullpen feature.
    assert row["verdict"] == "DEFER"
    assert row["passed_expected"] is True
    # The provable bridge resolves the large majority of game_pks.
    assert row["n_game_pks"] > 500
    assert row["resolved_frac"] >= 0.95
    # Ambiguous + unmatched are excluded, not mapped.
    assert row["n_resolved"] + row["n_ambiguous"] + row["n_unmatched"] == row["n_game_pks"]
