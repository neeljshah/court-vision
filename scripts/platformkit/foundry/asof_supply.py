"""S85 -- NAMED as-of supply for frozen family columns the gate corpus cannot serve.

`screen_predictor.source_column` serves a member column only when it is already a gate-corpus
column or a one-row-per-event column of the family's own frozen source; 14 pregame families fail
both tests (player / pitcher / referee / team-season grain, or no `asof` token in the name). This
module is the DECLARED bridge: per (family, column) pair it names the table, the join and the
event-level rule, nothing else. An undeclared pair is refused as before -- the registry is
additive, so no already-screened family's values move.

Three rules, and the whole leak contract lives in them:

  event  one row per event; served as-is. Legal ONLY for a column settled BEFORE the event
         (entry rank points, seed, draw size, height, `*_asof` columns already built as-of).
  side   two rows per event, one per side (a team abbreviation, or an is_p1 flag); the value is
         home-minus-away (p1-minus-p2), or one declared side. It serves the event's OWN row, so
         S129 fails it closed: no declared `pregame` basis (table + date rule), no supply.
  prior  (entity, date) grain; the served value is the expanding mean over rows of that entity
         with date STRICTLY BEFORE the event's own -- `merge_asof(allow_exact_matches=False)`.
         EVERY column then becomes as-of by construction, a same-game total included, because
         the event's own row is unreachable.

`prior` is what makes a referee's card total or a reliever's batters-faced honest: the served
value is that entity's history, never this match. The referee ASSIGNMENT is read from the event's
own row (published before kickoff); that row's card totals are not. On a `season` grain the event's
season comes from the SOURCE's own convention (`season_table` / `season_start_month`), never from
`dt.year` -- S128: 51.78 pct of soccer matches sit in the year AFTER their own season label.

A SCREEN is a NON-FINDING. Calibration language only.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from scripts.platformkit.foundry.asof_supply_columns import (
    ATP_WTA, IDENTIFIERS, MLB_ALIAS, TENNIS_FEATURES, TENNIS_META, TENNIS_RETURN, _NBA_QUARTER,
    _PIT, _STYLE)

ROOT = Path(__file__).resolve().parents[3]


class SupplyUnavailable(ValueError):
    """A declared pair could not be resolved on this corpus; the reason is the message."""


@dataclass(frozen=True)
class Supply:
    """One family's declared bridge. `columns` is the closed list this entry may serve."""

    source: str                 # repo-relative parquet path, or a glob for a sharded table
    rule: str                   # "event" | "side" | "prior"
    columns: tuple
    key: str = "event_id"       # event key column (event / side rules, and the "row" assignment)
    side: str = ""              # side column (side rule), or the assignment column (entity "row")
    entity: str = ""            # entity column (prior rule)
    date: str = ""              # date column (prior rule)
    entity_from: str = "team"   # "team" | "player" | "row" -- how the event names its entity
    grain: str = "date"         # "date" (calendar) or "season" (the SOURCE's own season label)
    season_table: str = ""      # (season grain) table mapping `key` -> the source's own season
    season_start_month: int = 0 # (season grain) or the month a season starts; 1 = calendar year
    pregame: str = ""           # (side rule) the DECLARED pregame as-of basis: table + date rule
    combine: str = "diff"       # "diff" (a - b) | "a" (the home / p1 side only)
    loader: str = ""            # optional reshaper in _LOADERS
    overrides: tuple = ()       # ((column, combine), ...) where one column combines differently


# ------------------------------------------------------------------ loaders (reshape only)
def _load_glob(pattern: str) -> pd.DataFrame:
    # S111: a COMMA lists patterns -- one glob wide enough for the ATP table and its `_wta`
    # sibling also catches the unrelated `_ext2026`.
    paths = [q for part in pattern.split(",") for q in sorted(ROOT.glob(part.strip()))]
    if not paths:
        raise SupplyUnavailable("no table matches %s" % pattern)
    return pd.concat([pd.read_parquet(q) for q in paths], ignore_index=True)


def _load_referee(path: str) -> pd.DataFrame:
    """The soccer event_id carries its own date (YYYYMMDD prefix); the table carries no date."""
    frame = _read(path).copy()
    frame["_date"] = pd.to_datetime(frame["event_id"].astype(str).str[:8], format="%Y%m%d",
                                    errors="coerce")
    return frame


