"""domains.mlb.matchup.pitch_mix_profiles -- per pitcher-season / batter-season
RESPONSE SURFACES: pitch-type usage mix, zone tendency, and a putaway-swinging
proxy. These feed pa_outcome_model.py's interaction feature.

CORPUS LIMIT (verified live this session against the CURRENT on-disk files,
statcast_fuller__2022.parquet=710509 rows / __2023.parquet=720984 rows -- FULL
2022+2023 seasons; these have been backfilled to full-season since
domains/mlb/platoon_split_index.py's docstring was written, which still
describes an 18-day sample window -- this module reads the current full
files): `type` (S/B/X) does not separate a called strike from a swinging
strike or a foul, and there is still no per-pitch `description` column on
this corpus (independently confirmed by catcher_framing_index.py and
scripts/platformkit/intel_validation/mlb_plate_discipline_claims.py, which
mark pitcher_whiff_rate/batter_chase_rate/batter_whiff_rate CORPUS_ABSENT --
this module does not re-attempt that derivation). `des` IS populated on
every PA-TERMINAL row (100% coverage where events.notna(): 0 nulls / 40834 K
rows checked in 2022) as a free-text sentence -- "... strikes out swinging.",
"... called out on strikes.", "... strikes out on a foul tip." -- which DOES
let us tell a swinging strikeout from a called strikeout on the PA-ending
pitch specifically (the ONLY per-pitch swing signal this corpus supports).
So "whiff rate by pitch type" is scoped down to PUTAWAY_SWINGING_SHARE: of
the strikeouts thrown/taken on a given pitch type, what fraction end
swinging vs looking. Real signal, narrower than true whiff%, honestly
labeled -- never called a whiff rate in any output.

RESPONSE SURFACES SHIPPED:
per (pitcher, season, pitch_type): usage_share, in_zone_rate (zone in
{1..9} vs {11..14}, ~0.35% null-zone pitches dropped, matching
mlb_plate_discipline_claims.py's convention), strike_rate (type=='S' rate --
called+swinging+foul conflated, NOT a whiff rate, matching
catcher_framing_index.py's ooz_strike_rate precedent), n_k,
putaway_swinging_share.
per (batter, season, pitch_type) -- terminal pitch of each PA only: n_pa,
k_rate, bb_rate (walk+intent_walk+hit_by_pitch), on_base_rate, slug_proxy
(total bases / PA: 1/2/3/4 for 1B/2B/3B/HR else 0), n_k,
putaway_swinging_share.

WINDOW: seasons 2022+2023. NETWORK: zero.
DESCRIPTIVE RESPONSE SURFACE ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI: python -m domains.mlb.matchup.pitch_mix_profiles
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

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATCAST = {
    2022: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet",
    2023: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet",
}
_OUT_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "matchup"
_PITCHER_OUT = _OUT_DIR / "pitcher_pitch_profiles.parquet"
_BATTER_OUT = _OUT_DIR / "batter_pitch_profiles.parquet"
_REPORT_OUT = _OUT_DIR / "pitch_mix_profiles_report.json"

SEASONS = (2022, 2023)
IN_ZONE_CODES = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9})
_K_EVENTS = {"strikeout", "strikeout_double_play"}
_BB_EVENTS = {"walk", "intent_walk", "hit_by_pitch"}
_ON_BASE_EVENTS = {"single", "double", "triple", "home_run"} | _BB_EVENTS
_TOTAL_BASES = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
_LOOKING_MARKER = "called out on strikes"
_PITCH_COLS = ["pitcher", "batter", "pitch_type", "zone", "type", "des", "events"]


def load_pitch_rows(seasons: tuple = SEASONS) -> pd.DataFrame:
    """Load + concat statcast pitch-level rows for the given seasons,
    dropping unresolved pitch_type."""
    frames = []
    for season in seasons:
        df = pd.read_parquet(_STATCAST[season], columns=_PITCH_COLS)
        df["season"] = season
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined["pitch_type"].notna() & (combined["pitch_type"] != "None")]
    return combined


def classify_terminal_k(des: pd.Series, events: pd.Series) -> pd.Series:
    """'swinging' / 'looking' / None per row -- only meaningful on K rows.
    See CORPUS LIMIT above: this is the only per-pitch swing/take signal
    this corpus supports."""
    is_k = events.isin(_K_EVENTS)
    looking = is_k & des.str.lower().str.contains(_LOOKING_MARKER, na=False)
    return pd.Series(np.where(is_k, np.where(looking, "looking", "swinging"), None), index=des.index)


def build_pitcher_profile(rows: pd.DataFrame) -> pd.DataFrame:
    df = rows.copy()
    df["is_strike"] = (df["type"] == "S").astype(int)
    df["zone_resolved"] = df["zone"].notna()
    df["in_zone"] = df["zone"].fillna(-1).astype(int).isin(IN_ZONE_CODES).astype(int)
    df["k_class"] = classify_terminal_k(df["des"], df["events"])

    total = df.groupby(["pitcher", "season"]).size().rename("n_pitches_total").reset_index()
    by_pt = df.groupby(["pitcher", "season", "pitch_type"]).agg(
        n_pitches=("type", "size"),
        n_strikes=("is_strike", "sum"),
        n_zone_resolved=("zone_resolved", "sum"),
        n_in_zone=("in_zone", "sum"),
    ).reset_index()
    by_pt = by_pt.merge(total, on=["pitcher", "season"])
    by_pt["usage_share"] = by_pt["n_pitches"] / by_pt["n_pitches_total"]
    by_pt["strike_rate"] = by_pt["n_strikes"] / by_pt["n_pitches"]
    by_pt["in_zone_rate"] = by_pt["n_in_zone"] / by_pt["n_zone_resolved"].replace(0, np.nan)

    k_rows = df[df["k_class"].notna()]
    k_agg = k_rows.groupby(["pitcher", "season", "pitch_type"]).agg(
        n_k=("k_class", "size"),
        n_k_swinging=("k_class", lambda s: (s == "swinging").sum()),
    ).reset_index()
    by_pt = by_pt.merge(k_agg, on=["pitcher", "season", "pitch_type"], how="left")
    by_pt["n_k"] = by_pt["n_k"].fillna(0).astype(int)
    by_pt["n_k_swinging"] = by_pt["n_k_swinging"].fillna(0).astype(int)
    by_pt["putaway_swinging_share"] = np.where(
        by_pt["n_k"] > 0, by_pt["n_k_swinging"] / by_pt["n_k"], np.nan
    )
    return by_pt


def build_batter_profile(rows: pd.DataFrame) -> pd.DataFrame:
    pa_rows = rows[rows["events"].notna()].copy()
    pa_rows["is_k"] = pa_rows["events"].isin(_K_EVENTS).astype(int)
    pa_rows["is_bb"] = pa_rows["events"].isin(_BB_EVENTS).astype(int)
    pa_rows["on_base"] = pa_rows["events"].isin(_ON_BASE_EVENTS).astype(int)
    pa_rows["tb"] = pa_rows["events"].map(_TOTAL_BASES).fillna(0)
    pa_rows["k_class"] = classify_terminal_k(pa_rows["des"], pa_rows["events"])

    agg = pa_rows.groupby(["batter", "season", "pitch_type"]).agg(
        n_pa=("events", "size"),
        n_k=("is_k", "sum"),
        n_bb=("is_bb", "sum"),
        n_on_base=("on_base", "sum"),
        total_bases=("tb", "sum"),
    ).reset_index()
    agg["k_rate"] = agg["n_k"] / agg["n_pa"]
    agg["bb_rate"] = agg["n_bb"] / agg["n_pa"]
    agg["on_base_rate"] = agg["n_on_base"] / agg["n_pa"]
    agg["slug_proxy"] = agg["total_bases"] / agg["n_pa"]

    k_rows = pa_rows[pa_rows["k_class"].notna()]
    k_agg = k_rows.groupby(["batter", "season", "pitch_type"]).agg(
        n_k_swinging=("k_class", lambda s: (s == "swinging").sum()),
    ).reset_index()
    agg = agg.merge(k_agg, on=["batter", "season", "pitch_type"], how="left")
    agg["n_k_swinging"] = agg["n_k_swinging"].fillna(0).astype(int)
    agg["putaway_swinging_share"] = np.where(
        agg["n_k"] > 0, agg["n_k_swinging"] / agg["n_k"], np.nan
    )
    return agg


def write_profiles(pitcher_profile: pd.DataFrame, batter_profile: pd.DataFrame,
                    out_dir: Path = _OUT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(pitcher_profile, preserve_index=False), _PITCHER_OUT)
    pq.write_table(pa.Table.from_pandas(batter_profile, preserve_index=False), _BATTER_OUT)

    report = {
        "component": "pitch_mix_profiles",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS),
        "n_pitcher_season_pitchtype_rows": int(len(pitcher_profile)),
        "n_batter_season_pitchtype_rows": int(len(batter_profile)),
        "n_pitchers": int(pitcher_profile["pitcher"].nunique()),
        "n_batters": int(batter_profile["batter"].nunique()),
        "putaway_swinging_share_is_not_whiff_rate": True,
        "descriptive_only": True,
        "edge_claimed": False,
    }
    with open(_REPORT_OUT, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    return report


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Build MLB pitch-mix response-surface profiles")
    parser.parse_args(argv)

    rows = load_pitch_rows()
    pitcher_profile = build_pitcher_profile(rows)
    batter_profile = build_batter_profile(rows)
    report = write_profiles(pitcher_profile, batter_profile)

    print(f"pitcher rows={report['n_pitcher_season_pitchtype_rows']} "
          f"pitchers={report['n_pitchers']}")
    print(f"batter rows={report['n_batter_season_pitchtype_rows']} "
          f"batters={report['n_batters']}")
    print(f"wrote -> {_PITCHER_OUT}")
    print(f"wrote -> {_BATTER_OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
