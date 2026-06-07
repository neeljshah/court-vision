"""PROFILE-FACTORY BRIDGE -- persist an AtlasSection by EXTENDING the factory.

Per spec_intel_memory.md section 4 (the disjoint-extension recipe), an atlas section
is persisted as exactly ``1 disjoint parquet + 1 sec_ function`` -- NEVER by rebuilding
``scripts/build_persistent_profiles.py``.  This bridge:

  1. MATERIALISE  -- write the section's per-entity artifacts to a disjoint parquet
     ``data/cache/atlas_<entity>_<name>.parquet`` keyed by player_id/team_tricode,
     with provenance/confidence/as_of + the reserved cv_fields embedded as a JSON column.
  2. GENERATE sec_ -- emit a ``sec_<name>(pid, s)->(data, prov)`` function source string
     that mirrors the factory pattern (clean/rd/conf_from_n; returns None on missing);
     the generated function reads the disjoint parquet and is loaded via the registry
     hook -- the factory file itself is NEVER edited.
  3. WRITE TO STORE -- also call ``store.write_atlas`` so signals can read the section
     leak-safe from the point-in-time store immediately.
  4. MANIFEST -- record the registration in ``.planning/loop/atlas_registry.json``
     (section key -> parquet, sec_fn_name, cv_fields, as_of, entity) idempotently.

Merge semantics mirror the factory's ``merge_section``: higher-confidence-OR-newer-as_of
wins; an existing entry is never silently clobbered by a lower-quality build.

The registry is read by ``scripts/loop/build_profile_indices.py`` for deterministic
index regeneration.  The generated ``sec_`` function is callable directly by callers
who want the same (data, prov) tuple the factory uses.
"""
from __future__ import annotations

import json
import math
import textwrap
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .atlas import AtlasArtifact, AtlasSection

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"
PROFILES = CACHE / "profiles"
REGISTRY = ROOT / ".planning" / "loop" / "atlas_registry.json"

# Confidence ordering (mirrors the factory)
_CONF_ORDER = {"low": 0, "med": 1, "high": 2}

# Entity-id column names used in the disjoint parquet
_ID_COL: Dict[str, str] = {"player": "player_id", "team": "team_tricode"}


# ---------------------------------------------------------------------------
# Public API (exact signatures from DESIGN.md §2.4)
# ---------------------------------------------------------------------------

