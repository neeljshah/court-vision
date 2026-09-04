"""Build strictly-prior NBA player and team rate snapshots from dated sidecars."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd


PLAYER_COLUMNS = ["player_id", "game_date", "ft_rate_q50", "ft_rate_spread", "ft_n_prior"]
TEAM_COLUMNS = [
    "team_id", "game_date", "team_possession_duration_z", "team_transition_share_z",
    "team_tempo_z", "team_avg_spacing_z", "team_paint_dwell_z", "team_spacing_z",
    "team_tempo_spacing_composite_z",
]
PLAYER_RATES = ["ft_rate_q50", "ft_rate_spread", "ft_n_prior"]
TEAM_RATES = TEAM_COLUMNS[2:]


def read_archive_clusters(path: Path, chunk_size: int = 50_000) -> pd.DataFrame:
    """Read the fixed archive cluster/date construct in bounded CSV chunks."""
    seen: dict[tuple[str, str], pd.Timestamp] = {}
    for chunk in pd.read_csv(path, usecols=["game", "cluster_id", "date"], chunksize=chunk_size):
        chunk["game_date"] = pd.to_datetime(chunk.pop("date")).dt.normalize()
        for row in chunk.drop_duplicates(["game", "cluster_id", "game_date"]).itertuples(index=False):
            key = (str(row.game), str(row.cluster_id))
            prior = seen.setdefault(key, row.game_date)
            if prior != row.game_date:
                raise ValueError(f"cluster {key} has inconsistent game dates")
    return pd.DataFrame(
        [(game, cluster, date) for (game, cluster), date in seen.items()],
        columns=["game", "cluster_id", "game_date"],
    ).sort_values(["game_date", "game", "cluster_id"], ignore_index=True)


def build_entity_snapshots(
    rows: pd.DataFrame,
    entity_column: str,
    rate_columns: Iterable[str],
    max_snapshot_date: pd.Timestamp,
) -> pd.DataFrame:
    """Aggregate every entity using only source rows strictly before each snapshot date."""
    rate_columns = list(rate_columns)
    frame = rows[[entity_column, "game_date", *rate_columns]].copy()
    frame["game_date"] = pd.to_datetime(frame["game_date"]).dt.normalize()
    frame = frame.dropna(subset=[entity_column, "game_date", *rate_columns])
    snapshots: list[pd.DataFrame] = []
    for snapshot_date in sorted(frame.loc[frame["game_date"] <= max_snapshot_date, "game_date"].unique()):
        history = frame.loc[frame["game_date"] < snapshot_date]
        if history.empty:
            continue
        aggregate = history.groupby(entity_column, as_index=False)[rate_columns].mean()
        aggregate = aggregate.rename(columns={entity_column: "entity_id"})
        aggregate["as_of_date"] = snapshot_date
        snapshots.append(aggregate)
    if not snapshots:
        return pd.DataFrame(columns=["entity_id", "as_of_date", *rate_columns])
    result = pd.concat(snapshots, ignore_index=True)
    if result.duplicated(["entity_id", "as_of_date"]).any():
        raise ValueError("snapshot key must be unique")
    return result[["entity_id", "as_of_date", *rate_columns]]


def qualify_clusters(
    clusters: pd.DataFrame,
    player_snapshots: pd.DataFrame,
    team_snapshots: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the latest strictly-prior player and team snapshot date to every cluster."""
    base = clusters.copy().sort_values("game_date").reset_index(drop=True)
    for label, snapshots in (("player", player_snapshots), ("team", team_snapshots)):
        dates = snapshots[["as_of_date"]].drop_duplicates().sort_values("as_of_date")
        dates = dates.rename(columns={"as_of_date": f"{label}_snapshot_date"})
        base = pd.merge_asof(
            base,
            dates,
            left_on="game_date",
            right_on=f"{label}_snapshot_date",
            direction="backward",
            allow_exact_matches=False,
        )
    base["qualifies"] = base[["player_snapshot_date", "team_snapshot_date"]].notna().all(axis=1)
    qualifying = base.loc[base["qualifies"]]
    if not (qualifying["player_snapshot_date"] < qualifying["game_date"]).all():
        raise AssertionError("player snapshot date is not strictly prior")
    if not (qualifying["team_snapshot_date"] < qualifying["game_date"]).all():
        raise AssertionError("team snapshot date is not strictly prior")
    return base.sort_values(["game_date", "game", "cluster_id"], ignore_index=True)


def produce(
    archive_path: Path,
    player_source_path: Path,
    team_source_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Produce player/team snapshot tables and exhaustive cluster qualification."""
    clusters = read_archive_clusters(archive_path)
    cutoff = clusters["game_date"].max()

    player_rows = pd.read_parquet(player_source_path, columns=PLAYER_COLUMNS)
    player_rows = player_rows.loc[player_rows["ft_n_prior"] > 0]
    player_snapshots = build_entity_snapshots(player_rows, "player_id", PLAYER_RATES, cutoff)
    del player_rows

    team_rows = pd.read_parquet(team_source_path, columns=TEAM_COLUMNS)
    team_snapshots = build_entity_snapshots(team_rows, "team_id", TEAM_RATES, cutoff)
    del team_rows

    qualification = qualify_clusters(clusters, player_snapshots, team_snapshots)
    return player_snapshots, team_snapshots, qualification


def write_artifacts(
    output_dir: Path,
    player_snapshots: pd.DataFrame,
    team_snapshots: pd.DataFrame,
    qualification: pd.DataFrame,
    input_paths: dict[str, Path],
) -> dict[str, object]:
    """Write reconstructible snapshot artifacts outside data/ and return their summary."""
    output_dir.mkdir(parents=True, exist_ok=True)
    player_path = output_dir / "player_rate_snapshots.parquet"
    team_path = output_dir / "team_rate_snapshots.parquet"
    qualification_path = output_dir / "cluster_qualification.csv"
    player_snapshots.to_parquet(player_path, index=False)
    team_snapshots.to_parquet(team_path, index=False)
    qualification.to_csv(qualification_path, index=False, date_format="%Y-%m-%d")
    qualifying = int(qualification["qualifies"].sum())
    total = int(len(qualification))
    summary = {
        "denominator_clusters": total,
        "qualifying_clusters": qualifying,
        "qualifying_fraction": f"{qualifying}/{total}",
        "player_snapshot_rows": int(len(player_snapshots)),
        "team_snapshot_rows": int(len(team_snapshots)),
        "inputs": {name: {"path": str(path), "bytes": path.stat().st_size} for name, path in input_paths.items()},
        "artifacts": {
            "player_snapshots": {"path": str(player_path), "bytes": player_path.stat().st_size},
            "team_snapshots": {"path": str(team_path), "bytes": team_path.stat().st_size},
            "qualification": {"path": str(qualification_path), "bytes": qualification_path.stat().st_size},
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="ascii")
    return summary


def main() -> None:
    """Run the S255 producer with explicit input and documentation paths."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--player-source", type=Path, required=True)
    parser.add_argument("--team-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    player, team, qualification = produce(args.archive, args.player_source, args.team_source)
    if len(qualification) != 661:
        raise ValueError(f"S255 requires 661 clusters, found {len(qualification)}")
    summary = write_artifacts(
        args.output_dir,
        player,
        team,
        qualification,
        {"archive": args.archive, "player_source": args.player_source, "team_source": args.team_source},
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
