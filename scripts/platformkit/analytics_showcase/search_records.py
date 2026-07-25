"""Flat search-record index powering the analytics site's Cmd+K command palette.

One record per navigable destination: entity cards (from the 7 atlas
manifests), analytic modules (from site_manifest.json), curated findings
pages, and top-level pages. Reads ONLY committed artifacts already in
scripts/platformkit/analytics_showcase/out/ -- zero new data.

Entity slugs/hrefs MUST match the real webapp routes, so the slug rule here
is copied byte-for-byte from entity_percentiles.py's _entity_slug/_slugify --
do not reimplement it differently.

Usage:
    python -m scripts.platformkit.analytics_showcase.search_records
    python -m scripts.platformkit.analytics_showcase.search_records --check
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
OUT_DIR = os.path.join(SHOWCASE, "out")
OUT_JSON = os.path.join(OUT_DIR, "search_records.json")
SITE_MANIFEST = os.path.join(OUT_DIR, "site_manifest.json")

# slug -> (manifest filename, display label). Same 7 packs, same slugs as
# entity_percentiles.py's PACKS -- these are the webapp route params.
PACKS = {
    "nba_players": ("atlas_nba_manifest.json", "NBA players"),
    "nba_teams": ("atlas_nba_teams_manifest.json", "NBA teams"),
    "mlb_batters": ("atlas_mlb_batters_manifest.json", "MLB batters"),
    "mlb_pitch": ("atlas_mlb_pitch_manifest.json", "MLB pitch types"),
    "soccer": ("atlas_soccer_manifest.json", "Soccer teams"),
    "tennis": ("atlas_tennis_manifest.json", "Tennis players"),
    "calibration": ("atlas_calibration_manifest.json", "Calibration segments"),
}

FINDINGS = [
    ("Retractions", "/analytics/findings/retraction"),
    ("Effective sample size", "/analytics/findings/effective-sample-size"),
    ("Verdict flips", "/analytics/findings/verdict-flips"),
    ("MLB leaderboards", "/analytics/findings/mlb-leaderboards"),
    ("Tennis findings", "/analytics/findings/tennis"),
    ("NBA momentum, tested", "/analytics/findings/nba-momentum"),
    ("The fourth-quarter shift", "/analytics/findings/q4-shift"),
    ("Shrinkage", "/analytics/findings/shrinkage"),
    ("Reliability diagrams", "/analytics/findings/reliability"),
    ("The life of a forecast", "/analytics/findings/forecast-life"),
    ("Soccer home advantage", "/analytics/findings/soccer-home-advantage"),
    ("Bookmaker accuracy", "/analytics/findings/bookmaker-accuracy"),
    ("Rim deterrence", "/analytics/findings/rim-deterrence"),
    ("League parity", "/analytics/findings/league-parity"),
    ("Lineup synergy", "/analytics/findings/lineup-synergy"),
    ("Favorite-longshot bias", "/analytics/findings/favorite-longshot"),
    ("Findings hub", "/analytics/findings"),
]

PAGES = [
    ("Home", "/analytics"),
    ("Forecaster", "/analytics/forecaster"),
    ("The Loop", "/analytics/the-loop"),
    ("Novel Stats", "/analytics/novel"),
    ("Explore", "/analytics/browse"),
    ("Entities", "/analytics/players"),
    ("Ask Scout", "/analytics/ask"),
    ("About", "/analytics/about"),
    ("Explainers", "/analytics/explainers"),
]


def _slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def _entity_slug(entry, seen):
    """Byte-identical to entity_percentiles._entity_slug: basename of
    card_path w/ ext stripped; on collision fall back to slugify(entity)."""
    card_path = entry.get("card_path") or ""
    base = re.split(r"[/\\]", card_path)[-1]
    stem = os.path.splitext(base)[0]
    slug = stem if stem not in seen else _slugify(entry.get("entity"))
    seen.add(slug)
    return slug


def _entity_title(entry):
    key_numbers = entry.get("key_numbers") or {}
    full_name = key_numbers.get("team_full_name")
    if isinstance(full_name, str) and full_name.strip():
        return full_name
    name = entry.get("entity") or ""
    if name.startswith("pitch_type:"):
        name = "pitch_type " + name[len("pitch_type:"):]
    elif name.startswith("team:"):
        name = "team " + name[len("team:"):]
    return name.replace("_", " ")


def _entity_records():
    records = []
    counts = 0
    for pack_slug, (manifest_fn, label) in PACKS.items():
        path = os.path.join(OUT_DIR, manifest_fn)
        entries = json.loads(open(path, encoding="utf-8").read())["entries"]
        seen = set()
        for entry in entries:
            slug = _entity_slug(entry, seen)
            title = _entity_title(entry)
            records.append({
                "id": f"entity:{pack_slug}:{slug}",
                "title": title,
                "subtitle": label,
                "href": f"/analytics/players/{pack_slug}/{slug}",
                "type": "entity",
                "keywords": [pack_slug.split("_")[0], label],
            })
            counts += 1
    return records


def _module_records():
    manifest = json.loads(open(SITE_MANIFEST, encoding="utf-8").read())
    records = []
    for mod in manifest["modules"]:
        records.append({
            "id": f"module:{mod['id']}",
            "title": mod["title"],
            "subtitle": "Analytic",
            "href": f"/analytics/m/{mod['id']}",
            "type": "module",
            "keywords": [],
        })
    return records


def _finding_records():
    records = []
    for title, href in FINDINGS:
        records.append({
            "id": f"finding:{_slugify(title)}",
            "title": title,
            "subtitle": "Findings",
            "href": href,
            "type": "finding",
            "keywords": [],
        })
    return records


def _page_records():
    records = []
    for title, href in PAGES:
        records.append({
            "id": f"page:{_slugify(title)}",
            "title": title,
            "subtitle": "Page",
            "href": href,
            "type": "page",
            "keywords": [],
        })
    return records


def build():
    entities = _entity_records()
    modules = _module_records()
    findings = _finding_records()
    pages = _page_records()
    records = entities + modules + findings + pages

    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate record id"

    counts = {
        "entity": len(entities),
        "module": len(modules),
        "finding": len(findings),
        "page": len(pages),
    }
    counts["total"] = len(records)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "counts": counts,
        "records": records,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _print_summary(payload):
    c = payload["counts"]
    print(f"search_records: entity={c['entity']} module={c['module']} "
          f"finding={c['finding']} page={c['page']} total={c['total']}")


def check():
    assert os.path.exists(OUT_JSON), f"missing {OUT_JSON}"
    payload = json.loads(open(OUT_JSON, encoding="utf-8").read())
    counts = payload["counts"]
    records = payload["records"]

    assert counts["total"] == sum(v for k, v in counts.items() if k != "total"), counts
    assert counts["total"] == len(records), (counts["total"], len(records))
    assert counts["total"] >= 1600, counts["total"]

    ids = set()
    for r in records:
        assert r["title"] and r["title"].strip(), f"empty title: {r}"
        assert r["href"].startswith("/analytics"), f"bad href: {r}"
        assert "//" not in r["href"], f"double slash in href: {r}"
        assert " " not in r["href"], f"space in href: {r}"
        assert r["id"] not in ids, f"duplicate id: {r['id']}"
        ids.add(r["id"])
        if r["type"] == "entity":
            segments = [s for s in r["href"].split("/") if s]
            assert len(segments) == 4, f"entity href not 4 segments: {r['href']}"

    # Guard against a real bug that shipped: a new findings/<slug>/page.tsx added
    # without a matching FINDINGS entry -> the page is unreachable from Cmd+K and
    # absent from the sitemap (which is derived from this index). Every findings
    # page dir on disk MUST have a finding record. webapp/ is committed source, so
    # this stays clone-safe.
    findings_dir = os.path.join(
        ROOT, "webapp", "app", "(analytics)", "analytics", "findings")
    if os.path.isdir(findings_dir):
        hrefs = {r["href"] for r in records}
        for name in sorted(os.listdir(findings_dir)):
            sub = os.path.join(findings_dir, name)
            if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "page.tsx")):
                want = f"/analytics/findings/{name}"
                assert want in hrefs, (
                    f"findings page {want} has no search record -- add it to "
                    f"FINDINGS in search_records.py (else it is missing from "
                    f"Cmd+K and the sitemap)")

    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        _print_summary(build())
