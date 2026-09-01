"""Measure observable depth in NBA and WNBA production tracking CSVs.

The ratios are fractions in the same convention as ``tracking_harness``.
This is a coverage probe, not an accuracy or betting-edge claim.  The B
thresholds inherit the basketball harness floors: ``coverage_min`` is used
for the stricter >=8-player frame metric, and ``ball_valid_min`` for ball
coverage.  The harness itself checks >=6 players; this probe deliberately
measures >=8.  A uses stricter operational floors for a healthy deep feed.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from domains.basketball_nba.tracking.screens import detect_screens
from scripts.platformkit.tracking_harness import SPORTS


_BASKETBALL = SPORTS["basketball"]
DEPTH_GRADE_THRESHOLDS = {
    "A": {"players_ge_8": 0.90, "homography": 0.90, "ball": 0.90,
           "jersey": 0.80, "team": 0.95},
    "B": {"players_ge_8": _BASKETBALL["coverage_min"],
           "homography": _BASKETBALL["coverage_min"],
           "ball": _BASKETBALL["ball_valid_min"],
           "jersey": 0.50, "team": 0.80},
}


@dataclass(frozen=True)
class DepthReport:
    source: str
    sport: str
    rows: int
    frames: int
    pct_frames_ge_8_players: float
    pct_frames_homography_valid: float
    ball_row_coverage: float
    jersey_number_fill_rate: float
    team_assignment_fill_rate: float
    median_track_length: float
    screen_candidate_count: int
    screen_candidates_per_minute: float
    depth_grade: str

    @property
    def grade(self) -> str:
        """Short alias for callers that refer to the depth grade as ``grade``."""
        return self.depth_grade

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly report including the grade thresholds."""
        result = asdict(self)
        result["grade_thresholds"] = DEPTH_GRADE_THRESHOLDS
        return result


