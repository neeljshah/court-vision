"""Run the G238 external homography and panorama observation on the pod."""

from __future__ import annotations

import argparse
import base64
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path


VIDEO = "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
POD_ROOT = "/workspace/nba-ai-system"
ROUTE_FILES = ("scripts/run_clip.py", "src/pipeline/unified_pipeline.py")


def instrumented_source() -> str:
    """Return a stdin-only observer that restores both patched methods on exit."""
    return r'''import csv, hashlib, inspect, json, os, runpy, sys, textwrap, traceback
from pathlib import Path

REPORT = Path(os.environ["G238_REPORT"])
DATA_DIR = os.environ["G238_DATA_DIR"]
from src.pipeline import unified_pipeline as module
from src.pipeline.unified_pipeline import UnifiedPipeline

events = []
pano_record = {}

def capture_event(**record):
    events.append(record)

def capture_pano(source_kind, source_path, image):
    pano_record.update({
        "source_kind": source_kind,
        "source_path": str(source_path),
        "shape_before_padding": [int(value) for value in image.shape],
        "md5_before_padding": hashlib.md5(image.tobytes()).hexdigest(),
    })

original_homography = UnifiedPipeline._get_homography
original_pano = UnifiedPipeline._load_pano
homography_calls = 0

def patched_homography():
    source = textwrap.dedent(inspect.getsource(original_homography))
    source = source.replace(
        "        M, mask = None, None\n",
        "        M, mask = None, None\n        matcher_path = 'none'\n", 1)
    source = source.replace(
        "        if self._kornia_matcher is not None:\n",
        "        if self._kornia_matcher is not None:\n            matcher_path = 'kornia_loftr'\n", 1)
    source = source.replace(
        "        if M is None and hasattr(self, 'sift') and self.sift is not None:\n",
        "        if M is None and hasattr(self, 'sift') and self.sift is not None:\n            matcher_path = 'sift'\n", 1)
    no_matrix = "        if M is None:\n            return self._M_ema\n"
    source = source.replace(no_matrix, "        if M is None:\n            capture_event(kind='no_matrix', matcher=matcher_path, inliers=0, matches=int(mask.size) if mask is not None else 0, tier='no_matrix', installed_m=False, bootstrap=self._M_ema is None)\n            return self._M_ema\n", 1)
    too_few = "        if inliers < min_inliers:\n            return self._M_ema\n"
    source = source.replace(too_few, "        if inliers < min_inliers:\n            capture_event(kind='matched', matcher=matcher_path, inliers=inliers, matches=int(mask.size) if mask is not None else 0, tier='reject_below_floor', installed_m=False, bootstrap=self._M_ema is None, effective_floor=min_inliers)\n            return self._M_ema\n", 1)
    sanity = "            if max(dists) > 99999:  # sanity gate disabled - position-level smoothing used instead\n                return self._M_ema\n"
    if sanity not in source:
        sanity = "            if max(dists) > 99999:  # sanity gate disabled \u2014 position-level smoothing used instead\n                return self._M_ema\n"
    source = source.replace(sanity, sanity.replace("                return self._M_ema", "                capture_event(kind='matched', matcher=matcher_path, inliers=inliers, matches=int(mask.size) if mask is not None else 0, tier='reject_sanity', installed_m=False, bootstrap=False, effective_floor=min_inliers)\n                return self._M_ema"), 1)
    final_return = "        return self._M_ema"
    final_index = source.rfind(final_return)
    record = "        capture_event(kind='matched', matcher=matcher_path, inliers=inliers, matches=int(mask.size) if mask is not None else 0, tier='hard_reset' if (self._M_ema is M or inliers >= module._H_RESET_INLIERS) else 'ema_blend', installed_m=True, bootstrap=self._M_ema is M and inliers < module._H_RESET_INLIERS, effective_floor=min_inliers)\n        return self._M_ema"
    if final_index < 0:
        raise RuntimeError("G238 homography final-return insertion point not found")
    source = source[:final_index] + record + source[final_index + len(final_return):]
    namespace = dict(original_homography.__globals__)
    namespace.update({"capture_event": capture_event, "module": module})
    exec(source, namespace)
    return namespace["_get_homography"]

def patched_pano():
    source = textwrap.dedent(inspect.getsource(original_pano))
    cache = "                print(f\" Pano cache hit: {os.path.basename(cached)}\")\n                return np.vstack"
    built = "            if UnifiedPipeline._pano_valid(pano):\n                return np.vstack"
    general = "                    print(f\" Using general pano (fallback): {fname}\")\n                    return np.vstack"
    for needle, replacement in (
        (cache, "                print(f\" Pano cache hit: {os.path.basename(cached)}\")\n                capture_pano('cache_hit', cached, pano)\n                return np.vstack"),
        (built, "            if UnifiedPipeline._pano_valid(pano):\n                capture_pano('per_clip_build', video_path, pano)\n                return np.vstack"),
        (general, "                    print(f\" Using general pano (fallback): {fname}\")\n                    capture_pano('general_fallback', general, img)\n                    return np.vstack"),
    ):
        if needle not in source:
            raise RuntimeError("G238 panorama insertion point not found")
        source = source.replace(needle, replacement, 1)
    namespace = dict(original_pano.__globals__)
    namespace["capture_pano"] = capture_pano
    exec(source, namespace)
    return namespace["_load_pano"]

outcome = {"events": [], "panorama": {}, "exception": None, "system_exit": None, "rows": 0}
try:
    observed_homography = patched_homography()
    def counted_homography(self, frame):
        global homography_calls
        homography_calls += 1
        before = len(events)
        result = observed_homography(self, frame)
        if len(events) == before:
            capture_event(kind='reuse_or_suspension', matcher='not_run', inliers=None, matches=None, tier='not_evaluated', installed_m=False, bootstrap=self._M_ema is None)
        return result
    UnifiedPipeline._get_homography = counted_homography
    UnifiedPipeline._load_pano = patched_pano()
    sys.argv = ["scripts/run_clip.py", "--video", "''' + VIDEO + r'''", "--game-id", "g238_homography", "--no-show", "--frames", "1200", "--skip-features", "--data-dir", DATA_DIR]
    runpy.run_path("scripts/run_clip.py", run_name="__main__")
except SystemExit as exc:
    outcome["system_exit"] = int(exc.code) if isinstance(exc.code, int) else 1
except BaseException as exc:
    outcome["exception"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
finally:
    UnifiedPipeline._get_homography = original_homography
    UnifiedPipeline._load_pano = original_pano
    outcome["events"] = events
    outcome["homography_calls"] = homography_calls
    outcome["panorama"] = pano_record
    outcome["h_min_inliers"] = module._H_MIN_INLIERS
    outcome["h_reset_inliers"] = module._H_RESET_INLIERS
    csv_path = Path(DATA_DIR) / "tracking_data.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            outcome["rows"] = sum(1 for _ in csv.DictReader(handle))
    REPORT.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="ascii")
print("G238_EVENTS=" + str(len(events)))
print("G238_EXCEPTION=" + str(outcome["exception"] is not None))
'''


