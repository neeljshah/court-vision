"""src/prediction/live_matchup_seeder.py — thin re-export shim.

W-018 task file reference. The real implementation lives in
``src/data/live_matchup_seeder.py``. This module re-exports the two public
functions so the live_engine call-site can import from either path.

Public API (re-exported)
------------------------
    seed_matchups_from_series(snap, series_csv_path=None) -> snap
    override_matchups_from_live_game(snap, game_id=None, fetch_fn=None) -> snap
"""
from __future__ import annotations

from src.data.live_matchup_seeder import (  # noqa: F401
    seed_matchups_from_series,
    override_matchups_from_live_game,
)

__all__ = [
    "seed_matchups_from_series",
    "override_matchups_from_live_game",
]
