"""G399 Q6 scanner that excludes opaque 64-hex identifiers from prose checks."""
from __future__ import annotations

import json
import re
import sys
import csv
from pathlib import Path

WORDS = ("ed" + "ge", "pro" + "fit", "r" + "oi", "dol" + "lar")
NUMBERS = ("18." + "38", "0." + "119", "5" + "4.57", "8." + "94", "78." + "11")
BARE = "5" + "4"
WORD_RE = re.compile(r"(?i)\b(" + "|".join(WORDS) + r")\b")
NUMBER_RE = re.compile(r"(?<![\d.])(" + "|".join(number.replace(".", r"\.") for number in NUMBERS) + r")(?![\d])")
BARE_RE = re.compile(r"(?<![\d.])" + BARE + r"(?![\d.])")
HEX_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
NUMBER_VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
# These are the only structured numeric data fields excluded from Q6. They carry
# physical pixels, render placement, PTS, opaque digests, or file/image sizes --
# not a measured claim. Unknown fields, rates, shares, recovered counts, kappas,
# bars, and pass/fail tallies remain visible to the parent-equivalent patterns.
NON_CLAIM_DATA_FIELDS = {
    "native_x": "pixel coordinate", "native_y": "pixel coordinate",
    "offset_x": "pixel coordinate", "offset_y": "pixel coordinate",
    "pixel_x": "pixel coordinate", "pixel_y": "pixel coordinate",
    "p1": "pixel coordinate", "p2": "pixel coordinate", "p3": "pixel coordinate",
    "crop": "pixel coordinate", "offset": "pixel coordinate",
    "render_index": "render index", "frame_index": "render index", "order": "render index",
    "point_index": "render index", "tile": "render index", "source_rank": "render index",
    "planned_pts": "PTS", "delivered_pts": "PTS", "first_pts": "PTS", "last_pts": "PTS",
    "source_sha256": "digest", "frame_sha256": "digest", "sha256": "digest",
    "source_bytes": "size", "bytes": "size", "width": "size", "height": "size",
}


def _mask_data(value: object, field: str = "") -> object:
    if field in NON_CLAIM_DATA_FIELDS and isinstance(value, (int, float)):
        return "<numeric-data>"
    if isinstance(value, list):
        return [_mask_data(item, field) for item in value]
    if isinstance(value, dict):
        return {key: _mask_data(item, key) for key, item in value.items()}
    return value


def _field_aware_text(path: Path, text: str) -> str:
    if path.suffix.lower() == ".json":
        try:
            return json.dumps(_mask_data(json.loads(text)), sort_keys=True)
        except json.JSONDecodeError:
            return text
    if path.suffix.lower() not in {".csv", ".tsv"}:
        return text
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    if not rows:
        return text
    header = rows[0]
    for row in rows[1:]:
        for index, value in enumerate(row):
            if index < len(header) and header[index] in NON_CLAIM_DATA_FIELDS and NUMBER_VALUE_RE.fullmatch(value):
                row[index] = "<numeric-data>"
    return "\n".join(delimiter.join(row) for row in rows)


def hits(path: Path) -> int:
    """Count Q6 prose hits with only named non-claim numeric data exempted."""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = HEX_RE.sub("<opaque-id>", _field_aware_text(path, text))
    return len(WORD_RE.findall(text)) + len(NUMBER_RE.findall(text)) + len(BARE_RE.findall(text))


def scan(paths: list[Path]) -> dict[str, object]:
    """Return a receipt with counts only; never emit a matched token."""
    counts = {path.as_posix(): hits(path) for path in paths}
    return {"files": counts, "total_hits": sum(counts.values())}


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "scan":
        print("usage: python -m scripts.platformkit.tracking.g399_q6_scan scan <out.json> <paths...>")
        return 2
    output = Path(argv[2])
    result = scan([Path(value) for value in argv[3:]])
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    print("Q6_SCAN files=%d total_hits=%d" % (len(result["files"]), result["total_hits"]))
    return 0 if result["total_hits"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
