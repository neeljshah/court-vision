"""domains.mlb.pitch_engine.corpus -- shared loader + bucket/label helpers for the
MLB PITCH-LEVEL engine (the analogue of the NBA possession sim2 corpus).

The pitch IS baseball's possession. This module turns the raw Statcast savant
parquet into two leak-free frames the empirical models fit on:

  * a PITCH frame: every pitch with its class, zone bucket, count/platoon/base
    buckets, and a 10-way per-pitch OUTCOME label
    {ball, called_strike, swinging_strike, foul, in_play_out, single, double,
     triple, hr, hbp};
  * a PA frame: one row per plate appearance (the terminal pitch) with its 8-way
    PA-event label {OUT,K,BB,HBP,1B,2B,3B,HR}, runs scored on the play, and the
    start base-out state (0..23) -- the inputs the game MC's base-out transition
    needs.

"AS-OF" DESIGN (declared, leak-free): the primary validation fits every table on
the FULL prior season (2023) and applies it to the held-out season (2024). 2023
wholly precedes 2024, so a 2024 pitch/PA/game is scored with zero 2024
information -- no within-season expanding is needed. Within-season expanding is a
v2 seam (see selection.py). The 2025/2026 parquets are being backfilled by a
detached process and are NOT read here.

Buckets (all coarse on purpose -- keeps empirical cells dense):
  pitch_class : FB / BR / OS   (fastballs / breaking / offspeed)
  zone_bucket : IZ / OZ        (statcast zone 1-9 in-zone vs 11-14 out)
  count       : 0..11          (balls 0-3) * 3 + (strikes 0-2)
  platoon     : 0..3           (p_throws in {R,L}) * 2 + (stand in {R,L})
  base_bucket : EMP / ON1 / RISP  (bases empty / runner on 1st only / 2B|3B occ)

INVARIANTS: domains-only; corpus READ-ONLY; ASCII; numpy/pandas; no src/kernel
imports; <=300 LOC. Tests: python -m pytest domains/mlb/pitch_engine/test_corpus.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
_STATCAST = _REPO / "data" / "cache" / "statcast"

FIT_SEASON = 2023
TEST_SEASON = 2024


def parquet_path(season: int) -> Path:
    return _STATCAST / ("savant_full__%d.parquet" % season)


# --- pitch-class map (coarse 3-way) -----------------------------------------
_FB = frozenset({"FF", "SI", "FC", "FA", "FT", "SF"})
_BR = frozenset({"SL", "CU", "KC", "ST", "SV", "CS", "SC", "KN", "KL"})
_OS = frozenset({"CH", "FS", "FO", "EP"})
PITCH_CLASSES = ("FB", "BR", "OS")


def pitch_class(pt: pd.Series) -> pd.Series:
    """FB/BR/OS per pitch; None for pitchouts / unresolved (dropped by callers)."""
    out = np.where(pt.isin(_FB), "FB",
          np.where(pt.isin(_BR), "BR",
          np.where(pt.isin(_OS), "OS", None)))
    return pd.Series(out, index=pt.index)


# --- per-pitch 10-way outcome label -----------------------------------------
OUTCOMES = ("ball", "called_strike", "swinging_strike", "foul",
            "in_play_out", "single", "double", "triple", "hr", "hbp")
_BALL_D = {"ball", "blocked_ball", "pitchout", "intent_ball", "automatic_ball"}
_CS_D = {"called_strike", "automatic_strike"}
_SS_D = {"swinging_strike", "swinging_strike_blocked", "foul_tip",
         "missed_bunt", "bunt_foul_tip"}
_FOUL_D = {"foul", "foul_bunt"}
_HIT_EVT = {"single": "single", "double": "double", "triple": "triple",
            "home_run": "hr"}


def pitch_outcome(desc: pd.Series, events: pd.Series) -> pd.Series:
    """Map (description, events) -> one of OUTCOMES. hit_into_play resolves via the
    PA event; a batted ball that is not a clean 1B/2B/3B/HR is an in_play_out."""
    d = desc.astype(str)
    ev = events.astype(str)
    out = np.full(len(d), None, dtype=object)
    out = np.where(d.isin(_BALL_D), "ball", out)
    out = np.where(d.isin(_CS_D), "called_strike", out)
    out = np.where(d.isin(_SS_D), "swinging_strike", out)
    out = np.where(d.isin(_FOUL_D), "foul", out)
    out = np.where(d == "hit_by_pitch", "hbp", out)
    inplay = d == "hit_into_play"
    hit = ev.map(_HIT_EVT)
    out = np.where(inplay, np.where(hit.notna(), hit, "in_play_out"), out)
    return pd.Series(out, index=d.index)


# --- PA-event label (8-way, terminal-pitch only) ----------------------------
PA_EVENTS = ("OUT", "K", "BB", "HBP", "1B", "2B", "3B", "HR")
_PA_MAP = {
    "strikeout": "K", "strikeout_double_play": "K",
    "walk": "BB", "intent_walk": "BB", "hit_by_pitch": "HBP",
    "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR",
}


def pa_event(events: pd.Series) -> pd.Series:
    """Terminal PA event -> 8-way class; everything else (field_out, force_out,
    GIDP, sac, fielders_choice, error, interference, truncated) folds to OUT."""
    return events.astype(str).map(_PA_MAP).fillna("OUT")


# --- context buckets --------------------------------------------------------
def count_idx(balls, strikes) -> np.ndarray:
    b = np.clip(np.asarray(balls, dtype=int), 0, 3)
    s = np.clip(np.asarray(strikes, dtype=int), 0, 2)
    return b * 3 + s


def platoon_idx(p_throws: pd.Series, stand: pd.Series) -> np.ndarray:
    pt = (p_throws.astype(str).values == "L").astype(int)
    st = (stand.astype(str).values == "L").astype(int)
    return pt * 2 + st


def base_state_bits(df: pd.DataFrame) -> np.ndarray:
    """3-bit base mask bit0=1B bit1=2B bit2=3B from on_1b/2b/3b (id or NaN)."""
    b1 = df["on_1b"].notna().values.astype(int)
    b2 = df["on_2b"].notna().values.astype(int)
    b3 = df["on_3b"].notna().values.astype(int)
    return b1 + 2 * b2 + 4 * b3


def base_bucket_from_bits(bits: np.ndarray) -> np.ndarray:
    """EMP / ON1 / RISP -> 0/1/2. RISP = 2B or 3B occupied."""
    risp = ((bits & 2) | (bits & 4)) > 0
    on1_only = (bits == 1)
    return np.where(risp, 2, np.where(on1_only, 1, 0)).astype(int)


BASE_BUCKETS = ("EMP", "ON1", "RISP")

_PITCH_COLS = ["game_pk", "inning", "inning_topbot", "at_bat_number",
               "pitch_number", "pitcher", "batter", "events", "description",
               "pitch_type", "balls", "strikes", "outs_when_up",
               "on_1b", "on_2b", "on_3b", "bat_score", "post_home_score",
               "post_away_score", "stand", "p_throws", "zone"]


def load_pitch_frame(season: int, cols: Optional[List[str]] = None) -> pd.DataFrame:
    """Load one season's pitches, attach class/zone/count/platoon/base buckets and
    the 10-way outcome label. Drops pitches with unresolved class or zone. Sorted
    in true game order (game, at_bat_number, pitch_number)."""
    df = pd.read_parquet(parquet_path(season), columns=cols or _PITCH_COLS)
    df = df.sort_values(["game_pk", "at_bat_number", "pitch_number"]).reset_index(drop=True)
    df["pclass"] = pitch_class(df["pitch_type"])
    df = df[df["pclass"].notna()].copy()
    df["zbucket"] = np.where(df["zone"].between(1, 9), "IZ",
                             np.where(df["zone"].between(11, 14), "OZ", None))
    df = df[df["zbucket"].notna()].copy()
    df["cidx"] = count_idx(df["balls"], df["strikes"])
    df["pidx"] = platoon_idx(df["p_throws"], df["stand"])
    bits = base_state_bits(df)
    df["bbucket"] = base_bucket_from_bits(bits)
    df["outcome"] = pitch_outcome(df["description"], df["events"])
    df = df[df["outcome"].notna()].copy()
    df["season"] = season
    return df


def build_pa_frame(pitch_df: pd.DataFrame) -> pd.DataFrame:
    """One row per PA (terminal pitch = events.notna()). Carries pa_evt (8-way),
    runs scored on the play, start base mask/outs -> base_out_state (0..23), and
    the batter/pitcher/platoon context. Leak-free: only the pitch's own row."""
    term = pitch_df[pitch_df["events"].notna()].copy()
    term["pa_evt"] = pa_event(term["events"])
    bat_is_home = term["inning_topbot"].astype(str).values == "Bot"
    post_bat = np.where(bat_is_home, term["post_home_score"].values,
                        term["post_away_score"].values)
    term["runs"] = np.maximum(post_bat - term["bat_score"].values, 0).astype(int)
    bits = base_state_bits(term)
    outs = np.clip(term["outs_when_up"].values.astype(int), 0, 2)
    term["base_mask"] = bits
    term["outs_start"] = outs
    term["base_out_state"] = bits * 3 + outs
    return term.reset_index(drop=True)


__all__ = ["FIT_SEASON", "TEST_SEASON", "parquet_path", "PITCH_CLASSES",
           "pitch_class", "OUTCOMES", "pitch_outcome", "PA_EVENTS", "pa_event",
           "count_idx", "platoon_idx", "base_state_bits", "base_bucket_from_bits",
           "BASE_BUCKETS", "load_pitch_frame", "build_pa_frame"]
