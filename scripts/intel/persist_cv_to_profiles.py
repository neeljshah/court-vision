"""persist_cv_to_profiles.py — Propagate filled CV _cv_fields from atlas parquets
into the per-player persistent profile JSONs and regenerate the profile indices.

This follows the bridge's DISJOINT-EXTENSION pattern:
  - NEVER rebuilds the full factory (build_persistent_profiles.py stays untouched).
  - Reads all ``data/cache/atlas_player_*.parquet`` that carry a ``_cv_fields``
    column (populated by populate_cv_fields.py).
  - Merges the filled slot values + ``_cv_meta`` into each
    ``data/cache/profiles/players/<player_id>.json`` under a top-level
    ``cv_atlas_fields`` key (non-destructive: only this key is updated).
  - Calls ``build_profile_indices.py:main()`` to regenerate PLAYER_INDEX.json
    so the index reflects the new state.

Idempotent: re-running overwrites only the ``cv_atlas_fields`` key with the
latest values; all other profile keys are preserved.

Safe to run any time; reads are from parquets already on disk (never hits the
NBA API).

Usage:
    python scripts/intel/persist_cv_to_profiles.py
    python scripts/intel/persist_cv_to_profiles.py --dry-run
    python scripts/intel/persist_cv_to_profiles.py --as-of 2026-05-31
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"
PROFILES_DIR = CACHE / "profiles" / "players"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_atlas_cv_lookup() -> Dict[int, Dict[str, Any]]:
    """Return {player_id: {section_name: {slot_name: value, ...}, _cv_meta: {...}}}.

    Scans all atlas_player_*.parquet files that have both ``player_id`` and
    ``_cv_fields`` columns.  For each player, collects the union of all filled
    slot values across atlas sections and the latest ``_cv_meta`` block.
    """
    atlas_files = sorted(CACHE.glob("atlas_player_*.parquet"))
    if not atlas_files:
        print(f"  [warn] no atlas_player_*.parquet found under {CACHE}")
        return {}

    # player_id -> {section: {slot: value}, _cv_meta_latest: {...}}
    lookup: Dict[int, Dict[str, Any]] = {}

    for path in atlas_files:
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            print(f"  [warn] could not read {path.name}: {exc}")
            continue

        if "_cv_fields" not in df.columns or "player_id" not in df.columns:
            continue

        section = path.stem.replace("atlas_player_", "")

        for _, row in df.iterrows():
            try:
                pid = int(row["player_id"])
            except (TypeError, ValueError):
                continue

            raw = row.get("_cv_fields")
            if raw is None:
                continue
            try:
                cv_dict: dict = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

            meta = cv_dict.pop("_cv_meta", None)
            # Collect filled slots (value != None) per section
            filled_slots: Dict[str, Any] = {}
            for slot_name, slot_data in cv_dict.items():
                if not isinstance(slot_data, dict):
                    continue
                val = slot_data.get("value")
                if val is not None:
                    filled_slots[slot_name] = {
                        "value": val,
                        "dtype": slot_data.get("dtype"),
                        "unit": slot_data.get("unit"),
                    }

            if not filled_slots and meta is None:
                continue

            if pid not in lookup:
                lookup[pid] = {"sections": {}, "_cv_meta_latest": None}

            if filled_slots:
                lookup[pid]["sections"][section] = filled_slots

            # Keep latest meta (by as_of date)
            if meta is not None:
                cur_meta = lookup[pid]["_cv_meta_latest"]
                if cur_meta is None:
                    lookup[pid]["_cv_meta_latest"] = meta
                else:
                    cur_as_of = str(cur_meta.get("as_of") or "")
                    new_as_of = str(meta.get("as_of") or "")
                    if new_as_of > cur_as_of:
                        lookup[pid]["_cv_meta_latest"] = meta

    return lookup


def _persist_cv_fields_to_profile(
    player_id: int,
    cv_data: Dict[str, Any],
    profiles_dir: Path,
    as_of: str,
    dry_run: bool = False,
) -> bool:
    """Update one player profile JSON with cv_atlas_fields.  Returns True if updated."""
    profile_path = profiles_dir / f"{player_id}.json"
    if not profile_path.exists():
        return False

    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    # Build the cv_atlas_fields payload
    payload = {
        "as_of": as_of,
        "sections": cv_data.get("sections", {}),
    }
    if cv_data.get("_cv_meta_latest"):
        payload["_cv_meta"] = cv_data["_cv_meta_latest"]

    # Preserve all existing keys; only update cv_atlas_fields
    profile["cv_atlas_fields"] = payload

    if not dry_run:
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(as_of: Optional[str] = None, dry_run: bool = False) -> int:
    """Propagate CV fields from atlas parquets into profile JSONs + regen indices."""
    as_of = as_of or date.today().isoformat()
    print(f"persist_cv_to_profiles  as_of={as_of}  dry_run={dry_run}")
    print(f"  Scanning atlas parquets in {CACHE} ...")

    lookup = _load_atlas_cv_lookup()
    print(f"  Found CV data for {len(lookup)} players across atlas parquets.")

    if not PROFILES_DIR.exists():
        print(f"  [warn] profiles/players dir not found: {PROFILES_DIR}")
        return 1

    n_updated = 0
    n_skipped = 0
    for pid, cv_data in sorted(lookup.items()):
        updated = _persist_cv_fields_to_profile(
            pid, cv_data, PROFILES_DIR, as_of, dry_run=dry_run
        )
        if updated:
            n_updated += 1
        else:
            n_skipped += 1

    status = "DRY-RUN" if dry_run else "WROTE"
    print(f"\n  [{status}] Updated {n_updated} profiles, skipped {n_skipped} "
          f"(no profile file for those player IDs).")

    # Regenerate PLAYER_INDEX.json + TEAM_INDEX.json
    if not dry_run:
        print("\n  Regenerating profile indices ...")
        try:
            import subprocess
            python = sys.executable
            idx_script = str(ROOT / "scripts" / "loop" / "build_profile_indices.py")
            result = subprocess.run(
                [python, idx_script],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            print(result.stdout.rstrip())
            if result.returncode != 0:
                print(f"  [warn] build_profile_indices exit={result.returncode}: {result.stderr[:200]}",
                      file=sys.stderr)
            else:
                print(f"  build_profile_indices -> exit=0")
        except Exception as exc:
            print(f"  [warn] build_profile_indices failed: {exc}", file=sys.stderr)
    else:
        print("  [dry-run] skipping index regeneration")

    print("\nDone.")
    return 0


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Propagate CV _cv_fields from atlas parquets into profile JSONs "
                    "+ regenerate PLAYER_INDEX.json."
    )
    parser.add_argument(
        "--as-of",
        default=None,
        metavar="YYYY-MM-DD",
        help="Provenance date stamp (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + log but do not write any files.",
    )
    args = parser.parse_args()
    sys.exit(main(as_of=args.as_of, dry_run=args.dry_run))


if __name__ == "__main__":
    _cli()
