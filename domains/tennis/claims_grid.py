"""Tennis claims-factory GRID -- pure DATA config (spec sec 1, CLAIMS_FACTORY_SPEC_2026-07-06).

Zero logic, zero branching, zero I/O, ZERO import of the factory or any
scripts.platformkit module. This dict is read BY the factory; it never reads
anything itself. Every dim's source column is verified to exist on the real
on-disk parquet (test_claims_grid.py's drift guard); a phantom column here is
a review FAIL per the spec. Shape mirrors domains/basketball_nba/claims_grid.py
(committed b214ec36) exactly.

CLAIM-ID NAMESPACE: family prefixes here are "tennis_p1_match_context" and
"tennis_p2_match_context" -- neither collides with tennis_claims_v4.py's
shipped ids (all prefixed "tennis_surface_split_*", checked this session
against data/cache/intel_claims/tennis_claims_v4.jsonl: 9 claims, family
prefixes {tennis_surface_split_ace_rate_*, tennis_surface_split_first_serve_
in_pct_*, tennis_surface_split_double_fault_rate_*}). Overlapping METRICS
(e.g. a future ace_rate here) would be fine per the task brief; there is no
metric-name collision either since this grid's dims are rank/duration, not
serve stats (see SOURCING GAP below for why).

SOURCING GAP -- reported honestly, not papered over:
Every candidate real-data source was checked on disk this session:
  - match_stats.parquet (59,312 rows: 30,616 ATP + 28,696 WTA by event_id
    prefix) carries the actual serve/return dims (p1_ace_rate, p1_1st_in_pct,
    etc.) but has ONLY an `event_id` column -- NO p1_id/p2_id, NO surface,
    NO date. Declaring entity_key=p1_id or a surface/season window on this
    source would require a JOIN to matches.parquet for the id/surface/date
    columns, which the grid format forbids (spec sec 1: config is pure data,
    the factory does a single `pd.read_parquet(family["source"])` with no
    join step -- claims_factory.py:219-220).
  - asof_meta.parquet (30,616 rows, exact event_id match to matches.parquet)
    has p1_rank_points/p1_seed/p1_minutes_prior_asof etc. but likewise only
    `event_id` -- no id/surface/date column of its own. Same joinless-source
    constraint applies.
  - matches.parquet is the ONLY raw parquet that carries p1_id/p2_id AND
    surface AND date on the same row with zero join required. Its own numeric
    columns are thin: p1_rank/p2_rank (rank AT match time) and minutes (match-
    level, not per-side). These are the two real, joinless per-side dims this
    grid can build.
  - matches.parquet's `date` column is a python `date` object, not a discrete
    season/year label; the factory's window filter is exact-equality only
    (claims_factory.py `_slice_rows`: `out[out[col] == val]`, no range/date
    logic). There is no `season` column on this parquet, so per-season
    windows (unlike NBA's `season_2024_25` filter on a real `season` string
    column) are NOT expressible without adding a derived column, which the
    grid format forbids (pure data, no logic). Windows here are therefore
    `career_to_date` (empty filter) plus the 3 real `surface` values as
    context splits -- NOT per-season, honestly narrower than NBA's grid.

FACTORY LIMITATION (separate, orthogonal gap): claims_factory.py's
`_build_dim_claim` (line 123-124) explicitly raises FactoryError for any
list-valued entity_key ("pair-keyed entity_key not yet supported by
generate_family") -- confirmed this session by reading the factory core and
by the absence of any pair-key case in test_claims_factory.py. The pair-keyed
CONTRACT itself is real and shipped (claims_validator.py + test_claims_
validator_pairkey.py, used by the hand-built tennis_h2h_claims.py), but the
GRID/FACTORY path cannot run a pair-keyed family yet. This grid therefore
declares two SCALAR entity_key families -- one per player-side (p1_id,
p2_id) -- rather than a pair key, so it is actually generatable once
sanctioned, not silently dead-on-arrival.

TWO FAMILIES (p1-perspective, p2-perspective) instead of one home/away-style
split: unlike NBA's single is_home/is_away binary column crossed into one
family, tennis's asymmetry is baked into two DIFFERENT id columns (p1_id vs
p2_id) on the same row, so it must be two families, not one family with a
context_split. Each family only sees that player's OWN matches from THAT
column's perspective (a player who appears as p2 in a match contributes
nothing to the p1 family's count for that match, and vice versa) -- a real,
disclosed limitation of the raw wide layout, not a bug.

Floors reuse the shipping precedent conventions (grounding reads):
  - career min_matches=40   (2x a season-style floor, same convention as
                              basketball_nba/claims_grid.py's career=2x season)
  - surface split min_matches=15 (tennis_claims_v4.py's own MIN_N_MATCHES_ON_
                              SURFACE=30 is a full-career single-surface floor
                              on a DIFFERENT, richer persistence-layer source;
                              this grid's per-side matches.parquet slice is
                              roughly half the sample of that layer for the
                              same player [half their matches are the OTHER
                              side's column], so 15 is the proportionate
                              per-side floor, not a weakening of the same bar)

HONEST PRE/POST-FLOOR COUNTS (computed this session from the real on-disk
matches.parquet, replaying the exact factory floor+groupby logic):
  - tennis_p1_match_context: 917 distinct p1_id players seen; post-floor =
    1,312 claims (197 clear career floor>=40, 459 clear the 3 surface-split
    floors>=15 summed across Hard/Clay/Grass, x 2 dims); pre-floor cartesian
    ceiling = 917 entities x 4 window-slots x 2 dims = 7,336 (ratio 0.18).
  - tennis_p2_match_context: 1,129 distinct p2_id players seen; post-floor =
    1,346 claims (203 career + 470 surface-split-summed, x 2 dims); pre-floor
    ceiling = 1,129 x 4 x 2 = 9,032 (ratio 0.15).
  - TOTAL post-floor (both families) = 2,658 against a combined pre-floor
    ceiling of 16,368. This is an order of magnitude below the 10,000s-per-
    sport target the spec's sec 1 table estimated for tennis (~10-20k) --
    the gap is the SOURCING GAP above (only 2 real joinless dims survive vs
    the ~20 serve/return dims the spec's estimate assumed access to); the
    honest fix is a Phase-2 factory extension (join support or a materialized
    long-format snapshot) which is out of scope for a grid-only config.
    These counts are UNCHANGED by the FIX-ROUND NOTE below: floors gate on
    `event_id` count (a raw, never-null row count), which the denominator
    fix does not touch -- only per-claim VALUES were wrong, not which
    (entity, window) cells clear the floor.

FIX-ROUND NOTE (blocking findings from the first review, fixed by changing
the denominator, not by adding a floor -- both dims, both families):
  (1) minutes_per_match originally used agg={"num": "sum(minutes)", "den":
      "count(event_id)"}. safe_formula's sum() skips NaN but count(event_id)
      counts ALL rows (event_id is never null) -- so the metric was actually
      known_minutes / all_matches, silently deflated by each player's missing-
      minutes fraction, not mean minutes per PLAYED match. VERIFIED on the
      real parquet: minutes is NULL in 10.2% of rows (3,122/30,616), varying
      53.7% in 2015 down to 13.9% in 2025 (heavier historical gaps), so the
      deflation is uneven across players by career era. This reordered the
      career_to_date leaderboard: buggy formula ranked Ilya Ivashka #1 at
      123.93; the fixed formula (den=count(minutes), i.e. mean over played
      matches only) correctly ranks Thanasi Kokkinakis #1 at 138.28 (he was
      demoted to a deflated #2 at 123.72 under the bug) -- reproduced exactly
      this session by replaying both formulas over the real parquet.
  (2) rank_at_match had the identical denominator-mismatch class: sum(p1_rank
      or p2_rank)/count(event_id) where the rank column is NULL in 0.7% (p1)
      / 1.1% (p2) of rows. Smaller null fraction than minutes so not
      independently ship-blocking, but the same bug class -- fixed in the
      same pass for consistency.
  FIX: den changed from `count(event_id)` to `count(p1_rank)` / `count(p2_rank)`
  / `count(minutes)` (the column actually being summed) for all 4 dim entries
  across both families -- a one-token change per the review's own diagnosis.
  safe_formula.py:149-150 confirms `count(col)` calls `series.count()`
  (pandas non-null count), so numerator and denominator now agree on the
  same non-null row set. No floor, window, or count-of-claims logic changed;
  the HONEST PRE/POST-FLOOR COUNTS above remain exactly as measured (floors
  key off `event_id`, an orthogonal, never-null column).

RANK-9 CENSUS FAMILY ADDED (claims-scale lane): tennis_fatigue_schedule_
density, entity_key=player_id, source=data/domains/tennis/
schedule_density.parquet -- a DERIVED parquet (domains/tennis/
ingest_schedule_density.py), not matches.parquet directly, because rest-day
and rolling-match-count features need each player's FULL match history
melted from the wide p1_id/p2_id columns into one long per-player-appearance
table, plus temporal diff/rolling computation the pure-data grid format
cannot express (see that module's own docstring). Its `year` window (2015-
2025) is legitimate here because the prep script derives it from `date`,
same pattern as the mlb_bullpen_fatigue_chains family added above this
session.

HONEST RE-MEASUREMENT (real on-disk data via the prep script's build(),
replaying the exact factory floor+groupby logic, this session): 61,232
player-match rows / 1,273 distinct players. career_to_date: 287/1,273 clear
>=40 matches. 3 surface splits: 744 (player,surface) cells clear >=15 (of
2,483). 11 year windows (2015-2025): 1,274 (player,year) cells clear >=15
(of 4,568). 3 dims x these window-slots -> ~6,915 post-floor exploded claims
(861 career + 2,232 surface-split + 3,822 year-split).

CLI: none -- this module is imported, never run directly.
"""
from __future__ import annotations

