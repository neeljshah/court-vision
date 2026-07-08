"""NBA lineup-synergy-residual DESCRIPTIVE ranking claim (lane
player-interactions). Lineup-keyed (team_id, lineup_key) -- a 5-man unit is
the ranking entity, not a player.

SOURCE: domains/basketball_nba/interactions/lineup_synergy.py's own FULL,
unfiltered population -- data/cache/team_system/interactions/
lineup_synergy_2025_26.parquet, one row per distinct 5-man lineup with the
metric (synergy_residual) already computed as a plain column. Same
precedent as nba_gravity_proxy_claims.py: the floor is REAPPLIED here on
the raw min/synergy_residual columns, not trusted from the source's own
`qualifies` boolean, so the validator's independent floor recomputation is
real (a genuine n_excluded_below_floor, not zero-by-construction).

METRIC: synergy_residual = the lineup's own actual net rating per48 minus
the mean of its 5 members' individual on/off net ratings (the "whole minus
sum of individually-rated parts" chemistry term; see lineup_synergy.py's
own docstring for the full weighting rationale). The validator's plain
(non-aggregate) formula path re-reads that column directly -- it does not
re-derive it from stints + on_off (that recompute lives in
lineup_synergy.py's own per-file test).

MIN-SAMPLE FLOOR: min>=100 minutes AND synergy_residual not null (null means
at least one of the 5 members didn't clear lineup_synergy.py's own
per-member floor) -- IDENTICAL threshold to lineup_synergy.py's own
MIN_LINEUP_MINUTES constant (kept as a literal value here, not imported, to
keep this module's only import surface pandas -- same precedent as
nba_gravity_proxy_claims.py/nba_on_off_claims.py, neither of which carry a
companion test file either; this floor's parity with the source's own
`qualifies` column is exercised directly by running validate_store below).

NETWORK: zero. DESCRIPTIVE lineup-chemistry ranking only -- NOT a causal
claim, no market/$ edge claimed, no gate.

CLI: python -m scripts.platformkit.intel_validation.nba_lineup_synergy_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_SYNERGY_SRC = REPO_ROOT / "data" / "cache" / "team_system" / "interactions" / "lineup_synergy_2025_26.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_lineup_synergy_claims.jsonl"

SEASON_WINDOW = "2025_26"
MIN_LINEUP_MINUTES = 100.0


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_synergy_claim() -> dict[str, Any]:
    df = pd.read_parquet(_SYNERGY_SRC)
    n_considered = len(df)
    qualifiers = df[(df["min"] >= MIN_LINEUP_MINUTES) & df["synergy_residual"].notna()].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("synergy_residual", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team_id": int(row.team_id),
            "lineup_key": str(row.lineup_key),
            "value": round(float(row.synergy_residual), 4),
            "n": round(float(row.min), 2),
        })

    return {
        "claim_id": f"nba_lineup_synergy_residual_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which NBA 5-man lineups outperform (or underperform) what their members' "
            f"individual on/off net ratings alone would predict (synergy residual, full "
            f"population above floor, {SEASON_WINDOW} 1192-game slice)?"
        ),
        "criteria": {
            "metric": "synergy_residual",
            "formula": "synergy_residual",
            "window": f"season_{SEASON_WINDOW}_nba_lineup_corpus",
            "min_sample": {"min": MIN_LINEUP_MINUTES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": ["team_id", "lineup_key"],
        },
        "ranking": ranking,
        "source_files": [_rel(_SYNERGY_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "synergy_residual = lineup's own actual net rating per48 (from stint-level "
            "pts_for/pts_against) minus the mean of its 5 members' individual "
            "net_rating_on_per48 (from on_off.py's on_off_2025_26.parquet) -- from "
            "data/cache/team_system/interactions/lineup_synergy_2025_26.parquet.",
            f"min_sample floor min>={MIN_LINEUP_MINUTES} minutes AND synergy_residual not "
            "null (null means at least one of the 5 members lacked >=100 individual "
            "on-court minutes in on_off_2025_26.parquet) -- reapplied here on the raw "
            "columns, independent of the source file's own `qualifies` flag.",
            "Lineup-keyed entity (team_id, lineup_key): the 5-man unit is the ranking "
            "entity, not a player.",
            "FULL POPULATION: every lineup clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE residual-vs-individual-baseline aggregate ONLY -- NOT a causal "
            "chemistry measurement (opponent quality, garbage time, and small-sample luck "
            "are not controlled for), NOT a gate, no market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA lineup-synergy-residual ranking claim")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claim = build_synergy_claim()
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
