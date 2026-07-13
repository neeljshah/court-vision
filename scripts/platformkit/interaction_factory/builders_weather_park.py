"""scripts.platformkit.interaction_factory.builders_weather_park -- B4: MLB
WEATHER x PARK as-of attrs (mlb_weather_park_self_cross template, plus a
same-grain cross against the B3 umpire pool), split out per the builders_
umpire.py / builders_carryover.py convention (keeps runner.py under its LOC
budget). Same contract as any other runner builder: `builder(attrs, tpl) ->
{"frame", "cluster", "corpus", "kind", ...} | None` -- registered into
runner._BUILDERS by runner.py itself.

STEP0 PREMISE (what exists on disk, checked live this session, 2026-07-13):
 * data/domains/mlb/probables.parquet (11316 rows, game_pk-keyed, no dup
   game_pk) already carries weather_condition, temp_f, wind (raw string) AND
   venue -- the same table domains.mlb.weather_totals_gate.build_weather_
   corpus() already joins to games_current for a leak-free (date, game_pk,
   temp_f, wind_speed, wind_out, wind_in, total_runs) frame (10369 rows,
   weather_totals_verdict.json verdict SHIP_REVIEW vs OUR OWN no-weather
   baseline -- sharpness only, no market/$ claim, see that module).
 * NO park-orientation / park-factor file exists anywhere on disk (checked:
   no *park_factor*, *orientation*, *azimuth*, *park_dir* file under data/ or
   domains/ or scripts/platformkit/ for MLB). wind_out_component is therefore
   built as RAW wind-out speed (mph), honestly named wind_out_mph_raw --
   NOT direction-adjusted for park orientation, because that data does not
   exist. Upgrade path: if a park-orientation file ever lands, replace this
   attr's body with a real relative-to-orientation component; the column name
   should change too (this one is deliberately NOT called "_component" to
   avoid implying vector math that isn't happening).
 * probables' venue joined onto build_weather_corpus()'s own frame (merge
   verified live: 10369/10369 weather rows, only 1 unmatched venue) gives 42
   distinct venues -- plenty for a venue-clustered as-of stat (MIN_CLUSTERS=5).
 * domains.mlb.umpire_totals_gate.build_umpire_totals_corpus() (B3's corpus,
   4861 rows, game_pk-keyed) overlaps the weather corpus on 4637 game_pks
   (verified live merge) -- a clean same-grain ("game", outcome total_runs)
   cross exists, so mlb_weather_park_umpire_cross IS registered below (not
   self-cross-only).

REUSE (not copy):
 * build_weather_park_corpus() calls domains.mlb.weather_totals_gate.build_
   weather_corpus() verbatim for the weather join + game_pk_bridge logic, and
   only ADDS venue via a plain left-merge on probables (game_pk has no dups,
   so this cannot fan out rows).
 * The cross builder imports build_umpire_game_frame + _UMPIRE_SOURCES
   straight from builders_umpire.py (B3) -- no umpire join logic duplicated.

EXOGENOUS-WEATHER LEAK NUANCE (binding, read before touching wind/temp code):
today's own weather (temp_f, wind) is NOT a downstream outcome of today's
game -- it is exogenous and pregame-KNOWABLE (a forecast/actual reading taken
before or at first pitch), unlike total_runs which the game itself produces.
So wind_out_mph_raw uses TODAY's own weather value with NO as-of shift. Only
the two park-NORM BASELINES (temp_above_park_norm_asof, park_runs_factor_
asof) are strictly-prior expanding stats -- same per-group cumsum().shift(1)
idiom builders_umpire.py's league/umpire means use, keyed by venue instead of
hp_umpire_id. See test_exogenous_weather_no_shift_but_park_norm_is_prior.

ATTRS (STATIC_POOLS key "mlb_weather_park_asof", atomic_unit "game"):
 * wind_out_mph_raw = today's raw wind-out speed (mph), 0.0 if not blowing
   out / unknown direction (same parse_wind() vocabulary weather_totals_gate
   uses) -- NOT as-of, see nuance above.
 * temp_above_park_norm_asof = today's temp_f minus THIS park's (venue)
   STRICTLY-PRIOR expanding mean temp_f, floored at MIN_PARK_PRIOR prior
   non-null readings at that venue.
 * park_runs_factor_asof = this park's STRICTLY-PRIOR expanding mean total_
   runs MINUS the STRICTLY-PRIOR expanding LEAGUE-WIDE mean total_runs
   (demeaned, same "vs league mean" framing ump_total_runs_tendency_asof
   uses), floored at MIN_PARK_PRIOR prior games at that venue.

OUTCOME: y = total_runs (this game's own REAL total, not as-of).

LEAK RULE (binding): a game's own park-norm asof value uses ONLY games
strictly before it in (date, game_pk) chronological order at that venue (or
league-wide) -- both cumsums are shift(1)'d before dividing. wind_out_mph_raw
is the one deliberate exception (see nuance above); see test_builders_
weather_park.py's tamper-today's-own-outcome trap test for the 2 park-norm
attrs specifically (wind is excluded from that trap by design).

CROSS: mlb_weather_park_umpire_cross pairs this pool against B3's mlb_
umpire_asof pool (both "game"-grain, both outcome total_runs) -- structurally
the same left_pool/right_pool "cross" pairing shape mlb_sp_fatigue_state_
conditioner/mlb_batquality_state_conditioner use, though semantically this is
context x context (weather/park x umpire), not prior x realized-in-game-
state -- documented honestly rather than borrowing that pairing's "prior_attr/
state_attr" framing where it doesn't literally apply.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_weather_park.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.mlb.weather_totals_gate import build_weather_corpus
from domains.mlb.umpire_totals_gate import build_umpire_totals_corpus
from scripts.platformkit.interaction_factory.builders_umpire import (
    build_umpire_game_frame, _UMPIRE_SOURCES,
)

REPO = Path(__file__).resolve().parents[3]
_PROBABLES = REPO / "data" / "domains" / "mlb" / "probables.parquet"
_GAMES_CURRENT = REPO / "data" / "domains" / "mlb" / "games_current.parquet"
_WEATHER_SOURCES = (_PROBABLES, _GAMES_CURRENT)
_WEATHER_PARK_CORPUS_ID = "weather_totals_gate_x_probables_park"
_CROSS_CORPUS_ID = "weather_totals_gate_x_umpire_totals_park"

MIN_PARK_PRIOR = 15  # same floor mlb_umpire_asof/MIN_UMPIRE_PRIOR uses

WEATHER_POOL_ATTRS = ("wind_out_mph_raw", "temp_above_park_norm_asof", "park_runs_factor_asof")


def build_weather_park_corpus(
    probables: Optional[pd.DataFrame] = None,
    games_current: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """weather_totals_gate.build_weather_corpus()'s own leak-free frame (date,
    game_pk, temp_f, wind_speed, wind_out, wind_in, total_runs) with venue
    added via a plain left-merge on probables (no duplicate game_pk in
    probables -- verified live -- so this cannot fan out rows)."""
    wc = build_weather_corpus(probables, games_current)
    prob = (probables.copy() if isinstance(probables, pd.DataFrame)
            else pd.read_parquet(str(_PROBABLES)))
    venue = prob[["game_pk", "venue"]].drop_duplicates(subset=["game_pk"])
    return wc.merge(venue, on="game_pk", how="left")


def build_weather_park_game_frame(corpus: pd.DataFrame, attrs: List[str],
                                   min_prior: int = MIN_PARK_PRIOR) -> pd.DataFrame:
    """Leak-free per-game frame from build_weather_park_corpus()'s shape. See
    module docstring's EXOGENOUS-WEATHER LEAK NUANCE for why wind_out_mph_raw
    is not as-of-shifted while the 2 park-norm attrs are."""
    d = corpus.sort_values(["date", "game_pk"], kind="mergesort").reset_index(drop=True)
    league_cum_n = d.index.to_series()  # row i (0-indexed) has exactly i strictly-prior rows
    league_cum_sum = d["total_runs"].cumsum().shift(1)
    league_mean = league_cum_sum / league_cum_n.where(league_cum_n > 0)

    grp = d.groupby("venue", sort=False)
    n_prior_games = grp.cumcount()
    valid_games = n_prior_games >= min_prior

    if "wind_out_mph_raw" in attrs:
        d["asof__wind_out_mph_raw"] = d["wind_out"]  # exogenous, no shift -- see docstring
    if "temp_above_park_norm_asof" in attrs:
        temp_notna = d["temp_f"].notna()
        park_cum_temp = grp["temp_f"].transform(lambda s: s.cumsum().shift(1))
        park_cum_n_temp = grp["temp_f"].transform(lambda s: s.notna().cumsum().shift(1))
        park_mean_temp = park_cum_temp / park_cum_n_temp.where(park_cum_n_temp >= min_prior)
        d["asof__temp_above_park_norm_asof"] = (d["temp_f"] - park_mean_temp).where(temp_notna)
    if "park_runs_factor_asof" in attrs:
        park_cum_runs = grp["total_runs"].transform(lambda s: s.cumsum().shift(1))
        park_mean_runs = park_cum_runs / n_prior_games.where(valid_games)
        d["asof__park_runs_factor_asof"] = (park_mean_runs - league_mean).where(valid_games)

    d["y"] = d["total_runs"]
    keep = ["game_pk", "venue", "y"] + [
        "asof__" + a for a in attrs if ("asof__" + a) in d.columns]
    return d[keep].copy()


def _mlb_weather_park_asof_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not all(p.exists() for p in _WEATHER_SOURCES):
        return None
    corpus = build_weather_park_corpus()
    frame = build_weather_park_game_frame(corpus, attrs)
    return {"frame": frame, "cluster": "venue", "corpus": _WEATHER_PARK_CORPUS_ID, "kind": "ols"}


def _mlb_weather_park_umpire_cross_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not all(p.exists() for p in _WEATHER_SOURCES) or not all(p.exists() for p in _UMPIRE_SOURCES):
        return None
    weather_attrs = [a for a in attrs if a in WEATHER_POOL_ATTRS]
    umpire_attrs = [a for a in attrs if a not in WEATHER_POOL_ATTRS]
    wp_frame = build_weather_park_game_frame(build_weather_park_corpus(), weather_attrs)
    ump_frame = build_umpire_game_frame(build_umpire_totals_corpus(), umpire_attrs)
    merged = wp_frame.merge(ump_frame.drop(columns=["y"]), on="game_pk", how="inner")
    return {"frame": merged, "cluster": "venue", "corpus": _CROSS_CORPUS_ID, "kind": "ols"}


__all__ = [
    "build_weather_park_corpus", "build_weather_park_game_frame",
    "_mlb_weather_park_asof_builder", "_mlb_weather_park_umpire_cross_builder",
    "MIN_PARK_PRIOR", "WEATHER_POOL_ATTRS",
]