_MATCHES = "data/domains/tennis/matches.parquet"
_SCHEDULE_DENSITY = "data/domains/tennis/schedule_density.parquet"

_SCHEDULE_DIMS = [
    {"metric": "rest_days_avg", "agg": {"num": "sum(rest_days)", "den": "count(rest_days)"}},
    {"metric": "matches_last_7d_avg", "agg": {"num": "sum(matches_last_7d)", "den": "count(matches_last_7d)"}},
    {"metric": "matches_last_14d_avg", "agg": {"num": "sum(matches_last_14d)", "den": "count(matches_last_14d)"}},
]

_SCHEDULE_CAREER_AND_YEAR_WINDOWS = [{"name": "career_to_date", "filter": {}}] + [
    {"name": f"year_{y}", "filter": {"year": y}} for y in range(2015, 2026)
]

_P1_DIMS = [
    {"metric": "rank_at_match", "agg": {"num": "sum(p1_rank)", "den": "count(p1_rank)"}},
    {"metric": "minutes_per_match", "agg": {"num": "sum(minutes)", "den": "count(minutes)"}},
]

_P2_DIMS = [
    {"metric": "rank_at_match", "agg": {"num": "sum(p2_rank)", "den": "count(p2_rank)"}},
    {"metric": "minutes_per_match", "agg": {"num": "sum(minutes)", "den": "count(minutes)"}},
]