def _load_player_adv(path: str) -> pd.DataFrame:
    """Player-grain as-of stats rolled to (team, date) through the boxscore's own roster, which
    is same-game knowledge -- so this frame is served ONLY through the `prior` rule."""
    frame, box = _read(path).copy(), _read("data/domains/basketball_nba/player_boxscores.parquet")
    box = box[["game_id", "player_id", "team"]].astype(str).drop_duplicates(["game_id", "player_id"])
    frame["game_id"] = frame["game_id"].astype(str)
    frame["player_id"] = frame["player_id"].astype(str)
    merged = frame.merge(box, on=["game_id", "player_id"], how="inner")
    values = [c for c in merged.columns if c not in ("game_id", "player_id", "date", "team")]
    return merged.groupby(["team", "date"], as_index=False)[values].mean()


_LOADERS = {"glob": _load_glob, "referee": _load_referee, "player_adv": _load_player_adv}

# ------------------------------------------------------------------ the registry
REGISTRY = {
    # This table's frozen event_id is an ESPN id; its game_id is the NBA id the gate corpus uses.
    "nba_quarter_shape": Supply("data/domains/basketball_nba/asof_quarter_shape.parquet", "event",
                                _NBA_QUARTER, key="game_id"),
    # Two rows per game, one per team. S129: the pregame basis is DECLARED and measured --
    # perturbing a game's own boxscore moves none of the 4 columns on that game (5 games sampled
    # evenly); the producer emits from PRE-game state, then updates (player_value_asof.py:87).
    "nba_player_value_features": Supply("data/domains/basketball_nba/player_value_features.parquet",
                                        "side", ("roster_value_asof", "star_absence_delta",
                                                 "continuity", "top_heavy"),
                                        key="game_id", side="team_abbr",
                                        pregame="player_boxscores.parquet, state BEFORE game_id"),
    "nba_opp_allowed": Supply("data/cache/pit/opp_allowed_asof_*.parquet", "prior", _PIT,
                              entity="team", date="game_date", loader="glob"),
    "nba_player_adv": Supply("data/domains/basketball_nba/asof_player_adv.parquet", "prior",
                             ("usagepercentage_asof", "offensiverating_asof",
                              "defensiverating_asof", "pie_asof", "possessions_asof", "n_prior"),
                             entity="team", date="date", loader="player_adv"),
    "mlb_bullpen_relief_chains": Supply("data/domains/mlb/bullpen_relief_chains.parquet", "prior",
                                        ("battersFaced", "rest_days", "is_b2b",
                                         "appearances_last_3d"), entity="team", date="date"),
    "soccer_referee_card_foul_profiles": Supply(
        "data/domains/soccer/referee_card_foul_profiles.parquet", "prior",
        ("total_fouls", "total_yellow", "total_red", "total_cards"),
        entity="referee", date="_date", entity_from="row", side="referee", combine="a",
        loader="referee"),
    "soccer_style_fingerprints": Supply("data/domains/soccer/style_fingerprints.parquet", "prior",
                                        _STYLE, entity="team", date="season", grain="season",
                                        season_table="data/domains/soccer/matches.parquet"),
    "tennis_features": Supply(ATP_WTA.format("features"), "event", TENNIS_FEATURES, loader="glob"),
    "tennis_return": Supply(ATP_WTA.format("return"), "event", TENNIS_RETURN, loader="glob"),
    "tennis_meta": Supply(ATP_WTA.format("meta"), "event", TENNIS_META, loader="glob"),
    # S122: `tennis_schedule_density` and `tennis_travel_scouting` are DELIBERATELY NOT declared.
    # Their sources key on Sackmann's `date` = the TOURNEY START (1451/1451 ATP and 974/974 WTA
    # tourneys carry ONE distinct date), so a trailing-window count cannot order a player's matches
    # within an event: the 2025 Wimbledon champion's seven serve 0,3,4,5,1,6,2 and 46.2 pct of rows
    # read rest_days == 0. Served p1-minus-p2 correlates +0.2616 with the outcome and "beat" the
    # devigged close by 0.0202 (p=0.0000) -- a LEAK. The built WTA halves would carry coverage to
    # 800/800 and 785/800, but no as-of column comes off this grain. See
    # docs/evidence/harness/S122_tennis_wta_schedule_travel_2026-09-03.md.
    "tennis_serve_return_profiles": Supply("data/domains/tennis/serve_return_profiles.parquet",
                                           "prior", ("serve_strength", "return_strength",
                                                     "n_matches", "z_serve_strength",
                                                     "z_return_strength"),
                                           entity="player_id", date="season", grain="season",
                                           entity_from="player", season_start_month=1),
}


