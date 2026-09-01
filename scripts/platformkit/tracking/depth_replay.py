"""Read-only before-and-after depth replay for canonical tracking CSVs."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from domains.basketball_nba.tracking.quality_probe import measure_dataframe
from scripts.platformkit.tracking_harness import evaluate


DEPTH_FIELDS = (
    "pct_frames_ge_8_players", "pct_frames_homography_valid",
    "ball_row_coverage", "jersey_number_fill_rate",
    "team_assignment_fill_rate", "median_track_length",
    "screen_candidates_per_minute",
)
HARNESS_FIELDS = ("coverage_pct", "jump_p95", "oob_pct")
PASS_NAMES = ("framing", "bridge", "merge")
Transform = Callable[[pd.DataFrame], pd.DataFrame]


def discover_games(root: str | Path = "data/tracking") -> list[Path]:
    """Return canonical tracking CSVs beneath ``root`` in stable order."""
    return sorted(Path(root).glob("*/tracking_data.csv"))


def _normalize(rows: pd.DataFrame) -> pd.DataFrame:
    aliases = {"x_position": "x", "y_position": "y", "player_id": "track_id"}
    return rows.rename(columns={old: new for old, new in aliases.items()
                                if old in rows and new not in rows}).copy()


def _values(report: Any, fields: Iterable[str]) -> dict[str, float]:
    raw = asdict(report) if is_dataclass(report) else dict(report)
    return {field: float(raw[field]) for field in fields
            if field in raw and raw[field] is not None}


def _report(rows: pd.DataFrame, sport: str) -> dict[str, float]:
    normalized = _normalize(rows)
    depth = _values(measure_dataframe(normalized, sport=sport), DEPTH_FIELDS)
    harness = _values(evaluate(normalized, sport), HARNESS_FIELDS)
    return {**depth, **harness}


def _common(before: Mapping[str, float], after: Mapping[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    """Keep only fields observed in both reports; never manufacture zeroes."""
    fields = sorted(set(before).intersection(after))
    return ({field: before[field] for field in fields},
            {field: after[field] for field in fields})


def _csv_path(game: str | Path) -> Path:
    path = Path(game)
    return path if path.name == "tracking_data.csv" else path / "tracking_data.csv"


def replay_game(game: str | Path, sport: str, *, framing: bool = False,
                bridge: bool = False, merge: bool = False,
                transforms: Mapping[str, Transform] | None = None) -> dict[str, object]:
    """Replay selected offline passes for one CSV without changing its source."""
    path = _csv_path(game)
    source = pd.read_csv(path)
    before = _report(source, sport)
    after = source.copy()
    enabled = {"framing": framing, "bridge": bridge, "merge": merge}
    transforms = transforms or {}
    applied: list[str] = []
    for name in PASS_NAMES:
        if enabled[name] and name in transforms:
            candidate = transforms[name](after.copy())
            if not isinstance(candidate, pd.DataFrame):
                raise TypeError("%s transform must return a DataFrame" % name)
            after = candidate
            applied.append(name)
    after_values = _report(after, sport)
    before_values, after_values = _common(before, after_values)
    return {
        "game_id": path.parent.name,
        "source": str(path),
        "passes": applied,
        "before": before_values,
        "after": after_values,
    }


def replay(games: Iterable[str | Path] | None, sport: str, *, framing: bool = False,
           bridge: bool = False, merge: bool = False,
           transforms: Mapping[str, Transform] | None = None,
           output_dir: str | Path = ".planning/tracking") -> Path:
    """Write a dated corpus replay report outside the source tracking tree."""
    selected = list(games) if games is not None else discover_games()
    rows = [replay_game(game, sport, framing=framing, bridge=bridge, merge=merge,
                        transforms=transforms) for game in selected]
    destination = Path(output_dir) / ("depth_replay_%s.json" % date.today().isoformat())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(rows, indent=2, ensure_ascii=True), encoding="ascii")
    return destination


def sha256(path: str | Path) -> str:
    """Return the source-file digest used to verify read-only replay runs."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay tracking-depth reports without source writes.")
    parser.add_argument("games", nargs="*", type=Path)
    parser.add_argument("--sport", required=True)
    parser.add_argument("--framing", action="store_true")
    parser.add_argument("--bridge", action="store_true")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path(".planning/tracking"))
    args = parser.parse_args()
    output = replay(args.games or None, args.sport, framing=args.framing, bridge=args.bridge,
                    merge=args.merge, output_dir=args.output_dir)
    print(str(output).encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
