"""G400: dispatch the ten sealed paired rating rounds on the PC.

Reuses the G373/G389 rater driver (codex resolver, hidden launcher, gate, Q6 reason
normalisation) and changes only what G400 seals differently: a round is one target
per drawn game, sources are MIXED native resolutions, so each id carries its own
frame size in the prompt and the parser validates each box against that size.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g373_rate as base

CODEX_HOME = {"terra": r"C:\Users\neelj\.codex-a7", "sol": r"C:\Users\neelj\.codex-sol"}
MIN_FREE_GB = 2.8
MAX_CODEX_EXEC = 2
GATE_RETRY_S = 90
FIELDS = ("frame_key", "rater", "round", "label", "box_x", "box_y", "box_w", "box_h",
          "cx", "cy", "width", "height", "reason")
LABELS = ("VISIBLE", "ABSENT", "UNKNOWN")
LINE = re.compile(r"^([0-9a-f]{12})\s*,\s*(VISIBLE|ABSENT|UNKNOWN)\s*,(.*)$")
GATE_PS = ("@(Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | "
           "Where-Object { $_.CommandLine -match ' exec ' }).Count")
FREE_PS = "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)"

PROMPT = """Rate basketball broadcast frames for the GAME BALL. Work only from the images.

Each line below names a file {sheets}/<id>.jpg and that image's exact pixel size.
Open and LOOK AT every one of the {count} images, in the order listed.

For each image emit exactly one CSV line, in that same order, appending to {out}:
<id>,<LABEL>,<box_x>,<box_y>,<box_w>,<box_h>,<short reason>

LABEL is exactly one of:
  VISIBLE - you can identify the game ball in this frame
  ABSENT  - there is no game ball anywhere in this frame
  UNKNOWN - you cannot tell

If VISIBLE, give the TIGHT bounding box of the ball in NATIVE pixels of THAT image:
box_x and box_y are the top-left corner, box_w and box_h the width and height, with
0 <= box_x, 0 <= box_y, box_x+box_w <= that image width, box_y+box_h <= that image
height, and box_w >= 1 and box_h >= 1. A basketball in a broadcast wide shot is
usually 10 to 60 pixels across at 1920x1080 and 7 to 40 at 1280x720.
If ABSENT or UNKNOWN, leave all four box fields EMPTY and never invent a box.
The reason is a few plain words, with no comma in it.

Rate only the game ball actually in play or held by a player. A ball in a logo, a
graphic, an advertisement or a crowd shot is not the game ball. Judge each frame on
its own. Do not open any other file, do not look for any previous or other rating,
and do not use any detector output. Write no header and no commentary to {out}.

