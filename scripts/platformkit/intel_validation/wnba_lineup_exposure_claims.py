"""WNBA lineup-exposure DESCRIPTIVE ranking claims (census rank 10: "only
non-NBA lineup data; opens the lineup class in a second sport").

Consumes domains.basketball_wnba.atlas_extract_lineup's team_lineup_exposure
atlas (data/cache/atlas_wnba_team_lineup_exposure.parquet, built from the
168-game CDN backfill corpus + full-game substitution-replay stint
reconstruction: domains/basketball_wnba/lineup_stints.py +
atlas_extract_lineup.py) and emits ONE full-population ranking claim --
most-used lineups by minutes_share -- in the SAME claims contract as
wnba_claims.py (reuses its _full_population_ranking/_rel helpers directly,
zero reinvented ranking logic).

FLOOR: n_games>=MIN_GAMES_LINEUP (matches atlas_extract_lineup's own floor)
-- a 5-man combo must recur across >=3 distinct games before it is ranked;
below-floor combos (one-off garbage-time 5-man units) are counted, not
dropped silently.

DESCRIPTIVE ONLY -- pts_for/pts_against/net_pts/minutes ride along in each
ranking row for context (NOT independently re-verified by claims_validator,
which only recomputes rank/value/n from criteria.formula against the
declared source_files); no gate, no predictive/calibration claim, no
market/$ edge claimed.

NETWORK: zero. Pure pandas over an already-materialized parquet.

CLI:
    python -m scripts.platformkit.intel_validation.wnba_lineup_exposure_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_wnba.atlas_extract_lineup import MIN_GAMES_LINEUP
from scripts.platformkit.intel_validation.wnba_claims import _full_population_ranking, _rel

REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_team_lineup_exposure.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "wnba_lineup_exposure_claims.jsonl"

SEASON_WINDOW = "2026"


def build_lineup_exposure_claim(src: Path = _SRC) -> dict[str, Any]:
    df = pd.read_parquet(src)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="minutes_share", entity_key="lineup_id", entity_col="lineup_id",
        name_col="lineup_player_names", min_n_col="n_games", min_n=MIN_GAMES_LINEUP,
    )
    # ride-along context (not checked by the validator's rank/value/n compare)
    context = df.set_index("lineup_id")[["team_id", "pts_for", "pts_against", "net_pts", "minutes"]]
    for row in ranking:
        if row["lineup_id"] not in context.index:
            continue
        c = context.loc[row["lineup_id"]]
        # team_id rides a mixed-dtype row selection (int64 team_id alongside
        # float64 pts columns upcasts the whole Series to float64, so a bare
        # str() prints "160....0" for a real numeric id); only round-trip
        # through int when it IS a float-ified int -- a non-numeric team_id
        # (e.g. a test fixture's "T1") stays a plain string.
        tid = c["team_id"]
        row["team_id"] = str(int(tid)) if isinstance(tid, float) and tid.is_integer() else str(tid)
        row["pts_for"] = round(float(c["pts_for"]), 4)
        row["pts_against"] = round(float(c["pts_against"]), 4)
        row["net_pts"] = round(float(c["net_pts"]), 4)
        row["minutes"] = round(float(c["minutes"]), 4)

    return {
        "claim_id": f"wnba_lineup_exposure_minutes_share_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            "Which WNBA 5-player lineups see the largest share of their "
            f"team's tracked minutes (full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "minutes_share",
            "formula": "minutes_share",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games": MIN_GAMES_LINEUP},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "lineup_id",
        },
        "ranking": ranking,
        "source_files": [_rel(src)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "minutes_share = (minutes this exact 5-man lineup shared the floor together) / "
            "(team's total tracked minutes across all lineups), from "
            "data/cache/atlas_wnba_team_lineup_exposure.parquet (season-2026 168-game CDN "
            "backfill corpus, full-game substitution-replay stint reconstruction: "
            "domains/basketball_wnba/lineup_stints.py + atlas_extract_lineup.py).",
            f"min_sample floor n_games>={MIN_GAMES_LINEUP} -- excludes one-off garbage-time "
            "5-man combos that only ever shared the floor in a single game.",
            "pts_for/pts_against/net_pts/minutes ride along per ranking row for context; these "
            "are NOT independently re-verified by claims_validator (only rank/value/n against "
            "criteria.formula are recomputed).",
            "FULL POPULATION: every lineup clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE lineup-exposure aggregate ONLY -- NOT a gate, NOT a predictive/"
            "calibration claim, no market/$ edge claimed. First non-NBA sport with lineup "
            "data on this platform (opens the lineup class in a second sport).",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit WNBA lineup-exposure DESCRIPTIVE ranking claim")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [build_lineup_exposure_claim()]
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
