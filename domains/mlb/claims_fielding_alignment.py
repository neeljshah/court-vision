"""MLB fielding-alignment DESCRIPTIVE claims (batter-side x infield-alignment
splits). SOURCE: data/cache/statcast/savant_full__{season}.parquet
(if_fielding_alignment/of_fielding_alignment cols, per-pitch statcast, game_date
present -- GAME-DATED). Two metrics per season, each its own ranking claim
over entity_key=split_group ("<stand>_<if_fielding_alignment>", e.g. "L_Standard"):

  - babip:  hits / balls-in-play, home runs excluded from both (standard
            BABIP convention -- a ball leaving the park is not a fielding play).
  - xwoba_contact: mean(estimated_woba_using_speedangle) over ALL batted
            balls (bb_type not null), home runs included (xwOBA-on-contact
            is defined over all contact, not just in-play outs/hits).

Each metric writes its own derived per-batted-ball SOURCE parquet under
data/cache/intel_claims/ (one row per batted ball, split_group + the raw
ingredient column + game_date) -- the validator's aggregate recompute reads
THIS file, not the raw savant parquet, so the population is exactly what was
ranked (same precedent as nba_lineup_synergy_claims.py's derived-table source).

DESCRIPTIVE only: no market/$ edge claimed, not a betting signal.

CLI: python -m domains.mlb.claims_fielding_alignment
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_STATCAST_DIR = REPO_ROOT / "data" / "cache" / "statcast"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_fielding_alignment_claims.jsonl"

SEASONS = ["2023", "2024"]
MIN_N = 30  # min batted balls per split_group to rank it


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")  # test out_dir outside the repo (tmp_path)


def _split_group(df: pd.DataFrame) -> pd.Series:
    return df["stand"].astype(str) + "_" + df["if_fielding_alignment"].astype(str).str.replace(" ", "_")


def _load_raw(season: str) -> pd.DataFrame:
    return pd.read_parquet(_STATCAST_DIR / f"savant_full__{season}.parquet")


def _build_babip_source(df: pd.DataFrame) -> pd.DataFrame:
    """One row per non-HR ball in play: split_group, is_hit (0/1), game_date."""
    bip = df[df["bb_type"].notna() & (df["events"] != "home_run")].copy()
    bip["split_group"] = _split_group(bip)
    bip["is_hit"] = bip["events"].isin(["single", "double", "triple"]).astype(int)
    return bip[["split_group", "is_hit", "game_date"]].reset_index(drop=True)


def _build_xwoba_source(df: pd.DataFrame) -> pd.DataFrame:
    """One row per batted ball (HR included) with a non-null xwOBA value."""
    contact = df[df["bb_type"].notna() & df["estimated_woba_using_speedangle"].notna()].copy()
    contact["split_group"] = _split_group(contact)
    contact = contact.rename(columns={"estimated_woba_using_speedangle": "xwoba"})
    return contact[["split_group", "xwoba", "game_date"]].reset_index(drop=True)


def _rank(source: pd.DataFrame, value_col: str, agg: str) -> tuple[list[dict], int, int]:
    """agg='mean' or 'sum'/'count' ratio -- here always mean(value_col).
    Returns (ranking, n_considered, n_excluded_below_floor)."""
    grouped = source.groupby("split_group")[value_col]
    n = grouped.count()
    value = grouped.mean() if agg == "mean" else grouped.sum() / n
    table = pd.DataFrame({"n": n, "value": value}).reset_index()
    n_considered = len(table)
    qualifiers = table[table["n"] >= MIN_N].sort_values("value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(qualifiers)
    ranking = [
        {"rank": i, "split_group": row.split_group, "value": round(float(row.value), 4), "n": int(row.n)}
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return ranking, n_considered, n_excluded


def _claim(
    claim_id: str, question: str, metric: str, formula: str, src_path: Path,
    ranking: list[dict], n_considered: int, n_excluded: int, caveats: list[str],
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric,
            "formula": formula,
            "aggregate": {"group_by": "split_group", "derived": {"n": f"count({formula[5:-1]})"}},
            "window": src_path.stem,
            "min_sample": {"n": MIN_N},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "split_group",
        },
        "ranking": ranking,
        "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": caveats,
    }


def build_babip_claim(season: str, df_raw: Optional[pd.DataFrame] = None, out_dir: Path = _OUT_DIR) -> dict[str, Any]:
    df = df_raw if df_raw is not None else _load_raw(season)
    source = _build_babip_source(df)
    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = out_dir / f"mlb_fielding_alignment_babip_source_{season}.parquet"
    source.to_parquet(src_path, index=False)
    ranking, n_considered, n_excluded = _rank(source, "is_hit", "mean")
    return _claim(
        f"mlb_babip_alignment_{season}",
        f"MLB {season}: BABIP by batter side x infield alignment (shift vs standard)?",
        "babip", "mean(is_hit)", src_path, ranking, n_considered, n_excluded,
        [
            "BABIP = hits (single/double/triple) / non-HR balls in play, home runs excluded from "
            "both numerator and denominator (standard convention -- a HR is not a fielding chance).",
            f"min_sample floor n>={MIN_N} non-HR balls in play per split_group.",
            "split_group = batter stand (L/R) x if_fielding_alignment (Standard/Infield_shade/Strategic).",
            "DESCRIPTIVE split only -- not causal (opponent/park/count context not controlled for), "
            "no market/$ edge claimed.",
        ],
    )


def build_xwoba_claim(season: str, df_raw: Optional[pd.DataFrame] = None, out_dir: Path = _OUT_DIR) -> dict[str, Any]:
    df = df_raw if df_raw is not None else _load_raw(season)
    source = _build_xwoba_source(df)
    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = out_dir / f"mlb_fielding_alignment_xwoba_source_{season}.parquet"
    source.to_parquet(src_path, index=False)
    ranking, n_considered, n_excluded = _rank(source, "xwoba", "mean")
    return _claim(
        f"mlb_xwoba_contact_alignment_{season}",
        f"MLB {season}: xwOBA-on-contact by batter side x infield alignment (shift vs standard)?",
        "xwoba_contact", "mean(xwoba)", src_path, ranking, n_considered, n_excluded,
        [
            "xwoba_contact = mean(estimated_woba_using_speedangle) over ALL batted balls "
            "(bb_type not null, home runs included -- xwOBA-on-contact is defined over all contact).",
            f"min_sample floor n>={MIN_N} batted balls with a non-null xwOBA value per split_group.",
            "split_group = batter stand (L/R) x if_fielding_alignment (Standard/Infield_shade/Strategic).",
            "DESCRIPTIVE split only -- not causal, no market/$ edge claimed.",
        ],
    )


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB fielding-alignment split claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = []
    for season in SEASONS:
        claims.append(build_babip_claim(season))
        claims.append(build_xwoba_claim(season))
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
