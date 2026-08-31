"""Sport-blind per-game tracking quality harness.

The contract every sport adapter must satisfy (MULTISPORT_TRACKING_PROGRAM.md):
feed it a normalized tracking table, get a QualityReport with pass/fail vs
that sport's thresholds. No sport-specific logic lives here.

Normalized schema (one row per detection, court/field coordinates):
    frame:int, track_id:int, cls:str ('player'|'ball'|...), x:float, y:float

Run: python scripts/platformkit/tracking_harness.py <tracking.csv> <sport>
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict

import pandas as pd

# Per-sport thresholds. Field bounds in the sport's court/field units.
# ponytail: flat dict, tune per sport as real games flow through.
SPORTS: dict = {
    # basketball thresholds calibrated on first real 720p60 game 2026-08-31
    # (broadcast crops mean ~7 tracked players typical; det_per_frame avg 8.05)
    "basketball": {"bounds": (0, 94, 0, 50), "min_players": 6,
                   "ball_valid_min": 0.30, "coverage_min": 0.60,
                   "oob_max": 0.05, "jump_p95_max": 6.0},
    "tennis":     {"bounds": (0, 78, 0, 36), "min_players": 2,
                   "ball_valid_min": 0.20, "coverage_min": 0.90,
                   "oob_max": 0.08, "jump_p95_max": 8.0},
    "soccer":     {"bounds": (0, 105, 0, 68), "min_players": 14,
                   "ball_valid_min": 0.20, "coverage_min": 0.85,
                   "oob_max": 0.05, "jump_p95_max": 8.0},
    "baseball":   {"bounds": (-30, 30, 0, 60), "min_players": 2,  # pitch-view
                   "ball_valid_min": 0.10, "coverage_min": 0.70,
                   "oob_max": 0.10, "jump_p95_max": 10.0},
}


@dataclass
class QualityReport:
    sport: str
    n_frames: int
    coverage_pct: float          # frames with >= min_players player tracks
    det_per_frame: float
    median_track_len: float      # continuity proxy (frames per track_id)
    ball_valid_pct: float        # frames with an in-bounds ball point
    jump_p95: float              # p95 per-track frame-to-frame move (units)
    oob_pct: float               # points outside field bounds
    passed: bool
    failures: list

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def evaluate(df: pd.DataFrame, sport: str) -> QualityReport:
    cfg = SPORTS[sport]
    x0, x1, y0, y1 = cfg["bounds"]
    n_frames = int(df["frame"].nunique())
    if n_frames == 0:
        return QualityReport(sport, 0, 0, 0, 0, 0, 0, 0, False, ["empty"])

    players = df[df["cls"] == "player"]
    per_frame = players.groupby("frame")["track_id"].nunique()
    coverage = float((per_frame >= cfg["min_players"]).sum() / n_frames)
    det_per_frame = float(len(df) / n_frames)
    track_len = float(players.groupby("track_id")["frame"].count().median()
                      ) if len(players) else 0.0

    # bounds apply to players; adapters emit a ball row IFF they have a
    # valid ball fix, so ball validity = frames with any ball row.
    oob = (~players["x"].between(x0, x1)) | (~players["y"].between(y0, y1))
    oob_pct = float(oob.mean()) if len(players) else 1.0
    ball_valid = float(df[df["cls"] == "ball"]["frame"].nunique() / n_frames)

    d = players.sort_values(["track_id", "frame"]).groupby("track_id")
    jump = ((d["x"].diff() ** 2 + d["y"].diff() ** 2) ** 0.5).dropna()
    jump_p95 = float(jump.quantile(0.95)) if len(jump) else 0.0

    failures = []
    if coverage < cfg["coverage_min"]:
        failures.append(f"coverage {coverage:.2f} < {cfg['coverage_min']}")
    if ball_valid < cfg["ball_valid_min"]:
        failures.append(f"ball_valid {ball_valid:.2f} < {cfg['ball_valid_min']}")
    if oob_pct > cfg["oob_max"]:
        failures.append(f"oob {oob_pct:.2f} > {cfg['oob_max']}")
    if jump_p95 > cfg["jump_p95_max"]:
        failures.append(f"jump_p95 {jump_p95:.1f} > {cfg['jump_p95_max']}")

    return QualityReport(sport, n_frames, round(coverage, 4),
                         round(det_per_frame, 2), track_len,
                         round(ball_valid, 4), round(jump_p95, 2),
                         round(oob_pct, 4), not failures, failures)


if __name__ == "__main__":
    path, sport = sys.argv[1], sys.argv[2]
    rep = evaluate(pd.read_csv(path), sport)
    sys.stdout.write(rep.to_json() + "\n")
    sys.exit(0 if rep.passed else 1)