def declared(family: Optional[str], name: str) -> bool:
    """True when this exact (family, column) pair has a declared bridge."""
    spec = REGISTRY.get(family or "")
    return spec is not None and name in spec.columns and name not in IDENTIFIERS


@lru_cache(maxsize=32)
def _read(path: str) -> pd.DataFrame:
    full = ROOT / path
    if not full.exists():
        raise SupplyUnavailable("source %s is not on disk" % path)
    return pd.read_parquet(full)


@lru_cache(maxsize=32)
def _frame(family: str) -> pd.DataFrame:
    spec = REGISTRY[family]
    return _LOADERS[spec.loader](spec.source) if spec.loader else _read(spec.source)


def _sides(spec: Supply, context: pd.DataFrame) -> tuple:
    """(a_key, b_key) string arrays aligned to `context.index` -- home/away, or p1/p2."""
    if spec.entity_from == "player":
        parts = pd.Series(context.index.astype(str), index=context.index).str.split("-")
        return parts.str[-3].to_numpy(), parts.str[-2].to_numpy()  # S122: from the END
    alias = MLB_ALIAS if str(context.attrs.get("sport", "")) == "mlb" else {}
    for column in ("home", "away"):
        if column not in context.columns:
            raise SupplyUnavailable("the corpus context carries no %r column" % column)
    return tuple(context[c].astype(str).map(lambda t: alias.get(t, t)).to_numpy()
                 for c in ("home", "away"))


def _combine(spec: Supply, name: str, a: np.ndarray, b: Optional[np.ndarray]) -> np.ndarray:
    return a if b is None or dict(spec.overrides).get(name, spec.combine) == "a" else a - b


def _column(family: str, name: str) -> pd.DataFrame:
    frame = _frame(family)
    if name not in frame.columns:
        raise SupplyUnavailable("%s is not a column of %s" % (name, REGISTRY[family].source))
    return frame


def _event_rule(family: str, name: str, index: pd.Index) -> np.ndarray:
    spec, frame = REGISTRY[family], _column(family, name)
    keyed = frame.dropna(subset=[spec.key]).copy()
    keyed[spec.key] = keyed[spec.key].astype(str)
    keyed = keyed.drop_duplicates(spec.key).set_index(spec.key)
    return pd.to_numeric(keyed[name], errors="coerce").reindex(index.astype(str)).to_numpy(float)


def _side_rule(family: str, name: str, index: pd.Index, context: pd.DataFrame) -> np.ndarray:
    spec, frame = REGISTRY[family], _column(family, name)
    if not spec.pregame:        # S129: this rule serves the EVENT'S OWN ROW; fail closed
        raise SupplyUnavailable("no declared pregame as-of basis for %s/%s" % (family, name))
    keyed = frame.dropna(subset=[spec.key, spec.side]).copy()
    keyed[spec.key] = keyed[spec.key].astype(str)
    boolean = keyed[spec.side].dtype == bool
    keyed["_side"] = keyed[spec.side].astype(str)
    series = pd.to_numeric(
        keyed.drop_duplicates([spec.key, "_side"]).set_index([spec.key, "_side"])[name],
        errors="coerce")
    if boolean:                      # an is_p1 flag: side "True" is p1, "False" is p2
        a_key, b_key = np.full(len(index), "True"), np.full(len(index), "False")
    else:
        a_key, b_key = _sides(spec, context)
    ids = index.astype(str)
    a = series.reindex(pd.MultiIndex.from_arrays([ids, a_key])).to_numpy(float)
    b = series.reindex(pd.MultiIndex.from_arrays([ids, b_key])).to_numpy(float)
    return _combine(spec, name, a, b)


