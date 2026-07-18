"""Self-heal regen mapping for the pod validation loop (see validation_loop.sh
module docstring for the root problem: a `git pull` re-validates stale
on-disk claims stores against possibly-changed producer code but never
regenerates them, inflating the mismatch counter on a producer-code change
that isn't real data corruption).

Two family sources, both scanned READ-ONLY (no writes, no data/ access):

  1. AUTO-GRID families -- every domains/<sport>/claims_grid.py's GRID
     (pure DATA, per that module's own docstring: "zero logic, zero I/O")
     lists families materialized by the shared claims_factory. Regen command:
         python -m scripts.platformkit.intel_validation.claims_factory
             --sport <sport> --family <family>
     Discovered by globbing domains/*/claims_grid.py and importing GRID --
     self-updating as new sports/families are added, never hardcoded.

  2. BESPOKE families -- hand-written producer modules under
     scripts/platformkit/intel_validation/ and domains/**/ that assign their
     own output path, e.g. `_CLAIMS_OUT = _OUT_DIR / "foo_claims.jsonl"` or
     `CLAIMS_PATH = Path(".../foo_claims.jsonl")`. Detected by regexing for
     a `VARNAME = ... "<stem>.jsonl"` assignment where VARNAME contains
     "CLAIMS" or ends in "_OUT" -- this excludes files that merely READ
     another family's store as an input dependency (e.g.
     domains/mlb/umpire_assignment_gate.py's `_PROFILE_PATH`, which reads
     umpire_zone_claims.jsonl but does not write it; verified by hand this
     session). Regen command: `python -m <dotted.module.path>`.

A HANDFUL of bespoke families use a producer filename that does not match
the family stem (the module-name convention that makes bespoke resolution
trivial breaks down) -- OVERRIDES below pins those explicitly rather than
leaning on regex fragility.

Some families genuinely have NO single regen command -- e.g.
prereg_hypothesis_ledger.jsonl (domains/*/prereg/stats_common.py's
LEDGER_PATH) is appended to by a dozen independent validate_*/sim2 scripts
across sports; there is no one command that reproduces the whole ledger.
Fail-closed by design: regen_command_for_family returns None for these, the
loop skips + logs them rather than guessing a wrong command.

CLI:
    python -m scripts.platformkit.pod_sprint.regen_manifest --producer <path>
    python -m scripts.platformkit.pod_sprint.regen_manifest --family <stem>
    python -m scripts.platformkit.pod_sprint.regen_manifest --all
"""
from __future__ import annotations

import argparse
import importlib
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_DOMAINS_DIR = REPO_ROOT / "domains"
_BESPOKE_ROOTS = [REPO_ROOT / "scripts" / "platformkit" / "intel_validation", _DOMAINS_DIR]
_FACTORY_MODULE = "scripts.platformkit.intel_validation.claims_factory"

# VARNAME = <expr> "stem.jsonl"  (single logical line; f-strings/multi-line
# path-joins are not claims-store declarations in this codebase's convention).
_OUT_VAR_PAT = re.compile(
    r'^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=.*?["\']([A-Za-z0-9_./]+?)\.jsonl["\']',
    re.MULTILINE,
)

# Hand-pinned: family stem -> dotted module path, for producers whose
# filename does NOT equal the family stem (breaks the naive convention).
# Documented individually -- each is a real, verified producer, not a guess.
OVERRIDES: dict[str, str] = {
    # domains/mlb/claims_shift_framing.py writes 2 families from one module
    # (_FRAMING_OUT / _SHIFT_VULN_OUT); neither stem matches the filename.
    "mlb_framing_claims": "domains.mlb.claims_shift_framing",
    "mlb_shift_vulnerability_claims": "domains.mlb.claims_shift_framing",
    # domains/basketball_nba/quality_validity_gate_claims.py writes
    # nba_quality_claims.jsonl (CLAIMS_PATH) -- filename doesn't match stem.
    "nba_quality_claims": "domains.basketball_nba.quality_validity_gate_claims",
}


def _is_out_var(name: str) -> bool:
    u = name.upper()
    return "CLAIMS" in u or u.endswith("_OUT") or u == "OUT"


def _to_module_path(repo_rel_py: str) -> str:
    rel = repo_rel_py.replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[: -len(".py")]
    return rel.replace("/", ".")


def _repo_rel(path: str) -> str:
    p = Path(path)
    try:
        p = p.resolve().relative_to(REPO_ROOT)
    except ValueError:
        p = Path(str(path).replace("\\", "/"))
    return str(p).replace("\\", "/")


def _grid_sport_dirs() -> list[str]:
    """Every domains/<sport>/ that carries a claims_grid.py -- globbed, not
    hardcoded, so a newly added sport's grid is picked up automatically."""
    if not _DOMAINS_DIR.is_dir():
        return []
    return sorted(
        p.parent.name for p in _DOMAINS_DIR.glob("*/claims_grid.py")
    )


