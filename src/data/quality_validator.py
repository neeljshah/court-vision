"""
quality_validator.py — Validate a cleaned game directory meets quality thresholds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

SENTINEL_THRESHOLD = 199.5


class QualityValidator:
    """Validate a cleaned game directory meets minimum quality thresholds."""

    THRESHOLDS: Dict[str, float] = {
        "min_tracking_rows":      5_000,
        "max_sentinel_pct":       5.0,
        "min_possession_count":   30,
        "min_median_poss_sec":    8.0,
        "max_median_poss_sec":    120.0,
        "min_shot_count":         5,
        "max_shot_count":         400,
        "min_player_name_pct":    50.0,
        "min_team_abbrev_pct":    80.0,
        "min_homography_pct":     10.0,
    }

    def __init__(self, game_dir: str) -> None:
        self.game_dir = Path(game_dir)
        self._game_id = self.game_dir.name

    def validate(self) -> dict:
        """Returns {metric: {value, threshold, passed}, overall_passed: bool}"""
        results: dict = {}

        # --- tracking_data.csv ---
        td_path = self.game_dir / "tracking_data.csv"
        tracking_rows = 0
        sentinel_pct = 0.0
        player_name_pct = 0.0
        team_abbrev_pct = 0.0
        homography_pct = 0.0

        if td_path.exists():
            df = pd.read_csv(td_path, encoding="utf-8", low_memory=False)
            tracking_rows = len(df)

            # Sentinel check across key spatial columns
            sentinel_cols = [c for c in ("nearest_opponent", "handler_isolation",
                                         "distance_to_ball") if c in df.columns]
            if sentinel_cols and tracking_rows:
                sentinel_count = sum(
                    (df[c] >= SENTINEL_THRESHOLD).sum()
                    for c in sentinel_cols
                )
                total_non_null = sum(df[c].notna().sum() for c in sentinel_cols)
                sentinel_pct = sentinel_count / max(total_non_null, 1) * 100

            if "player_name" in df.columns and tracking_rows:
                player_name_pct = df["player_name"].notna().mean() * 100
            if "team_abbrev" in df.columns and tracking_rows:
                team_abbrev_pct = df["team_abbrev"].notna().mean() * 100
            if "homography_valid" in df.columns and tracking_rows:
                homography_pct = df["homography_valid"].mean() * 100

        results["tracking_rows"] = {
            "value": tracking_rows,
            "threshold": self.THRESHOLDS["min_tracking_rows"],
            "passed": tracking_rows >= self.THRESHOLDS["min_tracking_rows"],
        }
        results["sentinel_pct"] = {
            "value": round(sentinel_pct, 1),
            "threshold": self.THRESHOLDS["max_sentinel_pct"],
            "passed": sentinel_pct <= self.THRESHOLDS["max_sentinel_pct"],
        }
        results["player_name_pct"] = {
            "value": round(player_name_pct, 1),
            "threshold": self.THRESHOLDS["min_player_name_pct"],
            "passed": player_name_pct >= self.THRESHOLDS["min_player_name_pct"],
        }
        results["team_abbrev_pct"] = {
            "value": round(team_abbrev_pct, 1),
            "threshold": self.THRESHOLDS["min_team_abbrev_pct"],
            "passed": team_abbrev_pct >= self.THRESHOLDS["min_team_abbrev_pct"],
        }
        results["homography_pct"] = {
            "value": round(homography_pct, 1),
            "threshold": self.THRESHOLDS["min_homography_pct"],
            "passed": homography_pct >= self.THRESHOLDS["min_homography_pct"],
        }

        # --- possessions.csv ---
        pv_path = self.game_dir / "possessions.csv"
        poss_count = 0
        median_poss_sec = 0.0

        if pv_path.exists():
            df_p = pd.read_csv(pv_path, encoding="utf-8", low_memory=False)
            poss_count = len(df_p)
            if "duration_sec" in df_p.columns and poss_count:
                median_poss_sec = df_p["duration_sec"].median()

        results["possession_count"] = {
            "value": poss_count,
            "threshold": self.THRESHOLDS["min_possession_count"],
            "passed": poss_count >= self.THRESHOLDS["min_possession_count"],
        }
        results["median_poss_sec"] = {
            "value": round(median_poss_sec, 1),
            "threshold": f"{self.THRESHOLDS['min_median_poss_sec']}–{self.THRESHOLDS['max_median_poss_sec']}",
            "passed": (self.THRESHOLDS["min_median_poss_sec"]
                       <= median_poss_sec
                       <= self.THRESHOLDS["max_median_poss_sec"]),
        }

        # --- shot_log.csv ---
        sl_path = self.game_dir / "shot_log.csv"
        shot_count = 0
        if sl_path.exists():
            shot_count = max(0, sum(1 for _ in open(sl_path, encoding="utf-8")) - 1)

        results["shot_count"] = {
            "value": shot_count,
            "threshold": f"{self.THRESHOLDS['min_shot_count']}–{self.THRESHOLDS['max_shot_count']}",
            "passed": (self.THRESHOLDS["min_shot_count"]
                       <= shot_count
                       <= self.THRESHOLDS["max_shot_count"]),
        }

        overall = all(v["passed"] for v in results.values())
        results["overall_passed"] = overall
        return results

    def grade(self) -> str:
        """Returns A/B/C/F grade based on how many thresholds pass."""
        r = self.validate()
        checks = [v["passed"] for k, v in r.items()
                  if isinstance(v, dict) and "passed" in v]
        if not checks:
            return "F"
        pct = sum(checks) / len(checks)
        if pct >= 0.90:
            return "A"
        if pct >= 0.75:
            return "B"
        if pct >= 0.50:
            return "C"
        return "F"
