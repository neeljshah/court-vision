"""Feature-source resolution extracted from :mod:`screen_predictor`."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from scripts.platformkit.eval_gate.family_bars import load_families
from scripts.platformkit.foundry import asof_supply
from scripts.platformkit.foundry.grammar import Hypothesis


@lru_cache(maxsize=96)
def _table(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def _families_of(hypothesis: Hypothesis) -> list:
    """Frozen families that could have enumerated this hypothesis."""
    return [family for family in load_families().families
            if family.sport == hypothesis.sport and family.horizon == hypothesis.horizon
            and family.market == hypothesis.market and hypothesis.feature in family.members]


def source_column(hypothesis: Hypothesis, name: str, table: pd.DataFrame,
                  context: Optional[pd.DataFrame] = None) -> pd.Series:
    """Return an as-of feature series indexed by event id."""
    names = [hypothesis.family] + [family.name for family in _families_of(hypothesis)]
    declared = next((item for item in names if item and asof_supply.declared(item, name)), None)
    if declared is not None:
        try:
            return asof_supply.supply(declared, name, table.index, context)
        except asof_supply.SupplyUnavailable as exc:
            raise _core.ScreenRefused("unavailable: %s" % exc)
    _core.check_feature_name(name, table.columns)
    if name in table.columns:
        return pd.to_numeric(table[name], errors="coerce")
    parts, tried = [], []
    for family in _families_of(hypothesis):
        for src in family.sources:
            frame = _table(str(_core.ROOT / src))
            key = next((item for item in ("event_id", "game_id") if item in frame.columns), None)
            tried.append(Path(src).name)
            if key is None or name not in frame.columns:
                continue
            got = frame[[key, name]].dropna(subset=[key])
            got[key] = got[key].astype(str)
            if got[key].duplicated().any():
                raise _core.ScreenRefused("unavailable: %s has >1 row per %s in %s (player/tick grain)"
                                          % (name, key, Path(src).name))
            parts.append(got.set_index(key)[name])
    if not parts:
        raise _core.ScreenRefused("unavailable: %s not found one-row-per-event in %s"
                                  % (name, ", ".join(sorted(set(tried))) or "no frozen family source"))
    joined = pd.concat(parts)
    joined = joined[~joined.index.duplicated(keep="first")]
    return pd.to_numeric(joined.reindex(table.index), errors="coerce")


# Bound at the BOTTOM of this file: screen_predictor imports source_column, so a top-of-file
# back-import crashes whenever this module is the one imported first.
from scripts.platformkit.foundry import screen_predictor as _core