_CAREER_WINDOW = [
    {"name": "career_to_date", "filter": {}},
]

_SURFACE_SPLITS = [
    {"name": "hard", "col": "surface", "eq": "Hard"},
    {"name": "clay", "col": "surface", "eq": "Clay"},
    {"name": "grass", "col": "surface", "eq": "Grass"},
]

GRID: dict = {
    "sport": "tennis",
    "families": [
        {
            "family": "tennis_p1_match_context",
            "source": _MATCHES,
            "grain": "per_match",
            "entity_key": "p1_id",
            "entity_name_col": "p1_name",
            "dims": _P1_DIMS,
            "windows": _CAREER_WINDOW,
            "context_splits": _SURFACE_SPLITS,
            "floors": {
                "career": {"event_id": 40},
                "split": {"event_id": 15},
            },
        },
        {
            "family": "tennis_p2_match_context",
            "source": _MATCHES,
            "grain": "per_match",
            "entity_key": "p2_id",
            "entity_name_col": "p2_name",
            "dims": _P2_DIMS,
            "windows": _CAREER_WINDOW,
            "context_splits": _SURFACE_SPLITS,
            "floors": {
                "career": {"event_id": 40},
                "split": {"event_id": 15},
            },
        },
        {
            "family": "tennis_fatigue_schedule_density",
            "source": _SCHEDULE_DENSITY,
            "grain": "per_player_match",
            "entity_key": "player_id",
            "entity_name_col": "player_name",
            "dims": _SCHEDULE_DIMS,
            "windows": _SCHEDULE_CAREER_AND_YEAR_WINDOWS,
            "context_splits": _SURFACE_SPLITS,
            "floors": {
                "career": {"event_id": 40},
                "season": {"event_id": 15},
                "split": {"event_id": 15},
            },
        },
    ],
}