def _season_of(spec: Supply, index: pd.Index, when: pd.Series) -> pd.Series:
    """S128: the event's season under the SOURCE's own convention, never `dt.year`."""
    if spec.season_table:
        keyed = _read(spec.season_table).drop_duplicates(spec.key)
        got = pd.Series(keyed["season"].to_numpy(), index=keyed[spec.key].astype(str))
        return pd.Series(got.reindex(index.astype(str)).to_numpy(float), index=when.index)
    if not spec.season_start_month:
        raise SupplyUnavailable("grain='season' declares no season_table or season_start_month")
    return (when.dt.year - (when.dt.month < spec.season_start_month)).astype(float)


def _prior_one(src: pd.DataFrame, entity: np.ndarray, when: pd.Series) -> np.ndarray:
    """The entity's expanding mean over rows STRICTLY BEFORE `when` -- the as-of guard itself."""
    left = pd.DataFrame({"_e": pd.Series(entity, index=when.index).astype(str), "_d": when})
    left = left.dropna(subset=["_d"]).sort_values("_d", kind="mergesort")
    if left.empty or src.empty:
        return np.full(len(when), np.nan)
    merged = pd.merge_asof(left, src, on="_d", by="_e", direction="backward",
                           allow_exact_matches=False)
    merged.index = left.index
    return merged["_v"].reindex(when.index).to_numpy(float)


def _prior_rule(family: str, name: str, index: pd.Index, context: pd.DataFrame) -> np.ndarray:
    spec, frame = REGISTRY[family], _column(family, name)
    src = frame[[spec.entity, spec.date, name]].dropna(subset=[spec.entity, spec.date]).copy()
    src["_e"] = src[spec.entity].astype(str)
    src["_d"] = (src[spec.date].astype(float) if spec.grain == "season"
                 else pd.to_datetime(src[spec.date], errors="coerce"))
    src = src.dropna(subset=["_d"]).sort_values("_d", kind="mergesort")
    src["_v"] = pd.to_numeric(src[name], errors="coerce").groupby(src["_e"]).transform(
        lambda s: s.expanding().mean())
    src = src.dropna(subset=["_v"])[["_e", "_d", "_v"]]
    when = pd.to_datetime(context["date"], errors="coerce")
    if spec.grain == "season":
        when = _season_of(spec, index, when)
    if spec.entity_from == "row":
        assign = _frame(family).dropna(subset=[spec.key]).copy()
        assign[spec.key] = assign[spec.key].astype(str)
        a_key = assign.drop_duplicates(spec.key).set_index(spec.key)[spec.side].reindex(
            index.astype(str)).astype(str).to_numpy()
        b_key = None
    else:
        a_key, b_key = _sides(spec, context)
    a = _prior_one(src, a_key, when)
    return _combine(spec, name, a, None if b_key is None else _prior_one(src, b_key, when))


def _refuse_all_nan(values: pd.Series, context: Optional[pd.DataFrame]) -> pd.Series:
    """S111 (c): a pair supplying ENTIRELY NaN on the window it will be SCORED on is UNAVAILABLE,
    not merely under-covered -- `nba_quarter_shape` served 0 non-null of 1,814 (an ESPN event_id
    against the corpus's NBA game_id) and still reached a silent UNCOVERED. `served_rows` is the
    screen binder's last-N window; absent -> the whole supplied index."""
    rows = None if context is None else context.attrs.get("served_rows")
    window = values if not rows else values.iloc[-int(rows):]
    if len(window) and not np.isfinite(pd.to_numeric(window, errors="coerce").to_numpy(float)).any():
        raise SupplyUnavailable("all-NaN on the served window")
    return values


def supply(family: str, name: str, index: pd.Index, context: Optional[pd.DataFrame]) -> pd.Series:
    """The declared as-of value for one (family, column) pair, aligned to the corpus `index`."""
    if not declared(family, name):
        raise SupplyUnavailable("%s/%s is not declared" % (family, name))
    spec = REGISTRY[family]
    if spec.rule == "event":
        values = _event_rule(family, name, index)
    elif context is None:
        raise SupplyUnavailable("rule %r needs the corpus context (date, home, away)" % spec.rule)
    elif spec.rule == "side":
        values = _side_rule(family, name, index, context)
    else:
        values = _prior_rule(family, name, index, context)
    return _refuse_all_nan(pd.Series(values, index=index, name=name), context)
