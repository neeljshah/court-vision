"""NBA "teammate effects" claim family (nba_teammate_context) -- who lifts
whom. Three claims:

  1. pair with/without net-rating lift (nba_teammate_context_pairs.py)
  2. gravity-teammate scoring-context delta (nba_teammate_context_gravity.py)
  3. lineup synergy-residual top/bottom (THIS file, 2024-25 only)

Claims 1-2 are built per season (2023_24, 2024_25, 2025_26). Claim 3 reads
data/cache/team_system/lineups/lineup_synergy_2024_25.parquet ONLY -- that
parquet has no 2025-26 edition (caveat says so explicitly, never silently
extrapolated).

CLAIM 3 SOURCE: lineup_synergy_2024_25.parquet already carries a computed
`qualifies` boolean (n_members_qualified-derived) -- reapplied here as a
real min_sample floor (qualifies>=True; pandas bool>=bool comparison behaves
as equality) so the validator's independent recompute is genuine, not
trusted from the producer's own flag. TOP 25 and BOTTOM 25 by
synergy_residual (declared TOP-N, not full population -- "top/bottom
lineups" per spec, distinct from nba_lineup_synergy_claims.py's own
full-population ranking of a sibling parquet).

CRITICAL HONESTY RULE (binding, user-established, all 3 claims):
DESCRIPTIVE_ONLY, roster confound + coach-deployment confound + garbage-time
contamination (unfiltered) caveats on every claim; none promoted to a
predictive/edge claim without an earned predictive-validity receipt.

NETWORK: zero. CLI:
    python -m scripts.platformkit.intel_validation.nba_teammate_context_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \\
        data/cache/intel_claims/nba_teammate_context_claims.jsonl \\
        --output data/cache/intel_claims/nba_teammate_context_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_teammate_context_claims.jsonl"

SEASONS = ["2023_24", "2024_25", "2025_26"]
SYNERGY_SEASON = "2024_25"
SYNERGY_TOP_N = 25

ROSTER_CONFOUND_CAVEAT = (
    "ROSTER CONFOUND: a lineup's synergy ranking is NOT a causal 'this lineup has real "
    "chemistry' claim -- which 5 players share the floor correlates with coach trust, "
    "opponent strength, and garbage-time usage, none of which are controlled for. "
    "DESCRIPTIVE_ONLY until an earned predictive-validity receipt says otherwise."
)
COACH_DEPLOYMENT_CAVEAT = (
    "COACH-DEPLOYMENT CONFOUND: which 5 players are deployed together is a lineup DECISION "
    "(matchup plan, rotation pattern), not randomly assigned."
)
GARBAGE_TIME_CAVEAT = (
    "GARBAGE-TIME CONTAMINATION: UNFILTERED -- no blowout-margin or clock-differential filter "
    "is applied to lineup minutes here."
)
NO_2025_26_CAVEAT = (
    "2024-25 ONLY: lineup_synergy_2024_25.parquet has no 2025-26 edition on disk -- this claim "
    "is never silently extrapolated to the current season."
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _build_synergy_claim(direction: str) -> dict[str, Any]:
    src = _LINEUPS_DIR / f"lineup_synergy_{SYNERGY_SEASON}.parquet"
    df = pd.read_parquet(src)
    n_considered = len(df)
    qualifiers = df[df["qualifies"] >= True].copy()
    n_excluded = n_considered - len(qualifiers)
    ascending = direction == "asc"
    qualifiers = qualifiers.sort_values("synergy_residual", ascending=ascending).head(SYNERGY_TOP_N).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i, "team_id": int(row.team_id), "lineup_key": str(row.lineup_key),
            "value": round(float(row.synergy_residual), 4), "n": round(float(row.min), 2),
        })

    label = "top" if direction == "desc" else "bottom"
    if not ranking:
        print(f"SKIP nba_teammate_context_synergy_{label}_{SYNERGY_SEASON}: 0 of "
              f"{n_considered} lineups clear the qualifies floor -- claim not emitted")

    return {
        "claim_id": f"nba_teammate_context_synergy_{label}_{SYNERGY_SEASON}",
        "kind": "ranking", "label": "DESCRIPTIVE_ONLY",
        "question": (
            f"Which NBA 5-man lineups {'most outperform' if direction == 'desc' else 'most underperform'} "
            f"their individual-talent-sum expectation ({label} {SYNERGY_TOP_N}, {SYNERGY_SEASON} slice)?"
        ),
        "criteria": {
            "metric": "synergy_residual", "formula": "synergy_residual",
            "window": f"season_{SYNERGY_SEASON}_nba_lineup_corpus",
            "min_sample": {"qualifies": True},
            "direction": direction, "value_precision": 4,
            "entity_key": ["team_id", "lineup_key"],
        },
        "ranking": ranking, "source_files": [_rel(src)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            ROSTER_CONFOUND_CAVEAT, COACH_DEPLOYMENT_CAVEAT, GARBAGE_TIME_CAVEAT, NO_2025_26_CAVEAT,
            f"synergy_residual read as-is from {_rel(src)} -- lineup's own actual net rating "
            "per48 minus the mean of its 5 members' individual on/off net ratings.",
            "min_sample floor qualifies==True (source-computed n_members_qualified flag) -- "
            "below-floor lineups are honestly counted in n_excluded_below_floor.",
            f"TOP {SYNERGY_TOP_N} only ({label}) -- NOT the full qualifying population; see "
            "nba_lineup_synergy_claims.py for a full-population ranking of the sibling "
            "interactions/lineup_synergy parquet.",
        ],
    }


def build_all_claims(seasons: list[str] | None = None) -> list[dict[str, Any]]:
    from scripts.platformkit.intel_validation.nba_teammate_context_pairs import build_pair_claim
    from scripts.platformkit.intel_validation.nba_teammate_context_gravity import build_gravity_claim

    seasons = seasons or SEASONS
    claims: list[dict[str, Any]] = []
    for season in seasons:
        claims.append(build_pair_claim(season))
        claims.append(build_gravity_claim(season))
    if SYNERGY_SEASON in seasons or seasons == SEASONS:
        claims.append(_build_synergy_claim("desc"))
        claims.append(_build_synergy_claim("asc"))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept = [c for c in claims if c["ranking"]]
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in kept:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA teammate-context claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default="all", choices=[*SEASONS, "all"])
    args = parser.parse_args(argv)

    seasons = SEASONS if args.season == "all" else [args.season]
    claims = build_all_claims(seasons)
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        if not claim["ranking"]:
            continue
        print(
            f"{claim['claim_id']}: n_considered={claim['n_considered']} "
            f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
            f"top1={json.dumps(claim['ranking'][0])}"
        )
    print(f"wrote {len([c for c in claims if c['ranking']])} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
