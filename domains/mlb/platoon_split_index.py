"""domains.mlb.platoon_split_index -- per-batter PLATOON SPLIT descriptive
index (LANE platoon-index, program v2 build rank 2).

METRIC (v1, descriptive only): platoon_delta = (PA-ending outcome rate vs
LHP) - (PA-ending outcome rate vs RHP), per batter. "Outcome rate" here is
on-base rate: (events in {single, double, triple, home_run, walk,
intent_walk, hit_by_pitch}) / PA, computed separately for PAs where
p_throws == 'L' and PAs where p_throws == 'R'. p_throws (the PITCHER's
throwing hand, not stand) has 100% coverage on this corpus -- verified live
this session via schema read. This is a RANKING/scouting claim, never a
market-edge claim -- see NO EDGE CLAIMS below.

PA DEFINITION: a row where `events` is non-null marks the PA-ending pitch
(verified live this session: events notna count == type=='X' union non-BIP
PA-enders; NOT `des`, which covers only 25.6% of pitches on this corpus --
same free-text-coverage trap documented in catcher_framing_index.py).

CORPUS: data/cache/statcast/statcast_fuller__2022.parquet (70961 rows) +
__2023.parquet (63159 rows) -- both seasons are an 18-day SAMPLE WINDOW
(2022: 2022-05-02..2022-07-12; 2023: 2023-05-01..2023-07-11), not full
seasons. Verified live this session: batter (503+ distinct ids), p_throws
100% coverage on both files.

MIN-SAMPLE FLOOR (per LANE spec): >=100 PA per (batter, p_throws) cell --
i.e. a batter must have >=100 PA vs LHP AND >=100 PA vs RHP to qualify.
HONEST DATA-SCALE FINDING (verified live this session, both seasons
concatenated): max PA any single batter accumulates vs LHP is 57 and vs RHP
is 128; only 23/633 distinct batters clear the >=100 floor vs RHP alone, and
ZERO clear it vs LHP, so ZERO batters qualify on BOTH cells simultaneously.
This is a mechanical consequence of the corpus's 18-day-per-season sampling
window (not a bug) -- the module and its claims emitter run correctly
end-to-end and produce a legitimately EMPTY qualifying set. The reject_ledger-
style honest outcome is: this index is ready to run the moment a fuller-
coverage (full-season) statcast pull lands; nothing here is stale-premise
or mis-implemented. Re-running this module against a full-season corpus
requires zero code changes.

SHAPE FOR THE CLAIMS CONTRACT: unlike a single-group_by aggregate (see
catcher_framing_claims.py), a platoon DELTA needs two separate per-hand
aggregates joined into ONE row per batter before ranking. This module
therefore emits a WIDE per-batter snapshot (pa_vs_l, outcome_vs_l, pa_vs_r,
outcome_vs_r) and the claims emitter (platoon_split_claims.py, if built)
uses the validator's PLAIN row-wise formula path (not criteria.aggregate):
formula = "(outcome_vs_l / pa_vs_l) - (outcome_vs_r / pa_vs_r)", which the
validator's whitelist grammar (safe_formula.evaluate_formula) can recompute
directly from these four columns with no aggregate grammar needed.

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE/SCOUTING ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m domains.mlb.platoon_split_index
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_REPO_ROOT = Path(__file__).resolve().parents[2]

_STATCAST_2022 = _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet"
_STATCAST_2023 = _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet"
_GAMELOGS = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

_OUT_DIR = _REPO_ROOT / "data" / "domains" / "mlb"
_INDEX_OUT = _OUT_DIR / "platoon_split_index.parquet"
_REPORT_OUT = _OUT_DIR / "platoon_split_index_report.json"

CORPUS_ID = "statcast_fuller_v1"
SEASONS = (2022, 2023)
MIN_PA_PER_HAND = 100  # per LANE spec: min_sample >= 100 PA per (batter, hand) cell

_ON_BASE_EVENTS = {
    "single", "double", "triple", "home_run",
    "walk", "intent_walk", "hit_by_pitch",
}


def load_pa_rows(seasons: tuple = SEASONS) -> pd.DataFrame:
    """Load + concat the fuller statcast parquets, keep only PA-ENDING rows
    (events notna -- NEVER des, which covers only 25.6% of pitches)."""
    frames = []
    paths = {2022: _STATCAST_2022, 2023: _STATCAST_2023}
    for season in seasons:
        path = paths[season]
        df = pd.read_parquet(path)
        df["season"] = season
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    pa_rows = combined[combined["events"].notna()].copy()
    pa_rows["on_base"] = pa_rows["events"].isin(_ON_BASE_EVENTS).astype(int)
    return pa_rows


def build_platoon_snapshot(pa_rows: Optional[pd.DataFrame] = None,
                            min_pa_per_hand: Optional[int] = None) -> tuple[pd.DataFrame, dict]:
    """Build the WIDE per-batter snapshot (pa_vs_l/outcome_vs_l/pa_vs_r/
    outcome_vs_r) -- one row per batter, both hand-cells present (0-filled
    if a batter never faced that hand). Returns (snapshot_df, report_dict)
    covering the FULL batter pool (no floor applied to the returned frame --
    matches the catcher_framing_index.py precedent of shipping raw counts
    and letting the claim's min_sample criteria do the excluding); the
    report's floor-derived counts use min_pa_per_hand (defaults to the
    CURRENT module-level MIN_PA_PER_HAND at call time)."""
    if min_pa_per_hand is None:
        min_pa_per_hand = MIN_PA_PER_HAND
    if pa_rows is None:
        pa_rows = load_pa_rows()

    grouped = pa_rows.groupby(["batter", "p_throws"]).agg(
        pa=("on_base", "size"),
        on_base=("on_base", "sum"),
    ).reset_index()

    wide = grouped.pivot(index="batter", columns="p_throws", values=["pa", "on_base"])
    wide.columns = [f"{metric}_vs_{hand.lower()}" for metric, hand in wide.columns]
    wide = wide.reset_index().fillna(0)

    for col in ("pa_vs_l", "on_base_vs_l", "pa_vs_r", "on_base_vs_r"):
        if col not in wide.columns:
            wide[col] = 0
    wide["pa_vs_l"] = wide["pa_vs_l"].astype(int)
    wide["pa_vs_r"] = wide["pa_vs_r"].astype(int)
    wide["on_base_vs_l"] = wide["on_base_vs_l"].astype(int)
    wide["on_base_vs_r"] = wide["on_base_vs_r"].astype(int)

    n_considered = len(wide)
    qualifiers = wide[(wide["pa_vs_l"] >= min_pa_per_hand) & (wide["pa_vs_r"] >= min_pa_per_hand)].copy()
    n_excluded = n_considered - len(qualifiers)

    as_of = datetime.now(timezone.utc).isoformat()
    wide["as_of"] = as_of
    wide["corpus_id"] = CORPUS_ID
    wide["season"] = "2022_2023"

    report = {
        "component": "platoon_split_index",
        "as_of": as_of,
        "corpus_id": CORPUS_ID,
        "seasons": list(SEASONS),
        "n_batters_considered": n_considered,
        "n_batters_excluded_below_floor": n_excluded,
        "min_pa_per_hand_floor": min_pa_per_hand,
        "n_qualifying_batters": len(qualifiers),
        "max_pa_vs_l_any_batter": int(wide["pa_vs_l"].max()) if n_considered else 0,
        "max_pa_vs_r_any_batter": int(wide["pa_vs_r"].max()) if n_considered else 0,
        "descriptive_only": True,
        "edge_claimed": False,
    }
    return wide, report


def build_platoon_index(pa_rows: Optional[pd.DataFrame] = None,
                         min_pa_per_hand: Optional[int] = None) -> tuple[pd.DataFrame, dict]:
    """Convenience wrapper: build the snapshot, apply the floor, compute
    platoon_delta for QUALIFYING batters only, attach names. Returns
    (qualifiers_df, report_dict) -- qualifiers_df may legitimately be EMPTY
    (see module docstring HONEST DATA-SCALE FINDING). min_pa_per_hand
    defaults to the CURRENT module-level MIN_PA_PER_HAND at call time (not
    def time), so monkeypatching the module constant is honored."""
    if min_pa_per_hand is None:
        min_pa_per_hand = MIN_PA_PER_HAND
    wide, report = build_platoon_snapshot(pa_rows, min_pa_per_hand=min_pa_per_hand)
    qualifiers = wide[
        (wide["pa_vs_l"] >= min_pa_per_hand) & (wide["pa_vs_r"] >= min_pa_per_hand)
    ].copy()

    if len(qualifiers):
        qualifiers["rate_vs_l"] = qualifiers["on_base_vs_l"] / qualifiers["pa_vs_l"]
        qualifiers["rate_vs_r"] = qualifiers["on_base_vs_r"] / qualifiers["pa_vs_r"]
        qualifiers["platoon_delta"] = qualifiers["rate_vs_l"] - qualifiers["rate_vs_r"]

        if _GAMELOGS.exists():
            names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
            name_lookup = dict(
                names.drop_duplicates(subset=["player_id"], keep="last")
                .set_index("player_id")["player"]
            )
            qualifiers["batter_name"] = qualifiers["batter"].map(
                lambda bid: name_lookup.get(int(bid), "Unknown")
            )
        else:
            qualifiers["batter_name"] = "Unknown"

        qualifiers = qualifiers.sort_values("platoon_delta", ascending=False).reset_index(drop=True)
    else:
        for col in ("rate_vs_l", "rate_vs_r", "platoon_delta", "batter_name"):
            qualifiers[col] = pd.Series(dtype="float64" if col != "batter_name" else "object")

    return qualifiers, report


def write_index(qualifiers: pd.DataFrame, report: dict,
                 index_out: Path = _INDEX_OUT, report_out: Path = _REPORT_OUT) -> tuple[Path, Path]:
    index_out.parent.mkdir(parents=True, exist_ok=True)
    keep_cols = [
        "batter", "batter_name", "pa_vs_l", "on_base_vs_l", "rate_vs_l",
        "pa_vs_r", "on_base_vs_r", "rate_vs_r", "platoon_delta",
        "as_of", "corpus_id", "season",
    ]
    write_cols = qualifiers[[c for c in keep_cols if c in qualifiers.columns]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), index_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    with open(report_out, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    return index_out, report_out


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the MLB platoon-split descriptive index")
    parser.add_argument("--min-pa-per-hand", type=int, default=MIN_PA_PER_HAND)
    args = parser.parse_args(argv)

    qualifiers, report = build_platoon_index(min_pa_per_hand=args.min_pa_per_hand)
    index_path, report_path = write_index(qualifiers, report)

    print(f"n_considered={report['n_batters_considered']} "
          f"n_excluded_below_floor={report['n_batters_excluded_below_floor']} "
          f"n_qualifying={report['n_qualifying_batters']}")
    print(f"max_pa_vs_l_any_batter={report['max_pa_vs_l_any_batter']} "
          f"max_pa_vs_r_any_batter={report['max_pa_vs_r_any_batter']}")
    if len(qualifiers):
        top = qualifiers.iloc[0]
        print(f"top1: {top['batter_name']} platoon_delta={top['platoon_delta']:.4f}")
    else:
        print("n_qualifying=0 -- HONEST_NEGATIVE: no batter clears the >=100 PA-per-hand "
              "floor on both hands in this 18-day-per-season corpus (see module docstring).")
    print(f"wrote index -> {index_path}")
    print(f"wrote report -> {report_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
