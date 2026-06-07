"""ATLAS -> MODEL FEATURES: expose SHIPPED atlas sections as leak-safe model inputs.

The ARM-B intelligence layer ships ~40+ descriptive atlas sections (player & team)
persisted by ``profile_factory_bridge`` as ``data/cache/atlas_<entity>_<name>.parquet``
and registered in ``.planning/loop/atlas_registry.json``.  They are ALSO written into
the leak-safe point-in-time store (``src.loop.store.PointInTimeStore``).

This module is the READ-SIDE bridge that lets the prop / win-prob models consume that
intelligence as flat, numeric, **leak-safe, as-of** features keyed by
``(player_id | tricode, as_of)``.  It is a NEW additive module: it does NOT modify
``src/features/feature_engineering.py`` or ``src/prediction/prop_pergame.py``.

Leak-safety contract (the whole point):
  * The point-in-time store is the PRIMARY source -- ``read_atlas(..., as_of)`` returns
    only records stamped ``<= as_of`` (never the future).
  * The disjoint parquet is a SINGLE current-state snapshot (one ``as_of`` per entity
    = the latest build).  It is used as a FALLBACK only when the store has no record,
    and ONLY if the row's ``as_of <= requested as_of`` -- otherwise reading it would
    leak future intelligence into a historical training row, so it is dropped.

Public API:
  * ``atlas_feature_row(entity_id, as_of, *, entity_type, sections, store)`` -> dict
  * ``join_atlas_features(rows, *, ...)`` -> enrich a prop-feature-matrix row list
  * ``atlas_feature_names(...)`` -> stable ordered feature-name list (for the model)

Feature naming: ``atlas_<section>__<dotted.path.to.leaf>`` for numeric leaves, e.g.
``atlas_usage_role__usage_rate`` or ``atlas_shot_profile__creation.drive_fg_pct``.
Categorical leaves (str) are emitted under the same name with the raw string value so a
caller can one-hot / target-encode them; DEFER ``_note`` stubs and null CV slots are
skipped entirely so they never pollute the matrix.
"""
from __future__ import annotations

import datetime as _dt
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import pandas as pd

from .store import PointInTimeStore, entity_key, get_store

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"
REGISTRY = ROOT / ".planning" / "loop" / "atlas_registry.json"

_ID_COL = {"player": "player_id", "team": "team_tricode"}
# Parquet bookkeeping columns that are never features.
_META_COLS = {"player_id", "team_tricode", "entity_id", "n", "confidence", "as_of",
              "_cv_fields"}
_DateLike = Union[str, _dt.date, _dt.datetime]


def _to_iso(when: _DateLike) -> str:
    """Normalise any date-like to an ISO ``YYYY-MM-DD`` string (date granularity)."""
    if isinstance(when, str):
        return when[:10]
    if isinstance(when, _dt.datetime):
        return when.date().isoformat()
    if isinstance(when, _dt.date):
        return when.isoformat()
    raise TypeError(f"unsupported as_of type: {type(when)!r}")


@lru_cache(maxsize=1)
def _registry() -> Dict[str, Dict[str, Any]]:
    """Load the atlas registry (section -> manifest). Empty dict if absent."""
    if not REGISTRY.exists():
        return {}
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def registered_sections(entity_type: Optional[str] = None) -> List[str]:
    """Return registered atlas section names, optionally filtered by entity type.

    Args:
        entity_type: ``"player"`` or ``"team"``; ``None`` returns both.

    Returns:
        Sorted list of section keys present in the registry.
    """
    reg = _registry()
    out = [k for k, v in reg.items()
           if entity_type is None or v.get("entity") == entity_type]
    return sorted(out)


