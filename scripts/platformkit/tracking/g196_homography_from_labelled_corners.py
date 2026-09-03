"""Measure labelled-paint homographies and render court overlays for G196.

This standalone harness reads committed labels/JPEGs only.  It deliberately does
not import or invoke the production tracking pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROLE_ORDER = (
    "paint_near_baseline_left_corner",
    "paint_near_baseline_right_corner",
    "paint_near_free_throw_left_corner",
    "paint_near_free_throw_right_corner",
)
COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT = 50.0
PAINT_DEPTH_FT = 19.0
LANE_WIDTH_FT = {"ncaa_basketball": 12.0, "wnba": 16.0}
EYE_CHECKS = {
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973": (
        "INDETERMINATE",
        "Tight hoop-end crop and lower-third hide independent long-court paint.",
    ),
    "ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925": (
        "YES",
        "The projected three-point curve follows the painted arc beyond the fitted key.",
    ),
    "wnba__wnba_01_1080p__s01__f001600": (
        "YES",
        "The independently visible three-point curve lands on the painted court.",
    ),
    "wnba__wnba_04__s06__f012223": (
        "INDETERMINATE",
        "Tight hoop-end framing and occlusion hide independent sideline, arc, and centre markings.",
    ),
    "wnba__wnba_07__s08__f016801": (
        "YES",
        "The independently visible three-point curve follows its painted court marking.",
    ),
}


def court_points_for_sport(sport: str) -> np.ndarray:
    """Return model points for the ordered near paint-corner roles, in feet."""
    lane_width = LANE_WIDTH_FT[sport]
    left = (COURT_WIDTH_FT - lane_width) / 2.0
    right = (COURT_WIDTH_FT + lane_width) / 2.0
    return np.float32(((left, 0.0), (right, 0.0), (left, PAINT_DEPTH_FT), (right, PAINT_DEPTH_FT)))


def solve_homography(image_points: np.ndarray, court_points: np.ndarray) -> np.ndarray:
    """Solve the exact four-correspondence image-to-court transform."""
    if image_points.shape != (4, 2) or court_points.shape != (4, 2):
        raise ValueError("G196 requires exactly four 2D image and court points")
    return cv2.getPerspectiveTransform(image_points.astype(np.float32), court_points.astype(np.float32))


def round_trip_residual(image_points: np.ndarray, homography: np.ndarray) -> dict[str, float]:
    """Return image-to-court-to-image residuals in pixels."""
    court = cv2.perspectiveTransform(image_points.reshape(1, -1, 2), homography)[0]
    inverse = np.linalg.inv(homography)
    reconstructed = cv2.perspectiveTransform(court.reshape(1, -1, 2), inverse)[0]
    distances = np.linalg.norm(reconstructed - image_points, axis=1)
    return {
        "rms_px": float(np.sqrt(np.mean(np.square(distances)))),
        "max_px": float(np.max(distances)),
    }


def _arc(center: tuple[float, float], radius: float, start: float, end: float) -> np.ndarray:
    angles = np.linspace(start, end, 121)
    return np.column_stack((center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)))


def full_court_lines(sport: str) -> list[np.ndarray]:
    """Build visible full-court line strings in the same feet coordinate contract."""
    lane_width = LANE_WIDTH_FT[sport]
    lane_left = (COURT_WIDTH_FT - lane_width) / 2.0
    lane_right = (COURT_WIDTH_FT + lane_width) / 2.0
    lines = [
        np.float32(((0, 0), (COURT_WIDTH_FT, 0), (COURT_WIDTH_FT, COURT_LENGTH_FT), (0, COURT_LENGTH_FT), (0, 0))),
        np.float32(((0, COURT_LENGTH_FT / 2), (COURT_WIDTH_FT, COURT_LENGTH_FT / 2))),
        np.float32(((lane_left, 0), (lane_right, 0), (lane_right, PAINT_DEPTH_FT), (lane_left, PAINT_DEPTH_FT), (lane_left, 0))),
        np.float32(((lane_left, COURT_LENGTH_FT), (lane_right, COURT_LENGTH_FT), (lane_right, COURT_LENGTH_FT - PAINT_DEPTH_FT), (lane_left, COURT_LENGTH_FT - PAINT_DEPTH_FT), (lane_left, COURT_LENGTH_FT))),
    ]
    center = (COURT_WIDTH_FT / 2.0, COURT_LENGTH_FT / 2.0)
    lines.append(_arc(center, 6.0, 0.0, 2.0 * np.pi).astype(np.float32))
    for baseline_y, direction in ((0.0, 1.0), (COURT_LENGTH_FT, -1.0)):
        basket_y = baseline_y + direction * 4.0
        free_throw_y = baseline_y + direction * PAINT_DEPTH_FT
        lines.append(np.float32(((lane_left, free_throw_y), (lane_right, free_throw_y))))
        lines.append(_arc((COURT_WIDTH_FT / 2.0, free_throw_y), lane_width / 2.0, 0.0, np.pi).astype(np.float32))
        radius = 22.0 + 1.75 / 12.0
        arc = _arc((COURT_WIDTH_FT / 2.0, basket_y), radius, 0.0, np.pi)
        if direction < 0:
            arc[:, 1] = 2.0 * basket_y - arc[:, 1]
        lines.append(arc.astype(np.float32))
        lines.append(np.float32(((arc[0, 0], baseline_y), arc[0])))
        lines.append(np.float32(((arc[-1, 0], baseline_y), arc[-1])))
    return lines


def render_overlay(image: np.ndarray, homography: np.ndarray, sport: str, image_points: np.ndarray) -> np.ndarray:
    """Draw inverse-projected court lines and labelled-corner markers on an image."""
    rendered = image.copy()
    inverse = np.linalg.inv(homography)
    for court_line in full_court_lines(sport):
        projected = cv2.perspectiveTransform(court_line.reshape(1, -1, 2), inverse)[0]
        if not np.isfinite(projected).all() or np.abs(projected).max() > 1_000_000:
            continue
        cv2.polylines(rendered, [np.round(projected).astype(np.int32)], False, (0, 255, 255), 2, cv2.LINE_AA)
    for point in image_points:
        cv2.circle(rendered, tuple(np.round(point).astype(int)), 7, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.circle(rendered, tuple(np.round(point).astype(int)), 10, (255, 255, 255), 1, cv2.LINE_AA)
    return rendered


def _records_by_audit_id(csv_path: Path) -> dict[str, list[dict[str, str]]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["status"] != "target":
            raise ValueError(f"{row['audit_id']}: non-target label present")
        grouped[row["audit_id"]].append(row)
    return dict(grouped)


def measure(csv_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    """Solve all labelled frames and write renders plus JSON-safe per-frame records."""
    records: list[dict[str, Any]] = []
    renders_dir = output_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    for audit_id, rows in sorted(_records_by_audit_id(csv_path).items()):
        if len(rows) != 4:
            raise ValueError(f"{audit_id}: expected exactly four label rows")
        by_role = {row["role"]: row for row in rows}
        if set(by_role) != set(ROLE_ORDER):
            raise ValueError(f"{audit_id}: required corner roles are not exactly present")
        ordered = [by_role[role] for role in ROLE_ORDER]
        sport = "wnba" if audit_id.startswith("wnba__") else "ncaa_basketball"
        image_points = np.float32([(float(row["x_px"]), float(row["y_px"])) for row in ordered])
        court_points = court_points_for_sport(sport)
        source_path = (csv_path.parent / ordered[0]["source_decode"]).resolve()
        image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(source_path)
        height, width = image.shape[:2]
        declared_width, declared_height = int(ordered[0]["image_width"]), int(ordered[0]["image_height"])
        if (width, height) != (declared_width, declared_height):
            raise ValueError(f"{audit_id}: JPEG dimensions disagree with CSV")
        homography = solve_homography(image_points, court_points)
        if not np.isfinite(homography).all() or abs(float(np.linalg.det(homography))) < 1e-12:
            raise ValueError(f"{audit_id}: unsolved or singular homography")
        residual = round_trip_residual(image_points, homography)
        render_path = renders_dir / f"{audit_id}.jpg"
        if not cv2.imwrite(str(render_path), render_overlay(image, homography, sport, image_points)):
            raise OSError(f"could not write {render_path}")
        records.append(
            {
                "audit_id": audit_id,
                "sport": sport,
                "source_jpeg_absolute_path": str(source_path),
                "native_resolution_px": [width, height],
                "image_points_px_role_order": list(ROLE_ORDER),
                "image_points_px": image_points.astype(float).tolist(),
                "court_points_ft_role_order": list(ROLE_ORDER),
                "court_points_ft": court_points.astype(float).tolist(),
                "homography_image_to_court": homography.astype(float).tolist(),
                "round_trip_residual_px": residual,
                "render_path": str(render_path.resolve()),
            }
        )
    return records


def write_evidence(records: list[dict[str, Any]], evidence_path: Path) -> None:
    """Write the G196 evidence memo using measured records and reviewed renders."""
    frame_rows = []
    for record in records:
        residual = record["round_trip_residual_px"]
        frame_rows.append(
            f"| {record['audit_id']} | {record['sport']} | "
            f"`{record['source_jpeg_absolute_path']}` | "
            f"{record['native_resolution_px'][0]}x{record['native_resolution_px'][1]} | yes | "
            f"{residual['rms_px']:.3e} | {residual['max_px']:.3e} | "
            f"[render](g196_homography_from_labelled_corners_artifact/renders/{record['audit_id']}.jpg) |"
        )
    eye_rows = []
    for index in (0, 4, 8, 12, 16):
        record = records[index]
        verdict, observation = EYE_CHECKS[record["audit_id"]]
        eye_rows.append(
            f"| {index} | {record['audit_id']} | {verdict} | {observation} | "
            f"[render](g196_homography_from_labelled_corners_artifact/renders/{record['audit_id']}.jpg) |"
        )
    lines = [
        "# G196: Homography from Hand-Labelled Paint Corners",
        "",
        "## Result",
        "",
        "**Court geometry is recoverable from hand-labelled paint corners in this set.** Three of the five evenly spaced render checks show independently visible, non-fitted three-point curves landing on the court; the other two are tight-crop indeterminates, not clean mismatches. For frames where four true paint corners can be obtained, the observed ceiling is detection/point quality, not a universally degenerate court model. This is recoverability evidence only, not proof that labels are production-accurate.",
        "",
        "Run **locally** in `C:\\Users\\neelj\\nba-track-a6`, not on the pod. It read 17 committed JPEGs and solved four-point transforms: no video decode, model inference, `run_clip.py`, pipeline route, daemon, or production-code change.",
        "",
        "## Contract and method",
        "",
        "The 68-row committed [G140 target CSV](g140_corner_targets/corner_pixel_targets.csv) supplies 17 audit IDs and the four required roles per ID, all `status=target`. Every `source_decode` resolves to a committed JPEG and native dimensions equal the CSV. The [per-frame records](g196_homography_from_labelled_corners_artifact/per_frame_records.json) store the role-ordered four image points, four court points, 3x3 image-to-court matrix, and residual for every frame.",
        "",
        "`cv2.getPerspectiveTransform` maps the four ordered image points `[near baseline left, near baseline right, near free-throw left, near free-throw right]` to the near paint rectangle. RANSAC is intentionally not used: four points are the exact projective minimum, leaving no redundant correspondence or alternative sample to score/reject. The inverse projects boundaries, sidelines, half-court, centre circle, paint/free-throw geometry, and three-point arcs back onto each source JPEG; yellow is the model overlay and red marks are source points.",
        "",
        "### Court coordinate contract (feet)",
        "",
        "Coordinates are `[x, y]`: `x=0..50` runs left sideline to right sideline and `y=0..94` runs from the labelled near baseline toward the other baseline. NCAA uses a 12-ft lane; WNBA uses a 16-ft lane, so their four model points differ:",
        "",
        "| League | Near baseline left | Near baseline right | Near free-throw left | Near free-throw right |",
        "|---|---:|---:|---:|---:|",
        "| NCAA basketball | `[19, 0]` | `[31, 0]` | `[19, 19]` | `[31, 19]` |",
        "| WNBA | `[17, 0]` | `[33, 0]` | `[17, 19]` | `[33, 19]` |",
        "",
        "NCAA Rule 1 Section 6 Art. 1 states a **12-ft** free-throw lane measured to its outside boundaries; its official court diagram gives the 94-by-50-ft court and 19-ft paint depth. See the [NCAA rules book](https://ncaaorg.s3.amazonaws.com/championships/sports/basketball/rules/women/PRWBB_RulesBook.pdf) and [court diagram](https://ncaaorg.s3.amazonaws.com/championships/sports/basketball/rules/common/PRXBB_CourtDiagram.pdf). The [official WNBA Rule 1/court diagram](https://cdn.wnba.com/sites/4/2026/05/2026-WNBA-Official-Rule-Book.pdf) uses the same 94-by-50-ft court and 19-ft depth but a **16-ft** outside lane width. The rendered model also uses the published 22 ft 1 3/4 in three-point arc.",
        "",
        "## Per-frame results (n=17, exhaustive construct)",
        "",
        "`Solved` means a finite nonsingular four-point matrix was constructed. The residual is image point -> court -> image, in pixels. It is a **conditioning/sanity check only**: with exactly four points, the fit is exact by construction, so a small residual proves neither role correctness nor projection accuracy.",
        "",
        "| Audit ID | Sport | Source JPEG (absolute path) | Native px | Solved | RMS residual px | Max residual px | Overlay |",
        "|---|---|---|---:|---|---:|---:|---|",
        *frame_rows,
        "",
        "## Five evenly spaced human eye checks",
        "",
        "The deterministic even indices are 0, 4, 8, 12, and 16 of stable sorted audit IDs. `YES` requires agreement with a visible painted marking beyond the four fitted correspondences. `INDETERMINATE` is neither a pass nor a failure: the needed independent marking is out of crop or occluded.",
        "",
        "| Index | Audit ID | Verdict | Human render observation | Render |",
        "|---:|---|---|---|---|",
        *eye_rows,
        "",
        "## NOT VERIFIED / honest limitation",
        "",
        "- Four points are the **exact minimum**: no redundancy, independent residual, or outlier rejection exists. G140's p90 label repeatability is **11.39 px**, and that label noise propagates directly into each matrix.",
        "- This does not validate the Hough solver, a learned detector, a production threshold, pipeline integration, production accuracy, or robustness to overlays/occlusions.",
        "- The two indeterminate eye-check frames do not establish a failure rate; they lack an independently visible marking with which to test extrapolation.",
        "- The 17 small numerical round trips are not an accuracy metric and do not make a production-readiness claim.",
        "",
    ]
    evidence_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    records = measure(args.csv.resolve(), args.output_dir.resolve())
    records_path = args.output_dir / "per_frame_records.json"
    records_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    if args.evidence:
        write_evidence(records, args.evidence.resolve())
    print(f"Solved {len(records)} of {len(records)} labelled frames")
    print(f"Records: {records_path}")


if __name__ == "__main__":
    main()
