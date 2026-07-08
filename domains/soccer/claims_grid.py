"""soccer (club-domain) claims-factory GRID -- pure DATA config (spec sec 1,
CLAIMS_FACTORY_SPEC_2026-07-06). Zero logic, zero branching, zero I/O; never
imports the factory or any scripts.platformkit module. Mirrors
domains/basketball_nba/claims_grid.py shape exactly.

NOTE ON DOMAIN IDENTITY: this grid reads data/domains/soccer/** (the CLUB
domain -- EPL/La Liga/Serie A/Bundesliga/Ligue 1/La Liga2 match_stats). This
is a DIFFERENT corpus from domains/soccer_intl (national-team results +
travel scouting) -- no overlap, no shared source file.

ONE family, rank-6 census entry (claims-scale lane): soccer_referee_card_
foul_profiles, entity_key=referee. Source is a DERIVED parquet, NOT the raw
match_stats.parquet -- see domains/soccer/ingest_referee_card_profiles.py's
own docstring for why (blank-referee placeholder rows + no year column on
the raw source, neither expressible as a pure-data grid filter). That prep
script must be run (or its output already on disk) before this grid is
generatable; claims_factory.generate_family raises a plain FileNotFoundError
(pd.read_parquet) if it is missing, same failure class as any other grid.

Formula grammar is safe_formula's AGGREGATE dialect (sum/mean/count/
count_distinct(col) + arithmetic) exactly as scripts/platformkit/intel_
validation/safe_formula.py defines it. `agg.num`/`agg.den` are the two
whitelisted aggregate-grammar expression strings the factory divides
(criteria.formula = f"({num})/({den})"); this module never builds that
string itself.

Floors (task brief: "referee >= 20 matches"): ONE uniform value (20) reused
for every window type (career / season(year) / split(division)) -- simpler
than NBA's career=2x-season convention and matches the task's stated floor
literally rather than inventing a different number per bucket.

HONEST RE-MEASUREMENT (real on-disk data via domains/soccer/
ingest_referee_card_profiles.py's build(), replaying the exact factory
floor+groupby logic, this session): 10,251 non-blank-referee rows / 130
distinct referees. career_to_date: 62/130 referees clear >=20 matches.
6 division splits: 85 (referee,div) cells clear >=20 (of 174 total cells).
12 year windows (2015-2026): 297 (referee,year) cells clear >=20 (of 605).
4 dims x these window-slots -> ~1,776 post-floor exploded claims (248 career
+ 340 division-split + 1,188 year-split), against a much larger pre-floor
cartesian ceiling -- thin relative to the ceiling because most of the 130
referees are foreign/lower-tier officials appearing in only a handful of
matches in this corpus; reported honestly, not padded.

CLI: none -- this module is imported, never run directly.
"""
from __future__ import annotations

_REFEREE_SRC = "data/domains/soccer/referee_card_foul_profiles.parquet"

_REFEREE_DIMS = [
    {"metric": "fouls_per_match", "agg": {"num": "sum(total_fouls)", "den": "count(event_id)"}},
    {"metric": "yellows_per_match", "agg": {"num": "sum(total_yellow)", "den": "count(event_id)"}},
    {"metric": "reds_per_match", "agg": {"num": "sum(total_red)", "den": "count(event_id)"}},
    {"metric": "cards_per_match", "agg": {"num": "sum(total_cards)", "den": "count(event_id)"}},
]

_CAREER_AND_YEAR_WINDOWS = [{"name": "career_to_date", "filter": {}}] + [
    {"name": f"year_{y}", "filter": {"year": y}} for y in range(2015, 2027)
]

_DIVISION_SPLITS = [
    {"name": div, "col": "div", "eq": div} for div in ("E0", "E1", "SP1", "I1", "F1", "D1")
]

GRID: dict = {
    "sport": "soccer",
    "families": [
        {
            "family": "soccer_referee_card_foul_profiles",
            "source": _REFEREE_SRC,
            "grain": "per_match",
            "entity_key": "referee",
            "entity_name_col": "referee",
            "dims": _REFEREE_DIMS,
            "windows": _CAREER_AND_YEAR_WINDOWS,
            "context_splits": _DIVISION_SPLITS,
            "floors": {
                "career": {"event_id": 20},
                "season": {"event_id": 20},
                "split": {"event_id": 20},
            },
        },
    ],
}
