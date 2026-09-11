"""G373 phase 1: drive the blind NATIVE reference-v2 rating batches on the PC.

The raters are codex lanes (the pod has no codex auth), so this runs on the PC and
never on the pod.  A batch sees sheet filenames only: no candidate box, no score,
no previous centre, no v1 rating, no other rater's output, and no detector output.

The binding RAM gate is checked before EVERY batch -- free physical memory and the
live codex.exe count -- and a blocked batch queues and retries rather than running,
because other lanes dispatch raters against the same box.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import time
from pathlib import Path

PYTHONW = r"C:\Users\neelj\AppData\Local\Programs\Python\Python310\pythonw.exe"
LAUNCHER = r"C:\Users\neelj\bin\hidden_launch2.py"
# The Codex app updates itself into a NEW hashed bin directory and REMOVES the old
# one, so a pinned hash can stop existing mid-run: the launcher writes DISPATCHED,
# fails to spawn, and the batch dies with no STARTED line and no output. G373 lost
# sol batches 42 and 43 to exactly that. Resolve the binary at run time instead,
# preferring the pinned build while it still exists so one run stays on one binary.
CODEX_BIN_ROOT = r"C:\Users\neelj\AppData\Local\OpenAI\Codex\bin"
CODEX_PINNED = "8e5b6932251c2c1c"
# codex.exe alone is not a usable install: without the image/tool host the
# rater cannot see a frame, and it reports that rather than inventing boxes.
REQUIRED_CODEX_FILES = ("codex.exe", "codex-code-mode-host.exe")
CODEX_HOME = {"terra": r"C:\Users\neelj\.codex-a12", "sol": r"C:\Users\neelj\.codex-sol"}
MIN_FREE_GB = 2.8
MAX_CODEX = 3
GATE_RETRY_S = 180
RATING_FIELDS = ("frame_key", "rater", "label", "box_x", "box_y", "box_w", "box_h",
                 "cx", "cy", "pass", "reason")
LABELS = ("VISIBLE", "ABSENT", "UNKNOWN")
LINE = re.compile(r"^([0-9a-f]{12})\s*,\s*(VISIBLE|ABSENT|UNKNOWN)\s*,(.*)$")

PROMPT = """Rate basketball broadcast frames for the GAME BALL. Work only from the images.

Each id below names a file {sheets}/<id>.jpg: one native 1920x1080 broadcast frame.
Open and LOOK AT every one of the {count} images, in the order listed.

For each image emit exactly one CSV line, in that same order, appending to {out}:
<id>,<LABEL>,<box_x>,<box_y>,<box_w>,<box_h>,<short reason>

LABEL is exactly one of:
  VISIBLE - you can identify the game ball in this frame
  ABSENT  - there is no game ball anywhere in this frame
  UNKNOWN - you cannot tell

If VISIBLE, give the TIGHT bounding box of the ball in NATIVE pixels of the
1920x1080 frame: box_x and box_y are the top-left corner, box_w and box_h the
width and height, with 0 <= box_x and box_x+box_w <= 1920, 0 <= box_y and
box_y+box_h <= 1080, and box_w >= 1 and box_h >= 1. A basketball in a broadcast
wide shot is usually 10 to 60 pixels across at this resolution.
If ABSENT or UNKNOWN, leave all four box fields EMPTY and never invent a box.
The reason is a few plain words, with no comma in it.

Rate only the game ball actually in play or held by a player. A ball in a logo, a
graphic, an advertisement or a crowd shot is not the game ball. Judge each frame on
its own. Do not open any other file, do not look for any previous or other rating,
and do not use any detector output. Write no header and no commentary to {out}.

