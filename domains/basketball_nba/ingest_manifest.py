"""domains.basketball_nba.ingest_manifest -- NBA corpus provenance contract.

Maps every basketball_nba corpus (census file-stem) to a leak_class + freshness SLA.
The leak_class records when each corpus becomes known relative to tip, so a builder
can assert it only feeds PREGAME features from pre_game/reference sources.

Derived as-of corpora (asof_*) are leak-free BY CONSTRUCTION (snapshot-before-update,
see scripts.platformkit.asof_common) so they are pre_game even though they summarise
history. games.parquet is the pregame schedule/elo spine; its home_win column is the
POST-game training label, not a pregame feature.

ASCII only. No src/kernel/api imports.
"""
from __future__ import annotations

from scripts.platformkit.ingest_manifest_core import (
    LEAK_IN_GAME,
    LEAK_POST_GAME,
    LEAK_PRE_GAME,
    IngestManifest,
    IngestSource,
)

NBA_MANIFEST = IngestManifest(
    sport="basketball_nba",
    sources=(
        IngestSource("games", LEAK_PRE_GAME, sla_minutes=1440,
                     description="schedule + elo spine; home_win is the post-game label"),
        IngestSource("odds", LEAK_PRE_GAME, sla_minutes=120,
                     description="moneyline (close-ish) used for devig + CLV join"),
        IngestSource("asof_features", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of base features (snapshot-before-update)"),
        IngestSource("asof_box_extra", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of extended box-derived features"),
        IngestSource("asof_runvar", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of run-variance features"),
        IngestSource("linescores", LEAK_IN_GAME, sla_minutes=10,
                     description="per-quarter scoring; feeds in-game conditioning only"),
        IngestSource("player_boxscores", LEAK_POST_GAME, sla_minutes=None,
                     description="final player box; prop training labels"),
        IngestSource("espn_boxscores", LEAK_POST_GAME, sla_minutes=None,
                     description="final team box (ESPN)"),
        IngestSource("postmortem", LEAK_POST_GAME, sla_minutes=None,
                     description="settlement / grading artifact"),
    ),
)
