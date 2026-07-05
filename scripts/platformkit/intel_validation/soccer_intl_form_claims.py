"""SOCCER_INTL trailing-form claims (PROGRAM v3 breadth, lane soccer-widen).
Widens soccer_intl beyond its single strength-ranking claim
(soccer_intl_strength_claims.py) using the SAME owned results.parquet corpus.
Sibling module soccer_intl_h2h_claims.py covers the pair-keyed H2H dimension
(split out to stay under the 300-LOC/file rail).

TRAILING-FORM DESCRIPTIVE: per team, win rate over the trailing N=10 matches
as-of the corpus end. N=10 rationale: a common "recent form" window in
sports analytics (short enough to reflect current form, long enough to
smooth single-match noise); every team clearing the existing n_matches>=200
floor convention (soccer_intl_strength_claims.MIN_N_MATCHES, reused here for
consistency across the two soccer_intl claim producers) has far more than 10
matches on record, so N=10 never truncates against a team's actual history.

DATE-ORDERING VERIFIED (not assumed): results.parquet's date column exists
and has zero NaT, but is NOT globally monotonic on disk (checked:
date.is_monotonic_increasing == False) -- this module explicitly re-sorts by
date before taking each team's trailing slice, rather than trusting on-disk
row order.

WHY A SIDE PARQUET: results.parquet is MATCH-level (one row per match,
home/away-keyed), not per-team -- a "win rate over the last N matches by
date" is a windowed groupby-then-tail aggregate, not a plain row-wise formula
the validator's non-aggregate path could evaluate directly off raw match
rows, and criteria.aggregate.group_by only supports a single derived-per-
group expression (sum/mean/count over the WHOLE group), not a "last N rows"
windowed slice. Per the SAME precedent as soccer_intl_strength_claims.py,
this producer pre-aggregates to a side parquet (soccer_intl_form_snapshot.
parquet) carrying the final per-team form_win_rate value directly, so the
validator's plain formula path (a bare column reference, "formula":
"form_win_rate" -- same pattern as tennis_hold_claims.py's "formula":
"hold_pct_asof") independently re-derives the ranking from that
materialized snapshot, zero import of this producer module.

CAVEAT: DESCRIPTIVE recent-form win rate only -- NOT a predictor. The
soccer_intl PREDICTIVE gate is CLOSED (xg_market_awareness.json:
NO_ADD_BEYOND_MARKET) and is NOT re-attempted here; no market/$ edge claimed.

NETWORK: zero. Pure pandas over the already-materialized results.parquet.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_intl_form_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_RESULTS = REPO_ROOT / "data" / "domains" / "soccer_intl" / "results.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "soccer_intl_form_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "soccer_intl_form_snapshot.parquet"

MIN_N_MATCHES = 200  # reuse soccer_intl_strength_claims.MIN_N_MATCHES's floor convention
FORM_TRAILING_N = 10  # trailing-N window for recent-form win rate (see module docstring)


def _winner(row: pd.Series) -> str | None:
    if row["home_score"] > row["away_score"]:
        return row["home_team"]
    if row["away_score"] > row["home_score"]:
        return row["away_team"]
    return None  # draw counts toward neither team's win total


def build_form_table(results: pd.DataFrame) -> pd.DataFrame:
    """One row per team: n_matches (total processed matches, same floor
    convention as soccer_intl_strength_claims.MIN_N_MATCHES) and
    form_win_rate (win rate over that team's trailing FORM_TRAILING_N
    matches, chronologically last by DATE -- results.parquet is explicitly
    re-sorted by date here, since on-disk row order is not guaranteed
    date-monotonic, see module docstring)."""
    df = results.sort_values("date", kind="mergesort").reset_index(drop=True)
    df["winner"] = df.apply(_winner, axis=1)
    long = pd.concat([
        df.assign(team=df["home_team"]),
        df.assign(team=df["away_team"]),
    ], ignore_index=True).sort_values("date", kind="mergesort")
    long["won"] = (long["winner"] == long["team"]).astype(int)

    rows = []
    for team, grp in long.groupby("team", sort=False):
        n_matches = len(grp)
        trailing = grp.tail(FORM_TRAILING_N)
        form_win_rate = float(trailing["won"].mean()) if len(trailing) > 0 else 0.0
        rows.append({
            "team": team,
            "n_matches": int(n_matches),
            "form_win_rate": form_win_rate,
            "n_trailing": int(len(trailing)),
        })
    return pd.DataFrame(rows)


def build_ranking_claim(results_path: Path | None = None) -> dict[str, Any]:
    matches = pd.read_parquet(results_path if results_path is not None else _RESULTS)
    form = build_form_table(matches)
    n_considered = len(form)
    n_excluded = int((form["n_matches"] < MIN_N_MATCHES).sum())

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_cols = form[["team", "n_matches", "form_win_rate", "n_trailing"]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _SNAPSHOT_OUT)

    qualifiers = form[form["n_matches"] >= MIN_N_MATCHES].copy()
    qualifiers = qualifiers.sort_values("form_win_rate", ascending=False).reset_index(drop=True)
    # FULL POPULATION: every team clearing the floor gets a row (no top-N
    # cap) -- below-floor teams are already counted in n_excluded above.

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team": str(row.team),
            "player_name": str(row.team),  # ask()'s ranking display-name key (cross-sport reuse)
            "value": round(float(row.form_win_rate), 4),
            "n": int(row.n_matches),
        })

    rel_source = str(_SNAPSHOT_OUT.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"soccer_intl_trailing{FORM_TRAILING_N}_form_win_rate_fullpop",
        "kind": "ranking",
        "question": (
            f"For every qualifying national team, what is its win rate over its trailing "
            f"{FORM_TRAILING_N} matches as-of the corpus end (full population above floor)?"
        ),
        "criteria": {
            "metric": "form_win_rate",
            "formula": "form_win_rate",  # bare column: the snapshot parquet already carries the
            # per-team metric value directly (same precedent as tennis_hold_claims.py's
            # "formula": "hold_pct_asof" -- a plain Name node the safe_formula grammar allows).
            "window": f"trailing_{FORM_TRAILING_N}_asof_corpus_end",
            "min_sample": {"n_matches": MIN_N_MATCHES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "DESCRIPTIVE recent-form win rate only -- NOT a predictor of a future match; "
            "the soccer_intl PREDICTIVE gate is CLOSED (xg_market_awareness.json: "
            "NO_ADD_BEYOND_MARKET) and is not re-attempted here. No market/$ edge claimed.",
            f"trailing window N={FORM_TRAILING_N} matches, chronologically last by DATE "
            "(results.parquet is explicitly re-sorted by date -- verified the on-disk row "
            "order is NOT globally date-monotonic, so sort order is never assumed).",
            f"min_sample floor n_matches>={MIN_N_MATCHES} (total processed matches for the "
            "team, reusing soccer_intl_strength_claims.py's floor convention for consistency "
            "across the two soccer_intl claim producers) -- below-floor teams are counted in "
            "n_excluded_below_floor, never silently dropped.",
            "FULL POPULATION: every team clearing the floor is ranked, no top-N cap.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit SOCCER_INTL trailing-form full-population ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claim = build_ranking_claim()
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
