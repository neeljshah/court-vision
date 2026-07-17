"""make_pack.py -- build the shareable CourtVision data-pack zip.

Reads the ALLOWLIST in pack_manifest.py, verifies every selected file against
the FORBIDDEN path/name/secret rules (fail-closed -- a violation aborts the
build loudly), then writes:

  data/cache/publish_pack/courtvision-datapack-YYYYMMDD.zip
  data/cache/publish_pack/pack_info.json

It NEVER uploads anything. It prints the exact `gh release create` command the
OWNER runs to publish. Descriptive-intelligence snapshot only: no betting data,
no live updates, edge_claimed:false.

Usage: python -m scripts.platformkit.publish_pack.make_pack [--out DIR] [--repo-root DIR]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time
import zipfile
from pathlib import Path

from scripts.platformkit.publish_pack import pack_manifest as M

REPO_ROOT = Path(__file__).resolve().parents[3]
GH_REPO = "neeljshah/court-vision"

# order matters: strip the longest/most-specific suffix first.
_FAMILY_SUFFIXES = (".index.jsonl", "_validation.json", ".jsonl", ".parquet")


def _family_stem(name: str) -> str:
    for suf in _FAMILY_SUFFIXES:
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def collect_candidates(root: Path) -> list[str]:
    """Return sorted rel-paths matched by the allowlist that exist on disk."""
    seen: set[str] = set()
    for sub, patterns in M.ALLOW_GLOBS:
        base = root / sub
        for pat in patterns:
            for p in glob.glob(str(base / pat)):
                pp = Path(p)
                if pp.is_file():
                    seen.add(_rel(pp, root))
    for rel in M.EXPLICIT_FILES:
        if (root / rel).is_file():
            seen.add(rel)
    return sorted(seen)


def select(root: Path, candidates: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Apply silent excludes (ledger substrings) + the per-file size cap.
    Returns (selected, excluded[(rel, reason)]). Size cap drops a whole family
    when its data jsonl is oversized, so no half-family ships."""
    cap = M.MAX_FILE_MB * 1024 * 1024
    excluded: list[tuple[str, str]] = []
    oversize_stems: set[str] = set()

    # first pass: find oversized intel-claims data families.
    for rel in candidates:
        name = Path(rel).name
        if rel.startswith("data/cache/intel_claims/") and name.endswith(".jsonl") \
                and not name.endswith(".index.jsonl"):
            if (root / rel).stat().st_size > cap:
                oversize_stems.add(_family_stem(name))

    selected: list[str] = []
    for rel in candidates:
        name = Path(rel).name
        stem = _family_stem(name)
        if any(s in stem for s in M.INTEL_EXCLUDE_SUBSTR):
            excluded.append((rel, "excluded family substring"))
            continue
        if rel.startswith("data/cache/intel_claims/") and stem in oversize_stems:
            excluded.append((rel, "family over size cap -> degrades to no_data"))
            continue
        if (root / rel).stat().st_size > cap:
            excluded.append((rel, "file over size cap"))
            continue
        selected.append(rel)
    return selected, excluded


def verify(root: Path, rel: str) -> None:
    """Fail-closed guard: raise if rel trips a FORBIDDEN path/name rule or its
    (text) content carries a secret-like token. A correct allowlist never trips
    this; if it fires, a glob over-matched and the build must stop."""
    reason = M.forbidden_reason(rel)
    if reason:
        raise RuntimeError(f"privacy gate: refusing {rel!r} -- {reason}")
    if rel.lower().endswith(M.TEXT_SUFFIXES):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        m = M.SECRET_PATTERN.search(text)
        if m:
            raise RuntimeError(
                f"privacy gate: refusing {rel!r} -- secret-like token {m.group(0)!r}")


def build(root: Path, out_dir: Path) -> dict:
    candidates = collect_candidates(root)
    selected, excluded = select(root, candidates)
    if not selected:
        raise RuntimeError("no files selected -- is data/ present?")

    for rel in selected:  # verify BEFORE writing a single byte.
        verify(root, rel)

    out_dir.mkdir(parents=True, exist_ok=True)
    date = time.strftime("%Y%m%d", time.gmtime())
    zip_path = out_dir / f"courtvision-datapack-{date}.zip"
    total_bytes = 0
    families = sum(1 for r in selected if r.endswith("_validation.json"))
    info = {
        "name": zip_path.name,
        "version_date": date,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file_count": len(selected),
        "uncompressed_mb": round(sum((root / r).stat().st_size for r in selected)
                                 / 1024 / 1024, 1),
        "family_count": families,
        "excluded_count": len(excluded),
        "edge_claimed": False,
        "honest_note": ("descriptive intelligence snapshot -- validated claim "
                        "families + profiles + derived domain parquets. No betting "
                        "data, no scraped odds, no live updates. Absent per-entity "
                        "pointer stores degrade to no_data by design."),
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in selected:
            src = root / rel
            total_bytes += src.stat().st_size
            zf.write(src, arcname=rel)
        # pack_info.json travels INSIDE the zip so the consumer can verify it.
        zf.writestr("pack_info.json", json.dumps(info, indent=2) + "\n")

    info["zip_mb"] = round(zip_path.stat().st_size / 1024 / 1024, 1)
    (out_dir / "pack_info.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8")
    info["_zip_path"] = str(zip_path)
    info["_excluded"] = excluded
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    ap.add_argument("--out", default=None,
                    help="output dir (default <repo>/data/cache/publish_pack)")
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()
    out_dir = Path(args.out).resolve() if args.out else root / "data" / "cache" / "publish_pack"

    info = build(root, out_dir)
    zip_path = info.pop("_zip_path")
    excluded = info.pop("_excluded")

    print(f"pack: {zip_path}")
    print(f"  files={info['file_count']} families={info['family_count']} "
          f"zip={info['zip_mb']}MB uncompressed={info['uncompressed_mb']}MB "
          f"excluded={info['excluded_count']}")
    # show a few notable exclusions (the big pointer stores).
    for rel, reason in excluded:
        if "size cap" in reason:
            print(f"  cut  {rel} -- {reason}")
    print("\n-- OWNER release step (NOT run by this script) --")
    print(f"  gh release create datapack-{info['version_date']} \\")
    print(f'    "{zip_path}" \\')
    print(f"    --repo {GH_REPO} \\")
    print(f'    --title "CourtVision data-pack {info["version_date"]}" \\')
    print('    --notes "Descriptive-intelligence snapshot. No betting data, no live updates."')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
