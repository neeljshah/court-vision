"""Soccer-intl tournament-context DESCRIPTIVE claims. SOURCE:
data/domains/soccer_intl/results.parquet (49,477 rows, cols date/tournament/
neutral -- GAME-DATED). Splits home-win/draw rate by 2x2x2 context:
competitive (tournament != "Friendly") x neutral venue x era (pre/post 2000).

Builds ONE derived per-match SOURCE parquet (group, is_home_win, is_draw,
date) under data/cache/intel_claims/, then two ranking claims over
entity_key=group (up to 8 groups): home_win_rate, draw_rate.

DESCRIPTIVE only: no market/$ edge claimed, not a betting signal.

CLI: python -m domains.soccer.claims_tournament_context
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_RESULTS = REPO_ROOT / "data" / "domains" / "soccer_intl" / "results.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "soccer_tournament_context_claims.jsonl"

MIN_N = 100  # min matches per context group to rank it


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def build_source(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    raw = df if df is not None else pd.read_parquet(_RESULTS)
    out = raw[["date", "home_score", "away_score", "tournament", "neutral"]].copy()
    competitive = out["tournament"] != "Friendly"
    era = out["date"].dt.year >= 2000
    out["group"] = (
        competitive.map({True: "competitive", False: "friendly"}) + "_"
        + out["neutral"].map({True: "neutral", False: "home_venue"}) + "_"
        + era.map({True: "post2000", False: "pre2000"})
    )
    out["is_home_win"] = (out["home_score"] > out["away_score"]).astype(int)
    out["is_draw"] = (out["home_score"] == out["away_score"]).astype(int)
    return out[["group", "is_home_win", "is_draw", "date"]].reset_index(drop=True)


def _rank(source: pd.DataFrame, value_col: str) -> tuple[list[dict], int, int]:
    grouped = source.groupby("group")[value_col]
    n = grouped.count()
    value = grouped.mean()
    table = pd.DataFrame({"n": n, "value": value}).reset_index()
    n_considered = len(table)
    qualifiers = table[table["n"] >= MIN_N].sort_values("value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(qualifiers)
    ranking = [
        {"rank": i, "group": row.group, "value": round(float(row.value), 4), "n": int(row.n)}
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return ranking, n_considered, n_excluded


def _claim(claim_id: str, question: str, metric: str, value_col: str,
           src_path: Path, ranking: list[dict], n_considered: int, n_excluded: int) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric,
            "formula": f"mean({value_col})",
            "aggregate": {"group_by": "group", "derived": {"n": f"count({value_col})"}},
            "window": "soccer_intl_full_corpus_1872_2026",
            "min_sample": {"n": MIN_N},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "group",
        },
        "ranking": ranking,
        "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "group = (competitive|friendly) x (neutral|home_venue) x (pre2000|post2000), where "
            "competitive means tournament != 'Friendly', era split on match year >= 2000.",
            f"min_sample floor n>={MIN_N} matches per group.",
            "DESCRIPTIVE split only -- not causal (no strength-of-team adjustment), no market/$ edge claimed.",
        ],
    }


def build_claims(out_dir: Path = _OUT_DIR) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = build_source()
    src_path = out_dir / "soccer_tournament_context_source.parquet"
    source.to_parquet(src_path, index=False)

    claims = []
    for metric, col, label in (
        ("home_win_rate", "is_home_win", "home win rate"),
        ("draw_rate", "is_draw", "draw rate"),
    ):
        ranking, n_considered, n_excluded = _rank(source, col)
        claims.append(_claim(
            f"soccer_intl_tournament_context_{metric}",
            f"How does {label} vary by competitive-vs-friendly x neutral-venue x era "
            f"(soccer-intl 1872-2026 corpus)?",
            metric, col, src_path, ranking, n_considered, n_excluded,
        ))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit soccer-intl tournament-context claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_claims()
    out_path = write_claims(claims, Path(args.output))

    print(f"wrote {len(claims)} claims -> {out_path}")
    for claim in claims:
        print(f"{claim['claim_id']}: n_considered={claim['n_considered']} "
              f"n_excluded_below_floor={claim['n_excluded_below_floor']} n_ranked={len(claim['ranking'])}")
        for row in claim["ranking"][:3]:
            print(f"  sample: {json.dumps(row)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
