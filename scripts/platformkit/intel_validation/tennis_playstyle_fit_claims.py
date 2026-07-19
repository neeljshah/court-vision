"""Tennis playstyle-fit/comparables ingredient claims (depth-wave-1, lane 3).

Emits FULL-POPULATION descriptive `kind:"ranking"` claims straight from the
wave-earlier atlas data/domains/tennis/atlas_playstyles.parquet (408 rows,
one row per player -- career-to-date surface/overall win-rate profile), in
the SAME claims contract shape as build_archetype_claim
(nba_fit_ingredient_builders.py:69): PLAIN (non-aggregate) formula path,
scalar entity_key="player_id" (no snapshot needed -- safe_formula's BinOp
Sub on two real columns, e.g. `grass_wr - clay_wr`, is directly supported
by the whitelist grammar, so this producer reads the atlas parquet as-is).

Two claims:
  (1) surface_tilt: grass_wr - clay_wr (a grass-tilted vs clay-tilted
      descriptive lean). Requires BOTH surface win-rates present -- a
      player with no recorded grass or clay matches has no tilt to report,
      so this claim's population is the total_matches>=20 floor further
      restricted to grass_wr/clay_wr both non-null (excluded count stated
      honestly in caveats, separate from the floor exclusion).
  (2) overall_win_rate: ov_wr (plain career win rate, all surfaces).

FLOOR: total_matches>=20 (below this a win-rate is noise, matching the
floor logic used across the tennis claim families in this directory).
Player names are enriched via a read-only join against
data/domains/tennis/players.parquet (full_name) -- descriptive display
field only, not part of the validated metric.

DESCRIPTIVE career-to-date playstyle profile only -- NOT a forecast, no
market/$ edge claimed.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_playstyle_fit_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]

_ATLAS_SOURCE = REPO_ROOT / "data" / "domains" / "tennis" / "atlas_playstyles.parquet"
_PLAYERS_SOURCE = REPO_ROOT / "data" / "domains" / "tennis" / "players.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_playstyle_fit_claims.jsonl"

MIN_TOTAL_MATCHES = 20  # below this a career win-rate is small-sample noise


def _name_lookup() -> dict[int, str]:
    players = pd.read_parquet(_PLAYERS_SOURCE, columns=["player_id", "full_name"])
    return dict(zip(players["player_id"].astype(int), players["full_name"].astype(str)))


def build_surface_tilt_claim(atlas: pd.DataFrame, names: dict[int, str]) -> dict[str, Any]:
    floored = atlas[atlas["total_matches"] >= MIN_TOTAL_MATCHES]
    n_considered = len(floored)
    n_excluded_floor = len(atlas) - n_considered

    tilt_pool = floored.dropna(subset=["grass_wr", "clay_wr"]).copy()
    n_excluded_no_surface_data = n_considered - len(tilt_pool)
    tilt_pool["surface_tilt"] = tilt_pool["grass_wr"] - tilt_pool["clay_wr"]
    # tie-break: value DESC, THEN player_id ASC -- matches claims_validator.py's
    # generic recompute tie-break, see tennis_ranking_claims.py docstring.
    tilt_pool = tilt_pool.sort_values(["surface_tilt", "player_id"], ascending=[False, True]).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(tilt_pool.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": names.get(pid, "Unknown"),
            "value": round(float(row.surface_tilt), 4),
            "n": int(row.total_matches),
            "grass_wr": round(float(row.grass_wr), 4),
            "clay_wr": round(float(row.clay_wr), 4),
        })

    rel_source = str(_ATLAS_SOURCE.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "tennis_playstyle_fit_surface_tilt_career",
        "kind": "ranking",
        "question": "Which players lean most grass-favoring vs clay-favoring (career-to-date)?",
        "criteria": {
            "metric": "surface_tilt",
            "formula": "grass_wr - clay_wr",
            "window": "career_to_date",
            "min_sample": {"total_matches": MIN_TOTAL_MATCHES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded_floor,
        "caveats": [
            "career-to-date descriptive playstyle; not a forecast; no market claim",
            f"min_sample floor total_matches>={MIN_TOTAL_MATCHES}; below-floor players "
            "counted in n_excluded_below_floor, never silently dropped.",
            f"{n_excluded_no_surface_data} above-floor players excluded from THIS claim only "
            "(not from n_excluded_below_floor) for having no recorded grass or clay matches -- "
            "a tilt cannot be computed without both surface win rates.",
        ],
    }


def build_overall_win_rate_claim(atlas: pd.DataFrame, names: dict[int, str]) -> dict[str, Any]:
    floored = atlas[atlas["total_matches"] >= MIN_TOTAL_MATCHES].copy()
    n_considered = len(atlas)
    n_excluded = n_considered - len(floored)
    # tie-break: value DESC, THEN player_id ASC -- matches claims_validator.py's
    # generic recompute tie-break, see tennis_ranking_claims.py docstring.
    floored = floored.sort_values(["ov_wr", "player_id"], ascending=[False, True]).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(floored.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": names.get(pid, "Unknown"),
            "value": round(float(row.ov_wr), 4),
            "n": int(row.total_matches),
        })

    rel_source = str(_ATLAS_SOURCE.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "tennis_playstyle_fit_overall_win_rate_career",
        "kind": "ranking",
        "question": "What is each qualifying player's career-to-date overall win rate?",
        "criteria": {
            "metric": "ov_wr",
            "formula": "ov_wr",
            "window": "career_to_date",
            "min_sample": {"total_matches": MIN_TOTAL_MATCHES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "career-to-date descriptive playstyle; not a forecast; no market claim",
            f"min_sample floor total_matches>={MIN_TOTAL_MATCHES}; below-floor players "
            "counted in n_excluded_below_floor, never silently dropped.",
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    atlas = pd.read_parquet(_ATLAS_SOURCE)
    names = _name_lookup()
    return [
        build_surface_tilt_claim(atlas, names),
        build_overall_win_rate_claim(atlas, names),
    ]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis playstyle-fit ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        print(
            f"{claim['claim_id']}: n_considered={claim['n_considered']} "
            f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
            f"top1={claim['ranking'][0] if claim['ranking'] else None}"
        )
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
