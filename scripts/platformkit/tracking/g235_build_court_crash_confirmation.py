"""Run the G235 _build_court observation and in-process guard experiment."""
from __future__ import annotations

import argparse
import base64
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path


VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
POD_ROOT = "/workspace/nba-ai-system"
ROUTE_FILES = (
    "scripts/run_clip.py",
    "src/pipeline/unified_pipeline.py",
    "scripts/platformkit/track_daemon.py",
)


def patched_method_source(guard: bool) -> str:
    """Return stdin-only Python which instruments one run without source writes."""
    guard_flag = "True" if guard else "False"
    return f'''import csv, inspect, json, os, runpy, sys, textwrap, traceback
from dataclasses import asdict
from pathlib import Path

MODE = "guarded" if {guard_flag} else "reproduction"
DATA_DIR = os.environ["G235_DATA_DIR"]
REPORT = Path(os.environ["G235_REPORT"])
from src.pipeline.unified_pipeline import UnifiedPipeline

original = UnifiedPipeline._build_court
captured = {{}}

def _shape(value):
    return None if value is None else [int(item) for item in value.shape]

def _dtype(value):
    return None if value is None else str(value.dtype)

def _capture(values):
    rectified = values.get("rectified")
    map_img = values.get("map_img")
    pano_ok = bool(values.get("_pano_ok"))
    if not pano_ok:
        fallback = "pano_empty"
    elif rectified is None:
        fallback = "rectification_exception"
    elif "_rotated" in values and values.get("_rw") == 940 and values.get("_rh") == 500:
        fallback = "portrait_forced_default"
    else:
        fallback = "none"
    captured.update({{
        "rectified_shape": _shape(rectified), "rectified_dtype": _dtype(rectified),
        "rw": values.get("_rw"), "rh": values.get("_rh"),
        "map_img_shape": _shape(map_img), "map_img_dtype": _dtype(map_img),
        "pano_ok": pano_ok, "existing_fallback": fallback,
    }})

source = textwrap.dedent(inspect.getsource(original))
needle = "map_2d = cv2.resize(map_img, (_rw, _rh))"
if needle not in source:
    raise RuntimeError("G235 observation insertion point not found")
source = source.replace(needle, "_capture(locals())\\n    " + needle, 1)
if {guard_flag}:
    shape_line = "                _rh, _rw = rectified.shape[:2]"
    guard_block = shape_line + "\\n                if _rw <= 0 or _rh <= 0:\\n                    _rw, _rh = 940, 500"
    if shape_line not in source:
        raise RuntimeError("G235 guard insertion point not found")
    source = source.replace(shape_line, guard_block, 1)
namespace = dict(original.__globals__)
namespace["_capture"] = _capture
exec(source, namespace)
UnifiedPipeline._build_court = namespace["_build_court"]
argv = ["scripts/run_clip.py", "--video", "{VIDEO}", "--game-id", "g235_" + MODE,
        "--no-show", "--frames", "3000", "--data-dir", DATA_DIR]
outcome = {{"mode": MODE, "command": argv, "captured": None, "exception": None,
           "system_exit": None, "rows": 0, "harness": None}}
try:
    sys.argv = argv
    runpy.run_path("scripts/run_clip.py", run_name="__main__")
except SystemExit as exc:
    outcome["system_exit"] = int(exc.code) if isinstance(exc.code, int) else 1
except BaseException as exc:
    outcome["exception"] = {{"type": type(exc).__name__, "message": str(exc),
                            "traceback": traceback.format_exc()}}
finally:
    UnifiedPipeline._build_court = original
outcome["captured"] = captured or None
csv_path = Path(DATA_DIR) / "tracking_data.csv"
if csv_path.exists():
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        outcome["rows"] = sum(1 for _ in csv.DictReader(handle))
    if outcome["rows"]:
        import pandas as pd
        from scripts.platformkit.tracking_harness import evaluate
        outcome["harness"] = asdict(evaluate(pd.read_csv(csv_path), "wnba", source=str(csv_path)))
REPORT.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\\n", encoding="ascii")
print("G235_MODE=" + MODE)
print("G235_ROWS=" + str(outcome["rows"]))
print("G235_EXCEPTION=" + str(outcome["exception"] is not None))
'''


