"""Decompose observed player coverage into a framing proxy and residual term."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.tracking_harness import SPORTS


@dataclass(frozen=True)
class FramingReport:
    """Coverage decomposition for one canonical tracking CSV."""

    n_frames: int
    visible_span_ft_p50: float
    visible_span_ft_p90: float
    pct_frames_wide: float
    coverage_ge8_all: float
    coverage_ge8_wide: float
    coverage_ge8_narrow: float
    framing_share: float
    detection_share: float
    proxy_note: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return asdict(self)


def _columns(frame: pd.DataFrame) -> tuple[str, str, str]:
    track = next((name for name in ("track_id", "player_id") if name in frame), None)
    x_value = next((name for name in ("x", "x_position", "ft_x") if name in frame), None)
    if not track or not x_value or "frame" not in frame:
        raise ValueError("tracking rows require frame, player_id or track_id, and x_position or x")
    return track, x_value, "cls" if "cls" in frame else ""


def _players(frame: pd.DataFrame) -> tuple[pd.DataFrame, str, str]:
    track, x_value, class_name = _columns(frame)
    rows = frame.copy()
    if class_name:
        rows = rows.loc[rows[class_name].astype("string").str.lower().eq("player")]
    rows[x_value] = pd.to_numeric(rows[x_value], errors="coerce")
    return rows.dropna(subset=["frame", track, x_value]), track, x_value


def edge_clip_flags(frame: pd.DataFrame, frame_width: float | None = None) -> pd.Series:
    """Return per-row flags for boxes touching a known image edge within 2 px.

    Canonical CSVs do not guarantee image width, so no right-edge flag is
    inferred unless ``frame_width`` or a frame-width column is available.
    """
    flags = pd.Series(False, index=frame.index)
    if "bbox_x1" in frame:
        flags |= pd.to_numeric(frame["bbox_x1"], errors="coerce").le(2)
    width = frame_width
    if width is None:
        for name in ("frame_width", "image_width", "video_width"):
            if name in frame:
                width = pd.to_numeric(frame[name], errors="coerce")
                break
    if "bbox_x2" in frame and width is not None:
        flags |= pd.to_numeric(frame["bbox_x2"], errors="coerce").ge(width - 2)
    return flags.fillna(False)


def analyze_dataframe(frame: pd.DataFrame, sport: str) -> FramingReport:
    """Compute the explicitly proxy-based framing decomposition for one table."""
    if sport not in SPORTS:
        raise ValueError("unknown sport {}".format(sport))
    players, track, x_value = _players(frame)
    all_frames = pd.Index(frame["frame"].dropna().unique())
    n_frames = len(all_frames)
    court_length = float(SPORTS[sport]["bounds"][1] - SPORTS[sport]["bounds"][0])
    spans = players.groupby("frame")[x_value].agg(lambda values: values.max() - values.min())
    wide = spans.ge(0.60 * court_length)
    counts = players.groupby("frame")[track].nunique()
    covered = counts.reindex(all_frames, fill_value=0).ge(8)
    wide_all = wide.reindex(all_frames, fill_value=False)
    coverage_all = float(covered.mean()) if n_frames else 0.0
    coverage_wide = float(covered[wide_all].mean()) if wide_all.any() else float("nan")
    coverage_narrow = float(covered[~wide_all].mean()) if (~wide_all).any() else float("nan")
    denominator = 1.0 - coverage_all
    framing_share = ((coverage_wide - coverage_all) / denominator
                     if denominator > 0.0 and np.isfinite(coverage_wide) else float("nan"))
    detection_share = 1.0 - framing_share if np.isfinite(framing_share) else float("nan")
    return FramingReport(
        n_frames=n_frames,
        visible_span_ft_p50=float(spans.quantile(0.50)) if len(spans) else float("nan"),
        visible_span_ft_p90=float(spans.quantile(0.90)) if len(spans) else float("nan"),
        pct_frames_wide=float(wide_all.mean()) if n_frames else 0.0,
        coverage_ge8_all=coverage_all,
        coverage_ge8_wide=coverage_wide,
        coverage_ge8_narrow=coverage_narrow,
        framing_share=framing_share,
        detection_share=detection_share,
        proxy_note=("Framing is proxied by observed court-x span; bbox edge clips are "
                    "available via edge_clip_flags but no court polygon is present."),
    )


def analyze_csv(path: str | Path, sport: str,
                output_root: str | Path = ".planning/tracking/framing") -> FramingReport:
    """Read one CSV and serialize its report without modifying the input."""
    source = Path(path)
    report = analyze_dataframe(pd.read_csv(source), sport)
    destination = Path(output_root) / "{}.json".format(source.parent.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), indent=2, allow_nan=True), encoding="ascii")
    return report


def sha256(path: str | Path) -> str:
    """Return the input hash used to verify analysis-only operation."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute framing-conditioned coverage proxy.")
    parser.add_argument("path", type=Path)
    parser.add_argument("sport", choices=sorted(SPORTS))
    parser.add_argument("--output-root", default=".planning/tracking/framing")
    args = parser.parse_args()
    report = analyze_csv(args.path, args.sport, args.output_root)
    print(json.dumps(report.to_dict(), ensure_ascii=True, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
