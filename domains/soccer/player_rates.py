"""Leak-free, empirical-Bayes-shrunk per-90 rate priors for soccer player props.

The engine keys every output by a CANONICAL stat name so it joins downstream to
the scraped prop line's stat (prop_base.canon_stat). Each canonical stat maps to
one or more raw ESPN columns written by ingest_espn_players.py.

LEAK-FREENESS (load-bearing): every rate is computed using ONLY rows whose
``date`` is STRICTLY BEFORE ``as_of_date``. A player's own row dated on/after the
match is never an input to predicting that match.

Public functions NEVER raise -- they degrade to {"status": "unknown"}.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_player_rates.py -q
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

# Shrinkage strength in "matches-worth" of minutes. International players have
# very few caps, so we lean on the position baseline until ~K matches of data.
SHRINK_K = 3.0
_EPS = 1e-9
_FULL_MATCH_MIN = 90.0
# Club-prior weight cap (in started-matches-worth). A club season is real recent
# form; we let it count as a STRONG prior but cap its weight so it can never fully
# swamp a player's own WC matches.
CLUB_WEIGHT_CAP = 20.0
# A rate is "club-backed" / no-longer-thin once effective sample reaches this.
CONFIDENCE_N_EFF = 5.0

# canonical stat -> list of raw ESPN columns to SUM per match.
CANON_TO_COLS: Dict[str, List[str]] = {
    "Shots": ["totalShots"],
    "Shots On Target": ["shotsOnTarget"],
    "Fouls": ["foulsCommitted"],
    "Fouls Drawn": ["foulsSuffered"],
    "Cards": ["yellowCards", "redCards"],
    "Assists": ["goalAssists"],
    "Goal+Assist": ["totalGoals", "goalAssists"],
    "Goals": ["totalGoals"],
    "Offsides": ["offsides"],
    "Saves": ["saves"],
}


def canonical_stats() -> List[str]:
    """The canonical stat names this engine can produce."""
    return list(CANON_TO_COLS.keys())


def _as_ts(value) -> Optional[pd.Timestamp]:
    try:
        ts = pd.Timestamp(value)
        return None if pd.isna(ts) else ts
    except Exception:
        return None


def _prior_rows(df: pd.DataFrame, as_of_date) -> Optional[pd.DataFrame]:
    """Rows STRICTLY BEFORE as_of_date (leak guard). None on bad input."""
    if df is None or len(df) == 0 or "date" not in df.columns:
        return None
    as_of = _as_ts(as_of_date)
    if as_of is None:
        return None
    dates = pd.to_datetime(df["date"], errors="coerce")
    mask = dates.notna() & (dates < as_of)
    return df.loc[mask]


def _stat_total(rows: pd.DataFrame, stat_canonical: str) -> Optional[float]:
    """Sum the raw columns for a canonical stat across rows. None if unknown."""
    cols = CANON_TO_COLS.get(stat_canonical)
    if cols is None:
        return None
    total = 0.0
    for col in cols:
        if col not in rows.columns:
            continue
        total += pd.to_numeric(rows[col], errors="coerce").fillna(0.0).sum()
    return float(total)


def _minutes_total(rows: pd.DataFrame) -> float:
    if "minutes" not in rows.columns:
        return 0.0
    return float(pd.to_numeric(rows["minutes"], errors="coerce").fillna(0.0).sum())


def position_baseline(
    df: pd.DataFrame, stat_canonical: str, as_of_date, position
) -> Optional[float]:
    """Position-level per-90 baseline from ALL players at ``position`` using only
    matches before ``as_of_date``. Returns None when the stat is unknown or no
    minutes exist for that position. Pooled (minutes-weighted) per-90.
    """
    if stat_canonical not in CANON_TO_COLS:
        return None
    prior = _prior_rows(df, as_of_date)
    if prior is None or len(prior) == 0:
        return None
    if position is not None and "position" in prior.columns:
        prior = prior.loc[prior["position"] == position]
    if len(prior) == 0:
        return None
    total_stat = _stat_total(prior, stat_canonical)
    total_min = _minutes_total(prior)
    if total_stat is None or total_min <= _EPS:
        return None
    return _FULL_MATCH_MIN * total_stat / total_min


def _club_weight(club_prior) -> tuple:
    """(per90, weight) from a club_prior dict, or (None, 0.0) if unusable.

    weight = min(starts, CLUB_WEIGHT_CAP) -- a started match is the per-90 unit, so
    ``starts`` is the club season's effective sample size (capped so it can never
    fully swamp the player's own WC matches)."""
    if not isinstance(club_prior, dict):
        return None, 0.0
    if club_prior.get("status") not in (None, "ok"):
        return None, 0.0
    per90 = club_prior.get("per90")
    if per90 is None:
        return None, 0.0
    try:
        per90 = float(per90)
    except (TypeError, ValueError):
        return None, 0.0
    try:
        starts = float(club_prior.get("starts") or 0.0)
    except (TypeError, ValueError):
        starts = 0.0
    weight = max(0.0, min(starts, CLUB_WEIGHT_CAP))
    if weight <= _EPS:
        return None, 0.0
    return per90, weight


