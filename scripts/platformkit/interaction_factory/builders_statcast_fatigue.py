"""scripts.platformkit.interaction_factory.builders_statcast_fatigue -- B1:
MLB starting-pitcher IN-GAME FATIGUE builders (mlb_sp_ingame_fatigue_self_cross,
mlb_sp_fatigue_state_conditioner templates), split out per the builders_
carryover.py / builders_ingame_state.py / builders_state_conditioner.py
convention (keeps runner.py under its LOC budget). Same contract as any other
runner builder: `builder(attrs, tpl) -> {"frame", "cluster", "corpus", "kind",
...} | None` -- registered into runner._BUILDERS by runner.py itself.

SOURCES: data/cache/statcast/statcast_fuller__2022.parquet and __2023.parquet
-- the only 2 files in that name family on disk (M20's statcast_refresh_job
maintains savant_full__<season>.parquet instead, a DIFFERENT file family --
confirmed via ls, no newer statcast_fuller__ file exists). Schemas differ
slightly across the 2 files (2023 lacks `description`; NEITHER carries
`release_extension`) -- every column read is OPTIONAL (present-or-NaN-
stand-in), same pattern commit a0c6da5f established for zone/type/spin/stand.

ATOMIC UNIT: one row per (game_pk, pitcher, checkpoint) -- checkpoint in
CHECKPOINTS, a fixed pitch-count list (own design choice, no task-declared
value; relievers who never reach a checkpoint honestly drop that row, never
invented). OUTCOME: `rest_of_appearance_xwoba` -- mean(estimated_woba_using_
speedangle) over this SAME appearance's pitches strictly AFTER the checkpoint
(a REAL, not as-of, label -- only features need to be leak-free, same as
builders_ingame_state.py's rest_of_game_margin). NOTE this is a BIP-only xwOBA
proxy (Statcast has no raw woba_value/denom column here, same absence
mlb_tto_claims.py documents) -- honest, not a full wOBA-against.

ATTRS (2 families):
 * IN-GAME FATIGUE STATE (realized, checkpoint-local; STATIC_POOLS key
   "mlb_sp_ingame_fatigue_state"): velo_delta_by_pitch_count / spin_delta_
   by_pitch_count / release_extension_delta = expanding mean(pitches 1..k of
   TODAY's appearance) minus the SAME appearance's first-15-pitch baseline;
   times_through_order = the TTO bucket (1/2/3+, mlb_tto_claims.py's own
   cumcount convention) of the plate appearance containing pitch k.
 * PRIOR-GAMES PRIOR (STATIC_POOLS key "mlb_sp_fatigue_prior"):
   woba_tto3_minus_tto1 = this pitcher's cross-game EXPANDING split
   (mean xwoba at TTO3+ minus TTO1), cumsum-shifted so a game's own row uses
   ONLY games strictly before it (a plain LAG-1-style carryover stat, same
   shape as builders_carryover.py's SP priors) -- pairs against the state
   family in the state-conditioner cross (nba_state_conditioner pattern,
   85a8ee80/a0c6da5f: "condition a pregame prior on a realized-state attr").

Both attribute families are declared as generator.STATIC_POOLS entries (the
tennis/soccer seam) rather than domains/mlb/profiles/attribute_registry.py
rows -- that file is outside this lane's OWNS, and STATIC_POOLS already
exists precisely for a pool served without a per-sport ATTRIBUTES registry
lookup (see generator.resolve_pool's `static_pool` key).

LEAK RULE (binding): an attribute at pitch k of today's game uses ONLY
pitches 1..k of today (state family, via a checkpoint-truncated expanding
window -- literally cannot see game_pitch_seq>k) plus games strictly before
today (prior family, via cumsum().shift(1) per pitcher ordered by game_date --
same idiom build_mlb_pa_frame's platoon_split uses). See
test_builders_statcast_fatigue.py's shifted-cumsum trap tests.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_statcast_fatigue.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
_STATCAST_2022 = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet"
_STATCAST_2023 = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet"
_STATCAST_SOURCES = (_STATCAST_2022, _STATCAST_2023)
_FATIGUE_CORPUS = "statcast_fuller_sp_fatigue"

BASELINE_PITCHES = 15    # task-declared: "FIRST-15-pitch baseline of the SAME appearance"
CHECKPOINTS = (30, 45, 60, 75, 90)   # own design choice -- typical SP pitch-count checkpoints
MIN_PRIOR_PA_TTO = 60    # matches attribute_registry.py TTO_durability / mlb_tto_claims.py MIN_PA_PER_BUCKET precedent

_NEEDED_COLS = ["game_pk", "game_date", "at_bat_number", "pitch_number", "pitcher", "batter",
                "release_speed", "release_spin_rate", "estimated_woba_using_speedangle"]
_OPTIONAL_COLS = ["release_extension"]   # absent from statcast_fuller__2022/2023 -- honest NaN stand-in, never invented


def _read_one(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    cols = [c for c in _NEEDED_COLS if c in df.columns] + [c for c in _OPTIONAL_COLS if c in df.columns]
    return df[cols]


def read_combined_source(sources=_STATCAST_SOURCES) -> pd.DataFrame:
    """Concat statcast_fuller__2022 + __2023 (only 2 files in the family on
    disk) with each file's own present-columns honestly preserved."""
    return pd.concat([_read_one(p) for p in sources], ignore_index=True)


