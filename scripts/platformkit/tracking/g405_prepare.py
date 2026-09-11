"""G405 prepare-only evidence inventory; it performs no discovery or probing."""
from __future__ import annotations

from pathlib import Path

REQUIRED_ARTIFACTS = ("prereg.md", "premise_snapshot.json", "discovery_config_hashes.json",
                      "discovery_population.csv", "draw.csv", "raw_formats/", "metadata/",
                      "probe_receipts.csv", "format_rows.csv", "discovery_queue.jsonl",
                      "availability.csv", "eye_index.csv", "cards/", "summary.json",
                      "repeats.json", "runtime_receipts/", "SHA256SUMS")


def prepared_artifact_paths(evidence: Path) -> list[Path]:
    """Return all G405 destinations without creating them or reading a store."""
    return [Path(evidence) / item for item in REQUIRED_ARTIFACTS]
