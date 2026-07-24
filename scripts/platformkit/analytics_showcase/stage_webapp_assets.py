"""Stage analytics-showcase artifacts into the webapp public tree.

Copies out/*.json -> webapp/public/data/showcase/ and the chart PNGs they
reference -> webapp/public/img/showcase/, path-cleaned to be clone-safe (no
box-local absolute, no backslashes, repo-relative). The 1,549 atlas card PNGs
are NOT copied, only their manifests. Also repairs cp1252-mojibake entity
names (_fix_mojibake) and stages docs/INGAME_PROOF.md's committed receipts
into showcase/forecaster/ (stage_forecaster).

Run:   python -m scripts.platformkit.analytics_showcase.stage_webapp_assets
Check: python -m scripts.platformkit.analytics_showcase.stage_webapp_assets --check
Authors do NOT run this; the gate phase does. --check does no filesystem writes.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_OUT = _REPO / "scripts" / "platformkit" / "analytics_showcase" / "out"
_IMG = _REPO / "docs" / "img"
_DATA_DST = _REPO / "webapp" / "public" / "data" / "showcase"
_IMG_DST = _REPO / "webapp" / "public" / "img" / "showcase"
_FORECASTER_DST = _DATA_DST / "forecaster"

# Skip: the atlas card image tree (1,549 PNGs) is intentionally not staged.
_ATLAS_IMG_PREFIX = "docs/img/atlas/"

# Note: _iter_jsons() globs ALL of out/*.json, so novel_*.json, brand_logo_variants.json,
# mechanism_ledger_export.json and evidence_index.json are already picked up as soon as
# they exist in out/ -- no extra wiring needed, just re-run stage() after they land.

# docs/INGAME_PROOF.md's headline (Brier 0.209->0.159 etc.) cites source scripts + the raw
# settlement-join cache, not a committed JSON receipt. These already-staged aggregate files
# characterize the SAME real corpus at finer grain and ARE committed -- copied alongside the
# pregame walk-forward proof so the Forecaster page has one small folder to read.
_FORECASTER_AGGREGATES = [
    "state_conditioned_calibration.json", "murphy_decomposition.json",
    "calibration_stability.json", "brier_skill_scores.json",
    "cross_sport_scoreboard.json",
]
_FORECASTER_WF = _REPO / "results" / "winprob_walk_forward_results.json"
# Raw receipt dirs docs/INGAME_PROOF.md's Section 2 table cites -- verified NOT git-tracked
# (local-only cache); never staged, only reported.
_INGAME_UNCOMMITTED = [
    "data/cache/ingame_grade_joined/mlb",
    "data/cache/ingame_grade_joined/soccer_intl",
]

# JSON string values under these keys are paths -> normalize to clone-safe.
_PATH_KEYS = {
    "card_path", "source", "out_path", "chart_path",
    "generated_from", "path", "image", "png", "chart",
}


def _looks_absolute(s):
    """True if s looks like a box-local absolute path (drive-letter prefixed)."""
    norm = s.replace("\\", "/")
    return Path(norm).is_absolute() or (len(norm) > 1 and norm[1] == ":")


def _clone_safe_path(s):
    """Absolute-or-messy path string -> repo-relative POSIX, else forward-slashed."""
    norm = s.replace("\\", "/")
    if _looks_absolute(s):
        try:
            return str(Path(norm).resolve().relative_to(_REPO)).replace("\\", "/")
        except (ValueError, OSError):
            # absolute but not under repo: strip drive, keep tail (still no C:/)
            return norm.split(":", 1)[-1].lstrip("/")
    return norm


def _normalize(obj):
    """Recursively rewrite path-like strings to be clone-safe. _PATH_KEYS is the
    known-path allowlist; the trailing content check is the safety net for a leak
    under an unlisted key or inside a list (e.g. "paths_tried"), where the list
    branch below loses its parent key and a keyed lookup alone would miss it."""
    if isinstance(obj, dict):
        return {
            k: (_clone_safe_path(v) if k in _PATH_KEYS and isinstance(v, str)
                else _normalize(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, str) and _looks_absolute(obj):
        return _clone_safe_path(obj)
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


def _fix_mojibake_str(s):
    """Repair UTF-8-bytes-misdecoded-as-cp1252 mojibake (e.g. an accented name whose
    bytes got read one-byte-at-a-time as cp1252 instead of as UTF-8). Round-tripping
    already-clean text through cp1252 raises (single accented bytes aren't valid UTF-8
    continuations), so correct strings pass through untouched."""
    try:
        fixed = s.encode("cp1252").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s
    return fixed


def _fix_mojibake(obj, counter):
    """Recursively repair mojibake strings; counter[0] += 1 per string actually changed."""
    if isinstance(obj, dict):
        return {k: _fix_mojibake(v, counter) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_mojibake(v, counter) for v in obj]
    if isinstance(obj, str):
        fixed = _fix_mojibake_str(obj)
        if fixed != obj:
            counter[0] += 1
        return fixed
    return obj


def _git_tracked(rel):
    """True if `rel` (repo-relative path) has >=1 file tracked by git. Read-only."""
    try:
        out = subprocess.run(["git", "ls-files", rel], cwd=_REPO,
                              capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip())
    except OSError:
        return False


def stage_forecaster():
    """Copy the committed receipts backing docs/INGAME_PROOF.md's headline into
    showcase/forecaster/; honestly skip + report the raw corpus it cites that isn't
    git-tracked. Assumes stage()'s main loop already populated _DATA_DST."""
    _FORECASTER_DST.mkdir(parents=True, exist_ok=True)
    included = []
    if _FORECASTER_WF.exists() and _git_tracked("results/winprob_walk_forward_results.json"):
        shutil.copy2(_FORECASTER_WF, _FORECASTER_DST / _FORECASTER_WF.name)
        included.append(_FORECASTER_WF.name)
    for name in _FORECASTER_AGGREGATES:
        src = _DATA_DST / name
        if src.exists():
            shutil.copy2(src, _FORECASTER_DST / name)
            included.append(name)
    skipped = [p for p in _INGAME_UNCOMMITTED if not _git_tracked(p)]
    manifest = {
        "as_of": "2026-07-23",
        "doc_source": "docs/INGAME_PROOF.md",
        "included": included,
        "skipped_uncommitted": skipped,
        "note": ("docs/INGAME_PROOF.md cites source scripts (proof_nba/proof_mlb "
                 "ingame_accuracy.py, ticker_settlement_join.py) and the raw "
                 "settlement-join cache, not a committed JSON receipt for the "
                 "0.209->0.159 headline; the files above are the committed, "
                 "already-verified aggregates over the same real corpus."),
    }
    (_FORECASTER_DST / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"forecaster: staged {len(included)} receipts, "
          f"{len(skipped)} cited paths honestly skipped (not git-tracked) "
          f"-> {_rel(_FORECASTER_DST)}")
    return included, skipped