def remote_script(token: str) -> str:
    """Build the one-run pod launcher, including pre-write load and disk checks."""
    runner = base64.b64encode(instrumented_source().encode("ascii")).decode("ascii")
    root = f"/tmp/g238_homography_{token}"
    data_dir = f"{POD_ROOT}/data/tracking/g238_homography_{token}"
    routes = " ".join(f"{POD_ROOT}/{path}" for path in ROUTE_FILES)
    return f'''#!/usr/bin/env bash
set -u
ROOT={root}
DATA_DIR={data_dir}
PROBE=/tmp/g238_disk_probe_{token}
rm -rf "$ROOT" "$DATA_DIR" "$PROBE"
python3 - <<'PY' > /tmp/g238_load_{token}.json
import json, os
active = []
names = {{"run_clip.py", "g235_build_court_crash_confirmation.py", "g236_label_reindex_existence.py", "g238_homography_inlier_census.py"}}
for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    try:
        executable = os.path.basename(os.readlink(f"/proc/{{name}}/exe"))
        args = open(f"/proc/{{name}}/cmdline", "rb").read().decode("utf-8", "replace").split("\\0")[:-1]
    except (FileNotFoundError, PermissionError, OSError):
        continue
    exact_route_args = [arg for arg in args if os.path.basename(arg) in names]
    if executable.startswith("python") and exact_route_args:
        active.append({{"pid": int(name), "executable": executable, "route_args": exact_route_args}})
print(json.dumps({{"active_transient_routes": active}}, sort_keys=True))
PY
PRE_DU=$(du -sm {POD_ROOT}/data)
dd if=/dev/zero of="$PROBE" bs=1M count=4 conv=fsync status=none
PROBE_RC=$?
rm -f "$PROBE"
if [ "$PROBE_RC" -ne 0 ]; then exit "$PROBE_RC"; fi
mkdir -p "$ROOT" "$DATA_DIR"
{{
  date -u +started_utc=%FT%TZ
  printf 'pre_du=%s\n' "$PRE_DU"
  printf 'disk_probe=dd_4MiB_conv_fsync_success\n'
  stat -c 'source=%n|bytes=%s' {VIDEO}
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,r_frame_rate -of default=noprint_wrappers=1 {VIDEO}
  sha256sum {routes}
}} > "$ROOT/context.txt"
mv /tmp/g238_load_{token}.json "$ROOT/load_context.json"
cd {POD_ROOT}
printf '%s' '{runner}' | base64 -d | env G238_DATA_DIR="$DATA_DIR" G238_REPORT="$ROOT/report.json" /usr/local/bin/python - > "$ROOT/run.log" 2>&1
RUN_RC=$?
printf 'run_exit_code=%s\n' "$RUN_RC" >> "$ROOT/context.txt"
if [ -d "$DATA_DIR" ]; then DATA_BYTES=$(du -sb "$DATA_DIR" | awk '{{print $1}}'); else DATA_BYTES=0; fi
ROOT_BYTES=$(du -sb "$ROOT" | awk '{{print $1}}')
printf 'temporary_root_bytes=%s\ntracking_directory_bytes=%s\nbytes_freed_expected=%s\n' "$ROOT_BYTES" "$DATA_BYTES" "$((ROOT_BYTES + DATA_BYTES))" > "$ROOT/cleanup.txt"
tar -C /tmp -czf - "$(basename "$ROOT")" -C {POD_ROOT}/data/tracking "$(basename "$DATA_DIR")" 2>/dev/null | base64 -w0
TAR_RC=${{PIPESTATUS[0]}}
rm -rf "$ROOT" "$DATA_DIR"
exit "$TAR_RC"
'''


def run(output_dir: Path, ssh_config: Path, ssh_host: str, token: str) -> None:
    """Run one measured attempt and return its temporary, auditable bundle."""
    if output_dir.exists():
        raise FileExistsError(output_dir)
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-F", str(ssh_config), ssh_host, "bash -s"],
        input=remote_script(token).encode("ascii"), stdout=subprocess.PIPE,
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
    root = f"/tmp/g238_homography_{token}"
    data_dir = f"{POD_ROOT}/data/tracking/g238_homography_{token}"
    cleanup = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-F", str(ssh_config), ssh_host,
         f"test ! -e {root} && test ! -e {data_dir}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    (output_dir / "cleanup_verification.json").write_text(
        '{"paths_absent": ' + ("true" if cleanup.returncode == 0 else "false") + "}\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--ssh-host", default="pod")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    run(args.output_dir, args.ssh_config, args.ssh_host, args.token)


if __name__ == "__main__":
    main()
