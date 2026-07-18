"""5th claim of the nba_lineup_context family: per-team best/worst 5-man
lineup by shot-location spacing (spacing_mean_dist), split out from
nba_lineup_context_claims.py to stay under the 300-LOC rail.

PREREGISTERED FLOOR (declared here BEFORE scoring): n_shots >= 100 -- higher
than nba_lineup_spacing_claims.py's n_shots>=20 (that family ranks EVERY
qualifying lineup leaguewide; this one narrows to a per-team best/worst pick,
so it demands a sturdier per-lineup shot sample). A team needs >=2 lineups
clearing the floor to have a distinct best AND worst -- teams with 0 or 1
survivors are SKIPPED (never emitted with a synthetic best=worst row).

SOURCE: lineup_spacing_<season>.parquet is grouped by team_id; each team's
FULL (unfiltered) subset is written to its own snapshot parquet so
claims_validator.py's plain-formula path can independently re-apply the
n_shots floor and re-derive n_excluded_below_floor per team, the same
"write the pool, let the validator floor it" precedent as
nba_shooter_profile_claims.py. Ranking is FULL (every team lineup above
floor), rank 1 = best (most spread out), last rank = worst.

CRITICAL HONESTY RULE: even a lineup-level ranking carries the same ROSTER
CONFOUND as an individual on/off claim -- which 5 players share the floor
correlates with coach trust, opponent strength, and garbage-time usage, so
this is DESCRIPTIVE_ONLY, never a causal "this lineup spaces the floor
better" claim.

NETWORK: zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"

SEASON_CORPUS = {"2024_25": "1230-game", "2025_26": "196-game"}
MIN_SHOTS = 100

ROSTER_CONFOUND_CAVEAT = (
    "ROSTER CONFOUND: a lineup's spacing ranking is NOT a causal 'this lineup spaces "
    "better' claim -- which 5 players share the floor correlates with coach trust, "
    "opponent strength, and garbage-time usage, none of which are controlled for. "
    "DESCRIPTIVE_ONLY until an earned predictive-validity receipt says otherwise."
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_spacing_claims(season: str = "2025_26") -> list[dict[str, Any]]:
    src = _LINEUPS_DIR / f"lineup_spacing_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    corpus = SEASON_CORPUS.get(season, season)
    snap_dir = _OUT_DIR / "nba_lineup_context_spacing_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    claims: list[dict[str, Any]] = []
    for team_id, grp in df.groupby("team_id"):
        n_considered = len(grp)
        qualifiers = grp[(grp["n_shots"] >= MIN_SHOTS) & grp["spacing_mean_dist"].notna()]
        if len(qualifiers) < 2:
            print(f"SKIP nba_lineup_context_spacing_{season}_{team_id}: "
                  f"{len(qualifiers)} of {n_considered} lineups clear the n_shots>={MIN_SHOTS} "
                  "floor -- need >=2 for a best/worst pick, claim not emitted")
            continue

        snap_path = snap_dir / f"team_{team_id}_{season}.parquet"
        grp.reset_index(drop=True).to_parquet(snap_path, index=False)

        ranked = qualifiers.sort_values("spacing_mean_dist", ascending=False).reset_index(drop=True)
        n_excluded = n_considered - len(ranked)
        ranking = [
            {"rank": i, "team_id": int(row.team_id), "lineup_key": str(row.lineup_key),
             "value": round(float(row.spacing_mean_dist), 4), "n": int(row.n_shots)}
            for i, row in enumerate(ranked.itertuples(index=False), start=1)
        ]
        claims.append({
            "claim_id": f"nba_lineup_context_spacing_{season}_{team_id}",
            "kind": "ranking", "label": "DESCRIPTIVE_ONLY",
            "question": (
                f"For team {team_id}, which 5-man lineup has the most (best) vs. least "
                f"(worst) spread-out shot-location diet ({corpus} {season} slice)?"
            ),
            "criteria": {
                "metric": "spacing_mean_dist", "formula": "spacing_mean_dist",
                "window": f"season_{season}_nba_lineup_corpus", "min_sample": {"n_shots": MIN_SHOTS},
                "direction": "desc", "value_precision": 4, "entity_key": "lineup_key",
            },
            "ranking": ranking, "source_files": [_rel(snap_path)],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
            "edge_claimed": False,
            "caveats": [
                ROSTER_CONFOUND_CAVEAT,
                f"min_sample floor n_shots>={MIN_SHOTS} -- narrower leaguewide claims use "
                "n_shots>=20 (every qualifying lineup); this per-team best/worst pick "
                "demands a sturdier per-lineup shot sample.",
                "team-scoped: source_files is a per-team snapshot of "
                f"{_rel(_LINEUPS_DIR / f'lineup_spacing_{season}.parquet')}, so the "
                "ranking is only comparable WITHIN this team, never across teams.",
                "FULL POPULATION (this team) above floor -- rank 1 is best (most spread), "
                "last rank is worst. DESCRIPTIVE_ONLY -- NOT a gate, no market/$ edge claimed.",
            ],
        })
    return claims
