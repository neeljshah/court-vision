"""Per-decoded-frame accounting for tennis tracking output."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


FRAME_MANIFEST_SCHEMA = (
    "frame", "evaluated", "status", "calibration_provenance", "emitted_player_rows",
)


def frame_manifest_path(tracking_path: str | Path) -> Path:
    """Return the required sidecar path for a tracking CSV."""
    return Path(tracking_path).with_name("frame_manifest.csv")


def write_frame_manifest(rows: pd.DataFrame, tracking_path: str | Path) -> None:
    """Persist every decoded-frame outcome beside its tracking CSV."""
    rows.reindex(columns=FRAME_MANIFEST_SCHEMA).to_csv(
        frame_manifest_path(tracking_path), index=False
    )
