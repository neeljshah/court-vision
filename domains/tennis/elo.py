"""domains.tennis.elo — leak-free walk-forward Elo for tennis matches.

Replay a chronologically-sorted sequence of matches and emit per-match PRE-match
Elo ratings (the leak-free prediction features). Ratings are updated AFTER the
pre-match snapshot is recorded — so future results can never contaminate features.

Surface blending: overall + per-surface ratings.  Walkovers (W/O) are skipped
(no tennis played → no rating update).  Retirements receive a normal update.

PRIVATE: outputs are price-bearing or license-restricted when combined with odds;
``data/domains/tennis/`` is never tracked.  No src.* / kernel.* / domains.nba.*
imports (falsifier F5 compliance).

Sackmann data is CC BY-NC-SA — private research use only; nothing derived is published.

Implementation is split for LOC-discipline:
  elo_core.py        — constants, EloState, helpers, replay, prob
  elo_walkforward.py — walk_forward_elo, elo_state_asof, replay_with_snapshots

This file is the public entry point; all names are re-exported so that
``from domains.tennis.elo import <anything>`` continues to resolve for the
adapter, proof scripts, and tests.
"""
from __future__ import annotations

# Re-export everything from the two implementation modules so this file
# remains the single public surface for domains.tennis.elo.

from domains.tennis.elo_core import (  # noqa: F401
    BASE_RATING,
    EloState,
    K_EXPONENT,
    K_NUMERATOR,
    K_OFFSET,
    SURFACE_BLEND,
    _blended_diff,
    _expected,
    _is_walkover,
    _k,
    _sort_key,
    _sorted,
    prob,
    replay,
)

from domains.tennis.elo_walkforward import (  # noqa: F401
    elo_state_asof,
    replay_with_snapshots,
    walk_forward_elo,
)

__all__ = [
    # Constants
    "BASE_RATING",
    "K_NUMERATOR",
    "K_OFFSET",
    "K_EXPONENT",
    "SURFACE_BLEND",
    # Data structures
    "EloState",
    # Core primitives
    "_k",
    "_expected",
    "_blended_diff",
    "_is_walkover",
    "_sort_key",
    "_sorted",
    "replay",
    "prob",
    # Walk-forward layer
    "walk_forward_elo",
    "elo_state_asof",
    "replay_with_snapshots",
]
