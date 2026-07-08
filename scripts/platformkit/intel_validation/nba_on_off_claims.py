"""NBA lineup ON/OFF net-rating DESCRIPTIVE ranking claim (lane
lineup-reconstruction-keystone). Pair-keyed (player_id, team_id) -- same
precedent as tennis_h2h_claims.py's list entity_key -- because 42 players in
this 196-game 2025-26 slice appear under >1 team_id (mid-window trades), so
player_id alone is not a unique ranking entity.

SOURCE (already the full, unfiltered per-entity population -- zero new
snapshot needed, same "atlas already aggregated it" precedent as
wnba_claims.py's full_population_ranking): domains/basketball_nba/lineups
/on_off.py's own output, data/cache/team_system/lineups/on_off_2025_26
.parquet, one row per (player_id, team_id) with plain columns (min_on,
net_rating_on_per48, ...) built from stint-level on/off attribution over
pbp_lineups.py's reconstructed lineup stints.

METRIC: net_rating_on_per48 = (team pts_for - pts_against while the player
is on the floor) per 48 minutes, already computed by on_off.py -- the
validator's plain (non-aggregate) formula path re-reads that column
directly (formula="net_rating_on_per48"), it does not re-derive it from
raw stints (that recompute lives in on_off.py's own per-file test).

MIN-SAMPLE FLOOR: min_on>=150 minutes -- a defensible floor against small
in-season samples (this corpus is 196 games total, not a full season per
team); below-floor players are counted in n_excluded_below_floor, never
silently dropped.

NETWORK: zero. DESCRIPTIVE net-rating-while-on-floor ranking only -- NOT a
predictor, no market/$ edge claimed, no gate.

CLI: python -m scripts.platformkit.intel_validation.nba_on_off_claims
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
_CLAIMS_OUT = _OUT_DIR / "nba_on_off_claims.jsonl"

# season window -> human corpus descriptor. Both windows are emitted into the
# SAME store; the weighting gate's prior_season_metrics resolves the 2024_25
# window itself when evaluating 2025-26 (leak-free design (a)).
SEASONS = {"2025_26": "196-game", "2024_25": "1230-game"}
MIN_ON_MINUTES = 150.0


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_on_off_claim(season: str = "2025_26") -> dict[str, Any]:
    src = _LINEUPS_DIR / f"on_off_{season}.parquet"
    corpus = SEASONS[season]
    df = pd.read_parquet(src)
    n_considered = len(df)
    qualifiers = df[(df["min_on"] >= MIN_ON_MINUTES) & df["net_rating_on_per48"].notna()].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("net_rating_on_per48", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "player_id": int(row.player_id),
            "team_id": int(row.team_id),
            "player_name": str(row.player_name),
            "value": round(float(row.net_rating_on_per48), 4),
            "n": round(float(row.min_on), 2),
        })

    return {
        "claim_id": f"nba_lineup_net_rating_on_full_{season}",
        "kind": "ranking",
        "question": (
            f"Which NBA players' teams outscore opponents the most per 48 minutes while "
            f"they are on the floor (full population above floor, {season} {corpus} slice)?"
        ),
        "criteria": {
            "metric": "net_rating_on_per48",
            "formula": "net_rating_on_per48",
            "window": f"season_{season}_nba_lineup_corpus",
            "min_sample": {"min_on": MIN_ON_MINUTES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": ["player_id", "team_id"],
        },
        "ranking": ranking,
        "source_files": [_rel(src)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "net_rating_on_per48 = (team pts_for - pts_against while this player is on the "
            f"floor) / on-court minutes * 48, from {_rel(src)} "
            "(stint-level attribution over pbp_lineups.py's reconstructed 5-man lineup "
            f"stints, {corpus} {season} PBP corpus).",
            f"min_sample floor min_on>={MIN_ON_MINUTES} minutes -- small on-court samples "
            "are excluded as noise.",
            "Pair-keyed entity (player_id, team_id): players can appear under more than "
            "one team_id in a window (mid-window trades), so player_id alone is not unique.",
            "FULL POPULATION: every (player,team) clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE net-rating-while-on-floor aggregate ONLY -- NOT a predictive/causal "
            "claim about the player's individual impact, NOT a gate, no market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA lineup on/off net-rating ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default="all", choices=[*SEASONS, "all"])
    args = parser.parse_args(argv)

    seasons = list(SEASONS) if args.season == "all" else [args.season]
    claims = [build_on_off_claim(s) for s in seasons]
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
