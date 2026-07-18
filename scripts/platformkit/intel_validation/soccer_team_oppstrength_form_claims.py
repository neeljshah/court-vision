"""Soccer team opponent-strength form claims (covers the opponent-strength /
strength-of-schedule resolver fail).

Sources:
  - data/domains/soccer/matches.parquet -- event_id/date/season/div/
    home_team/away_team/ftr (own result, for pts).
  - data/domains/soccer/asof_xg_proxy.parquet -- home_xg_supremacy_asof /
    away_xg_supremacy_asof, ALREADY leak-free as-of (prior-only, median
    n_prior=163, verified). The opponent-strength axis is the OPPONENT's own
    as-of xG supremacy at that match -- prior-only by construction, no fresh
    Elo built here.

Method:
  1. Melt matches+asof_xg_proxy to team-grain: each row carries the team's
     own points (pts) and its OPPONENT's xg_supremacy_asof at that match.
  2. Classify each row's opponent into a weak/mid/strong TERCILE, cut
     WITHIN (div, season) on the observed opp_xg_supremacy_asof values (a
     population-level cutpoint, not a leak of any individual match's own
     result -- every value entering the cut is itself already as-of).
  3. Per team, drop that team's own most-recent match (leak-free as-of,
     same discipline as soccer_team_form_asof_claims.py), then compute:
       ppg_vs_strong / ppg_vs_weak -- mean pts vs strong/weak-tercile
       opponents among the remaining prior matches.
       form_strength_gap = ppg_vs_strong - ppg_vs_weak.
       sos_asof -- trailing-10 mean opponent xg_supremacy_asof (strength of
       schedule), prior-only.

Floors: sos_asof needs n_prior>=10 (spec). ppg_vs_strong/ppg_vs_weak need
their own n_vs_strong/n_vs_weak>=5 (chosen here -- avoids a single-match
artifact driving the average; noted as a reasonable minimum, not itself a
spec-declared number). form_strength_gap requires BOTH >=5.

DESCRIPTIVE only: no forecast, no market claim.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_team_oppstrength_form_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/soccer_team_oppstrength_form_claims.jsonl \
        --output data/cache/intel_claims/soccer_team_oppstrength_form_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_SOCCER_DIR = REPO_ROOT / "data" / "domains" / "soccer"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT = _OUT_DIR / "soccer_team_oppstrength_form_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "soccer_team_oppstrength_form_claims.jsonl"

WINDOW = 10
SOS_FLOOR = 10
STRENGTH_FLOOR = 5
WINDOW_TAG = "asof_corpus_end"

# (snapshot column, metric name, description, {floor_col: floor_value})
_METRICS = (
    ("ppg_vs_strong", "ppg_vs_strong", "points per game vs strong-tercile opponents (prior matches)", {"n_vs_strong": STRENGTH_FLOOR}),
    ("ppg_vs_weak", "ppg_vs_weak", "points per game vs weak-tercile opponents (prior matches)", {"n_vs_weak": STRENGTH_FLOOR}),
    ("form_strength_gap", "form_strength_gap", "ppg vs strong minus ppg vs weak opponents", {"n_vs_strong": STRENGTH_FLOOR, "n_vs_weak": STRENGTH_FLOOR}),
    ("sos_asof", "sos_asof", "trailing-10 mean opponent xG-supremacy as-of (strength of schedule)", {"n_prior": SOS_FLOOR}),
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_joined() -> pd.DataFrame:
    matches = pd.read_parquet(
        _SOCCER_DIR / "matches.parquet",
        columns=["event_id", "date", "season", "div", "home_team", "away_team", "ftr"],
    )
    xg = pd.read_parquet(
        _SOCCER_DIR / "asof_xg_proxy.parquet",
        columns=["event_id", "home_xg_supremacy_asof", "away_xg_supremacy_asof"],
    )
    joined = matches.merge(xg, on="event_id", how="inner")
    return joined.dropna(subset=["date", "ftr"])


def build_long_frame(joined: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match: own pts + the OPPONENT's xg_supremacy_asof
    at that same match (the opponent-strength axis, already leak-free)."""
    home = pd.DataFrame({
        "team": joined["home_team"], "date": joined["date"], "season": joined["season"], "div": joined["div"],
        "pts": np.select([joined["ftr"] == "H", joined["ftr"] == "D"], [3, 1], default=0),
        "opp_xg_supremacy_asof": joined["away_xg_supremacy_asof"],
    })
    away = pd.DataFrame({
        "team": joined["away_team"], "date": joined["date"], "season": joined["season"], "div": joined["div"],
        "pts": np.select([joined["ftr"] == "A", joined["ftr"] == "D"], [3, 1], default=0),
        "opp_xg_supremacy_asof": joined["home_xg_supremacy_asof"],
    })
    long = pd.concat([home, away], ignore_index=True)
    return long.sort_values("date", kind="mergesort").reset_index(drop=True)