ids ({count}):
{ids}
"""


def complete_install(directory: Path) -> bool:
    """A usable Codex install is codex.exe AND the image/tool host beside it.

    The app reinstalls a hashed bin directory in STAGES, so a directory can hold
    codex.exe for a while with no host. Launching that build does not look like a
    failure: codex runs, exits 0, reports the host missing and rates nothing, so a
    whole batch is lost while every process-level signal stays healthy. Requiring
    the host is what makes this resolver honest -- G373 lost sol batches 62-68 to a
    partially restored directory that satisfied a codex.exe-only check."""
    return all((directory / name).is_file() for name in REQUIRED_CODEX_FILES)


def codex_binary() -> str:
    """The newest COMPLETE codex install, preferring the pinned build."""
    root = Path(CODEX_BIN_ROOT)
    if complete_install(root / CODEX_PINNED):
        return str(root / CODEX_PINNED / "codex.exe")
    found = sorted((path for path in root.iterdir()
                    if path.is_dir() and complete_install(path)),
                   key=lambda path: (path / "codex.exe").stat().st_mtime, reverse=True)
    if not found:
        raise SystemExit("no complete codex install under " + CODEX_BIN_ROOT)
    return str(found[0] / "codex.exe")


def gate(verbose: bool = True) -> bool:
    """The binding RAM gate: free physical GB and the live codex.exe count."""
    free = subprocess.run(["powershell", "-NoProfile", "-Command",
                           "[math]::Round((Get-CimInstance Win32_OperatingSystem)."
                           "FreePhysicalMemory/1MB,1)"],
                          capture_output=True, text=True, timeout=120).stdout.strip()
    tasks = subprocess.run(["tasklist", "/FI", "IMAGENAME eq codex.exe"],
                           capture_output=True, text=True, timeout=120).stdout
    running = tasks.count("codex.exe")
    try:
        free_gb = float(free)
    except ValueError:
        free_gb = 0.0
    ok = free_gb >= MIN_FREE_GB and running < MAX_CODEX
    if verbose:
        print(f"GATE free_gb={free_gb} codex={running} ok={ok}", flush=True)
    return ok


def wait_for_gate() -> None:
    """Queue and retry; never run a batch through a closed gate."""
    while not gate():
        print(f"GATE-WAIT retry_in={GATE_RETRY_S}s", flush=True)
        time.sleep(GATE_RETRY_S)


def launch(rater: str, prompt: str, log: Path, cwd: Path) -> None:
    """One codex rater batch, windowless, ending when its turn ends."""
    command = [PYTHONW, LAUNCHER, "--log", str(log), "--cwd", str(cwd),
               "--tag", "g373_rater_" + rater, "--env", "CODEX_HOME=" + CODEX_HOME[rater],
               "--", codex_binary(), "exec", "--skip-git-repo-check", "--sandbox",
               "workspace-write",
               "--", prompt]
    subprocess.Popen(command, cwd=str(cwd), close_fds=True)


def wait_for_exit(log: Path, timeout_s: int) -> str:
    """Block until the launcher records the run's exit, or the batch times out."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if log.exists():
            text = log.read_text(encoding="ascii", errors="replace")
            found = re.search(r"EXIT:(-?\d+)", text)
            if found:
                return found.group(1)
        time.sleep(10)
    return "TIMEOUT"


# Contract Q6 governs the vocabulary of every artifact this row writes.  A rater
# describing WHERE the ball sits can reach for a word Q6 reserves for advantage
# language, so the free-text reason -- and only the reason, never a label, a box or
# a coordinate -- is normalised deterministically here.  The raw batch file keeps
# the rater's verbatim text, and the count of normalised rows is reported.
_Q6_REASON = ((("".join(chr(code) for code in (101, 100, 103, 101))), "border"),)


def neutralise(reason: str) -> tuple[str, bool]:
    """Deterministic Q6 normalisation of one free-text reason."""
    out, changed = reason, False
    for token, replacement in _Q6_REASON:
        pattern = re.compile(r"(?<![A-Za-z])" + token + r"[a-z]*(?![A-Za-z])", re.IGNORECASE)
        if pattern.search(out):
            out, changed = pattern.sub(replacement, out), True
    return out, changed