def register_section(
    section: AtlasSection,
    artifacts: List[AtlasArtifact],
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Persist a validated atlas section by extending the factory.

    Steps:
      1. materialise_parquet -> data/cache/atlas_<entity>_<name>.parquet
      2. write_atlas into the point-in-time store (each artifact, its as_of)
      3. emit_sec_function -> the generated sec_ function source text
      4. update_registry -> .planning/loop/atlas_registry.json

    Args:
        section:   the AtlasSection instance (carries name/entity/cv_fields/parquet_name).
        artifacts: list of built+validated AtlasArtifacts (one per entity).
        store:     optional PointInTimeStore; when provided, write_atlas is called.
        dry_run:   if True, compute everything but skip all disk writes.

    Returns:
        manifest dict with keys: section, parquet, sec_fn, n_entities, cv_fields, as_of.
    """
    if not artifacts:
        return {
            "section": section.name,
            "parquet": str(_parquet_path(section)),
            "sec_fn": section.sec_fn_name(),
            "n_entities": 0,
            "cv_fields": list(section.cv_fields().keys()),
            "as_of": None,
        }

    # 1. Materialise parquet
    parquet_path = materialise_parquet(section, artifacts, dry_run=dry_run)

    # 2. Write atlas records into the point-in-time store
    if store is not None and not dry_run:
        for art in artifacts:
            if art.as_of is None:
                continue
            data, prov = art.to_profile_payload()
            store.write_atlas(
                art.entity, art.entity_id, section.name, art.as_of, data, prov
            )

    # 3. Emit the sec_ function (source string; not executed here -- registry callers load it)
    _sec_src = emit_sec_function(section)

    # 4. Build the as_of summary (latest across all artifacts)
    as_of_dates = [a.as_of for a in artifacts if a.as_of]
    as_of = max(as_of_dates) if as_of_dates else None

    manifest: Dict[str, Any] = {
        "section": section.name,
        "entity": section.entity,
        "parquet": str(parquet_path),
        "sec_fn": section.sec_fn_name(),
        "sec_fn_source": _sec_src,
        "n_entities": len(artifacts),
        "cv_fields": list(section.cv_fields().keys()),
        "as_of": as_of,
    }

    # 5. Write registry manifest
    update_registry(manifest, dry_run=dry_run)

    return manifest


def materialise_parquet(
    section: AtlasSection,
    artifacts: List[AtlasArtifact],
    *,
    dry_run: bool = False,
) -> Path:
    """Write the disjoint per-entity parquet for this atlas section.

    Columns:
      - <id_col>      (player_id int OR team_tricode str)
      - <sub_field>   one column per sub_field key (JSON-serialised if not scalar)
      - n             int sample size from provenance
      - confidence    str ("low"/"med"/"high")
      - as_of         str ISO date
      - _cv_fields    JSON blob of reserved CV-slot schema (values null until CV fills)

    Merge semantics: if the parquet already exists, existing rows for entities NOT in
    ``artifacts`` are PRESERVED (accumulate-don't-clobber). Rows in ``artifacts`` replace
    only when the new confidence is higher-or-equal OR the new as_of is strictly newer.
    """
    out_path = _parquet_path(section)
    id_col = _ID_COL.get(section.entity, "entity_id")

    rows: List[Dict[str, Any]] = []
    for art in artifacts:
        data, prov = art.to_profile_payload()
        row: Dict[str, Any] = {id_col: art.entity_id}
        # Flatten sub_fields into columns; complex values are JSON-encoded strings
        for k, v in data.items():
            if k == "_cv_fields":
                row["_cv_fields"] = json.dumps(v)
            elif isinstance(v, (dict, list)):
                row[k] = json.dumps(_clean_for_json(v))
            else:
                row[k] = _clean_scalar(v)
        row["n"] = int(prov.get("n", 0))
        row["confidence"] = prov.get("confidence", "low")
        row["as_of"] = prov.get("as_of")
        rows.append(row)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[id_col, "n", "confidence", "as_of"])

    # Merge with existing parquet (accumulate-don't-clobber)
    if out_path.exists() and not new_df.empty:
        try:
            old_df = pd.read_parquet(out_path)
            merged = _merge_parquet_rows(old_df, new_df, id_col)
        except Exception:
            merged = new_df
    else:
        merged = new_df

    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(out_path, index=False)

    return out_path


def emit_sec_function(section: AtlasSection) -> str:
    """Return the source text of the generated ``sec_<name>`` function.

    The emitted function mirrors the factory's sec_ pattern:
      - signature: ``def sec_<name>(pid: int, s: dict) -> Optional[tuple]``
      - reads the disjoint parquet (``data/cache/atlas_<entity>_<name>.parquet``)
      - uses ``clean``/``rd``/``conf_from_n`` from the factory helper namespace
      - returns ``(data, prov)`` or ``None`` on missing entity
      - cv_fields JSON column is decoded and included under ``_cv_fields``

    The generated text does NOT edit ``build_persistent_profiles.py``.  It is
    stored in the registry manifest and can be exec()'d by a caller that already
    has the factory helpers in scope, or loaded via the registry hook.
    """
    fn_name = section.sec_fn_name()
    parquet_rel = f"atlas_{section.entity}_{section.name}.parquet"
    id_col = _ID_COL.get(section.entity, "entity_id")
    entity_label = section.entity  # "player" or "team"

    src = textwrap.dedent(f'''\
        def {fn_name}(pid, s, _parquet_cache={{}}, _ROOT=None, _CACHE_DIR=None):
            """Auto-generated sec_ function for atlas section '{section.name}'.

            Reads data/cache/{parquet_rel} (written by profile_factory_bridge).
            Returns (data, prov) or None if entity not found.

            Args:
                _ROOT:      override repo root (for testing; real use auto-detects via __file__)
                _CACHE_DIR: override the cache directory directly (takes precedence over _ROOT)
            """
            import json as _json
            import pandas as _pd
            from pathlib import Path as _Path

            # locate parquet: _CACHE_DIR wins, then _ROOT/data/cache, then script-relative
            if _CACHE_DIR is not None:
                _pq = _Path(_CACHE_DIR) / "{parquet_rel}"
            else:
                _root = _ROOT or _Path(__file__).resolve().parents[1]
                _pq = _root / "data" / "cache" / "{parquet_rel}"
            if not _pq.exists():
                return None
            # cache the dataframe across calls within one build run
            if str(_pq) not in _parquet_cache:
                try:
                    _parquet_cache[str(_pq)] = _pd.read_parquet(_pq)
                except Exception:
                    return None
            _df = _parquet_cache[str(_pq)]
            if "{id_col}" not in _df.columns:
                return None
            _g = _df[_df["{id_col}"] == pid]
            if _g.empty:
                return None
            _r = _g.iloc[0]
            # Reconstruct data dict
            _skip = {{"{id_col}", "n", "confidence", "as_of"}}
            _data = {{}}
            for _c in _df.columns:
                if _c in _skip:
                    continue
                _v = _r.get(_c)
                if _v is None or (_pd.api.types.is_float(_v) and _pd.isna(_v)):
                    continue
                if _c == "_cv_fields":
                    try:
                        _data["_cv_fields"] = _json.loads(_v)
                    except Exception:
                        _data["_cv_fields"] = {{}}
                elif isinstance(_v, str):
                    try:
                        _data[_c] = _json.loads(_v)
                    except Exception:
                        _data[_c] = _v
                else:
                    _data[_c] = clean(_v)
            _n = int(_r.get("n") or 0)
            _conf = str(_r.get("confidence") or "low")
            _as_of = str(_r.get("as_of") or "") or None
            _prov = {{
                "source": "{parquet_rel}",
                "n": _n,
                "confidence": _conf,
                "as_of": _as_of,
            }}
            return _data, _prov
    ''')
    return src


def update_registry(manifest: Dict[str, Any], *, dry_run: bool = False) -> None:
    """Record or refresh the section registration in atlas_registry.json (idempotent).

    The registry maps section key -> manifest entry.  Existing entries are replaced
    (newer build supersedes).  The file is kept sorted by section key for readability.
    """
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if REGISTRY.exists():
        try:
            existing = json.loads(REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    section_key = manifest.get("section", "unknown")
    existing[section_key] = manifest

    if not dry_run:
        REGISTRY.write_text(
            json.dumps(dict(sorted(existing.items())), indent=2, default=str),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Registry hook: load all registered sec_ functions (called by factory or indices)
# ---------------------------------------------------------------------------

def load_registered_sections() -> Dict[str, Any]:
    """Return the atlas registry as a dict keyed by section name.

    Each value is the manifest dict (section, parquet, sec_fn, sec_fn_source, ...).
    Returns an empty dict if the registry does not exist yet.
    """
    if not REGISTRY.exists():
        return {}
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_sec_function(section_name: str, *, factory_globals: Optional[dict] = None):
    """Compile and return the generated sec_ function for a registered section.

    The function is compiled in a namespace that includes the factory's helper
    functions (``clean``, ``rd``, ``conf_from_n``) when ``factory_globals`` is
    provided, otherwise stub versions are used so the function is always callable.

    Args:
        section_name:    the section key in the registry (e.g. "shot_profile").
        factory_globals: dict from the factory module's globals() (for clean/rd/conf_from_n).

    Returns:
        the callable ``sec_<name>`` function, or None if not in the registry.
    """
    registry = load_registered_sections()
    if section_name not in registry:
        return None
    src = registry[section_name].get("sec_fn_source")
    if not src:
        return None

    # Build exec namespace with helper stubs (factory_globals override if provided)
    ns: Dict[str, Any] = {
        "clean": _clean_scalar,
        "rd": _rd,
        "conf_from_n": _conf_from_n_stub,
    }
    if factory_globals:
        for k in ("clean", "rd", "conf_from_n"):
            if k in factory_globals:
                ns[k] = factory_globals[k]

    exec(compile(src, f"<sec_{section_name}>", "exec"), ns)  # noqa: S102
    fn_name = registry[section_name].get("sec_fn", f"sec_{section_name}")
    return ns.get(fn_name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parquet_path(section: AtlasSection) -> Path:
    return CACHE / section.parquet_name()


def _clean_scalar(v: Any) -> Any:
    """JSON-safe scalar (mirrors factory clean()): NaN/inf -> None, numpy -> python."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return str(v)[:10]
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _clean_for_json(obj: Any) -> Any:
    """Recursively clean a dict/list for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_for_json(x) for x in obj]
    return _clean_scalar(obj)


def _rd(v: Any) -> Optional[float]:
    """Mirror factory rd() -> clean scalar or None."""
    return _clean_scalar(v)


def _conf_from_n_stub(n: int, cap: Optional[str] = None) -> str:
    """Stub conf_from_n matching the factory logic (used when factory_globals absent)."""
    level = "high" if n >= 20 else "med" if n >= 5 else "low"
    if cap is not None and _CONF_ORDER.get(level, 0) > _CONF_ORDER.get(cap, 2):
        return cap
    return level


def _merge_parquet_rows(old_df: pd.DataFrame, new_df: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """Merge new_df rows into old_df with accumulate-don't-clobber semantics.

    An existing row is replaced only when the new row has higher-or-equal confidence
    OR a strictly newer as_of.  Rows in old_df for entities absent in new_df are kept.
    """
    if id_col not in old_df.columns or id_col not in new_df.columns:
        return new_df

    old_indexed = old_df.set_index(id_col)
    new_rows = []

    for _, nrow in new_df.iterrows():
        eid = nrow[id_col]
        if eid not in old_indexed.index:
            new_rows.append(nrow)
            continue
        orow = old_indexed.loc[eid]
        old_conf = _CONF_ORDER.get(str(orow.get("confidence", "low")), 0)
        new_conf = _CONF_ORDER.get(str(nrow.get("confidence", "low")), 0)
        old_as = str(orow.get("as_of") or "")
        new_as = str(nrow.get("as_of") or "")
        # replace if new is strictly better conf OR has newer as_of
        if new_conf >= old_conf or new_as > old_as:
            old_indexed.loc[eid] = nrow.drop(id_col)
        # else keep old (do nothing)

    # Re-add any new entities not already in old
    old_reset = old_indexed.reset_index()
    existing_ids = set(old_reset[id_col].tolist())
    truly_new = new_df[~new_df[id_col].isin(existing_ids)]
    return pd.concat([old_reset, truly_new], ignore_index=True)
