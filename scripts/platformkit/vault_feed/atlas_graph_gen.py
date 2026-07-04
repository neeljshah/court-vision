"""atlas_graph_gen -- STAGING ONLY generator for graph hub notes from the 5
per-sport truth-spec JSONs under docs/research/intel-layer/.

Reads:
  - docs/research/intel-layer/{basketball,mlb,soccer_intl,tennis,wnba}_truth_spec.json

Each spec exposes dimension-like entries (the "dimension_map" the intel program
doc refers to):
  - basketball uses `factors` (field: `pillar`, plus `file`/`coverage_pct` for REAL,
    absence of `file` for GAP; no fallback-only distinction beyond that list)
  - mlb / soccer_intl / tennis / wnba use `dimensions` (field: `aspect_group`,
    `source_file`+`coverage` for REAL/THIN, `gap_source` for GAP)

Writes:
  - data/cache/vault_feed_staging/atlas_hubs/<sport>_<aspect_group>.md
    one hub note per (sport, aspect_group) pair; each dimension becomes a
    [[wikilink]] leaf tagged REAL / THIN / GAP.
  - Cross-sport links: aspect_groups that share a normalized name (e.g. "team",
    "team_strength" -> team-strength bucket) get a "Related hubs" section
    linking the other sports' hub notes for the same shared concept.

Deterministic + idempotent: no wall-clock timestamps in body text.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_DIR = REPO_ROOT / "docs/research/intel-layer"
OUT_DIR = REPO_ROOT / "data/cache/vault_feed_staging/atlas_hubs"

SPEC_FILES = {
    "basketball_nba": "basketball_truth_spec.json",
    "mlb": "mlb_truth_spec.json",
    "soccer_intl": "soccer_intl_truth_spec.json",
    "tennis": "tennis_truth_spec.json",
    "wnba": "wnba_truth_spec.json",
}

# Shared kernel concepts across sports -- normalize aspect_group names into a
# shared bucket for cross-sport links (extend as more sports adopt the labels).
SHARED_BUCKETS = {
    "team": "team_strength",
    "team_strength": "team_strength",
    "rest_schedule": "rest_schedule_density",
    "schedule_density": "rest_schedule_density",
    "travel": "travel_altitude",
    "altitude": "travel_altitude",
    "in_game_state": "in_game_conditioning",
    "ingame_state": "in_game_conditioning",
}


def _load_spec(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _basketball_entries(spec: dict) -> list:
    """Normalize `factors` (+ fallback_only_factors) into dimension-like dicts."""
    out = []
    for f in spec.get("factors", []):
        out.append({
            "name": f["factor"],
            "aspect_group": f.get("pillar", "UNGROUPED").lower(),
            "status": "REAL" if f.get("file") else "GAP",
            "detail": f.get("file") or f.get("column", ""),
        })
    for f in spec.get("fallback_only_factors", []):
        out.append({
            "name": f.get("factor", "unknown"),
            "aspect_group": (f.get("pillar") or "UNGROUPED").lower(),
            "status": "THIN",
            "detail": f.get("file") or f.get("column", ""),
        })
    return out


def _generic_entries(spec: dict) -> list:
    """Normalize `dimensions` (mlb/soccer/tennis/wnba schema)."""
    out = []
    for d in spec.get("dimensions", []):
        if "gap_source" in d:
            status = "GAP"
            detail = d["gap_source"]
        elif "source_file" in d:
            coverage = str(d.get("coverage", ""))
            status = "THIN" if "PARTIALLY" in coverage.upper() or "partial" in coverage.lower() else "REAL"
            detail = f"{d['source_file']} :: {d.get('source_column', '')}"
        else:
            status = "GAP"
            detail = ""
        out.append({
            "name": d["name"],
            "aspect_group": d.get("aspect_group", "ungrouped"),
            "status": status,
            "detail": detail,
        })
    return out


def build_atlas_hubs(spec_dir: Path = SPEC_DIR, out_dir: Path = OUT_DIR) -> dict:
    """Generate hub notes. Returns {hub_filename: n_leaves}."""
    sport_entries: dict = {}
    for sport, fname in SPEC_FILES.items():
        spec = _load_spec(spec_dir / fname)
        if spec is None:
            continue
        entries = _basketball_entries(spec) if sport == "basketball_nba" else _generic_entries(spec)
        sport_entries[sport] = entries

    if not sport_entries:
        return {}

    # group by (sport, aspect_group)
    hubs: dict = {}
    for sport, entries in sport_entries.items():
        for e in entries:
            key = (sport, e["aspect_group"])
            hubs.setdefault(key, []).append(e)

    # build shared-bucket -> [(sport, aspect_group)] index for cross-sport links
    bucket_index: dict = {}
    for (sport, aspect_group) in hubs:
        bucket = SHARED_BUCKETS.get(aspect_group)
        if bucket:
            bucket_index.setdefault(bucket, []).append((sport, aspect_group))

    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for (sport, aspect_group), entries in sorted(hubs.items()):
        entries = sorted(entries, key=lambda e: e["name"])
        fname = f"{sport}_{aspect_group}.md"
        lines = [f"## Atlas Hub: {sport} / {aspect_group}", ""]
        for e in entries:
            lines.append(f"- [[{e['name']}]] `{e['status']}` -- {e['detail']}")

        bucket = SHARED_BUCKETS.get(aspect_group)
        related = [p for p in bucket_index.get(bucket, []) if p != (sport, aspect_group)] if bucket else []
        if related:
            lines.append("")
            lines.append("### Related hubs (shared kernel concept)")
            for (rsport, raspect) in sorted(related):
                lines.append(f"- [[{rsport}_{raspect}]]")
        lines.append("")
        (out_dir / fname).write_text("\n".join(lines), encoding="utf-8", newline="\n")
        counts[fname] = len(entries)
    return counts


if __name__ == "__main__":
    counts = build_atlas_hubs()
    print(f"atlas_hubs written: {len(counts)} hub files, "
          f"{sum(counts.values())} total leaves")
