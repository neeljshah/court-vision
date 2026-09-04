"""One-shot G220c acquisition: merged 720p sections or local bounded cuts."""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.platformkit import footage_bridge
from scripts.platformkit import footage_content_gate
from scripts.platformkit.section_fallback import video_height


LOCAL_CAP_BYTES = 20_000_000_000
POD_CAP_BYTES = 4_000_000_000
SECTION_SECONDS = 16 * 60
SECTION_TIMEOUT_SECONDS = 90
WHOLE_FETCH_TIMEOUT_SECONDS = 900
CUT_TIMEOUT_SECONDS = 180
MERGING_SELECTOR = "bv*[height<=720][vcodec^=avc1]+ba/b[height<=720]"
STAGE = Path("data/videos/g220c_amateur_footage")
RECORDS = Path("docs/evidence/tracking/g220c_amateur_footage_working_rung_2026-09-04_records.json")
FRAMES = Path("docs/evidence/tracking/g220c_amateur_footage_working_rung_2026-09-04_frames")


@dataclass(frozen=True)
class Candidate:
    youtube_id: str
    duration_seconds: int
    sport: str


CANDIDATES = (
    Candidate("jh3fnwMi7dM", 8845, "basketball"),
    Candidate("qpZfGp_fScU", 4190, "basketball"),
    Candidate("1MwO3CDkeeM", 1858, "basketball"),
    Candidate("3asBuhRd_LI", 1772, "basketball"),
    Candidate("lAs8JaoWNwg", 4770, "soccer"),
    Candidate("XwpLBtt1G2g", 3869, "soccer"),
)


def section_for(candidate: Candidate) -> str:
    """Return the bridge-planned, exactly 16-minute bounded section."""
    section = footage_bridge.plan_section(candidate.duration_seconds)
    if not section:
        raise RuntimeError("no bounded section")
    return section


def _command(candidate: Candidate, destination: Path, section: str | None,
             remaining: int) -> list[str]:
    command = ["yt-dlp", "--merge-output-format", "mp4", "--no-part", "--no-playlist",
               "--cookies", str(footage_bridge.COOKIES), "--socket-timeout", "20",
               "--max-filesize", str(remaining), "--print", "after_move:%(format_id)s",
               "-f", MERGING_SELECTOR]
    if section:
        command += ["--download-sections", section]
    command += ["-o", str(destination), "https://www.youtube.com/watch?v=" + candidate.youtube_id]
    return command


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run one external command and terminate its own descendant tree on timeout."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, creationflags=footage_bridge._NO_WINDOW)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=30,
                       creationflags=footage_bridge._NO_WINDOW)
        stdout, stderr = process.communicate(timeout=30)
        raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _formats(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("after_move:"):
            return line.split(":", 1)[1].strip()
    return "not reported"


def _resolution(video: Path) -> str:
    result = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=width,height", "-of", "csv=p=0", str(video)], 60)
    if result.returncode:
        raise RuntimeError("ffprobe failed: " + (result.stderr or "")[-160:])
    return (result.stdout or "").strip().splitlines()[0]


def _cut(source: Path, destination: Path, section: str) -> None:
    times = section.lstrip("*").split("-")
    result = _run(["ffmpeg", "-y", "-ss", times[0], "-i", str(source), "-t", "00:16:00",
                   "-c", "copy", str(destination)], CUT_TIMEOUT_SECONDS)
    if result.returncode:
        raise RuntimeError("ffmpeg local cut failed: " + (result.stderr or "")[-160:])


def _frames(video: Path, destination: Path) -> list[str]:
    probe = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                  "default=nw=1:nk=1", str(video)], 60)
    duration = float((probe.stdout or "0").strip())
    if probe.returncode or duration <= 0:
        raise RuntimeError("unable to read slice duration")
    destination.mkdir(parents=True, exist_ok=True)
    names = []
    for index, factor in enumerate((1, 3, 5, 7, 11), 1):
        second = duration * factor / 12
        name = "%02d_%.3fs.jpg" % (index, second)
        result = _run(["ffmpeg", "-y", "-ss", "%.3f" % second, "-i", str(video), "-frames:v",
                       "1", "-vf", "scale=480:-2", "-q:v", "5", str(destination / name)], 60)
        if result.returncode:
            raise RuntimeError("frame seek failed: " + (result.stderr or "")[-120:])
        names.append(str(destination / name))
    return names


