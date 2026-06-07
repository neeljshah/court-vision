"""src/prediction/teammate_out_override.py — runtime usage redistribution
when a teammate is OUT (A3 fix).

Problem (A3 discovery): the prop_pergame model has no `teammate_out` feature.
Each player is predicted in isolation from their own L5/L10 form — so when a
high-usage teammate is ruled OUT after the model was trained, the OUT player's
absent production never gets reallocated to the bench/backups. This module
applies that redistribution as a post-prediction pass.

Inputs:
    - slate_df : long-form parquet with columns
        [player_id, player, team, opp, is_home, stat, q10, q50, q90, sigma, status]
      where status='OUT' rows already have q-quantiles zeroed out (the OUT
      player's production needs to be redirected away).
    - out_player_ids : set of NBA player_ids that are OUT for tonight (already
      reflected in status='OUT' rows in slate_df, but we accept the explicit
      list for resilience).
    - team_id : the team abbreviation we are redistributing for. Only that
      team's rows are mutated — never bleed adjustments across teams.
    - weights_df : observed minute / usage pool to use as redistribution
      weights. Typically a series-average DataFrame
      (e.g. wcf_player_series_avg.csv) with columns [player_id, team,
      min_pg, usg_pct_pg, ...]. Players in this frame who are NOT OUT and
      who are on `team_id` get a share of the OUT player's projection
      proportional to their observed minutes pool.

Allocation rule (the math):
    For each STAT (pts/reb/ast/...):
      1. Compute the absent_total = sum of WCF stat_pg for every OUT player
         on this team (their absent production, what needs redistributing).
      2. Compute the minutes_pool = sum of WCF min_pg across available
         players on this team (the bench/backups absorbing the gap).
      3. For each available player on the team, share = min_pg / pool.
      4. Bump = share * absent_total — how much *additional* stat output
         we expect them to produce.
      5. New q50 = old q50 + bump. We cap the multiplicative ratio at
         MAX_BOOST (default 1.40) to prevent runaway projections for
         small-minute players whose old q50 was tiny.
      6. q10 / q90 are scaled by the same multiplicative ratio (preserves
         distributional spread); sigma is scaled by sqrt(ratio) to keep
         variance growth modest.

Cautions enforced:
    - Only the OUT team's rows are touched (never SAS rows when OKC has injuries).
    - Players already in `out_player_ids` are NOT given a boost themselves
      (they're absent, not absorbing).
    - We do NOT double-count starter/bench scaling — this pass runs on the
      raw slate q50 BEFORE any STATUS_SCALE multiplier in lineups.py. Callers
      that apply both should run this FIRST, then any minutes-scaling pass.
    - MAX_BOOST caps absurd projections (e.g. a deep-bench player going
      from 1.0 to 5.0 PTS just because the math says so).

Returns the slate DataFrame with q10/q50/q90/sigma mutated in place for the
boosted players. A new column `teammate_out_boost` is added so downstream
EV / quantile-calibration code can see whether a row was adjusted.
"""
from __future__ import annotations

import os
from typing import Dict, Iterable, Optional, Set, Tuple

import pandas as pd


# Cap on multiplicative q50 ratio (new_q50 / old_q50). 1.40 means a player
# whose old q50 was 5.0 can be boosted up to 7.0 max — enough to capture
# the lion's share of a 22-MPG teammate-out gap, but not enough for a
# deep-bench player to suddenly outscore a starter.
MAX_BOOST: float = 1.40

# Minimum old_q50 floor for the multiplier cap. If old_q50 is below this,
# we use this floor for the cap math so a player with q50=0.05 doesn't get
# capped at 0.07 and miss the entire bump. Stat-specific would be ideal;
# 0.5 is a reasonable single-value compromise across pts/reb/ast/...
_RATIO_FLOOR: float = 0.5

# Maps slate stat name → WCF series CSV column name. The slate uses lowercase
# stat tokens (pts, reb, ast, fg3m, stl, blk, tov); the WCF CSV uses
# `<stat>_pg` columns. Anything not in this map gets skipped (e.g. no
# `min`-level stat redistribution — we operate on output stats only).
_STAT_TO_WCF: Dict[str, str] = {
    "pts":  "pts_pg",
    "reb":  "reb_pg",
    "ast":  "ast_pg",
    "fg3m": "fg3m_pg",
    "stl":  "stl_pg",
    "blk":  "blk_pg",
    "tov":  "tov_pg",
}