def remote_script(mode: str) -> str:
    """Build one pod experiment with a binding write probe and full cleanup."""
    if mode not in {"reproduction", "guarded"}:
        raise ValueError(mode)
    runner = base64.b64encode(patched_method_source(mode == "guarded").encode("ascii")).decode("ascii")
    root = f"/tmp/g235_{mode}"
    data_dir = f"{POD_ROOT}/data/tracking/g235_{mode}_20260904"
    quoted_routes = " ".join(f"{POD_ROOT}/{path}" for path in ROUTE_FILES)
    return f'''#!/usr/bin/env bash
set -u
ROOT={root}
DATA_DIR={data_dir}
PROBE=/tmp/g235_disk_probe_{mode}
rm -rf "$ROOT" "$DATA_DIR"
PRE_DU=$(du -sm {POD_ROOT}/data)
dd if=/dev/zero of="$PROBE" bs=1M count=4 conv=fsync status=none
PROBE_RC=$?
rm -f "$PROBE"
if [ "$PROBE_RC" -ne 0 ]; then exit "$PROBE_RC"; fi
mkdir -p "$ROOT"
mkdir -p "$DATA_DIR"
{{
  printf 'mode=%s\\n' '{mode}'
  date -u +started_utc=%FT%TZ
  printf 'pre_du=%s\\n' "$PRE_DU"
  printf 'disk_probe=dd_4MiB_conv_fsync_success\\n'
  stat -c 'source=%n|bytes=%s' {VIDEO}
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,r_frame_rate -of default=noprint_wrappers=1 {VIDEO}
  sha256sum {quoted_routes}
}} > "$ROOT/context.txt"
cd {POD_ROOT}
G235_DATA_DIR="$DATA_DIR" G235_REPORT="$ROOT/report.json" printf '%s' '{runner}' | base64 -d | env G235_DATA_DIR="$DATA_DIR" G235_REPORT="$ROOT/report.json" /usr/local/bin/python - > "$ROOT/run.log" 2>&1
RUN_RC=$?
printf 'run_exit_code=%s\\n' "$RUN_RC" >> "$ROOT/context.txt"
if [ -d "$DATA_DIR" ]; then DATA_BYTES=$(du -sb "$DATA_DIR" | awk '{{print $1}}'); else DATA_BYTES=0; fi
ROOT_BYTES=$(du -sb "$ROOT" | awk '{{print $1}}')
printf 'temporary_root_bytes=%s\\ntracking_directory_bytes=%s\\nbytes_freed_expected=%s\\n' "$ROOT_BYTES" "$DATA_BYTES" "$((ROOT_BYTES + DATA_BYTES))" > "$ROOT/cleanup.txt"
tar -C /tmp -czf - "$(basename "$ROOT")" -C {POD_ROOT}/data/tracking "$(basename "$DATA_DIR")" 2>/dev/null | base64 -w0
TAR_RC=${{PIPESTATUS[0]}}
rm -rf "$ROOT" "$DATA_DIR"
exit "$TAR_RC"
'''


def run(mode: str, output_dir: Path, ssh_config: Path, ssh_host: str) -> None:
    """Execute one experiment and extract its returned temporary artifact locally."""
    if output_dir.exists():
        raise FileExistsError(output_dir)
    completed = subprocess.run(
        ["ssh", "-F", str(ssh_config), ssh_host, "bash -s"],
        input=remote_script(mode).encode("ascii"), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace"))
    try:
        archive = tarfile.open(fileobj=BytesIO(base64.b64decode(completed.stdout)), mode="r:gz")
    except Exception as exc:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace")) from exc
    output_dir.mkdir(parents=True)
    archive.extractall(output_dir)
    (output_dir / "ssh_stderr.txt").write_bytes(completed.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("reproduction", "guarded"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--ssh-host", default="pod")
    args = parser.parse_args()
    run(args.mode, args.output_dir, args.ssh_config, args.ssh_host)


if __name__ == "__main__":
    main()
