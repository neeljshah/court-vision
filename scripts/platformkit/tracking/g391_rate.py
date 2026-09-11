"""G391: dispatch the two blind object/location rater lanes over the sealed packets.

The rater sees only opaque packet ids and the card images. It never learns the
reference label, the score outcome, or the 169/90 assignment, and the queue is the
sealed packets.csv order, never a sorted prefix.

A batch that parses nothing is recorded as a FAULT and never silently re-run: a
codex directory without the image/tool host rates nothing while every process
signal stays healthy (G373 lost whole batches to exactly that).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g373_rate as base

CODEX_HOME = {"terra": r"C:\Users\neelj\.codex-a7", "sol": r"C:\Users\neelj\.codex-sol"}
MIN_FREE_GB = 2.8
MAX_CODEX_EXEC = 3
GATE_RETRY_S = 110
LOCK = Path(r"C:\Users\neelj\AppData\Local\Temp\g391_launch.lock")
GATE_PS = ("@(Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | "
           "Where-Object { $_.CommandLine -match ' exec ' }).Count")
FREE_PS = "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)"

OBJECTS = ("BALL", "PERSON_OR_APPAREL", "CROWD", "SIGNAGE_OR_GRAPHIC", "EQUIPMENT",
           "COURT_OR_LOGO", "OTHER", "UNKNOWN")
STATES = ("BALL_AT_MARKER", "BALL_ELSEWHERE", "NO_BALL_VISIBLE", "BALL_UNCERTAIN")
UNCERTAINTY = ("LOW", "MEDIUM", "HIGH")
FIELDS = ("packet_id", "rater", "object", "ball_state", "ball_cx", "ball_cy",
          "ball_d", "uncertainty", "reason")
LINE = re.compile(r"^(G391-\d{3}-[0-9a-f]{16})\s*,\s*([A-Z_]+)\s*,\s*([A-Z_]+)\s*,(.*)$")

PROMPT = """Classify a marked candidate region in basketball broadcast frames. Work only from the images.

Each id below names a file {cards}/<id>.jpg. Every card has TWO panels:
  TOP    - the whole broadcast frame, downscaled, for context.
  BOTTOM - a 448x448 NATIVE-pixel crop around the SAME candidate, shown at 2x.
A thin black-and-white open square with four ticks marks the CANDIDATE REGION in
both panels. The marker is only a pointer: it is NOT a judgement you must agree
with, and the thing inside it is often not a ball at all.

Open and LOOK AT every one of the {count} images, in the order listed. For each
one emit exactly one CSV line, in that same order, appending to {out}:
<id>,<OBJECT>,<BALL_STATE>,<ball_cx>,<ball_cy>,<ball_d>,<uncertainty>,<short reason>

OBJECT names the physical thing INSIDE the marker, exactly one of:
  BALL               the game ball
  PERSON_OR_APPAREL  a body part, head, hair, hand, shoe, jersey, shorts, sleeve
  CROWD              undifferentiated spectators or stands
  SIGNAGE_OR_GRAPHIC a scorebug, broadcast graphic, advertisement, banner, painted sign
  EQUIPMENT          rim, net, backboard, stanchion, ball rack, chair, camera, cable, towel
  COURT_OR_LOGO      court floor, a court line, a painted court logo, the centre circle
  OTHER              clearly visible and none of the above
  UNKNOWN            you cannot tell what is inside the marker

BALL_STATE judges the WHOLE frame, exactly one of:
  BALL_AT_MARKER   the game ball is inside the marker
  BALL_ELSEWHERE   the game ball is clearly visible somewhere ELSE in the frame
  NO_BALL_VISIBLE  no game ball anywhere in the frame
  BALL_UNCERTAIN   you cannot tell

If BALL_AT_MARKER or BALL_ELSEWHERE, give the ball centre ball_cx,ball_cy and its
diameter ball_d in NATIVE pixels of the 1920x1080 frame, with 0<=ball_cx<=1920,
0<=ball_cy<=1080 and 1<=ball_d<=200. A ball in a broadcast wide shot is usually 10
to 60 pixels across. Otherwise leave those three fields EMPTY. NEVER invent a ball:
do not infer one you cannot actually see because it is hidden behind a player.
A ball in a logo, a graphic, an advertisement or a crowd shot is NOT the game ball.

uncertainty is exactly LOW, MEDIUM or HIGH.
reason is a few plain words with no comma in it.

Judge each card on its own. Do not open any other file, do not look for any other
rating, any label table or any detector output. Write no header and no commentary.

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


def gate_open() -> bool:
    """The binding PC gate, shared with every other lane on this box."""
    running, free_gb = _ps(GATE_PS), _ps(FREE_PS)
    ok = 0 <= running < MAX_CODEX_EXEC and free_gb >= MIN_FREE_GB
    print("GATE exec=%s free_gb=%s ok=%s" % (running, free_gb, ok), flush=True)
    return ok


def _lock() -> bool:
    try:
        handle = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime > 600:
            LOCK.unlink(missing_ok=True)
        return False
    os.close(handle)
    return True


