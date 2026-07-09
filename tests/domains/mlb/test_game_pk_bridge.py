"""Join-rate test for domains.mlb.game_pk_bridge (gap-ledger rank 7).

The game_pk<->event_id bridge is the ONLY provable join between player_gamelogs
(game_pk-keyed, current season) and games_current (event_id-keyed) -- a silent
join drop here corrupts any downstream in-game conditioning that needs both
corpora. This module had ZERO test coverage; this asserts the resolved-fraction
floor on the REAL on-disk corpus (never a synthetic stand-in for the join
itself -- see docs/research/test_coverage_fix_2026-07-11.md for the measured
baseline this floor is set against).

Per-file only: python -m pytest tests/domains/mlb/test_game_pk_bridge.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from domains.mlb.game_pk_bridge import (
    GC_TO_PG_TEAM,
    build_game_pk_bridge,
    resolve_event_id,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLAYER_GAMELOGS = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_GAMES_CURRENT = _REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet"

pytestmark = pytest.mark.skipif(
    not (_PLAYER_GAMELOGS.exists() and _GAMES_CURRENT.exists()),
    reason="data/domains/mlb/*.parquet is local-only (gitignored); "
           "skip the real-corpus join-rate check when absent.",
)

# Measured floor (2026-07-11): the real corpus resolves 94.8% (10369/10939) of
# 2-team game_pks to a unique games_current event_id; the rest are honestly
# EXCLUDED as doubleheader-ambiguous (~3.3%) or unmatched (~1.9%), never guessed.
# The floor sits a hair below the measured rate so ordinary corpus growth does
# not flake this test; a real regression (join logic or team-code dialect
# drift) would drop resolved_frac well below this band.
_MIN_RESOLVED_FRAC = 0.94


def test_real_corpus_join_rate_meets_floor():
    b = build_game_pk_bridge()
    assert b.n_game_pks > 0, "expected a non-empty 2-team game_pk corpus"
    assert b.resolved_frac >= _MIN_RESOLVED_FRAC, (
        "game_pk->event_id join rate regressed: %.4f < floor %.4f "
        "(resolved=%d ambiguous=%d unmatched=%d of %d)"
        % (b.resolved_frac, _MIN_RESOLVED_FRAC, b.n_resolved, b.n_ambiguous,
           b.n_unmatched, b.n_game_pks))
    # counts must partition exactly (never double-counted, never dropped silently).
    assert b.n_resolved + b.n_ambiguous + b.n_unmatched == b.n_game_pks
    # every mapped value is a real, non-empty event_id string.
    assert all(isinstance(v, str) and v for v in b.mapping.values())


def test_resolve_event_id_matches_the_built_mapping():
    b = build_game_pk_bridge()
    assert b.n_resolved > 0
    some_pk = next(iter(b.mapping))
    assert resolve_event_id(some_pk, b) == b.mapping[some_pk]
    # A game_pk never seen (or ambiguous/unmatched) resolves to None, never guessed.
    unseen_pk = max(b.mapping.keys()) + 10_000_000
    assert resolve_event_id(unseen_pk, b) is None


def test_team_dialect_map_is_the_documented_8_club_set():
    # GC_TO_PG_TEAM is the hand-derived games_current->player_gamelogs dialect
    # bridge (docstring: "Derived by diffing the two home_team value sets").
    # A silent shrink here would quietly re-break exactly the clubs it exists for.
    assert set(GC_TO_PG_TEAM.keys()) == {
        "ARI", "SDG", "TAM", "KAN", "SFO", "WAS", "OAK", "CUB",
    }
    assert len(set(GC_TO_PG_TEAM.values())) == 8  # 8 distinct pg-dialect codes


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q"]))
