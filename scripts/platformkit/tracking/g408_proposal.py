"""Static validation helpers for the un-applied G408 interface proposal."""
from __future__ import annotations

import hashlib
from pathlib import Path


REQUIRED_PATHS = (
    "scripts/platformkit/track_daemon.py",
    "scripts/run_clip.py",
    "src/pipeline/unified_pipeline.py",
    "scripts/platformkit/tracking/g203_decode_determinism_bisect.py",
)
LEGACY_FRAME_CAP = 3000


def caller_frame_cap(duration_seconds: float | None,
                     explicit_frames: int | None) -> int | None:
    """Model the proposal's caller precedence without invoking the caller."""
    if explicit_frames is not None:
        return explicit_frames
    return None if duration_seconds is not None else LEGACY_FRAME_CAP


def file_hashes(root: Path) -> dict[str, str]:
    """Hash current proposal bases without opening a source store."""
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in REQUIRED_PATHS}


def validate_proposed_diff(diff_text: str, base_hashes: dict[str, str],
                           root: Path) -> list[str]:
    """Return proposal validation errors; an empty list means static readiness.

    Checks the diff's declared bases against the live bytes, the anchors that
    carry the contract, and that the invariants the prereg names are NOT in any
    changed line: the flush interval, the stride computation and the legacy
    3000 argv value all have to survive untouched.
    """
    errors: list[str] = []
    for path in REQUIRED_PATHS:
        if "--- a/%s" % path not in diff_text or "+++ b/%s" % path not in diff_text:
            errors.append("missing-diff-path:%s" % path)
        expected = base_hashes.get(path)
        actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
        if expected != actual:
            errors.append("base-hash-mismatch:%s" % path)
    for anchor in ("--duration-seconds", "FRAME_CAP", "DEADLINE", "EOF_SHORT",
                   "UNKNOWN", "missing_or_nonfinite_pts",
                   "_pts >= self._pts_deadline", "requested_duration_s",
                   "stop_basis", "first_excluded_pts"):
        if anchor not in diff_text:
            errors.append("missing-anchor:%s" % anchor)
    changed = [line for line in diff_text.splitlines()
               if line[:1] in "+-" and line[:3] not in ("+++", "---")]
    for frozen in ("_VRAM_FLUSH_INTERVAL", "_FRAME_STRIDE_THRESH",
                   "_base_stride", "// _stride"):
        if any(frozen in line for line in changed):
            errors.append("touched-frozen-invariant:%s" % frozen)
    if not any('argv += ["--frames", "3000"]' in line for line in changed):
        errors.append("missing-legacy-frame-cap-preservation")
    return errors



SURVEY_TOKENS = ("build_command", "--frames", "--duration-seconds",
                 "max_frames", "duration_seconds", "total_frames",
                 "evaluated_frames", "requested_duration_s", "stop_basis",
                 "termination_reason", "start_pts", "last_admitted_pts",
                 "first_excluded_pts", "_VRAM_FLUSH_INTERVAL",
                 "_FramePrefetcher", "_decord_frame_iter", "_pyav_frame_iter",
                 "_evaluated_count_sidecar", "_SENTINEL", ".peek(")
SURVEY_ROOTS = ("scripts", "src", "api", "kernel", "tests")
CHANGED_BY_PROPOSAL = {
    "build_command": "signature gains two defaulted keyword arguments",
    "--frames": "argv value unchanged; emitted only when explicit or legacy",
    "--duration-seconds": "new opt-in argument, absent from every legacy argv",
    "max_frames": "unchanged meaning; stays an explicit EARLIER frame cap",
    "duration_seconds": "new additive parameter, default None",
    "_FramePrefetcher": "queue items gain a 4th element; read() shape unchanged",
    "_decord_frame_iter": "yields a 5th element (presentation seconds or None)",
    "_pyav_frame_iter": "yields a 5th element (presentation seconds or None)",
    "_evaluated_count_sidecar": "gains a defaulted duration_seconds argument",
    "_SENTINEL": "unchanged 3-tuple; read() tolerates both item widths",
    ".peek(": "unpacks by index so a 4-wide queue item still works",
}
ALIASES = {"requested_duration_s": "duration_seconds (sidecar spelling)",
           "stop_basis": "new field; legacy runs report frame_count",
           "termination_reason": "new field; legacy runs report EOF/FRAME_CAP",
           "last_admitted_pts": "arm-table spelling of the final admitted PTS",
           "first_excluded_pts": "arm-table spelling of the boundary PTS"}


def survey_readers(root: Path) -> list[dict]:
    """Every live reader of a token the proposal touches, outside evidence."""
    rows = []
    for area in SURVEY_ROOTS:
        for path in sorted((root / area).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if "g408_" in rel or "g401_" in rel:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(lines, 1):
                for token in SURVEY_TOKENS:
                    if token in line:
                        rows.append({"token": token, "path": rel,
                                     "line": number,
                                     "in_proposed_diff": rel in REQUIRED_PATHS,
                                     "changed_by_proposal":
                                         CHANGED_BY_PROPOSAL.get(token, "no"),
                                     "alias_note": ALIASES.get(token, "")})
    return rows
