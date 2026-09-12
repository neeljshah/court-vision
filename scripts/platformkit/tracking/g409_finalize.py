"""Receipts, reproductions and checksums for the delivered G409 directory."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.platformkit.tracking import g409_build as B

OUT = B.OUT
TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt"}
OWNED = [
    "scripts/platformkit/tracking/g409_audit.py",
    "scripts/platformkit/tracking/g409_blind.py",
    "scripts/platformkit/tracking/g409_build.py",
    "scripts/platformkit/tracking/g409_construct.py",
    "scripts/platformkit/tracking/g409_finalize.py",
    "scripts/platformkit/tracking/g409_observer.py",
    "scripts/platformkit/tracking/g409_prepare.py",
    "scripts/platformkit/tracking/g409_replay_driver.sh",
    "scripts/platformkit/tracking/g409_run.py",
    "scripts/platformkit/tracking/g409_transforms.py",
    "tests/platformkit/test_g409_box_coordinate_cause.py",
    "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12.md",
]


def delivered_tables() -> list[Path]:
    return sorted(p for p in OUT.rglob("*")
                  if p.is_file() and p.name not in {"repeats.json", "SHA256SUMS"})


def digest_map() -> dict[str, str]:
    out = {}
    for path in delivered_tables():
        out[path.relative_to(OUT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def build_launch_receipts(replay_dir: Path) -> dict:
    plan = {}
    for line in (replay_dir / "plan.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.rstrip("\r").split("\t")
        plan[parts[0]] = {"source_path": parts[1], "source_sha256": parts[2],
                          "start_frame": int(parts[3]), "frames": int(parts[4]),
                          "section_id": parts[5], "ticks": [int(v) for v in parts[6].split(",")]}
    status = {}
    status_path = replay_dir / "status.tsv"
    if status_path.exists():
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.rstrip("\r").split("\t")
            status[parts[0]] = parts
    launches = []
    for key in sorted(plan):
        row = status.get(key)
        obs = replay_dir / (key + ".jsonl")
        launches.append({
            "window_key": key, **plan[key],
            "replay_source_on_pod": row[1] if row else "",
            "replay_source_sha256": row[2] if row else "",
            "returncode": row[3] if row else "",
            "log_sha256": row[4] if row and len(row) > 4 else "",
            "observations_present": bool(obs.exists() and obs.stat().st_size),
            "observation_sha256": hashlib.sha256(obs.read_bytes()).hexdigest()
                                  if obs.exists() else "",
            "status": "REPLAYED" if (row and row[3] == "RC=0") else (
                "UNKNOWN" if not row else "FAILED"),
        })
    return {
        "command_template": ("cd /workspace/g409_scratch/tree && OMP_NUM_THREADS=1 "
                             "MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 "
                             "PYTHONDONTWRITEBYTECODE=1 G409_SINK=<sink> G409_TICKS=<ticks> "
                             "python3 scripts/run_clip.py --video=<src> --game-id=<section> "
                             "--no-show --frames <n> --start-frame <s> "
                             "--data-dir=/workspace/g409_scratch/out/<section>"),
        "argv_source": "G402 launch_receipts.csv argv reused verbatim except --data-dir",
        "planned_windows": len(plan),
        "replayed": sum(1 for r in launches if r["status"] == "REPLAYED"),
        "unknown": sum(1 for r in launches if r["status"] == "UNKNOWN"),
        "failed": sum(1 for r in launches if r["status"] == "FAILED"),
        "launches": launches,
    }


def _rebuild() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "scripts.platformkit.tracking.g409_run"],
                          cwd=str(B.ROOT), capture_output=True, text=True)


def build_repeats(rounds: int = 2) -> dict:
    settle = _rebuild()
    if settle.returncode != 0:
        raise RuntimeError("settle-rebuild-failed")
    baseline = digest_map()
    runs = []
    for _ in range(rounds):
        proc = _rebuild()
        after = digest_map()
        runs.append({
            "identical_to_baseline": after == baseline,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip().splitlines(),
            "stderr_tail": proc.stderr.strip().splitlines()[-3:],
            "per_table_digests": after,
        })
    return {
        "scope": ("two fresh processes rebuild every delivered G409 table, render and "
                  "receipt from the delivered sealed bytes; this does not prove inference "
                  "repeatability of the archived producer route"),
        "rounds": rounds,
        "settle_rebuild": {"returncode": settle.returncode,
                           "note": "one rebuild settles the scan over the receipts written "
                                   "in this same finalize pass, then the baseline is taken"},
        "identical": all(r["identical_to_baseline"] for r in runs),
        "baseline_digests": baseline,
        "frozen_inputs_not_regenerated": {
            "prereg.md": hashlib.sha256((OUT / "prereg.md").read_bytes()).hexdigest(),
            "stage_trace.jsonl": "regenerated from retained pod observations, not re-run",
        },
        "runs": runs,
    }


def build_sha256sums() -> str:
    lines = [
        "# byte domain: sha256 over the LF bytes this lane wrote for every file under "
        "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12/ plus the memo, the "
        "owned g409 helpers and the focused test; paths are repo-relative with forward "
        "slashes and SHA256SUMS excludes itself. Text files here are LF on disk and LF in "
        "the commit, so these digests equal the committed blob content; a fresh checkout "
        "with core.autocrlf=true materializes CRLF and will not match byte for byte. "
        "Renders are binary and identical in both. input_hashes.csv additionally carries "
        "the LF-normalized digest used to match the sealed upstream values.",
    ]
    paths = [p.relative_to(B.ROOT).as_posix() for p in OUT.rglob("*")
             if p.is_file() and p.name != "SHA256SUMS"]
    paths += [p for p in OWNED if (B.ROOT / p).exists()]
    for rel in sorted(set(paths)):
        digest = hashlib.sha256((B.ROOT / rel).read_bytes()).hexdigest()
        lines.append("%s  %s" % (digest, rel))
    return "\n".join(lines) + "\n"


def main() -> int:
    replay = B.ROOT / ".g409_rep"
    (OUT / "runtime_receipts").mkdir(parents=True, exist_ok=True)
    (OUT / "common_receipts").mkdir(parents=True, exist_ok=True)

    raw = OUT / "runtime_receipts" / "observations"
    raw.mkdir(parents=True, exist_ok=True)
    for src in sorted(replay.glob("*.jsonl")):
        (raw / src.name).write_bytes(src.read_bytes())
    for name in ("plan.tsv", "status.tsv"):
        if (replay / name).exists():
            (raw / name).write_bytes((replay / name).read_bytes())

    launch = build_launch_receipts(replay)
    (OUT / "launch_receipts.json").write_text(
        json.dumps(launch, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    repeats = build_repeats()
    (OUT / "repeats.json").write_text(
        json.dumps(repeats, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    (OUT / "SHA256SUMS").write_text(build_sha256sums(), encoding="utf-8", newline="\n")
    print(json.dumps({"replayed": launch["replayed"], "unknown": launch["unknown"],
                      "failed": launch["failed"], "repeats_identical": repeats["identical"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
