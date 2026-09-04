"""As-of rates coverage guard for the S247 NBA simulator evaluation."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from src.sim import fast_sim as _fast_sim


MIN_QUALIFYING_GAMES = 30


@dataclass(frozen=True)
class RatesLimitResult:
    """Immutable as-of coverage result, with no simulator pricing side effect."""

    qualifying_cluster_ids: tuple[str, ...]
    excluded_cluster_ids: tuple[str, ...]
    player_snapshot_date: date
    team_snapshot_date: date

    @property
    def verdict(self) -> str:
        return "READY_TO_SCORE" if len(self.qualifying_cluster_ids) >= MIN_QUALIFYING_GAMES else "CLOSED_AT_LIMIT"


def snapshot_date(path: Path) -> date:
    """Return the UTC filesystem date of an immutable rates snapshot."""

    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date()


def measure_rates_limit(
    archive_path: Path,
    player_rates_path: Path,
    team_rates_path: Path,
) -> RatesLimitResult:
    """Measure game-level rates eligibility before any simulator invocation."""

    player_date = snapshot_date(player_rates_path)
    team_date = snapshot_date(team_rates_path)
    games: dict[str, date] = {}
    with archive_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cluster_id = row["cluster_id"]
            game_date = date.fromisoformat(row["date"])
            previous = games.setdefault(cluster_id, game_date)
            if previous != game_date:
                raise ValueError(f"cluster {cluster_id} has multiple game dates")

    qualifying = tuple(
        cluster_id
        for cluster_id, game_date in sorted(games.items())
        if player_date < game_date and team_date < game_date
    )
    excluded = tuple(cluster_id for cluster_id in sorted(games) if cluster_id not in set(qualifying))
    return RatesLimitResult(qualifying, excluded, player_date, team_date)
