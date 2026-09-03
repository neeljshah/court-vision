"""Per-decoded-frame tracking completeness manifests.

The denominator is supplied by a decoder or ``ffprobe -count_frames``.  CSV
rows are used only to decide whether an already-decoded frame was solved;
they must never establish the frame count.
"""
from __future__ import annotations

import csv
import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


NON_PLAY = "non_play"
SOLVED = "solved"
UNSOLVED = "unsolved"
_STATUSES = {NON_PLAY, SOLVED, UNSOLVED}
_LOG = logging.getLogger(__name__)
# Container duration is rounded to a finite decimal representation, so a
# constant-frame-rate stream can land fractionally either side of its last
# frame. One frame admits that endpoint rounding without accepting a material
# metadata/count disagreement.
_METADATA_COUNT_TOLERANCE_FRAMES = 1.0


@dataclass(frozen=True)
class FrameManifestRow:
    """The status of one decoded frame."""

    frame_index: int
    status: str


@dataclass(frozen=True)
class CompletenessSummary:
    """Counts and denominator-derived completeness for a decoded video."""

    decoded: int
    solved: int
    unsolved: int
    non_play: int
    completeness: float

    def with_accuracy(self, accuracy: float) -> "CompletenessAccuracy":
        """Attach independently measured solved-frame accuracy to this summary."""
        if not 0.0 <= accuracy <= 1.0:
            raise ValueError("accuracy must be between zero and one")
        return CompletenessAccuracy(self.completeness, float(accuracy))


@dataclass(frozen=True)
class CompletenessAccuracy:
    """Keep coverage and solved-frame accuracy separate, plus their product."""

    completeness: float
    accuracy_on_solved_frames: float

    @property
    def completeness_times_accuracy(self) -> float:
        """Return the compound hook without redefining accuracy over missing frames."""
        return self.completeness * self.accuracy_on_solved_frames


@dataclass(frozen=True)
class DecodeManifest:
    """One status row per decoded frame and the corresponding summary."""

    rows: tuple[FrameManifestRow, ...]
    summary: CompletenessSummary

    def write_csv(self, path: str | Path) -> None:
        """Write the frame-level manifest as CSV."""
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=("frame_index", "status"))
            writer.writeheader()
            writer.writerows(asdict(row) for row in self.rows)

    def write_summary(self, path: str | Path, accuracy: float | None = None) -> None:
        """Write the four counts and optional independent accuracy hook as JSON."""
        payload = asdict(self.summary)
        if accuracy is not None:
            compound = self.summary.with_accuracy(accuracy)
            payload.update(asdict(compound))
            payload["completeness_times_accuracy"] = compound.completeness_times_accuracy
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


NonPlayClassifier = Callable[[int], bool]


def _positive_integer(value: object) -> int | None:
    """Return a positive integer metadata value, never a rounded estimate."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if not isinstance(value, str) or not value.isdecimal():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _positive_float(value: object) -> float | None:
    """Return a finite positive metadata number."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0.0 and parsed != float("inf") else None


def _frame_rate(value: object) -> float | None:
    """Parse ffprobe's rational frame rate without rounding it."""
    if not isinstance(value, str):
        return None
    numerator, separator, denominator = value.partition("/")
    if not separator:
        return None
    top = _positive_float(numerator)
    bottom = _positive_float(denominator)
    return top / bottom if top is not None and bottom is not None else None


def _metadata_frame_count(video_path: str | Path, ffprobe: str) -> tuple[int | None, str]:
    """Return a duration-consistent metadata count, or its fallback reason."""
    command = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames,r_frame_rate,duration:format=duration",
        "-of", "json", str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, ValueError, TypeError):
        return None, "unreadable metadata"
    streams = payload.get("streams")
    container = payload.get("format")
    if not isinstance(streams, list) or not streams:
        return None, "missing stream metadata"
    container_duration = container.get("duration") if isinstance(container, dict) else None
    candidates: list[tuple[int, float]] = []
    for stream in streams:
        if not isinstance(stream, dict):
            return None, "invalid stream metadata"
        count = _positive_integer(stream.get("nb_frames"))
        rate = _frame_rate(stream.get("r_frame_rate"))
        duration = _positive_float(stream.get("duration", container_duration))
        if count is None or rate is None or duration is None:
            return None, "missing positive metadata"
        expected = duration * rate
        if abs(count - expected) > _METADATA_COUNT_TOLERANCE_FRAMES:
            return None, "metadata disagrees with duration and frame rate"
        candidates.append((count, expected))
    counts = {count for count, _expected in candidates}
    if len(counts) != 1:
        return None, "ambiguous metadata counts"
    count, expected = candidates[0]
    _LOG.info("decoded_frame_count path=metadata video=%s count=%d expected=%.6f tolerance_frames=%.1f",
              video_path, count, expected, _METADATA_COUNT_TOLERANCE_FRAMES)
    return count, "metadata"


