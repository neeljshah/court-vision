"""domains.tennis.atlas_persist_manifest -- writes all four tennis atlas
layers to data/cache/tennis_atlas/*.parquet plus a manifest.json (lane
tennis-persist, program v3).

Composes the four persist_* functions (atlas_persist.persist_playstyles /
persist_h2h, atlas_persist_layers.persist_scouting / persist_surface_splits)
-- never recomputes their aggregation logic -- and records
{layer, rows, cols, source, built_at} per layer. built_at is the CORPUS's
own max match date (matches.parquet's `date` column), NEVER wall-clock, so
the manifest is reproducible from a fixed corpus snapshot.

Public API:
    build_and_persist(cache_dir=None, corpus_dir=None, vault_tennis_dir=None) -> dict
    write_manifest(cache_dir=None, corpus_dir=None, vault_tennis_dir=None) -> dict

A layer whose source is missing/errors is recorded with rows=0 and an
honest error string -- never silently dropped from the manifest.

NETWORK: zero. F5-clean: stdlib + pandas + domains.tennis.* only.

CLI:
    python -m domains.tennis.atlas_persist_manifest
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Optional

import pandas as pd

from domains.tennis.atlas_persist import CORPUS_ID, persist_h2h, persist_playstyles
from domains.tennis.atlas_persist_layers import (
    DEFAULT_CORPUS,
    _corpus_max_date,
    persist_scouting,
    persist_surface_splits,
)

_REPO_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR: pathlib.Path = _REPO_ROOT / "data" / "cache" / "tennis_atlas"


def build_and_persist(
    cache_dir: Optional[pathlib.Path] = None,
    corpus_dir: Optional[pathlib.Path] = None,
    vault_tennis_dir: Optional[pathlib.Path] = None,
) -> dict[str, Any]:
    """Persist all four layers to cache_dir (default DEFAULT_CACHE_DIR) and
    return the manifest dict (NOT yet written to disk -- see write_manifest).
    Never raises: a layer whose source is missing is recorded with rows=0
    and an honest error note, never silently omitted from the manifest.
    """
    cache_dir = pathlib.Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    corpus_dir = pathlib.Path(corpus_dir) if corpus_dir is not None else DEFAULT_CORPUS
    matches = pd.read_parquet(corpus_dir / "matches.parquet")
    built_at = _corpus_max_date(matches)

    layers: list[dict[str, Any]] = []

    def _run(layer_name: str, fn, out_path: pathlib.Path, **kwargs) -> None:
        try:
            result = fn(out_path, as_of=built_at, **kwargs)
            try:
                rel_source = str(result.out_path.resolve().relative_to(_REPO_ROOT)).replace("\\", "/")
            except ValueError:
                # out_path lives outside the repo tree (e.g. a tmp_path in tests) --
                # fall back to the absolute path rather than raising.
                rel_source = str(result.out_path.resolve()).replace("\\", "/")
            layers.append({
                "layer": layer_name,
                "rows": result.row_count,
                "cols": len(result.columns),
                "source": rel_source,
                "built_at": built_at,
                "error": None,
            })
        except Exception as e:  # noqa: BLE001 -- an honest per-layer gap, not a crash
            layers.append({
                "layer": layer_name, "rows": 0, "cols": 0, "source": None,
                "built_at": built_at, "error": str(e),
            })

    _run("playstyles", persist_playstyles, cache_dir / "playstyles.parquet", corpus_dir=corpus_dir)
    _run("h2h", persist_h2h, cache_dir / "h2h.parquet", corpus_dir=corpus_dir)
    _run("scouting", persist_scouting, cache_dir / "scouting.parquet", vault_tennis_dir=vault_tennis_dir)
    _run("surface_splits", persist_surface_splits, cache_dir / "surface_splits.parquet", corpus_dir=corpus_dir)

    return {
        "component": "tennis_atlas_persist",
        "built_at": built_at,
        "corpus_id": CORPUS_ID,
        "layers": layers,
    }


def write_manifest(
    cache_dir: Optional[pathlib.Path] = None,
    corpus_dir: Optional[pathlib.Path] = None,
    vault_tennis_dir: Optional[pathlib.Path] = None,
) -> dict[str, Any]:
    """build_and_persist() then atomically write manifest.json into cache_dir."""
    cache_dir = pathlib.Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    manifest = build_and_persist(cache_dir=cache_dir, corpus_dir=corpus_dir, vault_tennis_dir=vault_tennis_dir)

    manifest_path = cache_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="ascii", errors="strict") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True, sort_keys=True)
    return manifest


def _main() -> int:
    m = write_manifest()
    for layer in m["layers"]:
        print(f"{layer['layer']}: rows={layer['rows']} cols={layer['cols']} "
              f"source={layer['source']} error={layer['error']}")
    print(f"manifest -> {DEFAULT_CACHE_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
