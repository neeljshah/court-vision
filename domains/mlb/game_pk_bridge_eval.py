"""domains.mlb.game_pk_bridge_eval -- coverage readout for the game_pk<->event_id bridge.

There is no bullpen feature to score (Task-4b DEFERRED -- see asof_bullpen_DEFER.md), so the
honest readout for the PROVABLE artifact is the bridge's COVERAGE against the real corpus:
what fraction of player_gamelogs game_pks resolve to a unique games_current event_id, and
how many are correctly excluded as doubleheader-ambiguous or unmatched. This is a
COVERAGE/ACCURACY readout, not an edge readout -- no $/ROI is computed or claimed.

Usage:
  python -m domains.mlb.game_pk_bridge_eval
"""
from __future__ import annotations

from domains.mlb.game_pk_bridge import build_game_pk_bridge


def main() -> int:
    b = build_game_pk_bridge()
    print("MLB game_pk -> event_id bridge coverage (real corpus)")
    print("=" * 56)
    print(f"  game_pks (2-team)      : {b.n_game_pks}")
    print(f"  resolved (unique)      : {b.n_resolved} ({b.resolved_frac:.1%})")
    print(f"  doubleheader-ambiguous : {b.n_ambiguous} (excluded)")
    print(f"  unmatched              : {b.n_unmatched} (excluded)")
    print("-" * 56)
    print("COVERAGE readout only -- no market edge claimed; bullpen feature DEFERRED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