def _prep_pitches(pitch_df: pd.DataFrame) -> pd.DataFrame:
    """Sort to appearance-chronological order and attach 2 pitch-level keys:
    game_pitch_seq (1-indexed position within this pitcher's appearance --
    the LEAK boundary every checkpoint truncates at) and _tto_bucket (the
    containing PA's times-through-the-order bucket, 1/2/3+, broadcast to every
    pitch of that PA -- mlb_tto_claims.py's own cumcount(game_pk,pitcher,
    batter) convention, reused)."""
    d = pitch_df.sort_values(["game_pk", "pitcher", "at_bat_number", "pitch_number"]).reset_index(drop=True)
    d["game_pitch_seq"] = d.groupby(["game_pk", "pitcher"], sort=False).cumcount() + 1
    d["_ext"] = d["release_extension"] if "release_extension" in d.columns else float("nan")
    pa_first = d.drop_duplicates(["game_pk", "pitcher", "at_bat_number"], keep="first")[
        ["game_pk", "pitcher", "batter", "at_bat_number"]].sort_values(["game_pk", "pitcher", "at_bat_number"])
    pa_first["_times_faced"] = pa_first.groupby(["game_pk", "pitcher", "batter"], sort=False).cumcount() + 1
    pa_first["_tto_bucket"] = pa_first["_times_faced"].clip(upper=3).astype(float)
    return d.merge(pa_first[["game_pk", "pitcher", "at_bat_number", "_tto_bucket"]],
                    on=["game_pk", "pitcher", "at_bat_number"], how="left")


def build_mlb_fatigue_checkpoint_frame(pitch_df: pd.DataFrame, attrs: List[str],
                                        checkpoints=CHECKPOINTS,
                                        baseline_pitches: int = BASELINE_PITCHES) -> pd.DataFrame:
    """Per-(game_pk, pitcher, checkpoint) frame: y = rest_of_appearance_xwoba
    (real, this appearance's own pitches after k), asof__<attr> for whichever
    of the 4 realized-state attrs are requested. A checkpoint an appearance
    never reached honestly has no row (never invented)."""
    d = _prep_pitches(pitch_df)
    grp = d.groupby(["game_pk", "pitcher"], sort=False)
    d["_velo_cum"] = grp["release_speed"].transform(lambda s: s.expanding().mean())
    d["_spin_cum"] = grp["release_spin_rate"].transform(lambda s: s.expanding().mean())
    d["_ext_cum"] = grp["_ext"].transform(lambda s: s.expanding().mean())

    is_base = d["game_pitch_seq"] <= baseline_pitches
    base = d[is_base].groupby(["game_pk", "pitcher"]).agg(
        _velo_base=("release_speed", "mean"), _n_base_velo=("release_speed", "count"),
        _spin_base=("release_spin_rate", "mean"), _n_base_spin=("release_spin_rate", "count"),
        _ext_base=("_ext", "mean"), _n_base_ext=("_ext", "count"),
    ).reset_index()

    empty = pd.DataFrame(columns=["game_pk", "pitcher", "checkpoint", "y"])
    rows = []
    for k in checkpoints:
        at_k = d.loc[d["game_pitch_seq"] == k,
                      ["game_pk", "pitcher", "_velo_cum", "_spin_cum", "_ext_cum", "_tto_bucket"]]
        if at_k.empty:
            continue
        after = d.loc[d["game_pitch_seq"] > k].groupby(["game_pk", "pitcher"])[
            "estimated_woba_using_speedangle"].mean().reset_index(name="y")
        row = at_k.merge(base, on=["game_pk", "pitcher"], how="left").merge(
            after, on=["game_pk", "pitcher"], how="left")
        row["checkpoint"] = k
        rows.append(row)
    if not rows:
        return empty
    out = pd.concat(rows, ignore_index=True)

    for cum_col, base_col, n_col, attr in [
        ("_velo_cum", "_velo_base", "_n_base_velo", "velo_delta_by_pitch_count"),
        ("_spin_cum", "_spin_base", "_n_base_spin", "spin_delta_by_pitch_count"),
        ("_ext_cum", "_ext_base", "_n_base_ext", "release_extension_delta"),
    ]:
        if attr in attrs:
            out["asof__" + attr] = (out[cum_col] - out[base_col]).where(out[n_col] >= baseline_pitches)
    if "times_through_order" in attrs:
        out["asof__times_through_order"] = out["_tto_bucket"]

    keep = ["game_pk", "pitcher", "checkpoint", "y"] + [
        "asof__" + a for a in attrs if ("asof__" + a) in out.columns]
    return out[keep] if keep else empty


