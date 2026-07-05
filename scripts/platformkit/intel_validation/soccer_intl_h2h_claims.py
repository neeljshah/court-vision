"""SOCCER_INTL head-to-head (H2H) pair claims (PROGRAM v3 breadth, lane
soccer-widen). Widens soccer_intl beyond its single strength-ranking claim
(soccer_intl_strength_claims.py) using the SAME owned results.parquet corpus,
mirroring tennis_h2h_claims.py's pair-keyed contract precedent. Sibling module
soccer_intl_form_claims.py covers the trailing-form dimension (split out to
stay under the 300-LOC/file rail).

H2H PAIR CLAIMS: for every national-team pair with >= MIN_MEETINGS recorded
matches, h2h_win_share (win share of the canonically-lower team, "team_lo")
and h2h_meetings. Emitted through the pair-keyed entity_key path
(criteria.entity_key = [team_lo, team_hi]) claims_validator.py already
supports (proven in production by tennis_h2h_claims.py).

CANONICAL PAIR ORDERING -- VERIFIED, NOT ASSUMED: unlike tennis's h2h.parquet
(which already ships p1_id < p2_id), soccer_intl's results.parquet stores
teams as home_team/away_team with NO pre-existing canonical pair id. Checked
on-disk: of 12292 distinct ordered (home_team, away_team) pairs, 9500 also
have their REVERSE (away_team, home_team) direction on record (e.g. Brazil
hosts Argentina in some matches, Argentina hosts Brazil in others) -- a naive
groupby(['home_team','away_team']) would count the SAME rivalry as two
separate entities. This module canonicalizes team_lo = min(home,away) /
team_hi = max(home,away) (alphabetical) BEFORE aggregating, merging both
home/away directions into one row per unordered pair -- proven correct by
test_soccer_intl_h2h_claims.py's merge-equivalence test (a fixture where the
same two teams meet in both home/away directions collapses to exactly one
pair row with the combined meeting count).

WHY A SIDE PARQUET: results.parquet is MATCH-level (one row per match,
home/away-keyed), not pair-level -- the merged (team_lo, team_hi) key is not
a plain row-wise formula the validator's non-aggregate path could evaluate
directly off raw match rows, and criteria.aggregate.group_by only supports a
single bare-string column (not a merged pair key). Per the SAME precedent as
tennis_h2h_claims.py, this producer pre-aggregates to a side parquet
(soccer_intl_h2h_pairs.parquet) the validator's PLAIN formula path
independently re-derives from (zero import of this module).

CAVEAT: DESCRIPTIVE career head-to-head only -- NOT a predictor. The
soccer_intl PREDICTIVE gate is CLOSED (xg_market_awareness.json:
NO_ADD_BEYOND_MARKET) and is NOT re-attempted here; no market/$ edge claimed.

NETWORK: zero. Pure pandas over the already-materialized results.parquet.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_intl_h2h_claims
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
_CLAIMS_OUT = _OUT_DIR / "soccer_intl_h2h_claims.jsonl"
_PAIR_PARQUET_OUT = _OUT_DIR / "soccer_intl_h2h_pairs.parquet"

MIN_MEETINGS = 5  # rationale: below this, a pair's win share is 1-4 matches of noise,
# matching tennis_h2h_claims.py's discipline (that module uses 3; soccer intl's much
# larger 7542-pair population affords a slightly stricter floor without emptying it).


def _winner(row: pd.Series) -> str | None:
    if row["home_score"] > row["away_score"]:
        return row["home_team"]
    if row["away_score"] > row["home_score"]:
        return row["away_team"]
    return None  # draw counts toward neither team's win total


def build_pair_table(results: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct unordered (team_lo, team_hi) pair: meetings
    (total matches between them) and wins_lo (matches won outright by
    team_lo, the alphabetically-lower team name -- draws count toward
    neither). team_lo/team_hi are computed here (no pre-existing canonical
    id in results.parquet, see module docstring), so both home/away
    directions of the same rivalry merge into one grouped row."""
    df = results.copy()
    df["team_lo"] = df[["home_team", "away_team"]].min(axis=1)
    df["team_hi"] = df[["home_team", "away_team"]].max(axis=1)
    df["winner"] = df.apply(_winner, axis=1)
    df["win_lo"] = (df["winner"] == df["team_lo"]).astype(int)
    grouped = df.groupby(["team_lo", "team_hi"], as_index=False).agg(
        meetings=("winner", "size"),
        wins_lo=("win_lo", "sum"),
    )
    return grouped


def build_ranking_claim(results_path: Path | None = None) -> dict[str, Any]:
    matches = pd.read_parquet(results_path if results_path is not None else _RESULTS)
    pairs = build_pair_table(matches)
    n_considered = len(pairs)
    n_excluded = int((pairs["meetings"] < MIN_MEETINGS).sum())

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_cols = pairs[["team_lo", "team_hi", "wins_lo", "meetings"]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _PAIR_PARQUET_OUT)

    qualifiers = pairs[pairs["meetings"] >= MIN_MEETINGS].copy()
    qualifiers["h2h_win_share"] = qualifiers["wins_lo"] / qualifiers["meetings"]
    qualifiers = qualifiers.sort_values("h2h_win_share", ascending=False).reset_index(drop=True)
    # FULL PAIR POPULATION: every qualifying pair above the floor gets a row
    # (no head(N) slice) -- below-floor pairs are already counted in
    # n_excluded above, never dropped from n_considered.

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team_lo": str(row.team_lo),
            "team_hi": str(row.team_hi),
            "value": round(float(row.h2h_win_share), 4),
            "n": int(row.meetings),
        })

    rel_source = str(_PAIR_PARQUET_OUT.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "soccer_intl_h2h_win_share_fullpairs",
        "kind": "ranking",
        "question": (
            "For every national-team pair with a recorded head-to-head history, "
            "what is each pair's h2h win share (full pair population above floor)?"
        ),
        "criteria": {
            "metric": "h2h_win_share",
            "formula": "wins_lo / meetings",
            "window": "career_full_corpus",
            "min_sample": {"meetings": MIN_MEETINGS},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": ["team_lo", "team_hi"],
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "DESCRIPTIVE career head-to-head only -- NOT a predictor of a future match; "
            "the soccer_intl PREDICTIVE gate is CLOSED (xg_market_awareness.json: "
            "NO_ADD_BEYOND_MARKET) and is not re-attempted here. No market/$ edge claimed.",
            f"min_sample floor meetings>={MIN_MEETINGS} -- below this, a pair's win share "
            "reflects 1-4 matches, not a meaningful career h2h pattern; below-floor pairs "
            "are counted in n_excluded_below_floor, never dropped from n_considered.",
            "team_lo/team_hi is an ALPHABETICAL canonical ordering computed by this module "
            "(results.parquet has no pre-existing pair id); verified on-disk that both "
            "home/away directions of the same rivalry exist as separate rows and merges "
            "them into one pair -- wins_lo counts outright wins by the alphabetically-lower "
            "team name, draws count toward neither.",
            "FULL PAIR POPULATION: every qualifying pair above the floor is ranked (no "
            "top-N slice); pairs below the floor are counted in n_excluded_below_floor.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit SOCCER_INTL H2H full-pair-population ranking claims")
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
