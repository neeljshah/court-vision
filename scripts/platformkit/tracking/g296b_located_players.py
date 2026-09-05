"""Extract the fixed G296 pass B frames; no detector or comparison code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import zipfile

FRAME_INDICES = tuple(round(i * 174429 / 23) for i in range(24))
PLAYER_HEADER = (
    "source_frame,person_index,role,feet_visible,foot_x_px,foot_y_px,confidence,note"
)
FRAME_HEADER = "source_frame,court_visible,shot_description,players_located"
SOURCE = Path("/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4")
ARTIFACT = Path("docs/evidence/tracking/g296b_located_players_artifact")


def sha256(path: Path) -> str:
    """Hash a file without loading the source video into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract() -> None:
    """CPU-decode exactly the preregistered native frames in pod scratch."""
    assert Path.cwd() == Path("/workspace/wt/a12")
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    gate_cmd = ["dd", "if=/dev/zero", "of=/workspace/wt/a12/g296b_fsync_probe",
                "bs=1M", "count=8", "conv=fsync"]
    probe = subprocess.run(gate_cmd, capture_output=True, text=True)
    gate = {"command": shlex.join(gate_cmd), "returncode": probe.returncode,
            "stdout": probe.stdout, "stderr": probe.stderr,
            "loadavg": list(os.getloadavg()),
            "nproc": int(subprocess.check_output(["nproc"], text=True)),
            "workspace_du_mb": "UNKNOWN (not measured; network walk)"}
    (ARTIFACT / "gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    print(json.dumps(gate), flush=True)
    if probe.returncode:
        raise RuntimeError("FAILED dd conv=fsync probe")
    while os.getloadavg()[2] >= gate["nproc"]:
        print("CPU load15 gate pending", flush=True)
        time.sleep(20)
    gate["decode_loadavg"] = list(os.getloadavg())
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,nb_frames,r_frame_rate", "-of", "json", str(SOURCE)
    ], text=True))["streams"][0]
    assert (metadata["width"], metadata["height"]) == (1920, 1080)
    assert metadata["nb_frames"] == "174430"
    assert metadata["r_frame_rate"] == "30/1"
    source_hash = sha256(SOURCE)
    assert source_hash.startswith("f361ad7a32ccc6d98ae8e98e")
    frames = ARTIFACT / "frames"
    frames.mkdir(exist_ok=True)
    assert not list(frames.glob("*.jpg")), "Refuse to overwrite an earlier extraction"
    select = "+".join(f"eq(n\\,{index})" for index in FRAME_INDICES)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
           "-threads", "2", "-i", str(SOURCE), "-map", "0:v:0", "-an",
           "-vf", f"select={select}", "-vsync", "0", "-frames:v", "24",
           "-threads", "2", "-q:v", "2", str(frames / "selected_%02d.jpg")]
    print("FRAME_INDICES=" + json.dumps(FRAME_INDICES), flush=True)
    print("FORMULA_MATCH=true", flush=True)
    print(shlex.join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    extracted = sorted(frames.glob("selected_*.jpg"))
    assert len(extracted) == 24
    records = []
    for index, path in zip(FRAME_INDICES, extracted):
        dest = frames / f"frame_{index:06d}.jpg"
        path.rename(dest)
        size = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "stream=width,height",
            "-of", "json", str(dest)], text=True))["streams"][0]
        assert (size["width"], size["height"]) == (1920, 1080)
        records.append({"source_frame": index, "path": dest.as_posix(),
                        "bytes": dest.stat().st_size, "sha256": sha256(dest),
                        "width": 1920, "height": 1080})
    manifest = {"pass": "B", "machine": "pod /workspace/wt/a12",
                "source": {"path": str(SOURCE), "bytes": SOURCE.stat().st_size,
                           "sha256": source_hash, **metadata},
                "gate": gate, "frame_indices": FRAME_INDICES,
                "formula": "round(i * 174429 / 23) for i in range(24)",
                "ffmpeg_argv": cmd, "ffmpeg_command": shlex.join(cmd),
                "ffmpeg_version": subprocess.check_output(
                    ["ffmpeg", "-version"], text=True).splitlines()[0],
                "route_sha256": sha256(Path(__file__)), "frames": records}
    (ARTIFACT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(ARTIFACT / "frames_manifest.zip", "w") as archive:
        for path in [ARTIFACT / "manifest.json", ARTIFACT / "gate.json", *frames.glob("*.jpg")]:
            archive.write(path, path.relative_to(ARTIFACT))
    print("DONE: 24 full 1920x1080 native JPEGs; no crop or resize", flush=True)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    extract()
