"""scripts.platformkit.live_edge.combine.foul_minutes -- LIVE-EDGE CYCLE 5
FOUL-MINUTES: pregame-knowable features derived from the possession-grain
foul_state substrate (data/omni/live_edge/foul_attr/foul_state_<season>.parquet,
commit 2cae8c5a), to extend C1's minutes combiner
(scripts/platformkit/live_edge/combine/minutes_combiner.py).

STEP 0 premise check (2026-07-14): C1's combiner uses ONE claim-backed
feature (foul_rate_prior = trailing rate of pf>=4 by GAME END, from the
box-score `pf` column) and beats a per-player expanding-median baseline OOS
(pinball 3.1612 -> 3.0632, hist_gb, 2 seeds; data/omni/live_edge/combine/
minutes_combiner_report.json). foul_state carries possession-GRAIN detail
the box score does not have: (a) WHEN in the game a player crossed a foul
threshold (timing, not just the end-of-game count) and (b) how many
teammates were simultaneously in foul trouble while this player was
on-floor (lineup-level; only available 2024-25+2025-26 -- 2023-24 has no
lineup store per FOUL-AXIS docstring). This module builds two PREGAME-
knowable trailing features (shift(1), same rolling window as C1's
foul_rate_prior) so run_foul_minutes.py can test them as ADDITIONS to C1's
existing combiner under the identical walk-forward split (gate baseline
comparability rail).

Leak guard: foul_state's own build already snapshots counters strictly
pre-possession (build_foul.py docstring). Here we roll the resulting
per-player-game summaries FORWARD across games with shift(1) -- only
strictly-PRIOR games are ever visible to a row, matching C1's own
foul_rate_prior leak guard exactly.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_foul_minutes.py -q
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd

from scripts.platformkit.live_edge.combine import minutes_combiner as mc

_FOUL_STATE_DIR = pathlib.Path("data/omni/live_edge/foul_attr")
_SEASONS = ("2023_24", "2024_25", "2025_26")
FOULTROUBLE_PF_THRESHOLD = 4  # matches build_foul.py's own foultrouble_ct definition
EARLY_FOUL_PF_THRESHOLD = 2
EARLY_FOUL_PERIOD = 1


def _load_foul_state(seasons_dir: pathlib.Path | None = None) -> pd.DataFrame:
    d = seasons_dir or _FOUL_STATE_DIR
    frames = []
    for s in _SEASONS:
        p = d / f"foul_state_{s}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p, columns=[
                "game_id", "poss_idx", "period", "pf_map", "off_lineup_ids", "def_lineup_ids",
                "off_lineup_foultrouble_ct", "def_lineup_foultrouble_ct", "lineup_available",
            ]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _explode_pf_map(df: pd.DataFrame) -> pd.DataFrame:
    """(game_id, period, player_id, pf_value) long frame, one row per
    player with pf>0 as-of that possession's start (pf_map only stores
    positive entries -- see build_foul.py)."""
    nz = df[df["pf_map"] != "{}"]
    rows = []
    for game_id, period, raw in zip(nz["game_id"], nz["period"], nz["pf_map"]):
        for pid, pf in json.loads(raw).items():
            rows.append((game_id, period, int(pid), pf))
    return pd.DataFrame(rows, columns=["game_id", "period", "player_id", "pf_value"])


def _early_foul_q1_pairs(long_pf: pd.DataFrame) -> set:
    """(game_id, player_id) pairs where the player reached
    EARLY_FOUL_PF_THRESHOLD personal fouls within EARLY_FOUL_PERIOD."""
    if long_pf.empty:
        return set()
    hit = long_pf[(long_pf["period"] == EARLY_FOUL_PERIOD) & (long_pf["pf_value"] >= EARLY_FOUL_PF_THRESHOLD)]
    return set(zip(hit["game_id"], hit["player_id"]))


def _team_foultrouble_exposure(df: pd.DataFrame) -> pd.DataFrame:
    """Per (game_id, player_id): mean count of on-floor lineup members
    (own lineup, self-inclusion possible -- ponytail: threshold-based
    self-inclusion noise accepted, not corrected) with pf>=
    FOULTROUBLE_PF_THRESHOLD, across every possession this player was on
    the floor (offense or defense side). Only rows with lineup_available
    True carry a value (2024-25 / 2025-26 -- 2023-24 has no lineup store)."""
    lin = df[df["lineup_available"] == True]  # noqa: E712
    if lin.empty:
        return pd.DataFrame(columns=["game_id", "player_id", "team_foultrouble_exposure"])
    parts = []
    for side_ids, side_ct in (("off_lineup_ids", "off_lineup_foultrouble_ct"),
                               ("def_lineup_ids", "def_lineup_foultrouble_ct")):
        sub = lin[["game_id", side_ids, side_ct]].dropna(subset=[side_ids])
        sub = sub.assign(player_id=sub[side_ids].str.split(",")).explode("player_id")
        sub["player_id"] = pd.to_numeric(sub["player_id"], errors="coerce")
        parts.append(sub[["game_id", "player_id", side_ct]].rename(columns={side_ct: "value"}))
    long_exp = pd.concat(parts, ignore_index=True).dropna(subset=["player_id"])
    long_exp["player_id"] = long_exp["player_id"].astype(int)
    out = long_exp.groupby(["game_id", "player_id"])["value"].mean().reset_index()
    return out.rename(columns={"value": "team_foultrouble_exposure"})


def build_per_game_foul_features(seasons_dir: pathlib.Path | None = None) -> pd.DataFrame:
    """Per (game_id, player_id): early_foul_q1_flag (bool) +
    team_foultrouble_exposure (float, NaN in the pre-lineup 2023-24 era)."""
    df = _load_foul_state(seasons_dir)
    if df.empty:
        return pd.DataFrame(columns=["game_id", "player_id", "early_foul_q1_flag", "team_foultrouble_exposure"])
    long_pf = _explode_pf_map(df)
    pairs = _early_foul_q1_pairs(long_pf)
    all_players = long_pf[["game_id", "player_id"]].drop_duplicates().reset_index(drop=True)
    all_players["early_foul_q1_flag"] = [
        (g, p) in pairs for g, p in zip(all_players["game_id"], all_players["player_id"])
    ]
    exposure = _team_foultrouble_exposure(df)
    out = all_players.merge(exposure, on=["game_id", "player_id"], how="outer")
    out["early_foul_q1_flag"] = out["early_foul_q1_flag"].fillna(False)
    return out


def add_foul_state_features(sweep_df: pd.DataFrame, per_game: pd.DataFrame) -> pd.DataFrame:
    """Merge per-game foul_state summaries into the sweep frame, then roll
    them forward as PREGAME (trailing, shift(1)) rates -- same rolling
    window C1 uses for foul_rate_prior (mc.FOUL_RATE_WINDOW /
    mc.BASELINE_WINDOW_MIN_PERIODS), so base+candidate differ ONLY by the
    new features (gate baseline comparability rail)."""
    df = sweep_df.merge(per_game, on=["game_id", "player_id"], how="left")
    df = df.sort_values(["player_id", "date"]).reset_index(drop=True)

    flag = df["early_foul_q1_flag"].fillna(False).astype(float)
    g = flag.groupby(df["player_id"])
    trailing = g.apply(lambda s: s.shift(1).rolling(mc.FOUL_RATE_WINDOW, min_periods=mc.BASELINE_WINDOW_MIN_PERIODS).mean())
    df["early_foul_q1_rate_prior"] = trailing.reset_index(level=0, drop=True)
    league_trailing = flag.shift(1).rolling(mc.FOUL_RATE_WINDOW, min_periods=mc.BASELINE_WINDOW_MIN_PERIODS).mean()
    df["early_foul_q1_rate_prior"] = df["early_foul_q1_rate_prior"].fillna(league_trailing)

    exp = df["team_foultrouble_exposure"]
    ge = exp.groupby(df["player_id"])
    trailing_exp = ge.apply(lambda s: s.shift(1).rolling(mc.FOUL_RATE_WINDOW, min_periods=mc.BASELINE_WINDOW_MIN_PERIODS).mean())
    df["team_foultrouble_exposure_prior"] = trailing_exp.reset_index(level=0, drop=True)
    # no league fallback here: pre-2024-25 rows genuinely have no lineup
    # data -- left NaN, dropped downstream rather than fabricated.
    return df


__all__ = ["build_per_game_foul_features", "add_foul_state_features",
           "FOULTROUBLE_PF_THRESHOLD", "EARLY_FOUL_PF_THRESHOLD", "EARLY_FOUL_PERIOD"]
