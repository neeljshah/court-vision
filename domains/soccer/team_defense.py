"""Leak-free per-opponent, per-stat OPPONENT-ADJUSTMENT multipliers for soccer props.

The prop engine currently uses ``opp_mult = 1.0`` (it ignores the opponent). This
module computes, from REALIZED data only, how much a given opponent team inflates or
suppresses a player's expected count for each canonical stat.

ALLOWED-ATTRIBUTION (the key idea)
----------------------------------
Every match (``event_id``) has exactly two teams (one ``home``, one ``away``). For a
stat we SUM the raw ESPN column(s) across team A's players to get team A's match TOTAL,
then ATTRIBUTE that total as "ALLOWED" / "CONCEDED" by team B (the OTHER team in the
event). So per opponent team B::

    allowed_per_match[stat] = mean over B's matches of (the opposing team's total)

A team that allows MORE shots than the league average -> multiplier > 1 for "Shots".

OPPONENT-SIDE QUANTITY MAPPING (which realized quantity drives each player stat)
-------------------------------------------------------------------------------
For most stats the relevant opponent quantity is what the opponent ALLOWS of the SAME
stat (a forward shoots more vs a team that concedes many shots). Two stats are special:

  * "Fouls Drawn"  <- opponent foulsCommitted (a player draws more fouls vs a team
                      that COMMITS more fouls; the opponent's own committing rate, not
                      what it "allows").
  * "Saves"        <- opponent shotsOnTarget faced (a keeper makes more saves vs a team
                      that puts more shots ON TARGET, i.e. the opponent's SOT total).

  Shots / Shots On Target / Cards / Fouls all map to the opponent's ALLOWED of the same
  canonical stat. Goals / Assists / Goal+Assist / Offsides also map to allowed-of-same.

The mapping is encoded in ``OPP_QUANTITY`` (canonical stat -> the canonical stat whose
ALLOWED-per-match table to read). For Fouls Drawn and Saves the source is a team's own
COMMITTED/SOT total, which the allowed-table already exposes (team X's committed fouls
ARE allowed by its opponents -- but we want team X's OWN committing rate). We therefore
build BOTH an allowed-table and a "for" (own) table and select per stat.

SHRINKAGE + CLAMP
-----------------
The raw ratio ``team_allowed / league_baseline`` is empirical-Bayes shrunk toward 1.0 by
the opponent's match count ``n``::

    mult = (n * ratio + shrink_k * 1.0) / (n + shrink_k)

so a 1-match opponent barely moves off 1.0, then clamped to ``clamp`` (default 0.5..2.0).
Insufficient data -> 1.0.

LEAK-FREENESS (load-bearing): every quantity uses ONLY rows whose ``date`` is STRICTLY
BEFORE ``as_of_date``. Public functions NEVER raise; they degrade to 1.0 / empty dict.

This is ONE matchup lever for calibration input. It is NOT a $-edge; validate by
calibration / CLV. No edge is claimed.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_team_defense.py -q
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd

from domains.soccer.player_rates import CANON_TO_COLS, _as_ts, _prior_rows

SHRINK_K = 3.0
CLAMP = (0.5, 2.0)
_EPS = 1e-9

# canonical stat -> (canonical stat whose table to read, side).
# side "allowed" -> read the opponent's ALLOWED-per-match of that stat.
# side "for"     -> read the team's OWN (committed/produced) per-match of that stat.
OPP_QUANTITY: Dict[str, Tuple[str, str]] = {
    "Shots": ("Shots", "allowed"),
    "Shots On Target": ("Shots On Target", "allowed"),
    "Cards": ("Cards", "allowed"),
    "Fouls": ("Fouls", "allowed"),
    "Assists": ("Assists", "allowed"),
    "Goal+Assist": ("Goal+Assist", "allowed"),
    "Goals": ("Goals", "allowed"),
    "Offsides": ("Offsides", "allowed"),
    # Specials: a player draws more fouls vs a team that COMMITS more fouls;
    # a keeper saves more vs a team that produces more shots ON TARGET.
    "Fouls Drawn": ("Fouls", "for"),
    "Saves": ("Shots On Target", "for"),
}


def opponent_quantity_mapping() -> Dict[str, Tuple[str, str]]:
    """Public copy of the per-stat opponent-quantity mapping (stat -> (src, side))."""
    return dict(OPP_QUANTITY)


def _event_team_totals(rows: pd.DataFrame, stat_canonical: str) -> Optional[pd.DataFrame]:
    """Per (event_id, team) total of a canonical stat. None if cols/keys missing.

    Columns out: event_id, team_abbr, total. One row per team per event.
    """
    cols = CANON_TO_COLS.get(stat_canonical)
    if cols is None:
        return None
    if rows is None or len(rows) == 0:
        return None
    if "event_id" not in rows.columns or "team_abbr" not in rows.columns:
        return None
    work = rows[["event_id", "team_abbr"]].copy()
    total = pd.Series(0.0, index=rows.index)
    for col in cols:
        if col in rows.columns:
            total = total + pd.to_numeric(rows[col], errors="coerce").fillna(0.0)
    work["total"] = total.values
    grp = work.groupby(["event_id", "team_abbr"], as_index=False)["total"].sum()
    return grp


def _allowed_and_for(grp: pd.DataFrame) -> Optional[pd.DataFrame]:
    """From per-(event, team) totals, build per-team allowed + for tables.

    For each event with exactly two teams, team A's total is ALLOWED by team B and is
    A's OWN ("for") total. Returns long frame: team_abbr, allowed, for_, with one row
    per (team, event) appearance. None if no usable two-team events.
    """
    if grp is None or len(grp) == 0:
        return None
    out_rows = []
    for _ev, sub in grp.groupby("event_id"):
        if len(sub) != 2:
            continue  # need exactly two teams to attribute opponent allowance
        recs = sub.to_dict("records")
        a, b = recs[0], recs[1]
        # a's "for" = a's total; a "allowed" = b's total (a conceded b's total).
        out_rows.append({"team_abbr": a["team_abbr"], "for_": a["total"], "allowed": b["total"]})
        out_rows.append({"team_abbr": b["team_abbr"], "for_": b["total"], "allowed": a["total"]})
    if not out_rows:
        return None
    return pd.DataFrame(out_rows)


def team_allowed_table(df: pd.DataFrame, as_of_date) -> pd.DataFrame:
    """Per (team, stat): allowed-per-match mean + n, using matches before as_of_date.

    Returns a tidy frame with columns: team_abbr, stat, allowed_mean, for_mean, n.
    ``n`` is the team's match count for that stat. Empty frame on bad input. The
    table is leak-free: only rows dated STRICTLY BEFORE ``as_of_date`` contribute.
    """
    empty = pd.DataFrame(columns=["team_abbr", "stat", "allowed_mean", "for_mean", "n"])
    prior = _prior_rows(df, as_of_date)
    if prior is None or len(prior) == 0:
        return empty
    frames = []
    for stat in CANON_TO_COLS:
        grp = _event_team_totals(prior, stat)
        long = _allowed_and_for(grp)
        if long is None:
            continue
        agg = long.groupby("team_abbr", as_index=False).agg(
            allowed_mean=("allowed", "mean"),
            for_mean=("for_", "mean"),
            n=("allowed", "size"),
        )
        agg["stat"] = stat
        frames.append(agg)
    if not frames:
        return empty
    out = pd.concat(frames, ignore_index=True)
    return out[["team_abbr", "stat", "allowed_mean", "for_mean", "n"]]


def league_baseline(df: pd.DataFrame, stat: str, as_of, *, side: str = "allowed") -> Optional[float]:
    """League average allowed-per-match (or for-per-match) for a stat, leak-free.

    ``side`` "allowed" -> mean of every team's per-event allowed total; "for" -> mean of
    every team's own per-event total. Both are mathematically equal across the full
    league (every team's allowed is some team's for), but we keep the param for clarity.
    Returns None when the stat is unknown or no two-team events exist before ``as_of``.
    """
    if stat not in CANON_TO_COLS:
        return None
    prior = _prior_rows(df, as_of)
    if prior is None or len(prior) == 0:
        return None
    grp = _event_team_totals(prior, stat)
    long = _allowed_and_for(grp)
    if long is None or len(long) == 0:
        return None
    col = "for_" if side == "for" else "allowed"
    val = pd.to_numeric(long[col], errors="coerce").dropna()
    if len(val) == 0:
        return None
    mean = float(val.mean())
    return mean if mean > _EPS else None


def opponent_multiplier(
    df: pd.DataFrame,
    opponent_team,
    stat_canonical: str,
    as_of_date,
    *,
    shrink_k: float = SHRINK_K,
    clamp: Tuple[float, float] = CLAMP,
) -> float:
    """Empirical-Bayes-shrunk, clamped opponent multiplier for one stat. Never raises.

    Computes ratio = opponent_quantity / league_baseline (per the OPP_QUANTITY mapping),
    shrinks it toward 1.0 by the opponent's match count, and clamps. Returns 1.0 when the
    stat is unknown, the team is unseen, or there is insufficient leak-free data.
    """
    try:
        mapping = OPP_QUANTITY.get(stat_canonical)
        if mapping is None:
            return 1.0
        src_stat, side = mapping
        lo, hi = clamp
        table = team_allowed_table(df, as_of_date)
        if table is None or len(table) == 0:
            return 1.0
        team = str(opponent_team)
        row = table[(table["team_abbr"].astype(str) == team) & (table["stat"] == src_stat)]
        if len(row) == 0:
            return 1.0
        col = "for_mean" if side == "for" else "allowed_mean"
        team_val = float(pd.to_numeric(row.iloc[0][col], errors="coerce"))
        n = float(row.iloc[0]["n"])
        if pd.isna(team_val) or n <= 0:
            return 1.0
        base = league_baseline(df, src_stat, as_of_date, side=side)
        if base is None or base <= _EPS:
            return 1.0
        ratio = team_val / base
        k = max(0.0, float(shrink_k))
        mult = (n * ratio + k * 1.0) / (n + k) if (n + k) > _EPS else 1.0
        return float(min(hi, max(lo, mult)))
    except Exception:
        return 1.0


def all_multipliers(df: pd.DataFrame, opponent_team, as_of_date) -> Dict[str, float]:
    """{canonical stat -> opponent multiplier} for every mapped stat. Never raises."""
    out: Dict[str, float] = {}
    for stat in OPP_QUANTITY:
        out[stat] = opponent_multiplier(df, opponent_team, stat, as_of_date)
    return out
