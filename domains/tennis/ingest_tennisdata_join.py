"""domains.tennis.ingest_tennisdata_join — odds-join machinery.

Extracted from ingest_tennisdata.py (pure move — zero logic change).

Covers:
- JoinResult NamedTuple
- join_odds (inner join logic)
- _in_date_window, _norm_round_td, _tiebreak
- _orient_prices, _build_joined_row, _empty_joined_df
- _parse_date

F5 compliance: ONLY stdlib + numpy/pandas + domains.tennis.* imports.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import NamedTuple

import pandas as pd

from domains.tennis.ingest_tennisdata_load import (
    _add_norm_keys,
    _add_match_norm_keys,
    _norm_round,
)


# ---------------------------------------------------------------------------
# JoinResult — the output of join_odds()
# ---------------------------------------------------------------------------

class JoinResult(NamedTuple):
    """Bucketed output of the odds-join operation.

    Attributes
    ----------
    joined_df:
        Rows that matched a Sackmann event_id; contains the odds.parquet contract.
    unjoined_df:
        Completed rows that did not find a Sackmann match.
    excluded_df:
        Rows excluded because Comment != "Completed" (retirements, walkovers, etc.).
    join_rate:
        joined / (joined + unjoined) for Completed rows only.
    """
    joined_df: pd.DataFrame
    unjoined_df: pd.DataFrame
    excluded_df: pd.DataFrame
    join_rate: float


# ---------------------------------------------------------------------------
# Join helpers
# ---------------------------------------------------------------------------

_DATE_WINDOW_DAYS = 20  # tourney_date ≤ td_date ≤ tourney_date + 20d


def _parse_date(val: object) -> dt.date | None:
    """Coerce a raw date value to a Python date; return None on failure."""
    if pd.isna(val):
        return None
    if isinstance(val, (dt.date, dt.datetime)):
        return val.date() if isinstance(val, dt.datetime) else val
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def _in_date_window(match_date: object, td_date: dt.date) -> bool:
    md = _parse_date(match_date)
    if md is None:
        return False
    delta = (td_date - md).days
    return 0 <= delta <= _DATE_WINDOW_DAYS


def _norm_round_td(r: object) -> str | None:
    return _norm_round(str(r) if r and not (isinstance(r, float)) else None)


def _tiebreak(candidates: list[pd.Series], td_row: pd.Series) -> pd.Series:
    """Pick best candidate from windowed matches."""
    td_round = _norm_round_td(td_row.get("Round"))
    td_date = td_row.get("_date")

    def score(m: pd.Series) -> tuple:
        # 1. Round match (0 = match, 1 = no match)
        round_ok = 0 if (td_round and m.get("round") == td_round) else 1
        # 2. Date proximity
        md = _parse_date(m.get("date"))
        date_dist = abs((td_date - md).days) if (td_date and md) else 999
        # 3. Rank proximity (WRank vs p_rank)
        wrank = td_row.get("WRank")
        p1_rank = m.get("p1_rank")
        rank_dist = abs(float(wrank) - float(p1_rank)) if (
            wrank and p1_rank and not pd.isna(wrank) and not pd.isna(p1_rank)
        ) else 999
        # 4. Lexical event_id
        eid = str(m.get("event_id", ""))
        return (round_ok, date_dist, rank_dist, eid)

    return min(candidates, key=score)


# ---------------------------------------------------------------------------
# §Anti-Leak: orient prices to p1/p2 (outcome-blind)
# ---------------------------------------------------------------------------

def _orient_prices(row: pd.Series, match: pd.Series) -> dict:
    """Map winner/loser prices → p1/p2-oriented prices.

    winner column in matches is int8 (1 = p1 won, 2 = p2 won).
    If winner == 1: W-prices belong to p1, L-prices to p2.
    If winner == 2: W-prices belong to p2, L-prices to p1.
    """
    w = int(match.get("winner", 1))

    def _f32(v: object) -> float | None:
        try:
            f = float(v)
            return f if pd.notna(f) else None
        except (TypeError, ValueError):
            return None

    b365w = _f32(row.get("B365W"))
    b365l = _f32(row.get("B365L"))
    psw = _f32(row.get("PSW"))
    psl = _f32(row.get("PSL"))

    if w == 1:
        b365_p1, b365_p2 = b365w, b365l
        ps_p1, ps_p2 = psw, psl
    else:
        b365_p1, b365_p2 = b365l, b365w
        ps_p1, ps_p2 = psl, psw

    return {
        "b365_p1": b365_p1, "b365_p2": b365_p2,
        "ps_p1": ps_p1, "ps_p2": ps_p2,
    }


def _build_joined_row(td_row: pd.Series, match: pd.Series) -> dict:
    """Assemble one output row for odds.parquet."""
    def _s(v: object) -> str | None:
        return None if pd.isna(v) else str(v)

    def _f32(v: object) -> float | None:
        try:
            f = float(v)
            return f if pd.notna(f) else None
        except (TypeError, ValueError):
            return None

    oriented = _orient_prices(td_row, match)

    return {
        "event_id": _s(match.get("event_id")),
        "date_td": td_row.get("_date"),
        "tour": _s(match.get("tour")),
        "tournament_td": _s(td_row.get("Tournament")),
        "round_td": _s(td_row.get("Round")),
        "comment": _s(td_row.get("Comment")),
        # Raw W/L prices (retained for audit; do NOT use for modelling — leak risk)
        "b365w": _f32(td_row.get("B365W")),
        "b365l": _f32(td_row.get("B365L")),
        "psw": _f32(td_row.get("PSW")),
        "psl": _f32(td_row.get("PSL")),
        "maxw": _f32(td_row.get("MaxW")),
        "maxl": _f32(td_row.get("MaxL")),
        "avgw": _f32(td_row.get("AvgW")),
        "avgl": _f32(td_row.get("AvgL")),
        # P1/P2-oriented prices (use these downstream)
        **oriented,
    }


def _empty_joined_df() -> pd.DataFrame:
    cols = [
        "event_id", "date_td", "tour", "tournament_td", "round_td", "comment",
        "b365w", "b365l", "psw", "psl", "maxw", "maxl", "avgw", "avgl",
        "b365_p1", "b365_p2", "ps_p1", "ps_p2",
    ]
    return pd.DataFrame(columns=cols)


# ---------------------------------------------------------------------------
# Join algorithm (§3.2 spec)
# ---------------------------------------------------------------------------

def join_odds(
    td_df: pd.DataFrame,
    matches_df: pd.DataFrame,
) -> JoinResult:
    """Join a tennis-data season frame to the Sackmann matches frame.

    Parameters
    ----------
    td_df:
        Raw tennis-data rows (from load_raw_season_files or a test fixture).
        Must have columns: Date, Winner, Loser, _tour, _norm_winner, _norm_loser.
    matches_df:
        Sackmann matches frame (contract per §3.1).
        Must have columns: event_id, date, tour, tourney_id, p1_id, p2_id,
        p1_name, p2_name, p1_rank, p2_rank, winner, _norm_p1, _norm_p2.

    Returns
    -------
    JoinResult
    """
    td_df = _add_norm_keys(td_df)
    matches_df = _add_match_norm_keys(matches_df)

    # Parse td dates
    td_df = td_df.copy()
    td_df["_date"] = td_df["Date"].apply(_parse_date)

    # Split td into completed vs excluded
    is_completed = td_df["Comment"].fillna("Completed").str.strip().str.lower() == "completed"
    excluded_df = td_df[~is_completed].copy()
    completed_df = td_df[is_completed].copy()

    joined_rows: list[dict] = []
    unjoined_rows: list[pd.Series] = []

    # Build a multi-candidate index on (tour, frozenset-of-any-candidate-key-pair).
    # For each Sackmann match, enumerate the CARTESIAN product of its two players'
    # candidate-key sets and register the match under each frozenset pair.
    match_index: dict[tuple[str, frozenset], list[pd.Series]] = defaultdict(list)
    for _, m in matches_df.iterrows():
        tour_key = str(m.get("tour", ""))
        cands_p1: set = m.get("_cands_p1") or {m["_norm_p1"]}
        cands_p2: set = m.get("_cands_p2") or {m["_norm_p2"]}
        # Also include the primary (single) norm key as a fallback
        cands_p1 = cands_p1 | {m["_norm_p1"]}
        cands_p2 = cands_p2 | {m["_norm_p2"]}
        seen_pairs: set = set()
        for k1 in cands_p1:
            for k2 in cands_p2:
                pair = frozenset([k1, k2])
                if pair not in seen_pairs:
                    match_index[(tour_key, pair)].append(m)
                    seen_pairs.add(pair)

    for _, td_row in completed_df.iterrows():
        td_date = td_row.get("_date")
        tour = str(td_row.get("_tour", ""))

        # Build candidate key sets for both sides of the td row
        cands_w: set = td_row.get("_cands_winner") or {td_row["_norm_winner"]}
        cands_l: set = td_row.get("_cands_loser") or {td_row["_norm_loser"]}
        cands_w = cands_w | {td_row["_norm_winner"]}
        cands_l = cands_l | {td_row["_norm_loser"]}

        # Collect all matching Sackmann candidates (deduplicated by event_id)
        seen_eids: set = set()
        candidates: list[pd.Series] = []
        for kw in cands_w:
            for kl in cands_l:
                pair_key = frozenset([kw, kl])
                for m in match_index.get((tour, pair_key), []):
                    eid = m.get("event_id")
                    if eid not in seen_eids:
                        candidates.append(m)
                        seen_eids.add(eid)

        # Filter by date window
        if td_date is not None:
            windowed = [
                m for m in candidates
                if _in_date_window(m.get("date"), td_date)
            ]
        else:
            windowed = candidates

        if not windowed:
            unjoined_rows.append(td_row)
            continue

        # Tiebreak: round match → nearest date → rank proximity → lexical event_id
        best = _tiebreak(windowed, td_row)

        joined_rows.append(_build_joined_row(td_row, best))

    # Build DataFrames
    joined_df = pd.DataFrame(joined_rows) if joined_rows else _empty_joined_df()
    unjoined_df = pd.DataFrame(unjoined_rows) if unjoined_rows else pd.DataFrame()

    total = len(joined_rows) + len(unjoined_rows)
    join_rate = len(joined_rows) / total if total > 0 else 0.0

    return JoinResult(
        joined_df=joined_df,
        unjoined_df=unjoined_df,
        excluded_df=excluded_df,
        join_rate=join_rate,
    )
