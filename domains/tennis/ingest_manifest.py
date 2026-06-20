"""domains.tennis.ingest_manifest -- Tennis corpus provenance contract.

Maps every tennis corpus to a leak_class + freshness SLA. Honesty anchor: the raw
match_stats serve/return box is POST-game (only known after the match); the as-of
features derived from it (asof_features / asof_hold / asof_return) are PRE-game by
construction (snapshot-before-update, scripts.platformkit.asof_common). matches /
wta_matches are the pregame schedule/elo spine; their winner column is the post-game
label, not a pregame feature.

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

TENNIS_MANIFEST = IngestManifest(
    sport="tennis",
    sources=(
        IngestSource("matches", LEAK_PRE_GAME, sla_minutes=1440,
                     description="ATP match spine + elo inputs; winner is the post-game label"),
        IngestSource("wta_matches", LEAK_PRE_GAME, sla_minutes=1440,
                     description="WTA match spine; winner is the post-game label"),
        IngestSource("odds", LEAK_PRE_GAME, sla_minutes=120,
                     description="player moneylines (Pinnacle/B365) for devig + CLV"),
        IngestSource("match_stats", LEAK_POST_GAME, sla_minutes=None,
                     description="serve/return box (post-game); SOURCE for as-of features"),
        IngestSource("asof_features", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of serve-stat diffs (snapshot-before-update)"),
        IngestSource("asof_hold", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of serve hold% per surface"),
        IngestSource("asof_return", LEAK_PRE_GAME, sla_minutes=None,
                     description="leak-free as-of return-game % per surface (M11 Phase 2)"),
        IngestSource("players", LEAK_REFERENCE, sla_minutes=None,
                     description="player id/name registry"),
        IngestSource("postmortem", LEAK_POST_GAME, sla_minutes=None,
                     description="settlement / grading artifact"),
    ),
)
