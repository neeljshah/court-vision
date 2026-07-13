"""scripts.platformkit.interaction_factory.builders_statcast_batquality -- B2:
MLB BATTED-BALL QUALITY builders (mlb_batquality_self_cross, mlb_batquality_
state_conditioner templates), split out per the builders_statcast_fatigue.py /
builders_carryover.py convention (keeps runner.py under its LOC budget). Same
contract as any other runner builder: `builder(attrs, tpl) -> {"frame",
"cluster", "corpus", "kind", ...} | None` -- registered into runner._BUILDERS
by runner.py itself.

SOURCES: same 2 files as builders_statcast_fatigue.py (statcast_fuller__2022/
__2023.parquet, the only 2 files in that name family, confirmed via ls) --
REUSES that module's `_STATCAST_SOURCES` path/exists-check (imported, not
duplicated). Column needs differ (launch_speed instead of release_speed/spin),
so this module reads its own column subset rather than calling _fatigue.
read_combined_source. `launch_angle` is ABSENT from BOTH files on disk
(confirmed via a schema-only pyarrow.parquet.ParquetFile peek, no full read)
-- same honest optional-column pattern _fatigue uses for release_extension:
every attr that needs launch_angle (barrel_rate, la_sweetspot) is computed
via the real formula (unit-tested on a synthetic fixture that DOES carry
launch_angle) but is honestly NaN on the real corpus until a source with that
column exists. Never invented.

BARREL DEFINITION (stated, since no `barrel` column exists on this corpus):
a SIMPLIFIED single-band proxy -- launch_speed >= 98 mph AND launch_angle in
[26, 30] degrees -- the narrowest, highest-confidence slice of the real
Statcast barrel matrix (which widens the LA band as EV climbs above 98); NOT
the full matrix. SWEET-SPOT is the real, official Statcast definition:
launch_angle in [8, 32] regardless of EV.

ATTRS (1 static pool, "mlb_batquality_prior", 8 names -- 4 metrics x 2
windows, generator.STATIC_POOLS key, same seam as mlb_sp_ingame_fatigue_state/
mlb_sp_fatigue_prior): batter_ev_mean_asof, batter_barrel_rate_asof, batter_
la_sweetspot_asof (batter-side, from the batter's own batted balls) and
pitcher_ev_allowed_asof (pitcher-side, from batted balls against them) --
each with a _30d suffix (last-30-days, closed='left' time-rolling, TODAY
excluded) and a _season suffix (season-to-date, cumsum().shift(1) per entity
ordered by game_date -- build_mlb_fatigue_prior_frame's own idiom, reused).
MIN_PRIOR_N=10 prior batted balls required before a rate/mean is served (own
design choice, no task-declared value, never invented from a handful of BIP).

LEAK RULE (binding): a game's own asof__ row uses ONLY strictly-prior games
(season: cumsum().shift(1); 30d: rolling('30D', closed='left'), which by
pandas definition excludes the row's own timestamp) -- see
test_builders_statcast_batquality.py's game-level trap tests.

TWO TEMPLATES:
 * mlb_batquality_self_cross: atomic_unit "plate_appearance" -- self-crosses
   all 8 pool names (batter x batter, batter x pitcher, pitcher x pitcher
   pairs all legal, same flat-pool shape as nba_shot_offense_x_offense) to
   predict THIS PA's own realized launch_speed on contact (real, not asof;
   PAs with no batted ball honestly drop, same "checkpoint never reached"
   idiom as builders_statcast_fatigue).
 * mlb_batquality_state_conditioner: the nba_state_conditioner / mlb_sp_
   fatigue_state_conditioner pattern -- crosses a PRIOR (this pool, narrowed
   via pool_spec `exclude` to JUST the 2 pitcher_ev_allowed_asof windows --
   the only subset of this pool that shares this template's atomic_unit,
   pitcher_appearance_checkpoint, with no batter to key on) against the
   REALIZED mlb_sp_ingame_fatigue_state pool from bc395262 -- the single
   MLB "realized in-game state" pool that exists in generator.py today (the
   semantically-correct choice: mlb_pa_attr_x_count_state's right_pool,
   discipline_by_count/mix_by_leverage, is a plate_appearance-level count
   state with an unregistered builder, a different atomic_unit than the
   checkpoint frame this template reuses) -- predicting rest_of_appearance_
   xwoba (build_mlb_fatigue_checkpoint_frame, imported and reused verbatim,
   never duplicated).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_statcast_batquality.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.interaction_factory import builders_statcast_fatigue as _fatigue

_STATCAST_SOURCES = _fatigue._STATCAST_SOURCES
_BATQ_CORPUS = "statcast_fuller_batquality"

MIN_PRIOR_N = 10   # own design choice: min prior batted balls before a rate/mean is served

BARREL_EV_MIN = 98.0     # simplified single-band proxy -- see module docstring
BARREL_LA_MIN = 26.0
BARREL_LA_MAX = 30.0
SWEETSPOT_LA_MIN = 8.0    # real, official Statcast Sweet-Spot% band
SWEETSPOT_LA_MAX = 32.0

_NEEDED_COLS = ["game_pk", "game_date", "at_bat_number", "pitcher", "batter", "launch_speed"]
_OPTIONAL_COLS = ["launch_angle"]   # absent from statcast_fuller__2022/2023 -- honest NaN stand-in, never invented


def _read_one(path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    cols = [c for c in _NEEDED_COLS if c in df.columns] + [c for c in _OPTIONAL_COLS if c in df.columns]
    return df[cols]


def read_combined_source(sources=_STATCAST_SOURCES) -> pd.DataFrame:
    """Concat statcast_fuller__2022 + __2023, this module's own column subset
    (launch_speed/launch_angle) -- reuses _fatigue's source paths, not its
    column list (that module never reads launch_speed)."""
    return pd.concat([_read_one(p) for p in sources], ignore_index=True)


def is_barrel(launch_speed: pd.Series, launch_angle: pd.Series) -> pd.Series:
    """Simplified single-band barrel proxy (EV>=98 & LA in [26,30]) -- NaN
    when either input is missing, honest, never invented."""
    valid = launch_speed.notna() & launch_angle.notna()
    barrel = (launch_speed >= BARREL_EV_MIN) & (launch_angle >= BARREL_LA_MIN) & (launch_angle <= BARREL_LA_MAX)
    return barrel.where(valid)


def is_sweetspot(launch_angle: pd.Series) -> pd.Series:
    """Real Statcast Sweet-Spot% definition: LA in [8,32]. NaN when LA missing."""
    valid = launch_angle.notna()
    sweet = (launch_angle >= SWEETSPOT_LA_MIN) & (launch_angle <= SWEETSPOT_LA_MAX)
    return sweet.where(valid)


def _prep_bip(pitch_df: pd.DataFrame) -> pd.DataFrame:
    """Rows that are a batted ball (launch_speed present), + the 2 quality
    indicators + a parsed game_date."""
    d = pitch_df.loc[pitch_df["launch_speed"].notna()].copy()
    if "launch_angle" not in d.columns:
        d["launch_angle"] = float("nan")
    d["_is_barrel"] = is_barrel(d["launch_speed"], d["launch_angle"])
    d["_is_sweet"] = is_sweetspot(d["launch_angle"])
    d["game_date"] = pd.to_datetime(d["game_date"])
    return d


def _entity_game_agg(bip: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """One row per (entity, game_pk, game_date): sum/n for ev, barrel, sweet."""
    g = bip.groupby([entity_col, "game_pk", "game_date"], sort=False).agg(
        sum_ev=("launch_speed", "sum"), n_ev=("launch_speed", "count"),
        sum_barrel=("_is_barrel", "sum"), n_barrel=("_is_barrel", "count"),
        sum_sweet=("_is_sweet", "sum"), n_sweet=("_is_sweet", "count"),
    ).reset_index()
    return g.sort_values([entity_col, "game_date", "game_pk"]).reset_index(drop=True)


def _asof_metric(game_agg: pd.DataFrame, entity_col: str, sum_col: str, n_col: str,
                  out_prefix: str, min_n: int = MIN_PRIOR_N) -> pd.DataFrame:
    """season-to-date (cumsum().shift(1)) + last-30-days (rolling('30D',
    closed='left')) STRICTLY-PRIOR rate for one (sum_col, n_col) pair, keyed
    (entity_col, game_pk). `d` is sorted [entity_col, game_date, game_pk]
    before either window is computed, so groupby(entity_col, sort=False)'s
    first-encountered group order == d's own contiguous row order -- the
    30d rolling parts (computed per group, concatenated in that same order)
    realign onto d without an explicit merge key."""
    d = game_agg.sort_values([entity_col, "game_date", "game_pk"]).reset_index(drop=True)
    grp = d.groupby(entity_col, sort=False)
    season_sum = grp[sum_col].transform(lambda s: s.cumsum().shift(1))
    season_n = grp[n_col].transform(lambda s: s.cumsum().shift(1))

    parts = []
    for _, g in d.groupby(entity_col, sort=False):
        gi = g.set_index("game_date")
        parts.append(pd.DataFrame({
            "_30d_sum": gi[sum_col].rolling("30D", closed="left").sum().to_numpy(),
            "_30d_n": gi[n_col].rolling("30D", closed="left").sum().to_numpy(),
        }))
    win = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["_30d_sum", "_30d_n"])

    d["asof__" + out_prefix + "_season"] = (season_sum / season_n.where(season_n >= min_n)).to_numpy()
    d["asof__" + out_prefix + "_30d"] = (win["_30d_sum"] / win["_30d_n"].where(win["_30d_n"] >= min_n)).to_numpy()
    return d[[entity_col, "game_pk", "asof__" + out_prefix + "_season", "asof__" + out_prefix + "_30d"]]


def build_batter_batquality_prior(bip: pd.DataFrame) -> pd.DataFrame:
    game = _entity_game_agg(bip, "batter")
    ev = _asof_metric(game, "batter", "sum_ev", "n_ev", "batter_ev_mean_asof")
    barrel = _asof_metric(game, "batter", "sum_barrel", "n_barrel", "batter_barrel_rate_asof")
    sweet = _asof_metric(game, "batter", "sum_sweet", "n_sweet", "batter_la_sweetspot_asof")
    return ev.merge(barrel, on=["batter", "game_pk"]).merge(sweet, on=["batter", "game_pk"])


def build_pitcher_batquality_prior(bip: pd.DataFrame) -> pd.DataFrame:
    game = _entity_game_agg(bip, "pitcher")
    return _asof_metric(game, "pitcher", "sum_ev", "n_ev", "pitcher_ev_allowed_asof")


def build_mlb_batquality_pa_frame(pitch_df: pd.DataFrame, attrs: List[str]) -> pd.DataFrame:
    """Per-(game_pk, at_bat_number) frame: y = launch_speed of THIS PA's own
    batted ball (real, NaN/dropped if the PA had none -- never invented),
    asof__<attr> for whichever of the 8 pool attrs are requested, keyed onto
    the PA's batter and pitcher. cluster="batter" (kept as a plain column)."""
    bip = _prep_bip(pitch_df)
    batter_prior = build_batter_batquality_prior(bip)
    pitcher_prior = build_pitcher_batquality_prior(bip)

    pa = pitch_df.groupby(["game_pk", "at_bat_number"], sort=False).agg(
        batter=("batter", "first"), pitcher=("pitcher", "first"), y=("launch_speed", "last"),
    ).reset_index()
    pa = pa.merge(batter_prior, on=["batter", "game_pk"], how="left")
    pa = pa.merge(pitcher_prior, on=["pitcher", "game_pk"], how="left")

    keep = ["game_pk", "at_bat_number", "batter", "y"] + [
        "asof__" + a for a in attrs if ("asof__" + a) in pa.columns]
    return pa[keep] if len(keep) > 4 else pd.DataFrame(columns=["game_pk", "at_bat_number", "batter", "y"])


