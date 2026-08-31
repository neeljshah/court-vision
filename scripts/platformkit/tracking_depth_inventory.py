"""Report the observable depth of a basketball tracking CSV.

Run: python scripts/platformkit/tracking_depth_inventory.py [tracking.csv]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


# This is deliberately a hand-maintained production-schema map. Unknown columns
# remain visible and are conservatively placed in CONTEXT rather than discarded.
FAMILY_COLUMNS: dict[str, set[str]] = {
    "IDENTITY": {"track_id", "player_id", "player_name", "jersey_number", "jersey", "class", "cls", "confidence", "team_id"},
    "POSITION": {"x", "y", "x_position", "y_position", "court_x", "court_y", "x_court", "y_court", "bbox_x", "bbox_y", "bbox_w", "bbox_h", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "pose_x", "pose_y", "foot_x", "foot_y", "ankle_x", "ankle_y", "team_centroid_x", "team_centroid_y"},
    "MOTION": {"vx", "vy", "speed", "velocity", "acceleration", "accel", "heading", "direction", "direction_deg", "distance_traveled", "vertical_velocity", "contest_arm_angle", "ankle_angle", "hip_angle"},
    "TEAM/LINEUP": {"team", "team_side", "team_color", "lineup_id", "home_team", "away_team", "is_home", "is_offense", "is_defense", "position_role", "paint_count_own", "paint_count_opp"},
    "BALL": {"ball_x", "ball_y", "ball_x2d", "ball_y2d", "ball_z", "ball_speed", "ball_velocity", "ball_vx", "ball_vy", "ball_confidence", "ball_detected", "ball_possession", "ball_handler_id", "ball_track_id", "ball_distance", "distance_to_ball", "ball_shot_arc_angle", "ball_peak_height_px", "ball_pass_speed_pxpf", "dribble_hand"},
    "EVENTS": {"event", "event_type", "shot_type", "shot_made", "is_shot", "is_pass", "is_rebound", "is_turnover", "is_steal", "is_block", "is_foul", "is_possession_change", "jump_detected", "drive_flag", "fast_break_flag"},
    "SCOREBOARD-OCR": {"score_home", "score_away", "home_score", "away_score", "game_clock", "shot_clock", "shot_clock_est", "period", "quarter", "scoreboard_confidence", "ocr_confidence", "scoreboard_home", "scoreboard_away"},
    "CONTEXT": {"frame", "timestamp", "time", "game_id", "possession_id", "possession_number", "possession_team", "possession_side", "possession_type", "possession_duration", "play_type", "court_zone", "zone", "spacing", "team_spacing", "nearest_defender_distance", "defender_distance", "nearest_opponent", "nearest_teammate", "handler_isolation", "distance_to_basket", "vel_toward_basket", "camera_id", "source_video", "frame_width", "frame_height", "score_diff"},
}

COORDINATE_RANGES = {
    "x": (0.0, 94.0), "x_position": (0.0, 94.0), "court_x": (0.0, 94.0), "x_court": (0.0, 94.0), "ball_x": (0.0, 94.0), "ball_x2d": (0.0, 94.0), "foot_x": (0.0, 94.0), "ankle_x": (0.0, 94.0), "team_centroid_x": (0.0, 94.0),
    "y": (0.0, 50.0), "y_position": (0.0, 50.0), "court_y": (0.0, 50.0), "y_court": (0.0, 50.0), "ball_y": (0.0, 50.0), "ball_y2d": (0.0, 50.0), "foot_y": (0.0, 50.0), "ankle_y": (0.0, 50.0), "team_centroid_y": (0.0, 50.0),
}
FLAG_TOKENS = ("is_", "has_", "_flag", "_detected", "_made")


@dataclass
class ColumnInventory:
    name: str
    family: str
    non_null_pct: float
    distinct_values: int
    validity: str
    validity_pct: float | None


def family_for_column(name: str) -> str:
    """Return the capability family for a production-schema column."""
    key = name.strip().lower()
    for family, columns in FAMILY_COLUMNS.items():
        if key in columns:
            return family
    return "CONTEXT"


def _present(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def _numeric_validity(name: str, values: pd.Series) -> tuple[str, float | None]:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric = numeric.dropna()
    if numeric.empty:
        return "numeric parse rate", 0.0
    key = name.lower()
    if key in COORDINATE_RANGES:
        low, high = COORDINATE_RANGES[key]
        return f"pct within {low:g}..{high:g} court range", round(float(numeric.between(low, high).mean()) * 100, 2)
    if "speed" in key or key in {"acceleration", "accel", "distance_traveled", "ball_distance"}:
        return "pct >= 0", round(float((numeric >= 0).mean()) * 100, 2)
    if "confidence" in key:
        return "pct within 0..1", round(float(numeric.between(0, 1).mean()) * 100, 2)
    if key in {"frame", "period", "quarter", "timestamp", "time"}:
        return "pct >= 0", round(float((numeric >= 0).mean()) * 100, 2)
    return "no column-specific sane range", None


def _validity(name: str, series: pd.Series, present: pd.Series) -> tuple[str, float | None]:
    values = series[present]
    key = name.lower()
    if key.startswith(FLAG_TOKENS) or key in {"ball_detected", "shot_made"}:
        set_values = values.astype(str).str.strip().str.lower().isin(
            {"1", "1.0", "true", "yes", "y", "t"}
        )
        return "set flag rate", round(float(set_values.mean()) * 100, 2) if len(values) else 0.0
    if pd.api.types.is_numeric_dtype(series):
        return _numeric_validity(name, values)
    parsed = pd.to_numeric(values, errors="coerce")
    if len(values) and parsed.notna().mean() >= 0.95:
        return _numeric_validity(name, values)
    return "non-numeric; coverage only", None


def inventory_dataframe(df: pd.DataFrame) -> list[ColumnInventory]:
    """Measure coverage, cardinality, and conservative validity for every column."""
    total = len(df)
    report = []
    for name in df.columns:
        present = _present(df[name])
        coverage = 0.0 if not total else round(float(present.mean()) * 100, 2)
        distinct = int(df.loc[present, name].nunique(dropna=True))
        heuristic, valid_pct = _validity(name, df[name], present)
        report.append(ColumnInventory(name, family_for_column(name), coverage, distinct, heuristic, valid_pct))
    return report


def render_ascii(source: Path, rows: int, inventory: list[ColumnInventory]) -> str:
    """Render an ASCII-only report suitable for the Windows console."""
    lines = [f"TRACKING DEPTH INVENTORY: {source}", f"Rows: {rows}  Columns: {len(inventory)}"]
    for family in FAMILY_COLUMNS:
        items = [item for item in inventory if item.family == family]
        if not items:
            continue
        avg = sum(item.non_null_pct for item in items) / len(items)
        status = "NOT YET RELIABLE" if avg < 10 else "OBSERVED"
        lines.append(f"\n{family}: {avg:.2f}% mean coverage [{status}]")
        for item in items:
            validity = item.validity if item.validity_pct is None else f"{item.validity}: {item.validity_pct:.2f}%"
            lines.append(f"  {item.name}: coverage {item.non_null_pct:.2f}%, distinct {item.distinct_values}, {validity}")
    return "\n".join(lines)


def render_markdown(source: Path, rows: int, inventory: list[ColumnInventory]) -> str:
    """Render a transparent evidence document from the exact CSV measurements."""
    lines = ["# Tracking Depth Inventory", "", f"Source: `{source}`", "", f"Rows: {rows}", "", "This inventory describes observed CSV coverage only. A populated field is not proof of accurate identification, attribution, or event recognition.", ""]
    for family in FAMILY_COLUMNS:
        items = [item for item in inventory if item.family == family]
        if not items:
            continue
        avg = sum(item.non_null_pct for item in items) / len(items)
        status = "NOT YET RELIABLE" if avg < 10 else "OBSERVED"
        lines.extend([f"## {family} ({avg:.2f}% mean coverage; {status})", "", "| Column | Non-null | Distinct | Validity heuristic |", "| --- | ---: | ---: | --- |"])
        for item in items:
            validity = item.validity if item.validity_pct is None else f"{item.validity}: {item.validity_pct:.2f}%"
            lines.append(f"| {item.name} | {item.non_null_pct:.2f}% | {item.distinct_values} | {validity} |")
        lines.append("")
    return "\n".join(lines)


def newest_tracking_csv(root: Path) -> Path:
    """Find the newest standard tracking output beneath the supplied repository root."""
    candidates = list((root / "data" / "tracking").glob("*/tracking_data.csv"))
    if not candidates:
        raise FileNotFoundError("No data/tracking/*/tracking_data.csv found; pass a CSV path explicitly.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def write_inventory(csv_path: Path, sport: str, output_dir: Path) -> tuple[Path, Path, str]:
    """Create JSON and Markdown evidence artifacts and return their paths and console report."""
    df = pd.read_csv(csv_path)
    inventory = inventory_dataframe(df)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"tracking_depth_{sport}"
    json_path, markdown_path = output_dir / f"{stem}.json", output_dir / f"{stem}.md"
    payload = {"source": str(csv_path), "rows": len(df), "columns": [asdict(item) for item in inventory]}
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(csv_path, len(df), inventory), encoding="utf-8")
    return json_path, markdown_path, render_ascii(csv_path, len(df), inventory)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory observed tracking CSV capability coverage.")
    parser.add_argument("csv", nargs="?", type=Path, help="tracking CSV; defaults to newest standard output")
    parser.add_argument("--sport", default="nba", help="artifact suffix, default: nba")
    parser.add_argument("--output-dir", type=Path, default=Path("docs/evidence"))
    args = parser.parse_args()
    try:
        csv_path = args.csv or newest_tracking_csv(Path.cwd())
        json_path, markdown_path, report = write_inventory(csv_path, args.sport, args.output_dir)
    except (FileNotFoundError, pd.errors.EmptyDataError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2
    sys.stdout.write(report + f"\n\nWrote: {markdown_path}\nWrote: {json_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
