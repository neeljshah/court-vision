"""Generic cross-sport footage census: sample every resident clip, triage it.

footage_content_gate only ever screens ONE clip at download time and only
catches "no playing surface anywhere" -- it never re-checks what is already
sitting in the corpus. This tool walks the corpus dirs after the fact and
scores every clip the same way regardless of sport, reusing
footage_content_gate's already-tuned per-sport surface-color ranges (rung 2:
reuse what exists) rather than re-deriving green/tan/court-blue thresholds.

Verdict thresholds (stated up front, not tuned after seeing a result):
  JUNK    surface_frac == 0.0   -- the sport's surface never appears, in any
                                    sampled frame (matches the T5 baseball
                                    finding pattern: "zero green field in N
                                    sampled frames").
  SUSPECT 0.0 < surface_frac < USABLE_SURFACE_FRAC, OR graphic_frac is high
                                    even when surface_frac looks fine (catches
                                    a studio/talking-head clip that occasionally
                                    cuts to a real field).
  USABLE  surface_frac >= USABLE_SURFACE_FRAC and graphic_frac is low.

graphic_frac is a Canny edge-density floor: a frame with almost no edges is a
flat color card, a lower-third graphic, or a tight blurred-background
close-up -- not a wide game shot. It is a cheap proxy, not a classifier; that
is why SUSPECT verdicts get 3 rendered frames for a human to actually look at,
rather than trusting the number.

Run: python -m scripts.platformkit.tracking.footage_census --out-dir docs/evidence/tracking/corpus_census_2026-09-01
"""
from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.footage_content_gate import (
    _surface_fraction,
    is_quarantined,
    quarantine_manual,
)

VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
DEFAULT_DIRS = (Path("data/footage_corpus"), Path("data/videos/bridge"),
                Path("data/videos/reference"))
SAMPLE_COUNT = 24
# yt-dlp's video-only/audio-only partial streams before a merge, e.g.
# game.f137.mp4 -- never a full clip. Same pattern footage_bridge guards on.
_FORMAT_PART = re.compile(r"\.f\d{2,4}\.")
USABLE_SURFACE_FRAC = 0.5
GRAPHIC_SUSPECT_FRAC = 0.5
GRAPHIC_EDGE_FLOOR = 0.02


@dataclass(frozen=True)
class CensusRow:
    clip_id: str
    sport: str
    path: str
    samples: int
    surface_frac: float
    graphic_frac: float
    verdict: str


# Checked longest-first so "ncaa_basketball_x" doesn't split on its own
# internal underscore and read back as the wrong sport "ncaa".
_KNOWN_SPORTS = tuple(sorted(
    ("tennis", "wnba", "npb", "kbo", "soccer", "football", "mlb", "nhl",
     "ncaa_basketball", "cricket", "handball", "volleyball", "baseball"),
    key=len, reverse=True))


def sport_of(path: Path) -> str:
    """Sport label from filename convention: sport__game, sport_game, or sport."""
    stem = path.stem
    for sport in _KNOWN_SPORTS:
        if stem == sport or stem.startswith(sport + "_"):
            return sport
    for separator in ("__", "_"):
        if separator in stem:
            return stem.split(separator, 1)[0]
    return stem


def discover_clips(dirs: list[Path]) -> list[Path]:
    """Full merged clips under the given dirs, excluding quarantine and fragments."""
    clips: list[Path] = []
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if (path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
                    and not _FORMAT_PART.search(path.name)
                    and not is_quarantined(path)):
                clips.append(path)
    return clips