def assign_opp_tercile(long_df: pd.DataFrame) -> pd.DataFrame:
    """Weak/mid/strong tercile label per row, cut WITHIN (div, season) on the
    observed opp_xg_supremacy_asof values (population cutpoint; every value
    entering the cut is itself already as-of -- see module docstring)."""
    out = long_df.copy()
    out["opp_tercile"] = pd.array([None] * len(out), dtype="object")
    for (_div, _season), grp in out.groupby(["div", "season"], sort=False):
        vals = grp["opp_xg_supremacy_asof"].dropna()
        if len(vals) < 3:
            continue
        codes = pd.qcut(vals, 3, duplicates="drop").cat.codes
        kmax = int(codes.max())
        if kmax < 2:
            continue  # not enough distinct cutpoints to separate strong from weak
        labels = codes.map(lambda c: "weak" if c == 0 else ("strong" if c == kmax else "mid"))
        out.loc[labels.index, "opp_tercile"] = labels.values
    return out


def _trailing_mean(prior: pd.DataFrame, col: str, window: int) -> float:
    tail = prior.tail(window)
    return float(tail[col].mean()) if len(tail) else float("nan")


def build_snapshot(long_df: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """One row per team: opponent-strength-conditioned form, computed from
    matches STRICTLY BEFORE the team's own most recent match (dropped
    before any aggregate is taken -- leak-free as-of, same discipline as
    soccer_team_form_asof_claims.py)."""
    labeled = assign_opp_tercile(long_df)
    rows: list[dict[str, Any]] = []
    for team, grp in labeled.groupby("team", sort=False):
        grp = grp.sort_values("date", kind="mergesort").reset_index(drop=True)
        prior = grp.iloc[:-1]
        n_prior = len(prior)

        vs_strong = prior[prior["opp_tercile"] == "strong"]
        vs_weak = prior[prior["opp_tercile"] == "weak"]
        n_vs_strong, n_vs_weak = len(vs_strong), len(vs_weak)
        ppg_vs_strong = float(vs_strong["pts"].mean()) if n_vs_strong else float("nan")
        ppg_vs_weak = float(vs_weak["pts"].mean()) if n_vs_weak else float("nan")
        gap = (ppg_vs_strong - ppg_vs_weak) if (n_vs_strong and n_vs_weak) else float("nan")

        rows.append({
            "team": str(team),
            "n_prior": n_prior,
            "sos_asof": _trailing_mean(prior, "opp_xg_supremacy_asof", window),
            "n_vs_strong": n_vs_strong,
            "ppg_vs_strong": ppg_vs_strong,
            "n_vs_weak": n_vs_weak,
            "ppg_vs_weak": ppg_vs_weak,
            "form_strength_gap": gap,
        })
    return pd.DataFrame(rows)


def write_snapshot(snap: pd.DataFrame, out_path: Path = _SNAPSHOT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out_path, index=False)
    return out_path


def build_claim(snap: pd.DataFrame, column: str, metric_name: str, description: str,
                 floors: dict[str, int]) -> dict[str, Any]:
    n_considered = len(snap)
    mask = pd.Series(True, index=snap.index)
    for col, val in floors.items():
        mask &= snap[col] >= val
    qualifiers = snap[mask].dropna(subset=[column]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(column, ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "team": str(r.team), "value": round(float(getattr(r, column)), 4),
         **{col: int(getattr(r, col)) for col in floors}}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"soccer_team_oppstrength_form_{metric_name}_{WINDOW_TAG}",
        "kind": "ranking",
        "question": f"Soccer: full-population team ranking by {description}?",
        "criteria": {
            "metric": metric_name, "formula": column, "window": WINDOW_TAG,
            "aggregate": None, "min_sample": floors,
            "direction": "desc", "value_precision": 4, "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "DESCRIPTIVE opponent-strength-conditioned form, not a forecast, no market claim.",
            f"min_sample floor(s) {floors}; below-floor teams are counted in "
            "n_excluded_below_floor, never silently dropped.",
            "AS-OF/leak-free: every aggregate is computed from matches STRICTLY BEFORE the "
            "team's own most recent match (dropped before any window/mean is taken).",
            "Opponent-strength axis is the OPPONENT's own as-of xG supremacy at that match "
            "(domains.soccer.asof_xg_proxy, prior-only by construction) -- no fresh Elo built.",
            "Weak/mid/strong tercile cutpoints are computed WITHIN (division, season) over "
            "already-as-of opponent values -- a population-level cutpoint, not a leak of any "
            "single match's own result.",
            f"{column} = {description}; snapshot parquet this store owns carries the "
            "precomputed value, formula is an identity read of that column.",
            "FULL POPULATION: every team clearing the floor(s) is ranked, no top-N cap.",
        ],
    }


def build_all_claims(snap: pd.DataFrame) -> list[dict[str, Any]]:
    """One claim per metric -- SKIP (never emit) a metric with zero qualifiers."""
    claims = [build_claim(snap, col, name, desc, floors) for col, name, desc, floors in _METRICS]
    return [c for c in claims if c["ranking"]]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit soccer team opponent-strength form DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    long_df = build_long_frame(_load_joined())
    snap = build_snapshot(long_df)
    write_snapshot(snap)
    claims = build_all_claims(snap)
    out_path = write_claims(claims, Path(args.output))

    for c in claims:
        top1 = c["ranking"][0] if c["ranking"] else None
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])} top1={top1}")
    print(f"wrote snapshot -> {_SNAPSHOT}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