_CONDITIONER_STATE_EXCLUDE = ("pitcher_ev_allowed_asof_30d", "pitcher_ev_allowed_asof_season")


def _mlb_batquality_self_cross_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not all(p.exists() for p in _STATCAST_SOURCES):
        return None
    pitch_df = read_combined_source()
    frame = build_mlb_batquality_pa_frame(pitch_df, attrs)
    return {"frame": frame, "cluster": "batter", "corpus": _BATQ_CORPUS, "kind": "ols"}


def _mlb_batquality_state_conditioner_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Two separate scoped-column reads of the SAME 2 source files (this
    module's launch_speed/launch_angle subset for the prior, _fatigue's own
    release_speed/spin/xwoba subset for the checkpoint frame) -- neither
    module's column list carries what the other needs, so a single shared
    read would silently drop columns; parquet only materializes the columns
    actually requested, so the 2nd pass is cheap, not a full re-read."""
    if not all(p.exists() for p in _STATCAST_SOURCES):
        return None
    bip = _prep_bip(read_combined_source())
    pitcher_prior = build_pitcher_batquality_prior(bip)
    state_attrs = [a for a in attrs if a not in _CONDITIONER_STATE_EXCLUDE]
    ck = _fatigue.build_mlb_fatigue_checkpoint_frame(_fatigue.read_combined_source(), state_attrs)
    out = ck.merge(pitcher_prior, on=["game_pk", "pitcher"], how="left")
    return {"frame": out, "cluster": "pitcher", "corpus": _BATQ_CORPUS, "kind": "ols"}


__all__ = [
    "read_combined_source", "is_barrel", "is_sweetspot",
    "build_batter_batquality_prior", "build_pitcher_batquality_prior", "build_mlb_batquality_pa_frame",
    "_mlb_batquality_self_cross_builder", "_mlb_batquality_state_conditioner_builder",
    "MIN_PRIOR_N", "BARREL_EV_MIN", "BARREL_LA_MIN", "BARREL_LA_MAX", "SWEETSPOT_LA_MIN", "SWEETSPOT_LA_MAX",
]
