"""kernel_manifest.py — Phase-0 falsification instrument for the tennis second-domain proof.

Hashes the §4.1 kernel files (sha256 per file) and provides freeze/check CLI.
Any hash delta beyond the single whitelisted FLAGS registration line = proof INVALID.

Usage
-----
    python kernel_manifest.py --freeze [--out PATH]
    python kernel_manifest.py --check [--manifest PATH] [--allow-flagline]

CLI exits non-zero and prints violating paths when --check finds any delta.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# §4.1 kernel file list — MUST NOT be edited to make tennis run (falsifier F1)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]  # scripts/platformkit/proof_tennis → repo root

KERNEL_FILES: list[str] = [
    "src/loop/gate.py",
    "src/loop/signal.py",
    "src/loop/ledger.py",
    "src/loop/store.py",
    "src/validation/clv_tracker.py",
    "src/prediction/devig.py",
    "src/prediction/conformal_props.py",
    "src/prediction/quantile_calibration.py",
    "src/pipeline/prediction_calibrator.py",
    "src/prediction/betting_portfolio.py",
    "src/prediction/risk_controls.py",
    "src/prediction/drawdown_tracker.py",
    "src/prediction/walk_forward_backtester.py",
    "src/prediction/bet_grades.py",
    "src/brain/flags.py",
    "src/brain/gate_nmin.py",
    "src/brain/discovery_gate.py",
    "scripts/team_system/signals/gates.py",
    "scripts/team_system/signals/judge.py",
]

DEFAULT_MANIFEST_PATH = (
    _REPO_ROOT / ".planning" / "platform" / "proof_tennis" / "kernel_manifest.sha256"
)

# The only flag name whose addition to src/brain/flags.py is whitelisted.
_ALLOWED_FLAG_NAME = "CV_DOMAIN_TENNIS"

# The kernel file that may receive the single whitelisted registry addition.
_FLAGLINE_FILE = "src/brain/flags.py"


# ---------------------------------------------------------------------------
# Core functions (importable)
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Return hex sha256 of *path*. Raises FileNotFoundError if absent."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_manifest(file_list: list[str], repo_root: Optional[Path] = None) -> dict[str, str]:
    """Hash each path in *file_list* relative to *repo_root*.

    Parameters
    ----------
    file_list:
        Relative posix paths from repo root (e.g. "src/loop/gate.py").
    repo_root:
        Absolute path to repository root.  Defaults to the root inferred
        from this file's location.

    Returns
    -------
    dict mapping relative path → sha256 hex string.

    Raises
    ------
    FileNotFoundError
        If any listed file is absent from the tree (manifest list drift).
    """
    root = repo_root or _REPO_ROOT
    manifest: dict[str, str] = {}
    missing: list[str] = []
    for rel in file_list:
        abs_path = root / Path(rel)
        if not abs_path.exists():
            missing.append(rel)
        else:
            manifest[rel] = _sha256_file(abs_path)
    if missing:
        raise FileNotFoundError(
            f"Kernel manifest drift — {len(missing)} listed file(s) absent from tree:\n"
            + "\n".join(f"  MISSING: {p}" for p in missing)
        )
    return manifest


def check_manifest(
    frozen: dict[str, str],
    current: dict[str, str],
) -> list[str]:
    """Compare *frozen* manifest to *current* manifest.

    Parameters
    ----------
    frozen:
        The baseline manifest loaded from the .sha256 file.
    current:
        Freshly computed manifest (same key set expected).

    Returns
    -------
    List of relative paths whose hash changed (violations).
    An empty list means clean.
    """
    violations: list[str] = []
    all_keys = set(frozen) | set(current)
    for key in sorted(all_keys):
        if key not in frozen:
            violations.append(key)  # new file appeared in manifest list
        elif key not in current:
            violations.append(key)  # file disappeared
        elif frozen[key] != current[key]:
            violations.append(key)
    return violations


def _is_flagline_delta_allowed(
    frozen_hash: str,
    file_rel: str,
    repo_root: Path,
) -> bool:
    """Return True iff the ONLY diff between the frozen file and the current
    file is exactly one added line that is a FLAGS dict entry for
    _ALLOWED_FLAG_NAME, and nothing else changed.

    This implements the §4.1 whitelist: the one-line CV_DOMAIN_TENNIS
    registration is permitted; any other change still fails.
    """
    if file_rel != _FLAGLINE_FILE:
        return False  # whitelist applies only to flags.py

    abs_path = repo_root / Path(file_rel)
    if not abs_path.exists():
        return False

    current_hash = _sha256_file(abs_path)
    if current_hash == frozen_hash:
        return True  # identical — no delta at all; trivially allowed

    # Reconstruct what the file looked like before by stripping the allowed
    # flag block, then re-hash raw bytes.  If that matches the frozen hash,
    # the only change was the CV_DOMAIN_TENNIS addition.
    #
    # We operate on raw bytes split by newlines so that platform-specific
    # line endings (\r\n on Windows) are preserved exactly — the filtered
    # result must be byte-identical to what _sha256_file read on the original.
    #
    # A "flag entry block" looks like:
    #   "CV_DOMAIN_TENNIS": {   (optionally with trailing comma)
    #       ... arbitrary inner lines ...
    #   },
    # We split on b'\n', filter the block, then rejoin — this preserves any
    # \r that precedes \n (i.e. \r\n endings stay intact on each kept line).
    current_raw = abs_path.read_bytes()
    raw_lines: list[bytes] = current_raw.split(b"\n")

    flag_key_bytes = ('"' + _ALLOWED_FLAG_NAME + '"').encode("utf-8")
    filtered_raw: list[bytes] = []
    inside_block = False
    brace_depth = 0
    for raw_line in raw_lines:
        stripped = raw_line.strip()
        if not inside_block and flag_key_bytes in stripped:
            inside_block = True
            brace_depth = stripped.count(b"{") - stripped.count(b"}")
            if brace_depth <= 0:
                inside_block = False
            continue
        if inside_block:
            brace_depth += stripped.count(b"{") - stripped.count(b"}")
            if brace_depth <= 0:
                inside_block = False
            continue
        filtered_raw.append(raw_line)

    filtered_bytes = b"\n".join(filtered_raw)
    filtered_hash = hashlib.sha256(filtered_bytes).hexdigest()
    return filtered_hash == frozen_hash


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "kernel_manifest — freeze and check kernel file hashes for the "
            "tennis second-domain proof (SECOND_DOMAIN_PROOF.md §4.1)."
        )
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--freeze",
        action="store_true",
        help="Compute and write the manifest to --out (default: %(default)s).",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Re-hash kernel files and compare to frozen manifest.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output path for --freeze (default: "
            ".planning/platform/proof_tennis/kernel_manifest.sha256)."
        ),
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to frozen manifest for --check (same default as --out).",
    )
    p.add_argument(
        "--allow-flagline",
        action="store_true",
        dest="allow_flagline",
        help=(
            "When checking, permit a delta in src/brain/flags.py that consists "
            "only of adding the CV_DOMAIN_TENNIS FLAGS entry (the whitelisted "
            "registry addition per §4.1)."
        ),
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point.  Returns exit code (0 = clean, 1 = violations/error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    out_path: Path = args.out or DEFAULT_MANIFEST_PATH
    manifest_path: Path = args.manifest or DEFAULT_MANIFEST_PATH

    if args.freeze:
        try:
            manifest = compute_manifest(KERNEL_FILES)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Manifest frozen: {len(manifest)} files → {out_path}")
        return 0

    # --check
    if not manifest_path.exists():
        print(
            f"ERROR: frozen manifest not found at {manifest_path}. "
            "Run --freeze first.",
            file=sys.stderr,
        )
        return 1
    frozen: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        current = compute_manifest(KERNEL_FILES)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    violations = check_manifest(frozen, current)

    if args.allow_flagline and _FLAGLINE_FILE in violations:
        if _is_flagline_delta_allowed(frozen[_FLAGLINE_FILE], _FLAGLINE_FILE, _REPO_ROOT):
            violations = [v for v in violations if v != _FLAGLINE_FILE]

    if not violations:
        print(f"OK — {len(current)} kernel files unchanged.")
        return 0

    print(f"PROOF INVALID — {len(violations)} kernel file(s) changed:", file=sys.stderr)
    for v in violations:
        print(f"  CHANGED: {v}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