def _cleanup(stage: Path) -> int:
    freed = 0
    for path in stage.glob("g220c__*.part"):
        try:
            freed += path.stat().st_size
            path.unlink()
        except OSError:
            pass
    return freed


def acquire_one(candidate: Candidate, stage: Path, prior_downloaded: int) -> dict[str, Any]:
    """Acquire one reviewed candidate locally, never upload or enqueue it."""
    section = section_for(candidate)
    record: dict[str, Any] = {"candidate": asdict(candidate), "section": section,
                               "selector": MERGING_SELECTOR, "route": "section",
                               "outcome": "unavailable", "downloaded_bytes": 0,
                               "uploaded_bytes": 0}
    if not footage_bridge.COOKIES.is_file():
        record["error"] = "cookies unavailable; refused 360p fallback"
        return record
    remaining = LOCAL_CAP_BYTES - prior_downloaded
    if remaining <= 0:
        record.update(outcome="skipped_local_cap", error="20,000 MB local cap reached")
        return record
    slice_path = stage / ("g220c__%s.mp4" % candidate.youtube_id)
    whole_path = stage / ("g220c__%s.whole.mp4" % candidate.youtube_id)
    try:
        section_result = _run(_command(candidate, slice_path, section, remaining), SECTION_TIMEOUT_SECONDS)
        video = footage_bridge._resolve_download(slice_path)
        if not section_result.returncode and video is not None:
            record["format_ids"] = _formats(section_result.stdout or "")
        else:
            record["route"] = "whole_then_local_slice"
            record["section_error"] = footage_bridge._error_tail(section_result.stderr, section_result.stdout)
            whole_result = _run(_command(candidate, whole_path, None, remaining), WHOLE_FETCH_TIMEOUT_SECONDS)
            whole = footage_bridge._resolve_download(whole_path)
            if whole_result.returncode or whole is None:
                record["error"] = footage_bridge._error_tail(whole_result.stderr, whole_result.stdout)
                return record
            record["format_ids"] = _formats(whole_result.stdout or "")
            record["whole_bytes"] = whole.stat().st_size
            _cut(whole, slice_path, section)
            video = footage_bridge._resolve_download(slice_path)
            freed = whole.stat().st_size if whole.exists() else 0
            whole.unlink(missing_ok=True)
            record["local_whole_bytes_freed"] = freed
        if video is None:
            record["error"] = "no merged slice produced"
            return record
        size, height = video.stat().st_size, video_height(video)
        record.update(downloaded_bytes=size, local_path=str(video), resolution=_resolution(video), height=height)
        if height < 720:
            video.unlink(missing_ok=True)
            record.update(outcome="resolution_failure_removed", error="obtained below 720p")
            return record
        record["content_gate"] = {"decision": footage_content_gate.screen_fail_open(video, candidate.sport).decision,
                                  "scope": "ingest only; never a metric denominator"}
        record["frames"] = _frames(video, FRAMES / candidate.youtube_id)
        record["outcome"] = "acquired_local_not_uploaded"
        return record
    except subprocess.TimeoutExpired:
        record["error"] = "bounded external command timeout"
        return record
    except (OSError, RuntimeError, ValueError) as exc:
        record["error"] = str(exc)[:300]
        return record
    finally:
        record["part_bytes_freed"] = _cleanup(stage)


def acquire_all(candidates: Iterable[Candidate], stage: Path = STAGE) -> dict[str, Any]:
    """Run exactly the six reviewed candidates, retaining no pod-side output."""
    stage.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"local_cap_bytes": LOCAL_CAP_BYTES, "pod_cap_bytes": POD_CAP_BYTES,
                               "pod_uploads": "none before acceptance (verifier B5)", "records": []}
    downloaded = 0
    for candidate in candidates:
        record = acquire_one(candidate, stage, downloaded)
        payload["records"].append(record)
        downloaded += int(record.get("downloaded_bytes", 0)) + int(record.get("whole_bytes", 0))
    payload["running_local_download_bytes"] = downloaded
    payload["running_pod_upload_bytes"] = 0
    payload["part_bytes_freed"] = _cleanup(stage)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="G220c local-only one-shot acquisition")
    parser.add_argument("--stage", type=Path, default=STAGE)
    parser.add_argument("--records", type=Path, default=RECORDS)
    args = parser.parse_args()
    payload = acquire_all(CANDIDATES, args.stage)
    args.records.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("g220c candidates=%d local_bytes=%d pod_bytes=0" %
          (len(payload["records"]), payload["running_local_download_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
