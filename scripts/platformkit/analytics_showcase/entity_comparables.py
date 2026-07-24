"""Most-similar-in-this-pack for every atlas entity card.

Reads ONLY the 7 committed atlas manifests already in
scripts/platformkit/analytics_showcase/out/. Zero new data, zero new
science -- cosine similarity over the numeric key_numbers every entity in a
pack has in common, after z-scoring each field within the pack.

For each pack, the common field set is every numeric key_number (same
selection rule as entity_percentiles: int/float not bool, key does not match
`_id$`, key != "team_full_name") present on EVERY entity in the pack. A pack
is skipped if fewer than MIN_FIELDS common fields survive or fewer than
MIN_ENTITIES entities exist. Zero-variance fields are dropped before scoring.

Usage:
    python -m scripts.platformkit.analytics_showcase.entity_comparables
    python -m scripts.platformkit.analytics_showcase.entity_comparables --check
"""
import json
import math
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
OUT_DIR = os.path.join(SHOWCASE, "out")
OUT_JSON = os.path.join(OUT_DIR, "entity_comparables.json")

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

MIN_FIELDS = 3
MIN_ENTITIES = 10
TOP_N = 5
METHOD = (
    "Cosine similarity on z-scored key_numbers, restricted per pack to fields "
    "every entity in that pack carries. Similarity is over the listed fields "
    "ONLY and implies nothing about quality or future performance."
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


def _pack_slugs(entries):
    """All slugs for a pack's entries, in order, via the binding slug rule."""
    seen = set()
    return [_entity_slug(e, seen) for e in entries]


def _is_usable_number(v):
    if isinstance(v, bool):
        return False
    if not isinstance(v, (int, float)):
        return False
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return False
    return True


def _name_for(entry):
    """Mirrors nameFor() in webapp/app/(analytics)/analytics/players/[pack]/[slug]/page.tsx."""
    full = (entry.get("key_numbers") or {}).get("team_full_name")
    if isinstance(full, str) and full:
        return full
    entity = entry.get("entity") or ""
    entity = re.sub(r"^(pitch_type|team):", r"\1 ", entity)
    return entity.replace("_", " ")


def _build_pack(pack_slug, manifest_fn):
    path = os.path.join(OUT_DIR, manifest_fn)
    entries = json.loads(open(path, encoding="utf-8").read())["entries"]
    n_in_pack = len(entries)

    seen = set()
    slugs = []
    names = {}
    key_numbers = {}
    for entry in entries:
        slug = _entity_slug(entry, seen)
        slugs.append(slug)
        names[slug] = _name_for(entry)
        key_numbers[slug] = entry.get("key_numbers") or {}

    if n_in_pack < MIN_ENTITIES:
        return None, {"pack": pack_slug, "reason": "too few entities", "n_entities": n_in_pack, "n_common_fields": 0}

    # candidate fields: usable-number keys present in EVERY entity's key_numbers,
    # and usable-number for every one of them.
    candidate_keys = None
    for slug in slugs:
        kn = key_numbers[slug]
        this_keys = {k for k, v in kn.items() if not k.endswith("_id") and k != "team_full_name" and _is_usable_number(v)}
        candidate_keys = this_keys if candidate_keys is None else (candidate_keys & this_keys)
    candidate_keys = sorted(candidate_keys or [])

    if len(candidate_keys) < MIN_FIELDS:
        return None, {"pack": pack_slug, "reason": "too few common fields", "n_entities": n_in_pack, "n_common_fields": len(candidate_keys)}

    # z-score each candidate field across the pack; drop zero-variance fields.
    fields_used = []
    dropped_zero_variance = []
    z = {slug: {} for slug in slugs}
    for k in candidate_keys:
        vals = [float(key_numbers[slug][k]) for slug in slugs]
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n
        std = math.sqrt(var)
        if std == 0.0:
            dropped_zero_variance.append(k)
            continue
        fields_used.append(k)
        for slug, v in zip(slugs, vals):
            z[slug][k] = (v - mean) / std

    if len(fields_used) < MIN_FIELDS:
        return None, {"pack": pack_slug, "reason": "too few fields after dropping zero-variance", "n_entities": n_in_pack, "n_common_fields": len(fields_used)}

    vecs = {slug: [z[slug][k] for k in fields_used] for slug in slugs}
    norms = {slug: math.sqrt(sum(x * x for x in vecs[slug])) for slug in slugs}

    entities = {}
    for a in slugs:
        va, na = vecs[a], norms[a]
        scored = []
        for b in slugs:
            if b == a:
                continue
            vb, nb = vecs[b], norms[b]
            if na == 0.0 or nb == 0.0:
                cos = 0.0
            else:
                dot = sum(x * y for x, y in zip(va, vb))
                cos = dot / (na * nb)
            scored.append((b, cos))
        scored.sort(key=lambda t: t[1], reverse=True)
        top = scored[:TOP_N]
        worst = min(scored, key=lambda t: t[1])
        entities[a] = {
            "similar": [{"slug": s, "name": names[s], "score": round(c, 3)} for s, c in top],
            "antipode": {"slug": worst[0], "name": names[worst[0]], "score": round(worst[1], 3)},
        }

    pack = {
        "n_in_pack": n_in_pack,
        "fields_used": fields_used,
        "dropped_zero_variance": dropped_zero_variance,
        "entities": entities,
    }
    return pack, None


def build():
    packs = {}
    skipped_packs = []
    n_entities = 0
    for pack_slug, manifest_fn in PACKS.items():
        pack, skip = _build_pack(pack_slug, manifest_fn)
        if skip is not None:
            skipped_packs.append(skip)
            continue
        packs[pack_slug] = pack
        n_entities += pack["n_in_pack"]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "method": METHOD,
        "min_fields": MIN_FIELDS,
        "min_entities": MIN_ENTITIES,
        "n_packs_covered": len(packs),
        "n_entities": n_entities,
        "skipped_packs": skipped_packs,
        "packs": packs,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _print_summary(payload):
    print(f"entity_comparables: n_packs_covered={payload['n_packs_covered']} n_entities={payload['n_entities']}")
    for slug, pack in payload["packs"].items():
        print(f"  {slug}: n_in_pack={pack['n_in_pack']} fields_used={pack['fields_used']} "
              f"dropped_zero_variance={pack['dropped_zero_variance']}")
    for skip in payload["skipped_packs"]:
        print(f"  SKIPPED {skip['pack']}: {skip['reason']} (n_entities={skip['n_entities']} n_common_fields={skip['n_common_fields']})")


def check():
    assert os.path.exists(OUT_JSON), f"missing {OUT_JSON}"
    payload = json.loads(open(OUT_JSON, encoding="utf-8").read())

    for pack_slug, pack in payload["packs"].items():
        manifest_fn = PACKS[pack_slug]
        manifest_path = os.path.join(OUT_DIR, manifest_fn)
        entries = json.loads(open(manifest_path, encoding="utf-8").read())["entries"]
        valid_slugs = set(_pack_slugs(entries))
        assert valid_slugs == set(pack["entities"]), f"{pack_slug}: entity set mismatch"

        n_in_pack = pack["n_in_pack"]
        expected_n = min(TOP_N, n_in_pack - 1)
        for ent_slug, rec in pack["entities"].items():
            similar = rec["similar"]
            antipode = rec["antipode"]
            assert len(similar) == expected_n, f"{pack_slug}.{ent_slug}: expected {expected_n} similar, got {len(similar)}"

            prev_score = None
            for item in similar:
                assert item["slug"] in valid_slugs, f"{pack_slug}.{ent_slug}: unknown similar slug {item['slug']!r}"
                assert item["slug"] != ent_slug, f"{pack_slug}.{ent_slug}: lists itself as similar"
                score = item["score"]
                assert isinstance(score, float) and -1.0 <= score <= 1.0, f"{pack_slug}.{ent_slug}: score {score!r} out of range"
                if prev_score is not None:
                    assert score <= prev_score, f"{pack_slug}.{ent_slug}: similar scores not non-increasing"
                prev_score = score

            assert antipode["slug"] in valid_slugs, f"{pack_slug}.{ent_slug}: unknown antipode slug {antipode['slug']!r}"
            assert antipode["slug"] != ent_slug, f"{pack_slug}.{ent_slug}: lists itself as antipode"
            a_score = antipode["score"]
            assert isinstance(a_score, float) and -1.0 <= a_score <= 1.0, f"{pack_slug}.{ent_slug}: antipode score {a_score!r} out of range"
            if similar:
                assert a_score <= similar[-1]["score"], f"{pack_slug}.{ent_slug}: antipode score exceeds last similar score"

    print("OK")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        _print_summary(p)
