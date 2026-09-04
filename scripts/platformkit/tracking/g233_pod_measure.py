"""Run G233 transiently on the pod and retrieve its temporary artifact."""
from __future__ import annotations

import argparse
import base64
import hashlib
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATHS = (
    "scripts/platformkit/tracking/g196_homography_from_labelled_corners.py",
    "scripts/platformkit/tracking/g215_temporal_homography_propagation.py",
    "scripts/platformkit/tracking/g222_direct_to_seed_propagation.py",
    "scripts/platformkit/tracking/g233_basketball_seeded_court_coordinates.py",
)
NAMES = tuple(path.replace("/", ".").removesuffix(".py") for path in PATHS)


def _strip_main(source: str) -> str:
    return source.rsplit('\nif __name__ == "__main__":', 1)[0]


def remote_script(frame_count: int) -> str:
    """Build the stdin-only pod run; dd/fsync precedes every measurement write."""
    sources = [(name, _strip_main((ROOT / path).read_text(encoding="utf-8"))) for name, path in zip(NAMES, PATHS)]
    payload = base64.b64encode(repr(sources).encode()).decode("ascii")
    hashes = "\\n".join(f"{hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}  streamed/{path}" for path in PATHS)
    runner = f'''import base64,sys,types
sources=eval(base64.b64decode("{payload}").decode(),{{"__builtins__":{{}}}})
for name,source in sources:
 module=types.ModuleType(name); module.__file__="<stdin>/"+name.replace(".","/")+".py"; sys.modules[name]=module; exec(source,module.__dict__)
sys.argv=["g233","--video","/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4","--output-dir","/tmp/g233_measurement","--frame-count","{frame_count}"]
sys.modules["scripts.platformkit.tracking.g233_basketball_seeded_court_coordinates"].main()
'''
    encoded = base64.b64encode(runner.encode()).decode("ascii")
    return f'''#!/usr/bin/env bash
set -eu
ROOT=/tmp/g233_measurement; PROBE=/tmp/g233_disk_probe
rm -rf "$ROOT" "$PROBE"
du -sm /workspace/nba-ai-system/data > /tmp/g233_pre_du.txt
dd if=/dev/zero of="$PROBE" bs=1M count=4 conv=fsync status=none
rm -f "$PROBE"; mkdir -p "$ROOT"
{{ date -u +%FT%TZ; cat /tmp/g233_pre_du.txt; stat -c '%n|%s' /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4; ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,r_frame_rate -of default=noprint_wrappers=1 /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4; sha256sum /workspace/nba-ai-system/src/tracking/player_detection.py /workspace/nba-ai-system/src/tracking/advanced_tracker.py /workspace/nba-ai-system/src/pipeline/unified_pipeline.py; printf '%s\\n' '{hashes}'; }} > "$ROOT/context.txt"
cd /workspace/nba-ai-system
printf '%s' '{encoded}' | base64 -d | /usr/local/bin/python - > "$ROOT/run.log" 2>&1 || RC=$?
RC=${{RC:-0}}; printf '%s\\n' "$RC" > "$ROOT/exit_code.txt"; du -sb "$ROOT" > "$ROOT/pod_artifact_bytes.txt"
tar -C "$ROOT" -czf - . | base64 -w0
rm -f /tmp/g233_pre_du.txt; rm -rf "$ROOT"; exit "$RC"
'''


def run(output_dir: Path, ssh_config: Path, ssh_host: str, frame_count: int) -> int:
    """Run once, extract the artifact locally, and keep no pod measurement directory."""
    completed = subprocess.run(["ssh", "-F", str(ssh_config), ssh_host, "bash -s"], input=remote_script(frame_count).encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if output_dir.exists() and any(output_dir.iterdir()): raise FileExistsError(output_dir)
    try: archive = tarfile.open(fileobj=BytesIO(base64.b64decode(completed.stdout)), mode="r:gz")
    except Exception as error: raise RuntimeError(completed.stderr.decode("ascii", errors="replace")) from error
    output_dir.mkdir(parents=True, exist_ok=True); archive.extractall(output_dir); (output_dir / "ssh_stderr.txt").write_bytes(completed.stderr)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--ssh-config", type=Path, required=True); parser.add_argument("--ssh-host", default="pod"); parser.add_argument("--frame-count", type=int, default=1200)
    return run(**vars(parser.parse_args()))


if __name__ == "__main__": raise SystemExit(main())
