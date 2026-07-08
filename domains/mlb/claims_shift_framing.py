"""domains.mlb.claims_shift_framing -- 2 DESCRIPTIVE claims stores on the
savant_full corpus, reusing domains.mlb.prereg_shift_framing's premise-checked
machinery (build_taken_pitches / classify_borderline / CATCHER_FLOOR / load_savant),
zero reimplementation:

  1. mlb_framing_claims.jsonl -- per catcher (>=500 borderline takes, same floor
     H2 uses), borderline called-strike rate vs the league borderline rate. One
     ranking claim per season (2023, 2024).

  2. mlb_shift_vulnerability_claims.jsonl -- per BATTER, BABIP-on-grounders under
     shifted vs standard infield alignment, ranked by delta (standard - shifted,
     descending = most shift-vulnerable), top-50, one ranking claim per season.

     DEVIATION from the brief's "as-of pull share x BABIP-vs-shift delta" framing:
     prereg_shift_framing.run_h1 is BLOCKED -- this corpus has no hit-coordinate/
     spray column, so a genuine pull-share weight cannot be computed (see that
     module's docstring). This claim measures shift-vulnerability DIRECTLY (each
     batter's own realized BABIP delta under the two alignments) instead of
     weighting by an unmeasurable tendency proxy -- a real substitution, stated
     here so it is never silently read as the originally-worded claim.

     N-FLOOR: the brief's declared n>=100 shifted GBs/batter is too thin post-ban
     (verified live: only 16-22 batters/season clear it) -- floor=50 used instead
     (94-113 batters/season clear it), per the brief's own thin-post-ban fallback.

DESCRIPTIVE only: no market/$ edge claimed.
CLI: python -m domains.mlb.claims_shift_framing
Per-file test: python -m pytest domains/mlb/test_claims_shift_framing.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from domains.mlb.prereg_shift_framing import (
    CATCHER_FLOOR, _SHIFTED_ALIGNMENTS, build_taken_pitches, classify_borderline, load_savant,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_FRAMING_OUT = _OUT_DIR / "mlb_framing_claims.jsonl"
_SHIFT_VULN_OUT = _OUT_DIR / "mlb_shift_vulnerability_claims.jsonl"

SEASONS = ("2023", "2024")
SHIFT_VULN_FLOOR = 50  # brief's n>=100 too thin post-ban (16-22 batters/season) -- see docstring
TOP_N = 50


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")  # test out_dir outside the repo (tmp_path)


def build_framing_claim(season: str, df_raw: Optional[pd.DataFrame] = None,
                         out_dir: Path = _OUT_DIR, floor: int = CATCHER_FLOOR) -> dict[str, Any]:
    df = df_raw if df_raw is not None else load_savant(season)
    taken = build_taken_pitches(df)
    border = taken[classify_borderline(taken)].copy()
    league_rate = float(border["is_strike"].mean()) if len(border) else None
    # rename to match criteria.aggregate.group_by/entity_key ("catcher_id") -- the
    # independent validator groups the SOURCE parquet by that literal column name.
    border = border.rename(columns={"fielder_2": "catcher_id"})

    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = out_dir / f"mlb_framing_borderline_source_{season}.parquet"
    src_cols = ["catcher_id", "is_strike"] + (["game_date"] if "game_date" in border.columns else [])
    border[src_cols].reset_index(drop=True).to_parquet(src_path, index=False)

    counts = border.groupby("catcher_id")["is_strike"].agg(n="size", strikes="sum").reset_index()
    n_considered = len(counts)
    qual = counts[counts["n"] >= floor].copy()
    n_excluded = n_considered - len(qual)
    qual["rate"] = qual["strikes"] / qual["n"]
    qual["vs_league"] = qual["rate"] - league_rate
    qual = qual.sort_values("rate", ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "catcher_id": int(r.catcher_id), "value": round(float(r.rate), 4),
         "vs_league": round(float(r.vs_league), 4), "n": int(r.n)}
        for i, r in enumerate(qual.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"mlb_framing_borderline_{season}", "kind": "ranking",
        "question": f"MLB {season}: borderline called-strike rate by catcher vs league?",
        "criteria": {
            "metric": "borderline_called_strike_rate", "formula": "mean(is_strike)",
            "aggregate": {"group_by": "catcher_id", "derived": {"n": "count(is_strike)"}},
            "window": src_path.stem, "min_sample": {"n": floor}, "direction": "desc",
            "value_precision": 4, "entity_key": "catcher_id",
        },
        "ranking": ranking, "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "league_rate": round(league_rate, 4) if league_rate is not None else None,
        "edge_claimed": False,
        "caveats": [
            "borderline = classify_borderline edge-shell (SHELL_FT=0.25 ft) on taken pitches "
            "(description in called_strike/ball) -- see prereg_shift_framing.py docstring.",
            f"min_sample floor n>={floor} borderline takes/catcher (matches H2's own floor).",
            "DESCRIPTIVE catcher-skill split only -- not causal (pitcher/ump/batter-mix not "
            "controlled for), no market/$ edge claimed.",
        ],
    }


def build_shift_vulnerability_claim(season: str, df_raw: Optional[pd.DataFrame] = None,
                                     out_dir: Path = _OUT_DIR, floor: int = SHIFT_VULN_FLOOR,
                                     top_n: int = TOP_N) -> dict[str, Any]:
    """babip_delta = babip_standard - babip_shifted, computed via 4 per-row
    indicator columns (is_hit_shifted/is_hit_standard/n_shifted/n_standard) so
    the SAME arithmetic is expressible in the independent validator's whitelist
    aggregate grammar (sum/mean/count + arithmetic, no conditional filtering
    inside a formula string -- see safe_formula.py): babip_x = sum(is_hit_x)/
    sum(n_x) per alignment, delta = their difference, all as ONE groupby(batter_id)
    aggregate. The exported source is restricted to batters with >=1 GB under
    BOTH alignments (the same population an inner join would keep) so the
    validator's own recompute population matches n_considered/n_excluded_below_floor
    exactly -- a batter present under only one alignment would divide by zero
    (0/0 -> NaN) in the OTHER alignment's term and was never rankable anyway."""
    df = df_raw if df_raw is not None else load_savant(season)
    gb = df[(df["type"] == "X") & (df["bb_type"] == "ground_ball") & (df["events"] != "home_run")].copy()
    gb["is_hit"] = gb["events"].isin(["single", "double", "triple"]).astype(int)
    gb["is_shifted"] = gb["if_fielding_alignment"].isin(_SHIFTED_ALIGNMENTS)
    gb["is_hit_shifted"] = gb["is_hit"].where(gb["is_shifted"], 0)
    gb["is_hit_standard"] = gb["is_hit"].where(~gb["is_shifted"], 0)
    gb["n_shifted"] = gb["is_shifted"].astype(int)
    gb["n_standard"] = (~gb["is_shifted"]).astype(int)
    gb = gb.rename(columns={"batter": "batter_id"})

    has_shifted = set(gb.loc[gb["n_shifted"] == 1, "batter_id"])
    has_standard = set(gb.loc[gb["n_standard"] == 1, "batter_id"])
    joined_population = has_shifted & has_standard  # same population an inner join would keep
    gb = gb[gb["batter_id"].isin(joined_population)].copy()

    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = out_dir / f"mlb_shift_vulnerability_source_{season}.parquet"
    src_cols = ["batter_id", "is_hit_shifted", "is_hit_standard", "n_shifted", "n_standard"]
    src_cols += ["game_date"] if "game_date" in gb.columns else []
    gb[src_cols].reset_index(drop=True).to_parquet(src_path, index=False)

    agg = gb.groupby("batter_id").agg(
        n_shifted=("n_shifted", "sum"), n_standard=("n_standard", "sum"),
        babip_shifted=("is_hit_shifted", "sum"), babip_standard=("is_hit_standard", "sum"),
    )
    agg["babip_shifted"] = agg["babip_shifted"] / agg["n_shifted"]
    agg["babip_standard"] = agg["babip_standard"] / agg["n_standard"]
    n_considered = len(agg)
    qual = agg[agg["n_shifted"] >= floor].copy()
    n_excluded = n_considered - len(qual)
    qual["babip_delta"] = qual["babip_standard"] - qual["babip_shifted"]
    qual = qual.sort_values("babip_delta", ascending=False).head(top_n).reset_index()

    ranking = [
        {"rank": i, "batter_id": int(r.batter_id), "value": round(float(r.babip_delta), 4),
         "babip_standard": round(float(r.babip_standard), 4), "babip_shifted": round(float(r.babip_shifted), 4),
         "n": int(r.n_shifted), "n_shifted": int(r.n_shifted), "n_standard": int(r.n_standard)}
        for i, r in enumerate(qual.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"mlb_shift_vulnerability_{season}", "kind": "ranking",
        "question": f"MLB {season}: which batters lose the most BABIP-on-grounders to a shifted infield?",
        "criteria": {
            "metric": "babip_delta_standard_minus_shifted",
            "formula": "(sum(is_hit_standard)/sum(n_standard)) - (sum(is_hit_shifted)/sum(n_shifted))",
            "aggregate": {"group_by": "batter_id",
                          "derived": {"n_shifted": "sum(n_shifted)", "n_standard": "sum(n_standard)"}},
            "window": src_path.stem, "min_sample": {"n_shifted": floor}, "top_n": top_n,
            "direction": "desc", "value_precision": 4, "entity_key": "batter_id",
        },
        "ranking": ranking, "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "DEVIATION: not pull-share-weighted (see module docstring) -- DIRECT per-batter "
            "BABIP delta (standard-alignment BABIP minus shifted-alignment BABIP), home runs "
            "excluded from both (standard BABIP convention).",
            f"n-floor: n_shifted>={floor} grounders/batter (brief's n>=100 too thin post-ban).",
            "DESCRIPTIVE split only -- not causal (pitcher/park/count context not controlled "
            "for), no market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main() -> int:
    framing_claims = [build_framing_claim(s) for s in SEASONS]
    vuln_claims = [build_shift_vulnerability_claim(s) for s in SEASONS]
    write_claims(framing_claims, _FRAMING_OUT)
    write_claims(vuln_claims, _SHIFT_VULN_OUT)

    print(f"wrote {len(framing_claims)} claims -> {_FRAMING_OUT}")
    for c in framing_claims:
        print(f"  {c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])} "
              f"league_rate={c['league_rate']}")
    print(f"wrote {len(vuln_claims)} claims -> {_SHIFT_VULN_OUT}")
    for c in vuln_claims:
        print(f"  {c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
