"""Select preregistration bytes from committed Git objects before working files."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SealedMapping:
    """One audited reader and the preregistration path it seals."""

    reader_path: str
    sealed_path: str
    revision: str = "HEAD"


@dataclass(frozen=True)
class ObjectSelection:
    """The selected bytes and their committed-object selection state."""

    sealed_path: str
    source: str
    data: bytes | None


class ObjectCheckerError(RuntimeError):
    """A Git or filesystem failure that must not be treated as absence."""


MAPPINGS = (
    SealedMapping("scripts/platformkit/test_s261_ingame_headline_rederive_v2_attempt2.py", "docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md"),
    SealedMapping("scripts/platformkit/ingame/s272_ingame_tail_recal.py", "docs/evidence/harness/S272_ingame_tail_recal_prereg_2026-09-04.md"),
    SealedMapping("scripts/platformkit/ingame/s277_ingame_market_staleness.py", "docs/evidence/harness/S277_ingame_market_staleness_prereg_2026-09-04_attempt2.md"),
    SealedMapping("tests/platformkit/ingame/test_s265_incumbent_conformal_band_sample.py", "docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md"),
    SealedMapping("tests/platformkit/test_s268_distributional_evaluator_route.py", "docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md"),
    SealedMapping("tests/platformkit/test_s270_ingame_power_feasibility.py", "docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md"),
    SealedMapping("tests/platformkit/test_s273_mlb_ingame_latency_screen.py", "docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md"),
    SealedMapping("tests/platformkit/test_s274_mlb_distribution_evaluator_route.py", "docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md"),
)


def _git(root: Path, sealed_path: str, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        raise ObjectCheckerError(f"git unavailable for {sealed_path}: {exc.__class__.__name__}: {exc}") from exc


def _is_proven_absent(result: subprocess.CompletedProcess[bytes], revision: str, sealed_path: str) -> bool:
    """Accept only Git's path-not-in-revision result as an absence proof."""
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    allowed = {
        f"fatal: path '{sealed_path}' exists on disk, but not in '{revision}'",
        f"fatal: path '{sealed_path}' does not exist in '{revision}'",
    }
    return result.returncode == 128 and not result.stdout and stderr in allowed


def select_object_bytes(root: Path, sealed_path: str, revision: str = "HEAD") -> ObjectSelection:
    """Read a committed object, a proven-absent working file, or report absence."""
    object_name = f"{revision}:{sealed_path}"
    probe = _git(root, sealed_path, "cat-file", "-e", object_name)
    if probe.returncode == 0:
        content = _git(root, sealed_path, "cat-file", "-p", object_name)
        if content.returncode != 0:
            detail = content.stderr.decode("utf-8", errors="replace").strip()
            raise ObjectCheckerError(f"cannot read committed object for {sealed_path}: {detail or 'unknown Git error'}")
        return ObjectSelection(sealed_path, "committed", content.stdout)
    if not _is_proven_absent(probe, revision, sealed_path):
        detail = probe.stderr.decode("utf-8", errors="replace").strip()
        raise ObjectCheckerError(f"cannot determine object state for {sealed_path}: {detail or 'unknown Git error'}")
    working_path = root / sealed_path
    if not working_path.exists():
        return ObjectSelection(sealed_path, "absent", None)
    try:
        return ObjectSelection(sealed_path, "fallback", working_path.read_bytes())
    except OSError as exc:
        raise ObjectCheckerError(f"cannot read fallback file for {sealed_path}: {exc.__class__.__name__}: {exc}") from exc


def select_mapping(root: Path, mapping: SealedMapping) -> ObjectSelection:
    """Select bytes for one preregistered reader-to-anchor mapping."""
    return select_object_bytes(root, mapping.sealed_path, mapping.revision)


def _format(selection: ObjectSelection) -> str:
    if selection.data is None:
        return f"ABSENT {selection.sealed_path} -"
    return f"{selection.source.upper()} {selection.sealed_path} {hashlib.sha256(selection.data).hexdigest()}"


def main(argv: list[str] | None = None) -> int:
    """Print selections and return 2 on a repository or object error."""
    parser = argparse.ArgumentParser(description="S303 committed-object checker")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    mappings = tuple(SealedMapping("manual", path, args.revision) for path in args.paths) if args.paths else MAPPINGS
    for mapping in mappings:
        try:
            print(_format(select_mapping(args.root, mapping)))
        except ObjectCheckerError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
