"""Leak-safe, runtime-available schedule context signals.

Venue data is injected at the N10 boundary. Prior state is snapshotted with
``asof_common.walk_forward_asof`` before the current game is folded in.
"""
from __future__ import annotations
import importlib
import math
from collections.abc import Callable, Mapping
from typing import Any
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from scripts.platformkit.asof_common import AsofSpec, walk_forward_asof
OUTPUT_COLUMNS = (
    "rest_differential",
    "games_in_last_7_days_diff",
    "travel_km_since_last_game",
    "timezone_shift_signed",
    "circadian_hour_at_start",
    "altitude_delta_m",
)
RUNTIME_TAG = "RUNTIME"
RUNTIME_AVAILABLE = True
class _LastValue:
    def __init__(self) -> None:
        self.n = 0
        self._value = float("nan")
    def snapshot(self) -> float:
        return self._value

    def update(self, obs: object) -> None:
        self.n += 1
        if obs is not None and not pd.isna(obs):
            self._value = float(obs)
class _TrailingMean:
    def __init__(self, width: int) -> None:
        self.n = 0
        self._width = width
        self._values: list[float] = []
    def snapshot(self) -> float:
        return float(np.mean(self._values)) if self._values else float("nan")

    def update(self, obs: object) -> None:
        if obs is None or pd.isna(obs):
            return
        self.n += 1
        self._values.append(float(obs))
        del self._values[:-self._width]
def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)
def great_circle_km(a: object, b: object) -> float:
    """Return the great-circle distance between two venue-like values."""
    alat, alon = float(_field(a, "lat")), float(_field(a, "lon"))
    blat, blon = float(_field(b, "lat")), float(_field(b, "lon"))
    radius = 6371.0088
    p1, p2 = math.radians(alat), math.radians(blat)
    dp, dl = math.radians(blat - alat), math.radians(blon - alon)
    h = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return radius * 2.0 * math.asin(math.sqrt(min(1.0, h)))
def _venue_from_table(table: object, team: object, venue_id: object,
                      when: pd.Timestamp) -> object:
    if table is None:
        try:
            mod = importlib.import_module("scripts.platformkit.signals.venue_table")
            return mod.lookup(team, when.date())
        except (ImportError, AttributeError, KeyError, TypeError, ValueError):
            return None
    if callable(table):
        try:
            return table(team, when.date())
        except (KeyError, TypeError, ValueError):
            return None
    lookup = getattr(table, "lookup", None)
    if callable(lookup):
        try:
            return lookup(team, when.date())
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(table, pd.DataFrame):
        rows = table
        if venue_id is not None and "venue_id" in rows:
            rows = rows[rows["venue_id"].astype(str) == str(venue_id)]
        elif "team_id" in rows:
            rows = rows[rows["team_id"].astype(str) == str(team)]
        elif "team_ids" in rows:
            def has_team(value: object) -> bool:
                if _is_missing(value):
                    return False
                if isinstance(value, str):
                    return str(team) == value
                return str(team) in {str(v) for v in (value or [])}
            rows = rows[rows["team_ids"].map(has_team)]
        return rows.iloc[0].to_dict() if len(rows) else None
    if isinstance(table, Mapping):
        for key in (venue_id, team):
            if key is not None and key in table:
                return table[key]
        for value in table.values():
            ids = _field(value, "team_ids", ()) or ()
            if str(team) in {str(v) for v in ids}:
                return value
    return None
def _normalize_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    source = schedule.copy()
    event_col = next((c for c in ("event_id", "game_id", "id") if c in source), None)
    date_col = next((c for c in ("date", "game_date") if c in source), None)
    start_col = next((c for c in ("start_time", "scheduled_start", "start") if c in source), None)
    if date_col is None:
        raise ValueError("schedule requires date or game_date")
    if start_col is None:
        source["__start_time"] = None
        start_col = "__start_time"
    if {"home_team", "away_team"}.issubset(source.columns):
        out = pd.DataFrame({
            "event_id": source[event_col] if event_col else [f"game_{i}" for i in range(len(source))],
            "date": pd.to_datetime(source[date_col], errors="coerce").dt.normalize(),
            "start_time": source[start_col],
            "home_team": source["home_team"], "away_team": source["away_team"],
            "home_venue": source["home_venue"] if "home_venue" in source else source.get("venue"),
            "away_venue": source["away_venue"] if "away_venue" in source else source.get("venue"),
        })
        return out
    if "team" not in source:
        raise ValueError("schedule requires home_team/away_team or team")
    if event_col is None:
        if "opponent" not in source:
            raise ValueError("long schedule without opponent requires game_id/event_id")
        source["__event_id"] = source.groupby([date_col, "team", "opponent"], sort=False).ngroup()
        event_col = "__event_id"
    if "is_home" in source:
        home_mask = source["is_home"].astype(bool)
    elif "home" in source:
        home_mask = source["home"].astype(bool)
    else:
        home_mask = source.groupby(event_col, sort=False).cumcount().eq(0)
    rows: list[dict[str, object]] = []
    for event_id, group in source.groupby(event_col, sort=False, dropna=False):
        order = group.index
        home_idx = order[home_mask.loc[order].to_numpy().nonzero()[0][0]] if home_mask.loc[order].any() else order[0]
        away_idx = next((i for i in order if i != home_idx), home_idx)
        home = source.loc[home_idx]
        away = source.loc[away_idx]
        rows.append({"event_id": event_id, "date": pd.Timestamp(home[date_col]).normalize(),
                     "start_time": home[start_col], "home_team": home["team"],
                     "away_team": away["team"], "home_venue": home.get("venue"),
                     "away_venue": away.get("venue")})
    return pd.DataFrame(rows, columns=["event_id", "date", "start_time", "home_team",
                                       "away_team", "home_venue", "away_venue"])
