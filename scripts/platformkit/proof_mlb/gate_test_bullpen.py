"""scripts.platformkit.proof_mlb.gate_test_bullpen -- TASK-4b join verification + honest DEFER.

The Task-4b bullpen ERA-proxy feature CANNOT be built as specified: its two
required inputs do not join.

  * Load (innings/earnedRuns) lives in player_gamelogs.parquet, keyed on game_pk,
    covering ONLY the current season (2026).
  * The documented STARTING-PITCHER identity source pitchers.parquet is keyed on
    event_id and covers 2010..2021 -- ZERO date overlap with player_gamelogs. So SP
    identity (needed to isolate NON-SP bullpen pitchers) is unavailable for the
    player_gamelogs era, and player_gamelogs row-order is NOT start order (only ~25%%
    of the time is the first pitcher row the game's max-innings pitcher).

This module therefore VERIFIES the one part that IS provable -- the game_pk -> event_id
bridge through games_current (domains.mlb.game_pk_bridge) -- and records an honest DEFER
for the bullpen ERA-proxy feature with the precise blocker. It NEVER fabricates an SP
split or a feature value. A DEFER is honest market-/data-coverage evidence, not failure.

Leak contract checked here: the bridge keys on (date, team-pair) only -- pure GAME
identity, no score/inning/outcome column -- so it cannot leak any in-game or future
information into a downstream as-of feature.

PURE pandas/numpy + domains.mlb.game_pk_bridge (read-only) + reject_ledger. ASCII only.
ACCURACY/COVERAGE ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from domains.mlb.game_pk_bridge import build_game_pk_bridge, BridgeResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLAYER_GAMELOGS = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_GAMES_CURRENT = _REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet"

# The bullpen feature this task proposed; recorded DEFER (not REJECT: revisitable once a
# game_pk-keyed SP-identity corpus exists for the player_gamelogs era).
BULLPEN_SIGNAL = "mlb_diff_bullpen_era_asof"
DEFER_REASON = (
    "DEFER: cannot build. SP identity source pitchers.parquet (2010-2021) is era-disjoint "
    "from player_gamelogs (2026); player_gamelogs has no SP/RP flag and its pitcher row "
    "order is not start order (first==max-IP only ~25pct). No provable non-SP split, so the "
    "bullpen ERA-proxy is not constructible without fabricating SP identity. The game_pk->"
    "event_id bridge IS provable (1002/1031 unambiguous via games_current) and is shipped."
)

_LEAKY_GC_COLS = ("home_runs", "away_runs", "target_home_win")  # must NOT key the bridge


def verify_join(
    player_gamelogs: Optional[pd.DataFrame] = None,
    games_current: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    """Run the provable game_pk->event_id bridge and assert it is leak-free.

    Returns a verdict dict (run_v3-shaped enough for reject_ledger.record_proof_verdicts):
    the bridge coverage plus the honest DEFER verdict for the bullpen feature.
    """
    pg = (player_gamelogs if isinstance(player_gamelogs, pd.DataFrame)
          else pd.read_parquet(str(_PLAYER_GAMELOGS)))
    gc = (games_current if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(str(_GAMES_CURRENT)))

    bridge: BridgeResult = build_game_pk_bridge(pg, gc)

    # Leak assertion 1: every mapped event_id is a real games_current event.
    valid_events = set(gc["event_id"].astype(str))
    bad = [e for e in bridge.mapping.values() if e not in valid_events]
    if bad:
        raise AssertionError(f"bridge produced {len(bad)} event_ids absent from games_current")

    # Leak assertion 2: bridge is GAME-IDENTITY only -- the resolver source code keys on
    # (date, team-pair) and never reads a score/outcome column. We re-confirm here that the
    # mapping is invariant to the leaky outcome columns by rebuilding with them dropped.
    gc_noscore = gc.drop(columns=[c for c in _LEAKY_GC_COLS if c in gc.columns])
    bridge2 = build_game_pk_bridge(pg, gc_noscore)
    if bridge2.mapping != bridge.mapping:
        raise AssertionError("bridge changed when outcome columns dropped -- not leak-free")

    return {
        "signal": BULLPEN_SIGNAL,
        "actual": "DEFER",
        "verdict": "DEFER",
        "reason": DEFER_REASON,
        "n_game_pks": bridge.n_game_pks,
        "n_resolved": bridge.n_resolved,
        "n_ambiguous": bridge.n_ambiguous,
        "n_unmatched": bridge.n_unmatched,
        "resolved_frac": round(bridge.resolved_frac, 4),
        "expected": "DEFER",
        "passed_expected": True,
    }


def run_gate_test(
    player_gamelogs: Optional[pd.DataFrame] = None,
    games_current: Optional[pd.DataFrame] = None,
) -> List[dict]:
    """Return the verdict rows (one DEFER row for the un-buildable bullpen feature)."""
    return [verify_join(player_gamelogs, games_current)]


def _summary_line(rows: List[dict]) -> str:
    r = rows[0]
    return (f"MLB bullpen ERA-proxy: DEFER (un-buildable -- SP source era-disjoint). "
            f"game_pk->event_id bridge PROVEN {r['n_resolved']}/{r['n_game_pks']} "
            f"({r['resolved_frac']:.1%}), {r['n_ambiguous']} doubleheader-ambiguous + "
            f"{r['n_unmatched']} unmatched correctly excluded. No edge claimed.")


def main() -> int:
    """CLI: verify the bridge, print the honest DEFER, record it in the reject ledger."""
    rows = run_gate_test()
    print("\nMLB Task-4b bullpen join verification (REAL corpus)")
    print("=" * 70)
    r = rows[0]
    print(f"  game_pks (2-team)       : {r['n_game_pks']}")
    print(f"  resolved (unambiguous)  : {r['n_resolved']} ({r['resolved_frac']:.1%})")
    print(f"  doubleheader-ambiguous  : {r['n_ambiguous']} (excluded, not guessed)")
    print(f"  unmatched               : {r['n_unmatched']} (excluded)")
    print(f"  bullpen feature verdict : {r['verdict']}")
    print("-" * 70)
    print(_summary_line(rows))
    try:
        from scripts.platformkit.reject_ledger import record_proof_verdicts
        record_proof_verdicts("mlb", rows, corpus="player_gamelogs+games_current",
                              source="signal_proof")
        print("(verdict recorded to reject ledger)")
    except Exception as exc:  # pragma: no cover - ledger is best-effort
        print(f"(ledger record skipped: {exc})")
    print("(DEFER = honest data-coverage evidence; no edge is ever claimed here.)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["BULLPEN_SIGNAL", "DEFER_REASON", "verify_join", "run_gate_test",
           "_summary_line", "main"]
