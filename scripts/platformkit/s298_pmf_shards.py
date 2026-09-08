"""Reassemble the S298 PMF archive from committed <45MB shards and verify integrity.

The full PMF archive (73504906 bytes, SHA-256 b9da5f26...) is too large for a
single git blob under this repo's 45 MB commit rail, so it is committed as 8
row-range shards that concatenate back to the exact original decompressed
bytes. `load_pmf_shards()` streams that reconstruction one shard (gzip member)
at a time and hashes line-by-line, so it never materializes the ~329 MB
decompressed archive or a joined-rows copy in memory, then asserts the row
count and SHA-256 match the recorded constants below. `shard_manifest()`
derives the `artifacts.pmf_shards` object the scorer embeds in its JSON
payload straight from the committed shard files, so the writer and the
committed evidence always describe the same bytes.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARD_DIR = ROOT / "docs/evidence/harness"
SHARD_GLOB = "S298_rare_count_mixture_2026-09-07_pmfs_part*.csv.gz"
CANONICAL_ROW_COUNT = 630136
CANONICAL_DECOMPRESSED_BYTES = 328969124
CANONICAL_DECOMPRESSED_SHA256 = "c6e2db5f8a9b5a8ee0f524088043274d77539af06cf8fdb2e072705a7ab5c161"
ORIGINAL_ARCHIVE_BYTES = 73504906
ORIGINAL_ARCHIVE_SHA256 = "b9da5f26db957289ccf699e0e0dd604cab08f13c1b894ad7b974a191a5f9801e"


def _shard_parts() -> list[Path]:
    parts = sorted(SHARD_DIR.glob(SHARD_GLOB))
    if len(parts) != 8:
        raise AssertionError("expected 8 PMF shards, found {0}".format(len(parts)))
    return parts


def _iter_lines(path: Path):
    """Yield each decompressed line (newline stripped), streaming from disk."""
    with gzip.open(path, "rb") as handle:
        for line in handle:
            if not line.endswith(b"\n"):
                raise AssertionError(path.name + " missing trailing newline")
            yield line[:-1]


def load_pmf_shards() -> str:
    """Stream-reconstruct the canonical PMF CSV from shards; return its SHA-256 hex digest.

    Processes one shard at a time and hashes line-by-line, so at most one
    shard's decompressed lines are ever in flight (never the full ~329 MB
    canonical archive or a joined-rows copy).
    """
    digest, header, rows, total_bytes = hashlib.sha256(), None, 0, 0
    for part in _shard_parts():
        lines = _iter_lines(part)
        first = next(lines)
        if header is None:
            header = first
            digest.update(header + b"\n")
            total_bytes += len(header) + 1
        elif first != header:
            raise AssertionError(part.name + " header mismatch")
        for line in lines:
            digest.update(line + b"\n")
            total_bytes += len(line) + 1
            rows += 1
    if rows != CANONICAL_ROW_COUNT:
        raise AssertionError("row count {0} != {1}".format(rows, CANONICAL_ROW_COUNT))
    if total_bytes != CANONICAL_DECOMPRESSED_BYTES:
        raise AssertionError("decompressed byte count {0} != {1}".format(total_bytes, CANONICAL_DECOMPRESSED_BYTES))
    actual = digest.hexdigest()
    if actual != CANONICAL_DECOMPRESSED_SHA256:
        raise AssertionError("canonical SHA-256 mismatch: " + actual)
    return actual


def shard_manifest() -> dict:
    """Build the `artifacts.pmf_shards` object from the committed shard files on disk.

    Re-validates the streamed canonical reconstruction first, so a manifest is
    never published for a shard set that fails to reassemble.
    """
    load_pmf_shards()
    shards = []
    for part in _shard_parts():
        raw = part.read_bytes()
        rows = sum(1 for _ in _iter_lines(part)) - 1  # exclude header
        shards.append({"name": part.name, "bytes": len(raw), "rows": rows,
                        "sha256": hashlib.sha256(raw).hexdigest()})
    return {"reader": "scripts/platformkit/s298_pmf_shards.py",
            "canonical_row_count": CANONICAL_ROW_COUNT,
            "canonical_decompressed_sha256": CANONICAL_DECOMPRESSED_SHA256,
            "original_archive_bytes": ORIGINAL_ARCHIVE_BYTES,
            "original_archive_sha256": ORIGINAL_ARCHIVE_SHA256,
            "shards": shards}


def pmf_shard_artifacts() -> dict:
    """Return {"pmf_shards": manifest} when all 8 committed shards are present; else {}.

    Lets the scorer's `artifacts` payload agree with the committed JSON
    without ever emitting a stale or partial manifest on a fresh run that has
    not been sharded yet.
    """
    if len(list(SHARD_DIR.glob(SHARD_GLOB))) != 8:
        return {}
    return {"pmf_shards": shard_manifest()}


def main() -> None:
    digest = load_pmf_shards()
    print("S298_PMF_SHARDS_OK rows={0} sha256={1} bytes={2}".format(
        CANONICAL_ROW_COUNT, digest, CANONICAL_DECOMPRESSED_BYTES))


if __name__ == "__main__":
    main()
