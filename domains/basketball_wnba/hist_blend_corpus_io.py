"""domains.basketball_wnba.hist_blend_corpus_io -- corpus loading + row-
building for hist_blend_crosscorpus.py (LANE 3 sub-task A). Split out purely
to respect the <=300 LOC/file cap; see hist_blend_crosscorpus.py's docstring
for the full method rationale (corpus A/B provenance, why each corpus gets
its own walk-forward Elo, exhibition-game exclusion). This module owns ONLY
the I/O + Row-construction; fit/validate/adopt logic lives in the sibling
module and imports these functions.

INVARIANTS: domains/basketball_wnba/ only; <=300 LOC; ASCII only; no network
at import time; never writes data/registry/; never raises out.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.basketball_wnba.ingame_blend_families import Row

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data" / "domains" / "wnba"
LINESCORES_PARQUET = _DATA_DIR / "linescores.parquet"
CDN_BACKFILL_DIR = _DATA_DIR / "cdn_backfill"
CDN_STATES_PARQUET = _DATA_DIR / "cdn_backfill_states.parquet"

CHECKPOINTS: Tuple[str, ...] = ("end_q1", "half", "end_q3")

# WNBA Elo constants mirrored from elo_config.py (single-season corpora here,
# so SEASON_REGRESS never fires -- kept only for API parity with ratings.py).
_ELO_K = 30.0
_ELO_MEAN = 1500.0
_ELO_HFA = 40.0

_EXCLUDE_NAME_MARKERS = ("National Team",)


# ---------------------------------------------------------------------------
# Shared: minimal single-season walk-forward Elo
# ---------------------------------------------------------------------------


def walk_forward_elo_simple(games: pd.DataFrame) -> pd.DataFrame:
    """Minimal single-season walk-forward Elo (no cross-season regression --
    both corpora here are one season). Returns games with p0 column added, in
    the SAME chronological order passed in. Pure, no I/O."""
    elo: Dict[str, float] = {}
    p0s: List[float] = []
    for _, g in games.iterrows():
        home, away = str(g["home_team"]), str(g["away_team"])
        eh = elo.setdefault(home, _ELO_MEAN)
        ea = elo.setdefault(away, _ELO_MEAN)
        d = (eh + _ELO_HFA) - ea
        p = 1.0 / (1.0 + math.pow(10.0, -d / 400.0))
        p0s.append(p)
        s_home = 1.0 if float(g["home_win"]) >= 0.5 else 0.0
        delta = _ELO_K * (s_home - p)
        elo[home] = eh + delta
        elo[away] = ea - delta
    out = games.copy()
    out["p0"] = p0s
    return out


# ---------------------------------------------------------------------------
# Corpus A: linescores.parquet, restricted to the 2026 season slice
# ---------------------------------------------------------------------------


def load_corpus_a_2026(parquet_path: Optional[Path] = None) -> pd.DataFrame:
    """2026-only rows of linescores.parquet, sorted chronologically. Empty
    DataFrame (never raises) if the file is absent."""
    p = parquet_path or LINESCORES_PARQUET
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    df = df[df["season"].astype(str) == "2026"].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "home_team", "away_team"], kind="mergesort").reset_index(drop=True)


def build_rows_corpus_a(df_with_p0: pd.DataFrame) -> Dict[str, List[Row]]:
    """checkpoint -> [Row, ...] from corpus A's own cumulative linescore columns."""
    out: Dict[str, List[Row]] = {cp: [] for cp in CHECKPOINTS}
    for _, g in df_with_p0.iterrows():
        p0, outcome = float(g["p0"]), float(g["home_win"])
        pairs = {
            "end_q1": (float(g["home_end_q1"]) - float(g["away_end_q1"]), 1),
            "half": (float(g["home_half"]) - float(g["away_half"]), 2),
            "end_q3": (float(g["home_end_q3"]) - float(g["away_end_q3"]), 3),
        }
        for cp, (diff, period) in pairs.items():
            out[cp].append(Row(p0=p0, score_diff=diff, period=period, clock_s=0.0, outcome=outcome))
    return out