def build_mlb_fatigue_prior_frame(pitch_df: pd.DataFrame,
                                   min_prior_pa: int = MIN_PRIOR_PA_TTO) -> pd.DataFrame:
    """Per-(game_pk, pitcher) frame: asof__woba_tto3_minus_tto1 = this
    pitcher's cross-game EXPANDING (mean xwoba at TTO3+) minus (mean xwoba at
    TTO1), cumsum-shifted per pitcher ordered by game_date so a game's own row
    uses ONLY games strictly before it (build_mlb_pa_frame's platoon_split
    cumsum-shift idiom, at GAME granularity instead of PA granularity)."""
    d = _prep_pitches(pitch_df)
    pa = d.groupby(["game_pk", "pitcher", "at_bat_number"], sort=False).agg(
        game_date=("game_date", "first"),
        xwoba=("estimated_woba_using_speedangle", "last"),
        tto_bucket=("_tto_bucket", "first"),
    ).reset_index()
    pa = pa.sort_values(["pitcher", "game_date", "game_pk"]).reset_index(drop=True)

    game = pa.groupby(["pitcher", "game_date", "game_pk"], sort=False).apply(lambda g: pd.Series({
        "sum_tto1": g.loc[g["tto_bucket"] == 1, "xwoba"].sum(),
        "n_tto1": g.loc[g["tto_bucket"] == 1, "xwoba"].notna().sum(),
        "sum_tto3": g.loc[g["tto_bucket"] == 3, "xwoba"].sum(),
        "n_tto3": g.loc[g["tto_bucket"] == 3, "xwoba"].notna().sum(),
    }), include_groups=False).reset_index()
    if game.empty:
        return pd.DataFrame(columns=["game_pk", "pitcher", "asof__woba_tto3_minus_tto1"])
    game = game.sort_values(["pitcher", "game_date", "game_pk"]).reset_index(drop=True)
    ggrp = game.groupby("pitcher", sort=False)
    cum_sum1 = ggrp["sum_tto1"].transform(lambda s: s.cumsum().shift(1))
    cum_n1 = ggrp["n_tto1"].transform(lambda s: s.cumsum().shift(1))
    cum_sum3 = ggrp["sum_tto3"].transform(lambda s: s.cumsum().shift(1))
    cum_n3 = ggrp["n_tto3"].transform(lambda s: s.cumsum().shift(1))
    rate1 = cum_sum1 / cum_n1.where(cum_n1 >= min_prior_pa)
    rate3 = cum_sum3 / cum_n3.where(cum_n3 >= min_prior_pa)
    game["asof__woba_tto3_minus_tto1"] = rate3 - rate1
    return game[["game_pk", "pitcher", "asof__woba_tto3_minus_tto1"]]


def _mlb_sp_ingame_fatigue_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not all(p.exists() for p in _STATCAST_SOURCES):
        return None
    pitch_df = read_combined_source()
    frame = build_mlb_fatigue_checkpoint_frame(pitch_df, attrs)
    return {"frame": frame, "cluster": "pitcher", "corpus": _FATIGUE_CORPUS, "kind": "ols"}


def _mlb_sp_fatigue_state_conditioner_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not all(p.exists() for p in _STATCAST_SOURCES):
        return None
    pitch_df = read_combined_source()
    state_attrs = [a for a in attrs if a != "woba_tto3_minus_tto1"]
    ck = build_mlb_fatigue_checkpoint_frame(pitch_df, state_attrs)
    prior = build_mlb_fatigue_prior_frame(pitch_df)
    out = ck.merge(prior, on=["game_pk", "pitcher"], how="left")
    return {"frame": out, "cluster": "pitcher", "corpus": _FATIGUE_CORPUS, "kind": "ols"}


__all__ = [
    "read_combined_source", "build_mlb_fatigue_checkpoint_frame", "build_mlb_fatigue_prior_frame",
    "_mlb_sp_ingame_fatigue_builder", "_mlb_sp_fatigue_state_conditioner_builder",
    "CHECKPOINTS", "BASELINE_PITCHES", "MIN_PRIOR_PA_TTO",
]
