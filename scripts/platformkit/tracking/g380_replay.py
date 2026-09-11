"""G380 paired scratch replay: original vs patched producer on preserved sections.

One pinned scratch copy of the deploy tree serves BOTH arms, so weights and caps
are identical by construction; only the four producer files are swapped. Sources
are copied a few at a time and deleted after both arms, ahead of the guard."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from scripts.platformkit.tracking import g380_patch, g380_report

DEPLOY = Path("/workspace/deploy/nba-ai-system")
CORPUS = Path("/workspace/data/footage_corpus")
NEW_COLUMNS = ("position_source", "source_branch", "matched_event_id")
DU_STOP_MB = 40800
PAIR_FIELDS = ("idx", "game_id", "source_name", "source_bytes", "arm_order", "before_s",
               "before_rc", "after_s", "after_rc", "ratio", "status")
IDENTITY_FIELDS = ("game_id", "rows_before", "rows_after", "cols_before", "cols_after",
                   "canonical_sha256_before", "canonical_sha256_after", "identical",
                   "ball_sha256_before", "ball_sha256_after", "ball_identical", "first_diff")
RECEIPT_FIELDS = ("game_id", "receipt_present", "receipt_ticks", "trace_ticks",
                  "receipt_equals_trace", "trace_subset_of_receipt", "receipt_only_ticks",
                  "attempted_frames_capped", "evaluated_frames", "label_counts")


def _first_int(cmd) -> int:
    out = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return int(out.stdout.split()[0])
    except (IndexError, ValueError):
        return -1


def du_mb(path="/workspace") -> int:
    return _first_int(["du", "-sm", path])


def free_vram_mib() -> int:
    return _first_int(["nvidia-smi", "--query-gpu=memory.free",
                       "--format=csv,noheader,nounits"])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(path: Path, drop: tuple) -> tuple:
    """Re-serialize a CSV without `drop` columns so the two arms are comparable."""
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        keep = [i for i, name in enumerate(header) if name not in drop]
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow([header[i] for i in keep])
        rows = 0
        for row in reader:
            writer.writerow([row[i] if i < len(row) else "" for i in keep])
            rows += 1
    text = buffer.getvalue()
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), rows, len(header), text


def restore(tree: Path) -> None:
    """Return the scratch tree's producer files to the deployed bytes."""
    for rel in g380_patch.FILES:
        target = tree / rel
        target.unlink(missing_ok=True)
        os.link(DEPLOY / rel, target)


def run_arm(tree: Path, source: Path, game_id: str, out_dir: Path, trace: Path | None) -> tuple:
    env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1")
    if trace is not None:
        env["G380_TRACE"] = str(trace)
        env["PYTHONPATH"] = str(Path("/workspace/g380_scratch/hook"))
    cmd = [sys.executable, "scripts/run_clip.py", "--video=" + str(source),  # "=" form:
           "--game-id=" + game_id, "--no-show", "--frames", "3000",  # a leading "-" in a
           "--data-dir=" + str(out_dir)]  # game_id is read as a flag by argparse
    start = time.time()
    with (out_dir.parent / (game_id + ".log")).open("w", encoding="utf-8") as handle:
        proc = subprocess.run(cmd, cwd=str(tree), env=env, stdout=handle,
                              stderr=subprocess.STDOUT)
    return round(time.time() - start, 2), proc.returncode


def cmd_plan(args) -> None:
    """Seal an even sample of the corpus as it stands right now."""
    items = sorted(p.name for p in CORPUS.glob("*.mp4"))
    seed = hashlib.sha256("|".join(items).encode("ascii")).hexdigest()
    k = min(args.k, len(items))
    step = len(items) / float(k)
    picks = [items[min(len(items) - 1, int(i * step))] for i in range(k)]
    rows = []
    for idx, name in enumerate(picks, 1):
        game_id = name[:-4].split("__", 1)[1]
        path = CORPUS / name
        rows.append({"idx": idx, "source_name": name, "game_id": game_id,
                     "video": game_id.split("_s")[0],
                     "source_bytes": path.stat().st_size if path.exists() else 0})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("idx", "source_name", "game_id", "video",
                                                    "source_bytes"))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"corpus_n": len(items), "corpus_listing_sha256": seed, "k": k,
                      "distinct_videos": len({r["video"] for r in rows})}, sort_keys=True))