# ---------------------------------------------------------------------------
# Corpus B: CDN backfill (boxscore final score + cdn_backfill_states.parquet)
# ---------------------------------------------------------------------------


def load_corpus_b_games(backfill_dir: Optional[Path] = None) -> pd.DataFrame:
    """One row per real-franchise CDN game (excludes exhibitions), with the
    CDN's OWN final score (game.homeTeam.score / awayTeam.score -- independent
    of linescores.parquet entirely). Columns: game_id, date, home_team,
    away_team, home_win. Never raises; empty frame if the dir is absent."""
    d = backfill_dir or CDN_BACKFILL_DIR
    if not d.exists():
        return pd.DataFrame()
    rows: List[Dict[str, object]] = []
    for gd in sorted(d.iterdir()):
        if not gd.is_dir():
            continue
        box_path = gd / "boxscore.json"
        if not box_path.exists():
            continue
        try:
            game = json.loads(box_path.read_text(encoding="utf-8")).get("game")
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(game, dict):
            continue
        home_team = (game.get("homeTeam") or {}).get("teamName", "")
        away_team = (game.get("awayTeam") or {}).get("teamName", "")
        if any(m in home_team or m in away_team for m in _EXCLUDE_NAME_MARKERS):
            continue
        try:
            hs = float((game.get("homeTeam") or {}).get("score"))
            aws = float((game.get("awayTeam") or {}).get("score"))
        except (TypeError, ValueError):
            continue
        if hs == aws:
            continue  # no ties in basketball; malformed row -- skip, never fake
        rows.append({
            "game_id": str(gd.name), "date": str(game.get("gameEt", ""))[:10],
            "home_team": home_team, "away_team": away_team,
            "home_win": 1.0 if hs > aws else 0.0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["date", "home_team", "away_team"], kind="mergesort").reset_index(drop=True)


def load_corpus_b_states(states_parquet: Optional[Path] = None) -> pd.DataFrame:
    """cdn_backfill_states.parquet as shipped wave 14 (checkpoint score rows,
    no outcome column -- outcome is joined in from load_corpus_b_games)."""
    p = states_parquet or CDN_STATES_PARQUET
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def build_rows_corpus_b(games_with_p0: pd.DataFrame, states_df: pd.DataFrame) -> Dict[str, List[Row]]:
    """checkpoint -> [Row, ...] joining corpus B's own p0 (from
    walk_forward_elo_simple over load_corpus_b_games output) with its
    checkpoint states (score_home/score_away at end_q1/half/end_q3)."""
    p0_by_gid = {str(r["game_id"]): (float(r["p0"]), float(r["home_win"]))
                 for _, r in games_with_p0.iterrows()}
    period_by_cp = {"end_q1": 1, "half": 2, "end_q3": 3}
    out: Dict[str, List[Row]] = {cp: [] for cp in CHECKPOINTS}
    for _, s in states_df.iterrows():
        gid = str(s["game_id"])
        if gid not in p0_by_gid:
            continue  # excluded exhibition game or missing boxscore -- skip, don't fake
        p0, outcome = p0_by_gid[gid]
        cp = str(s["checkpoint"])
        if cp not in out:
            continue
        diff = float(s["score_home"]) - float(s["score_away"])
        out[cp].append(Row(p0=p0, score_diff=diff, period=period_by_cp[cp],
                            clock_s=0.0, outcome=outcome))
    return out


__all__ = [
    "LINESCORES_PARQUET", "CDN_BACKFILL_DIR", "CDN_STATES_PARQUET", "CHECKPOINTS",
    "walk_forward_elo_simple", "load_corpus_a_2026", "build_rows_corpus_a",
    "load_corpus_b_games", "load_corpus_b_states", "build_rows_corpus_b",
]