def decoded_frame_count(video_path: str | Path, ffprobe: str = "ffprobe") -> int:
    """Read a validated metadata count, or decode frames when metadata is unsafe."""
    metadata_count, reason = _metadata_frame_count(video_path, ffprobe)
    if metadata_count is not None:
        return metadata_count
    _LOG.info("decoded_frame_count path=decode_fallback video=%s reason=%s", video_path, reason)
    command = [
        ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1",
        str(video_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    values = [line.strip() for line in result.stdout.splitlines() if line.strip() and line.strip() != "N/A"]
    unique_values = set(values)
    # MPEG-TS exposes a selected stream both inside its program and in the
    # top-level stream list.  The default ffprobe writer emits the identical
    # count twice in that case.  Deduplicate only identical reports: differing
    # values remain ambiguous and must not select a stream by position.
    if len(unique_values) != 1:
        raise ValueError("ffprobe did not return exactly one decoded-frame count")
    count = int(unique_values.pop())
    if count < 0:
        raise ValueError("decoded frame count must be non-negative")
    return count


def emitted_frame_indices(csv_path: str | Path, frame_column: str = "frame") -> set[int]:
    """Return the distinct emitted frame indices, retaining no adapter values."""
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or frame_column not in reader.fieldnames:
            raise ValueError("tracking CSV requires a '{}' column".format(frame_column))
        frames: set[int] = set()
        for number, row in enumerate(reader, start=2):
            try:
                value = int(str(row[frame_column]).strip())
            except (TypeError, ValueError) as error:
                raise ValueError("invalid frame index at CSV row {}".format(number)) from error
            frames.add(value)
    return frames


def build_decode_manifest(
    decoded: int,
    tracking_csv: str | Path,
    non_play: NonPlayClassifier | None = None,
    *,
    frame_column: str = "frame",
) -> DecodeManifest:
    """Build one row per decoded frame from an independent decoder denominator.

    ``non_play`` receives only a frame index.  It must be a closure over
    decoder-side signals (pixels, shot-boundary labels, or metadata produced
    during decoding), never CSV contents, adapter output, homography, detector
    counts, or motion tests.  A non-play decision takes precedence over an
    emitted row so excluded frames cannot inflate completeness.
    """
    if decoded < 0:
        raise ValueError("decoded must be non-negative")
    emitted = emitted_frame_indices(tracking_csv, frame_column)
    invalid = sorted(index for index in emitted if index < 0 or index >= decoded)
    if invalid:
        raise ValueError("emitted frame index outside decoded range: {}".format(invalid[0]))
    classifier = non_play or (lambda _frame_index: False)
    rows: list[FrameManifestRow] = []
    counts = {status: 0 for status in _STATUSES}
    for frame_index in range(decoded):
        status = NON_PLAY if classifier(frame_index) else (SOLVED if frame_index in emitted else UNSOLVED)
        rows.append(FrameManifestRow(frame_index, status))
        counts[status] += 1
    total = counts[SOLVED] + counts[UNSOLVED] + counts[NON_PLAY]
    if total != decoded:
        raise AssertionError("manifest rows do not equal decoded frame count")
    in_play = counts[SOLVED] + counts[UNSOLVED]
    completeness = counts[SOLVED] / in_play if in_play else 0.0
    summary = CompletenessSummary(decoded, counts[SOLVED], counts[UNSOLVED], counts[NON_PLAY], completeness)
    return DecodeManifest(tuple(rows), summary)


def build_from_decoder(
    video_path: str | Path,
    tracking_csv: str | Path,
    non_play: NonPlayClassifier | None = None,
    *,
    frame_column: str = "frame",
) -> DecodeManifest:
    """Count frames with ffprobe, then build a tracking-independent manifest."""
    return build_decode_manifest(decoded_frame_count(video_path), tracking_csv, non_play, frame_column=frame_column)


def status_rows(manifest: DecodeManifest) -> Iterable[FrameManifestRow]:
    """Expose rows for callers that stream them to a storage format."""
    return iter(manifest.rows)