def cmd_prefetch(args) -> None:
    """Copy the next few planned sources into scratch before the guard prunes them."""
    scratch = Path(args.scratch) / "sources"
    scratch.mkdir(parents=True, exist_ok=True)
    with Path(args.plan).open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    status = {}
    for row in rows[args.skip:args.skip + args.limit]:
        src, copy = CORPUS / row["source_name"], scratch / row["source_name"]
        if copy.exists():
            status[row["game_id"]] = "PRESENT"
        elif not src.exists():
            status[row["game_id"]] = "SOURCE_GONE"
        elif du_mb() > DU_STOP_MB:
            status[row["game_id"]] = "DU_STOP"
        else:
            shutil.copyfile(src, copy)
            status[row["game_id"]] = "COPIED"
    print(json.dumps({"du_mb": du_mb(), "status": status}, sort_keys=True), flush=True)


def _append(path: Path, fields: tuple, row: dict) -> None:
    fresh = not path.exists()
    with path.open("a", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        if fresh:
            writer.writeheader()
        writer.writerow(row)


def _pair(row, tree, scratch, out, args) -> None:
    """Run both arms on one copied source, then delete every byte it needed."""
    game_id, name = row["game_id"], row["source_name"]
    src, copy = CORPUS / name, scratch / "sources" / name
    pair = {"idx": row["idx"], "game_id": game_id, "source_name": name,
            "source_bytes": row["source_bytes"], "arm_order": "BEFORE_AFTER"}
    if not copy.exists():
        if not src.exists():
            _append(out / "replay_pairs.csv", PAIR_FIELDS, {**pair, "status": "SOURCE_GONE"})
            return
        used = du_mb()
        if used > DU_STOP_MB:
            _append(out / "replay_pairs.csv", PAIR_FIELDS, {**pair, "status": "DU_STOP_%d" % used})
            raise SystemExit("DU STOP at %d MB" % used)
        shutil.copyfile(src, copy)
    dirs = {arm: scratch / ("out_" + arm) / game_id for arm in ("before", "after")}
    # The hook runs in the patched arm only and would inflate the seconds ratio.
    trace = scratch / "traces" / (game_id + ".trace") if args.keep else None
    try:
        for arm in ("before", "after"):
            while free_vram_mib() < args.min_vram:
                time.sleep(30)
            dirs[arm].mkdir(parents=True, exist_ok=True)
            if arm == "before":
                restore(tree)
                seconds, rc = run_arm(tree, copy, game_id, dirs[arm], None)
                pair["before_s"], pair["before_rc"] = seconds, rc
            else:
                g380_patch.cmd_apply(argparse.Namespace(tree=str(tree)))
                if trace is not None:
                    trace.parent.mkdir(parents=True, exist_ok=True)
                seconds, rc = run_arm(tree, copy, game_id, dirs[arm], trace)
                pair["after_s"], pair["after_rc"] = seconds, rc
        pair["ratio"] = round(pair["after_s"] / pair["before_s"], 6) if pair.get("before_s") else ""
        pair["status"] = "OK" if pair.get("before_rc") == 0 and pair.get("after_rc") == 0 \
            else "ARM_FAILED"
        _compare(game_id, dirs, trace, out)
    finally:
        _append(out / "replay_pairs.csv", PAIR_FIELDS, pair)
        copy.unlink(missing_ok=True)
        if not args.keep:
            for path in dirs.values():
                shutil.rmtree(path, ignore_errors=True)


def _compare(game_id, dirs, trace, out) -> None:
    """Identity on every non-provenance column, plus receipt-versus-trace agreement."""
    before, after = dirs["before"] / "tracking_data.csv", dirs["after"] / "tracking_data.csv"
    identity = {"game_id": game_id}
    if before.is_file() and after.is_file():
        d_b, n_b, c_b, t_b = canonical(before, ())
        d_a, n_a, c_a, t_a = canonical(after, NEW_COLUMNS)
        identity.update(rows_before=n_b, rows_after=n_a, cols_before=c_b, cols_after=c_a,
                        canonical_sha256_before=d_b, canonical_sha256_after=d_a,
                        identical=d_b == d_a)
        if d_b != d_a:
            lines_b, lines_a = t_b.splitlines(), t_a.splitlines()
            hit = next((i for i, (x, y) in enumerate(zip(lines_b, lines_a)) if x != y), -1)
            identity["first_diff"] = "line %d" % hit if hit >= 0 else "length %d vs %d" % (
                len(lines_b), len(lines_a))
    else:
        identity.update(identical=False, first_diff="MISSING_CSV")
    for arm, key in (("before", "ball_sha256_before"), ("after", "ball_sha256_after")):
        ball = dirs[arm] / "ball_tracking.csv"
        identity[key] = sha256_file(ball) if ball.is_file() else "ABSENT"
    identity["ball_identical"] = identity["ball_sha256_before"] == identity["ball_sha256_after"]
    _append(out / "identity.csv", IDENTITY_FIELDS, identity)

    receipts = list((dirs["after"]).rglob("evaluated_tick_receipt.json"))
    traced = trace is not None and trace.is_file()
    emitted = g380_report._trace_rows(trace) if traced else []
    trace_ticks = sorted({item["frame"] for item in emitted})
    row = {"game_id": game_id, "receipt_present": bool(receipts),
           "trace_ticks": len(trace_ticks) if traced else "NOT_TRACED"}
    if receipts:
        data = json.loads(receipts[0].read_text(encoding="utf-8"))
        ids = sorted(int(x) for x in data.get("evaluated_tick_ids") or [])
        row.update(receipt_ticks=len(ids),
                   attempted_frames_capped=data.get("attempted_frames_capped"))
        if traced:
            row.update(receipt_equals_trace=ids == trace_ticks,
                       trace_subset_of_receipt=set(trace_ticks) <= set(ids),
                       receipt_only_ticks=len(set(ids) - set(trace_ticks)))
    if after.is_file():
        counts = {}
        with after.open(newline="", encoding="utf-8", errors="replace") as handle:
            for item in csv.DictReader(handle):
                key = item.get("position_source", "MISSING")
                counts[key] = counts.get(key, 0) + 1
        row["label_counts"] = json.dumps(counts, sort_keys=True)
        row["evaluated_frames"] = len(set(trace_ticks)) if traced else "NOT_TRACED"
    _append(out / "receipts.csv", RECEIPT_FIELDS, row)


def cmd_run(args) -> None:
    tree, scratch, out = Path(args.tree), Path(args.scratch), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (scratch / "sources").mkdir(parents=True, exist_ok=True)
    with Path(args.plan).open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    done = set()
    pairs = out / "replay_pairs.csv"
    if pairs.exists():
        with pairs.open(newline="", encoding="ascii") as handle:
            done = {item["game_id"] for item in csv.DictReader(handle)}
    for row in rows[args.skip:args.skip + args.limit]:
        if row["game_id"] in done:
            continue
        row["idx"], row["source_bytes"] = int(row["idx"]), int(row["source_bytes"])
        _pair(row, tree, scratch, out, args)
        print("pair %s done du=%d" % (row["game_id"], du_mb()), flush=True)
    restore(tree)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--out", required=True)
    plan.add_argument("--k", type=int, default=30)
    plan.set_defaults(handler=cmd_plan)
    run = sub.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--tree", default="/workspace/g380_scratch/armA")
    run.add_argument("--scratch", default="/workspace/g380_scratch")
    run.add_argument("--skip", type=int, default=0)
    run.add_argument("--limit", type=int, default=100)
    run.add_argument("--min-vram", type=int, default=3000)
    run.add_argument("--keep", action="store_true")  # keep outputs + trace for this pair
    run.set_defaults(handler=cmd_run)
    pre = sub.add_parser("prefetch")
    pre.add_argument("--plan", required=True)
    pre.add_argument("--scratch", default="/workspace/g380_scratch")
    pre.add_argument("--skip", type=int, default=0)
    pre.add_argument("--limit", type=int, default=5)
    pre.set_defaults(handler=cmd_prefetch)
    args = parser.parse_args()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
