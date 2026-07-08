"""NBA player "gravity proxy" DESCRIPTIVE ranking claim (lane
lineup-reconstruction-keystone). Pair-keyed (player_id, team_id), same
rationale as nba_on_off_claims.py (42 players appear under >1 team_id in
this 196-game slice).

SOURCE: the SAME full, unfiltered on_off_2025_26.parquet as
nba_on_off_claims.py -- gravity_proxy is a plain subtraction of two columns
already on that per-entity table (teammate_efg_on, teammate_efg_off), so
the validator's plain formula path ("teammate_efg_on - teammate_efg_off")
recomputes it directly with zero extra snapshot. This is deliberately NOT
domains/basketball_nba/lineups/gravity_spacing.py's own
gravity_proxy_2025_26.parquet output, because that product parquet is
ALREADY floor-filtered (build_gravity() only emits qualifying rows) -- if
claimed source_files pointed there, the validator's independent floor
re-application would see zero excluded rows and the claim's stated
n_considered/n_excluded would be meaningless. Pointing at the full
population instead lets the validator re-derive both the value AND the
floor honestly, exactly mirroring gravity_spacing.build_gravity's own logic.

METRIC: gravity_proxy = teammate_efg_on - teammate_efg_off (positive means
teammates shoot a better eFG% with this player on the floor than off it).

MIN-SAMPLE FLOOR: min_on>=300, teammate_fga_on>=200, teammate_fga_off>=200
-- IDENTICAL floors to gravity_spacing.py's MIN_ON_MINUTES/MIN_TEAMMATE_FGA
constants (kept as literal values here, not imported, to keep this module's
only import surface pandas -- the two are proven identical by
test_nba_gravity_proxy_claims.py's parity check against build_gravity()).

NETWORK: zero. DESCRIPTIVE gravity-proxy ranking only -- NOT a causal claim,
no market/$ edge claimed, no gate.

CLI: python -m scripts.platformkit.intel_validation.nba_gravity_proxy_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_ON_OFF_SRC = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "on_off_2025_26.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_gravity_proxy_claims.jsonl"

SEASON_WINDOW = "2025_26"
MIN_ON_MINUTES = 300.0
MIN_TEAMMATE_FGA = 200


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_gravity_claim() -> dict[str, Any]:
    df = pd.read_parquet(_ON_OFF_SRC)
    n_considered = len(df)
    mask = (
        (df["min_on"] >= MIN_ON_MINUTES)
        & (df["teammate_fga_on"] >= MIN_TEAMMATE_FGA)
        & (df["teammate_fga_off"] >= MIN_TEAMMATE_FGA)
        & df["teammate_efg_on"].notna()
        & df["teammate_efg_off"].notna()
    )
    qualifiers = df[mask].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["gravity_proxy"] = qualifiers["teammate_efg_on"] - qualifiers["teammate_efg_off"]
    qualifiers = qualifiers.sort_values("gravity_proxy", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "player_id": int(row.player_id),
            "team_id": int(row.team_id),
            "player_name": str(row.player_name),
            "value": round(float(row.gravity_proxy), 4),
            "n": int(min(row.teammate_fga_on, row.teammate_fga_off)),
        })

    return {
        "claim_id": f"nba_gravity_proxy_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which NBA players' teammates shoot the best eFG% with them on the floor vs. "
            f"off it (gravity proxy, full population above floor, {SEASON_WINDOW} 196-game slice)?"
        ),
        "criteria": {
            "metric": "gravity_proxy",
            "formula": "teammate_efg_on - teammate_efg_off",
            "window": f"season_{SEASON_WINDOW}_nba_lineup_corpus",
            "min_sample": {
                "min_on": MIN_ON_MINUTES, "teammate_fga_on": MIN_TEAMMATE_FGA, "teammate_fga_off": MIN_TEAMMATE_FGA,
            },
            "direction": "desc",
            "value_precision": 4,
            "entity_key": ["player_id", "team_id"],
        },
        "ranking": ranking,
        "source_files": [_rel(_ON_OFF_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "gravity_proxy = teammate eFG% while this player is ON the floor minus teammate "
            "eFG% while OFF it, from data/cache/team_system/lineups/on_off_2025_26.parquet "
            "(shot-event attribution over pbp_lineups.py's reconstructed lineup stints, "
            "196-game 2025-26 PBP corpus). A DESCRIPTIVE association, not a causal gravity "
            "measurement (lineup/opponent quality is not controlled for).",
            f"min_sample floor min_on>={MIN_ON_MINUTES} AND teammate_fga_on>={MIN_TEAMMATE_FGA} "
            f"AND teammate_fga_off>={MIN_TEAMMATE_FGA} -- both sides of the split need real "
            "teammate shot volume, not just on-court minutes, or the eFG% comparison is noise.",
            "Pair-keyed entity (player_id, team_id): 42 players in this corpus appear under "
            "more than one team_id (mid-window trades), so player_id alone is not unique.",
            "FULL POPULATION: every (player,team) clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/causal claim, "
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
    parser = argparse.ArgumentParser(description="Emit NBA gravity-proxy ranking claim")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claim = build_gravity_claim()
    out_path = write_claims([claim], Path(args.output))
    print(
        f"{claim['claim_id']}: n_considered={claim['n_considered']} "
        f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
        f"top1={claim['ranking'][0] if claim['ranking'] else None}"
    )
    print(f"wrote 1 claim -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
