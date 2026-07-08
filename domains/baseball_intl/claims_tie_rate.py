"""NPB/KBO cross-league tie-rate DESCRIPTIVE claims. SOURCE: data/domains/npb/
npb_results.parquet + data/domains/kbo/kbo_results.parquet (both have a
'tied' col, plus date/home_score/away_score -- GAME-DATED). Three metrics,
ranked over entity_key=league ("npb"/"kbo"):

  - tie_rate:                    mean(tied) over ALL games.
  - run_diff1_share:             mean(|home_score - away_score| == 1) over ALL games.
  - home_win_share_decided:      mean(home_win) over games with tied==False only
                                  (the "home/away split" -- decided-game home-win share).

Builds TWO derived SOURCE parquets under data/cache/intel_claims/ (all-games,
and decided-games-only) since the third metric's population excludes ties.

DESCRIPTIVE only: no market/$ edge claimed, not a betting signal.

CLI: python -m domains.baseball_intl.claims_tie_rate
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_NPB_RESULTS = REPO_ROOT / "data" / "domains" / "npb" / "npb_results.parquet"
_KBO_RESULTS = REPO_ROOT / "data" / "domains" / "kbo" / "kbo_results.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "baseball_intl_tie_rate_claims.jsonl"

MIN_N = 100  # min games per league to rank it


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _load_raw(npb_df: Optional[pd.DataFrame] = None, kbo_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    npb = (npb_df if npb_df is not None else pd.read_parquet(_NPB_RESULTS)).copy()
    kbo = (kbo_df if kbo_df is not None else pd.read_parquet(_KBO_RESULTS)).copy()
    npb["league"], kbo["league"] = "npb", "kbo"
    return pd.concat([npb, kbo], ignore_index=True)


def build_all_games_source(npb_df: Optional[pd.DataFrame] = None, kbo_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    df = _load_raw(npb_df, kbo_df)
    df["is_tied"] = df["tied"].astype(int)
    df["is_rundiff1"] = ((df["home_score"] - df["away_score"]).abs() == 1).astype(int)
    return df[["league", "is_tied", "is_rundiff1", "date"]].reset_index(drop=True)


def build_decided_source(npb_df: Optional[pd.DataFrame] = None, kbo_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    df = _load_raw(npb_df, kbo_df)
    decided = df[~df["tied"]].copy()
    decided["is_home_win"] = decided["home_win"].astype(int)
    return decided[["league", "is_home_win", "date"]].reset_index(drop=True)


def _rank(source: pd.DataFrame, value_col: str) -> tuple[list[dict], int, int]:
    grouped = source.groupby("league")[value_col]
    n = grouped.count()
    value = grouped.mean()
    table = pd.DataFrame({"n": n, "value": value}).reset_index()
    n_considered = len(table)
    qualifiers = table[table["n"] >= MIN_N].sort_values("value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(qualifiers)
    ranking = [
        {"rank": i, "league": row.league, "value": round(float(row.value), 4), "n": int(row.n)}
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return ranking, n_considered, n_excluded


def _claim(claim_id: str, question: str, metric: str, value_col: str,
           src_path: Path, ranking: list[dict], n_considered: int, n_excluded: int, caveat: str) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric,
            "formula": f"mean({value_col})",
            "aggregate": {"group_by": "league", "derived": {"n": f"count({value_col})"}},
            "window": "npb_kbo_full_corpus",
            "min_sample": {"n": MIN_N},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "league",
        },
        "ranking": ranking,
        "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [caveat, f"min_sample floor n>={MIN_N} games per league.",
                    "DESCRIPTIVE split only -- not causal, no market/$ edge claimed."],
    }


def build_claims(out_dir: Path = _OUT_DIR) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_games = build_all_games_source()
    all_src = out_dir / "baseball_intl_tie_rate_all_games_source.parquet"
    all_games.to_parquet(all_src, index=False)
    decided = build_decided_source()
    decided_src = out_dir / "baseball_intl_tie_rate_decided_source.parquet"
    decided.to_parquet(decided_src, index=False)

    claims = []
    ranking, n_considered, n_excluded = _rank(all_games, "is_tied")
    claims.append(_claim(
        "baseball_intl_tie_rate", "How does tie rate differ between NPB and KBO?",
        "tie_rate", "is_tied", all_src, ranking, n_considered, n_excluded,
        "tie_rate = mean(tied) over ALL games (npb_results.parquet/kbo_results.parquet own 'tied' col).",
    ))
    ranking, n_considered, n_excluded = _rank(all_games, "is_rundiff1")
    claims.append(_claim(
        "baseball_intl_run_diff1_share", "How does the share of 1-run-differential games differ between NPB and KBO?",
        "run_diff1_share", "is_rundiff1", all_src, ranking, n_considered, n_excluded,
        "run_diff1_share = mean(|home_score - away_score| == 1) over ALL games (tied games have diff=0, excluded by construction).",
    ))
    ranking, n_considered, n_excluded = _rank(decided, "is_home_win")
    claims.append(_claim(
        "baseball_intl_home_win_share_decided",
        "Among decided (non-tied) games, how does home-win share differ between NPB and KBO?",
        "home_win_share_decided", "is_home_win", decided_src, ranking, n_considered, n_excluded,
        "home_win_share_decided = mean(home_win) over games with tied==False only (ties removed from the population).",
    ))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NPB/KBO tie-rate conditioning claims")
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
