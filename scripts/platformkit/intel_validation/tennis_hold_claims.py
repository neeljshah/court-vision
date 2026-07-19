"""Tennis hold-pct ranking claims producer (mission spine 5, lane claims-breadth).

Emits FULL-POPULATION as-of hold-pct% ranking claims per tour (ATP + WTA) --
every player above the min_sample floor gets a ranked row, not a top-N slice
-- in the SAME claims contract shape as scripts/platformkit/intel_validation's
ranking claims (see data/cache/intel_claims/nba_shooting_claims.jsonl for the
sibling NBA producer's row shape) so the independent claims_validator.py can
VERIFY them with zero code sharing between producer and validator.

WHY A LONG-FORMAT SIDE PARQUET: the on-disk asof_hold*.parquet is WIDE
(one row per MATCH, p1_/p2_-prefixed columns, no player_id column at all --
see domains/tennis/asof_hold.py). The claims contract's non-aggregate path
needs one row per ENTITY (player_id) with a plain column the formula can
reference. This module reshapes wide->long (join asof_hold*.parquet against
the matches spine for p1_id/p2_id/date, melt p1/p2 into one row each), then
keeps each player's LAST as-of snapshot within the declared season window
(their most recent trailing hold-pct as of that match) -- a plain per-row
lookup, not a groupby-aggregate. The reshaped table is written to
data/cache/intel_claims/tennis_hold_snapshot_<tour>.parquet and named as the
claim's source_files entry, so the validator re-derives the ranking from that
same on-disk artifact, independent of this module.

LEAK DISCIPLINE: hold_pct_asof is already a leak-free trailing feature (each
row is a snapshot BEFORE that match is played, per domains/tennis/asof_hold.py's
own future-leak assertion). Taking a player's LAST snapshot in-window adds no
new leak -- it is simply "the most recent as-of prior we have for them".

MIN-SAMPLE FLOOR: n_prior >= 50 service-games-equivalent matches (a player's
running match count feeding the hold_pct_asof average) -- defensible floor
against small-sample noise; STATED explicitly in each claim's min_sample.

NETWORK: zero. Pure pandas over already-materialized parquets.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_hold_claims
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

_ATP_MATCHES = REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet"
_ATP_HOLD = REPO_ROOT / "data" / "domains" / "tennis" / "asof_hold.parquet"
_WTA_MATCHES = REPO_ROOT / "data" / "domains" / "tennis" / "wta_matches.parquet"
_WTA_HOLD = REPO_ROOT / "data" / "domains" / "tennis" / "asof_hold_wta.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_hold_claims.jsonl"

SEASON_WINDOW = "2025"  # last complete on-disk season for BOTH tours (verified)
MIN_N_PRIOR = 50


def _reshape_long(matches: pd.DataFrame, hold: pd.DataFrame) -> pd.DataFrame:
    """Join the match spine (p1_id/p2_id/date) against the wide asof_hold
    table, then melt p1_/p2_ into one row per player per match:
    columns = player_id, date, hold_pct_asof, n_prior."""
    spine = matches[["event_id", "date", "p1_id", "p2_id"]].copy()
    joined = spine.merge(hold[["event_id", "p1_hold_pct_asof", "p2_hold_pct_asof",
                                "p1_n_prior", "p2_n_prior"]], on="event_id", how="inner")
    p1 = joined.rename(columns={
        "p1_id": "player_id", "p1_hold_pct_asof": "hold_pct_asof", "p1_n_prior": "n_prior",
    })[["player_id", "date", "hold_pct_asof", "n_prior"]]
    p2 = joined.rename(columns={
        "p2_id": "player_id", "p2_hold_pct_asof": "hold_pct_asof", "p2_n_prior": "n_prior",
    })[["player_id", "date", "hold_pct_asof", "n_prior"]]
    long_df = pd.concat([p1, p2], ignore_index=True)
    long_df["player_id"] = pd.to_numeric(long_df["player_id"], errors="coerce")
    long_df = long_df.dropna(subset=["player_id"])
    long_df["player_id"] = long_df["player_id"].astype("int64")
    return long_df


def _season_snapshot(long_df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Restrict to the season window, then keep each player's LAST (most
    recent-dated) as-of row within that window -- one row per player."""
    season_year = int(season)
    in_season = long_df[long_df["date"].map(lambda d: d.year) == season_year].copy()
    in_season = in_season.sort_values("date", kind="mergesort")
    latest = in_season.groupby("player_id", as_index=False).tail(1).reset_index(drop=True)
    return latest