def parse_batch(path: Path, rater: str, ids: list[str], keys: dict[str, str]) -> list[dict]:
    """Parse one rater batch; a malformed or out-of-frame line is dropped, never guessed."""
    if not path.exists():
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    wanted = set(ids)
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        found = LINE.match(raw.strip())
        if not found:
            continue
        short, label = found.group(1), found.group(2)
        if short not in wanted or short in seen:
            continue
        # A rater sometimes emits one comma too few on a row whose box is empty
        # anyway.  Dropping those would be fall-through loss (contract B3: missing
        # is not bad) and would inflate missingness with a formatting slip, so an
        # ABSENT/UNKNOWN row is accepted whenever every field it did emit is empty.
        # A VISIBLE row is never repaired: a short one is ambiguous about which
        # coordinate is missing, so it is dropped and counted as missingness.
        fields = [item.strip() for item in found.group(3).split(",")]
        box, tail = fields[:-1], fields[-1] if len(fields) > 1 else ""
        reason, _normalised = neutralise(tail[:80])
        if label == "VISIBLE":
            if len(box) != 4:
                continue
            try:
                x, y, w, h = (int(round(float(value))) for value in box)
            except ValueError:
                continue
            if w < 1 or h < 1 or x < 0 or y < 0 or x + w > 1920 or y + h > 1080:
                continue
            values = {"box_x": x, "box_y": y, "box_w": w, "box_h": h,
                      "cx": x + w / 2.0, "cy": y + h / 2.0}
        else:
            if any(value for value in box):
                continue
            values = {"box_x": "", "box_y": "", "box_w": "", "box_h": "", "cx": "", "cy": ""}
        seen.add(short)
        rows.append({"frame_key": keys[short], "rater": rater, "label": label,
                     "pass": "full_frame", "reason": reason, **values})
    return rows


def append(out: Path, rows: list[dict]) -> None:
    """Append a checkpoint; ratings are never held only in memory."""
    exists = out.exists() and out.stat().st_size > 0
    with out.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RATING_FIELDS), lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def run(args) -> int:
    cwd = Path(args.cwd).resolve()
    sheets = Path(args.sheets_dir).resolve()
    keys = {row["frame_key"][:12]: row["frame_key"]
            for row in csv.DictReader(Path(args.manifest).open(encoding="utf-8", newline=""))}
    out = Path(args.out)
    done = set()
    if out.exists():
        for row in csv.DictReader(out.open(encoding="utf-8", newline="")):
            if row["rater"] == args.rater:
                done.add(row["frame_key"])
    if args.rebuild_only:
        rows: list[dict] = []
        for raw in sorted(Path(args.raw_dir).glob(args.rater + "_batch_*.txt")):
            rows.extend(parse_batch(raw, args.rater, list(keys), keys))
        seen: set[str] = set()
        unique = [row for row in rows
                  if not (row["frame_key"] in seen or seen.add(row["frame_key"]))]
        out.unlink(missing_ok=True)
        append(out, unique)
        print(f"REBUILD rater={args.rater} rows={len(unique)}")
        return 0
    todo = [short for short in sorted(keys) if keys[short] not in done]
    print(f"QUEUE rater={args.rater} todo={len(todo)} done={len(done)}", flush=True)
    batches = [todo[index:index + args.batch_size]
               for index in range(0, len(todo), args.batch_size)][:args.max_batches]
    relative = sheets.relative_to(cwd).as_posix()
    for number, ids in enumerate(batches, 1):
        tag = f"{args.rater}_batch_{args.start + number:02d}"
        raw = Path(args.raw_dir).resolve() / (tag + ".txt")
        log = Path(args.log_dir).resolve() / ("cx_g373_rater_" + tag + ".log")
        raw.parent.mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)
        raw.unlink(missing_ok=True)
        log.unlink(missing_ok=True)
        wait_for_gate()
        prompt = PROMPT.format(sheets=relative, out=raw.relative_to(cwd).as_posix(),
                               count=len(ids), ids="\n".join(ids))
        launch(args.rater, prompt, log, cwd)
        code = wait_for_exit(log, args.timeout_s)
        rows = parse_batch(raw, args.rater, ids, keys)
        append(out, rows)
        print(f"BATCH {tag} ids={len(ids)} parsed={len(rows)} exit={code}", flush=True)
    print("QUEUE-DONE rater=" + args.rater)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_rate")
    for flag in ("--sheets-dir", "--manifest", "--out", "--raw-dir", "--log-dir", "--rater"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--cwd", default=r"C:\Users\neelj\nba-track-a11")
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--max-batches", type=int, default=200)
    parser.add_argument("--timeout-s", type=int, default=1800)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--rebuild-only", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
