"""domains.tennis.match_postmortem — per-match POST-MORTEM foundation (KNOWLEDGE layer).

One descriptive record per event_id: WHY the match went the way it did.
LEAK TIER: DESCRIPTIVE (realized match stats only). RETIREMENT = noise/censoring.

Score parsing: n_breaks ≈ sum over non-tiebreak sets of max(0, |w-l| - 1).
Conservative proxy documented; actual break counting needs point-level data.
Hold%: (1stWon + 2ndWon) / svpt proxy.  BP conv: (bpFaced-bpSaved) / bpFaced.
See match_postmortem_eval.py for CLI / distribution reporting.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TENNIS_DATA = _REPO_ROOT / "data" / "domains" / "tennis"
_MATCHES_PQ = _TENNIS_DATA / "matches.parquet"
_STATS_PQ = _TENNIS_DATA / "match_stats.parquet"
_OUT_PQ = _TENNIS_DATA / "postmortem.parquet"

_SET_TOKEN = re.compile(
    r"(\d+)-(\d+)"       # w_games - l_games (from p1 perspective)
    r"(?:\((\d+)\))?"    # optional (tiebreak_loser_pts)
    r"(?:\[(\d+)\])?"    # optional [super-tb score]
)


def parse_score(score: str) -> dict:
    """Parse tennis score string into structured components.

    Returns dict: n_sets, n_breaks (approx), n_tiebreaks, straight_sets,
    walkover, retirement_in_score, sets (list of {w,l,tb,super_tb}).
    straight_sets is from p1's perspective (p1 won all sets).
    n_breaks is conservative: max(0, |w-l| - 1) per non-tiebreak set.
    """
    out = dict(n_sets=0, n_breaks=0, n_tiebreaks=0,
               straight_sets=False, walkover=False, retirement_in_score=False, sets=[])
    if not isinstance(score, str):
        return out

    s = score.strip().upper()
    if s in ("W/O", "WALKOVER", ""):
        out["walkover"] = True
        return out

    if "RET" in s:
        out["retirement_in_score"] = True
        s = re.sub(r"\s*RET\b.*", "", s).strip()

    super_tb = bool(re.search(r"\[(\d+)(?:-(\d+))?\]", s))
    s_clean = re.sub(r"\[.*?\]", "", s).strip()

    sets = []
    for m in _SET_TOKEN.finditer(s_clean):
        w, l = int(m.group(1)), int(m.group(2))
        tb = int(m.group(3)) if m.group(3) is not None else None
        sets.append({"w": w, "l": l, "tb": tb, "super_tb": False})

    if super_tb:
        sets.append({"w": 0, "l": 0, "tb": 0, "super_tb": True})

    out["sets"] = sets
    out["n_sets"] = len(sets)
    out["n_tiebreaks"] = sum(1 for s_ in sets if s_["tb"] is not None or s_["super_tb"])

    n_breaks = 0
    for s_ in sets:
        if s_["super_tb"] or s_["tb"] is not None:
            continue  # tiebreak sets: no break counting (both held to reach tb)
        n_breaks += max(0, s_["w"] - s_["l"] - 1)
    out["n_breaks"] = n_breaks

    out["straight_sets"] = (
        len(sets) >= 2 and all(s_["w"] > s_["l"] or s_["super_tb"] for s_ in sets)
    )
    return out


def _hold_pct_from_svpts(
    svpt: float, first_won: float, second_won: float
) -> tuple[Optional[float], str]:
    """Return (hold_pct, method) via svpt proxy: (1stWon + 2ndWon) / svpt."""
    if pd.isna(svpt) or svpt <= 0:
        return None, "missing_svpt"
    spw = (first_won if not pd.isna(first_won) else 0.0) + (
        second_won if not pd.isna(second_won) else 0.0
    )
    return float(spw / svpt), "svpt_proxy"


def _bp_conv_pct(bp_saved: float, bp_faced: float) -> Optional[float]:
    """Opponent BP conversion: (bpFaced - bpSaved) / bpFaced."""
    if pd.isna(bp_faced) or bp_faced <= 0:
        return None
    if pd.isna(bp_saved):
        bp_saved = 0.0
    return float(max(0.0, bp_faced - bp_saved) / bp_faced)


def _decide_label(row: pd.Series, parsed: dict) -> str:
    """Assign decided_by label (mutually exclusive, priority-ordered).

    Priority: RETIREMENT > BLOWOUT > TIEBREAK_SWING > BROKE_LATE >
              BP_CONVERSION_EDGE > SERVE_HELD_THROUGHOUT > SURFACE_MISMATCH >
              THREE_SET_GRIND > ROUTINE
    """
    if row.get("retirement", False) or parsed.get("retirement_in_score") or parsed.get("walkover"):
        return "RETIREMENT"

    n_tb = parsed["n_tiebreaks"]
    n_sets = parsed["n_sets"]
    straight = parsed["straight_sets"]
    n_breaks = parsed["n_breaks"]
    p1_hold, p2_hold = row.get("p1_hold_pct"), row.get("p2_hold_pct")
    p1_bp, p2_bp = row.get("p1_bp_conv_pct"), row.get("p2_bp_conv_pct")
    winner = row.get("winner", 1)
    p1_rank, p2_rank = row.get("p1_rank"), row.get("p2_rank")
    surface = str(row.get("surface", "")).lower()

    if straight and n_breaks >= 4:
        return "BLOWOUT"
    if n_tb >= 2:
        return "TIEBREAK_SWING"
    if n_tb == 1 and n_sets >= 2 and not straight:
        return "BROKE_LATE"
    if p1_bp is not None and p2_bp is not None and abs(p1_bp - p2_bp) >= 0.20:
        return "BP_CONVERSION_EDGE"
    if (p1_hold is not None and p2_hold is not None
            and p1_hold >= 0.70 and p2_hold >= 0.70 and n_breaks <= 1):
        return "SERVE_HELD_THROUGHOUT"
    if (p1_rank is not None and p2_rank is not None
            and not pd.isna(p1_rank) and not pd.isna(p2_rank)
            and surface in ("clay", "grass")):
        rank_fav = 1 if p1_rank < p2_rank else 2
        if rank_fav != winner:
            return "SURFACE_MISMATCH"
    if n_sets >= 3:
        return "THREE_SET_GRIND"
    return "ROUTINE"


def build_postmortem(
    matches: Optional[pd.DataFrame] = None,
    stats: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build per-match post-mortem DataFrame.

    Parameters
    ----------
    matches, stats : DataFrame | None
        If None, loaded from default parquet paths (data/domains/tennis/).

    Returns
    -------
    DataFrame with one row per event_id from matches.
    Columns: event_id, surface, best_of, minutes, retirement, n_sets, n_breaks,
             n_tiebreaks, straight_sets, p1_hold_pct, p2_hold_pct,
             p1_bp_conv_pct, p2_bp_conv_pct, p1_serve_pts_won, p2_serve_pts_won,
             p1_aces, p2_aces, hold_method, decided_by, noise_flag.
    """
    if matches is None:
        matches = pd.read_parquet(_MATCHES_PQ)
    if stats is None:
        stats = pd.read_parquet(_STATS_PQ)

    df = matches.merge(stats, on="event_id", how="left")
    parsed_scores = df["score"].apply(parse_score)

    p1_hold, p1_method = zip(*df.apply(
        lambda r: _hold_pct_from_svpts(r.get("p1_svpt"), r.get("p1_1stWon"), r.get("p1_2ndWon")),
        axis=1,
    ))
    p2_hold, _ = zip(*df.apply(
        lambda r: _hold_pct_from_svpts(r.get("p2_svpt"), r.get("p2_1stWon"), r.get("p2_2ndWon")),
        axis=1,
    ))
    p1_bp_conv = df.apply(lambda r: _bp_conv_pct(r.get("p1_bpSaved"), r.get("p1_bpFaced")), axis=1)
    p2_bp_conv = df.apply(lambda r: _bp_conv_pct(r.get("p2_bpSaved"), r.get("p2_bpFaced")), axis=1)

    def _srv_pts(w_col: str, s_col: str) -> pd.Series:
        return df.apply(
            lambda r: float((r.get(w_col) or 0) + (r.get(s_col) or 0))
            if not pd.isna(r.get(w_col, float("nan"))) else None, axis=1,
        )

    out = pd.DataFrame({
        "event_id":         df["event_id"].values,
        "surface":          df["surface"].values,
        "best_of":          df["best_of"].values,
        "minutes":          df["minutes"].values,
        "retirement":       df["retirement"].astype(bool).values,
        "p1_hold_pct":      list(p1_hold),
        "p2_hold_pct":      list(p2_hold),
        "p1_bp_conv_pct":   p1_bp_conv.values,
        "p2_bp_conv_pct":   p2_bp_conv.values,
        "p1_serve_pts_won": _srv_pts("p1_1stWon", "p1_2ndWon").values,
        "p2_serve_pts_won": _srv_pts("p2_1stWon", "p2_2ndWon").values,
        "p1_aces":          df.get("p1_ace", pd.Series([None] * len(df))).values,
        "p2_aces":          df.get("p2_ace", pd.Series([None] * len(df))).values,
        "hold_method":      list(p1_method),
        "n_sets":           [p["n_sets"]      for p in parsed_scores],
        "n_breaks":         [p["n_breaks"]    for p in parsed_scores],
        "n_tiebreaks":      [p["n_tiebreaks"] for p in parsed_scores],
        "straight_sets":    [p["straight_sets"] for p in parsed_scores],
        "winner":           df["winner"].values,
        "p1_rank":          df["p1_rank"].values,
        "p2_rank":          df["p2_rank"].values,
    })

    out["decided_by"] = out.apply(
        lambda r: _decide_label(r, parsed_scores.iloc[r.name]), axis=1
    )
    out["noise_flag"] = out["decided_by"].apply(
        lambda lbl: "RETIREMENT_CENSORED" if lbl == "RETIREMENT" else None
    )
    return out.drop(columns=["winner", "p1_rank", "p2_rank"])


def write_postmortem(df: Optional[pd.DataFrame] = None) -> Path:
    """Write postmortem.parquet; return path."""
    if df is None:
        df = build_postmortem()
    _OUT_PQ.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUT_PQ, index=False)
    return _OUT_PQ