def _asof_pair(frame: pd.DataFrame, home_obs: str, away_obs: str,
               prefix: str, factory: Callable[[], object]) -> pd.DataFrame:
    spec = AsofSpec(sort_keys=("date", "event_id"),
                    slots=(("home_team", home_obs, "home"), ("away_team", away_obs, "away")),
                    id_col="event_id")
    result = walk_forward_asof(frame, spec, factory).set_index("event_id")
    result = result.reindex(frame["event_id"])
    return result[["home_asof", "away_asof", "home_n_prior", "away_n_prior"]].rename(
        columns={"home_asof": f"home_{prefix}", "away_asof": f"away_{prefix}"})
def _start_parts(value: object, when: pd.Timestamp, tz_name: object) -> tuple[float, float]:
    if _is_missing(value):
        return float("nan"), float("nan")
    try:
        raw = str(value).strip()
        if len(raw) <= 8 and raw.count(":") >= 1 and "-" not in raw and "T" not in raw:
            pieces = raw.split(":")
            stamp = when.normalize() + pd.Timedelta(hours=int(pieces[0]),
                                                      minutes=int(pieces[1]))
        else:
            stamp = pd.Timestamp(value)
        zone = ZoneInfo(str(tz_name)) if not _is_missing(tz_name) else None
        if stamp.tzinfo is not None:
            local = stamp.tz_convert(zone) if zone else stamp
            offset = local.utcoffset().total_seconds() / 3600.0
            return local.hour + local.minute / 60.0 + local.second / 3600.0, offset
        local = stamp
        if zone:
            local = stamp.tz_localize(zone)
            offset = local.utcoffset().total_seconds() / 3600.0
        else:
            offset = float("nan")
        return local.hour + local.minute / 60.0 + local.second / 3600.0, offset
    except (KeyError, TypeError, ValueError, OSError):
        try:
            hour, minute = str(value).strip().split(":")[:2]
            return float(hour) + float(minute) / 60.0, float("nan")
        except (ValueError, TypeError):
            return float("nan"), float("nan")


def fill_rate_report(frame: pd.DataFrame) -> dict[str, float]:
    n = len(frame)
    return {column: float(frame[column].notna().mean()) if n else 0.0 for column in OUTPUT_COLUMNS}


