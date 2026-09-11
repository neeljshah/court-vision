"""G396 prepare-only premise and control-identity helpers."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g396_protocol as protocol

SEED = 396
ANGLES = (0, 30, 60)
TILE_POSITIONS = (1, 2, 3, 4, 5, 6)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rehash_identities(census: Path, transforms: Path, cache: Path) -> dict[str, object]:
    """Rehash parent natives, contexts, and tiles without reading a whole store."""
    natives = [row for row in _rows(census) if row.get("retained") == "RETAINED"]
    tiles = _rows(transforms)
    contexts = {row["context"]: row["context_sha256"] for row in tiles}
    native_bad = [row["frame_key"] for row in natives if not Path(row["native_path"]).is_file()
                  or _digest(Path(row["native_path"])) != row["native_sha256"]]
    context_bad = [name for name, digest in contexts.items() if not (cache / name).is_file()
                   or _digest(cache / name) != digest]
    tile_bad = [row["tile"] for row in tiles if not (cache / row["tile"]).is_file()
                or _digest(cache / row["tile"]) != row["tile_sha256"]]
    return {"retained_natives": len(natives), "native_bad": native_bad,
            "contexts": len(contexts), "context_bad": context_bad,
            "tiles": len(tiles), "tile_bad": tile_bad,
            "parent_decode_failures": len(_rows(census)) - len(natives),
            "holds": len(natives) == 49 and len(contexts) == 30 and len(tiles) == 180
            and len(_rows(census)) == 60 and not native_bad and not context_bad and not tile_bad}


def premise(scores: Path, eligibility: Path, identity: dict[str, object]) -> dict[str, object]:
    """Recompute the fixed G392 before-condition before preparing G396."""
    rows = _rows(scores)
    totals = {rater: sum(row.get("passed") == "1" for row in rows if row.get("rater") == rater)
              for rater in ("sol", "terra")}
    by_id = {row["control_id"]: {} for row in rows}
    for row in rows:
        by_id.setdefault(row["control_id"], {})[row["rater"]] = row.get("passed") == "1"
    joint = sum(values.get("sol") and values.get("terra") for values in by_id.values())
    parent = json.loads(eligibility.read_text(encoding="utf-8"))
    holds = (len(rows) == 60 and len(by_id) == protocol.CONTROL_COUNT and totals == {"sol": 30, "terra": 20}
             and joint == 20 and parent.get("real_scored") is False and bool(identity.get("holds")))
    return {"g392_rows": len(rows), "g392_controls": len(by_id), "sol": totals["sol"],
            "terra": totals["terra"], "joint": joint, "real_scored": parent.get("real_scored"),
            "identity": identity, "holds": holds}


def control_plan(kind: str) -> list[dict[str, object]]:
    """Return the fixed non-pixel schedule for one new G396 control set."""
    if kind not in {"practice", "qualification"}:
        raise ValueError("kind must be practice or qualification")
    shift = 0 if kind == "practice" else 1
    return [{"control_id": "G396_%s_%03d" % (kind.upper(), index + 1), "seed": SEED,
             "tile_index": TILE_POSITIONS[(index + shift) % len(TILE_POSITIONS)],
             "angle_degrees": ANGLES[(index + shift) % len(ANGLES)]}
            for index in range(protocol.CONTROL_COUNT)]


def controls_disjoint(new_rows: list[dict[str, str]], old_rows: list[dict[str, str]]) -> bool:
    """Reject any reused control pixels or finite-band truth tuple."""
    keys = lambda rows: {(row.get("image_sha256", ""), row.get("source_context", ""), row.get("tile_index", ""),
                          row.get("x1", ""), row.get("y1", ""), row.get("x2", ""), row.get("y2", "")) for row in rows}
    return not (keys(new_rows) & keys(old_rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--eligibility", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--transforms", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = premise(args.scores, args.eligibility, rehash_identities(args.census, args.transforms, args.cache))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["holds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