def launch(rater: str, prompt: str, log: Path, cwd: Path, tag: str) -> str:
    """Spawn one windowless rater batch; returns the codex binary it used."""
    binary = base.codex_binary()
    command = [base.PYTHONW, base.LAUNCHER, "--log", str(log), "--cwd", str(cwd),
               "--tag", tag, "--env", "CODEX_HOME=" + CODEX_HOME[rater],
               "--", binary, "exec", "--skip-git-repo-check", "--sandbox",
               "workspace-write", "-c", "model_reasoning_effort=medium", "--", prompt]
    subprocess.Popen(command, cwd=str(cwd), close_fds=True)
    return binary


def parse_batch(path: Path, rater: str, ids: list[str]) -> list[dict]:
    """Parse one batch; a malformed or out-of-frame line is dropped, never guessed."""
    if not path.exists():
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    wanted = set(ids)
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        found = LINE.match(raw.strip())
        if not found:
            continue
        packet, obj, state = found.group(1), found.group(2), found.group(3)
        if packet not in wanted or packet in seen:
            continue
        if obj not in OBJECTS or state not in STATES:
            continue
        fields = [item.strip() for item in found.group(4).split(",")]
        if len(fields) < 4:
            continue
        cx, cy, diameter, uncertainty = fields[0], fields[1], fields[2], fields[3].upper()
        reason, _changed = base.neutralise(",".join(fields[4:])[:80])
        if uncertainty not in UNCERTAINTY:
            uncertainty = "HIGH"
        if state in ("BALL_AT_MARKER", "BALL_ELSEWHERE"):
            try:
                values = [float(cx), float(cy), float(diameter)]
            except ValueError:
                continue
            if not (0 <= values[0] <= 1920 and 0 <= values[1] <= 1080
                    and 1 <= values[2] <= 200):
                continue
            cx, cy, diameter = ("%g" % value for value in values)
        else:
            if any((cx, cy, diameter)):
                continue
        seen.add(packet)
        rows.append({"packet_id": packet, "rater": rater, "object": obj,
                     "ball_state": state, "ball_cx": cx, "ball_cy": cy,
                     "ball_d": diameter, "uncertainty": uncertainty,
                     "reason": reason.replace(",", " ")})
    return rows


def append(out: Path, rows: list[dict]) -> None:
    """Append a checkpoint; ratings are never held only in memory."""
    exists = out.exists() and out.stat().st_size > 0
    with out.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def done_ids(out: Path, rater: str) -> set[str]:
    if not out.exists():
        return set()
    with out.open(encoding="utf-8", newline="") as handle:
        return {row["packet_id"] for row in csv.DictReader(handle)
                if row["rater"] == rater}


def run(args) -> int:
    cwd = Path(args.cwd).resolve()
    with (cwd / args.packets).open(encoding="utf-8", newline="") as handle:
        packets = [row["packet_id"] for row in csv.DictReader(handle)]
    out = Path(args.out)
    raw_dir, log_dir = Path(args.raw_dir), Path(args.log_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    faults = raw_dir / (args.rater + "_faults.txt")
    todo = [p for p in packets if p not in done_ids(out, args.rater)]
    print("QUEUE rater=%s todo=%d" % (args.rater, len(todo)), flush=True)
    batches = [todo[i:i + args.batch_size]
               for i in range(0, len(todo), args.batch_size)][:args.max_batches]
    for number, ids in enumerate(batches, 1):
        tag = "g391_rater_%s_%02d" % (args.rater, args.start + number)
        raw = raw_dir.resolve() / (tag + ".txt")
        log = Path(log_dir.resolve() / ("cx_" + tag + ".log"))
        raw.unlink(missing_ok=True)
        log.unlink(missing_ok=True)
        while not (gate_open() and _lock()):
            time.sleep(GATE_RETRY_S)
        prompt = PROMPT.format(cards=args.cards_dir, out=raw.relative_to(cwd).as_posix(),
                               count=len(ids), ids="\n".join(ids))
        binary = launch(args.rater, prompt, log, cwd, tag)
        time.sleep(45)
        LOCK.unlink(missing_ok=True)
        code = base.wait_for_exit(log, args.timeout_s)
        already = done_ids(out, args.rater)
        rows = [row for row in parse_batch(raw, args.rater, ids)
                if row["packet_id"] not in already]
        if not rows:
            with faults.open("a", encoding="ascii") as handle:
                handle.write("%s ids=%d parsed=0 exit=%s binary=%s\n"
                             % (tag, len(ids), code, binary))
        append(out, rows)
        print("BATCH %s ids=%d parsed=%d exit=%s" % (tag, len(ids), len(rows), code),
              flush=True)
    print("QUEUE-DONE rater=" + args.rater, flush=True)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g391_rate")
    for flag in ("--packets", "--cards-dir", "--out", "--raw-dir", "--log-dir", "--rater"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--cwd", default=r"C:\Users\neelj\nba-track-a10")
    parser.add_argument("--batch-size", type=int, default=35)
    parser.add_argument("--max-batches", type=int, default=200)
    parser.add_argument("--timeout-s", type=int, default=2700)
    parser.add_argument("--start", type=int, default=0)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
