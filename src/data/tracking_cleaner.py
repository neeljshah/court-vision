"""
tracking_cleaner.py — Post-process CV pipeline outputs to enforce data quality.

Cleans tracking_data.csv, possessions.csv, shot_log.csv, and features.csv
in a game directory. All operations are idempotent (running twice is safe).
Originals backed up as *.csv.bak before first overwrite.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

log = logging.getLogger(__name__)

SENTINEL_THRESHOLD = 199.5
COURT_X_MAX = 94.0
COURT_Y_MAX = 50.0
SPACING_CLIP = 5000.0
OVERFLOW_GUARD = 1e6
POSS_MIN_SEC = 2.0
POSS_MERGE_GAP_SEC = 5.0
SHOT_DEDUP_SEC = 8.0
DEFENDER_DIST_FT_MAX = 50.0


class TrackingCleaner:
    """Post-process tracking pipeline outputs to enforce data quality."""

    def __init__(self, game_dir: str) -> None:
        self.game_dir = Path(game_dir)
        self._game_id = self.game_dir.name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clean_all(self) -> dict:
        """Run all cleaning steps. Returns quality report dict."""
        report: dict = {"game_id": self._game_id}

        td_path = self.game_dir / "tracking_data.csv"
        if td_path.exists():
            df = self.clean_tracking()
            report["tracking_rows"] = len(df)
        else:
            report["tracking_rows"] = 0

        pv_path = self.game_dir / "possessions.csv"
        if pv_path.exists():
            df_p = self.clean_possessions()
            report["possession_count"] = len(df_p)
            if "duration_sec" in df_p.columns and len(df_p):
                report["median_poss_sec"] = round(df_p["duration_sec"].median(), 1)
            else:
                report["median_poss_sec"] = 0.0
        else:
            report["possession_count"] = 0
            report["median_poss_sec"] = 0.0

        sl_path = self.game_dir / "shot_log.csv"
        if sl_path.exists():
            df_s = self.clean_shots()
            report["shot_count"] = len(df_s)
        else:
            report["shot_count"] = 0

        fc_path = self.game_dir / "features.csv"
        if fc_path.exists():
            df_f = self.clean_features()
            report["feature_rows"] = len(df_f)
        else:
            report["feature_rows"] = 0

        return report

    def clean_tracking(self) -> pd.DataFrame:
        """Clean tracking_data.csv in-place."""
        path = self.game_dir / "tracking_data.csv"
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
        original_len = len(df)

        df = self._clean_sentinel_cols(df, ["nearest_opponent", "handler_isolation",
                                            "distance_to_ball", "nearest_teammate"])
        df = self._clip_coords(df)
        df = self._clip_spacing(df)

        if "team_abbrev" not in df.columns or df["team_abbrev"].isna().mean() > 0.5:
            df = self._backfill_team_abbrev(df)
        if "player_name" not in df.columns or df["player_name"].isna().mean() > 0.5:
            df = self._backfill_player_names(df)
        if "homography_valid" not in df.columns:
            df["homography_valid"] = 0
        # Ensure string columns don't flip to float64 when all-NaN
        for col in ("team_abbrev", "player_name"):
            if col in df.columns:
                df[col] = df[col].astype(object)

        self._backup_and_write(path, df)
        log.info("tracking %s: %d rows cleaned", self._game_id, original_len)
        return df

    def clean_possessions(self) -> pd.DataFrame:
        """Clean possessions.csv — merge fragments, filter short."""
        path = self.game_dir / "possessions.csv"
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)

        # Ensure duration_sec column
        if "duration_sec" not in df.columns and "start_frame" in df.columns and "end_frame" in df.columns:
            fps = 30.0
            df["duration_sec"] = (df["end_frame"] - df["start_frame"]) / fps

        if "duration_sec" not in df.columns:
            return df  # can't clean without duration

        before = len(df)
        before_median = df["duration_sec"].median() if len(df) else 0.0

        # Drop NaN team
        df = df.dropna(subset=["team"]) if "team" in df.columns else df

        # Merge consecutive same-team possessions with small gap
        df = df.sort_values("start_frame").reset_index(drop=True) if "start_frame" in df.columns else df
        df = self._merge_possession_gaps(df)

        # Filter < 2s after merge
        df = df[df["duration_sec"] >= POSS_MIN_SEC].reset_index(drop=True)

        after_median = df["duration_sec"].median() if len(df) else 0.0
        log.info("possessions %s: %d→%d  median %.1fs→%.1fs",
                 self._game_id, before, len(df), before_median, after_median)

        self._backup_and_write(path, df)
        return df

    def clean_shots(self) -> pd.DataFrame:
        """Clean shot_log.csv — dedupe, validate, blank bad defender_distance."""
        path = self.game_dir / "shot_log.csv"
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)

        before = len(df)

        # defender_distance sentinel + pixel-space guard
        if "defender_distance" in df.columns:
            df.loc[df["defender_distance"] >= SENTINEL_THRESHOLD, "defender_distance"] = pd.NA
            df.loc[df["defender_distance"] > DEFENDER_DIST_FT_MAX, "defender_distance"] = pd.NA

        # shot_distance bounds
        if "shot_distance" in df.columns:
            df.loc[(df["shot_distance"] < 0) | (df["shot_distance"] > COURT_X_MAX), "shot_distance"] = pd.NA

        # Dedup by timestamp proximity
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp").reset_index(drop=True)
            keep = [True] * len(df)
            last_ts = -9999.0
            for i, ts in enumerate(df["timestamp"]):
                try:
                    ts_f = float(ts)
                except (TypeError, ValueError):
                    continue
                if ts_f - last_ts < SHOT_DEDUP_SEC:
                    keep[i] = False
                else:
                    last_ts = ts_f
            df = df[keep].reset_index(drop=True)

        log.info("shots %s: %d→%d", self._game_id, before, len(df))
        self._backup_and_write(path, df)
        return df

    def clean_features(self) -> pd.DataFrame:
        """Clean features.csv — superset of tracking rules + overflow guard."""
        path = self.game_dir / "features.csv"
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)

        df = self._clean_sentinel_cols(df, ["nearest_opponent", "handler_isolation",
                                            "distance_to_ball", "defender_distance"])
        df = self._clip_coords(df)
        df = self._clip_spacing(df)

        # Shot quality proxy clip
        if "shot_quality_proxy" in df.columns:
            df["shot_quality_proxy"] = df["shot_quality_proxy"].clip(0.0, 1.0)

        # Overflow guard on rolling/computed cols
        num_cols = df.select_dtypes(include="number").columns
        for col in num_cols:
            mask = df[col].abs() > OVERFLOW_GUARD
            if mask.any():
                df.loc[mask, col] = pd.NA

        self._backup_and_write(path, df)
        return df

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clean_sentinel_cols(self, df: pd.DataFrame, cols: list) -> pd.DataFrame:
        for col in cols:
            if col in df.columns:
                df.loc[df[col] >= SENTINEL_THRESHOLD, col] = pd.NA
        return df

    def _clip_coords(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in ("x_norm", "y_norm"):
            if col in df.columns:
                df[col] = df[col].clip(0.0, 1.0)
        if "ft_x" in df.columns:
            df["ft_x"] = df["ft_x"].clip(0.0, COURT_X_MAX)
        if "ft_y" in df.columns:
            df["ft_y"] = df["ft_y"].clip(0.0, COURT_Y_MAX)
        return df

    def _clip_spacing(self, df: pd.DataFrame) -> pd.DataFrame:
        if "spacing_advantage" in df.columns:
            df["spacing_advantage"] = df["spacing_advantage"].clip(-SPACING_CLIP, SPACING_CLIP)
        if "team_spacing" in df.columns:
            df.loc[df["team_spacing"] < 0, "team_spacing"] = pd.NA
        return df

    def _merge_possession_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Merge consecutive same-team possessions separated by < POSS_MERGE_GAP_SEC."""
        if "start_frame" not in df.columns or "end_frame" not in df.columns or "team" not in df.columns:
            return df
        fps = 30.0
        gap_frames = POSS_MERGE_GAP_SEC * fps
        merged_rows = []
        for _, row in df.iterrows():
            if merged_rows and merged_rows[-1]["team"] == row["team"]:
                prev = merged_rows[-1]
                if row["start_frame"] - prev["end_frame"] <= gap_frames:
                    # Merge
                    prev["end_frame"] = row["end_frame"]
                    prev["duration_sec"] = (prev["end_frame"] - prev["start_frame"]) / fps
                    if "duration_frames" in prev:
                        prev["duration_frames"] = prev["end_frame"] - prev["start_frame"]
                    continue
            merged_rows.append(dict(row))
        return pd.DataFrame(merged_rows)

    def _backfill_team_abbrev(self, df: pd.DataFrame) -> pd.DataFrame:
        tc_path = self.game_dir / "team_colors.json"
        if "team_abbrev" not in df.columns:
            df["team_abbrev"] = pd.NA
        if not tc_path.exists():
            # No team_colors.json — try manifest-based fallback directly
            self._apply_manifest_team_fallback(df)
            return df
        try:
            with open(tc_path, encoding="utf-8") as f:
                tc = json.load(f)
            # Support both formats:
            #   flat:   {"green": "ORL", "white": "UTA"}    (pipeline/backfill output)
            #   nested: {"green": {"label": ..., "abbreviation": "ORL"}}  (legacy)
            label_to_abbr = {}
            for k, v in tc.items():
                if isinstance(v, dict):
                    label_to_abbr[v.get("label", k)] = v.get("abbreviation", k)
                elif isinstance(v, str) and v:
                    label_to_abbr[k] = v
            if "team" in df.columns:
                if "team_abbrev" not in df.columns:
                    df["team_abbrev"] = pd.NA
                for label, abbr in label_to_abbr.items():
                    mask = df["team"] == label
                    df.loc[mask & df["team_abbrev"].isna(), "team_abbrev"] = abbr

                # Fallback: if no labels matched (e.g. team_colors keys are abbreviations
                # not color labels), use manifest home/away with NBA convention.
                if df["team_abbrev"].isna().all():
                    self._apply_manifest_team_fallback(df)
        except Exception as e:
            log.warning("team_abbrev backfill failed: %s", e)
        return df

    def _apply_manifest_team_fallback(self, df: pd.DataFrame) -> None:
        """Use manifest home/away + NBA convention (home=white) to fill team_abbrev."""
        manifest_path = self.game_dir / "manifest.json"
        if not manifest_path.exists() or "team" not in df.columns:
            return
        try:
            with open(manifest_path, encoding="utf-8") as mf:
                manifest = json.load(mf)
            home = manifest.get("home", "")
            away = manifest.get("away", "")
            if not home or not away:
                return
            df["team_abbrev"] = df["team_abbrev"].astype(object)
            color_vals = df["team"].dropna().unique()
            white_labels = [c for c in color_vals if "white" in str(c).lower()]
            other_labels = [c for c in color_vals if "white" not in str(c).lower()]
            for wl in white_labels:
                df.loc[df["team"] == wl, "team_abbrev"] = home
            for ol in other_labels:
                df.loc[df["team"] == ol, "team_abbrev"] = away
            log.info("team_abbrev: manifest fallback (home=%s=white, away=%s)", home, away)
        except Exception as me:
            log.warning("manifest fallback for team_abbrev failed: %s", me)

    def _backfill_player_names(self, df: pd.DataFrame) -> pd.DataFrame:
        jnm_path = self.game_dir / "jersey_name_map.json"
        if not jnm_path.exists():
            if "player_name" not in df.columns:
                df["player_name"] = pd.NA
            return df
        try:
            with open(jnm_path, encoding="utf-8") as f:
                jnm = json.load(f)
            if "player_name" not in df.columns:
                df["player_name"] = pd.NA
            if "jersey_number" in df.columns:
                num_to_name = {str(k): v for k, v in jnm.items()}
                for num, name in num_to_name.items():
                    mask = df["jersey_number"].astype(str) == num
                    df.loc[mask & df["player_name"].isna(), "player_name"] = name
        except Exception as e:
            log.warning("player_name backfill failed: %s", e)
        return df

    def _backup_and_write(self, path: Path, df: pd.DataFrame) -> None:
        bak = path.with_suffix(".csv.bak")
        if not bak.exists():
            shutil.copy2(path, bak)
        df.to_csv(path, index=False, encoding="utf-8")