def _safe_float(x, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return v


def _compute_share_weights(
    weights_df: pd.DataFrame,
    team: str,
    out_player_ids: Set[int],
) -> Dict[int, float]:
    """For team's available players, return {player_id: share_of_minutes_pool}.

    Only players on `team` who are NOT in out_player_ids and who have a
    non-zero min_pg are eligible. Returns {} when no eligible pool exists.
    """
    if weights_df is None or weights_df.empty:
        return {}
    team_rows = weights_df[weights_df["team"].astype(str).str.upper()
                              == str(team).upper()].copy()
    if team_rows.empty:
        return {}
    # min_pg is the dominant signal — bench guys with no court time
    # get no share. Drop NaN and zero-minute players outright.
    team_rows["min_pg"] = team_rows["min_pg"].apply(_safe_float)
    team_rows = team_rows[team_rows["min_pg"] > 0.0]
    # Exclude the OUT players themselves from absorbing.
    team_rows = team_rows[~team_rows["player_id"].astype(int).isin(out_player_ids)]
    if team_rows.empty:
        return {}
    total = float(team_rows["min_pg"].sum())
    if total <= 0:
        return {}
    return {
        int(r.player_id): float(r.min_pg) / total
        for r in team_rows.itertuples(index=False)
    }


def _compute_absent_totals(
    weights_df: pd.DataFrame,
    team: str,
    out_player_ids: Set[int],
) -> Dict[str, float]:
    """Return {stat: sum_of_stat_pg across OUT players on this team}.

    These are the absolute counts (PTS / REB / ...) that need redistributing.
    Uses the WCF series-average columns. Missing data → 0.0 contribution.
    """
    out: Dict[str, float] = {stat: 0.0 for stat in _STAT_TO_WCF}
    if weights_df is None or weights_df.empty or not out_player_ids:
        return out
    team_rows = weights_df[
        (weights_df["team"].astype(str).str.upper() == str(team).upper())
        & (weights_df["player_id"].astype(int).isin(out_player_ids))
    ]
    if team_rows.empty:
        return out
    for stat, col in _STAT_TO_WCF.items():
        if col not in team_rows.columns:
            continue
        total = sum(_safe_float(v) for v in team_rows[col].tolist())
        out[stat] = total
    return out


def redistribute_usage(
    slate_df: pd.DataFrame,
    out_player_ids: Iterable[int],
    team_id: str,
    weights_df: pd.DataFrame,
    max_boost: float = MAX_BOOST,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Apply teammate-OUT redistribution for a single team.

    Args:
        slate_df: long-form slate (one row per player/stat).
        out_player_ids: NBA player_ids that are OUT tonight on `team_id`.
        team_id: team abbreviation to redistribute for.
        weights_df: observed-minutes DataFrame (WCF series averages).
        max_boost: multiplicative cap on q50 (default 1.40).

    Returns:
        (adjusted_slate_df, audit_df) where audit_df has one row per
        (player, stat) that was boosted, with columns
        [player_id, player, stat, old_q50, bump, new_q50, ratio].

    The adjusted slate is a copy — caller's frame is not mutated. The added
    column `teammate_out_boost` is the absolute additive bump applied to q50
    (zero for rows that weren't adjusted).
    """
    df = slate_df.copy()
    if "teammate_out_boost" not in df.columns:
        df["teammate_out_boost"] = 0.0

    out_ids: Set[int] = {int(p) for p in out_player_ids}
    if not out_ids:
        empty_audit = pd.DataFrame(
            columns=["player_id", "player", "stat", "old_q50", "bump",
                     "new_q50", "ratio"])
        return df, empty_audit

    shares = _compute_share_weights(weights_df, team_id, out_ids)
    absent = _compute_absent_totals(weights_df, team_id, out_ids)
    if not shares or not any(v > 0 for v in absent.values()):
        empty_audit = pd.DataFrame(
            columns=["player_id", "player", "stat", "old_q50", "bump",
                     "new_q50", "ratio"])
        return df, empty_audit

    audit_rows = []
    team_mask = (df["team"].astype(str).str.upper() == str(team_id).upper())
    for stat, absent_total in absent.items():
        if absent_total <= 0:
            continue
        if stat not in _STAT_TO_WCF:
            continue
        for pid, share in shares.items():
            bump = float(share) * float(absent_total)
            if bump <= 0:
                continue
            row_mask = (
                team_mask
                & (df["player_id"].astype(int) == int(pid))
                & (df["stat"] == stat)
                & (df["status"] != "OUT")
            )
            sub = df[row_mask]
            if sub.empty:
                continue
            idx = sub.index[0]
            old_q50 = _safe_float(df.at[idx, "q50"])
            ratio_base = max(old_q50, _RATIO_FLOOR)
            # Cap absolute bump so the q50 ratio stays under max_boost.
            max_bump = ratio_base * (max_boost - 1.0)
            applied = min(bump, max_bump)
            if applied <= 0:
                continue
            # Display ratio uses the real old_q50 (so audit `ratio` is the
            # honest new/old multiplier when old_q50 > 0). For internal
            # spread-scaling we use ratio_base (floored) so a near-zero
            # old q10/q90/sigma still gets meaningful scaling.
            spread_ratio = (old_q50 + applied) / ratio_base if ratio_base > 0 else 1.0
            ratio = ((old_q50 + applied) / old_q50
                     if old_q50 > 1e-6 else float("inf"))
            # Scale q10 / q90 by the same multiplicative ratio (preserves
            # spread proportionally). q50 + applied directly.
            old_q10 = _safe_float(df.at[idx, "q10"])
            old_q90 = _safe_float(df.at[idx, "q90"])
            old_sigma = _safe_float(df.at[idx, "sigma"])
            df.at[idx, "q50"] = round(old_q50 + applied, 4)
            df.at[idx, "q10"] = round(old_q10 * spread_ratio, 4)
            df.at[idx, "q90"] = round(old_q90 * spread_ratio, 4)
            # sqrt scaling on sigma keeps variance growth modest.
            df.at[idx, "sigma"] = round(old_sigma * (spread_ratio ** 0.5), 4)
            df.at[idx, "teammate_out_boost"] = round(
                _safe_float(df.at[idx, "teammate_out_boost"]) + applied, 4)
            audit_rows.append({
                "player_id": int(pid),
                "player":    str(df.at[idx, "player"]),
                "stat":      stat,
                "old_q50":   round(old_q50, 4),
                "bump":      round(applied, 4),
                "new_q50":   round(old_q50 + applied, 4),
                "ratio":     (round(ratio, 4)
                              if ratio != float("inf") else float("inf")),
            })

    audit = pd.DataFrame(
        audit_rows,
        columns=["player_id", "player", "stat", "old_q50", "bump",
                 "new_q50", "ratio"])
    return df, audit


def load_out_player_ids(
    injuries_path: str,
    team: str,
    slate_df: Optional[pd.DataFrame] = None,
) -> Set[int]:
    """Resolve OUT-player names from data/injuries_<date>.json → player_ids.

    Uses the slate's own (player_id, player, team) mapping for name->id
    resolution so we don't need a separate roster fetch. Falls back to a
    case-insensitive substring match if exact lookup fails.
    """
    import json
    import unicodedata

    def _norm(s: str) -> str:
        nfkd = unicodedata.normalize("NFKD", str(s or ""))
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

    if not os.path.exists(injuries_path):
        return set()
    try:
        with open(injuries_path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return set()

    out_names = {
        _norm(p.get("name", ""))
        for p in payload.get("players", [])
        if str(p.get("team", "")).strip().upper() == str(team).upper()
        and str(p.get("status", "")).upper() == "OUT"
    }
    if not out_names or slate_df is None or slate_df.empty:
        return set()

    team_rows = slate_df[slate_df["team"].astype(str).str.upper()
                            == str(team).upper()].drop_duplicates("player_id")
    out_ids: Set[int] = set()
    for _, row in team_rows.iterrows():
        nm = _norm(row.get("player", ""))
        if nm in out_names:
            out_ids.add(int(row["player_id"]))
            continue
        # Substring fallback — handles "Michael Porter Jr." vs "Michael Porter"
        for tgt in out_names:
            if tgt and (tgt in nm or nm in tgt) and abs(len(tgt) - len(nm)) <= 4:
                out_ids.add(int(row["player_id"]))
                break
    return out_ids
