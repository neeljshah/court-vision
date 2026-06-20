"""domains.nfl.ingest_manifest -- generated provenance contract (SCAFFOLD).

Edit the sources / leak_class / SLA to match the real nfl corpora.
"""
from __future__ import annotations

from scripts.platformkit.ingest_manifest_core import (
    LEAK_POST_GAME,
    LEAK_PRE_GAME,
    LEAK_REFERENCE,
    IngestManifest,
    IngestSource,
)

NFL_MANIFEST = IngestManifest(
    sport="nfl",
    sources=(
        IngestSource("games", LEAK_PRE_GAME, sla_minutes=1440, description="schedule spine; result is the post-game label"),
        IngestSource("odds", LEAK_PRE_GAME, sla_minutes=120, description="moneylines for devig + CLV"),
    ),
)
