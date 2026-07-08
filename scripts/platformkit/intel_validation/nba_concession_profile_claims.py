"""NBA opponent scheme-concession DESCRIPTIVE ranking claims (lane
composition-backbone). Two claims from the SAME full, unfiltered per-defense
population in concession_profiles.py's own output -- same "atlas already
aggregated it" precedent as nba_on_off_claims.py -- one row per team_id
(the defense), 30 rows total (every 2025-26 team), no snapshot rebuilt here.

  1. rim_efg_allowed  (asc -- lower means a BETTER rim defense: opponents
     shoot a worse eFG% at the rim against this team).
  2. share_assisted_allowed (desc -- higher means this defense allows more
     ball-movement-assisted offense, a scheme-permeability descriptor).

SOURCE: data/cache/team_system/composition/concession_2025_26.parquet, built
by domains/basketball_nba/composition/concession_profiles.py from the
1192-game 2025-26 PBP corpus (every shot's defending team + zone/assist/
transition attribution).

MIN-SAMPLE FLOORS: n_shots_faced>=400 for both claims, plus
rim_fga_allowed>=100 for the rim claim -- this corpus mixes regular-season
and playoff games so per-team shot volume varies widely (playoff-run teams
face far more shots than early-eliminated ones); the floor is a safety net,
not an active filter, at only 30 entities total.

NETWORK: zero. DESCRIPTIVE shot-diet-allowed ranking only -- NOT a
predictive/causal claim, no market/$ edge claimed, no gate.

CLI: python -m scripts.platformkit.intel_validation.nba_concession_profile_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_CONCESSION_SRC = REPO_ROOT / "data" / "cache" / "team_system" / "composition" / "concession_2025_26.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_concession_profile_claims.jsonl"

SEASON_WINDOW = "2025_26"
MIN_SHOTS_FACED = 400
MIN_RIM_FGA_ALLOWED = 100


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _build_ranking(
    df: pd.DataFrame, metric: str, direction: str, min_sample: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    n_considered = len(df)
    mask = pd.Series(True, index=df.index)
    for col, floor in min_sample.items():
        mask &= df[col] >= floor
    mask &= df[metric].notna()
    qualifiers = df[mask].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(metric, ascending=(direction == "asc")).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "defense_team_id": int(getattr(row, "defense_team_id")),
            "value": round(float(getattr(row, metric)), 4),
            "n": int(getattr(row, "n_shots_faced")),
        })
    return ranking, n_considered, n_excluded


def build_rim_concession_claim(df: pd.DataFrame) -> dict[str, Any]:
    min_sample = {"n_shots_faced": MIN_SHOTS_FACED, "rim_fga_allowed": MIN_RIM_FGA_ALLOWED}
    ranking, n_considered, n_excluded = _build_ranking(df, "rim_efg_allowed", "asc", min_sample)
    return {
        "claim_id": f"nba_concession_rim_efg_allowed_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which NBA defenses allow the lowest eFG%% at the rim (full population above "
            f"floor, {SEASON_WINDOW} 1192-game PBP corpus)?"
        ),
        "criteria": {
            "metric": "rim_efg_allowed",
            "formula": "rim_efg_allowed",
            "window": f"season_{SEASON_WINDOW}_nba_composition_corpus",
            "min_sample": min_sample,
            "direction": "asc",
            "value_precision": 4,
            "entity_key": "defense_team_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_CONCESSION_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "rim_efg_allowed = (FGM + 0.5*FG3M) / FGA at the 'Restricted Area' PBP zone label, "
            "for shots this team defended, from concession_2025_26.parquet (every shot in the "
            "1192-game 2025-26 PBP corpus, defending team resolved as the non-shooting team_id).",
            f"min_sample floor n_shots_faced>={MIN_SHOTS_FACED} AND rim_fga_allowed>="
            f"{MIN_RIM_FGA_ALLOWED} -- this corpus mixes regular-season and playoff games, so "
            "per-team shot volume varies widely; the floor is a safety net at only 30 entities.",
            "DESCRIPTIVE shot-diet-allowed aggregate ONLY -- does not control for opponent shot "
            "selection or shooter quality faced; NOT a predictive/causal defensive-rating claim, "
            "NOT a gate, no market/$ edge claimed.",
        ],
    }


def build_assisted_concession_claim(df: pd.DataFrame) -> dict[str, Any]:
    min_sample = {"n_shots_faced": MIN_SHOTS_FACED}
    ranking, n_considered, n_excluded = _build_ranking(df, "share_assisted_allowed", "desc", min_sample)
    return {
        "claim_id": f"nba_concession_share_assisted_allowed_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which NBA defenses allow the highest share of ASSISTED makes (full population "
            f"above floor, {SEASON_WINDOW} 1192-game PBP corpus)?"
        ),
        "criteria": {
            "metric": "share_assisted_allowed",
            "formula": "share_assisted_allowed",
            "window": f"season_{SEASON_WINDOW}_nba_composition_corpus",
            "min_sample": min_sample,
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "defense_team_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_CONCESSION_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "share_assisted_allowed = assisted makes / total makes allowed (assistPersonId "
            "present on the made-shot PBP action), from concession_2025_26.parquet, 1192-game "
            "2025-26 PBP corpus.",
            f"min_sample floor n_shots_faced>={MIN_SHOTS_FACED} -- safety net at only 30 entities.",
            "DESCRIPTIVE ball-movement-allowed aggregate ONLY -- NOT a predictive/causal claim, "
            "NOT a gate, no market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA concession-profile ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    df = pd.read_parquet(_CONCESSION_SRC)
    claims = [build_rim_concession_claim(df), build_assisted_concession_claim(df)]
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
