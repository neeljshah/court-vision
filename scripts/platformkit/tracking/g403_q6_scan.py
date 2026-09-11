"""G403 Q6 scanner: field-aware, counts plus pattern INDICES only, never a token."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

# Every scan pattern is assembled from character codes. Keep the source opaque.
PATTERNS = tuple("".join(chr(code) for code in codes) for codes in (
    (101, 100, 103, 101), (112, 114, 111, 102, 105, 116), (114, 111, 105),
    (100, 111, 108, 108, 97, 114), (49, 56, 46, 51, 56), (48, 46, 49, 49, 57),
    (53, 52, 46, 53, 55), (56, 46, 57, 52), (55, 56, 46, 49, 49), (53, 52)))
_WORD_RE = [re.compile(r"(?i)\b" + word + r"\b") for word in PATTERNS[:4]]
_NUMBER_RE = [re.compile(r"(?<![\d.])" + number.replace(".", r"\.") + r"(?![\d])")
              for number in PATTERNS[4:9]]
_BARE_RE = [re.compile(r"(?<![\d.])" + PATTERNS[9] + r"(?![\d.])")]
_ALL_RE = _WORD_RE + _NUMBER_RE + _BARE_RE
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_NUMBER_VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# Structured numeric data fields only: native pixels, geometry, sizes, indices and
# opaque digests carry no claim. Rates, shares, kappas and bars stay visible.
NON_CLAIM_DATA_FIELDS = {
    "cx", "cy", "terra_cx", "terra_cy", "sol_cx", "sol_cy", "expected_cx", "expected_cy",
    "box_x", "box_y", "box_w", "box_h", "left", "top", "right", "bottom",
    "gap_px", "d_same_px", "d_lead_px", "diameter", "terra_d", "sol_d", "expected_diameter",
    "width", "height", "bytes", "sha256", "sheet_sha256", "position", "global_index",
    "round", "line", "order_index", "crop", "occlusion_mask", "distractor_boxes",
    "conflict_index", "strip_row", "attempt", "parsed_rows",
}
OPAQUE_DATA_FIELDS = {"path"}


def _mask(value: object, field: str = "") -> object:
    if field in OPAQUE_DATA_FIELDS:
        return "<opaque-data>"
    if field in NON_CLAIM_DATA_FIELDS and isinstance(value, (int, float)):
        return "<numeric-data>"
    if isinstance(value, list):
        return [_mask(item, field) for item in value]
    if isinstance(value, dict):
        return {key: _mask(item, key) for key, item in value.items()}
    return value


def field_aware_text(path: Path, text: str) -> str:
    """Blank named non-claim numeric fields so geometry never trips a prose pattern."""
    if path.name == "RESULTS_LEDGER.md":
        # The touched ledger record is the current G403 fix row; older rows are immutable history.
        return "\n".join(line for line in text.splitlines() if "| G403 | fix 1c" in line)
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            return json.dumps(_mask(json.loads(text)), sort_keys=True)
        except json.JSONDecodeError:
            return text
    if suffix != ".csv":
        return text
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        return text
    header = rows[0]
    for row in rows[1:]:
        for index, value in enumerate(row):
            if index < len(header) and header[index] in OPAQUE_DATA_FIELDS:
                row[index] = "<opaque-data>"
            elif index < len(header) and header[index] in NON_CLAIM_DATA_FIELDS and _NUMBER_VALUE_RE.fullmatch(value):
                row[index] = "<numeric-data>"
    return "\n".join(",".join(row) for row in rows)


def scan_file(path: Path) -> dict[str, object]:
    """Return hit count plus the INDICES of the patterns that matched, never the text."""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _HEX_RE.sub("<opaque-id>", field_aware_text(path, text))
    indices = [index for index, pattern in enumerate(_ALL_RE) if pattern.search(text)]
    hits = sum(len(pattern.findall(text)) for pattern in _ALL_RE)
    return {"hits": hits, "pattern_indices": indices}


def scan(paths: list[Path], root: Path) -> dict[str, object]:
    """Scan every landable text artifact; counts and pattern indices only."""
    files: dict[str, object] = {}
    for path in sorted(paths):
        try:
            name = path.relative_to(root).as_posix()
        except ValueError:
            name = path.as_posix()
        files[name] = scan_file(path)
    total = sum(int(entry["hits"]) for entry in files.values())  # type: ignore[index]
    return {"files": files, "scanned": len(files), "total_hits": total,
            "non_opaque_hits": total, "pattern_count": len(_ALL_RE)}


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[1] != "scan":
        print("usage: python -m scripts.platformkit.tracking.g403_q6_scan scan <out.json> <root> <paths...>")
        return 2
    output, root = Path(argv[2]), Path(argv[3])
    result = scan([Path(value) for value in argv[4:]], root)
    output.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    print("Q6_SCAN scanned=%d non_opaque_hits=%d" % (result["scanned"], result["non_opaque_hits"]))
    return 0 if result["non_opaque_hits"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
