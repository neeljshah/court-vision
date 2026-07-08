"""cross_sport_market claims-factory GRID -- pure DATA config (spec sec 1,
CLAIMS_FACTORY_SPEC_2026-07-06). Census rank 8 (depth_imbalance_descriptors)
+ line-movement descriptor families, built from OUR OWN captured market
history (data/cache/line_history/, data/cache/depth_history/), never a
paid/third-party feed. Zero logic, zero I/O, ZERO import of the factory --
mirrors domains/soccer_intl/claims_grid.py's shape exactly.

Two families, TWO sources (both built this session by
scripts/platformkit/quant/line_dynamics_prep.py and
scripts/platformkit/quant/depth_imbalance_prep.py -- see those modules'
docstrings for the tidy-prep logic; this file only declares columns that
already exist on their output parquets):

(1) market_line_drift_descriptors
    source=data/domains/cross_sport_market/line_dynamics.parquet (3,187 rows,
    one row per game/market_type/side/book pre-close observation).
    entity_key=market_bucket (sport+"_"+market_type, e.g. "mlb_moneyline").
    Real coverage this session (count_distinct(obs_id) per bucket):
    mlb_{moneyline,spread,total}=1154/402/844, soccer_intl_{spread,total}=
    146/146, tennis_{moneyline,spread,total}=122/112/112, wnba_{moneyline,
    spread,total}=64/32/32 -- ALL clear the 30-floor. soccer_intl_moneyline=21
    does NOT clear it (floor gates that one bucket out of its own ranking,
    not the whole family -- exactly the spec's per-entity gate, not a
    blocker). kbo/nba/npb/soccer have ZERO rows in the 48h pre-close window
    this session (kbo/npb captures exist but commence_time is far-future/
    futures-shaped; nba is offseason; soccer's captured rows this session
    were all futures markets, ~48 days out) -- BLOCKED-on-premise for those
    sports, not silently dropped: see line_dynamics_prep.py's module
    docstring for the exact filter that produces this split.

    DROPPED this session: a "longshot bucket" family (rate at which a
    <15%-implied-prob quote drifts down vs up before close, per the task
    spec). Real count of is_longshot_start==True observations across ALL
    sports/buckets this session: 21 total (measured directly against
    line_dynamics_prep.py's build() output) -- below the 30-per-bucket floor
    in EVERY bucket, not close in any of them. This is the exact same
    "thin comps dying on floors is honest" outcome soccer_intl's grid
    documents for its dropped season_gte window: reported as BLOCKED, no
    family shipped, no floor lowered to manufacture a claim.

(2) cross_sport_market_depth_imbalance_descriptors
    source=data/domains/cross_sport_market/depth_imbalance.parquet (29,543
    rows, one row per Kalshi orderbook snapshot). entity_key=sport (6
    buckets: kbo=5805, mlb=6515, npb=3487, soccer_intl=5876, tennis=2045,
    wnba=5815 -- ALL clear the 30-floor by 2+ orders of magnitude). nba has
    zero captures this window (offseason, no active Kalshi NBA game markets).
    A finer "favorite vs underdog" ticker sub-bucket (mid-price >= 0.5) was
    tried and DROPPED this session -- verified on the real data that 100% of
    rows have mid-price < 0.5 (checked directly, zero exceptions), so it adds
    a column without adding any real partition; entity_key stays plain
    `sport` (ponytail: a split that doesn't split is not a split).

Formula grammar is safe_formula's AGGREGATE dialect (sum/mean/count/
count_distinct(col) + arithmetic), verified this session against a live
slice of both real parquets via evaluate_group_formula (see
test_claims_grid.py). `agg.num`/`agg.den` are the two whitelisted operand
strings the factory divides (criteria.formula = f"({num})/({den})"); this
module never builds that string itself.

Floor columns (`obs_id` on both sources) are row-unique WITHIN every entity
group BY CONSTRUCTION (each tidy-prep module builds obs_id as a concatenation
of the exact tuple that grain is de-duplicated on -- verified this session:
0 duplicate obs_id values on either output parquet), so
count_distinct(obs_id) never undercounts true row volume -- the same trap
soccer_intl's grid documents avoiding with match_row.

Floors (REQUIRED per window per spec sec 1; fail-closed if missing):
  - season (all_captures, the only window either family declares): min
    obs_id = 30 (task spec's stated floor: ">=30 obs per cell").
  NOTE: neither family declares a "career"-prefixed window or context_splits,
  so only the "season" floor type is ever looked up (`_window_type`,
  claims_factory.py:81-87).

CLI: none -- this module is imported, never run directly.
"""
from __future__ import annotations

_LINE_DYNAMICS = "data/domains/cross_sport_market/line_dynamics.parquet"
_DEPTH_IMBALANCE = "data/domains/cross_sport_market/depth_imbalance.parquet"

_LINE_DRIFT_DIMS = [
    {"metric": "drift_60m", "agg": {"num": "sum(drift_60m)", "den": "count(drift_60m)"}},
    {"metric": "drift_30m", "agg": {"num": "sum(drift_30m)", "den": "count(drift_30m)"}},
    {"metric": "drift_10m", "agg": {"num": "sum(drift_10m)", "den": "count(drift_10m)"}},
    {"metric": "reversal_rate", "agg": {"num": "sum(reversal_flag)", "den": "count(reversal_flag)"}},
]

_DEPTH_IMBALANCE_DIMS = [
    {"metric": "mean_imbalance", "agg": {"num": "sum(imbalance)", "den": "count(imbalance)"}},
    {"metric": "bid_heavy_rate", "agg": {"num": "sum(bid_heavy_flag)", "den": "count(bid_heavy_flag)"}},
]

_ALL_CAPTURES_WINDOW = [
    {"name": "all_captures", "filter": {}},
]

GRID: dict = {
    "sport": "cross_sport_market",
    "families": [
        {
            "family": "market_line_drift_descriptors",
            "source": _LINE_DYNAMICS,
            "grain": "per_game_per_market_per_side_per_book",
            "entity_key": "market_bucket",
            "entity_name_col": "market_bucket",
            "dims": _LINE_DRIFT_DIMS,
            "windows": _ALL_CAPTURES_WINDOW,
            "floors": {
                "season": {"obs_id": 30},
            },
        },
        {
            "family": "cross_sport_market_depth_imbalance_descriptors",
            "source": _DEPTH_IMBALANCE,
            "grain": "per_ticker_per_snapshot",
            "entity_key": "sport",
            "entity_name_col": "sport",
            "dims": _DEPTH_IMBALANCE_DIMS,
            "windows": _ALL_CAPTURES_WINDOW,
            "floors": {
                "season": {"obs_id": 30},
            },
        },
    ],
}
