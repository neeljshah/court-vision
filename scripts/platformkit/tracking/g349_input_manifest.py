"""Write hashes for the raw inputs named by a G349 window manifest."""
from __future__ import annotations
import argparse
import csv
import hashlib
from pathlib import Path

def _ids(manifest: Path) -> list[str]:
    with manifest.open(encoding="utf-8", newline="") as handle:
        return [row["window_id"] for row in csv.DictReader(line for line in handle if not line.startswith("#"))]
def _hash(path: Path) -> tuple[str, str]:
    try:
        data = path.read_bytes()
    except OSError:
        return "000000000000", "ABSENT"
    return f"{len(data):012d}", hashlib.sha256(data).hexdigest()
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tracking-root")
    args = parser.parse_args()
    choices = [Path(args.tracking_root)] if args.tracking_root else [Path("data/tracking"), Path(r"C:/Users/neelj/nba-ai-system/data/tracking")]
    root = next((path for path in choices if path.is_dir()), choices[0])
    rows = []
    for window_id in _ids(args.manifest):
        for name in ("tracking_data.csv", "ball_tracking.csv"):
            relative = Path(window_id) / name
            size, digest = _hash(root / relative)
            rows.append((relative.as_posix(), size, digest))
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("path", "byte_size", "sha256"))
        writer.writerows(rows)
if __name__ == "__main__":
    main()
