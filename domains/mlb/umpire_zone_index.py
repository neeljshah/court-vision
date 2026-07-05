"""domains.mlb.umpire_zone_index -- umpire-adjacent DESCRIPTIVE index (arm 2 of 2;
the catcher arm is domains/mlb/catcher_framing_index.py, arm 1).

PROBE THAT AUTHORIZED THIS MODULE: see data/domains/mlb/umpire_join_probe.json.
Summary: probables.parquet (11105 rows, game_pk-keyed, game_date spans
2022-04-07..2026-09-22) carries hp_umpire_id. The statcast_fuller 2022+2023
corpus (460 distinct game_pks) joins DIRECTLY on game_pk against
probables.parquet with 100%% match (460/460), zero doubleheader ambiguity,
100%% hp_umpire_id coverage on the matched set -- verified live in the probe.
game_pk_bridge.py (97.2%% resolved) is NOT needed: it bridges a DIFFERENT pair
of corpora (player_gamelogs.parquet current-season game_pk <-> games_current
.parquet event_id); the statcast<->probables join shares game_pk natively.

METRIC (v1, descriptive only, same framing as catcher_framing_index.py): per-
umpire out-of-zone STRIKE rate (called-OR-swung) -- of all pitches with type
in {S,B} that landed OUTSIDE the strike zone (per the SAME zone/geometric
predicate as the catcher index, imported not copied), what fraction were
coded type=='S'. Statcast's `type` field has exactly three values (S/B/X) and
does NOT distinguish a called strike from a swinging strike or a foul ball --
all three are type=='S'. This metric THEREFORE measures "how often pitches
behind this umpire's plate, when out of zone, end up strikes by any means
(called, swung, or fouled)" -- NOT an isolated called-strike/zone-consistency
rate. It is confounded by the specific PITCHER/BATTER mix each umpire happens
to have worked (umpire-to-game assignment is not random with respect to team
quality or pitcher command), and by the same batter chase/whiff behavior that
confounds the catcher index. This is NOT a predictive claim and NOT a market
edge -- see NO EDGE CLAIMS. Same CORRECTNESS-FIX rationale as the catcher
module: there is no Statcast code that isolates a called strike alone on this
corpus, so this module does not claim to measure umpire zone judgment in
isolation, only the same called-or-swung out-of-zone strike rate, aggregated
by umpire instead of by catcher.

REUSE (not copy): load_called_pitches() and derive_out_of_zone() are imported
directly from domains.mlb.catcher_framing_index -- identical zone (PRIMARY,
MLB's 1-9 in-zone / 11-14 out-of-zone) and geometric plate_x/z-vs-sz_top/bot
cross-check logic, so the two indices are directly comparable and any future
fix to the shared zone predicate lands in both at once.

JOIN: statcast pitch rows (game_pk) -> probables.parquet (game_pk ->
hp_umpire_id, hp_umpire_name), inner join, verified live in the probe artifact
(460/460 games, no doubleheader ambiguity, no fan-out: 1 probables row per
matched game_pk). Any statcast row whose game_pk is NOT in probables.parquet
is dropped (there are none among the 2022+2023 corpus per the probe).

MIN-SAMPLE FLOOR: >=500 out-of-zone called-or-swung pitches per umpire (the
metric's own denominator), same floor convention as catcher_framing_index.py.
An umpire works far more pitches per game than a single catcher across a
season slice (every plate appearance, not just a shared battery), so the
floor is expected to bind less often on games-per-umpire than on the catcher
side -- reported in the output, not tuned to a target.

CAVEAT (leak-free use): probables.parquet's snapshot_date/captured_at for the
2022/2023 rows is a 2026-07 backfill snapshot, NOT captured at-the-time of
the games (see the probe artifact). This is fine for a DESCRIPTIVE/
retrospective umpire-identity join (the game already happened, umpire
assignment is a fixed historical fact) but this index is NOT a leak-free
pre-game as-of feature and is not offered as one.

PLANTED NULL (sanity correlation, REPORTED never targeted -- mirrors
catcher_framing_index.py's shuffle_fielder2_within_game): shuffle_umpire_
within_game shuffles hp_umpire_id WITHIN each game_pk's pitch set is not
meaningful (one umpire per game), so instead this module shuffles the game_pk
-> umpire ASSIGNMENT across games (holding each game's own pitch outcomes
fixed) -- destroying the true umpire-to-outcome link while preserving each
game's real pitch-mix/park/batter composition. A downstream validity-gate
lane can consume this for a planted-null check; no correlation target is
computed or shipped by this module itself.

CORPUS: data/cache/statcast/statcast_fuller__2022.parquet (70961 rows) +
__2023.parquet (63159 rows), joined against data/domains/mlb/probables.parquet
(11105 rows) for hp_umpire_id/hp_umpire_name.

NETWORK: zero. Pure pandas over already-materialized parquets.
ACCURACY/SCOUTING ONLY -- NO MARKET EDGE CLAIMED.

CLI:
    python -m domains.mlb.umpire_zone_index
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.catcher_framing_index import (
    SEASONS,
    derive_out_of_zone,
    load_called_pitches,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

_PROBABLES = _REPO_ROOT / "data" / "domains" / "mlb" / "probables.parquet"

_OUT_DIR = _REPO_ROOT / "data" / "domains" / "mlb"
_INDEX_OUT = _OUT_DIR / "umpire_zone_index.parquet"
_REPORT_OUT = _OUT_DIR / "umpire_zone_index_report.json"

CORPUS_ID = "statcast_fuller_v1_x_probables"
MIN_OOZ_CALLED = 500  # min out-of-zone called pitches per umpire (metric denominator)


def load_umpire_lookup(probables_path: Path = _PROBABLES) -> pd.DataFrame:
    """Load game_pk -> hp_umpire_id/hp_umpire_name from probables.parquet,
    deduped to one row per game_pk (verified in the probe: no fan-out on the
    statcast-matched subset). Returns columns [game_pk, hp_umpire_id,
    hp_umpire_name]."""
    cols = ["game_pk", "hp_umpire_id", "hp_umpire_name"]
    probables = pd.read_parquet(probables_path, columns=cols)
    probables = probables.drop_duplicates(subset="game_pk", keep="last")
    return probables


def join_umpire(called: pd.DataFrame, umpire_lookup: pd.DataFrame) -> pd.DataFrame:
    """Inner-join statcast called pitches onto the umpire lookup by game_pk.
    Rows whose game_pk has no probables.parquet match are dropped (none
    expected on the 2022+2023 corpus per the probe artifact)."""
    joined = called.merge(umpire_lookup, on="game_pk", how="inner")
    return joined


def shuffle_umpire_within_season(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """PLANTED-NULL harness: shuffle the game_pk->hp_umpire_id ASSIGNMENT
    across games (one umpire label drawn per distinct game_pk, then
    broadcast back to that game's pitch rows), holding each game's own pitch
    outcomes/park/batter mix fixed. This destroys the true umpire-to-outcome
    link while preserving all game-level context. A downstream sanity check
    run on this shuffled frame must show the umpire-rate spread collapsing
    toward noise -- never targeted/optimized here, exposed for a future
    validity-gate lane to consume (mirrors catcher_framing_index.py's
    shuffle_fielder2_within_game)."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    game_pks = out["game_pk"].drop_duplicates().values
    umpire_ids = out.drop_duplicates(subset="game_pk")["hp_umpire_id"].values
    shuffled_umpire_ids = rng.permutation(umpire_ids)
    game_to_shuffled = dict(zip(game_pks, shuffled_umpire_ids))
    out["hp_umpire_id"] = out["game_pk"].map(game_to_shuffled)
    return out


def build_umpire_index(called: Optional[pd.DataFrame] = None,
                        min_ooz_called: int = MIN_OOZ_CALLED) -> tuple[pd.DataFrame, dict]:
    """Aggregate out-of-zone STRIKE rate (called-or-swung, NOT a called-strike
    /zone-consistency rate -- see module docstring) per umpire (hp_umpire_id).
    Returns (index_df, report_dict). index_df has one row per QUALIFYING
    umpire (min_ooz_called floor already applied); report_dict carries the
    full n_considered/n_excluded/join bookkeeping."""
    if called is None:
        called = load_called_pitches()
    derived = derive_out_of_zone(called)
    umpire_lookup = load_umpire_lookup()

    n_pitches_before_join = len(derived)
    joined = join_umpire(derived, umpire_lookup)
    n_pitches_after_join = len(joined)
    n_distinct_game_pks_before = called["game_pk"].nunique()
    n_distinct_game_pks_after = joined["game_pk"].nunique()

    ooz = joined[joined["out_of_zone"]].copy()

    grouped = ooz.groupby("hp_umpire_id").agg(
        n_ooz_called=("is_strike", "size"),
        ooz_strikes=("is_strike", "sum"),
    ).reset_index()
    n_considered = len(grouped)
    qualifiers = grouped[grouped["n_ooz_called"] >= min_ooz_called].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["ooz_strike_rate"] = (
        qualifiers["ooz_strikes"] / qualifiers["n_ooz_called"]
    )
    qualifiers = qualifiers.rename(columns={"hp_umpire_id": "umpire_id"})
    qualifiers = qualifiers.sort_values(
        "ooz_strike_rate", ascending=False
    ).reset_index(drop=True)

    name_lookup = dict(
        joined.drop_duplicates(subset=["hp_umpire_id"], keep="last")
        .set_index("hp_umpire_id")["hp_umpire_name"]
    )
    qualifiers["umpire_name"] = qualifiers["umpire_id"].map(
        lambda uid: name_lookup.get(uid, "Unknown")
    )

    both_available = joined[["plate_x", "plate_z", "sz_top", "sz_bot"]].notna().all(axis=1)
    geom_agreement = float(
        ((joined.loc[both_available, "out_of_zone"])
         == (joined.loc[both_available, "geom_out_of_zone"].astype(bool))).mean()
    ) if both_available.any() else None

    as_of = datetime.now(timezone.utc).isoformat()
    qualifiers["as_of"] = as_of
    qualifiers["corpus_id"] = CORPUS_ID
    qualifiers["season"] = "2022_2023"

    report = {
        "component": "umpire_zone_index",
        "metric": "ooz_strike_rate_called_or_swung",
        "metric_is_NOT_a_called_strike_or_zone_consistency_rate": True,
        "as_of": as_of,
        "corpus_id": CORPUS_ID,
        "seasons": list(SEASONS),
        "n_pitches_before_join": int(n_pitches_before_join),
        "n_pitches_after_join": int(n_pitches_after_join),
        "n_distinct_game_pks_before_join": int(n_distinct_game_pks_before),
        "n_distinct_game_pks_after_join": int(n_distinct_game_pks_after),
        "join_match_rate_pitches": float(n_pitches_after_join / n_pitches_before_join) if n_pitches_before_join else None,
        "join_match_rate_games": float(n_distinct_game_pks_after / n_distinct_game_pks_before) if n_distinct_game_pks_before else None,
        "n_umpires_considered": n_considered,
        "n_umpires_excluded_below_floor": n_excluded,
        "min_ooz_called_floor": min_ooz_called,
        "n_qualifying_umpires": len(qualifiers),
        "zone_vs_geometric_agreement_frac": geom_agreement,
        "leak_free_pregame_feature": False,
        "leak_free_caveat": "probables.parquet umpire assignment is a 2026-07 backfill snapshot, not captured at-the-time of the 2022/2023 games -- descriptive/retrospective only, see umpire_join_probe.json",
        "descriptive_only": True,
        "edge_claimed": False,
    }
    return qualifiers, report


def write_index(qualifiers: pd.DataFrame, report: dict,
                 index_out: Path = _INDEX_OUT, report_out: Path = _REPORT_OUT) -> tuple[Path, Path]:
    index_out.parent.mkdir(parents=True, exist_ok=True)
    write_cols = qualifiers[[
        "umpire_id", "umpire_name", "n_ooz_called", "ooz_strikes",
        "ooz_strike_rate", "as_of", "corpus_id", "season",
    ]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), index_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    with open(report_out, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    return index_out, report_out


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the umpire out-of-zone strike-rate (called-or-swung) descriptive index"
    )
    parser.add_argument("--min-ooz-called", type=int, default=MIN_OOZ_CALLED)
    args = parser.parse_args(argv)

    qualifiers, report = build_umpire_index(min_ooz_called=args.min_ooz_called)
    index_path, report_path = write_index(qualifiers, report)

    print(f"n_considered={report['n_umpires_considered']} "
          f"n_excluded_below_floor={report['n_umpires_excluded_below_floor']} "
          f"n_qualifying={report['n_qualifying_umpires']}")
    print(f"join_match_rate_games={report['join_match_rate_games']}")
    print(f"zone_vs_geometric_agreement_frac={report['zone_vs_geometric_agreement_frac']}")
    if len(qualifiers):
        top = qualifiers.iloc[0]
        print(f"top1: {top['umpire_name']} rate={top['ooz_strike_rate']:.4f} "
              f"n={int(top['n_ooz_called'])} (called-or-swung, NOT a called-strike rate)")
    print(f"wrote index -> {index_path}")
    print(f"wrote report -> {report_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
