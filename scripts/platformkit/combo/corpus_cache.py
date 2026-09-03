"""Gate-ready per-sport corpus builder and freshness contract.

Per-sport source construction lives in ``corpus_cache_sources``; this module
keeps the established public loader, sidecar, and stale-read behaviour.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_CACHE_DIR = _REPO / "data" / "cache" / "combo"
SPORTS: Tuple[str, ...] = ("mlb", "nba", "soccer", "tennis")
DATE_COL = "event_date"
POSITIONAL_ORDER = "POSITIONAL-ORDER"


class StaleCorpusError(RuntimeError):
    """A cached corpus's source files moved since it was built -- refuse the read."""


def _corpus_path(sport: str) -> Path:
    return _CACHE_DIR / f"gate_corpus_{sport}.parquet"


def _sidecar_path(sport: str) -> Path:
    return _CACHE_DIR / f"gate_corpus_{sport}.sources.json"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _source_key(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        return str(path)


def _resolve_source(key: str) -> Path:
    p = Path(key)
    return p if p.is_absolute() else _REPO / key


def _source_manifest(paths: List[Path]) -> Dict[str, Dict[str, object]]:
    return {_source_key(p): {"mtime": p.stat().st_mtime, "sha256": _file_sha256(p)}
            for p in paths}


def _assert_portable(sport: str, manifest: Dict[str, object], cp: Path,
                     unavailable: List[str]) -> None:
    recorded = manifest.get("corpus_sha256")
    named = ", ".join(unavailable)
    if not recorded:
        raise StaleCorpusError(
            f"portable load refused for {sport!r}: sidecar records no corpus_sha256 "
            f"(pre-S68 sidecar) and recorded source(s) {named} are unavailable here -- "
            f"rebuild via build_gate_corpus({sport!r}) on a host that has them")
    actual = _file_sha256(cp)
    if actual != recorded:
        raise StaleCorpusError(
            f"portable load refused for {sport!r}: {cp.name} sha256 {actual} != "
            f"sidecar corpus_sha256 {recorded}")


from scripts.platformkit.combo import corpus_cache_sources as _sources

_NBA_PAIR_DIFFS = _sources._NBA_PAIR_DIFFS
SOCCER_LEAKY_COLUMNS = _sources.SOCCER_LEAKY_COLUMNS
_SOCCER_ASOF_EXISTING = _sources._SOCCER_ASOF_EXISTING
_SOCCER_ASOF_ADDED = _sources._SOCCER_ASOF_ADDED
_asof_only = _sources._asof_only
_build_mlb, _build_nba = _sources._build_mlb, _sources._build_nba
_build_soccer, _build_tennis = _sources._build_soccer, _sources._build_tennis
_BUILDERS = _sources._BUILDERS


def build_gate_corpus(sport: str) -> pd.DataFrame:
    """Build ONE sport's gate-ready frame, persist to parquet + sources sidecar."""
    if sport not in _BUILDERS:
        raise ValueError(f"unknown sport {sport!r}; must be one of {SPORTS}")
    built = _BUILDERS[sport]()
    df, sources = built[0], built[1]
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_corpus_path(sport), index=False)
    census = _sources.column_coverage(df)
    manifest = {"sport": sport, "built_at": time.time(), "n_rows": len(df),
                "corpus_sha256": _file_sha256(_corpus_path(sport)),
                "sources": _source_manifest(sources),
                "provenance": built[2] if len(built) > 2 else {},
                "coverage": census["coverage"], "zero_coverage": census["zero_coverage"]}
    _sidecar_path(sport).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return df


def load_gate_corpus(sport: str, portable: Optional[bool] = None) -> pd.DataFrame:
    """Load a cached corpus; refuse when a recorded source has moved."""
    if portable is None:
        portable = os.environ.get("FOUNDRY_PORTABLE_CORPUS") == "1"
    cp, sp = _corpus_path(sport), _sidecar_path(sport)
    if not cp.exists() or not sp.exists():
        raise StaleCorpusError(f"no cached corpus for {sport!r}; run build_gate_corpus first")
    manifest = json.loads(sp.read_text(encoding="utf-8"))
    unavailable: List[str] = []
    for src, rec in manifest.get("sources", {}).items():
        p = _resolve_source(src)
        if not p.exists():
            if not portable:
                raise StaleCorpusError(f"source {src} for {sport!r} corpus no longer exists")
            unavailable.append(src)
            continue
        if p.stat().st_mtime != rec["mtime"] or _file_sha256(p) != rec["sha256"]:
            if not portable:
                raise StaleCorpusError(
                    f"source {src} for {sport!r} corpus changed since build "
                    f"(mtime/sha mismatch) -- rebuild via build_gate_corpus({sport!r})")
            unavailable.append(src)
    if unavailable:
        _assert_portable(sport, manifest, cp, unavailable)
    return pd.read_parquet(cp)


def freshness_report(sport: str) -> Dict[str, object]:
    """Return read-only freshness and ordering facts for one cached corpus."""
    if sport not in _BUILDERS:
        raise ValueError(f"unknown sport {sport!r}; must be one of {SPORTS}")
    cp, sp = _corpus_path(sport), _sidecar_path(sport)
    rep: Dict[str, object] = {
        "sport": sport, "corpus_path": str(cp),
        "cache_exists": cp.exists(), "sidecar_exists": sp.exists(),
        "cache_mtime": cp.stat().st_mtime if cp.exists() else None,
        "built_at": None, "n_rows_at_build": None, "n_rows_cached": None,
        "sources": [], "stale": True, "stale_reason": "no cached corpus or sidecar",
        "order_basis": POSITIONAL_ORDER, "provenance": {}, "load_provenance": None,
    }
    if not (cp.exists() and sp.exists()):
        return rep
    manifest = json.loads(sp.read_text(encoding="utf-8"))
    rep["built_at"] = manifest.get("built_at")
    rep["n_rows_at_build"] = manifest.get("n_rows")
    rep["provenance"] = manifest.get("provenance", {})
    cached = pd.read_parquet(cp)
    rep["n_rows_cached"] = len(cached)
    rep["order_basis"] = DATE_COL if DATE_COL in cached.columns else POSITIONAL_ORDER
    census = _sources.column_coverage(cached)
    rep["coverage"] = census["coverage"]
    rep["zero_coverage"] = census["zero_coverage"]
    changed_names: List[str] = []
    for src, rec in manifest.get("sources", {}).items():
        p = _resolve_source(src)
        exists = p.exists()
        now = p.stat().st_mtime if exists else None
        changed = (not exists) or now != rec["mtime"] or _file_sha256(p) != rec["sha256"]
        rep["sources"].append({"path": src, "exists": exists, "changed": changed,
                               "mtime_at_build": rec["mtime"], "mtime_now": now})
        if changed:
            changed_names.append(p.name)
    rep["stale"] = bool(changed_names)
    rep["stale_reason"] = ("sources changed since build: " + ", ".join(changed_names)
                           if changed_names else None)
    if not changed_names:
        rep["load_provenance"] = "host-local"
    else:
        rec_sha = manifest.get("corpus_sha256")
        rep["load_provenance"] = ("portable-sidecar"
                                  if rec_sha and _file_sha256(cp) == rec_sha else "unloadable")
    return rep


__all__ = ["SPORTS", "DATE_COL", "POSITIONAL_ORDER", "SOCCER_LEAKY_COLUMNS",
           "StaleCorpusError", "build_gate_corpus", "load_gate_corpus", "freshness_report"]