def _name_lookup(matches: pd.DataFrame) -> dict[int, str]:
    names: dict[int, str] = {}
    for id_col, name_col in (("p1_id", "p1_name"), ("p2_id", "p2_name")):
        sub = matches[[id_col, name_col]].dropna()
        for pid, name in zip(sub[id_col], sub[name_col]):
            names[int(pid)] = str(name)
    return names


def build_tour_snapshot(tour: str) -> tuple[Path, pd.DataFrame, int, int]:
    """Build + write the long-format season snapshot parquet for one tour.
    Returns (parquet_path, snapshot_df, n_considered, n_excluded_below_floor)."""
    if tour == "atp":
        matches = pd.read_parquet(_ATP_MATCHES)
        hold = pd.read_parquet(_ATP_HOLD)
        out_path = _OUT_DIR / "tennis_hold_snapshot_atp.parquet"
    elif tour == "wta":
        matches = pd.read_parquet(_WTA_MATCHES)
        hold = pd.read_parquet(_WTA_HOLD)
        out_path = _OUT_DIR / "tennis_hold_snapshot_wta.parquet"
    else:
        raise ValueError(f"unknown tour: {tour!r}")

    long_df = _reshape_long(matches, hold)
    snapshot = _season_snapshot(long_df, SEASON_WINDOW)
    n_considered = len(snapshot)
    n_excluded = int((snapshot["n_prior"] < MIN_N_PRIOR).sum())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_cols = snapshot[["player_id", "hold_pct_asof", "n_prior"]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), out_path)

    names = _name_lookup(matches)
    snapshot = snapshot.copy()
    snapshot["player_name"] = snapshot["player_id"].map(lambda pid: names.get(int(pid), "Unknown"))
    return out_path, snapshot, n_considered, n_excluded


def build_ranking_claim(tour: str) -> dict[str, Any]:
    out_path, snapshot, n_considered, n_excluded = build_tour_snapshot(tour)
    qualifiers = snapshot[snapshot["n_prior"] >= MIN_N_PRIOR].copy()
    qualifiers = qualifiers.dropna(subset=["hold_pct_asof"])
    # tie-break: value DESC, THEN player_id ASC -- matches claims_validator.py's
    # generic recompute tie-break, see tennis_ranking_claims.py docstring.
    qualifiers = qualifiers.sort_values(["hold_pct_asof", "player_id"], ascending=[False, True]).reset_index(drop=True)
    # FULL POPULATION: every qualifier above the floor gets a row (no head(N)
    # slice) -- below-floor entities are already counted in n_excluded above.
    top = qualifiers

    ranking = []
    for i, row in enumerate(top.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "player_id": int(row.player_id),
            "player_name": row.player_name,
            "value": round(float(row.hold_pct_asof), 4),
            "n": int(row.n_prior),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    tour_label = "ATP" if tour == "atp" else "WTA"
    # window embeds the tour (season_2025_atp / season_2025_wta) so an explicit
    # "window=season_2025_atp" hint disambiguates tour in ask()'s top_n filter --
    # both tours otherwise share metric=hold_pct_asof and would tie-break on
    # computed_at alone (see ask.py's _answer_top_n most-recent tie-break).
    # claim_id keeps its original "top50" token (a stable identifier, not a
    # population-size claim) even though the ranking itself is now the FULL
    # qualifying population -- renaming it would break cached demo transcripts
    # / dossier keys that reference this exact string.
    return {
        "claim_id": f"tennis_hold_pct_top50_{tour}_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Who holds serve best on the {tour_label} tour (full population, season={SEASON_WINDOW})?",
        "criteria": {
            "metric": "hold_pct_asof",
            "formula": "hold_pct_asof",
            "window": f"season_{SEASON_WINDOW}_{tour}",
            "window_spec": {
                "kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None,
            },
            "min_sample": {"n_prior": MIN_N_PRIOR},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"hold_pct_asof is a leak-free TRAILING as-of prior (domains/tennis/asof_hold.py / "
            f"asof_hold_wta.py); each player's row is their LAST as-of snapshot within season="
            f"{SEASON_WINDOW} (their most recent trailing hold%, not a season-average recompute).",
            f"min_sample floor n_prior>={MIN_N_PRIOR} (running matches-in-history feeding the "
            "trailing average) -- a defensible floor against small-sample noise, not a "
            "tour-standard service-games threshold.",
            "FULL POPULATION: every qualifying player above the floor is ranked (no top-N "
            "slice); below-floor players are counted in n_excluded_below_floor, never dropped.",
            "CALIBRATION/descriptive ranking only -- no market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis hold-pct ranking claims (ATP+WTA)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [build_ranking_claim("atp"), build_ranking_claim("wta")]
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
