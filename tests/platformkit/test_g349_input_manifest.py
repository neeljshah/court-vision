"""G349 fix 1b: the input manifest helper hashes present files and marks absent ones."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g349_input_manifest import _hash, _ids


def test_hash_present_file_reports_size_and_sha256(tmp_path: Path) -> None:
    target = tmp_path / "tracking_data.csv"
    payload = b"frame,x,y\n000001,1,2\n"
    target.write_bytes(payload)
    size, digest = _hash(target)
    assert size == f"{len(payload):012d}"
    assert digest == hashlib.sha256(payload).hexdigest()


def test_hash_absent_file_is_marked_absent(tmp_path: Path) -> None:
    size, digest = _hash(tmp_path / "missing.csv")
    assert size == "000000000000"
    assert digest == "ABSENT"


def test_ids_skip_comment_lines(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# sealed list\n")
        writer = csv.writer(handle)
        writer.writerow(["window_id", "note"])
        writer.writerow(["0022500630", "a"])
        writer.writerow(["0022500906", "b"])
    assert _ids(manifest) == ["0022500630", "0022500906"]
