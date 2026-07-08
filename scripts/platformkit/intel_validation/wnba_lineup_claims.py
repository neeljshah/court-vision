"""WNBA lineup-intelligence TOP-25 ranking claims (lane
lineup-reconstruction-keystone, second sport): on-court net impact, gravity
proxy, and lineup spacing, over data/cache/team_system/lineups/
{on_off,lineup_spacing}_wnba_2026.parquet (168 games, schema-identical to
the NBA equivalents this module mirrors: nba_on_off_claims.py,
nba_gravity_proxy_claims.py, nba_player_interaction_claims.py's generic
TOP-N + negative-id-floor ranking builder).

on_off + gravity BOTH read the full, unfiltered on_off_wnba_2026.parquet
(one row per player_id/team_id) -- gravity_proxy is computed here as
teammate_efg_on - teammate_efg_off rather than read from the ALREADY
floor-filtered gravity_proxy_wnba_2026.parquet, so the validator's floor
re-application stays honest (non-vacuous n_excluded), same precedent as
nba_gravity_proxy_claims.py. spacing reads lineup_spacing_wnba_2026.parquet
(lineup-keyed team_id/lineup_key, no player_id column -- the negative-id
floor below does not apply; zero '-' chars in any lineup_key, verified).

FLOORS (task spec): on/off min_on>=300; gravity min_on>=300 AND
teammate_fga_on/off>=200 (== nba_gravity_proxy_claims.py); spacing
n_shots>=50. player_id>=0 added to on_off/gravity min_sample to exclude an
unresolved stint-reconstruction sentinel id (seen in NBA corpora; zero in
this WNBA slice, floor kept real for validator honesty regardless).

WINDOW: game-dated, from lineup_matchups_wnba_2026.parquet's game_date
(min=2026-04-25, max=2026-07-03, 168 games, verified) -- hardcoded literal,
same precedent as nba_on_off_claims.py's SEASONS dict.

NETWORK: zero. DESCRIPTIVE rankings only -- NOT predictive/causal, NOT a
gate, no market/$ edge claimed.

CLI: python -m scripts.platformkit.intel_validation.wnba_lineup_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "wnba_lineup_claims.jsonl"

CORPUS = "168-game 2026-04-25_to_2026-07-03"
WINDOW = "wnba_2026_2026-04-25_to_2026-07-03"
TOP_N = 25


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _apply_floor(df: pd.DataFrame, min_sample: dict[str, Any]) -> tuple[pd.Series, int]:
    """IDENTICAL rule to claims_validator's `_apply_min_sample_floors`: a
    plain per-column >= mask, ANDed."""
    mask = pd.Series(True, index=df.index)
    for col, floor in min_sample.items():
        mask &= df[col] >= floor
    return mask, int((~mask).sum())


def _build_ranking_claim(
    *, claim_id: str, question: str, metric_col: str, formula: str,
    entity_key: list[str], min_sample: dict[str, Any], src: Path,
    row_fmt: Callable[[Any, float], tuple[float, str]], caveats: list[str],
    compute: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> dict[str, Any]:
    df = pd.read_parquet(src)
    n_considered = len(df)
    if compute is not None:
        df = compute(df)
    floor_mask, n_excluded = _apply_floor(df, min_sample)
    qualifiers = df[floor_mask & df[metric_col].notna()].copy()
    qualifiers = qualifiers.sort_values(metric_col, ascending=False).head(TOP_N).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        entry: dict[str, Any] = {"rank": i}
        for k in entity_key:
            v = getattr(row, k)
            entry[k] = str(v) if k == "lineup_key" else int(v)
        value = round(float(getattr(row, metric_col)), 4)
        n_val, text = row_fmt(row, value)
        entry["value"] = value
        entry["n"] = n_val
        entry["text"] = text
        ranking.append(entry)

    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric_col,
            "formula": formula,
            "window": WINDOW,
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


def _on_off_row(row: Any, value: float) -> tuple[float, str]:
    n_val = round(float(row.min_on), 2)
    text = (
        f"{row.player_name}'s team outscores opponents by {value:+.2f} pts/48 min while "
        f"they are on the floor over the {CORPUS} WNBA slice, n={n_val:.0f} minutes on."
    )
    return n_val, text


def _gravity_row(row: Any, value: float) -> tuple[float, str]:
    n_val = float(min(row.teammate_fga_on, row.teammate_fga_off))
    text = (
        f"{row.player_name}'s teammates shoot eFG% {value * 100:+.1f}pp better with them on "
        f"the floor vs. off over the {CORPUS} WNBA slice ({row.teammate_efg_on:.3f} vs. "
        f"{row.teammate_efg_off:.3f}), n={n_val:.0f} teammate shot attempts (min of on/off sides)."
    )
    return n_val, text


def _spacing_row(row: Any, value: float) -> tuple[float, str]:
    n_val = float(row.n_shots)
    text = (
        f"Lineup [{row.lineup_key}] (team {int(row.team_id)}) shows a {value:.1f}-unit average "
        f"shot-distance spacing over the {CORPUS} WNBA slice, n={n_val:.0f} shots."
    )
    return n_val, text


def build_on_off_claim() -> dict[str, Any]:
    src = _LINEUPS_DIR / "on_off_wnba_2026.parquet"
    return _build_ranking_claim(
        claim_id="wnba_lineup_net_rating_on_top25_2026",
        question=(
            "Which WNBA players' teams outscore opponents the most per 48 minutes while they "
            f"are on the floor (top 25, {CORPUS} slice)?"
        ),
        metric_col="net_rating_on_per48", formula="net_rating_on_per48",
        entity_key=["player_id", "team_id"],
        min_sample={"min_on": 300.0, "player_id": 0},
        src=src, row_fmt=_on_off_row,
        caveats=[
            "net_rating_on_per48 = (team pts_for - pts_against while this player is on the "
            f"floor) / on-court minutes * 48, from {_rel(src)} (stint-level attribution, "
            f"{CORPUS} WNBA PBP corpus).",
            "min_sample floor min_on>=300 minutes AND player_id>=0 (drops unresolved "
            "negative-placeholder roster ids; zero present in this slice, floor kept real "
            "for validator honesty).",
            "TOP 25 by net_rating_on_per48 only -- NOT the full qualifying population.",
            "DESCRIPTIVE net-rating-while-on-floor aggregate ONLY -- NOT a predictive/causal "
            "claim, NOT a gate, no market/$ edge claimed.",
        ],
    )


def build_gravity_claim() -> dict[str, Any]:
    src = _LINEUPS_DIR / "on_off_wnba_2026.parquet"
    return _build_ranking_claim(
        claim_id="wnba_gravity_proxy_top25_2026",
        question=(
            "Which WNBA players' teammates shoot the best eFG% with them on the floor vs. "
            f"off it (gravity proxy, top 25, {CORPUS} slice)?"
        ),
        metric_col="gravity_proxy", formula="teammate_efg_on - teammate_efg_off",
        entity_key=["player_id", "team_id"],
        min_sample={"min_on": 300.0, "teammate_fga_on": 200, "teammate_fga_off": 200, "player_id": 0},
        src=src, row_fmt=_gravity_row,
        compute=lambda df: df.assign(gravity_proxy=df["teammate_efg_on"] - df["teammate_efg_off"]),
        caveats=[
            "gravity_proxy = teammate eFG% while this player is ON the floor minus teammate "
            f"eFG% while OFF it, from {_rel(src)} ({CORPUS} WNBA PBP corpus). A DESCRIPTIVE "
            "association, not a causal gravity measurement.",
            "min_sample floor min_on>=300 AND teammate_fga_on/off>=200 (identical floors to "
            "nba_gravity_proxy_claims.py) AND player_id>=0 (negative-placeholder exclusion; "
            "zero present in this slice).",
            "TOP 25 by gravity_proxy only -- NOT the full qualifying population.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, no market/$ edge claimed.",
        ],
    )


def build_spacing_claim() -> dict[str, Any]:
    src = _LINEUPS_DIR / "lineup_spacing_wnba_2026.parquet"
    return _build_ranking_claim(
        claim_id="wnba_lineup_spacing_top25_2026",
        question=(
            "Which WNBA 5-man lineups show the widest average shot-distance spacing "
            f"(top 25, {CORPUS} slice)?"
        ),
        metric_col="spacing_mean_dist", formula="spacing_mean_dist",
        entity_key=["team_id", "lineup_key"],
        min_sample={"n_shots": 50},
        src=src, row_fmt=_spacing_row,
        caveats=[
            f"spacing_mean_dist = mean pairwise shot-location distance for this 5-man lineup, "
            f"from {_rel(src)} ({CORPUS} WNBA PBP corpus).",
            "min_sample floor n_shots>=50 -- lineup-keyed entity (team_id, lineup_key), no "
            "player_id column exists on this source so the negative-placeholder-id floor "
            "used by the on/off + gravity claims above does not apply here; verified zero "
            "'-' characters in any lineup_key in this slice.",
            "TOP 25 by spacing_mean_dist only -- NOT the full qualifying population.",
            "DESCRIPTIVE spacing aggregate ONLY -- NOT a predictive/causal claim, NOT a gate, "
            "no market/$ edge claimed.",
        ],
    )


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit WNBA lineup-intelligence TOP-25 ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [build_on_off_claim(), build_gravity_claim(), build_spacing_claim()]
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
