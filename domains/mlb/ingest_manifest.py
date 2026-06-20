"""domains.mlb.ingest_manifest -- MLB corpus provenance contract.

Maps every mlb corpus (census file-stem) to a leak_class + freshness SLA.
The leak_class records when each corpus becomes known relative to first pitch,
so a builder can assert it only feeds PREGAME features from pre_game/reference
sources.

Derived as-of corpora (asof_*) are leak-free BY CONSTRUCTION (snapshot-before-
update, see scripts.platformkit.asof_common) so they are pre_game even though
they summarise history. games.parquet is the pregame schedule/elo spine; its
target_home_win column is the POST-game training label, not a pregame feature.

Corpus stems on disk (data/domains/mlb/):
  games, games_current, odds, pitchers, asof_features, asof_park,
  player_gamelogs, espn_boxscores, postmortem

ASCII only. No src/kernel/api imports.
"""
from __future__ import annotations

from scripts.platformkit.ingest_manifest_core import (
    LEAK_IN_GAME,
    LEAK_POST_GAME,
    LEAK_PRE_GAME,
    LEAK_REFERENCE,
    IngestManifest,
    IngestSource,
)

MLB_MANIFEST = IngestManifest(
    sport="mlb",
    sources=(
        IngestSource("games", LEAK_PRE_GAME, sla_minutes=1440,
                     description="schedule + elo spine; target_home_win is the post-game label"),
        IngestSource("odds", LEAK_PRE_GAME, sla_minutes=120,
                     description="moneyline (open/close) used for devig + CLV join"),
        IngestSource("pitchers", LEAK_PRE_GAME, sla_minutes=240,
                     description="starting pitcher assignments (pregame scratch available)"),
        IngestSource("asof_features", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of SP ERA/RA features (snapshot-before-update)"),
        IngestSource("asof_park", LEAK_REFERENCE, sla_minutes=None,
                     description="historical park factor (updated end-of-season; reference)"),
        IngestSource("games_current", LEAK_PRE_GAME, sla_minutes=1440,
                     description="current-season schedule refresh (ESPN feed)"),
        IngestSource("player_gamelogs", LEAK_POST_GAME, sla_minutes=None,
                     description="per-player per-game box (post-game); prop training labels"),
        IngestSource("espn_boxscores", LEAK_POST_GAME, sla_minutes=None,
                     description="final team box (ESPN)"),
        IngestSource("postmortem", LEAK_POST_GAME, sla_minutes=None,
                     description="settlement / grading artifact (inning-level breakdown)"),
    ),
)
