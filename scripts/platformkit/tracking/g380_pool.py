"""G380 rotating-corpus source pool (prereg amendment A1).

The pod quota guard deletes ledgered corpus sections older than 90 minutes, so a
sealed NAME list cannot survive a multi-hour replay -- the first run lost 22 of 30
sources that way.  This tops the scratch pool up from the corpus AS IT ROTATES,
records the listing digest of every top-up, and appends each copy to the plan the
replay actually consumes.  It moves no bar; the sampling rule is the amendment.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

CORPUS = Path("/workspace/data/footage_corpus")
DU_STOP_MB = 40800
PLAN_FIELDS = ("idx", "source_name", "game_id", "video", "source_bytes")
COPY_FIELDS = ("copied_utc", "corpus_listing_sha256", "corpus_n", "source_name", "game_id",
               "source_bytes")


def du_mb(path: str = "/workspace") -> int:
    out = subprocess.run(["du", "-sm", path], capture_output=True, text=True)
    try:
        return int(out.stdout.split()[0])
    except (IndexError, ValueError):
        return -1


def _read(path: Path) -> list:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _append(path: Path, fields: tuple, rows: list) -> None:
    fresh = not path.exists()
    with path.open("a", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        if fresh:
            writer.writeheader()
        writer.writerows(rows)


def topup(plan: Path, pairs: Path, scratch: Path, budget: int) -> dict:
    """Copy up to `budget` unseen sections, evenly across the live corpus listing."""
    pool = scratch / "sources"
    pool.mkdir(parents=True, exist_ok=True)
    items = sorted(item.name for item in CORPUS.glob("*.mp4"))
    digest = hashlib.sha256("|".join(items).encode("ascii")).hexdigest()
    seen = {row["game_id"] for row in _read(plan)} | {row["game_id"] for row in _read(pairs)}
    held = len(list(pool.glob("*.mp4")))
    room = max(0, budget - held)
    fresh = [name for name in items if name[:-4].split("__", 1)[1] not in seen]
    picks, copied = [], []
    if fresh and room:
        step = len(fresh) / float(min(room, len(fresh)))
        picks = [fresh[min(len(fresh) - 1, int(i * step))] for i in range(min(room, len(fresh)))]
    start = len(_read(plan))
    for offset, name in enumerate(dict.fromkeys(picks)):
        source = CORPUS / name
        if not source.is_file() or du_mb() > DU_STOP_MB:
            break
        game_id = name[:-4].split("__", 1)[1]
        size = source.stat().st_size
        try:
            shutil.copyfile(source, pool / name)
        except OSError:
            continue
        copied.append({"copied_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "corpus_listing_sha256": digest, "corpus_n": len(items),
                       "source_name": name, "game_id": game_id, "source_bytes": size})
        _append(plan, PLAN_FIELDS, [{"idx": start + offset + 1, "source_name": name,
                                     "game_id": game_id, "video": game_id.split("_s")[0],
                                     "source_bytes": size}])
    _append(scratch / "ev" / "copy_manifest.csv", COPY_FIELDS, copied)
    return {"corpus_n": len(items), "corpus_listing_sha256": digest, "held_before": held,
            "copied": len(copied), "du_mb": du_mb(),
            "pool_now": len(list(pool.glob("*.mp4")))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--scratch", default="/workspace/g380_scratch")
    parser.add_argument("--budget", type=int, default=6)
    args = parser.parse_args()
    print(json.dumps(topup(Path(args.plan), Path(args.pairs), Path(args.scratch), args.budget),
                     sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
