"""Reproduce G82's percentile sweep and measure retained real tracking tables."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
import pandas as pd


OVERSIZED_LOW_FT = 10.0
OVERSIZED_HIGH_FT = 29.0


def _steps(df: pd.DataFrame, track: str, x: str, y: str) -> pd.DataFrame:
    """Return the harness-equivalent consecutive-row player differences."""
    ordered = df.sort_values([track, "frame"]).copy()
    grouped = ordered.groupby(track)
    ordered["frame_gap"] = grouped["frame"].diff()
    ordered["distance_ft"] = np.hypot(grouped[x].diff(), grouped[y].diff())
    return ordered.dropna(subset=["distance_ft"]).copy()


def measure_table(name: str, sport: str, path: Path, *, track: str, x: str,
                  y: str, player_filter: bool) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    """Measure a retained table without modifying its source rows."""
    raw = pd.read_csv(path)
    players = raw.loc[raw["cls"].eq("player")].copy() if player_filter else raw.copy()
    steps = _steps(players, track, x, y)
    if steps.empty:
        raise ValueError(f"{path} has no player steps")
    stride = int(steps["frame_gap"].value_counts().idxmax())
    p95 = float(steps["distance_ft"].quantile(0.95))
    oversized = steps.loc[steps["distance_ft"].between(OVERSIZED_LOW_FT, OVERSIZED_HIGH_FT,
                                                         inclusive="both")].copy()
    missed = oversized.loc[oversized["distance_ft"] > p95].copy()
    rate = steps["distance_ft"] / (steps["frame_gap"] / stride)
    result: dict[str, object] = {
        "table": name,
        "sport": sport,
        "source": path.as_posix(),
        "rows": len(raw),
        "player_rows": len(players),
        "frames": raw["frame"].nunique(),
        "steps": len(steps),
        "sampling_stride_frames_modal": stride,
        "current_jump_p95_ft": p95,
        "jump_max_ft": float(steps["distance_ft"].max()),
        "oversized_10_29_count": len(oversized),
        "oversized_above_p95_count": len(missed),
        "oversized_above_p95_fraction": len(missed) / len(oversized) if len(oversized) else None,
        "row_diffs_gap_gt_stride_count": int((steps["frame_gap"] > stride).sum()),
        "row_diffs_gap_gt_stride_fraction": float((steps["frame_gap"] > stride).mean()),
        "max_frame_gap": int(steps["frame_gap"].max()),
        "gap_normalized_p95_ft_per_stride": float(rate.quantile(0.95)),
        "gap_normalized_max_ft_per_stride": float(rate.max()),
    }
    missed.insert(0, "table", name)
    return result, missed, players


def reproduce_sweep() -> list[dict[str, object]]:
    """Independently reproduce the audit's 40-ft teleport prevalence sweep."""
    output: list[dict[str, object]] = []
    for every in (50, 30, 20, 15, 12, 10, 8):
        distances = np.full(600, 0.6)
        distances[np.arange(every - 1, 600, every)] = 40.0
        p95 = float(pd.Series(distances).quantile(0.95))
        output.append({
            "teleport_every_steps": every,
            "teleport_count": int((distances == 40).sum()),
            "teleport_prevalence_pct": float((distances == 40).mean() * 100),
            "jump_p95_ft": p95,
            "verdict_at_8ft": "FAIL" if p95 > 8 else "PASS",
        })
    return output


def _coordinate_pair(players: pd.DataFrame, *, track: str, x: str, y: str,
                     previous_frame: int, current_frame: int, out_path: Path,
                     title: str) -> None:
    """Render the two source-table frames as court-coordinate maps for review."""
    canvas = np.full((460, 1120, 3), 250, dtype=np.uint8)
    for offset, frame, label in ((30, previous_frame, "previous"), (580, current_frame, "current")):
        cv2.rectangle(canvas, (offset, 55), (offset + 500, 355), (45, 110, 45), 2)
        cv2.line(canvas, (offset + 250, 55), (offset + 250, 355), (45, 110, 45), 1)
        cv2.putText(canvas, f"{label} frame {frame}", (offset, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
        points = players.loc[players["frame"].eq(frame)]
        for _, row in points.iterrows():
            px = offset + int(float(row[x]) / 94.0 * 500)
            py = 355 - int(float(row[y]) / 50.0 * 300)
            cv2.circle(canvas, (px, py), 7, (20, 20, 220), -1)
            cv2.putText(canvas, str(int(row[track])), (px + 8, py - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.putText(canvas, title, (30, 415), cv2.FONT_HERSHEY_SIMPLEX, 0.54, (0, 0, 0), 1)
    if not cv2.imwrite(str(out_path), canvas):
        raise RuntimeError(f"failed to write {out_path}")


def write_evidence(output_dir: Path) -> None:
    """Create the G82 durable numerical artifacts and coordinate-pair renders."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = (
        ("tennis_09_retained", "tennis", Path("data/tracking/G83_tennis_09/tracking_data.csv"),
         "track_id", "x", "y", True),
        ("basketball_0022501165", "basketball", Path("data/tracking/0022501165/tracking_data.csv"),
         "player_id", "ft_x", "ft_y", False),
    )
    results: list[dict[str, object]] = []
    all_missed: list[pd.DataFrame] = []
    rendered_players: pd.DataFrame | None = None
    rendered_missed: pd.DataFrame | None = None
    for case in cases:
        result, missed, players = measure_table(*case[:3], track=case[3], x=case[4], y=case[5],
                                                player_filter=case[6])
        results.append(result)
        all_missed.append(missed)
        if case[0] == "basketball_0022501165":
            rendered_players, rendered_missed = players, missed
    pd.DataFrame(results).to_csv(output_dir / "per_table_statistics.csv", index=False)
    pd.concat(all_missed, ignore_index=True).to_csv(output_dir / "oversized_steps_above_p95.csv", index=False)
    pd.DataFrame(reproduce_sweep()).to_csv(output_dir / "reproduced_sweep.csv", index=False)

    if rendered_players is None or rendered_missed is None or len(rendered_missed) < 6:
        raise RuntimeError("need six real missed basketball steps for the mandatory visual check")
    selection = rendered_missed.sort_values(["frame", "player_id"]).iloc[
        np.linspace(0, len(rendered_missed) - 1, 6, dtype=int)
    ]
    selection.to_csv(output_dir / "eye_check_selection.csv", index=False)
    for index, (_, row) in enumerate(selection.iterrows(), start=1):
        previous = int(row["frame"] - row["frame_gap"])
        current = int(row["frame"])
        text = (f"track {int(row['player_id'])}: {row['distance_ft']:.2f} ft over "
                f"{int(row['frame_gap'])} frames; coordinate render, source video unavailable")
        _coordinate_pair(rendered_players, track="player_id", x="ft_x", y="ft_y",
                         previous_frame=previous, current_frame=current,
                         out_path=output_dir / f"render_{index:02d}_frames_{previous}_{current}.png",
                         title=text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    write_evidence(args.output_dir)


if __name__ == "__main__":
    main()
