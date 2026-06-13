"""scripts.platformkit.atlas.hub_data — Static manifest tables for build_all.py.

Extracted to keep build_all.py ≤ 300 LOC while providing headroom for new features.
Imported by build_all; do NOT import build_all from here (would be circular).

Discipline: Py3.9, from __future__ import annotations, ≤ 300 LOC.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# PERSON-FREE discipline (the platform's binding invariant)
# ---------------------------------------------------------------------------
# The platform's contribution to the Obsidian graph must carry NO specific
# names or matchups — only person-free ARCHETYPE families (playstyles, style
# matchups, style trends, scheme transitions, home environment) plus the
# cross-sport meta/hub.  PERSON_FREE gates OFF the NAMED-entity generators
# (named team/player atlas → Teams, head-to-head → Matchups, named seasons →
# Seasons, named tournaments → Tournaments, per-entity Scouting).  This is a
# GATE, not a deletion: set PERSON_FREE = False to restore the full build.
PERSON_FREE: bool = True

# Logical keys for every generator build_all can run, partitioned by whether
# the notes they emit name specific entities (NAMED) or are archetype/meta
# families (PERSON_FREE).  Keys are stable identifiers used by the selection
# helper + tests; they are NOT module names.
#
# NAMED (person/entity-bearing) — gated OFF when PERSON_FREE is True:
#   "base_atlas"  → per-sport build_atlas → Teams/ (named teams/players)
#   "h2h"         → atlas_h2h → Matchups/ (named entity-vs-entity)
#   "tournaments" → atlas_tournaments → Tournaments/ (named tournaments)
#   "seasons"     → atlas_seasons → Seasons/ (named seasons)
#   "scouting"    → atlas_scouting → Scouting/ (per-named-entity reports, --full)
NAMED_GENERATORS: List[str] = [
    "base_atlas", "h2h", "tournaments", "seasons", "scouting",
]

# PERSON_FREE (archetype + environment) — ALWAYS run:
#   "playstyles"         → Playstyles/Archetypes (style clusters, no names)
#   "style_matchups"     → StyleMatchups/ (archetype-vs-archetype)
#   "style_trends"       → StyleTrends/ (archetype trends)
#   "scheme_transitions" → SchemeTransitions/ (soccer schemes)
#   "home_environment"   → HomeEnvironment/ (MLB park env)
#   "trends"             → Trends/ (NBA league trends, no names)
PERSON_FREE_GENERATORS: List[str] = [
    "playstyles", "style_matchups", "style_trends",
    "scheme_transitions", "home_environment", "trends",
]

# Map each EXTRA_GENS subdir → its logical generator key (so _build_extras can
# honor PERSON_FREE without hardcoding subdir strings in build_all).
EXTRA_SUBDIR_KEY: Dict[str, str] = {
    "StyleMatchups": "style_matchups",
    "StyleTrends": "style_trends",
    "SchemeTransitions": "scheme_transitions",
    "HomeEnvironment": "home_environment",
    "Trends": "trends",
    "Scouting": "scouting",
}


def selected_generators(person_free: bool) -> List[str]:
    """Pure helper: which generator keys run for the given person_free mode.

    person_free=True  → only PERSON_FREE_GENERATORS (named ones gated off).
    person_free=False → every generator (NAMED + PERSON_FREE), legacy build.

    Tested directly by tests/platform/test_atlas_person_free.py WITHOUT running
    any generation.  build_all imports this so the gate has a single source.
    """
    if person_free:
        return list(PERSON_FREE_GENERATORS)
    return list(NAMED_GENERATORS) + list(PERSON_FREE_GENERATORS)

# (sport_id, display_name, adapter_module, corpus_hint)
SPORT_MANIFEST: List[Tuple[str, str, str, str]] = [
    ("tennis_atp",     "Tennis",         "domains.tennis.atlas",               "data/domains/tennis"),
    ("soccer_fd",      "Soccer",         "domains.soccer.atlas",               "data/domains/soccer"),
    ("mlb_sbro",       "MLB",            "domains.mlb.atlas",                  "data/domains/mlb"),
    ("basketball_nba", "Basketball_NBA", "domains.basketball_nba.memory_atlas", "data"),
]

ALIASES: Dict[str, str] = {
    "tennis": "tennis_atp", "tennis_atp": "tennis_atp",
    "soccer": "soccer_fd",  "soccer_fd":  "soccer_fd",
    "mlb":    "mlb_sbro",   "mlb_sbro":   "mlb_sbro",
    "nba": "basketball_nba", "basketball": "basketball_nba",
    "basketball_nba": "basketball_nba", "all": "all",
}

# Per-sport extra generators (--full only): (domain, module_suffix, fn_name, subdir, corpus_kwarg)
# corpus_kwarg is the parameter name passed to the generator function.
# For kwarg NOT in ("corpus_dir", "data_dir"), _build_extras passes sport_out (the sport vault dir).
EXTRA_GENS: List[Tuple[str, str, str, str, str]] = [
    ("tennis",         "atlas_style_matchups",     "build_style_matchups",    "StyleMatchups",     "corpus_dir"),
    ("tennis",         "atlas_style_trends",        "build_style_trends",      "StyleTrends",       "corpus_dir"),
    ("tennis",         "atlas_scouting",            "build_scouting",          "Scouting",          "vault_tennis_dir"),
    ("soccer",         "atlas_style_matchups",     "build_style_matchups",    "StyleMatchups",     "corpus_dir"),
    ("soccer",         "atlas_style_trends",        "build_style_trends",      "StyleTrends",       "corpus_dir"),
    ("soccer",         "atlas_scheme_transitions",  "build_scheme_transitions","SchemeTransitions",  "corpus_dir"),
    ("soccer",         "atlas_scouting",            "build_scouting",          "Scouting",          "corpus_dir"),
    ("mlb",            "atlas_style_matchups",     "build_style_matchups",    "StyleMatchups",     "corpus_dir"),
    ("mlb",            "atlas_style_trends",        "build_style_trends",      "StyleTrends",       "corpus_dir"),
    ("mlb",            "atlas_home_environment",    "build_home_environment",  "HomeEnvironment",   "corpus_dir"),
    ("mlb",            "atlas_scouting",            "build_scouting",          "Scouting",          "corpus_dir"),
    ("basketball_nba", "memory_atlas_trends",       "build_trends",            "Trends",            "data_dir"),
    # BUG FIX: was ("basketball_nba", "atlas_scouting", ..., "corpus_dir") — module did not exist.
    # Real module is memory_atlas_scouting; kwarg is vault_nba_dir (receives sport_out).
    ("basketball_nba", "memory_atlas_scouting",     "build_scouting",          "Scouting",          "vault_nba_dir"),
]

# Cross-sport META generators (--full, run after all sports): (module_suffix, fn_name)
META_GENS: List[Tuple[str, str]] = [
    ("graph_report", "build_graph_report"), ("signals_hub", "build_signals_hub"),
    ("archetype_taxonomy", "build_taxonomy"), ("intelligence_overview", "build_intelligence_overview"),
    ("graph_health", "build_graph_health"), ("world_model", "build_world_model"),
    ("base_rates", "build_base_rates"), ("calibration_segments", "build_calibration_segments"),
]

# The 8 cross-sport meta-notes that backlink to [[_Hub]].
# Listed here so write_hub() can add a "## Meta-Graph Notes" section.
META_NOTE_LINKS: List[str] = [
    "_World_Model", "_Intelligence_Overview", "_Archetype_Taxonomy",
    "_Signals_Hub", "_Base_Rates", "_Calibration_Segments", "_GraphStats", "_Graph_Health",
]

# --with-catalogs: (loader_mod, cat_mod, joint_mod, joint_fn, seasons, display, corpus_hint)
# joint_fn: tennis/soccer="run_joint_catalog"; mlb joint module uses "run_catalog".
CAT: List[Tuple[str, str, str, str, List[int], str, str]] = [  # noqa: E501
    ("scripts.platformkit.proof_tennis.run_proof", "domains.tennis.signal_catalog", "domains.tennis.signal_catalog_joint", "run_joint_catalog", list(range(2015, 2027)), "Tennis", "data/domains/tennis"),  # noqa: E501
    ("scripts.platformkit.proof_soccer.run_proof", "domains.soccer.signal_catalog", "domains.soccer.signal_catalog_joint", "run_joint_catalog", list(range(2015, 2026)), "Soccer", "data/domains/soccer"),  # noqa: E501
    ("scripts.platformkit.proof_mlb.run_proof", "domains.mlb.signal_catalog", "domains.mlb.signal_catalog_joint", "run_catalog", list(range(2010, 2022)), "MLB", "data/domains/mlb"),  # noqa: E501
]
