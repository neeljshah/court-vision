"""Bounded G220 amateur-game-camera section acquisition, with no pod deploy."""
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


CAP_BYTES = 4_000_000_000
SECTION_SECONDS = 16 * 60
PROBE_BYTES = 4 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 30
STAGE = Path("data/videos/g220_amateur_footage")
RECORDS = Path("docs/evidence/tracking/g220_amateur_footage_acquisition_2026-09-04_records.json")


@dataclass(frozen=True)
class Candidate:
    youtube_id: str
    duration_seconds: int
    expected_height: int
    sport: str
    description: str


CANDIDATES = (
    Candidate("jh3fnwMi7dM", 8845, 1080, "basketball", "Lorain vs Bedford HS"),
    Candidate("qpZfGp_fScU", 4190, 720, "basketball", "Bismarck HS at Dickinson"),
    Candidate("1MwO3CDkeeM", 1858, 1080, "basketball", "Bremen at Triton fifth grade"),
    Candidate("3asBuhRd_LI", 1772, 1080, "basketball", "Pella eighth grade vs Newton"),
    Candidate("lAs8JaoWNwg", 4770, 720, "soccer", "GACS mens soccer"),
    Candidate("XwpLBtt1G2g", 3869, 1080, "soccer", "Nepean Hotspurs U15-16"),
)


def _remote(command: str, timeout: int = 300) -> str:
    result = footage_bridge._ssh(command, timeout=timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout or "no pod output").strip()[-240:]
        raise RuntimeError("pod command failed rc=%d: %s" % (result.returncode, detail))
    return (result.stdout or "").strip()


def pod_snapshot() -> str:
    """Return the lightweight start-load observation without process matching."""
    return _remote(
        "printf 'utc='; date -u +%Y-%m-%dT%H:%M:%SZ; "
        "printf ' load='; uptime; "
        "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total "
        "--format=csv,noheader 2>&1",
    )


def disk_guard(label: str) -> dict[str, Any]:
    """Perform G220's durable remote dd probe and authoritative data-size read."""
    probe = "/workspace/nba-ai-system/data/.g220_dd_%s" % label
    command = (
        "set -e; probe=%s; dd if=/dev/zero of=$probe bs=1M count=4 conv=fsync "
        "status=none; bytes=$(wc -c <$probe); rm -f $probe; "
        "printf 'dd_bytes=%s data_du_mb=' $bytes; du -sm /workspace/nba-ai-system/data"
        % (probe, "%s")
    )
    text = _remote(command)
    parts = text.split()
    values = dict(part.split("=", 1) for part in parts if "=" in part)
    du_mb = int(values.get("data_du_mb", "-1"))
    if int(values.get("dd_bytes", "0")) != PROBE_BYTES or du_mb < 0:
        raise RuntimeError("invalid disk guard result: %s" % text)
    return {"label": label, "dd_bytes": PROBE_BYTES, "data_du_mb": du_mb,
            "raw": text}


def video_resolution(video: Path) -> str:
    """Return the actual first-stream resolution for the evidence record."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True, timeout=60,
        creationflags=footage_bridge._NO_WINDOW,
    )
    width, height = (result.stdout or "").strip().splitlines()[0].split(",")
    return "%sx%s" % (width, height)


def section_for(candidate: Candidate) -> str:
    """Use the bridge planner but reject an unbounded candidate rather than fetch it."""
    section = footage_bridge.plan_section(candidate.duration_seconds)
    if not section:
        raise RuntimeError("no bounded 16-minute section for %s" % candidate.youtube_id)
    return section


def download_command(candidate: Candidate, destination: Path, section: str,
                     rung: str, remaining_bytes: int) -> list[str]:
    """Build one cookie-backed section command from the bridge's reviewed ladder."""
    return [
        "yt-dlp", "--merge-output-format", "mp4", "--no-part", "--no-playlist",
        "--cookies", str(footage_bridge.COOKIES), "--socket-timeout", "20",
        "--download-sections", section,
        "--max-filesize", str(remaining_bytes), "-f", rung, "-o", str(destination),
        "https://www.youtube.com/watch?v=" + candidate.youtube_id,
    ]


def _produced(destination: Path) -> Path | None:
    return footage_bridge._resolve_download(destination)


