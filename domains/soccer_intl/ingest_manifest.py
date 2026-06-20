"""domains.soccer_intl.ingest_manifest -- international (national-team) soccer
corpus provenance contract.

Mirrors domains/soccer/ingest_manifest.py shape but for the INTERNATIONAL
(national-team) corpus, which is far thinner than the club domain: the ONLY
corpus that genuinely exists on disk is the martj42/international_results dump.

Maps every soccer_intl corpus (census file-stem) to a leak_class + freshness SLA.
The leak_class records when each corpus becomes known relative to kickoff, so a
builder can assert it only feeds PREGAME features from pre_game/reference sources.

HONEST SCOPE: domains/soccer declares 9 sources (odds, asof_*, ESPN priors,
postmortem, ...). soccer_intl has NONE of those on disk -- it carries a single
results corpus and derives its leak-free as-of lambdas IN MEMORY at predict time
(domains/soccer_intl/ratings.walk_forward_goals), not as a persisted asof_*
parquet. Declaring sources that do not exist would FAIL validate_against_inventory
and would be dishonest, so this manifest declares EXACTLY the one corpus present.

Corpus stems on disk (data/domains/soccer_intl/):
  results

``results`` carries date / home_team / away_team / home_score / away_score /
tournament / city / country / neutral. The pre-match goals rates and Poisson
lambdas are reconstructed strictly prior-only by chronological replay, so the
fields a PREGAME prediction reads (date, teams, neutral) are pre_game, while the
home_score/away_score columns are the POST-game training label, not features.
Because both the pregame spine and the post-game label live in the same single
file, the corpus's earliest-known leak_class is pre_game (it IS the schedule
spine); the post-game score columns are documented above, not split into a
separate stem that does not exist.

ASCII only. No src/kernel/api imports.
"""
from __future__ import annotations

from scripts.platformkit.ingest_manifest_core import (
    LEAK_PRE_GAME,
    IngestManifest,
    IngestSource,
)

SOCCER_INTL_MANIFEST = IngestManifest(
    sport="soccer_intl",
    sources=(
        IngestSource(
            "results",
            LEAK_PRE_GAME,
            sla_minutes=1440,
            description=(
                "martj42 international results spine (date/teams/neutral are the "
                "pregame schedule; home_score/away_score are the post-game label, "
                "NOT a pregame feature). As-of goals lambdas are replayed prior-only "
                "in memory (ratings.walk_forward_goals); no persisted asof_* parquet."
            ),
        ),
    ),
)
