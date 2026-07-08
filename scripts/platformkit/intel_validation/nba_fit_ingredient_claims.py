"""NBA fit-ingredient claims producer (PROGRAM v3 item 2, lane fit-ingredients).

Emits three DESCRIPTIVE (never predictive) ingredient claim families that
compose_fit() in intel_query/ask.py joins into a SCOUTING fit answer. Each
family is a `kind: "ranking"` claim row in the SAME contract shape the
sibling producers use (see tennis_hold_claims.py), so the independent
claims_validator.py VERIFIES each one with zero code sharing. Per-ingredient
detail (definition, floor, provenance) lives in each build_*_claim()'s own
docstring/caveats in nba_fit_ingredient_builders.py (split out to stay under
the 300 LOC/file rail) -- summary:

  (a) player archetype/attribute profile: data/cache/team_system/
      player_roles.parquet, FULL POPULATION above stated floor MIN_MPG.
      Non-aggregate validator path, entity_key=pid.
  (b) team scheme identity: data/cache/team_system/scheme_coverage.parquet
      (a REAL team_system cache artifact this lane only READS; its builder
      script stays untouched), row_type=="team_scheme", all 30 teams.
      Non-aggregate validator path, entity_key=team.
  (c) role vacancy per team x posgroup: DERIVED from raw player_boxscores
      joined to player_roles for posgroup; see build_role_vacancy_claim's
      docstring for the vacancy_share definition. Aggregate validator path
      (safe_formula.evaluate_group_formula), entity_key=team, group_by=team.

  Window stamps for all three: see nba_fit_ingredient_builders.py's
  ARCHETYPE_WINDOW / SCHEME_IDENTITY_SEASON / ROLE_VACANCY_SEASON constants
  for the per-family vintage evidence.

LEAK DISCIPLINE: player_roles/scheme_coverage are season-to-date descriptive
aggregates already on disk -- a SCOUTING composition, not an in-game/
pregame predictive feature. player_boxscores rows are completed-game box
scores; the pts-per-minute split is a plain season aggregate, no leak.

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE / SCOUTING ONLY -- NO PREDICTIVE OR MARKET-EDGE CLAIM.

CLI:
    python -m scripts.platformkit.intel_validation.nba_fit_ingredient_claims
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.platformkit.intel_validation.nba_fit_ingredient_builders import (
    _ascii_summary,
    build_archetype_claim,
    build_role_vacancy_claim,
    build_scheme_identity_claim,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_fit_ingredient_claims.jsonl"


def build_all_claims() -> list[dict[str, Any]]:
    return [
        build_archetype_claim(),
        build_scheme_identity_claim(),
        build_role_vacancy_claim(),
    ]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA fit-ingredient claims (a/b/c)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        top1 = _ascii_summary(c["ranking"][0] if c["ranking"] else None)
        print(
            f"{c['claim_id']}: n_considered={c['n_considered']} "
            f"n_excluded_below_floor={c['n_excluded_below_floor']} rows={len(c['ranking'])} "
            f"top1={top1}"
        )
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
