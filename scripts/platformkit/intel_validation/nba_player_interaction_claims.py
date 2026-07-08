"""NBA player-interaction TOP-N ranking claims (lane player-interactions):
"how much does X affect Y" across all THREE seasons on disk, for the three
interaction primitives in domains/basketball_nba/interactions/:

  pairwise_gravity   -- pairwise_onoff.py's efg_delta (directed X,Y pair:
                        does Y's presence lift X's own eFG?)
  lineup_synergy_top -- lineup_synergy.py's synergy_residual (5-man unit
                        actual net rtg/48 minus talent-sum expectation) --
                        TOP-N subset of the SAME source nba_lineup_synergy_
                        claims.py already ranks in full; different claim_id
                        namespace, no conflict.
  usage_redistribution -- share_delta (who absorbs a high-usage player's
                        shot share when he sits) -- brand-new claim, no
                        prior producer.

TOP-N=50 per metric per season (declared below, not the full population --
see nba_lineup_synergy_claims.py/nba_gravity_proxy_claims.py for the
full-population precedent this deliberately does NOT duplicate).

N-FLOOR (declared before running, per task spec): >=100 "possessions" or
>=100 shots joint exposure. Concretely, per metric:
  pairwise_gravity: min_together>=200 AND min_x_without_y>=100 (minutes) --
    already baked into pairwise_onoff.py's own output (it only ever WRITES
    qualifying rows), so this floor is a strict superset of the declared
    100-possession minimum; reapplied here as a real min_sample so the
    validator's independent floor recompute is honest, not zero-by-
    vacuous-construction.
  lineup_synergy_top: lineup min>=100 minutes (IDENTICAL floor + precedent
    as nba_lineup_synergy_claims.py -- that source parquet IS the full,
    unfiltered population).
  usage_redistribution: teammate_fga_joint>=100 (fga_with+fga_without) --
    the raw shot-count column usage_redistribution.py now carries for
    exactly this purpose.

NEGATIVE PLACEHOLDER IDS: some seasons' stint reconstruction fills an
unresolved lineup slot with a negative sentinel id (worst in 2023-24, ~6%
of roster slots per pbp_lineups.py's build_team_stints; present at lower
rates in 2024-25/2025-26 too -- verified, not season-specific). Folded
into min_sample itself (player_x>=0, player_y>=0, min_member_id>=0) so the
exclusion is REAL and validator-reproducible, not a silent pre-filter the
validator can't see.

Each ranking row carries a `text` field stating the effect SIZE and n in
plain language (task spec), in addition to the standard rank/entity/value/n
fields every other producer in this lane emits.

NETWORK: zero. DESCRIPTIVE effect-size ranking only -- NOT causal, NOT a
gate, no market/$ edge claimed.

CLI: python -m scripts.platformkit.intel_validation.nba_player_interaction_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_INTERACTIONS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "interactions"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_player_interaction_claims.jsonl"

SEASONS = ["2025_26", "2024_25", "2023_24"]
TOP_N = 50


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _season_label(season: str) -> str:
    return season.replace("_", "-")


def _apply_floor(df: pd.DataFrame, min_sample: dict[str, Any]) -> tuple[pd.Series, int]:
    """IDENTICAL rule to claims_validator's `_apply_min_sample_floors`: a
    plain per-column >= mask, ANDed. Kept separate from any metric-notna
    filtering so n_excluded_below_floor always matches the validator's own
    (floor-only) recompute, regardless of whether a null metric value ever
    coincides with a floor-passing row."""
    mask = pd.Series(True, index=df.index)
    for col, floor in min_sample.items():
        mask &= df[col] >= floor
    return mask, int((~mask).sum())


def _build_ranking_claim(
    *, claim_id: str, question: str, metric_col: str, entity_key: list[str],
    min_sample: dict[str, Any], src: Path, season: str, row_fmt, caveats: list[str],
) -> dict[str, Any]:
    df = pd.read_parquet(src)
    n_considered = len(df)
    floor_mask, n_excluded = _apply_floor(df, min_sample)
    qualifiers = df[floor_mask & df[metric_col].notna()].copy()
    qualifiers = qualifiers.sort_values(metric_col, ascending=False).head(TOP_N).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        entry = {"rank": i}
        for k in entity_key:
            v = getattr(row, k)
            entry[k] = str(v) if k == "lineup_key" else int(v)
        value = round(float(getattr(row, metric_col)), 4)
        n_val, text = row_fmt(row, value, season)
        entry["value"] = value
        entry["n"] = n_val
        entry["text"] = text
        ranking.append(entry)

    return {
        "claim_id": f"{claim_id}_{season}",
        "kind": "ranking",
        "question": question.format(season=_season_label(season)),
        "criteria": {
            "metric": metric_col,
            "formula": metric_col,
            "window": f"season_{season}_nba_lineup_corpus",
            "min_sample": min_sample,
            "direction": "desc",
            "value_precision": 4,
            "entity_key": entity_key,
        },
        "ranking": ranking,
        "source_files": [_rel(src)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": caveats,
    }


def _pairwise_row(row: Any, value: float, season: str) -> tuple[float, str]:
    n_val = round(float(min(row.min_together, row.min_x_without_y)), 2)
    text = (
        f"{row.player_y_name} on-court lifts {row.player_x_name}'s eFG by {value * 100:+.1f}pp "
        f"over {_season_label(season)}, n={n_val:.0f} min joint exposure "
        f"({row.x_efg_with_y_on:.3f} vs {row.x_efg_without_y:.3f})."
    )
    return n_val, text


def _synergy_row(row: Any, value: float, season: str) -> tuple[float, str]:
    n_val = float(row.min)
    text = (
        f"Lineup [{row.lineup_key}] (team {int(row.team_id)}) beats its individual-talent-sum "
        f"expectation by {value:+.1f} net rtg/48 over {_season_label(season)}, n={n_val:.0f} "
        f"lineup-minutes (actual {row.net_per48:.1f} vs expected {row.expected_net_per48:.1f})."
    )
    return n_val, text


def _usage_row(row: Any, value: float, season: str) -> tuple[float, str]:
    n_val = float(row.teammate_fga_joint)
    text = (
        f"When {row.player_name} sits, {row.teammate_name} absorbs {value * 100:+.1f}pp more of the "
        f"team's shot share over {_season_label(season)}, n={n_val:.0f} shots joint exposure "
        f"(eFG {row.efg_with} -> {row.efg_without})."
    )
    return n_val, text


def build_claims_for_season(season: str) -> list[dict[str, Any]]:
    claims = []
    claims.append(_build_ranking_claim(
        claim_id="nba_pairwise_gravity_top50",
        question="Which NBA directed teammate pairs show the strongest on-court eFG lift ({season}, top 50)?",
        metric_col="efg_delta",
        entity_key=["team_id", "player_x", "player_y"],
        min_sample={"min_together": 200.0, "min_x_without_y": 100.0, "player_x": 0, "player_y": 0},
        src=_INTERACTIONS_DIR / f"pairwise_onoff_{season}.parquet",
        season=season,
        row_fmt=_pairwise_row,
        caveats=[
            "efg_delta = X's own eFG% with Y on the floor minus X's own eFG% with Y off, holding X on "
            "the floor fixed (directed pair: (X,Y) != (Y,X)) -- from pairwise_onoff.py.",
            "min_sample floor min_together>=200 AND min_x_without_y>=100 minutes is ALREADY baked into "
            "the source file (it only ever writes qualifying pairs) -- reapplied here as a real "
            "min_sample so n_excluded_below_floor is honestly recomputable, not zero by vacuous "
            "construction; the ADDITIONAL player_x>=0/player_y>=0 floor drops pairs touching an "
            "unresolved negative-placeholder roster id (present in all 3 seasons at varying rates).",
            "TOP 50 by efg_delta only -- NOT the full qualifying population.",
            "DESCRIPTIVE on/off eFG association ONLY -- NOT causal (opponent quality, shot difficulty, "
            "garbage time not controlled for), NOT a gate, no market/$ edge claimed.",
        ],
    ))
    claims.append(_build_ranking_claim(
        claim_id="nba_lineup_synergy_top50",
        question="Which NBA 5-man lineups outperform their talent-sum expectation the most ({season}, top 50)?",
        metric_col="synergy_residual",
        entity_key=["team_id", "lineup_key"],
        min_sample={"min": 100.0, "min_member_id": 0},
        src=_INTERACTIONS_DIR / f"lineup_synergy_{season}.parquet",
        season=season,
        row_fmt=_synergy_row,
        caveats=[
            "synergy_residual = lineup's own actual net rtg/48 minus the mean of its 5 members' "
            "individual on/off net ratings -- from lineup_synergy.py's FULL unfiltered population.",
            "min_sample floor min>=100 lineup-minutes (identical to nba_lineup_synergy_claims.py); "
            "min_member_id>=0 additionally drops lineups containing an unresolved negative-placeholder "
            "roster id.",
            "TOP 50 by synergy_residual only -- see nba_lineup_synergy_claims.py for the FULL "
            "population ranking of this same source.",
            "DESCRIPTIVE residual-vs-baseline aggregate ONLY -- NOT causal chemistry, NOT a gate, "
            "no market/$ edge claimed.",
        ],
    ))
    claims.append(_build_ranking_claim(
        claim_id="nba_usage_redistribution_top50",
        question="Which NBA teammates absorb the most shot-share when a high-usage teammate sits ({season}, top 50)?",
        metric_col="share_delta",
        entity_key=["player_id", "team_id", "teammate_id"],
        min_sample={"teammate_fga_joint": 100},
        src=_INTERACTIONS_DIR / f"usage_redistribution_{season}.parquet",
        season=season,
        row_fmt=_usage_row,
        caveats=[
            "share_delta = teammate's own FGA share of team shots while the high-usage player is OFF "
            "the floor minus while he is ON it (positive = teammate absorbs more shots when he sits) "
            "-- from usage_redistribution.py.",
            "min_sample floor teammate_fga_joint (fga_with+fga_without)>=100 -- both sides of the "
            "split need real teammate shot volume, not just the high-usage player's own 200/50-min "
            "with/without floor (already baked into which player_id rows exist at all).",
            "TOP 50 by share_delta only -- NOT the full qualifying population.",
            "Injury-impact PRIMITIVE ONLY (no injury data read here, just the on/off shot-diet split) "
            "-- DESCRIPTIVE, NOT causal, NOT a gate, no market/$ edge claimed.",
        ],
    ))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA player-interaction TOP-50 ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default="all", choices=[*SEASONS, "all"])
    args = parser.parse_args(argv)

    seasons = SEASONS if args.season == "all" else [args.season]
    claims = [c for s in seasons for c in build_claims_for_season(s)]
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        print(
            f"{claim['claim_id']}: n_considered={claim['n_considered']} "
            f"n_excluded_below_floor={claim['n_excluded_below_floor']} n_ranked={len(claim['ranking'])} "
            f"top1={json.dumps(claim['ranking'][0]) if claim['ranking'] else None}"
        )
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
