"""domains.soccer_intl.config - constants for the national-team soccer adapter.

Mirrors domains/soccer/config.py shape but for INTERNATIONAL (national-team)
football sourced from the public martj42/international_results corpus.

Imports NOTHING from src.* / kernel.* / domains.nba / domains.tennis (falsifier
F5 compliance).  data/domains/soccer_intl/ is gitignored local-only.

Market targets (both emitted by the predictor, both read off ONE scoreline matrix):
  * 1X2 moneyline: P(home win) / P(draw) / P(away win)
  * O/U 2.5 goals: P(total goals >= 3)

NEUTRAL-SITE AWARENESS: most World Cup games are played at neutral venues, so the
home-field goal bump is applied ONLY when the match is NOT neutral.  The bump is
learned from the corpus (see ratings.fit_home_adv) rather than hard-coded.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Sport identity
# ---------------------------------------------------------------------------

SPORT_ID = "soccer_intl"   # national-team (international) soccer

# Binary stat the kernel gate would route to Brier scoring (O/U-2.5 over side).
# Same config-level reinterpretation used by domains/soccer (NOT a kernel edit).
STAT_REGISTRY: tuple[str, ...] = ("winprob",)

# ---------------------------------------------------------------------------
# Data source (public, free)
# ---------------------------------------------------------------------------

# martj42/international_results - CC0-ish public dataset of international results
# 1872-present.  Columns: date, home_team, away_team, home_score, away_score,
# tournament, city, country, neutral.
DATA_SOURCE_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)

DATA_DIR_REL = "data/domains/soccer_intl"
RESULTS_PARQUET = f"{DATA_DIR_REL}/results.parquet"
RAW_CSV_REL = f"{DATA_DIR_REL}/_raw/results.csv"

# ---------------------------------------------------------------------------
# Entity schema (national teams)
# ---------------------------------------------------------------------------

ENTITY_SCHEMA = {
    "entity_type": "team",
    "team": True,
    "id_field": "team_name",
    "id_dtype": str,
}

OVER_SIDE = "O2.5"
UNDER_SIDE = "U2.5"

# ---------------------------------------------------------------------------
# Ratings + walk-forward constants
# ---------------------------------------------------------------------------

# International scoring is LOWER and matches are FAR sparser per team than club
# leagues, so the EW update is slower (longer memory) and the prior is lower.
ALPHA = 0.06            # EW update rate for goals-for / goals-against per match
PRIOR_GF = 1.25         # prior goals-for rate for an unseen / sparse team
PRIOR_GA = 1.25         # prior goals-against rate for an unseen / sparse team
RATE_CLIP = (0.2, 4.0)  # clip team rates before forming the Poisson lambda
OU_LINE = 2.5           # over/under goal line
MIN_MATCHES = 8         # min prior international matches before a team is "seen"

# Home-field advantage is fit from the corpus (ratings.fit_home_adv) on NON-neutral
# matches only.  This fallback is used if the fit cannot run (empty corpus).
HOME_ADV_GOALS_FALLBACK = 0.30   # extra home lambda multiplier base (mult = 1+adv)

# Recent-decades emphasis: pre-cutoff matches before this year are dropped from
# rating replay (older football is a different game and dilutes current strength).
MIN_SEASON_YEAR = 1990
