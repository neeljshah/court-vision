"""G392 prepare-only premise accounting and packet configuration helpers."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from scripts.platformkit.tracking import g392_protocol as protocol

RATERS = ("terra", "sol")
TILE_OFFSETS = ((0, 0), (640, 0), (1280, 0), (0, 540), (640, 540), (1280, 540))
ANGLES = (0, 30, 60)
SEED = 392


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _passes(rows: list[dict[str, str]], name: str) -> int:
    return sum(row.get(name, "").strip().upper() == "YES" for row in rows)


def _qualified_successors(root: Path) -> list[str]:
    """Find only explicit true qualification flags, one JSON file at a time."""
    found = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and (payload.get("protocol_qualified") is True or payload.get("qualified") is True):
            found.append(path.as_posix())
    return found


def premise_receipt(sealed_controls: Path, limit_controls: Path, real_frames: Path, g388_summary: Path,
                    g387_census: Path, g387_selection: Path, tracking_evidence: Path) -> dict[str, object]:
    """Reproduce G388 accounting that must hold before G392 packet preparation."""
    sealed, limit, real = _rows(sealed_controls), _rows(limit_controls), _rows(real_frames)
    census, selection = _rows(g387_census), _rows(g387_selection)
    summary = json.loads(g388_summary.read_text(encoding="utf-8"))
    retained = [row for row in census if row.get("retained") == "RETAINED"]
    native_ready = [row for row in retained if row.get("status") == "READY" and row.get("width") == "1920" and row.get("height") == "1080"]
    receipt = {
        "sealed_controls": {"joint": _passes(sealed, "pass"), "terra": _passes(sealed, "terra_pass"), "sol": _passes(sealed, "sol_pass"), "denominator": len(sealed)},
        "limit_controls": {"joint": _passes(limit, "pass"), "terra": _passes(limit, "terra_pass"), "sol": _passes(limit, "sol_pass"), "denominator": len(limit)},
        "real_audited_recovery": {"passed": sum(row.get("audited_same_band") == "1" for row in real), "denominator": len(real)},
        "retained_native_identities": len(native_ready), "selected_context_identities": len(selection),
        "g388_protocol_qualified": summary.get("protocol_qualified"), "qualified_successors": _qualified_successors(tracking_evidence),
    }
    receipt["holds"] = (receipt["sealed_controls"] == {"joint": 10, "terra": 11, "sol": 28, "denominator": 30}
                        and receipt["limit_controls"] == {"joint": 13, "terra": 14, "sol": 28, "denominator": 30}
                        and receipt["real_audited_recovery"] == {"passed": 0, "denominator": 30}
                        and receipt["retained_native_identities"] == 49 and receipt["selected_context_identities"] == 30
                        and receipt["g388_protocol_qualified"] is False and not receipt["qualified_successors"])
    return receipt


def control_plan(kind: str) -> list[dict[str, object]]:
    """Return the frozen non-pixel schedule for one distinct 30-control set."""
    if kind not in {"practice", "qualification"}:
        raise ValueError("kind must be practice or qualification")
    shift = 0 if kind == "practice" else 1
    return [{"control_id": "G392_%s_%03d" % (kind.upper(), index + 1), "seed": SEED,
             "tile_index": (index + shift) % len(TILE_OFFSETS) + 1,
             "tile_offset": TILE_OFFSETS[(index + shift) % len(TILE_OFFSETS)],
             "angle_degrees": ANGLES[(index + shift) % len(ANGLES)],
             "truth_namespace": kind, "min_span_px": protocol.MIN_SPAN}
            for index in range(protocol.CONTROL_COUNT)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    premise = subparsers.add_parser("premise")
    for name in ("sealed_controls", "limit_controls", "real_frames", "g388_summary", "g387_census", "g387_selection", "tracking_evidence"):
        premise.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    premise.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = premise_receipt(args.sealed_controls, args.limit_controls, args.real_frames, args.g388_summary,
                              args.g387_census, args.g387_selection, args.tracking_evidence)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["holds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
