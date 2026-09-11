"""Construct-only exercise of the G401 proposed daemon cap path.

Nothing here launches the daemon or the tracker. The candidate `build_command`
is compiled out of the proposal text with AST surgery, exactly like G393, and
its argv is parsed by the UNCHANGED run_clip parser to prove additivity.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g393_parser_harness import extract_parser
from scripts.platformkit.tracking.source_timebase import probe_status

DAEMON = "scripts/platformkit/track_daemon.py"
WANTED_FUNCTIONS = ("duration_frame_cap", "cap_receipt", "build_command")
WANTED_GLOBALS = ("TRACKING", "CLIP_SPORTS", "SPORT_ADAPTER",
                  "TARGET_DURATION_SECONDS", "LEGACY_FRAME_CAP")

# Sealed before measurement. Each case is (label, fps, probe status).
FIXTURE_CASES = (
    ("fps_30", 30.0, "ok"),
    ("fps_29_97", 29.97002997002997, "ok"),
    ("fps_59_94", 59.94005994005994, "ok"),
    ("fps_60", 60.0, "ok"),
    ("fps_unknown_no_probe", None, None),
    ("fps_variable_parse_failure", 0.0, "failed:parse"),
    ("fps_short_source_60", 60.0, "ok"),
)


def load_candidate(source: str) -> dict[str, Any]:
    """Compile only the cap constants and the three cap functions."""
    tree = ast.parse(source, filename=DAEMON)
    body: list[ast.stmt] = []
    for name in WANTED_GLOBALS:
        matches = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == name
                           for t in node.targets)]
        if len(matches) != 1:
            raise ValueError("unrecognized-global:%s" % name)
        body.append(matches[0])
    for name in WANTED_FUNCTIONS:
        matches = [node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(matches) != 1:
            raise ValueError("unrecognized-function:%s" % name)
        body.append(matches[0])
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    import math
    namespace: dict[str, Any] = {"Path": Path, "sys": sys, "str": str,
                                 "int": int, "list": list, "dict": dict,
                                 "float": float, "isinstance": isinstance,
                                 "math": math, "probe_status": probe_status}
    exec(compile(module, DAEMON, "exec"), namespace)
    return namespace


def fixture_source(fps: float | None, status: str | None) -> dict | None:
    """A probe_source()-shaped dict, or None for the never-probed case."""
    if status is None:
        return None
    return {"source_fps": fps, "source_width": 1280, "source_height": 720,
            "source_resolution": "1280x720", "source_duration": None,
            "status": status}


def build_fixtures(candidate: dict[str, Any], legacy_build,
                   parser) -> list[dict]:
    """Every sealed case: legacy argv, candidate argv, receipt, parse result."""
    video = Path("/workspace/data/footage_bridge/nba__fixture_s90.mp4")
    rows = []
    for label, fps, status in FIXTURE_CASES:
        source = fixture_source(fps, status)
        legacy = legacy_build("nba", video, "fixture_s90")
        argv = candidate["build_command"]("nba", video, "fixture_s90", source)
        receipt = candidate["cap_receipt"](source)
        parsed = parser.parse_args(argv[2:])
        rows.append({
            "case": label, "source_fps": fps, "probe_status": status,
            "legacy_argv": legacy, "candidate_argv": argv,
            "legacy_frames": legacy[legacy.index("--frames") + 1],
            "candidate_frames": argv[argv.index("--frames") + 1],
            "receipt": receipt,
            "argv_parses_with_unchanged_run_clip": True,
            "parsed_frames": parsed.frames,
            "parsed_start_frame": parsed.start_frame,
            "flag_names_added": sorted(set(argv) - set(legacy) -
                                       {argv[argv.index("--frames") + 1]}),
            "default_argv_matches_legacy":
                candidate["build_command"]("nba", video, "fixture_s90") == legacy,
        })
    return rows


def read_parser(run_clip_path: Path):
    """The UNCHANGED run_clip argparse surface."""
    return extract_parser(run_clip_path.read_text(encoding="utf-8"))


# Every name the proposal touches or deliberately preserves. `changed_by_proposal`
# says whether this row's VALUE can move; no row's NAME moves.
SURVEYED = {
    "build_command": "signature gains an optional trailing argument",
    "--frames": "argv value only, when the daemon passes its probe",
    "decoded_frames": "preserved alias, untouched",
    "evaluated_frames": "preserved alias, untouched",
    "source_frame_count": "preserved alias, untouched",
    "evaluated_frame_count": "preserved sidecar name, untouched",
    "max_frames": "preserved run_clip and pipeline name, untouched",
    "_VRAM_FLUSH_INTERVAL": "must not move",
}
SURVEY_ROOTS = ("scripts", "src", "kernel", "api", "intel", "tests")
SURVEY_SUFFIXES = (".py", ".sh")


def reader_survey(root: Path) -> list[dict]:
    """Enumerate every call site of the surveyed cap and count names."""
    rows = []
    for top in SURVEY_ROOTS:
        base = root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in SURVEY_SUFFIXES or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                for token, note in SURVEYED.items():
                    if token in line:
                        rows.append({
                            "token": token,
                            "path": path.relative_to(root).as_posix(),
                            "line": number,
                            "changed_by_proposal": path.as_posix().endswith(
                                "scripts/platformkit/track_daemon.py")
                            and token in ("build_command", "--frames"),
                            "alias_note": note})
    return rows
