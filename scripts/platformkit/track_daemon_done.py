"""Durable daemon completion verdicts, separated to keep the daemon small."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

import pandas as pd

from scripts.platformkit.tracking.decode_manifest import (
    build_decode_manifest,
    decoded_frame_count,
)
from scripts.platformkit.tracking_timebase import sampling_plan
from scripts.platformkit.tracking_harness import evaluate


VERDICT_FILE = "harness_verdict.json"
_ADAPTER_MAX_FRAMES = 30000
_REQUIRED = frozenset(("passed", "failure_heads", "coverage_pct",
                       "coordinate_space", "rung", "evaluated_at", "csv_fsynced"))


def tracking_csv(tracking: Path, game_id: str) -> Path:
    """Return the canonical tracking output location for one game."""
    return tracking / game_id / "tracking_data.csv"


def tracking_rows(tracking: Path, game_id: str) -> int:
    """Return CSV data rows, or zero when no readable output exists."""
    path = tracking_csv(tracking, game_id)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    except OSError:
        return 0


def _fsync_csv(path: Path) -> bool:
    try:
        if path.stat().st_size == 0:
            return False
        # Windows rejects fsync on a read-only descriptor; r+b changes no bytes.
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())
        return True
    except OSError:
        return False


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    try:
        with partial.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        partial.replace(path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _coordinate_space(frame: pd.DataFrame) -> str:
    if "coordinate_space" not in frame:
        return "undeclared"
    values = sorted({str(value) for value in frame["coordinate_space"].dropna().unique()})
    return values[0] if len(values) == 1 else "mixed" if values else "undeclared"


def _rung(space: str) -> str:
    if space == "image_px":
        return "IMAGE_PX_DECLARED"
    if space in {"court_feet", "pitch_metres"}:
        return "COURT_FEET" if space == "court_feet" else "METRIC_LOCAL"
    return "UNDECLARED"


def _with_frame_denominator(frame: pd.DataFrame, denominator: range) -> pd.DataFrame:
    emitted = {int(value) for value in frame["frame"].dropna().unique()}
    missing = sorted(set(denominator) - emitted)
    if not missing:
        return frame
    fillers = pd.DataFrame({"frame": missing, "track_id": "__decoded__",
                            "cls": "__decoded__", "x": 0.0, "y": 0.0})
    for column in frame.columns:
        if column not in fillers:
            values = frame[column].dropna().unique()
            fillers[column] = values[0] if len(values) == 1 else None
    return pd.concat((frame, fillers.loc[:, frame.columns]), ignore_index=True)


def _source_fps(frame: pd.DataFrame) -> float | None:
    """Return the uniquely stamped source fps, if completion preparation supplied it."""
    if "source_fps" not in frame:
        return None
    values = pd.to_numeric(frame["source_fps"], errors="coerce").dropna().unique()
    if len(values) != 1 or values[0] <= 0:
        return None
    return float(values[0])


def _evaluated_denominator(decoded: int, source_fps: float | None,
                           max_frames: int = _ADAPTER_MAX_FRAMES) -> tuple[range, int | None]:
    """Return adapter-evaluated source indices and their declared sampling stride."""
    if source_fps is None:
        return range(decoded), None
    stride = sampling_plan(source_fps).stride
    # Adapter loops increment ``processed`` only for source_frame % stride == 0.
    # Its max_frames condition therefore caps evaluated samples, not source reads.
    return range(0, min(decoded, stride * max_frames), stride), stride


# A staged game carries its ACQUISITION label (mlb, kbo, npb, wnba, ncaa_basketball),
# which is a source lane, not a sport the harness scores. tracking_harness.SPORTS
# happens to carry kbo and npb as byte-identical aliases of baseball but has no
# mlb entry, so mlb fell straight through to "unknown sport mlb" and the first new
# MLB game tracked after the footage bridge came back was never quality scored at
# all. Only basketball was being folded here; every baseball feeder was missed.
# This mirrors track_daemon.SPORT_ADAPTER, which cannot be imported from here --
# track_daemon imports adjudicate from this module, so the dependency runs the
# other way and importing back would be a cycle.
HARNESS_SPORT = {
    "wnba": "basketball", "basketball": "basketball",
    "ncaa_basketball": "basketball", "nba": "basketball",
    "mlb": "baseball", "kbo": "baseball", "npb": "baseball",
    "baseball": "baseball",
    # Listed even though they are already their own harness sport. The map is
    # exhaustive on purpose: a fall-through default is what let mlb through, so
    # a new acquisition lane must fail the paired test rather than silently
    # inherit its own name.
    "tennis": "tennis", "soccer": "soccer", "football": "football",
}


def write_adjudicated(tracking: Path, game_id: str, payload: dict) -> None:
    """Atomically publish a completed frozen-harness verdict sidecar."""
    _atomic_json(tracking / game_id / VERDICT_FILE, payload)


def adjudicate(video: Path, sport: str, game_id: str, tracking: Path,
               harness: Callable = evaluate,
               frame_counter: Callable[[Path], int] = decoded_frame_count,
               *, publish: bool = True,
               printer: Callable[[str], None] = print) -> dict | None:
    """Run the frozen harness and optionally publish its per-game sidecar."""
    csv_path = tracking_csv(tracking, game_id)
    if not _fsync_csv(csv_path):
        return None
    try:
        emitted = pd.read_csv(csv_path)
    except Exception as exc:
        # An unreadable table is NOT the same as an unfinished game: both used to
        # return None silently, so a corrupt CSV sat unadjudicated forever with no
        # error anywhere. Say so; the return contract is unchanged.
        printer("adjudicate: unreadable tracking csv %s: %s"
                % (csv_path, str(exc)[:160]))
        return None
    if emitted.empty:
        return None
    failures: list[str] = []
    decoded = 0
    stride: int | None = None
    evaluated_frames: int | None = None
    harness_coverage_pct: float | None = None
    try:
        decoded = frame_counter(video)
        manifest = build_decode_manifest(decoded, csv_path)
        denominator, stride = _evaluated_denominator(decoded, _source_fps(emitted))
        evaluated_frames = len(denominator) if stride is not None else None
        harness_input = _with_frame_denominator(emitted, denominator)
        coverage = manifest.summary.completeness
    except Exception as exc:
        harness_input = emitted
        coverage = 0.0
        failures.append("decoded_frame_denominator: %s" % str(exc)[:120])
    harness_sport = HARNESS_SPORT.get(sport, sport)
    try:
        report = harness(harness_input, harness_sport, source=str(csv_path))
        harness_coverage_pct = float(getattr(report, "coverage_pct", 0.0))
        failures.extend(getattr(report, "failures", []))
        passed = bool(getattr(report, "passed", False)) and not failures
    except Exception as exc:
        failures.append("ungraded: %s" % str(exc)[:120])
        passed = False
    payload = {"passed": passed, "failure_heads": failures[:4],
               "coverage_pct": round(float(coverage), 4),
               "harness_coverage_pct": (round(harness_coverage_pct, 4)
                                        if harness_coverage_pct is not None else None),
               "coordinate_space": _coordinate_space(emitted),
               "rung": _rung(_coordinate_space(emitted)),
               "evaluated_at": int(time.time()), "csv_fsynced": True,
               "decoded_frames": decoded, "evaluated_frames": evaluated_frames,
               "stride": stride}
    if publish:
        write_adjudicated(tracking, game_id, payload)
    return payload


def read_adjudicated(tracking: Path, game_id: str) -> dict | None:
    """Return a durable verdict only when its nonempty CSV exists too."""
    if tracking_rows(tracking, game_id) == 0:
        return None
    try:
        payload = json.loads((tracking / game_id / VERDICT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if _REQUIRED <= payload.keys() and payload["csv_fsynced"] is True else None


def retain(video: Path, corpus: Path, printer: Callable[[str], None]) -> bool:
    """Move footage; a failed move is renamed out of the claimable glob."""
    try:
        corpus.mkdir(parents=True, exist_ok=True)
        video.replace(corpus / video.name)
        return True
    except OSError as exc:
        failed = video.with_name(video.name + ".failed")
        try:
            video.replace(failed)
            printer("retain failed %s: %s -- renamed %s" % (video, exc, failed))
        except OSError as rename_exc:
            printer("retain failed %s: %s; rename failed: %s" %
                    (video, exc, rename_exc))
        return False