def player_rate(
    df: pd.DataFrame,
    player_id,
    stat_canonical: str,
    as_of_date,
    *,
    position=None,
    club_prior=None,
) -> Dict[str, object]:
    """Leak-free, shrunk per-90 rate for one player + canonical stat.

    Returns dict with keys: per90, n_matches, minutes, shrunk, status, n_eff.
    status is "ok" when a usable rate (player or baseline) was produced and
    "unknown" when neither the player nor the position baseline has any signal.
    n_eff is the effective sample (WC matches-worth + club-prior weight); the board
    treats a rate as no-longer-thin when n_eff >= CONFIDENCE_N_EFF.

    ``club_prior`` (optional) = {"per90": float, "starts": float} from a player's
    CLUB season (real recent form). When supplied with a usable per90 it is blended
    in as a STRONG prior (weight = min(starts, CLUB_WEIGHT_CAP)) so a player with a
    solid club season is no longer thin even on ~1 WC match. When None the behaviour
    is EXACTLY the prior implementation (n_eff just reports the WC matches-worth).
    Never raises.
    """
    unknown = {
        "per90": None,
        "n_matches": 0,
        "minutes": 0.0,
        "shrunk": False,
        "status": "unknown",
        "n_eff": 0.0,
    }
    if stat_canonical not in CANON_TO_COLS:
        return dict(unknown)

    prior = _prior_rows(df, as_of_date)
    if prior is None:
        return dict(unknown)

    pid = str(player_id)
    own = prior
    if "player_id" in prior.columns:
        own = prior.loc[prior["player_id"].astype(str) == pid]

    # Infer the player's position from their own prior rows if not supplied.
    pos = position
    if pos is None and "position" in own.columns and len(own) > 0:
        modes = own["position"].dropna()
        if len(modes) > 0:
            pos = modes.mode().iloc[0] if len(modes.mode()) else modes.iloc[0]

    baseline = position_baseline(df, stat_canonical, as_of_date, pos)

    total_min = _minutes_total(own)
    n_matches = int(len(own))
    n_wc = total_min / _FULL_MATCH_MIN

    club_per90, club_w = _club_weight(club_prior)

    # ---- club-backed blend path (only when a usable club prior is supplied) ----
    if club_per90 is not None:
        total_stat = _stat_total(own, stat_canonical) if total_min > _EPS else 0.0
        wc_per90 = (
            _FULL_MATCH_MIN * (total_stat or 0.0) / total_min
            if total_min > _EPS else 0.0
        )
        num = n_wc * wc_per90 + club_w * club_per90
        den = n_wc + club_w
        blended = num / den if den > _EPS else club_per90
        n_eff = n_wc + club_w
        # Optional residual shrink toward the position baseline for any thin gap.
        per90 = blended
        if baseline is not None and n_eff < SHRINK_K:
            per90 = (n_eff * blended + SHRINK_K * baseline) / (n_eff + SHRINK_K)
        return {
            "per90": float(per90),
            "n_matches": n_matches,
            "minutes": float(total_min),
            "shrunk": bool(n_eff < CONFIDENCE_N_EFF),
            "status": "ok",
            "n_eff": float(n_eff),
        }

    # ---- legacy path (club_prior is None / unusable): EXACT prior behaviour ----
    if total_min <= _EPS:
        # Zero prior minutes -> fall back to the position baseline (shrunk).
        if baseline is None:
            return dict(unknown)
        return {
            "per90": float(baseline),
            "n_matches": n_matches,
            "minutes": 0.0,
            "shrunk": True,
            "status": "ok",
            "n_eff": 0.0,
        }

    total_stat = _stat_total(own, stat_canonical)
    raw_per90 = _FULL_MATCH_MIN * (total_stat or 0.0) / total_min

    if baseline is None:
        # No baseline to shrink toward -> report the raw rate, unshrunk.
        return {
            "per90": float(raw_per90),
            "n_matches": n_matches,
            "minutes": float(total_min),
            "shrunk": False,
            "status": "ok",
            "n_eff": float(n_wc),
        }

    n_eff = n_wc
    shrunk = (n_eff * raw_per90 + SHRINK_K * baseline) / (n_eff + SHRINK_K)
    return {
        "per90": float(shrunk),
        "n_matches": n_matches,
        "minutes": float(total_min),
        "shrunk": True,
        "status": "ok",
        "n_eff": float(n_eff),
    }
