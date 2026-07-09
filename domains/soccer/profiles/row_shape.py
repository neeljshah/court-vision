"""domains.soccer.profiles.row_shape -- the entity_id/entity_name/window/
raw_value/n/ingredients row-shaping helpers shared by build_profiles.py (the
original 7 attributes) and ingredients_expanded.py (the 07-08 expansion's 18
new attributes). Split out so ingredients_expanded.py can import these
WITHOUT a circular import against build_profiles.py (which itself imports
the expansion's compute functions).
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def _num_or_str(v: Any) -> Any:
    if isinstance(v, str):
        return v
    return None if pd.isna(v) else round(float(v), 4)


def _rows(agg: pd.DataFrame, ingredient_cols: list[str], window: Optional[str]) -> pd.DataFrame:
    """Standardize an attribute's per-entity agg DataFrame (entity_id,
    entity_name, raw_value, n, + ingredient_cols[, window]) into the
    entity_id/entity_name/window/raw_value/n/ingredients row shape."""
    out = []
    for r in agg.itertuples(index=False):
        d = r._asdict()
        out.append({
            "entity_id": str(d["entity_id"]), "entity_name": d["entity_name"],
            "window": window if window is not None else d["window"],
            "raw_value": float(d["raw_value"]), "n": int(d["n"]),
            "ingredients": {c: _num_or_str(d[c]) for c in ingredient_cols},
        })
    return pd.DataFrame(out)


def _entity_names(snap: pd.DataFrame) -> pd.Series:
    return snap.drop_duplicates("entity_id").set_index("entity_id")["entity_name"]
