"""Claim 1 of the nba_teammate_context family: pair with/without net-rating
lift -- "who lifts whom" via directed same-team duos.

For every ordered pair (A, B) who ever shared a team roster in a game
(A != B): the team's own net rating per 48 while BOTH are on the floor,
minus the team's net rating per 48 while A is on and B is off. A positive
lift means B's presence measurably raises the team's net rating while A is
already on the floor -- directional, (A,B) != (B,A), same convention as
domains/basketball_nba/interactions/pairwise_onoff.py's efg_delta (this
module reuses its exact roster-loop shape, but on pts_for/pts_against from
stints alone -- no PBP shot events needed for a net-rating lift).

PREREGISTERED FLOORS (declared here BEFORE any scoring runs):
    both_on_seconds     >= 18000.0   (300 minutes)
    a_without_b_seconds >= 12000.0   (200 minutes)

SOURCE: data/cache/team_system/lineups/stints_<season>.parquet, CLEAN stints
only (n_on_court==5, same precedent as on_off.py -- the ~0.6%% of drifted
stints are dropped rather than silently corrupting a split).

WHY A SNAPSHOT PARQUET (not criteria.aggregate): the claims contract's
aggregate grammar groups by ONE bare column and cannot parse lineup_key
membership or split by a second player's on/off state -- so, following the
SAME precedent as tennis_h2h_claims.py, this producer pre-aggregates the
FULL (unfiltered) ordered-pair population to a snapshot parquet with plain
lift/seconds columns, and the claim goes through the validator's PLAIN
(non-aggregate) formula path, which already supports a list entity_key.

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
BOTH_ON_MIN_SECONDS = 18000.0
A_WITHOUT_B_MIN_SECONDS = 12000.0

ROSTER_CONFOUND_CAVEAT = (
    "ROSTER CONFOUND: this pair with/without lift is NOT a causal player-impact estimate -- "
    "which two players share the floor together correlates with coach trust, opponent "
    "strength, and garbage-time usage, none of which are controlled for here. "
    "DESCRIPTIVE_ONLY until an earned predictive-validity receipt says otherwise."
)
COACH_DEPLOYMENT_CAVEAT = (
    "COACH-DEPLOYMENT CONFOUND: who shares the floor with whom is CHOSEN by the coaching "
    "staff (matchup, foul trouble, rest plan), not randomly assigned -- a high lift may "
    "reflect deliberate favorable deployment (e.g. B only plays A's minutes against bench "
    "units), not a genuine on-court chemistry effect."
)
GARBAGE_TIME_CAVEAT = (
    "GARBAGE-TIME CONTAMINATION: UNFILTERED. The stint table's `quality` field is a "
    "reconstruction-repair flag (bad_seed_n / n_on_court mismatch notes), not a garbage-time "
    "indicator -- no blowout-margin or clock-differential filter is applied to either "
    "condition's minutes here."
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _name_lookup(box_df: pd.DataFrame) -> dict[int, str]:
    names = box_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]
    return {int(k): str(v) for k, v in names.items()}


def compute_pair_table(stints_df: pd.DataFrame) -> pd.DataFrame:
    """FULL (unfiltered) ordered-pair population: one row per (team_id,
    player_a, player_b) ever observed sharing a team roster in a game, with
    plain both_on_seconds / a_without_b_seconds / net_per48_both /
    net_per48_a_without_b / lift columns. Denominators of zero -> NaN net
    rating (never a crash); rows never observed apart, or never observed
    together, simply carry a NaN on that side and get floored out downstream."""
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    clean["players"] = clean["lineup_key"].str.split(",")

    acc: dict[tuple[int, int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for (_gid, tid), grp in clean.groupby(["game_id", "team_id"]):
        roster = sorted(set().union(*grp["players"])) if len(grp) else []
        for players, elapsed_s, pts_for, pts_against in zip(
            grp["players"], grp["elapsed_s"], grp["pts_for"], grp["pts_against"]
        ):
            on = set(players)
            for a in on:
                for b in roster:
                    if b == a:
                        continue
                    key = (tid, int(a), int(b))
                    if b in on:
                        acc[key]["both_on_s"] += elapsed_s
                        acc[key]["both_on_pf"] += pts_for
                        acc[key]["both_on_pa"] += pts_against
                    else:
                        acc[key]["a_wo_b_s"] += elapsed_s
                        acc[key]["a_wo_b_pf"] += pts_for
                        acc[key]["a_wo_b_pa"] += pts_against

    rows = []
    for (tid, a, b), v in acc.items():
        both_s, wo_s = v["both_on_s"], v["a_wo_b_s"]
        net_both = (v["both_on_pf"] - v["both_on_pa"]) * 48.0 * 60.0 / both_s if both_s > 0 else float("nan")
        net_wo = (v["a_wo_b_pf"] - v["a_wo_b_pa"]) * 48.0 * 60.0 / wo_s if wo_s > 0 else float("nan")
        rows.append({
            "team_id": tid, "player_a": a, "player_b": b,
            "both_on_seconds": round(both_s, 2), "a_without_b_seconds": round(wo_s, 2),
            "net_per48_both": net_both, "net_per48_a_without_b": net_wo,
            "lift": net_both - net_wo,
        })
    return pd.DataFrame(rows)


def build_pair_claim(season: str = "2025_26") -> dict[str, Any]:
    stints_src = _LINEUPS_DIR / f"stints_{season}.parquet"
    stints_df = pd.read_parquet(stints_src)
    table = compute_pair_table(stints_df)
    n_considered = len(table)

    names = _name_lookup(pd.read_parquet(_BOX_SRC))
    table["player_a_name"] = table["player_a"].map(names).fillna("Unknown")
    table["player_b_name"] = table["player_b"].map(names).fillna("Unknown")

    snap_dir = _OUT_DIR / "nba_teammate_context_pair_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"pair_lift_{season}.parquet"
    table.to_parquet(snap_path, index=False)

    mask = (
        (table["both_on_seconds"] >= BOTH_ON_MIN_SECONDS)
        & (table["a_without_b_seconds"] >= A_WITHOUT_B_MIN_SECONDS)
        & table["lift"].notna()
    )
    n_excluded = n_considered - int(mask.sum())
    qualifiers = table[mask].sort_values("lift", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i, "team_id": int(row.team_id),
            "player_a": int(row.player_a), "player_b": int(row.player_b),
            "player_a_name": str(row.player_a_name), "player_b_name": str(row.player_b_name),
            "entity_name": f"{row.player_a_name} + {row.player_b_name}",
            "value": round(float(row.lift), 4),
            "n": round(float(min(row.both_on_seconds, row.a_without_b_seconds)) / 60.0, 2),
        })

    corpus = SEASON_CORPUS.get(season, season)
    if not ranking:
        print(f"SKIP nba_teammate_context_pair_lift_{season}: 0 of {n_considered} pairs "
              "clear the min_sample floor -- claim not emitted")

    return {
        "claim_id": f"nba_teammate_context_pair_lift_{season}",
        "kind": "ranking", "label": "DESCRIPTIVE_ONLY",
        "question": (
            f"Which NBA teammate pairs lift the team's net rating the most when both share "
            f"the floor, vs. one without the other ({corpus} {season} slice)?"
        ),
        "criteria": {
            "metric": "pair_lift", "formula": "net_per48_both - net_per48_a_without_b",
            "window": f"season_{season}_nba_lineup_corpus",
            "min_sample": {"both_on_seconds": BOTH_ON_MIN_SECONDS, "a_without_b_seconds": A_WITHOUT_B_MIN_SECONDS},
            "direction": "desc", "value_precision": 4,
            "entity_key": ["team_id", "player_a", "player_b"],
        },
        "ranking": ranking, "source_files": [_rel(snap_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            ROSTER_CONFOUND_CAVEAT, COACH_DEPLOYMENT_CAVEAT, GARBAGE_TIME_CAVEAT,
            "lift = net_per48_both (team net rating/48 with A and B both on) minus "
            "net_per48_a_without_b (team net rating/48 with A on, B off) -- directional, "
            "row (A,B) is 'B's lift on A', distinct from row (B,A) 'A's lift on B'.",
            "min_sample floor both_on_seconds>=18000 (300 min) AND a_without_b_seconds>=12000 "
            "(200 min) -- below-floor pairs are honestly counted in n_excluded_below_floor, "
            "never dropped from n_considered.",
            "FULL POPULATION above floor, no top-N cap. DESCRIPTIVE_ONLY -- NOT a gate, "
            "no market/$ edge claimed.",
        ],
    }
