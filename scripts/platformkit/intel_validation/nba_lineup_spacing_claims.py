"""NBA lineup floor-spacing DESCRIPTIVE ranking claim (lane
lineup-reconstruction-keystone). Pair-keyed (team_id, lineup_key) -- a
5-man lineup_key (comma-joined sorted personIds) is only unique WITHIN a
team, so the pair is the real ranking entity.

SOURCE: domains/basketball_nba/lineups/gravity_spacing.py's build_spacing()
output, data/cache/team_system/lineups/lineup_spacing_2025_26.parquet --
FULL POPULATION (every lineup with >=2 attributed shots; the module's own
docstring records that this is deliberately unfiltered so the claims floor
below is applied, and independently re-derivable, HERE rather than baked
into the product parquet).

METRIC: spacing_mean_dist = mean pairwise Euclidean distance (court x/y)
between every shot attempted while that exact 5-man lineup was on the floor
-- a proxy for shot-location spread, not itself expressible in
safe_formula's aggregate grammar (pdist is not a whitelisted aggregate), so
this follows the SAME "pre-aggregated side parquet, plain formula path"
precedent as tennis_h2h_claims.py: the validator re-reads the already
-computed spacing_mean_dist column directly (formula="spacing_mean_dist"),
it does not re-run pdist itself (that recompute lives in
gravity_spacing.py's own per-file test).

MIN-SAMPLE FLOOR: n_shots>=20 -- below this a lineup's shot-location spread
is dominated by 1-3 possessions, not a stable spacing signal.

NETWORK: zero. DESCRIPTIVE shot-location-spread ranking only -- NOT a
predictor, no market/$ edge claimed, no gate.

CLI: python -m scripts.platformkit.intel_validation.nba_lineup_spacing_claims
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
_CLAIMS_OUT = _OUT_DIR / "nba_lineup_spacing_claims.jsonl"

# season window -> human corpus descriptor. Both windows are emitted into the
# SAME store; the weighting gate's prior_season_metrics resolves the 2024_25
# window itself when evaluating 2025-26 (leak-free design (a)).
SEASONS = {"2025_26": "196-game", "2024_25": "1230-game"}
MIN_SHOTS = 20


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_spacing_claim(season: str = "2025_26") -> dict[str, Any]:
    src = _LINEUPS_DIR / f"lineup_spacing_{season}.parquet"
    corpus = SEASONS[season]
    df = pd.read_parquet(src)
    n_considered = len(df)
    qualifiers = df[(df["n_shots"] >= MIN_SHOTS) & df["spacing_mean_dist"].notna()].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("spacing_mean_dist", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team_id": int(row.team_id),
            "lineup_key": str(row.lineup_key),
            "value": round(float(row.spacing_mean_dist), 4),
            "n": int(row.n_shots),
        })

    return {
        "claim_id": f"nba_lineup_spacing_full_{season}",
        "kind": "ranking",
        "question": (
            f"Which NBA 5-man lineups have the most spread-out shot-location diet "
            f"(mean pairwise shot distance, full population above floor, "
            f"{season} {corpus} slice)?"
        ),
        "criteria": {
            "metric": "spacing_mean_dist",
            "formula": "spacing_mean_dist",
            "window": f"season_{season}_nba_lineup_corpus",
            "min_sample": {"n_shots": MIN_SHOTS},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": ["team_id", "lineup_key"],
        },
        "ranking": ranking,
        "source_files": [_rel(src)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "spacing_mean_dist = mean pairwise Euclidean distance (court x/y percent "
            "coordinates) between every shot attempted while this exact 5-man lineup was on "
            f"the floor, from {_rel(src)} "
            f"(pbp_lineups.py's reconstructed stints, {corpus} {season} PBP corpus). A "
            "DESCRIPTIVE shot-location-spread proxy, not a validated 'floor spacing' metric.",
            f"min_sample floor n_shots>={MIN_SHOTS} -- below this a lineup's shot-location "
            "spread reflects a handful of possessions, not a stable pattern.",
            "Pair-keyed entity (team_id, lineup_key): a 5-man lineup_key is only unique "
            "within its own team, and the identical five-personId combination can recur "
            "across multiple stints/games for that team (rows are already summed across "
            "every recurrence before this floor is applied).",
            "FULL POPULATION: every lineup clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE shot-location aggregate ONLY -- NOT a gate, NOT a predictive claim, "
            "no market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA lineup-spacing ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default="all", choices=[*SEASONS, "all"])
    args = parser.parse_args(argv)

    seasons = list(SEASONS) if args.season == "all" else [args.season]
    claims = [build_spacing_claim(s) for s in seasons]
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        print(
            f"{claim['claim_id']}: n_considered={claim['n_considered']} "
            f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
            f"top1={json.dumps(claim['ranking'][0]) if claim['ranking'] else None}"
        )
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
