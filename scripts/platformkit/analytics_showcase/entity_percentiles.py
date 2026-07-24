"""Within-pack percentile ranks for every numeric key_number on all 1,549
atlas entity cards.

Reads ONLY the 7 committed atlas manifests already in
scripts/platformkit/analytics_showcase/out/. Zero new data, zero new
science -- this is a pure re-rank of numbers that already exist on disk.

For each pack (nba_players, nba_teams, mlb_batters, mlb_pitch, soccer,
tennis, calibration), and for each numeric key_number field with at least
MIN_N_RANKED entities carrying a value, computes a 0..100 percentile:
"higher than X% of the pack". No good/bad direction is implied anywhere.

Usage:
    python -m scripts.platformkit.analytics_showcase.entity_percentiles
    python -m scripts.platformkit.analytics_showcase.entity_percentiles --check
"""
import json
import math
import os
import re
import statistics
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
OUT_DIR = os.path.join(SHOWCASE, "out")
OUT_JSON = os.path.join(OUT_DIR, "entity_percentiles.json")

# slug -> manifest filename. Slugs are BINDING -- must match the webapp
# route param [pack] exactly.
PACKS = {
    "nba_players": "atlas_nba_manifest.json",
    "nba_teams": "atlas_nba_teams_manifest.json",
    "mlb_batters": "atlas_mlb_batters_manifest.json",
    "mlb_pitch": "atlas_mlb_pitch_manifest.json",
    "soccer": "atlas_soccer_manifest.json",
    "tennis": "atlas_tennis_manifest.json",
    "calibration": "atlas_calibration_manifest.json",
}

MIN_N_RANKED = 30
METHOD = (
    "Within-pack rank of each numeric key_number across the committed atlas "
    "manifests. percentile = round(100 * (n_below + 0.5*n_tied) / n_ranked). "
    "Higher raw value always maps to a higher percentile; no good/bad "
    "direction is implied. Fields ranked in fewer than 30 entities are omitted."
)


def _slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s


def _entity_slug(entry, seen):
    """Must byte-match webapp/app/(analytics)/analytics/players/[pack]/[slug]/page.tsx:
    slug = basename of card_path (split on / or \\), trailing .ext stripped;
    on collision with a prior slug in this pack, fall back to slugify(entity).
    """
    card_path = entry.get("card_path") or ""
    base = re.split(r"[/\\]", card_path)[-1]
    stem = os.path.splitext(base)[0]
    slug = stem if stem not in seen else _slugify(entry.get("entity"))
    seen.add(slug)
    return slug


def _is_usable_number(v):
    if isinstance(v, bool):
        return False
    if not isinstance(v, (int, float)):
        return False
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return False
    return True


def _pack_slugs(entries):
    """All slugs for a pack's entries, in order, via the binding slug rule."""
    seen = set()
    return [_entity_slug(e, seen) for e in entries]


def _percentiles(values_by_slug):
    values = list(values_by_slug.values())
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    pct_by_slug = {}
    for slug, v in values_by_slug.items():
        below = bisect_left(sorted_vals, v)
        tied = bisect_right(sorted_vals, v) - below
        pct_by_slug[slug] = int(round(100 * (below + 0.5 * tied) / n))
    stat = {
        "n_ranked": n,
        "min": sorted_vals[0],
        "median": statistics.median(sorted_vals),
        "max": sorted_vals[-1],
    }
    return pct_by_slug, stat


def _build_pack(manifest_fn):
    path = os.path.join(OUT_DIR, manifest_fn)
    entries = json.loads(open(path, encoding="utf-8").read())["entries"]

    seen = set()
    field_values = {}  # field -> {slug: value}
    for entry in entries:
        slug = _entity_slug(entry, seen)
        for k, v in (entry.get("key_numbers") or {}).items():
            if k.endswith("_id") or k == "team_full_name":
                continue
            if not _is_usable_number(v):
                continue
            field_values.setdefault(k, {})[slug] = v

    fields = {}
    skipped_low_n = []
    entities = {}
    for k in sorted(field_values):
        vals = field_values[k]
        if len(vals) < MIN_N_RANKED:
            skipped_low_n.append(k)
            continue
        pct_by_slug, stat = _percentiles(vals)
        fields[k] = stat
        for slug, pct in pct_by_slug.items():
            entities.setdefault(slug, {})[k] = pct

    return {
        "manifest": manifest_fn,
        "n_in_pack": len(entries),
        "fields": fields,
        "skipped_low_n": skipped_low_n,
        "entities": entities,
    }


def build():
    packs = {}
    n_entities = 0
    n_values = 0
    for slug, manifest_fn in PACKS.items():
        pack = _build_pack(manifest_fn)
        packs[slug] = pack
        n_entities += pack["n_in_pack"]
        n_values += sum(len(v) for v in pack["entities"].values())

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "method": METHOD,
        "min_n_ranked": MIN_N_RANKED,
        "n_packs": len(PACKS),
        "n_entities": n_entities,
        "n_values": n_values,
        "packs": packs,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _print_summary(payload):
    print(f"entity_percentiles: n_entities={payload['n_entities']} n_values={payload['n_values']}")
    for slug, pack in payload["packs"].items():
        print(f"  {slug}: n_in_pack={pack['n_in_pack']} n_fields={len(pack['fields'])} "
              f"skipped_low_n={pack['skipped_low_n']}")


def check():
    assert os.path.exists(OUT_JSON), f"missing {OUT_JSON}"
    payload = json.loads(open(OUT_JSON, encoding="utf-8").read())
    assert payload["n_packs"] == 7, payload["n_packs"]
    assert len(payload["packs"]) == 7, list(payload["packs"])

    n_values_seen = 0
    for slug, pack in payload["packs"].items():
        manifest_path = os.path.join(OUT_DIR, pack["manifest"])
        entries = json.loads(open(manifest_path, encoding="utf-8").read())["entries"]
        valid_slugs = set(_pack_slugs(entries))
        for ent_slug, field_map in pack["entities"].items():
            assert ent_slug in valid_slugs, f"{slug}: unknown entity slug {ent_slug!r}"
            for field, pct in field_map.items():
                assert isinstance(pct, int) and not isinstance(pct, bool), f"{slug}.{field}: {pct!r} not int"
                assert 0 <= pct <= 100, f"{slug}.{field}: {pct} out of range"
                n_values_seen += 1
        for field, stat in pack["fields"].items():
            for key in ("min", "median", "max"):
                v = stat[key]
                assert not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))), f"{slug}.{field}.{key} nan/inf"

    assert n_values_seen == payload["n_values"], (n_values_seen, payload["n_values"])
    assert payload["n_values"] > 10000, payload["n_values"]
    print("OK")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        _print_summary(p)
