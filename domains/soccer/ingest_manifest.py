"""domains.soccer.ingest_manifest -- soccer (club O/U) corpus provenance contract.

Maps every soccer corpus (census file-stem) to a leak_class + freshness SLA.
The leak_class records when each corpus becomes known relative to kickoff, so a
builder can assert it only feeds PREGAME features from pre_game/reference sources.

Derived as-of corpora (asof_*) are leak-free BY CONSTRUCTION (snapshot-before-
update, see scripts.platformkit.asof_common) so they are pre_game even though
they summarise history. matches.parquet is the pregame schedule/ratings spine;
its target_over25 column is the POST-game training label, not a pregame feature.

Corpus stems on disk (data/domains/soccer/):
  matches, odds, match_stats, asof_features, asof_xg_proxy,
  espn_matchstats, espn_player_stats, espn_club_priors, postmortem

ASCII only. No src/kernel/api imports.
"""
from __future__ import annotations

from scripts.platformkit.ingest_manifest_core import (
    LEAK_POST_GAME,
    LEAK_PRE_GAME,
    LEAK_REFERENCE,
    IngestManifest,
    IngestSource,
)

SOCCER_MANIFEST = IngestManifest(
    sport="soccer",
    sources=(
        IngestSource("matches", LEAK_PRE_GAME, sla_minutes=1440,
                     description="schedule + Poisson-goals spine; target_over25 is post-game label"),
        IngestSource("odds", LEAK_PRE_GAME, sla_minutes=120,
                     description="O/U 2.5 prematch+close prices for devig + CLV join"),
        IngestSource("asof_features", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of shots/SoT features (snapshot-before-update)"),
        IngestSource("asof_xg_proxy", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of expected-goals proxy (snapshot-before-update)"),
        IngestSource("match_stats", LEAK_POST_GAME, sla_minutes=None,
                     description="full post-game match stats; SOURCE for as-of features"),
        IngestSource("espn_club_priors", LEAK_REFERENCE, sla_minutes=None,
                     description="ESPN club-level player priors (season-aggregate reference)"),
        IngestSource("espn_matchstats", LEAK_POST_GAME, sla_minutes=None,
                     description="ESPN match-level score + venue (post-game settlement)"),
        IngestSource("espn_player_stats", LEAK_POST_GAME, sla_minutes=None,
                     description="ESPN per-player match stats (post-game; prop labels)"),
        IngestSource("postmortem", LEAK_POST_GAME, sla_minutes=None,
                     description="settlement / grading artifact"),
    ),
)
