"""G404 one-card-per-request rater transport (amendment A1).

Delivers exactly one native card per transport request, validates the rater's card
id and image SHA-256 echo before advancing, and records a BINDING_FAULT for any
failed echo. It never renumbers, realigns, replaces or silently re-sends a card.
The PC capacity gate (at most two rater runs, fewer than three codex exec
processes, free RAM at or above the bar) is checked before every launch.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import time
from pathlib import Path

ANSWER = re.compile(r"CARD\s+(?P<card>\S+)\s+SHA256\s+(?P<sha>[0-9a-fA-F]{64})\s+"
                    r"LABEL\s+(?P<label>PLAY|NONPLAY|UNKNOWN)\s+SUPPORT\s+(?P<support>.*)",
                    re.IGNORECASE)
FIELDS = ("rater", "card_id", "dispatch_position", "expected_sha256", "echo_sha256",
          "label", "support", "echo_status", "returncode", "seconds", "answer_path")
FREE_GB_BAR = 2.8
POLL_S = 90


def capacity(min_free_gb: float, max_exec: int) -> tuple[bool, float, int]:
    """Count codex exec processes by command line and read free RAM; never by image name."""
    script = ("$p=@(Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | "
              "Where-Object { $_.CommandLine -like '* exec *' }).Count; "
              "$f=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB; "
              "Write-Output \"$p $f\"")
    raw = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                         capture_output=True, text=True)
    parts = raw.stdout.split()
    if len(parts) < 2:
        return False, 0.0, 99
    running, free_gb = int(float(parts[0])), float(parts[1])
    return (running < max_exec and free_gb >= min_free_gb), free_gb, running


def prompt_for(card: Path, card_id: str, answer: Path) -> str:
    return (
        "Open the single image file " + str(card).replace("\\", "/") + " and look at it. "
        "Compute that file's SHA-256. Then write EXACTLY ONE line, and nothing else, to "
        + str(answer).replace("\\", "/") + " :\n"
        "CARD " + card_id + " SHA256 <the 64 hex digits you computed> LABEL <PLAY or "
        "NONPLAY or UNKNOWN> SUPPORT <at most twelve words naming what you see>\n"
        "PLAY means visible multi-player on-court basketball action; wide replay action "
        "of live play qualifies. NONPLAY means a wipe, bench, huddle, crowd, portrait, "
        "full-screen graphic, or a rim-only or otherwise non-play view. UNKNOWN means you "
        "cannot tell. Never guess a label to avoid UNKNOWN. Judge only this one image.")


def dispatch(args, row: dict, rater: str, home: str) -> dict:
    card = Path(row["card_path"])
    answer = Path(args.raw_dir) / ("g404_%s_%s.txt" % (rater, row["card_id"]))
    answer.parent.mkdir(parents=True, exist_ok=True)
    log = Path(args.receipts) / ("cx_g404_%s_%s.log.txt" % (rater, row["card_id"]))
    log.parent.mkdir(parents=True, exist_ok=True)
    command = ["C:/Users/neelj/AppData/Local/Programs/Python/Python310/pythonw.exe",
               "C:/Users/neelj/bin/hidden_launch2.py", "--log", str(log),
               "--cwd", str(card.parent), "--tag", "g404_%s_%s" % (rater, row["card_id"]),
               "--env", "CODEX_HOME=" + home, "--", args.codex, "exec",
               "--skip-git-repo-check", "--sandbox", "workspace-write",
               "-c", "model_reasoning_effort=" + args.effort, "--",
               prompt_for(card, row["card_id"], answer)]
    started = time.time()
    subprocess.Popen(command)
    deadline = started + args.card_timeout
    while time.time() < deadline:
        if log.exists() and "EXIT:" in log.read_text(encoding="ascii", errors="replace"):
            break
        time.sleep(3)
    text = answer.read_text(encoding="utf-8", errors="replace") if answer.exists() else ""
    match = ANSWER.search(text)
    record = {"rater": rater, "card_id": row["card_id"],
              "dispatch_position": row["dispatch_position"],
              "expected_sha256": row["card_sha256"], "echo_sha256": "", "label": "",
              "support": "", "echo_status": "BINDING_FAULT_NO_ANSWER",
              "returncode": "", "seconds": "%.1f" % (time.time() - started),
              "answer_path": str(answer).replace("\\", "/")}
    if match:
        record["echo_sha256"] = match.group("sha").lower()
        record["label"] = match.group("label").upper()
        record["support"] = match.group("support").strip()[:120]
        same_card = match.group("card").strip() == row["card_id"]
        same_image = record["echo_sha256"] == row["card_sha256"].lower()
        record["echo_status"] = ("OK" if same_card and same_image else
                                 "BINDING_FAULT_CARD_ID" if not same_card else
                                 "BINDING_FAULT_IMAGE_SHA")
    return record


def run(args) -> int:
    with Path(args.draw).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))[args.start:args.start + args.count]
    out = Path(args.out)
    written = out.exists()
    for row in rows:
        while True:
            ok, free_gb, running = capacity(FREE_GB_BAR, args.max_exec)
            print("GATE exec=%d free_gb=%.2f ok=%s" % (running, free_gb, ok), flush=True)
            if ok:
                break
            time.sleep(POLL_S)
        record = dispatch(args, row, args.rater, args.home)
        with out.open("a" if written else "w", encoding="ascii", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
            if not written:
                writer.writeheader()
                written = True
            writer.writerow({key: str(value).encode("ascii", "replace").decode("ascii")
                             for key, value in record.items()})
        print("CARD", record["card_id"], record["echo_status"], record["label"], flush=True)
        if record["echo_status"] != "OK" and args.stop_on_fault:
            print(json.dumps({"stopped_on": record["card_id"],
                              "reason": record["echo_status"]}))
            return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_rate")
    for flag in ("--draw", "--out", "--raw-dir", "--receipts", "--rater", "--home",
                 "--codex", "--effort"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--max-exec", type=int, default=3)
    parser.add_argument("--card-timeout", type=float, default=300.0)
    parser.add_argument("--stop-on-fault", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
