"""Stream the G233b seed gate to the pod without changing its checkout."""

from __future__ import annotations

import argparse
import base64
import hashlib
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VIDEO = "/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4"
PATHS = (
    "scripts/platformkit/tracking/g196_homography_from_labelled_corners.py",
    "scripts/platformkit/tracking/g233b_ncaa_seed_gate.py",
)


def _strip_main(source: str) -> str:
    return source.rsplit('\nif __name__ == "__main__":', 1)[0]


def remote_script() -> str:
    """Build the one-purpose remote command with its binding write probe."""
    sources = [
        (path.replace("/", ".").removesuffix(".py"), _strip_main((ROOT / path).read_text(encoding="utf-8")))
        for path in PATHS
    ]
    payload = base64.b64encode(repr(sources).encode()).decode("ascii")
    hashes = "\n".join(
        f"{hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}  streamed/{path}" for path in PATHS
    )
    runner = f'''import base64,sys,types
sources=eval(base64.b64decode("{payload}").decode(),{{"__builtins__":{{}}}})
for name,source in sources:
    module=types.ModuleType(name)
    module.__file__="<stdin>/"+name.replace(".","/")+".py"
    sys.modules[name]=module
    exec(source,module.__dict__)
sys.argv=["g233b","--video","{VIDEO}","--output-dir","/tmp/g233b_seed_gate/measurement"]
sys.modules["scripts.platformkit.tracking.g233b_ncaa_seed_gate"].main()
'''
    encoded = base64.b64encode(runner.encode("ascii")).decode("ascii")
    return f'''#!/usr/bin/env bash
set -eu
ROOT=/tmp/g233b_seed_gate
PROBE=/tmp/g233b_seed_gate_disk_probe
if [ -e "$ROOT" ] || [ -e "$PROBE" ]; then
    exit 73
fi
BASELINE=$(du -sm /workspace/nba-ai-system/data)
dd if=/dev/zero of="$PROBE" bs=1M count=4 conv=fsync status=none
rm -f "$PROBE"
mkdir -p "$ROOT"
cleanup() {{ rm -rf "$ROOT"; rm -f "$PROBE"; }}
trap cleanup EXIT
{{ date -u +%FT%TZ; printf '%s\\n' "$BASELINE"; stat -c '%n|%s' "{VIDEO}"; ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,avg_frame_rate -of default=noprint_wrappers=1 "{VIDEO}"; printf '%s\\n' '{hashes}'; }} > "$ROOT/context.txt"
cd /workspace/nba-ai-system
set +e
printf '%s' '{encoded}' | base64 -d | /usr/local/bin/python - > "$ROOT/run.log" 2>&1
RC=$?
set -e
printf '%s\\n' "$RC" > "$ROOT/exit_code.txt"
du -sb "$ROOT" > "$ROOT/pod_artifact_bytes.txt"
tar -C "$ROOT" -czf - . | base64 -w0
exit "$RC"
'''


def _extract(archive_bytes: bytes, output_dir: Path) -> None:
    with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        root = output_dir.resolve()
        if any(not (root / member.name).resolve().is_relative_to(root) for member in members):
            raise ValueError("pod archive contains an unsafe path")
        archive.extractall(output_dir)


def run(output_dir: Path, ssh_config: Path, ssh_host: str) -> int:
    """Run once, retrieve the transient artifact, and retain no pod directory."""
    if output_dir.exists():
        raise FileExistsError(output_dir)
    completed = subprocess.run(
        ["ssh", "-F", str(ssh_config), ssh_host, "bash -s"],
        input=remote_script().encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    try:
        _extract(base64.b64decode(completed.stdout), output_dir)
    except Exception as error:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace")) from error
    (output_dir / "ssh_stderr.txt").write_bytes(completed.stderr)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--ssh-config", required=True, type=Path)
    parser.add_argument("--ssh-host", default="pod")
    return run(**vars(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