ids ({count}):
{ids}
"""


def _ps(command: str) -> float:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                         capture_output=True, text=True, timeout=180).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return -1.0


def gate_open(mine: int) -> bool:
    """Binding shared gate: fewer than three live codex exec runs and free RAM."""
    running, free_gb = _ps(GATE_PS), _ps(FREE_PS)
    ok = 0 <= running < MAX_CODEX_EXEC and free_gb >= MIN_FREE_GB and mine < 2
    print(f"GATE exec={running} free_gb={free_gb} mine={mine} ok={ok}", flush=True)
    return ok


def wait_for_gate(mine: int, deadline: float) -> bool:
    while not gate_open(mine):
        if time.time() >= deadline:
            return False
        time.sleep(GATE_RETRY_S)
    return True


def launch(rater: str, prompt: str, log: Path, cwd: Path, tag: str) -> str:
    binary = base.codex_binary()
    command = [base.PYTHONW, base.LAUNCHER, "--log", str(log), "--cwd", str(cwd),
               "--tag", tag, "--env", "CODEX_HOME=" + CODEX_HOME[rater],
               "--", binary, "exec", "--skip-git-repo-check", "--sandbox",
               "workspace-write", "-c", "model_reasoning_effort=medium", "--", prompt]
    subprocess.Popen(command, cwd=str(cwd), close_fds=True)
    return binary


def parse_batch(path: Path, rater: str, round_no: int, wanted: dict[str, dict]) -> list[dict]:
    """Parse one raw batch; a malformed or out-of-frame line is dropped, never guessed."""
    if not path.exists():
        return []
    rows, seen = [], set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        found = LINE.match(raw.strip())
        if not found:
            continue
        short, label = found.group(1), found.group(2)
        if short not in wanted or short in seen:
            continue
        meta = wanted[short]
        width, height = int(meta["width"]), int(meta["height"])
        fields = [item.strip() for item in found.group(3).split(",")]
        box, tail = fields[:-1], fields[-1] if len(fields) > 1 else ""
        reason, _changed = base.neutralise(tail[:80])
        if label == "VISIBLE":
            if len(box) != 4:
                continue
            try:
                x, y, w, h = (int(round(float(value))) for value in box)
            except ValueError:
                continue
            if w < 1 or h < 1 or x < 0 or y < 0 or x + w > width or y + h > height:
                continue
            values = {"box_x": x, "box_y": y, "box_w": w, "box_h": h,
                      "cx": x + w / 2.0, "cy": y + h / 2.0}
        else:
            if any(value for value in box):
                continue
            values = {"box_x": "", "box_y": "", "box_w": "", "box_h": "",
                      "cx": "", "cy": ""}
        seen.add(short)
        rows.append({"frame_key": meta["frame_key"], "rater": rater, "round": round_no,
                     "label": label, "width": width, "height": height,
                     "reason": reason, **values})
    return rows


def append(out: Path, rows: list[dict]) -> None:
    exists = out.exists() and out.stat().st_size > 0
    with out.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def done_keys(out: Path, rater: str) -> set[str]:
    if not out.exists():
        return set()
    with out.open(encoding="utf-8", newline="") as handle:
        return {row["frame_key"] for row in csv.DictReader(handle)
                if row["rater"] == rater}


def run(args) -> int:
    cwd = Path(args.cwd).resolve()
    plan_path, manifest_path = Path(args.batch_plan), Path(args.manifest)
    with manifest_path.open(encoding="ascii", newline="") as handle:
        manifest = {row["frame_key"]: row for row in csv.DictReader(handle)}
    with plan_path.open(encoding="ascii", newline="") as handle:
        plan = list(csv.DictReader(handle))
    out, raw_dir = Path(args.out), Path(args.raw_dir)
    log_dir = Path(args.log_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    receipts = Path(args.receipts)
    deadline = time.time() + args.budget_min * 60.0
    finished = done_keys(out, args.rater)
    sheets_rel = Path(args.sheets).resolve()
    for round_no in range(args.first_round, args.last_round + 1):
        keys = [row["frame_key"] for row in plan if int(row["round"]) == round_no]
        keys = [key for key in keys
                if key not in finished and manifest[key]["status"] == "PLANNED"]
        if not keys:
            continue
        wanted = {key[:12]: {"frame_key": key, "width": manifest[key]["width"],
                             "height": manifest[key]["height"]} for key in keys}
        tag = f"g400_rater_{args.rater}_{round_no:02d}"
        raw = raw_dir.resolve() / (tag + ".txt")
        log = log_dir.resolve() / ("cx_" + tag + ".log")
        raw.unlink(missing_ok=True)
        log.unlink(missing_ok=True)
        if not wait_for_gate(0, deadline):
            print("DEADLINE-BEFORE-ROUND", round_no, flush=True)
            break
        listing = "\n".join(f"{short} {meta['width']}x{meta['height']}"
                            for short, meta in wanted.items())
        prompt = PROMPT.format(sheets=sheets_rel.as_posix(),
                               out=raw.as_posix(), count=len(wanted), ids=listing)
        started = time.time()
        binary = launch(args.rater, prompt, log, cwd, tag)
        code = base.wait_for_exit(log, min(args.timeout_s,
                                           max(60, int(deadline - time.time()))))
        rows = parse_batch(raw, args.rater, round_no, wanted)
        append(out, rows)
        finished.update(row["frame_key"] for row in rows)
        exists = receipts.exists() and receipts.stat().st_size > 0
        with receipts.open("a", encoding="ascii", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            if not exists:
                writer.writerow(("tag", "rater", "round", "ids", "parsed", "exit",
                                 "seconds", "raw_file", "codex_binary", "status"))
            writer.writerow((tag, args.rater, round_no, len(wanted), len(rows), code,
                             int(time.time() - started), raw.name, binary,
                             "OK" if rows else "FAULT_NO_OUTPUT"))
        print(f"BATCH {tag} ids={len(wanted)} parsed={len(rows)} exit={code}", flush=True)
        if time.time() >= deadline:
            print("DEADLINE-REACHED after round", round_no, flush=True)
            break
    print("QUEUE-DONE rater=" + args.rater, flush=True)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g400_rate")
    for flag in ("--batch-plan", "--manifest", "--out", "--raw-dir", "--log-dir",
                 "--rater", "--sheets", "--receipts"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--cwd", default=r"C:\Users\neelj\nba-track-a7")
    parser.add_argument("--first-round", type=int, default=1)
    parser.add_argument("--last-round", type=int, default=10)
    parser.add_argument("--timeout-s", type=int, default=900)
    parser.add_argument("--budget-min", type=int, default=100)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