def _present(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip().str.lower()
    return values.notna() & text.ne("") & ~text.isin({"nan", "none", "null", "unknown", "-1", "-1.0"})


def _truthy(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip().str.lower()
    return text.isin({"1", "1.0", "true", "t", "yes", "y"})


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Mirror the production normalizer's three tracking aliases."""
    aliases = {"player_id": "track_id", "ft_x": "x", "ft_y": "y"}
    return df.rename(columns={key: value for key, value in aliases.items()
                              if key in df and value not in df}).copy()


def _player_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    identifier = "track_id" if "track_id" in df else "player_id"
    if identifier not in df or "frame" not in df:
        raise ValueError("tracking CSV requires frame and player_id columns")
    rows = df.loc[_present(df[identifier])].copy()
    if "cls" in rows:
        rows = rows.loc[~rows["cls"].astype("string").str.lower().eq("ball")]
    return rows, identifier


def _frame_ratio(df: pd.DataFrame, mask: pd.Series, frames: int) -> float:
    if not frames:
        return 0.0
    return float(df.loc[mask, "frame"].nunique() / frames)


def _ball_mask(df: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    if "cls" in df:
        mask |= df["cls"].astype("string").str.lower().eq("ball")
    for x_name, y_name in (("ball_x2d", "ball_y2d"), ("ball_x", "ball_y")):
        if x_name in df:
            present = _present(df[x_name])
            if y_name in df:
                present &= _present(df[y_name])
            mask |= present
            break
    return mask


def _screen_count(df: pd.DataFrame, fps: float) -> int:
    screen_input = df.copy()
    if "ball_x2d" in screen_input and "ball_x" not in screen_input:
        screen_input["ball_x"] = screen_input["ball_x2d"]
    if "ball_y2d" in screen_input and "ball_y" not in screen_input:
        screen_input["ball_y"] = screen_input["ball_y2d"]
    try:
        return int(len(detect_screens(screen_input, fps=fps)))
    except (KeyError, TypeError, ValueError):
        return 0


def measure_dataframe(df: pd.DataFrame, sport: str = "nba", fps: float = 30.0,
                      source: str = "<dataframe>") -> DepthReport:
    """Measure one production tracking frame table."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    normalized = _normalize(df)
    players, identifier = _player_rows(normalized)
    frames = int(normalized["frame"].nunique())
    eight = players.groupby("frame")[identifier].nunique().ge(8)
    pct_eight = float(eight.sum() / frames) if frames else 0.0
    homography = (_frame_ratio(normalized, _truthy(normalized["homography_valid"]), frames)
                  if "homography_valid" in normalized else 0.0)
    ball = _frame_ratio(normalized, _ball_mask(normalized), frames)
    jersey = (float(_present(players["jersey_number"]).mean())
              if "jersey_number" in players and len(players) else 0.0)
    team_col = next((name for name in ("team", "team_id", "side") if name in players), None)
    team = float(_present(players[team_col]).mean()) if team_col and len(players) else 0.0
    lengths = players.groupby(identifier)["frame"].nunique()
    median_length = float(lengths.median()) if len(lengths) else 0.0
    screens = _screen_count(normalized, fps)
    numeric_frames = pd.to_numeric(normalized["frame"], errors="coerce").dropna()
    span = float(numeric_frames.max() - numeric_frames.min() + 1) if len(numeric_frames) else 0.0
    minutes = span / fps / 60.0
    screens_per_minute = float(screens / minutes) if minutes else 0.0
    grade = _grade(pct_eight, homography, ball, jersey, team)
    return DepthReport(str(source), sport.lower(), len(df), frames, round(pct_eight, 4),
                       round(homography, 4), round(ball, 4), round(jersey, 4),
                       round(team, 4), round(median_length, 2), screens,
                       round(screens_per_minute, 2), grade)


def _grade(players: float, homography: float, ball: float, jersey: float,
           team: float) -> str:
    values = (players, homography, ball, jersey, team)
    for grade in ("A", "B"):
        if all(value >= threshold for value, threshold in zip(
                values, DEPTH_GRADE_THRESHOLDS[grade].values())):
            return grade
    return "C"


def quality_probe(path: str | Path, sport: str = "nba", fps: float = 30.0) -> DepthReport:
    """Read a production CSV and return its tracking depth report."""
    source = Path(path)
    return measure_dataframe(pd.read_csv(source), sport=sport, fps=fps, source=str(source))


def _sport_for_path(path: Path) -> str:
    return "wnba" if "wnba" in str(path).lower() else "nba"


def _ascii(value: object) -> str:
    return str(value).encode("ascii", "replace").decode("ascii")


def compare_games(paths: Sequence[str | Path] | Mapping[str, str | Path]) -> list[DepthReport]:
    """Print an ASCII side-by-side table and return one report per CSV."""
    pairs = list(paths.items()) if isinstance(paths, Mapping) else [(_sport_for_path(Path(path)), path) for path in paths]
    reports = [quality_probe(path, sport=sport) for sport, path in pairs]
    headers = ("SPORT", "GAME", "DEPTH", ">=8", "HOMO", "BALL", "JERSEY", "TEAM", "MED_TRACK", "SCREENS/MIN")
    rows = [[sport.upper(), Path(report.source).name, report.depth_grade,
             "{:.1f}%".format(report.pct_frames_ge_8_players * 100),
             "{:.1f}%".format(report.pct_frames_homography_valid * 100),
             "{:.1f}%".format(report.ball_row_coverage * 100),
             "{:.1f}%".format(report.jersey_number_fill_rate * 100),
             "{:.1f}%".format(report.team_assignment_fill_rate * 100),
             "{:.1f}".format(report.median_track_length),
             "{:.2f}".format(report.screen_candidates_per_minute)]
            for (sport, _), report in zip(pairs, reports)]
    widths = [max(len(header), *(len(_ascii(row[index])) for row in rows))
              for index, header in enumerate(headers)]
    line = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    print(line)
    print("| " + " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)) + " |")
    print(line)
    for row in rows:
        print("| " + " | ".join(_ascii(value).ljust(widths[index]) for index, value in enumerate(row)) + " |")
    print(line)
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe NBA/WNBA tracking depth.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--sport", default="nba")
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()
    if len(args.paths) > 1:
        compare_games(args.paths)
    else:
        print(json.dumps(quality_probe(args.paths[0], args.sport, args.fps).to_dict(),
                         indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
