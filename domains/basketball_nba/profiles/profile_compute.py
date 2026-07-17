"""Shared math + row-shaping for the attribute engine. One place that knows
the SHARED SCHEMA (see attribute_registry.py's module docstring for the
column contract) so every *_attributes.py module just produces intermediate
frames and calls into here.

rating_2k is a PRESENTATION-ONLY transform: 25 + percentile*0.74 maps
percentile [0,100] -> a 2K-style [25,99] band. Gates/fits must ALWAYS read
raw_value, never rating_2k or percentile -- documented on ATTRIBUTES itself
and re-asserted in the builder's coverage print.

NETWORK: zero.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]


def _ascii_name(name: str) -> str:
    """NFKD-fold to plain ASCII (mirrors intel_query/ask.py's _ascii_name) so
    an accented and a plain spelling of the same entity_id (e.g. a player
    name with a diacritic vs its bare-letter form) collapse to one canonical
    string in the shared-schema parquet instead of two duplicate rows."""
    decomposed = unicodedata.normalize("NFKD", str(name))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


RATING_FLOOR = 25.0
RATING_SLOPE = 0.74


def rating_2k(percentile: float) -> float:
    """25 + percentile*0.74 -- presentation only, never feed to a gate/fit."""
    return round(RATING_FLOOR + float(percentile) * RATING_SLOPE, 2)


def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """0-100 percentile WITHIN the qualified population passed in (the
    caller has already applied the floor -- this never re-derives one)."""
    s = series if higher_is_better else -series
    return (s.rank(pct=True, method="average") * 100.0).round(4)


def exclude_negative_ids(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
    """Drop rows touching a negative placeholder id in ANY of `cols` -- the
    unresolved-lineup-slot landmine documented in nba_player_interaction_
    claims.py, present at varying rates across all 3 NBA seasons on disk."""
    mask = pd.Series(True, index=df.index)
    for c in cols:
        if c in df.columns:
            mask &= df[c] >= 0
    return df[mask]


def ingredients_json(values: dict[str, Any]) -> str:
    """Compact json string, floats rounded to 4dp so round-tripping through
    the ingredients column is exact for the test's own reload check."""
    out = {}
    for k, v in values.items():
        if isinstance(v, float):
            out[k] = round(v, 4)
        elif hasattr(v, "item"):  # numpy scalar
            out[k] = round(float(v), 4) if isinstance(v.item(), float) else v.item()
        else:
            out[k] = v
    return json.dumps(out, separators=(",", ":"))


def rel_sources(*paths: Path) -> str:
    return ";".join(str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in paths)


def finalize_rows(
    df: pd.DataFrame,
    *,
    entity_col: str,
    name_col: str | None,
    raw_col: str,
    n_col: str,
    window: str,
    attribute: str,
    status: str,
    sources: str,
    ingredient_cols: Iterable[str],
    higher_is_better: bool = True,
    entity_id_int: bool = True,
) -> list[dict[str, Any]]:
    """The ONE place raw_value -> percentile -> rating_2k -> row dict
    happens. `df` must already be floor-filtered and id-filtered by the
    caller -- this only ranks + shapes."""
    d = df.dropna(subset=[raw_col]).reset_index(drop=True)
    if d.empty:
        return []
    pct = percentile_rank(d[raw_col], higher_is_better=higher_is_better)
    rows = []
    for i, r in d.iterrows():
        eid = int(r[entity_col]) if entity_id_int else str(r[entity_col])
        rows.append({
            "entity_id": eid,
            "entity_name": _ascii_name(r[name_col]) if name_col else "",
            "window": window,
            "attribute": attribute,
            "raw_value": round(float(r[raw_col]), 6),
            "percentile": float(pct[i]),
            "rating_2k": rating_2k(pct[i]),
            "n": float(r[n_col]),
            "ingredients": ingredients_json({c: r[c] for c in ingredient_cols if c in d.columns}),
            "status": status,
            "sources": sources,
        })
    return rows


def zscore(s: pd.Series) -> pd.Series:
    """Standardize within the qualified population passed in; a zero-
    variance column (all-equal after floor filtering) returns 0.0 for every
    row rather than dividing by zero."""
    mu, sd = s.mean(), s.std()
    return (s - mu) / sd if sd else pd.Series(0.0, index=s.index)


def compose_rim_pressure(d: pd.DataFrame) -> pd.Series:
    """3 suppression swings, each oriented so POSITIVE = better defense, then
    z-scored within the qualified population and summed -- so the composite's
    sign is 'higher = more rim deterrence' regardless of each ingredient's own
    raw scale (share is a 0-1 fraction, eFG a 0-1 rate, pts_against a per-48
    point count -- not directly comparable unscaled)."""
    swing_rim_share = d["rim_share_allowed_off"] - d["rim_share_allowed_on"]
    swing_rim_efg = d["rim_efg_allowed_off"] - d["rim_efg_allowed_on"]
    swing_pts_against = d["pts_against_per48_off"] - d["pts_against_per48_on"]
    return zscore(swing_rim_share) + zscore(swing_rim_efg) + zscore(swing_pts_against)


def direct_column_rows(
    df: pd.DataFrame,
    *,
    entity_col: str,
    name_col: str | None,
    cols: Iterable[str],
    n_col: str,
    window: str,
    status: str,
    sources: str,
    attr_prefix: str = "",
    higher_is_better: bool = True,
) -> list[dict[str, Any]]:
    """One attribute per column in `cols`, each row's own value is its own
    (only) ingredient -- the pass-through case used by concession/shot-diet
    where a source column IS the attribute, verbatim."""
    rows: list[dict[str, Any]] = []
    for col in cols:
        rows.extend(finalize_rows(
            df, entity_col=entity_col, name_col=name_col, raw_col=col, n_col=n_col,
            window=window, attribute=f"{attr_prefix}{col}", status=status, sources=sources,
            ingredient_cols=[col], higher_is_better=higher_is_better,
        ))
    return rows
