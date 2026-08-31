"""Render honest calibration-audit evidence charts from WP report JSON files."""
from __future__ import annotations

import argparse
import json
import math
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_REPO = Path(__file__).resolve().parents[2]
_SIZE = (1280, 720)


def _newest(report_dir: Path, prefix: str) -> Optional[Path]:
    paths = list(report_dir.glob(prefix + "*.json"))
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def _load(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _rows(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("reliability", "bins", "rows", "overall"):
            if isinstance(value.get(key), list):
                return _rows(value[key])
    return []


def _reliability(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _rows(report.get("reliability", report))


def _value(row: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def _points(rows: Sequence[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Optional[float]], List[Optional[float]]]:
    points = []
    for row in rows:
        predicted = _value(row, "mean_predicted_prob", "mean_pred", "predicted", "prediction")
        observed = _value(row, "observed_win_freq", "observed", "obs_freq", "actual")
        if predicted is not None and observed is not None:
            points.append((predicted, observed, _value(row, "n", "count", "sample_size") or 1.0,
                           _value(row, "ci_low", "wilson_low", "lower_ci"),
                           _value(row, "ci_high", "wilson_high", "upper_ci")))
    if not points:
        return np.array([]), np.array([]), np.array([]), [], []
    return (np.array([item[0] for item in points]), np.array([item[1] for item in points]),
            np.array([item[2] for item in points]), [item[3] for item in points],
            [item[4] for item in points])


def _plot_reliability(rows: Sequence[Dict[str, Any]], path: Path, title: str, label: str = "Observed") -> None:
    x, y, n, low, high = _points(rows)
    fig, axis = plt.subplots(figsize=(10, 5.625), dpi=128)
    axis.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect calibration")
    if len(x):
        sizes = 40 + 300 * n / max(n)
        if any(a is not None and b is not None for a, b in zip(low, high)):
            err_low = [max(0.0, yy - (aa if aa is not None else yy)) for yy, aa in zip(y, low)]
            err_high = [max(0.0, (bb if bb is not None else yy) - yy) for yy, bb in zip(y, high)]
            axis.errorbar(x, y, yerr=[err_low, err_high], fmt="none", color="#2563eb", alpha=.55)
        axis.scatter(x, y, s=sizes, color="#2563eb", alpha=.8, label=label)
        axis.plot(x, y, color="#2563eb", alpha=.45)
    axis.set(xlim=(0, 1), ylim=(0, 1), xlabel="Predicted win probability", ylabel="Observed win frequency", title=title)
    axis.grid(alpha=.2)
    axis.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _losers(report: Dict[str, Any]) -> Tuple[List[float], Dict[str, float]]:
    block = report.get("max_loser_wp", report.get("max_loser", {}))
    values = [_value(row, "max_loser_wp", "value") for row in block.get("per_game", []) if isinstance(row, dict)]
    quantiles = {str(key): float(value) for key, value in block.get("quantiles", {}).items()
                 if isinstance(value, (int, float))}
    return [value for value in values if value is not None], quantiles


def _plot_losers(report: Dict[str, Any], path: Path) -> bool:
    values, quantiles = _losers(report)
    if not values:
        return False
    fig, axis = plt.subplots(figsize=(10, 5.625), dpi=128)
    axis.hist(values, bins=np.linspace(0, 1, 21), color="#dc2626", alpha=.78, edgecolor="white")
    for label, value in sorted(quantiles.items(), key=lambda item: float(item[1])):
        axis.axvline(value, ls="--", lw=1.5, label="P%s %.2f" % (label, value))
    axis.set(xlim=(0, 1), xlabel="Maximum predicted WP for eventual loser", ylabel="Games",
             title="Max-loser win probability distribution")
    axis.grid(axis="y", alpha=.2)
    axis.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def _oos_pair(report: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    pairs = (("before_reliability", "after_reliability"), ("raw_reliability", "isotonic_reliability"),
             ("pre_isotonic_reliability", "post_isotonic_reliability"))
    for before, after in pairs:
        if before in report and after in report:
            return _rows(report[before]), _rows(report[after])
    for value in report.values():
        if isinstance(value, dict):
            found = _oos_pair(value)
            if found != ([], []):
                return found
    return [], []


def _plot_overlay(before: Sequence[Dict[str, Any]], after: Sequence[Dict[str, Any]], path: Path) -> None:
    fig, axis = plt.subplots(figsize=(10, 5.625), dpi=128)
    axis.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect calibration")
    for rows, color, label in ((before, "#dc2626", "Before isotonic"), (after, "#16a34a", "After isotonic")):
        x, y, n, _, _ = _points(rows)
        if len(x):
            axis.plot(x, y, "o-", color=color, label=label, ms=4 + min(max(n), 100) / 35)
    axis.set(xlim=(0, 1), ylim=(0, 1), xlabel="Predicted probability", ylabel="Observed frequency",
             title="OOS reliability: before and after isotonic")
    axis.grid(alpha=.2); axis.legend(loc="lower right")
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def _frame(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    return cv2.resize(image, _SIZE, interpolation=cv2.INTER_AREA)


def _title_card(title: str, caveats: str) -> np.ndarray:
    frame = np.full((_SIZE[1], _SIZE[0], 3), 22, dtype=np.uint8)
    cv2.putText(frame, title, (70, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.25, (240, 240, 240), 2, cv2.LINE_AA)
    y = 200
    for line in textwrap.wrap(caveats or "Calibration evidence only; not an edge claim.", 78):
        cv2.putText(frame, line, (70, y), cv2.FONT_HERSHEY_SIMPLEX, .7, (190, 210, 230), 1, cv2.LINE_AA); y += 42
    return frame


def _write_video(charts: Sequence[Tuple[str, Path]], caveats: str, path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, _SIZE)
    if not writer.isOpened():
        raise RuntimeError("unable to open MP4 writer")
    try:
        for title, chart in charts:
            for frame in (_title_card(title, caveats), _frame(chart)):
                for _ in range(120):
                    writer.write(frame)
    finally:
        writer.release()


def render(report_dir: Path, out_dir: Path, caveats: str = "") -> List[Path]:
    """Render all available calibration audit charts and their MP4 slideshow."""
    out_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = _load(_newest(report_dir, "wp_diagnostics_"))
    oos = _load(_newest(report_dir, "wp_oos_"))
    series = _load(_newest(report_dir, "wp_series_audit_"))
    charts: List[Tuple[str, Path]] = []
    rows = _reliability(diagnostics)
    if rows:
        path = out_dir / "reliability_diagram.png"; _plot_reliability(rows, path, "WP reliability diagram"); charts.append(("WP reliability diagram", path))
    path = out_dir / "max_loser_wp_histogram.png"
    if _plot_losers(series or diagnostics, path):
        charts.append(("Max-loser WP histogram", path))
    before, after = _oos_pair(oos)
    if before and after:
        path = out_dir / "oos_isotonic_overlay.png"; _plot_overlay(before, after, path); charts.append(("OOS isotonic reliability", path))
    if charts:
        _write_video(charts, caveats, out_dir / "calibration_audit.mp4")
    return [path for _, path in charts]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render calibration audit evidence charts.")
    parser.add_argument("--out-dir", type=Path, default=_REPO / "docs" / "evidence" / "calibration")
    parser.add_argument("--caveats", default="Calibration evidence only; not an edge claim.")
    args = parser.parse_args(argv)
    charts = render(_REPO / "data" / "ab_reports", args.out_dir, args.caveats)
    print("CHARTS: %d" % len(charts)); print("OUTPUT: %s" % args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