def _flatten(obj: Any, prefix: str, out: Dict[str, Any]) -> None:
    """Recursively flatten numeric/categorical leaves into ``out`` under dotted keys.

    Skips: ``_note``/``_source`` DEFER stubs, null values, the ``_cv_fields`` block,
    and any key starting with ``_``.  Numbers and short strings become leaves; bools
    are coerced to int (model-friendly).  Lists are skipped (not point features).
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str) or k.startswith("_"):
                continue
            _flatten(v, f"{prefix}.{k}" if prefix else k, out)
        return
    if obj is None:
        return
    if isinstance(obj, bool):
        out[prefix] = int(obj)
        return
    if isinstance(obj, (int, float)):
        f = float(obj)
        if f != f:  # NaN
            return
        out[prefix] = f
        return
    if isinstance(obj, str):
        # categorical leaf (kept raw); skip empty/whitespace
        s = obj.strip()
        if s:
            out[prefix] = s
        return
    # lists / other types are not point features -> skip


def _decode_parquet_value(v: Any) -> Any:
    """Decode one parquet cell: JSON-encoded dict/list strings become objects."""
    if isinstance(v, str):
        stripped = v.strip()
        if stripped[:1] in ("{", "["):
            try:
                return json.loads(stripped)
            except Exception:
                return v
    return v


@lru_cache(maxsize=128)
def _load_parquet(entity_type: str, section: str) -> Optional[pd.DataFrame]:
    """Load (and cache) a section's disjoint parquet, or None if missing."""
    pq = CACHE / f"atlas_{entity_type}_{section}.parquet"
    if not pq.exists():
        return None
    try:
        return pd.read_parquet(pq)
    except Exception:
        return None


def _section_dict_from_store(
    store: PointInTimeStore, entity_type: str, entity_id: Any,
    section: str, as_of_iso: str,
) -> Optional[Dict[str, Any]]:
    """Leak-safe read of one section's payload from the point-in-time store."""
    data = store.read_atlas(entity_type, entity_id, section, as_of_iso, with_cv=False)
    return data if isinstance(data, dict) else None


def _section_dict_from_parquet(
    entity_type: str, entity_id: Any, section: str, as_of_iso: str,
) -> Optional[Dict[str, Any]]:
    """Leak-safe fallback read from the disjoint parquet.

    Returns the entity's payload dict ONLY if the parquet row's ``as_of <= as_of_iso``.
    A row stamped after the requested as_of would leak future intelligence, so it is
    dropped (returns None).
    """
    df = _load_parquet(entity_type, section)
    if df is None:
        return None
    id_col = _ID_COL.get(entity_type, "entity_id")
    if id_col not in df.columns:
        return None
    g = df[df[id_col] == entity_id]
    if g.empty:
        return None
    row = g.iloc[0]
    row_as_of = str(row.get("as_of") or "")
    if not row_as_of or row_as_of > as_of_iso:  # leak guard
        return None
    payload: Dict[str, Any] = {}
    for col in df.columns:
        if col in _META_COLS:
            continue
        v = row.get(col)
        if v is None or (isinstance(v, float) and v != v):
            continue
        payload[col] = _decode_parquet_value(v)
    return payload


def atlas_feature_row(
    entity_id: Any,
    as_of: _DateLike,
    *,
    entity_type: str = "player",
    sections: Optional[Iterable[str]] = None,
    store: Optional[PointInTimeStore] = None,
    prefix: bool = True,
) -> Dict[str, Any]:
    """Return the flat leak-safe atlas feature dict for one entity as-of a date.

    The point-in-time store is the primary, fully leak-safe source; the disjoint
    parquet is a fallback used only when the store has no record AND the parquet
    row's ``as_of <= as_of`` (otherwise it is dropped to avoid look-ahead leakage).

    Args:
        entity_id:   player_id (int) or team tricode (str).
        as_of:       leak boundary -- only intelligence valid at/before this date.
        entity_type: ``"player"`` or ``"team"``.
        sections:    restrict to these section keys; ``None`` = all registered sections
                     for the entity type.
        store:       a ``PointInTimeStore`` (defaults to the process-wide store).
        prefix:      prefix every feature with ``atlas_<section>__`` (default True);
                     pass False to get bare dotted keys (rarely wanted).

    Returns:
        ``{feature_name: value}`` -- numeric (float) or categorical (str) leaves only.
        Empty dict if the entity has no atlas coverage at/before ``as_of``.
    """
    store = store or get_store()
    as_of_iso = _to_iso(as_of)
    secs = list(sections) if sections is not None else registered_sections(entity_type)

    out: Dict[str, Any] = {}
    for section in secs:
        payload = _section_dict_from_store(
            store, entity_type, entity_id, section, as_of_iso)
        if payload is None:
            payload = _section_dict_from_parquet(
                entity_type, entity_id, section, as_of_iso)
        if not payload:
            continue
        leaves: Dict[str, Any] = {}
        _flatten(payload, "", leaves)
        pfx = f"atlas_{section}__" if prefix else ""
        for k, v in leaves.items():
            out[f"{pfx}{k}"] = v
    return out


