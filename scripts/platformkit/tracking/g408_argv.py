"""Sealed argv fixtures for the un-applied G408 build_command proposal.

The proposed caller precedence is modelled here in isolation, so the eight
sealed cases can be exercised WITHOUT importing or invoking the daemon.  The
legacy shape (no duration) must stay byte-identical to the landed argv.
"""
from __future__ import annotations

LEGACY_FRAME_CAP = "3000"

CASES = (
    ("fps_30", 30.0, 100.0, None),
    ("fps_29_97", 29.97, 100.0, None),
    ("fps_59_94", 59.94005994005994, 100.0, None),
    ("fps_60", 60.0, 100.0, None),
    ("fps_25", 25.0, 100.0, None),
    ("fps_unknown", None, 100.0, None),
    ("fps_variable", None, 100.0, None),
    ("short_source", 59.94005994005994, 100.0, None),
    ("legacy_no_duration", 59.94005994005994, None, None),
    ("explicit_frames_with_duration", 59.94005994005994, 100.0, 900),
    ("explicit_frames_no_duration", 59.94005994005994, None, 900),
)


def proposed_argv(python: str, video: str, game_id: str, tracking_dir: str,
                  duration_seconds: float | None = None,
                  frames: int | None = None) -> list[str]:
    """Model the proposed clip argv.  Mirrors the proposed build_command body."""
    argv = [python, "scripts/run_clip.py", "--video", video,
            "--game-id", game_id, "--no-show"]
    if duration_seconds is not None:
        argv += ["--duration-seconds", str(duration_seconds)]
    if frames is not None:
        argv += ["--frames", str(frames)]
    elif duration_seconds is None:
        argv += ["--frames", LEGACY_FRAME_CAP]
    argv += ["--data-dir", tracking_dir]
    return argv


def legacy_argv(python: str, video: str, game_id: str,
                tracking_dir: str) -> list[str]:
    """The landed argv bytes, reproduced for the byte-identity fixture."""
    return [python, "scripts/run_clip.py", "--video", video,
            "--game-id", game_id, "--no-show", "--frames", LEGACY_FRAME_CAP,
            "--data-dir", tracking_dir]


def fixtures(python: str = "python", video: str = "V", game_id: str = "G",
             tracking_dir: str = "D") -> list[dict]:
    """Build every sealed fixture row with its legacy-identity verdict."""
    rows = []
    for name, fps, duration, frames in CASES:
        argv = proposed_argv(python, video, game_id, tracking_dir, duration,
                             frames)
        legacy = legacy_argv(python, video, game_id, tracking_dir)
        rows.append({
            "case": name,
            "source_fps": "UNKNOWN" if fps is None else fps,
            "duration_seconds": "" if duration is None else duration,
            "explicit_frames": "" if frames is None else frames,
            "argv": argv,
            "implicit_3000_present": "--frames" in argv
                                     and argv[argv.index("--frames") + 1]
                                     == LEGACY_FRAME_CAP and frames is None,
            "legacy_identical": argv == legacy,
            "stop_basis": "frame_count" if duration is None
                          else "presentation_pts",
            "earlier_frame_cap": "" if frames is None else frames,
            "deadline_depends_on_fps": False,
        })
    return rows
