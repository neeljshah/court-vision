"""Shared clone-safe --check fallback.

On a fresh clone, data/ is absent (gitignored). When a module's --check can't
re-derive from local data, it falls back to verifying the committed
out/<module>.json artifact structurally instead of inventing a result, and
says so in visibly-labeled stdout. With local data present, behavior is
unchanged (full re-derivation, this file is not on that path).

Usage:
    try:
        from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
    except ImportError:
        from _clone_safe import verify_recorded_artifact
"""
import json
import os
from pathlib import Path

_SHOWCASE = Path(__file__).resolve().parent


def verify_recorded_artifact(out_json_path, validate, label):
    """Load the committed artifact, run `validate(data)` (should assert),
    print the recorded-artifact-mode PASS line, and return the data.
    Raises (does not silently pass) if the artifact is missing or invalid.
    """
    p = Path(out_json_path)
    assert p.exists(), f"{label}: local data absent AND no committed artifact at {p} -- cannot verify"
    data = json.loads(p.read_text(encoding="utf-8"))
    validate(data)
    print(f"PASS (recorded-artifact mode: local data absent) -- {label}: verified {p.name}")
    return data


def staged_input(name):
    """Resolve an upstream showcase artifact this module reads as its corpus.

    With CV_INGAME_CORPUS_SUFFIX set (e.g. "_segmented") the staged
    out_segmented/ copy -- rebuilt from the segmented in-game join corpus --
    is preferred when it exists; otherwise, and for artifacts that were never
    staged there, the published out/ copy is used. Default (env unset) is
    always out/. Returns a str path.
    """
    if os.environ.get("CV_INGAME_CORPUS_SUFFIX"):
        staged = _SHOWCASE / "out_segmented" / name
        if staged.exists():
            return str(staged)
    return str(_SHOWCASE / "out" / name)
