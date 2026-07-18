"""Claim 2 of the nba_teammate_context family: gravity-teammate scoring
context -- does sharing the floor with a top-quartile-gravity teammate lift
a player's own team scoring rate?

For every player A: the team's own pts_for per 48 (from stints) while A
shares the floor with >=1 teammate whose gravity_proxy (already computed by
domains/basketball_nba/lineups/gravity_spacing.py) is in the season's TOP
QUARTILE, vs. while A shares the floor with NONE.

PREREGISTERED FLOOR + QUARTILE DEFINITION (declared here BEFORE scoring):
    top-quartile threshold = the 75th percentile of gravity_proxy across the
    FULL, as-delivered gravity_proxy_<season>.parquet population (leaguewide,
    not per-team) -- a deterministic function of that on-disk file.
    with_seconds    >= 12000.0  (200 minutes)
    without_seconds >= 12000.0  (200 minutes)

SOURCES: data/cache/team_system/lineups/stints_<season>.parquet (CLEAN
n_on_court==5 stints only, same precedent as on_off.py) +
data/cache/team_system/lineups/gravity_proxy_<season>.parquet (already-
computed gravity_proxy column, read as-is).

WHY A SNAPSHOT PARQUET: same rationale as nba_teammate_context_pairs.py --
the quartile-membership + on-floor-teammate-lookup logic cannot be expressed
in the claims contract's whitelisted aggregate grammar, so this producer
pre-aggregates to a snapshot parquet with plain pts_per48_with/without
columns and goes through the validator's PLAIN formula path.

NETWORK: zero.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_BOX_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"

SEASON_CORPUS = {"2023_24": "1230-game", "2024_25": "1230-game", "2025_26": "196-game"}
GRAVITY_QUARTILE = 0.75
WITH_MIN_SECONDS = 12000.0
WITHOUT_MIN_SECONDS = 12000.0

ROSTER_CONFOUND_CAVEAT = (
    "ROSTER CONFOUND: this gravity-teammate scoring-context delta is NOT a causal estimate -- "
    "which teammates share the floor correlates with coach trust, opponent strength, and "
    "garbage-time usage, none of which are controlled for here. DESCRIPTIVE_ONLY until an "
    "earned predictive-validity receipt says otherwise."
)
COACH_DEPLOYMENT_CAVEAT = (
    "COACH-DEPLOYMENT CONFOUND: whether a top-gravity teammate shares the floor with a given "
    "player is a lineup DECISION (starter/bench pairing, matchup plan), not randomly assigned."
)
GARBAGE_TIME_CAVEAT = (
    "GARBAGE-TIME CONTAMINATION: UNFILTERED. The stint table's `quality` field is a "
    "reconstruction-repair flag, not a garbage-time indicator -- no blowout-margin or "
    "clock-differential filter is applied to either condition's minutes here."
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _name_lookup(box_df: pd.DataFrame) -> dict[int, str]:
    names = box_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]
    return {int(k): str(v) for k, v in names.items()}


def gravity_threshold(gravity_df: pd.DataFrame) -> float:
    """Leaguewide top-quartile threshold: the 75th percentile of
    gravity_proxy over the FULL as-delivered population of the season's
    gravity_proxy parquet (no additional pre-filter)."""
    return float(gravity_df["gravity_proxy"].quantile(GRAVITY_QUARTILE))


def compute_gravity_context(stints_df: pd.DataFrame, gravity_df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """FULL (unfiltered) per-(player_id, team_id) population: pts_per48_with
    (team pts_for/48 while sharing the floor with >=1 top-quartile-gravity
    teammate) vs. pts_per48_without (sharing with none). Denominators of
    zero -> NaN (never a crash)."""
    threshold = gravity_threshold(gravity_df)
    top_set = set(
        zip(
            gravity_df.loc[gravity_df["gravity_proxy"] >= threshold, "team_id"].astype(int),
            gravity_df.loc[gravity_df["gravity_proxy"] >= threshold, "player_id"].astype(int),
        )
    )

    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    clean["players"] = clean["lineup_key"].str.split(",")

    acc: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for (_gid, tid), grp in clean.groupby(["game_id", "team_id"]):
        for players, elapsed_s, pts_for in zip(grp["players"], grp["elapsed_s"], grp["pts_for"]):
            on = {int(p) for p in players}
            for a in on:
                teammates = on - {a}
                has_top = any((tid, t) in top_set for t in teammates)
                key = (int(tid), a)
                if has_top:
                    acc[key]["with_s"] += elapsed_s
                    acc[key]["with_pf"] += pts_for
                else:
                    acc[key]["without_s"] += elapsed_s
                    acc[key]["without_pf"] += pts_for

    rows = []
    for (tid, pid), v in acc.items():
        with_s, without_s = v["with_s"], v["without_s"]
        pts_with = v["with_pf"] * 48.0 * 60.0 / with_s if with_s > 0 else float("nan")
        pts_without = v["without_pf"] * 48.0 * 60.0 / without_s if without_s > 0 else float("nan")
        rows.append({
            "player_id": pid, "team_id": tid,
            "with_seconds": round(with_s, 2), "without_seconds": round(without_s, 2),
            "pts_per48_with": pts_with, "pts_per48_without": pts_without,
        })
    return pd.DataFrame(rows), threshold


def build_gravity_claim(season: str = "2025_26") -> dict[str, Any]:
    stints_df = pd.read_parquet(_LINEUPS_DIR / f"stints_{season}.parquet")
    gravity_df = pd.read_parquet(_LINEUPS_DIR / f"gravity_proxy_{season}.parquet")
    table, threshold = compute_gravity_context(stints_df, gravity_df)
    n_considered = len(table)

    names = _name_lookup(pd.read_parquet(_BOX_SRC))
    table["player_name"] = table["player_id"].map(names).fillna("Unknown")

    snap_dir = _OUT_DIR / "nba_teammate_context_gravity_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"gravity_context_{season}.parquet"
    table.to_parquet(snap_path, index=False)

    mask = (
        (table["with_seconds"] >= WITH_MIN_SECONDS)
        & (table["without_seconds"] >= WITHOUT_MIN_SECONDS)
        & table["pts_per48_with"].notna() & table["pts_per48_without"].notna()
    )
    n_excluded = n_considered - int(mask.sum())
    qualifiers = table[mask].copy()
    qualifiers["gravity_teammate_delta"] = qualifiers["pts_per48_with"] - qualifiers["pts_per48_without"]
    qualifiers = qualifiers.sort_values("gravity_teammate_delta", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i, "player_id": int(row.player_id), "team_id": int(row.team_id),
            "player_name": str(row.player_name),
            "value": round(float(row.gravity_teammate_delta), 4),
            "n": round(float(min(row.with_seconds, row.without_seconds)) / 60.0, 2),
        })

    corpus = SEASON_CORPUS.get(season, season)
    if not ranking:
        print(f"SKIP nba_teammate_context_gravity_{season}: 0 of {n_considered} players "
              "clear the min_sample floor -- claim not emitted")

    return {
        "claim_id": f"nba_teammate_context_gravity_{season}",
        "kind": "ranking", "label": "DESCRIPTIVE_ONLY",
        "question": (
            f"Whose own team scores at the highest rate when he shares the floor with a "
            f"top-quartile-gravity teammate, vs. with none ({corpus} {season} slice)?"
        ),
        "criteria": {
            "metric": "gravity_teammate_delta", "formula": "pts_per48_with - pts_per48_without",
            "window": f"season_{season}_nba_lineup_corpus",
            "min_sample": {"with_seconds": WITH_MIN_SECONDS, "without_seconds": WITHOUT_MIN_SECONDS},
            "direction": "desc", "value_precision": 4,
            "entity_key": ["player_id", "team_id"],
        },
        "ranking": ranking, "source_files": [_rel(snap_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            ROSTER_CONFOUND_CAVEAT, COACH_DEPLOYMENT_CAVEAT, GARBAGE_TIME_CAVEAT,
            f"top-quartile gravity_proxy threshold this season = {threshold:.4f} (75th "
            "percentile, leaguewide, computed over the full as-delivered gravity_proxy "
            "parquet -- prereg'd before scoring, not tuned after seeing results).",
            "gravity_teammate_delta = pts_per48_with (team pts_for/48 while sharing the "
            "floor with >=1 top-quartile-gravity teammate) minus pts_per48_without (sharing "
            "with none); a player's OWN gravity_proxy is irrelevant to his own row -- only his "
            "teammates' matter.",
            "min_sample floor with_seconds>=12000 (200 min) AND without_seconds>=12000 (200 "
            "min) -- below-floor players are honestly counted in n_excluded_below_floor, never "
            "dropped from n_considered.",
            "FULL POPULATION above floor, no top-N cap. DESCRIPTIVE_ONLY -- NOT a gate, "
            "no market/$ edge claimed.",
        ],
    }