def _scan_auto_grid() -> dict[str, str]:
    """family_stem -> sport, from every discovered domains/<sport>/claims_grid.py."""
    out: dict[str, str] = {}
    for sport in _grid_sport_dirs():
        try:
            mod = importlib.import_module(f"domains.{sport}.claims_grid")
        except ImportError:
            continue
        for fam in mod.GRID.get("families", []):
            out[fam["family"]] = sport
    return out


def _scan_bespoke() -> dict[str, str]:
    """family_stem -> dotted module path, from producer files' OWN output-
    path assignment (never a downstream importer or support/snapshot
    builder that writes no distinct intel_claims store of its own)."""
    out: dict[str, str] = {}
    for root in _BESPOKE_ROOTS:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if not fn.endswith(".py") or fn.startswith("test_"):
                    continue
                fpath = Path(dirpath) / fn
                try:
                    text = fpath.read_text(encoding="utf-8")
                except OSError:
                    continue
                module = _to_module_path(_repo_rel(str(fpath)))
                for m in _OUT_VAR_PAT.finditer(text):
                    varname, val = m.group(1), m.group(2)
                    if not _is_out_var(varname):
                        continue
                    stem = val.split("/")[-1]
                    out.setdefault(stem, module)
    return out


_auto_grid_cache: dict[str, str] | None = None
_bespoke_cache: dict[str, str] | None = None


def _auto_grid() -> dict[str, str]:
    global _auto_grid_cache
    if _auto_grid_cache is None:
        _auto_grid_cache = _scan_auto_grid()
    return _auto_grid_cache


def _bespoke() -> dict[str, str]:
    global _bespoke_cache
    if _bespoke_cache is None:
        _bespoke_cache = _scan_bespoke()
    return _bespoke_cache


def regen_command_for_family(family_stem: str) -> str | None:
    """The shell command that regenerates one family, or None if this scan
    can't resolve a single command for it (loop skips it, logs it)."""
    sport = _auto_grid().get(family_stem)
    if sport:
        return f"python -m {_FACTORY_MODULE} --sport {sport} --family {family_stem}"
    module = OVERRIDES.get(family_stem) or _bespoke().get(family_stem)
    if module:
        return f"python -m {module}"
    return None


def family_for_producer(producer_path: str) -> list[str]:
    """Families a changed producer FILE is responsible for regenerating.

    - domains/<sport>/claims_grid.py -> every family in that sport's GRID
      (grid config is shared across all its families -- a conservative
      whole-sport regen, matching claims_factory.generate_sport()).
    - the shared claims_factory.py itself -> every auto-grid family across
      EVERY sport (its criteria/formula-evaluation logic backs all of them).
    - anything else -> the family stem(s) this scan found it writing
      (bespoke scan + OVERRIDES), or [] if it writes no distinct family of
      its own (a support/ingredient/snapshot builder, or a shared multi-
      writer ledger with no single owning file) -- honest, not guessed.
    """
    rel = _repo_rel(producer_path)
    if rel.startswith("domains/") and rel.endswith("/claims_grid.py"):
        sport = rel.split("/")[1]
        try:
            mod = importlib.import_module(f"domains.{sport}.claims_grid")
        except ImportError:
            return []
        return [fam["family"] for fam in mod.GRID.get("families", [])]

    module = _to_module_path(rel)
    if module == _FACTORY_MODULE:
        return sorted(_auto_grid().keys())

    found = sorted(fam for fam, m in _bespoke().items() if m == module)
    found += [fam for fam, m in OVERRIDES.items() if m == module and fam not in found]
    return found


def _print_all() -> None:
    combined: dict[str, str] = {}
    combined.update({fam: f"python -m {_FACTORY_MODULE} --sport {sport} --family {fam}" for fam, sport in _auto_grid().items()})
    for fam in list(_bespoke().keys()) + list(OVERRIDES.keys()):
        cmd = regen_command_for_family(fam)
        if cmd:
            combined[fam] = cmd
    for fam in sorted(combined):
        print(f"{fam}\t{combined[fam]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Producer-file -> claims-family regen manifest")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--producer", help="producer .py path; prints resolved family stems, one per line")
    group.add_argument("--family", help="family stem; prints its regen command, or nothing if unresolved")
    group.add_argument("--all", action="store_true", help="print every family -> regen command (audit)")
    args = parser.parse_args(argv)

    if args.all:
        _print_all()
        return 0
    if args.producer:
        for fam in family_for_producer(args.producer):
            print(fam)
        return 0
    cmd = regen_command_for_family(args.family)
    if cmd:
        print(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
