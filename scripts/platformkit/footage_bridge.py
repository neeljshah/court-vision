"""Download footage on the local (residential) IP, track it on the pod, delete both copies.

Why this exists: YouTube blocks the pod's datacenter IP ("Sign in to confirm
you're not a bot") for every league, while the same cookies work from the local
machine. The pod has the GPU. So the local box is used ONLY as a network hop:
download -> scp -> track on pod -> delete local AND remote copies immediately.
Neither disk ever accumulates video.

Run: python -m scripts.platformkit.footage_bridge --queue data/footage_queue_tennis.json --limit 3
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

POD = ["-o", "StrictHostKeyChecking=no", "-p", "40048", "root@213.192.2.83"]
POD_ROOT = "/workspace/nba-ai-system"
LOCAL_STAGE = Path("data/videos/bridge")
COOKIES = Path("data/videos/youtube_cookies.txt")
SPORT_ADAPTER = {"tennis": "tennis", "soccer": "soccer", "npb": "baseball",
                 "kbo": "baseball", "mlb": "baseball", "baseball": "baseball"}


def _ssh(command: str, timeout: int = 5400) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", *POD, command], capture_output=True, text=True,
                          timeout=timeout)


def already_tracked(game_id: str) -> bool:
    probe = _ssh("test -s %s/data/tracking/%s/tracking_data.csv && echo YES || echo NO"
                 % (POD_ROOT, game_id), timeout=120)
    return "YES" in probe.stdout


def download_local(item: dict) -> Path:
    """Download one item to the local stage, returning the merged file."""
    LOCAL_STAGE.mkdir(parents=True, exist_ok=True)
    target = LOCAL_STAGE / (item["game_id"] + ".mp4")
    command = ["yt-dlp", "--merge-output-format", "mp4", "--no-part",
               "-f", item.get("format") or "bv*[height<=1080][vcodec^=avc1]+ba/b[height<=720]",
               "-o", str(target), item["url"]]
    if COOKIES.is_file():
        command[1:1] = ["--cookies", str(COOKIES)]
    subprocess.run(command, check=True, timeout=5400)
    if target.exists():
        return target
    produced = sorted((p for p in LOCAL_STAGE.glob(target.stem + "*")
                       if p.is_file() and not p.name.endswith(".part")),
                      key=lambda p: p.stat().st_size, reverse=True)
    if not produced:
        raise FileNotFoundError("no local artifact for %s" % item["game_id"])
    return produced[0]


def push_and_track(local: Path, item: dict) -> str:
    """Upload, track on the pod, score, then delete the remote video."""
    game_id, sport = item["game_id"], item["sport"]
    remote = "%s/data/footage/%s%s" % (POD_ROOT, game_id, local.suffix)
    subprocess.run(["scp", "-o", "StrictHostKeyChecking=no", "-P", "40048",
                    str(local), "root@213.192.2.83:" + remote],
                   check=True, timeout=5400)
    adapter = SPORT_ADAPTER.get(sport, sport)
    if adapter in ("wnba", "basketball"):
        track = ("cd %s && PYTHONPATH=%s python scripts/run_clip.py --video %s "
                 "--game-id %s --no-show --frames 18000" % (POD_ROOT, POD_ROOT, remote, game_id))
    else:
        track = ("cd %s && PYTHONPATH=%s python adapter_run.py %s %s %s"
                 % (POD_ROOT, POD_ROOT, adapter, remote, game_id))
    result = _ssh(track)
    _ssh("rm -f %s" % remote, timeout=300)
    ok = _ssh("test -s %s/data/tracking/%s/tracking_data.csv && echo YES || echo NO"
              % (POD_ROOT, game_id), timeout=120)
    return "tracked" if "YES" in ok.stdout else "no_output:" + result.stdout[-160:].replace("\n", " ")


def run(queue_path: Path, limit: int) -> None:
    items = json.loads(queue_path.read_text(encoding="utf-8"))
    done = 0
    for item in items:
        if done >= limit:
            break
        game_id = item["game_id"]
        if already_tracked(game_id):
            continue
        local = None
        try:
            local = download_local(item)
            status = push_and_track(local, item)
        except Exception as exc:  # pragma: no cover - operational path
            status = "failed:%s" % str(exc)[:160]
        finally:
            if local is not None:
                for leftover in LOCAL_STAGE.glob(local.stem + "*"):
                    leftover.unlink(missing_ok=True)
        print("%s %s %s" % (game_id, item["sport"], status), flush=True)
        done += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-download / pod-track bridge")
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    run(args.queue, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
