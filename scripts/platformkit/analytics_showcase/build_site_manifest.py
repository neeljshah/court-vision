"""Website data-layer builder for the analytics showcase.

Scans out/*.json (analytics modules) + out/atlas_*_manifest.json + docs/img/*.png
and emits out/site_manifest.json: one honest row per analytics module for the
website to render, plus top-level counts. Paths are REPO-RELATIVE only (clone-safe;
never a box-local absolute like C:/Users/neelj/...).

Run:  python -m scripts.platformkit.analytics_showcase.build_site_manifest
Check: python -m scripts.platformkit.analytics_showcase.build_site_manifest --check
"""
import glob
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_OUT = _REPO / "scripts" / "platformkit" / "analytics_showcase" / "out"
_IMG = _REPO / "docs" / "img"
_EVID = _REPO / "docs" / "evidence"
_MANIFEST = _OUT / "site_manifest.json"

# Not analytics modules: atlas manifests feed atlas_card_count; these are meta.
# Artifacts that live in out/ but are not analytics modules: build tooling
# output, indexes, and render ledgers. They would render as empty catalog cards.
_SKIP = {
    "site_manifest.json",
    "check_all_report.json",
    "claims_corpus_meta.json",
    "brand_logo_variants.json",
    "evidence_index.json",
    "share_ledger.json",
    # Per-entity percentile ranks feeding the entity-card bars, not a catalog module.
    "entity_percentiles.json",
    # Cross-module joins layered onto entity cards, not a catalog module.
    "entity_joins.json",
    # Within-pack nearest-neighbour comparables layered onto entity cards, not a catalog module.
    "entity_comparables.json",
    # Flat search-record index for the Cmd+K palette, not a catalog module.
    "search_records.json",
}

# Fields, in priority order, whose value is an honest one-line summary of a module.
# Short verdict/headline/label first; longer notes as fallback.
_ONE_LINE_KEYS = (
    "headline", "verdict", "label", "note", "honest_note",
    "summary", "method", "methodology",
)


def _rel(path):
    """Repo-relative POSIX string, or None. Never leaks an absolute box path."""
    if path is None:
        return None
    p = Path(path)
    try:
        return str(p.relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        return None


def _first_str(data):
    """First honest one-liner from a module's own fields; '' if none."""
    if not isinstance(data, dict):
        return ""
    for k in _ONE_LINE_KEYS:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            s = " ".join(v.split())
            return s if len(s) <= 240 else s[:237] + "..."
    return ""


def _as_of(data):
    if not isinstance(data, dict):
        return None
    for k in ("as_of", "generated_at", "generated_from"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _title(mod_id):
    return mod_id.replace("_", " ").title()


def _evidence_index():
    """Map artifact filename -> repo-relative evidence page path (first match)."""
    idx = {}
    for md in sorted(_EVID.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        # every out/<name>.json referenced by this page
        for name in re.findall(r"out/([A-Za-z0-9_]+)\.json", text):
            idx.setdefault(name, _rel(md))
    return idx


def _atlas_card_count():
    total = 0
    for f in sorted(_OUT.glob("atlas_*_manifest.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        n = d.get("n_entries")
        if isinstance(n, int):
            total += n
        elif isinstance(d.get("entries"), list):
            total += len(d["entries"])
    return total


def _checks_green():
    """From check_all_report.json: {green: bool, pass, total}."""
    p = _OUT / "check_all_report.json"
    if not p.exists():
        return {"green": None, "pass": 0, "total": 0}
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"green": None, "pass": 0, "total": 0}
    if not isinstance(rows, list):
        return {"green": None, "pass": 0, "total": 0}
    passed = sum(1 for r in rows if isinstance(r, dict) and r.get("status") == "PASS")
    total = len(rows)
    return {"green": total > 0 and passed == total, "pass": passed, "total": total}


def _module_status(data, one_line):
    """ok if it has real content; partial if it self-reports missing/skipped data."""
    if not isinstance(data, dict):
        # a bare list (e.g. some rollups) still counts as built content
        return "ok" if data else "not_buildable"
    if data.get("skipped") or data.get("no_data") or data.get("status") == "no_data":
        return "partial"
    return "ok" if data else "not_buildable"


def build():
    evid = _evidence_index()
    modules = []
    for f in sorted(_OUT.glob("*.json")):
        if f.name in _SKIP or f.name.startswith("atlas_"):
            continue
        mod_id = f.stem
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            status = _module_status(data, None)
            one_line = _first_str(data)
        except (OSError, ValueError):
            data, status, one_line = None, "not_buildable", ""
        png = _IMG / f"{mod_id}.png"
        modules.append({
            "id": mod_id,
            "title": _title(mod_id),
            "one_line": one_line,
            "out_path": _rel(f),
            "chart_path": _rel(png) if png.exists() else None,
            "status": status,
            "edge_claimed": False,  # rail: this repo never claims edge
            "as_of": _as_of(data),
            "evidence_page": evid.get(mod_id),
        })
    return {
        "generated_from": _rel(_OUT),
        "module_count": len(modules),
        "atlas_card_count": _atlas_card_count(),
        "checks_green": _checks_green(),
        "edge_claimed": False,
        "modules": modules,
    }


def _validate(m):
    assert isinstance(m, dict), "manifest is not an object"
    for k in ("generated_from", "module_count", "atlas_card_count",
              "checks_green", "modules"):
        assert k in m, f"missing top-level key: {k}"
    assert m["module_count"] == len(m["modules"]), "module_count mismatch"
    assert m["edge_claimed"] is False, "edge_claimed must be False"
    abs_pat = re.compile(r"^[A-Za-z]:[\\/]|^/")
    for row in m["modules"]:
        for k in ("id", "title", "out_path", "status", "edge_claimed", "as_of",
                  "evidence_page", "chart_path", "one_line"):
            assert k in row, f"module {row.get('id')} missing field: {k}"
        assert row["edge_claimed"] is False, f"{row['id']}: edge_claimed must be False"
        assert row["status"] in ("ok", "not_buildable", "partial"), \
            f"{row['id']}: bad status {row['status']}"
        for k in ("out_path", "chart_path", "evidence_page"):
            v = row[k]
            assert v is None or not abs_pat.match(v), \
                f"{row['id']}: {k} is absolute (not clone-safe): {v}"


def check():
    assert _MANIFEST.exists(), f"recorded manifest absent: {_rel(_MANIFEST)}"
    m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    _validate(m)
    print(f"PASS -- site_manifest.json: {m['module_count']} modules, "
          f"{m['atlas_card_count']} atlas cards, checks_green={m['checks_green']['green']}")


def demo():
    """Self-check: build in-memory, validate, and assert clone-safety."""
    m = build()
    _validate(m)
    assert m["module_count"] > 0, "no modules found"
    assert m["atlas_card_count"] > 0, "no atlas cards counted"
    for row in m["modules"]:
        assert not (row["out_path"] or "").startswith("C:"), "absolute path leaked"
    print(f"demo OK: {m['module_count']} modules, {m['atlas_card_count']} atlas cards")


def main():
    if "--check" in sys.argv:
        check()
        return
    if "--demo" in sys.argv:
        demo()
        return
    m = build()
    _validate(m)
    _MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"wrote {_rel(_MANIFEST)}: {m['module_count']} modules, "
          f"{m['atlas_card_count']} atlas cards, "
          f"checks_green={m['checks_green']['green']}")


if __name__ == "__main__":
    main()
