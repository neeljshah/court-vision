"""Tennis H2H dominance + playstyle archetype ranking claims (program v2,
lane tennis-h2h-claims -- FIRST real exercise of the PAIR-KEYED claims
contract path, entity_key=[p1_id, p2_id]).

Two DESCRIPTIVE ranking claims, same shared claims contract shape as every
other producer under scripts/platformkit/intel_validation (see
tennis_hold_claims.py for the sibling single-entity precedent):

(a) H2H DOMINANCE per (p1_id, p2_id) pair, from the per-match
    data/domains/tennis/atlas_h2h.parquet (30616 match rows). A "pair" is
    UNDIRECTED -- the same two players' matches must aggregate together
    regardless of which one a given match row lists as p1/p2. This module
    canonicalizes the pair key to (lo_id, hi_id) = (min(p1_id,p2_id),
    max(p1_id,p2_id)) and computes:
        meetings = count of matches between the pair
        wins_lo  = count of matches the lo_id player won
        dominance = wins_lo / meetings  (lo_id player's win share vs hi_id)
    min_sample: meetings >= 3. Top 50 pairs by dominance (desc).
    entity_key=[p1_id, p2_id] (pair-keyed; canonical lo/hi order) --
    exercises the list-entity_key extension in claims_validator.py.

(b) PLAYSTYLE ARCHETYPE ranking per player, from
    data/domains/tennis/atlas_playstyles.parquet (408 players, 17 cols,
    already pre-filtered to the atlas qualifier floor total_matches>=15 --
    see atlas_playstyle_specs.MIN_MATCHES). The primary style-score column
    PRESENT in this table is ov_wr (overall win rate) -- there is no
    separate composite "style score" column on disk, so ov_wr is the
    metric ranked. entity_key=player_id (scalar, unchanged contract path).

Both claims are DESCRIPTIVE/scouting rankings. NO market/$ edge claimed.
The in-game playstyle path is CLOSED/blocked per lane brief -- pregame
descriptive only.

NETWORK: zero. Pure pandas over already-materialized parquets.

CLI:
    python -m domains.tennis.h2h_index_claims
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

REPO_ROOT = Path(__file__).resolve().parents[2]

_ATLAS_H2H = REPO_ROOT / "data" / "domains" / "tennis" / "atlas_h2h.parquet"
_ATLAS_PLAYSTYLES = REPO_ROOT / "data" / "domains" / "tennis" / "atlas_playstyles.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_H2H_SIDE_PARQUET = _OUT_DIR / "tennis_h2h_pair_dominance.parquet"
_PLAYSTYLE_SIDE_PARQUET = _OUT_DIR / "tennis_playstyle_ov_wr.parquet"
_CLAIMS_OUT = _OUT_DIR / "tennis_h2h_index_claims.jsonl"

MIN_MEETINGS = 3
TOP_N = 50
CORPUS_ID = "sackmann_atp_matches_parquet"  # matches atlas_h2h.parquet's own corpus_id


def _canonical_pair_dominance(h2h: pd.DataFrame) -> pd.DataFrame:
    """Undirected pair aggregate: (lo_id, hi_id) = (min, max) of the match's
    p1_id/p2_id, wins_lo = matches the lo_id player won, meetings = count.
    Returns one row per distinct pair with a plain lo_id/hi_id/wins_lo/
    meetings/dominance table (no groupby-derived columns left as MultiIndex)."""
    df = h2h[["p1_id", "p2_id", "winner"]].copy()
    df["lo_id"] = df[["p1_id", "p2_id"]].min(axis=1)
    df["hi_id"] = df[["p1_id", "p2_id"]].max(axis=1)
    # winner_id: the actual player_id who won this match row (1->p1_id, 2->p2_id)
    df["winner_id"] = df["p1_id"].where(df["winner"] == 1, df["p2_id"])
    df["lo_won"] = (df["winner_id"] == df["lo_id"]).astype(int)

    grouped = df.groupby(["lo_id", "hi_id"], as_index=False).agg(
        meetings=("lo_won", "count"),
        wins_lo=("lo_won", "sum"),
    )
    grouped["dominance"] = grouped["wins_lo"] / grouped["meetings"]
    return grouped


def _name_lookup(h2h: pd.DataFrame) -> dict[int, str]:
    names: dict[int, str] = {}
    for id_col, name_col in (("p1_id", "p1_name"), ("p2_id", "p2_name")):
        sub = h2h[[id_col, name_col]].dropna()
        for pid, name in zip(sub[id_col], sub[name_col]):
            names[int(pid)] = str(name)
    return names


def build_h2h_side_table() -> tuple[Path, pd.DataFrame, int, int]:
    """Build + write the canonical pair-dominance side parquet.
    Returns (parquet_path, full_table, n_considered, n_excluded_below_floor)."""
    h2h = pd.read_parquet(_ATLAS_H2H)
    table = _canonical_pair_dominance(h2h)
    n_considered = len(table)
    n_excluded = int((table["meetings"] < MIN_MEETINGS).sum())

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_cols = table.rename(columns={"lo_id": "p1_id", "hi_id": "p2_id"})[
        ["p1_id", "p2_id", "wins_lo", "meetings", "dominance"]
    ].copy()
    # store as-of/corpus_id/season per storage R5 (new parquets write these at creation)
    write_cols["as_of"] = datetime.now(timezone.utc).date().isoformat()
    write_cols["corpus_id"] = CORPUS_ID
    write_cols["season"] = int(h2h["season"].max())
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _H2H_SIDE_PARQUET)

    return _H2H_SIDE_PARQUET, table, n_considered, n_excluded


def build_h2h_dominance_claim() -> dict[str, Any]:
    out_path, table, n_considered, n_excluded = build_h2h_side_table()
    h2h = pd.read_parquet(_ATLAS_H2H)
    names = _name_lookup(h2h)

    qualifiers = table[table["meetings"] >= MIN_MEETINGS].copy()
    qualifiers = qualifiers.sort_values("dominance", ascending=False).reset_index(drop=True)
    top = qualifiers.head(TOP_N)

    ranking = []
    for i, row in enumerate(top.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "p1_id": int(row.lo_id),
            "p2_id": int(row.hi_id),
            "p1_name": names.get(int(row.lo_id), "Unknown"),
            "p2_name": names.get(int(row.hi_id), "Unknown"),
            "value": round(float(row.dominance), 3),
            "n": int(row.meetings),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "tennis_h2h_dominance_top50_atp",
        "kind": "ranking",
        "question": "Which player owns the H2H matchup within a rivalry pair (top 50 pairs, ATP)?",
        "criteria": {
            "metric": "dominance",
            "formula": "wins_lo / meetings",
            "window": "all_time_atp",
            "min_sample": {"meetings": MIN_MEETINGS},
            "direction": "desc",
            "value_precision": 3,
            "entity_key": ["p1_id", "p2_id"],
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "dominance = (matches won by the pair's lower-numeric-id player) / (total meetings) "
            "-- an UNDIRECTED pair aggregate; p1_id/p2_id here are the canonical (min_id, max_id) "
            "pair key, NOT match-order p1/p2.",
            f"min_sample floor meetings>={MIN_MEETINGS} -- a defensible floor against 1-2 match "
            "sample noise, not a tour-standard rivalry threshold.",
            "DESCRIPTIVE/scouting ranking only -- no market/$ edge claimed.",
        ],
    }


def build_playstyle_side_table() -> tuple[Path, pd.DataFrame]:
    """Write the playstyle side parquet (player_id, ov_wr, total_matches)
    named as the claim's source_files entry -- a plain column subset of the
    on-disk atlas, not a recompute (the atlas floor already applies)."""
    styles = pd.read_parquet(_ATLAS_PLAYSTYLES)
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_cols = styles[["player_id", "ov_wr", "total_matches"]].copy()
    write_cols["as_of"] = datetime.now(timezone.utc).date().isoformat()
    write_cols["corpus_id"] = CORPUS_ID
    write_cols["season"] = int(styles["corpus_season_max"].max())
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _PLAYSTYLE_SIDE_PARQUET)
    return _PLAYSTYLE_SIDE_PARQUET, styles


def build_playstyle_claim() -> dict[str, Any]:
    out_path, styles = build_playstyle_side_table()
    n_considered = len(styles)
    # atlas_playstyles.parquet is already pre-filtered to the atlas qualifier
    # floor (total_matches >= 15, see atlas_playstyle_specs.MIN_MATCHES) --
    # 0 rows fall below that floor by construction; the min_sample declared
    # here is that SAME floor, stated explicitly so the validator re-checks it.
    from domains.tennis.atlas_playstyle_specs import MIN_MATCHES
    n_excluded = int((styles["total_matches"] < MIN_MATCHES).sum())

    qualifiers = styles[styles["total_matches"] >= MIN_MATCHES].copy()
    qualifiers = qualifiers.sort_values("ov_wr", ascending=False).reset_index(drop=True)
    top = qualifiers.head(TOP_N)

    ranking = []
    for i, row in enumerate(top.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "player_id": int(row.player_id),
            "value": round(float(row.ov_wr), 3),
            "n": int(row.total_matches),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "tennis_playstyle_ov_wr_top50_atp",
        "kind": "ranking",
        "question": "Who has the best overall win rate among ATP players with an established playstyle profile (top 50)?",
        "criteria": {
            "metric": "ov_wr",
            "formula": "ov_wr",
            "window": "all_time_atp",
            "min_sample": {"total_matches": MIN_MATCHES},
            "direction": "desc",
            "value_precision": 3,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "ov_wr is the primary style-score column PRESENT on the playstyle atlas -- there is "
            "no separate composite 'style score' column on disk; archetype LABELS (e.g. Clay "
            "Court Specialist) live in atlas_playstyle_specs.py's threshold logic, not as a "
            "per-player scored column, so this ranks overall win rate, not an archetype score.",
            "min_sample floor total_matches>=15 is the SAME atlas qualifier floor already applied "
            "when atlas_playstyles.parquet was built (see atlas_playstyle_specs.MIN_MATCHES) -- "
            "0 rows are newly excluded here; the floor is restated for validator re-derivation.",
            "DESCRIPTIVE/scouting ranking only -- no market/$ edge claimed. In-game playstyle path "
            "is CLOSED/blocked; this is pregame descriptive only.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis H2H dominance + playstyle ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [build_h2h_dominance_claim(), build_playstyle_claim()]
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