def _remove_run_parts(stage: Path) -> int:
    freed = 0
    for path in stage.glob("g220__*.part"):
        try:
            freed += path.stat().st_size
            path.unlink()
        except OSError:
            continue
    return freed


def _gate_payload(video: Path, sport: str) -> dict[str, Any]:
    verdict = footage_content_gate.screen_fail_open(video, sport)
    return {"decision": verdict.decision, "reason": verdict.reason,
            "metrics": asdict(verdict.metrics)}


def acquire_one(candidate: Candidate, stage: Path, used_bytes: int) -> dict[str, Any]:
    """Fetch exactly one planned section, never upload it or enqueue tracking."""
    before = disk_guard(candidate.youtube_id + "_before")
    record: dict[str, Any] = {"candidate": asdict(candidate), "before_guard": before,
                               "section": section_for(candidate), "rung": None,
                               "outcome": "unavailable", "bytes": 0, "height": 0}
    destination = stage / ("g220__%s.mp4" % candidate.youtube_id)
    try:
        if not footage_bridge.COOKIES.is_file():
            record["error"] = "youtube cookies unavailable; refusing 360p section fallback"
            return record
        remaining = CAP_BYTES - used_bytes
        if remaining <= 0:
            record["outcome"] = "skipped_cap"
            record["error"] = "4,000 MB cap reached before candidate"
            return record
        for rung in footage_bridge.FORMAT_RUNGS[:1]:
            record["rung"] = rung
            result = subprocess.run(
                download_command(candidate, destination, record["section"], rung, remaining),
                capture_output=True, text=True, timeout=FETCH_TIMEOUT_SECONDS,
                creationflags=footage_bridge._NO_WINDOW,
            )
            video = _produced(destination)
            if result.returncode or video is None:
                record["error"] = footage_bridge._error_tail(result.stderr, result.stdout)
                continue
            size = video.stat().st_size
            record.update({"local_path": str(video), "bytes": size,
                           "absolute_path": str(video.resolve()),
                           "height": video_height(video),
                           "resolution": video_resolution(video),
                           "content_gate": _gate_payload(video, candidate.sport)})
            if size > remaining:
                record.update({"outcome": "cap_exceeded_removed",
                               "error": "section exceeded remaining hard cap"})
                video.unlink(missing_ok=True)
            elif record["height"] < 720:
                record.update({"outcome": "resolution_failure_removed",
                               "error": "section below 720p"})
                video.unlink(missing_ok=True)
            else:
                record["outcome"] = "acquired"
            return record
        return record
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        record["error"] = str(exc)[:300]
        return record
    finally:
        record["part_bytes_freed"] = _remove_run_parts(stage)
        record["after_guard"] = disk_guard(candidate.youtube_id + "_after")


def write_records(records: Path, payload: dict[str, Any]) -> None:
    """Persist the evolving one-shot record so an interrupted fetch remains auditable."""
    records.parent.mkdir(parents=True, exist_ok=True)
    records.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def acquire_all(candidates: Iterable[Candidate], stage: Path = STAGE,
                records: Path | None = None) -> dict[str, Any]:
    """Run G220's exhaustive reviewed construct, stopping before a new cap breach."""
    stage.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"pod_start_load": pod_snapshot(), "cap_bytes": CAP_BYTES,
                               "section_seconds": SECTION_SECONDS, "records": []}
    if records is not None:
        write_records(records, payload)
    used = 0
    for candidate in candidates:
        if used >= CAP_BYTES:
            payload["records"].append({"candidate": asdict(candidate), "outcome": "skipped_cap"})
            continue
        record = acquire_one(candidate, stage, used)
        payload["records"].append(record)
        used += int(record.get("bytes", 0))
        if records is not None:
            write_records(records, payload)
    payload["running_total_bytes"] = used
    payload["part_bytes_freed"] = _remove_run_parts(stage)
    if records is not None:
        write_records(records, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="G220 bounded amateur footage acquisition")
    parser.add_argument("--stage", type=Path, default=STAGE)
    parser.add_argument("--records", type=Path, default=RECORDS)
    args = parser.parse_args()
    payload = acquire_all(CANDIDATES, args.stage, args.records)
    print("g220 candidates=%d acquired=%d bytes=%d" % (
        len(payload["records"]),
        sum(row.get("outcome") == "acquired" for row in payload["records"]),
        payload["running_total_bytes"],
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