def join_atlas_features(
    rows: List[Dict[str, Any]],
    *,
    entity_type: str = "player",
    id_key: str = "player_id",
    date_key: str = "date",
    sections: Optional[Iterable[str]] = None,
    store: Optional[PointInTimeStore] = None,
    overwrite: bool = False,
) -> List[Dict[str, Any]]:
    """Enrich a prop-feature-matrix row list in place with leak-safe atlas features.

    Each row is the per-game dict produced by ``prop_pergame.build_pergame_dataset``
    (keyed by ``player_id`` with an ISO ``"date"``).  For every row we look up the
    entity's atlas features as-of that row's date and merge them in.  Because the
    lookup is keyed on the row's own date, the enrichment is leak-free per row.

    Args:
        rows:        list of feature-row dicts (mutated in place and also returned).
        entity_type: ``"player"`` or ``"team"``.
        id_key:      row key holding the entity id (default ``"player_id"``).
        date_key:    row key holding the row's as-of ISO date (default ``"date"``).
        sections:    restrict to these section keys; ``None`` = all for the entity.
        store:       point-in-time store (defaults to the process-wide store).
        overwrite:   if False (default) existing row keys are preserved (atlas only
                     fills gaps); if True atlas values overwrite collisions.

    Returns:
        The same ``rows`` list, each dict enriched with ``atlas_*`` keys. Rows missing
        the id/date key are left untouched.
    """
    store = store or get_store()
    # cache per (entity_id, date) so repeated player-dates don't re-read.
    cache: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        eid = row.get(id_key)
        when = row.get(date_key)
        if eid is None or when is None:
            continue
        ck = (eid, _to_iso(when))
        feats = cache.get(ck)
        if feats is None:
            feats = atlas_feature_row(
                eid, when, entity_type=entity_type,
                sections=sections, store=store)
            cache[ck] = feats
        for k, v in feats.items():
            if overwrite or k not in row:
                row[k] = v
    return rows


def atlas_feature_names(
    entity_type: str = "player",
    *,
    sections: Optional[Iterable[str]] = None,
    numeric_only: bool = True,
) -> List[str]:
    """Return the stable, ordered atlas feature-name list for the model schema.

    Names are discovered from the disjoint parquets (the materialised schema), so the
    list is deterministic across processes.  Use this to append atlas columns to a
    model's feature list without instantiating the store.

    Args:
        entity_type:  ``"player"`` or ``"team"``.
        sections:     restrict to these section keys; ``None`` = all registered.
        numeric_only: drop categorical (string-valued) leaves (default True) so the
                      list is safe to feed straight into a numeric model matrix.

    Returns:
        Sorted list of ``atlas_<section>__<path>`` feature names.
    """
    secs = list(sections) if sections is not None else registered_sections(entity_type)
    names: set = set()
    for section in secs:
        df = _load_parquet(entity_type, section)
        if df is None or df.empty:
            continue
        # use the first non-empty row to discover leaf names
        row = df.iloc[0]
        payload: Dict[str, Any] = {}
        for col in df.columns:
            if col in _META_COLS:
                continue
            v = row.get(col)
            if v is None or (isinstance(v, float) and v != v):
                continue
            payload[col] = _decode_parquet_value(v)
        leaves: Dict[str, Any] = {}
        _flatten(payload, "", leaves)
        for k, v in leaves.items():
            if numeric_only and not isinstance(v, (int, float)):
                continue
            names.add(f"atlas_{section}__{k}")
    return sorted(names)


def clear_caches() -> None:
    """Clear module-level parquet/registry caches (call after a fresh atlas build)."""
    _registry.cache_clear()
    _load_parquet.cache_clear()
