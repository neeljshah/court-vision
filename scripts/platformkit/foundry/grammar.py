"""Closed-alphabet hypothesis grammar for signal-foundry families."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pandas as pd

_TRANSFORMS = frozenset(("raw", "ew", "rank_in_league", "z_vs_league", "delta_vs_prior", "ratio_to_opponent"))
_HORIZONS = frozenset(("pregame", "period", "live_tick"))
_MARKETS = frozenset(("ml", "total", "spread", "prop", "inplay"))
_EW_HALFLIVES = frozenset((3, 5, 10, 20))
_REGISTRY_PATH = Path("data/registry/signal_registry.parquet")
_MONTH = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class Hypothesis:
    """One fully specified foundry candidate before any evaluation."""

    sport: str
    feature: str
    transform: str
    params: tuple[Any, ...]
    conditioning: frozenset[str]
    horizon: str
    market: str


def _param_map(params: tuple[Any, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in params:
        if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str):
            raise ValueError("params must contain (name, value) pairs")
        if item[0] in result:
            raise ValueError("duplicate parameter: {0}".format(item[0]))
        result[item[0]] = item[1]
    return result


def _normalise_params(transform: str, params: tuple[Any, ...]) -> tuple[tuple[str, int], ...]:
    values = _param_map(params)
    if transform != "ew":
        return ()
    if set(values) != {"halflife"} or values["halflife"] not in _EW_HALFLIVES:
        raise ValueError("ew halflife must be one of {3, 5, 10, 20}")
    return (("halflife", int(values["halflife"])),)


def _validate_conditioning(conditioning: frozenset[str]) -> frozenset[str]:
    for item in conditioning:
        if not isinstance(item, str) or "=" not in item:
            raise ValueError("conditioning must contain k=v strings")
        key, value = item.split("=", 1)
        if key not in {"phase", "rest", "month", "confidence"} or not value:
            raise ValueError("unknown conditioning key: {0}".format(item))
        if key == "rest" and value not in {"B2B", "RESTED", "NORMAL"}:
            raise ValueError("invalid rest conditioning: {0}".format(item))
        if key == "month" and not _MONTH.fullmatch(value):
            raise ValueError("invalid month conditioning: {0}".format(item))
        if key == "confidence" and value not in {"T1", "T2", "T3"}:
            raise ValueError("invalid confidence conditioning: {0}".format(item))
    return conditioning


@lru_cache(maxsize=1)
def _signal_ids() -> dict[tuple[str, str], str]:
    """Read the registry if materialized; it is never modified by this module."""
    if not _REGISTRY_PATH.exists():
        return {}
    frame = pd.read_parquet(_REGISTRY_PATH)
    if "signal_id" not in frame:
        return {}
    feature_column = next((name for name in ("feature", "column", "source_column", "name") if name in frame), None)
    sport_column = next((name for name in ("sport", "domain") if name in frame), None)
    if feature_column is None:
        return {}
    result = {}
    for row in frame[["signal_id", feature_column] + ([sport_column] if sport_column else [])].itertuples(index=False):
        signal_id, feature, *sport = row
        if pd.notna(signal_id) and pd.notna(feature):
            result[((str(sport[0]) if sport else ""), str(feature))] = str(signal_id)
    return result


def canonical_payload(hypothesis: Hypothesis) -> dict[str, Any]:
    """Return the grid-normalized payload used as the hash preimage."""
    if hypothesis.transform not in _TRANSFORMS:
        raise ValueError("unknown transform: {0}".format(hypothesis.transform))
    if hypothesis.horizon not in _HORIZONS or hypothesis.market not in _MARKETS:
        raise ValueError("unknown horizon or market")
    params = _normalise_params(hypothesis.transform, hypothesis.params)
    conditioning = _validate_conditioning(hypothesis.conditioning)
    feature = _signal_ids().get((hypothesis.sport, hypothesis.feature), hypothesis.feature)
    return {"sport": hypothesis.sport, "feature": feature, "transform": hypothesis.transform,
            "params": params, "conditioning": sorted(conditioning), "horizon": hypothesis.horizon,
            "market": hypothesis.market}


def semantic_hash(hypothesis: Hypothesis) -> str:
    """Hash a canonical hypothesis so ordering and unused inputs cannot matter."""
    encoded = json.dumps(canonical_payload(hypothesis), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _transform_variants(transforms: Sequence[Any]) -> Iterator[tuple[str, tuple[Any, ...]]]:
    for entry in transforms:
        if isinstance(entry, str):
            name, params = entry, ()
            if name == "ew":
                for value in sorted(_EW_HALFLIVES):
                    yield name, (("halflife", value),)
                continue
        elif isinstance(entry, Mapping):
            name = entry.get("name")
            values = {key: value for key, value in entry.items() if key != "name"}
            if name == "ew" and isinstance(values.get("halflife"), (list, tuple, set, frozenset)):
                for value in values["halflife"]:
                    yield name, (("halflife", value),)
                continue
            params = tuple(values.items())
        elif isinstance(entry, tuple) and len(entry) == 2:
            name, value = entry
            params = (("halflife", value),) if name == "ew" else ()
        else:
            raise ValueError("invalid transform declaration")
        if name not in _TRANSFORMS:
            raise ValueError("unknown transform: {0}".format(name))
        _normalise_params(name, tuple(params))
        yield name, tuple(params)


def _conditioning_options(value: Any) -> tuple[frozenset[str], ...]:
    if isinstance(value, frozenset):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return (frozenset(value),)
    return tuple(frozenset(item) for item in value)


def _columns(spec: Mapping[str, Any]) -> tuple[str, ...]:
    has_columns, has_parquet = "columns" in spec, "parquet" in spec
    if has_columns == has_parquet:
        raise ValueError("spec needs exactly one of columns or parquet")
    if has_parquet:
        path = Path(spec["parquet"])
        if not path.exists():
            raise ValueError("catalogue parquet is absent: {0}".format(path))
        return tuple(str(name) for name in pd.read_parquet(path).columns)
    return tuple(str(name) for name in spec["columns"])


def enumerate_family(spec: Mapping[str, Any]) -> Iterator[Hypothesis]:
    """Exhaustively enumerate a closed family without charging an evaluation trial."""
    required = {"sport", "transforms", "conditionings", "horizons", "markets", "family", "runtime_available"}
    missing = required.difference(spec)
    if missing:
        raise ValueError("missing family fields: {0}".format(", ".join(sorted(missing))))
    columns = _columns(spec)
    availability = spec["runtime_available"]
    if not isinstance(availability, Mapping) or set(availability) != set(columns):
        raise ValueError("runtime_available requires one explicit declaration per column")
    if not all(isinstance(value, bool) for value in availability.values()):
        raise ValueError("runtime_available values must be bool")
    variants = tuple(_transform_variants(spec["transforms"]))
    conditionings = _conditioning_options(spec["conditionings"])
    if not variants or not conditionings:
        raise ValueError("family needs transforms and closed conditionings")
    for condition in conditionings:
        _validate_conditioning(condition)
    for horizon, market, column, (transform, params), condition in product(
            spec["horizons"], spec["markets"], columns, variants, conditionings):
        hypothesis = Hypothesis(str(spec["sport"]), column, transform, params, condition, horizon, market)
        canonical_payload(hypothesis)
        yield hypothesis
