"""domains.mlb.catcher_framing_index -- catcher-adjacent DESCRIPTIVE index (arm 1 of 2;
the umpire arm is a SEPARATE, later lane -- see module docstring bottom section).

METRIC (v1, descriptive only, RELABELED after FIX ROUND -- see CORRECTNESS
FIX note below): per-catcher out-of-zone STRIKE rate (called-OR-swung) --
of all pitches with type in {S,B} (Statcast's only two non-in-play codes)
that landed OUTSIDE the strike zone, what fraction were coded type=='S'.
Statcast's `type` field has exactly three values (S/B/X) and does NOT
distinguish a called strike from a swinging strike or a foul ball -- all
three are type=='S'. THIS METRIC THEREFORE MEASURES "how often pitches this
catcher receives, when out of zone, end up strikes by any means (called,
swung, or fouled)" -- NOT a called-strike/framing rate. It is confounded by
BATTER chase/whiff behavior (a batter/pitcher property) and is NOT a framing
proxy. Framing cannot be computed from this corpus (see CORRECTNESS FIX).
This is NOT a predictive claim and NOT a market edge -- see NO EDGE CLAIMS.

CORRECTNESS FIX (this round): the original v1 spec assumed a `type=='C'`
called-strike code and an isolatable called-strike subset; NEITHER exists on
this corpus. Verified live this session: type value_counts on the full
2022+2023 corpus are S=62226 / B=48233 / X=23661 -- no 'C'. The `des` column
(free-text event description) only populates on TERMINAL pitches of an
at-bat (strikeouts, walks, balls in play) -- verified live: 9.8% coverage on
called pitches (type in {S,B}), and of the out-of-zone type=='S' pitches
that DO carry a des, ~92% read "strikes out swinging" (a swing), only ~8%
are a genuine called third strike. There is no column on this corpus that
isolates a called strike from a swinging strike or a foul within type=='S'.
Rather than ship a mislabeled "framing" claim, this module computes and
labels the metric it can actually support: out-of-zone strike rate
(called-or-swung), with the chase-rate confound stated explicitly wherever
the metric is surfaced. A genuine framing index would require a re-pull with
a pitch-call/description column (e.g. `description` with 'called_strike' /
'swinging_strike' / 'foul' distinct values) and is NOT built here.

OUT-OF-ZONE DETERMINATION: derived from `zone` (PRIMARY, MLB's own 1-9
in-zone / 11-14 out-of-zone classification), cross-checked against the
geometric plate_x/z-vs-sz_top/bot rectangle (verified live this session:
95.5-95.9% agreement on the 2022+2023 corpus -- the residual is edge-
convention rounding in MLB's own zone grid, not a data-quality problem).
`zone` is used as the primary out-of-zone determination per the LANE spec's
explicit ordering ("zone... and plate_x/z vs sz_top/bot for the out-of-zone
determination"); the geometric predicate is computed alongside and its
agreement fraction is reported in the output report, never silently dropped.
`des` is NEVER used for the strike/ball or zone determination (only 9.8-25.6%
coverage depending on the slice -- a free-text event parser silently drops
most rows and, per the CORRECTNESS FIX above, cannot cleanly isolate called
strikes at scale even where it IS present).

CORPUS: data/cache/statcast/statcast_fuller__2022.parquet (70961 rows) +
__2023.parquet (63159 rows) -- verified live this session: zone 99.6-99.8%,
type 100%, fielder_2 (catcher MLBAM id) 100%, plate_x/z ~99.7%, sz_top/bot
present. fielder_2 is the entity_key (catcher, not pitcher).

MIN-SAMPLE FLOOR: >=500 OUT-OF-ZONE called-or-swung pitches per catcher (the
metric's own denominator) -- verified live this session: 107 distinct
catchers total, 74 clear >=500 on the TOTAL-called-pitch reading, 54 clear it
on the stricter out-of-zone-only reading used here (mean out-of-zone
called-or-swung pitches/catcher ~1032, close to the ~1300 estimate in the
LANE spec). The floor is applied to the denominator of the ranked metric,
matching the mlb_pitcher_claims.py / tennis_hold_claims.py precedent (floor
on the metric's own sample size).

NAME LOOKUP: fielder_2 (catcher MLBAM id) resolves 107/107 against
data/domains/mlb/player_gamelogs.parquet's player_id/player columns (verified
live this session) -- same MLBAM id scheme, no bridge needed.

PLANTED NULL (sanity correlation, REPORTED never targeted -- see LANE spec):
shuffling fielder_2 WITHIN game (so each catcher's true out-of-zone-strike
signal is destroyed but game-level umpire/park/batter-mix effects are
preserved) must make any downstream sanity correlation vanish. This module
exposes
`shuffle_fielder2_within_game` for that purpose; no correlation target is
computed or shipped by this module itself (that lives in a future validity-
gate lane, mirroring domains/basketball_nba/quality_validity_gate.py's split
from quality_indices.py).

UMPIRE ARM (separate, later lane -- probe only, nothing built here):
verified live this session that domains/mlb/game_pk_bridge.py's game_pk<->
event_id bridge is NOT needed for the umpire arm -- data/domains/mlb/
probables.parquet already carries hp_umpire_id keyed DIRECTLY on the same
raw MLB game_pk statcast uses (no bridge). Overlap check: 460/460 (100%) of
the statcast 2022+2023 corpus's distinct game_pks have a matching row in
probables.parquet, one row per game_pk (no doubleheader ambiguity in this
slice), hp_umpire_id non-null in 100% of those rows. CAVEAT for the human
umpire-arm decision: probables.parquet's own snapshot_date/captured_at for
those rows is 2026-07-02..07-04 (a backfill snapshot taken now), NOT captured
at-the-time of the 2022/2023 games -- fine for a DESCRIPTIVE/retrospective
umpire-identity join (the game already happened, umpire assignment is a fixed
historical fact), but NOT usable as a leak-free pre-game as-of feature without
a separately-verified as-of-capture history. Nothing built for this arm this
wave -- descriptive catcher-only index below is the full deliverable.

NETWORK: zero. Pure pandas over already-materialized parquets.
ACCURACY/SCOUTING ONLY -- NO MARKET EDGE CLAIMED.

CLI:
    python -m domains.mlb.catcher_framing_index
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

_REPO_ROOT = Path(__file__).resolve().parents[2]

_STATCAST_2022 = _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet"
_STATCAST_2023 = _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet"
_GAMELOGS = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

_OUT_DIR = _REPO_ROOT / "data" / "domains" / "mlb"
_INDEX_OUT = _OUT_DIR / "catcher_framing_index.parquet"
_REPORT_OUT = _OUT_DIR / "catcher_framing_index_report.json"

CORPUS_ID = "statcast_fuller_v1"
SEASONS = (2022, 2023)
MIN_OOZ_CALLED = 500  # min out-of-zone called pitches per catcher (metric denominator)

# plate half-width + ball-radius proxy for the geometric out-of-zone cross-check
# (MLB's own `zone` field is the PRIMARY signal; this is a reported agreement
# check only, never substituted in).
_PLATE_HALF_WIDTH_FT = 0.83


def load_called_pitches(seasons: tuple = SEASONS) -> pd.DataFrame:
    """Load + concat the fuller statcast parquets, keep only non-in-play
    pitches (type in {S,B} -- Statcast's only two codes for a pitch that
    was NOT put in play; balls in play (type=='X') are excluded). NOTE:
    type=='S' bundles called strikes + swinging strikes + fouls -- there is
    no code that isolates a called strike alone (see module docstring
    CORRECTNESS FIX)."""
    frames = []
    paths = {2022: _STATCAST_2022, 2023: _STATCAST_2023}
    for season in seasons:
        path = paths[season]
        df = pd.read_parquet(path)
        df["season"] = season
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    called = combined[combined["type"].isin(["S", "B"])].copy()
    return called


def derive_out_of_zone(called: pd.DataFrame) -> pd.DataFrame:
    """Derive the out-of-zone predicate from `zone` (PRIMARY, MLB's own 1-9
    in-zone / 11-14 out-of-zone classification) and compute the geometric
    plate_x/z-vs-sz_top/bot cross-check alongside (reported, not substituted).
    NEVER uses `des` (9.8-25.6% coverage depending on slice -- see module
    docstring). `is_strike` = type=='S', which is called-strike OR swinging-
    strike OR foul -- Statcast has no code that isolates a called strike
    alone on this corpus (see module docstring CORRECTNESS FIX)."""
    out = called.copy()
    out["is_strike"] = (out["type"] == "S").astype(int)
    out["out_of_zone"] = out["zone"] >= 11

    geom_available = out[["plate_x", "plate_z", "sz_top", "sz_bot"]].notna().all(axis=1)
    geom_in_zone = (
        (out["plate_x"].abs() <= _PLATE_HALF_WIDTH_FT)
        & (out["plate_z"] >= out["sz_bot"])
        & (out["plate_z"] <= out["sz_top"])
    )
    out["geom_out_of_zone"] = np.where(geom_available, ~geom_in_zone, np.nan)
    return out


def shuffle_fielder2_within_game(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """PLANTED-NULL harness: shuffle fielder_2 (catcher id) WITHIN each game_pk
    so each row keeps its real game-level context (umpire, park, pitch mix)
    but loses the TRUE catcher-to-outcome link. A downstream sanity check run
    on this shuffled frame must show the framing-rate spread collapsing toward
    noise -- never targeted/optimized here, exposed for a future validity-gate
    lane to consume (mirrors quality_validity_gate.py's planted-null pattern)."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    for _, idx in out.groupby("game_pk").groups.items():
        idx = np.asarray(idx)
        if len(idx) < 2:
            continue
        shuffled = rng.permutation(out.loc[idx, "fielder_2"].values)
        out.loc[idx, "fielder_2"] = shuffled
    return out


def build_catcher_index(called: Optional[pd.DataFrame] = None,
                         min_ooz_called: int = MIN_OOZ_CALLED) -> tuple[pd.DataFrame, dict]:
    """Aggregate out-of-zone STRIKE rate (called-or-swung, NOT a called-strike
    /framing rate -- see module docstring CORRECTNESS FIX) per catcher
    (fielder_2). Returns (index_df, report_dict). index_df has one row per
    QUALIFYING catcher (min_ooz_called floor already applied); report_dict
    carries the full n_considered/n_excluded/geometric-agreement bookkeeping."""
    if called is None:
        called = load_called_pitches()
    derived = derive_out_of_zone(called)
    ooz = derived[derived["out_of_zone"]].copy()

    grouped = ooz.groupby("fielder_2").agg(
        n_ooz_called=("is_strike", "size"),
        ooz_strikes=("is_strike", "sum"),
    ).reset_index()
    n_considered = len(grouped)
    qualifiers = grouped[grouped["n_ooz_called"] >= min_ooz_called].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["ooz_strike_rate"] = (
        qualifiers["ooz_strikes"] / qualifiers["n_ooz_called"]
    )
    qualifiers = qualifiers.rename(columns={"fielder_2": "catcher_id"})
    qualifiers = qualifiers.sort_values(
        "ooz_strike_rate", ascending=False
    ).reset_index(drop=True)

    names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
    name_lookup = dict(
        names.drop_duplicates(subset=["player_id"], keep="last")
        .set_index("player_id")["player"]
    )
    qualifiers["catcher_name"] = qualifiers["catcher_id"].map(
        lambda cid: name_lookup.get(int(cid), "Unknown")
    )

    both_available = derived[["plate_x", "plate_z", "sz_top", "sz_bot"]].notna().all(axis=1)
    geom_agreement = float(
        ((derived.loc[both_available, "out_of_zone"])
         == (derived.loc[both_available, "geom_out_of_zone"].astype(bool))).mean()
    ) if both_available.any() else None

    as_of = datetime.now(timezone.utc).isoformat()
    qualifiers["as_of"] = as_of
    qualifiers["corpus_id"] = CORPUS_ID
    qualifiers["season"] = "2022_2023"  # spans both fuller-statcast seasons

    report = {
        "component": "catcher_framing_index",
        "metric": "ooz_strike_rate_called_or_swung",
        "metric_is_NOT_a_called_strike_or_framing_rate": True,
        "as_of": as_of,
        "corpus_id": CORPUS_ID,
        "seasons": list(SEASONS),
        "n_catchers_considered": n_considered,
        "n_catchers_excluded_below_floor": n_excluded,
        "min_ooz_called_floor": min_ooz_called,
        "n_qualifying_catchers": len(qualifiers),
        "zone_vs_geometric_agreement_frac": geom_agreement,
        "des_coverage_frac_NOT_USED": float(called["des"].notna().mean()) if "des" in called.columns else None,
        "descriptive_only": True,
        "edge_claimed": False,
    }
    return qualifiers, report


def write_index(qualifiers: pd.DataFrame, report: dict,
                 index_out: Path = _INDEX_OUT, report_out: Path = _REPORT_OUT) -> tuple[Path, Path]:
    index_out.parent.mkdir(parents=True, exist_ok=True)
    write_cols = qualifiers[[
        "catcher_id", "catcher_name", "n_ooz_called", "ooz_strikes",
        "ooz_strike_rate", "as_of", "corpus_id", "season",
    ]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), index_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    with open(report_out, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    return index_out, report_out


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the catcher out-of-zone strike-rate (called-or-swung) descriptive index"
    )
    parser.add_argument("--min-ooz-called", type=int, default=MIN_OOZ_CALLED)
    args = parser.parse_args(argv)

    qualifiers, report = build_catcher_index(min_ooz_called=args.min_ooz_called)
    index_path, report_path = write_index(qualifiers, report)

    print(f"n_considered={report['n_catchers_considered']} "
          f"n_excluded_below_floor={report['n_catchers_excluded_below_floor']} "
          f"n_qualifying={report['n_qualifying_catchers']}")
    print(f"zone_vs_geometric_agreement_frac={report['zone_vs_geometric_agreement_frac']}")
    if len(qualifiers):
        top = qualifiers.iloc[0]
        print(f"top1: {top['catcher_name']} rate={top['ooz_strike_rate']:.4f} "
              f"n={int(top['n_ooz_called'])} (called-or-swung, NOT a called-strike rate)")
    print(f"wrote index -> {index_path}")
    print(f"wrote report -> {report_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
