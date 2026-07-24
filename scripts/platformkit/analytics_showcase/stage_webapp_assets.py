"""Stage analytics-showcase artifacts into the webapp public tree.

Copies out/*.json -> webapp/public/data/showcase/ and the chart PNGs they
reference -> webapp/public/img/showcase/, rewriting every path to be
clone-safe (repo-relative, forward slashes). The 1,549 per-entity atlas card
PNGs are NOT copied -- only their manifests, whose card_path is normalized so
the site can link them if the images are staged separately.

Web-safe = no box-local absolute (C:/Users/...), no backslashes, path-keys
resolved relative to repo root. The webapp reads ONLY from public/, so nothing
here may leave a `../scripts` traversal or an absolute path in the JSON.

Run:   python -m scripts.platformkit.analytics_showcase.stage_webapp_assets
Check: python -m scripts.platformkit.analytics_showcase.stage_webapp_assets --check
Authors do NOT run this; the gate phase does. --check does no filesystem writes.
"""
import json
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_OUT = _REPO / "scripts" / "platformkit" / "analytics_showcase" / "out"
_IMG = _REPO / "docs" / "img"
_DATA_DST = _REPO / "webapp" / "public" / "data" / "showcase"
_IMG_DST = _REPO / "webapp" / "public" / "img" / "showcase"

# Skip: the atlas card image tree (1,549 PNGs) is intentionally not staged.
_ATLAS_IMG_PREFIX = "docs/img/atlas/"

# JSON string values under these keys are paths -> normalize to clone-safe.
_PATH_KEYS = {
    "card_path", "source", "out_path", "chart_path",
    "generated_from", "path", "image", "png", "chart",
}


def _clone_safe_path(s):
    """Absolute-or-messy path string -> repo-relative POSIX, else forward-slashed."""
    norm = s.replace("\\", "/")
    p = Path(norm)
    if p.is_absolute() or (len(norm) > 1 and norm[1] == ":"):
        try:
            return str(Path(norm).resolve().relative_to(_REPO)).replace("\\", "/")
        except (ValueError, OSError):
            # absolute but not under repo: strip drive, keep tail (still no C:/)
            return norm.split(":", 1)[-1].lstrip("/")
    return norm


def _normalize(obj):
    """Recursively rewrite path-key string values to be clone-safe. In place-ish."""
    if isinstance(obj, dict):
        return {
            k: (_clone_safe_path(v) if k in _PATH_KEYS and isinstance(v, str)
                else _normalize(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    return obj


def _png_refs(obj, acc):
    """Collect every docs/img/*.png reference (already clone-safe) into acc."""
    if isinstance(obj, dict):
        for v in obj.values():
            _png_refs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _png_refs(v, acc)
    elif isinstance(obj, str) and obj.endswith(".png") and "docs/img/" in obj:
        if not obj.startswith(_ATLAS_IMG_PREFIX):
            acc.add(obj)


def _iter_jsons():
    return sorted(_OUT.glob("*.json"))


def stage():
    _DATA_DST.mkdir(parents=True, exist_ok=True)
    _IMG_DST.mkdir(parents=True, exist_ok=True)
    png_refs = set()
    n_json = 0
    for f in _iter_jsons():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data = _normalize(data)
        _png_refs(data, png_refs)
        (_DATA_DST / f.name).write_text(
            json.dumps(data, indent=1, ensure_ascii=True), encoding="utf-8")
        n_json += 1
    n_png = 0
    for rel in sorted(png_refs):
        src = _REPO / rel
        if src.exists():
            shutil.copy2(src, _IMG_DST / src.name)
            n_png += 1
    print(f"staged {n_json} JSONs -> {_rel(_DATA_DST)}, "
          f"{n_png} chart PNGs -> {_rel(_IMG_DST)} "
          f"(skipped atlas card tree {_ATLAS_IMG_PREFIX}*)")
    return n_json, n_png


def _rel(p):
    return str(p.relative_to(_REPO)).replace("\\", "/")


def _assert_web_safe(name, data):
    """No absolute/backslash paths survive in a staged JSON's path-keys."""
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _PATH_KEYS and isinstance(v, str):
                    assert "\\" not in v, f"{name}: backslash in {k}: {v}"
                    assert not (len(v) > 1 and v[1] == ":"), \
                        f"{name}: drive-absolute {k}: {v}"
                    assert not v.startswith("/"), f"{name}: root-absolute {k}: {v}"
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)


def check():
    """Static, no-write: verify normalization is web-safe on the source JSONs."""
    n = 0
    for f in _iter_jsons():
        try:
            data = _normalize(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        _assert_web_safe(f.name, data)
        n += 1
    assert n > 0, "no source JSONs found"
    print(f"PASS -- {n} JSONs normalize to web-safe paths (no writes)")


def demo():
    """Self-check on synthetic input: absolute + backslash paths get cleaned."""
    dirty = {
        "source": "data\\cache\\x.json",
        "card_path": str(_REPO / "docs" / "img" / "atlas" / "nba" / "a.png"),
        "one_line": "prose with a back\\slash stays untouched",
        "rows": [{"chart_path": "docs/img/y.png"}],
    }
    clean = _normalize(dirty)
    assert clean["source"] == "data/cache/x.json", clean["source"]
    assert clean["card_path"] == "docs/img/atlas/nba/a.png", clean["card_path"]
    assert clean["one_line"] == dirty["one_line"], "non-path key must be untouched"
    assert clean["rows"][0]["chart_path"] == "docs/img/y.png"
    refs = set()
    _png_refs(clean, refs)
    assert refs == {"docs/img/y.png"}, f"atlas png must be skipped: {refs}"
    _assert_web_safe("demo", clean)
    print("demo OK")


def main():
    if "--check" in sys.argv:
        check()
    elif "--demo" in sys.argv:
        demo()
    else:
        stage()


if __name__ == "__main__":
    main()