def stage():
    _DATA_DST.mkdir(parents=True, exist_ok=True)
    _IMG_DST.mkdir(parents=True, exist_ok=True)
    png_refs = set()
    n_json = 0
    mojibake_count = [0]
    for f in _iter_jsons():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data = _normalize(data)
        data = _fix_mojibake(data, mojibake_count)
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
          f"(skipped atlas card tree {_ATLAS_IMG_PREFIX}*), "
          f"{mojibake_count[0]} mojibake names repaired")
    stage_forecaster()
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
    mojibake_count = [0]
    for f in _iter_jsons():
        try:
            data = _normalize(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        data = _fix_mojibake(data, mojibake_count)
        _assert_web_safe(f.name, data)
        n += 1
    assert n > 0, "no source JSONs found"
    # forecaster provenance (read-only): confirm tracked/untracked verdicts can't drift.
    assert _git_tracked("results/winprob_walk_forward_results.json"), \
        "expected results/winprob_walk_forward_results.json to be git-tracked"
    for p in _INGAME_UNCOMMITTED:
        assert not _git_tracked(p), f"expected {p} to be uncommitted (found tracked)"
    print(f"PASS -- {n} JSONs normalize to web-safe paths (no writes), "
          f"{mojibake_count[0]} mojibake names would repair, "
          f"forecaster receipt provenance verified")


def demo():
    """Self-check on synthetic input: absolute + backslash paths get cleaned, mojibake
    repaired, clean accented text left alone."""
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

    # mojibake, built from \u escapes (pure-ASCII source): "\u00e9" (e-acute) mis-decoded
    # one byte at a time as cp1252 is "\u00c3\u00a9"; the soft hyphen U+00AD in the
    # i-acute case is the invisible "flattened accent" the mojibake report described.
    e_mojibake = "\u00c3\u00a9"
    i_mojibake = "\u00c3\u00ad"
    e_correct = "\u00e9"
    i_correct = "\u00ed"
    mangled = {"entity": "Jos" + e_mojibake + " Ram" + i_mojibake + "rez"}
    counter = [0]
    fixed = _fix_mojibake(mangled, counter)
    assert fixed["entity"] == "Jos" + e_correct + " Ram" + i_correct + "rez", fixed["entity"]
    assert counter[0] == 1, counter
    correct = {"entity": "Mart" + i_correct + "n Maldonado"}   # already correct, untouched
    counter2 = [0]
    fixed2 = _fix_mojibake(correct, counter2)
    assert fixed2 == correct and counter2[0] == 0, (fixed2, counter2)
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
