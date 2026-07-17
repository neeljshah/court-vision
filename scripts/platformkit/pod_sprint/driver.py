"""Pod sprint driver -- runs the 2-day TRAIN+VALIDATE job chain unattended.

Detached-safe: every job is a subprocess with its own log file; state is
checkpointed to JSON after every job so a rerun resumes where it left off.
No Claude / no network needed once launched.  Usage (on the pod):

    nohup bash scripts/platformkit/pod_sprint/run_sprint.sh &

or locally for a subset:

    python -m scripts.platformkit.pod_sprint.driver --only preflight
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
STATE_PATH = Path(os.environ.get("SPRINT_STATE", "/workspace/sprint_state.json"))
LOG_DIR = Path(os.environ.get("SPRINT_LOGS", "/workspace/sprint_logs"))
PY = sys.executable

# Ordered job chain.  Each: name, argv, timeout_s, required (failure of a
# required job halts the chain; optional jobs log FAIL and continue).
JOBS: list[dict] = [
    {
        "name": "preflight",
        "argv": [PY, "-c",
                 "import torch,xgboost,lightgbm,sklearn,pandas,pyarrow;"
                 "print('cuda', torch.cuda.is_available())"],
        "timeout_s": 120,
        "required": True,
    },
    {
        "name": "eval_gate",
        "argv": [PY, str(REPO / "scripts/platformkit/eval_gate/run_all.py")],
        "timeout_s": 1800,
        "required": True,
    },
    {
        "name": "benchmark_baseline",
        "argv": [PY, "-m", "scripts.platformkit.platform_scoreboard"],
        "timeout_s": 7200,
        "required": True,
    },
    {
        "name": "calibration_baseline",
        "argv": [PY, "-m", "scripts.platformkit.calibration_scoreboard"],
        "timeout_s": 7200,
        "required": False,
    },
    {
        "name": "claims_qa_full",
        "argv": [PY, "-m", "scripts.platformkit.answers.qa_runner", "--tier", "FULL"],
        "timeout_s": 10800,
        "required": False,
    },
    {
        "name": "train_gbm_nba",
        "argv": [PY, "-m", "scripts.platformkit.models.gbm_nba_ml"],
        "timeout_s": 14400,
        "required": False,
    },
    {
        "name": "train_gbm_sweep",
        "argv": [PY, "-m", "scripts.platformkit.pod_sprint.gbm_sweep"],
        "timeout_s": 14400,
        "required": False,
    },
    {
        "name": "train_pregame_calibration",
        "argv": [PY, str(REPO / "scripts/calibration_fit.py")],
        "timeout_s": 14400,
        "required": False,
    },
    {
        "name": "benchmark_after",
        "argv": [PY, "-m", "scripts.platformkit.platform_scoreboard"],
        "timeout_s": 7200,
        "required": False,
    },
    {
        "name": "prediction_eval",
        "argv": [PY, "-m", "scripts.platformkit.pod_sprint.prediction_eval"],
        "timeout_s": 7200,
        "required": False,
    },
]

MAX_ATTEMPTS = 2


def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE_PATH)


def _run_job(job: dict, state: dict) -> str:
    """Run one job, tee output to its log, record result. Returns status."""
    name = job["name"]
    rec = state.setdefault(name, {"attempts": 0})
    if rec.get("status") == "ok":
        return "ok"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"
    rec["attempts"] += 1
    rec["started"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save_state(state)
    print(f"[sprint] {name} attempt {rec['attempts']} -> {log_path}", flush=True)
    with open(log_path, "a") as log:
        log.write(f"\n=== attempt {rec['attempts']} {rec['started']} ===\n")
        log.flush()
        try:
            proc = subprocess.run(
                job["argv"], cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                timeout=job["timeout_s"],
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = -1
            log.write(f"\n=== TIMEOUT after {job['timeout_s']}s ===\n")
    rec["rc"] = rc
    rec["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    rec["status"] = "ok" if rc == 0 else "fail"
    _save_state(state)
    if rc != 0 and rec["attempts"] < MAX_ATTEMPTS:
        return _run_job(job, state)
    return rec["status"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="run only these job names")
    ap.add_argument("--fresh", action="store_true", help="ignore prior state")
    args = ap.parse_args(argv)

    state = {} if args.fresh else _load_state()
    for job in JOBS:
        if args.only and job["name"] not in args.only:
            continue
        status = _run_job(job, state)
        if status != "ok" and job["required"]:
            print(f"[sprint] REQUIRED job {job['name']} failed -- halting.",
                  flush=True)
            _write_summary(state, halted_at=job["name"])
            return 1
    _write_summary(state, halted_at=None)
    return 0


def _write_summary(state: dict, halted_at: str | None) -> None:
    summary = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "halted_at": halted_at,
        "jobs": {k: {kk: v.get(kk) for kk in ("status", "rc", "attempts",
                                              "started", "ended")}
                 for k, v in state.items()},
    }
    out = LOG_DIR / "sprint_summary.json"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1))
    print(f"[sprint] summary -> {out}", flush=True)
    for name, rec in summary["jobs"].items():
        print(f"  {name}: {rec['status']} rc={rec['rc']}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