def build_schedule_context(schedule: pd.DataFrame, venue_table: object = None,
                           *, last_k: int = 3, return_report: bool = False) -> Any:
    """Build N11's six strictly-prior schedule signals.

    Missing N10 metadata produces NaN and a lower fill rate, never a fabricated zero.
    """
    if last_k < 1:
        raise ValueError("last_k must be positive")
    frame = _normalize_schedule(schedule)
    if frame.empty:
        empty = pd.DataFrame({"event_id": pd.Series(dtype="object"),
                              **{c: pd.Series(dtype="float64") for c in OUTPUT_COLUMNS}})
        empty.attrs["fill_rate"] = fill_rate_report(empty)
        return (empty, empty.attrs["fill_rate"]) if return_report else empty
    if frame["event_id"].duplicated().any():
        raise ValueError("schedule event_id values must be unique")
    venue_info: dict[tuple[str, str], object] = {}
    for side in ("home", "away"):
        for i, row in frame.iterrows():
            team = row[f"{side}_team"]
            venue_info[(side, str(row["event_id"]))] = _venue_from_table(
                venue_table, team, row[f"{side}_venue"], row["date"])
    obs = frame.copy()
    obs["__date_num"] = (obs["date"] - pd.Timestamp("1970-01-01")) / pd.Timedelta(days=1)
    for side in ("home", "away"):
        dates, lats, lons, elevs, offsets = [], [], [], [], []
        hours = []
        for _, row in obs.iterrows():
            venue = venue_info[(side, str(row["event_id"]))]
            lat = _field(venue, "lat")
            lon = _field(venue, "lon")
            elev = _field(venue, "elevation_m")
            tz_name = _field(venue, "tz_name")
            hour, offset = _start_parts(row["start_time"], row["date"], tz_name)
            dates.append(row["__date_num"]); lats.append(lat); lons.append(lon)
            elevs.append(elev); offsets.append(offset); hours.append(hour)
        obs[f"__{side}_date"] = dates; obs[f"__{side}_lat"] = lats
        obs[f"__{side}_lon"] = lons; obs[f"__{side}_elev"] = elevs
        obs[f"__{side}_offset"] = offsets; obs[f"__{side}_hour"] = hours
    date_asof = _asof_pair(obs, "__home_date", "__away_date", "date", _LastValue)
    current_dates = obs.set_index("event_id")["__date_num"].reindex(date_asof.index)
    home_days = current_dates - date_asof["home_date"]
    away_days = current_dates - date_asof["away_date"]
    prior_home = date_asof["home_n_prior"] > 0
    prior_away = date_asof["away_n_prior"] > 0
    result = pd.DataFrame({"event_id": frame["event_id"].to_numpy()})
    rest = (home_days - away_days).where(prior_home & prior_away)
    result["rest_differential"] = result["event_id"].map(rest).astype(float)
    ordered = obs.sort_values(["date", "event_id"], kind="mergesort")
    histories: dict[object, list[float]] = {}
    congestion_rows: list[tuple[float, float]] = []
    for _, row in ordered.iterrows():
        current = row["__date_num"]
        values = []
        for team in (row["home_team"], row["away_team"]):
            prior_dates = histories.get(team, [])
            values.append(float(sum(0.0 < current - d <= 7.0 for d in prior_dates)) if prior_dates else float("nan"))
        congestion_rows.append((row["event_id"], values[0] - values[1] if all(np.isfinite(values)) else float("nan")))
        for team in (row["home_team"], row["away_team"]):
            histories.setdefault(team, []).append(current)
    congestion_map = dict(congestion_rows)
    result["games_in_last_7_days_diff"] = result["event_id"].map(congestion_map).astype(float)
    lat = _asof_pair(obs, "__home_lat", "__away_lat", "lat", _LastValue)
    lon = _asof_pair(obs, "__home_lon", "__away_lon", "lon", _LastValue)
    offset = _asof_pair(obs, "__home_offset", "__away_offset", "offset", lambda: _TrailingMean(last_k))
    elev = _asof_pair(obs, "__home_elev", "__away_elev", "elev", lambda: _TrailingMean(last_k))
    travel_values, tz_values, circadian_values, altitude_values = [], [], [], []
    for i, row in obs.iterrows():
        event = str(row["event_id"])
        current_venue = venue_info[("away", event)]
        current_lat, current_lon = _field(current_venue, "lat"), _field(current_venue, "lon")
        old_lat, old_lon = lat.loc[row["event_id"], "away_lat"], lon.loc[row["event_id"], "away_lon"]
        travel_values.append(great_circle_km({"lat": old_lat, "lon": old_lon},
                             {"lat": current_lat, "lon": current_lon}) if not any(_is_missing(v) for v in (old_lat, old_lon, current_lat, current_lon)) else float("nan"))
        current_offset = _field(current_venue, "tz_name")
        _, current_offset = _start_parts(row["start_time"], row["date"], current_offset)
        old_offset = offset.loc[row["event_id"], "away_offset"]
        tz_values.append(current_offset - old_offset if not any(_is_missing(v) for v in (current_offset, old_offset)) else float("nan"))
        hour = row["__away_hour"]
        circadian_values.append((hour + old_offset - current_offset) % 24.0 if not any(_is_missing(v) for v in (hour, current_offset, old_offset)) else float("nan"))
        old_elev = elev.loc[row["event_id"], "away_elev"]
        current_elev = _field(current_venue, "elevation_m")
        altitude_values.append(float(current_elev) - old_elev if not any(_is_missing(v) for v in (current_elev, old_elev)) else float("nan"))
    result["travel_km_since_last_game"] = travel_values
    result["timezone_shift_signed"] = tz_values
    result["circadian_hour_at_start"] = circadian_values
    result["altitude_delta_m"] = altitude_values
    result = result[["event_id", *OUTPUT_COLUMNS]]
    result.attrs["fill_rate"] = fill_rate_report(result)
    return (result, result.attrs["fill_rate"]) if return_report else result


compute_schedule_context = build_schedule_context
build = build_schedule_context

__all__ = ["OUTPUT_COLUMNS", "RUNTIME_TAG", "RUNTIME_AVAILABLE", "great_circle_km",
           "fill_rate_report", "build_schedule_context", "compute_schedule_context", "build"]