def _edge_density(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    return float(np.mean(edges > 0))


def sample_frames(video: Path, count: int = SAMPLE_COUNT) -> list[np.ndarray]:
    """count evenly spaced frames across the clip, read by seek (cheap)."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("unreadable video: %s" % video)
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total = max(capture.get(cv2.CAP_PROP_FRAME_COUNT), 1.0)
    duration = total / fps
    frames = []
    for fraction in np.linspace(0.05, 0.95, count):
        capture.set(cv2.CAP_PROP_POS_MSEC, duration * fraction * 1000.0)
        ok, frame = capture.read()
        if ok:
            frames.append(cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA))
    capture.release()
    return frames


def verdict_of(surface_frac: float, graphic_frac: float) -> str:
    if surface_frac == 0.0:
        return "JUNK"
    if surface_frac < USABLE_SURFACE_FRAC or graphic_frac >= GRAPHIC_SUSPECT_FRAC:
        return "SUSPECT"
    return "USABLE"


def census_clip(video: Path, sample_count: int = SAMPLE_COUNT
               ) -> tuple[CensusRow, list[np.ndarray]]:
    """Score one clip. Returns the row plus its sampled frames for rendering."""
    sport = sport_of(video)
    frames = sample_frames(video, sample_count)
    if not frames:
        raise ValueError("no readable frames: %s" % video)
    surfaces = [_surface_fraction(frame, sport) for frame in frames]
    graphics = [_edge_density(frame) < GRAPHIC_EDGE_FLOOR for frame in frames]
    surface_frac = sum(value >= 0.015 for value in surfaces) / len(surfaces)
    graphic_frac = sum(graphics) / len(graphics)
    row = CensusRow(video.stem, sport, str(video), len(frames),
                    round(surface_frac, 3), round(graphic_frac, 3),
                    verdict_of(surface_frac, graphic_frac))
    return row, frames


def render_sample(frames: list[np.ndarray], clip_id: str, out_dir: Path) -> None:
    """Write 3 representative frames (first/middle/last sampled) for eye review."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, position in zip((0, len(frames) // 2, len(frames) - 1), ("a", "b", "c")):
        cv2.imwrite(str(out_dir / ("%s_%s.jpg" % (clip_id, position))), frames[index])


def write_csv(rows: list[CensusRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["clip_id", "sport", "path", "samples", "surface_frac",
                         "graphic_frac", "verdict"])
        for row in rows:
            writer.writerow([row.clip_id, row.sport, row.path, row.samples,
                             row.surface_frac, row.graphic_frac, row.verdict])


def run_census(dirs: list[Path], out_dir: Path, sample_count: int = SAMPLE_COUNT,
              do_quarantine: bool = True) -> list[CensusRow]:
    """Census every discovered clip; quarantine JUNK; render SUSPECT frames."""
    rows: list[CensusRow] = []
    for video in discover_clips(dirs):
        try:
            row, frames = census_clip(video, sample_count)
        except (cv2.error, OSError, ValueError) as exc:
            rows.append(CensusRow(video.stem, sport_of(video), str(video), 0,
                                  0.0, 0.0, "SUSPECT:unreadable(%s)" % str(exc)[:60]))
            continue
        rows.append(row)
        if row.verdict == "SUSPECT":
            render_sample(frames, row.clip_id, out_dir)
        elif row.verdict == "JUNK" and do_quarantine:
            quarantine_manual(video, "footage_census_zero_surface_evidence")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dirs", nargs="+", type=Path, default=list(DEFAULT_DIRS))
    parser.add_argument("--out-dir", type=Path,
                        default=Path("docs/evidence/tracking/corpus_census_2026-09-01"))
    parser.add_argument("--sample-count", type=int, default=SAMPLE_COUNT)
    parser.add_argument("--no-quarantine", action="store_true")
    args = parser.parse_args()
    rows = run_census(args.dirs, args.out_dir, args.sample_count,
                      do_quarantine=not args.no_quarantine)
    write_csv(rows, args.out_dir / "census.csv")
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        verdict = row.verdict.split(":")[0]
        counts.setdefault(row.sport, {"USABLE": 0, "SUSPECT": 0, "JUNK": 0})
        counts[row.sport][verdict] = counts[row.sport].get(verdict, 0) + 1
    for sport, tally in sorted(counts.items()):
        total = sum(tally.values())
        print("%s: usable=%d suspect=%d junk=%d of %d" %
              (sport, tally.get("USABLE", 0), tally.get("SUSPECT", 0),
               tally.get("JUNK", 0), total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
