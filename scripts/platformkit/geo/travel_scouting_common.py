# -*- coding: utf-8 -*-
"""scripts.platformkit.geo.travel_scouting_common -- shared helpers for the
per-sport SCOUTING travel/altitude descriptor builders (mlb / soccer / tennis).

DESCRIPTOR-ONLY: every function here produces a per-game/per-match SCOUTING
column (miles flown in since the entity's previous appearance in this corpus,
plus this venue's altitude_m). None of this is a model feature -- the NBA
travel gate (scripts/platformkit/nba_travel_gate_run.py) already ran the
identical style of gate on travel_home/travel_away/abs_travel_diff and the
honest result was REJECT (Elo + schedule rest/HFA subsume travel). These
sibling sports get the SAME scouting treatment, never re-litigated as a
market edge, per docs/JOB_EVIDENCE_PACKET.md discipline.

No network calls -- reuses scripts.platformkit.geo.city_geo (static table).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from scripts.platformkit.geo.city_geo import great_circle_km, lookup

KM_TO_MILES = 0.621371


def miles_between(city_a: Optional[str], city_b: Optional[str],
                  country_a: Optional[str] = None,
                  country_b: Optional[str] = None) -> Optional[float]:
    """Great-circle miles between two cities via the static geo table, or
    None on an honest miss (either city unresolved)."""
    row_a = lookup(city_a, country_a) if city_a else None
    row_b = lookup(city_b, country_b) if city_b else None
    if row_a is None or row_b is None:
        return None
    km = great_circle_km(row_a["lat"], row_a["lon"], row_b["lat"], row_b["lon"])
    return km * KM_TO_MILES


def altitude_m(city: Optional[str], country: Optional[str] = None) -> Optional[float]:
    """Venue altitude in meters via the static geo table, or None on a miss."""
    row = lookup(city, country) if city else None
    return float(row["altitude_m"]) if row is not None else None


def prior_city_travel(df: pd.DataFrame, entity_col: str, date_col: str,
                      city_col: str, country_col: Optional[str] = None,
                      ) -> pd.Series:
    """Per-ENTITY chronological previous-appearance travel in miles.

    For each row, looks at the SAME entity's most recent PRIOR row (by
    date_col, ties broken by original row order) and returns the great-circle
    miles from that prior row's city to this row's city. The very first
    appearance of an entity has no prior city -> NaN (honest, never 0-filled).
    This is a strictly-prior quantity: it only ever looks backward in time.
    """
    work = df[[entity_col, date_col, city_col] + ([country_col] if country_col else [])].copy()
    work["_orig_order"] = range(len(work))
    work = work.sort_values([entity_col, date_col, "_orig_order"], kind="mergesort")
    prev_city = work.groupby(entity_col, sort=False)[city_col].shift(1)
    prev_country = (work.groupby(entity_col, sort=False)[country_col].shift(1)
                    if country_col else pd.Series(None, index=work.index))

    out = pd.Series(index=work.index, dtype="float64")
    for idx in work.index:
        c_from = prev_city.loc[idx]
        c_to = work.loc[idx, city_col]
        if pd.isna(c_from) or pd.isna(c_to):
            out.loc[idx] = float("nan")
            continue
        ctry_from = prev_country.loc[idx] if country_col else None
        ctry_to = work.loc[idx, country_col] if country_col else None
        m = miles_between(c_from, c_to, ctry_from, ctry_to)
        out.loc[idx] = m if m is not None else float("nan")
    return out.reindex(df.index)


def coverage_report(series: pd.Series, label: str) -> dict:
    """Honest lookup coverage: fraction of non-null rows in a descriptor
    series. Reported plainly, never hidden."""
    total = len(series)
    hit = int(series.notna().sum())
    return {"label": label, "total_rows": int(total), "hit_rows": hit,
            "coverage": round(hit / total, 4) if total else 0.0}


__all__ = ["miles_between", "altitude_m", "prior_city_travel", "coverage_report",
           "KM_TO_MILES"]
