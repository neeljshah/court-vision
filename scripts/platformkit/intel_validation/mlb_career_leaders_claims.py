"""MLB career counting-stat leaderboard claims producer (family
mlb_career_counting_leaders, spec_mlb.md Family 2). Mirrors
platoon_split_claims.py's structure: one WIDE per-player snapshot parquet,
then N ranking claims via the validator's PLAIN row-wise formula path
(criteria.aggregate=None, criteria.formula = a bare column name already
precomputed in the snapshot) -- zero code sharing with claims_validator.py.

SOURCE: data/domains/mlb/player_gamelogs.parquet (321,012 rows, verified
2022-04-07 -> 2026-07-02). CAREER SPAN IS 2022+ ONLY -- every caveat below
says "since 2022", never "lifetime" or "career" unqualified (this corpus
starts in 2022, it is not a full MLB career record).

9 counting stats x 2 population variants (all-time, active-only) = 18
claims. "active" = last_season == the corpus's own max season (2026 at
build time) -- an ACTIVE-only view of the SAME snapshot via an extra
min_sample floor (is_active >= 1), not a second snapshot file: the
validator's _apply_min_sample_floors already does `df[col] >= floor` per
declared column, so `is_active` (stored 0/1) doubles as a floor column for
free (verified against claims_validator._apply_min_sample_floors).

min_sample floor: n_games >= 1 (a player must have appeared at least once --
already implied by the groupby, so this is a formality, not a real cut; a
counting-stat TOTAL has no small-sample noise problem the way a rate stat
does, so no larger floor is imposed here).

LEAK: pure descriptive career totals over a completed corpus window -- no
forecasting claim, no leak-risk window. NETWORK: zero.
DESCRIPTIVE ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.mlb_career_leaders_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_career_counting_leaders.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "mlb_career_counting_leaders_snapshot.parquet"

MIN_GAMES_FLOOR = 1

# (claim-stat name, source counting column) -- 9 dims per spec_mlb.md Family 2.
_STAT_DIMS: list[tuple[str, str]] = [
    ("career_hr", "homeRuns"), ("career_rbi", "rbi"), ("career_hits", "hits"),
    ("career_2b", "doubles"), ("career_3b", "triples"), ("career_runs", "runs"),
    ("career_sb", "stolenBases"), ("career_bb", "baseOnBalls"), ("career_k", "strikeOuts"),
]


def build_snapshot(gamelogs_path: Path = _GAMELOGS) -> tuple[Path, dict]:
    """One row per player_id: 9 career sum() totals, n_games, last_season,
    is_active. Written wide so every ranking claim below can use the PLAIN
    row-wise formula path (a bare column reference, already precomputed)."""
    cols = ["player_id", "player", "date", "game_pk"] + [c for _, c in _STAT_DIMS]
    df = pd.read_parquet(gamelogs_path, columns=cols)
    max_season = int(df["date"].dt.year.max())
    seasons_covered = sorted(int(y) for y in df["date"].dt.year.unique())

    agg: dict[str, Any] = {"player": ("player", "last"), "n_games": ("game_pk", "nunique"),
                            "last_season": ("date", lambda s: int(s.dt.year.max()))}
    for stat, col in _STAT_DIMS:
        agg[stat] = (col, "sum")
    wide = df.groupby("player_id").agg(**agg).reset_index()
    wide["is_active"] = (wide["last_season"] == max_season).astype(int)
    for stat, _ in _STAT_DIMS:
        wide[stat] = wide[stat].astype(int)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(wide, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, {"max_season": max_season, "seasons_covered": seasons_covered,
                            "n_players": len(wide), "n_active": int(wide["is_active"].sum())}


def _build_leaderboard_claim(stat: str, snapshot_path: Path, report: dict,
                              active_only: bool) -> dict[str, Any]:
    raw = pd.read_parquet(snapshot_path)
    n_considered = len(raw)
    min_sample: dict[str, Any] = {"n_games": MIN_GAMES_FLOOR}
    if active_only:
        min_sample["is_active"] = 1
    mask = pd.Series(True, index=raw.index)
    for col, floor in min_sample.items():
        mask &= raw[col] >= floor
    qualifiers = raw[mask].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(stat, ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "player_id": int(row.player_id), "player_name": str(row.player),
         "value": round(float(getattr(row, stat)), 4), "n": int(row.n_games),
         "last_season": int(row.last_season), "is_active": bool(row.is_active)}
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]

    seasons_str = "/".join(str(s) for s in report["seasons_covered"])
    metric_name = f"{stat}_active" if active_only else stat
    population_note = ("restricted to ACTIVE players (appeared in the corpus's most-recent "
                        f"season, {report['max_season']})" if active_only else "FULL population")
    rel_source = str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_career_counting_leaders_{metric_name}",
        "kind": "ranking",
        "question": f"Which MLB batters lead in {stat.replace('career_', 'career ')} "
                    f"since 2022 ({population_note})?",
        "criteria": {
            "metric": metric_name,
            "formula": stat,
            "window": f"since_{report['seasons_covered'][0]}" if report["seasons_covered"] else "unknown",
            "window_spec": None,
            "aggregate": None,
            "min_sample": min_sample,
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"career total = sum() of {stat} across every game row in this corpus, seasons "
            f"present at build time: {seasons_str} -- labelled 'since {report['seasons_covered'][0]}', "
            "NEVER 'lifetime'/'career' unqualified (this corpus does not go back to a player's "
            "MLB debut if that predates 2022)." if report["seasons_covered"] else "no seasons found",
            f"min_sample floor: n_games >= {MIN_GAMES_FLOOR}" +
            (" AND is_active (appeared in the corpus's most-recent season)" if active_only else "") +
            f" ({len(qualifiers)}/{n_considered} players qualify).",
            f"FULL POPULATION: all {len(qualifiers)} qualifying players are ranked here (no "
            "top-N truncation) -- below-floor players honestly counted in "
            "n_excluded_below_floor, never silently dropped.",
            "DESCRIPTIVE counting-stat leaderboard only -- no forecasting/market/$ edge claimed.",
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    snapshot_path, report = build_snapshot()
    claims = []
    for stat, _ in _STAT_DIMS:
        for active_only in (False, True):
            claims.append(_build_leaderboard_claim(stat, snapshot_path, report, active_only))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB career counting-stat leaderboard claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    if not _GAMELOGS.exists():
        print(f"NO_DATA: {_GAMELOGS} not found -- no claims written.")
        return 0
    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
