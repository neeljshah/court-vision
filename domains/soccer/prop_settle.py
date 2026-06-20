"""domains.soccer.prop_settle -- settle a soccer player prop vs REALIZED stats.

The settlement source is the post-match ESPN per-player stats parquet
(data/domains/soccer/espn_player_stats.parquet): one row per player per match,
keyed by (event_id, player_id). A canonical stat (e.g. "Cards") may map to one or
more raw ESPN columns; we reuse player_rates.CANON_TO_COLS so settlement reads
EXACTLY the same columns the rate engine modelled.

HONESTY: paper settlement only. We never claim a $-edge here -- we record whether
the realized count cleared the line. A .5 line can never push; an INTEGER line
pushes on equality. A missing player / match / stat -> "pending" (NOT a loss).

Public functions NEVER raise -- they degrade to None / {"result": "pending"}.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_prop_settle.py -q
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from domains.soccer.player_rates import CANON_TO_COLS

# Settlement-logic version. BUMP this whenever the realized_stat / settle_prop
# grading semantics change in a way that can move a calibration result (e.g. the
# all-NaN VOID fix that stopped fabricating realized 0.0 for unscraped stats).
# A calibration cache is stamped with the version it was computed under; the
# tiering path REFUSES to emit CALIBRATION_PROVEN from a cache whose stamp does
# not match this value (a result measured under OLD settlement logic must NEVER
# drive a PROVEN label). v2 = post all-NaN VOID fix (no fillna(0.0) fabrication).
SETTLE_LOGIC_VERSION = "v2-void-nan"


def realized_stat(
    realized_df, player_id, event_id, stat_canonical: str
) -> Optional[float]:
    """Sum the CANON_TO_COLS raw columns for one player's row in one match.

    Returns the realized count (float) or None when the canonical stat is unknown,
    the (player_id, event_id) row is absent, no mapped column is present, OR every
    mapped column value for the matched row(s) is NaN (stat genuinely MISSING --
    a DNP / unscraped stat, which must VOID, never be fabricated as a realized 0).
    A genuinely-recorded 0 returns 0.0. Never raises.
    """
    cols = CANON_TO_COLS.get(stat_canonical)
    if cols is None:
        return None
    try:
        import pandas as pd  # local guarded import

        if realized_df is None or len(realized_df) == 0:
            return None
        df = realized_df
        if "player_id" not in df.columns or "event_id" not in df.columns:
            return None
        pid = str(player_id)
        eid = str(event_id)
        mask = (df["player_id"].astype(str) == pid) & (
            df["event_id"].astype(str) == eid
        )
        rows = df.loc[mask]
        if len(rows) == 0:
            return None
        present = [c for c in cols if c in rows.columns]
        if not present:
            return None
        # HONESTY: distinguish a genuinely-recorded 0 from a MISSING stat. A
        # player can have a box-score row (match final, player listed) yet have
        # NaN in the mapped stat column (DNP / not scraped). We must NOT fillna(0)
        # such a NaN -- that fabricates a realized 0.0 and an UNDER on a positive
        # line then always "wins". We only sum NON-NaN values; if EVERY mapped
        # value across the matched row(s) is NaN, the stat is unknown -> None.
        any_real = False
        total = 0.0
        for col in present:
            num = pd.to_numeric(rows[col], errors="coerce")
            if num.notna().any():
                any_real = True
                total += float(num.fillna(0.0).sum())
        if not any_real:
            return None  # row exists but stat is genuinely missing -> VOID/None
        return float(total)
    except Exception:  # noqa: BLE001 -- public fn must never raise
        return None


def settle_prop(
    realized_value: Optional[float], line, side: str
) -> Dict[str, Any]:
    """Grade one prop given the realized count, the line, and the side.

    side "over" wins if realized > line; "under" wins if realized < line; equality
    is a "push" (only reachable on an integer line -- a .5 line never ties). A None
    realized value -> {"result": "pending"}. Never raises.
    """
    if realized_value is None:
        return {"result": "pending", "realized": None}
    try:
        rv = float(realized_value)
        ln = float(line)
    except (TypeError, ValueError):
        return {"result": "pending", "realized": None}
    s = str(side).strip().lower()
    if rv == ln:
        return {"result": "push", "realized": rv}
    over_wins = rv > ln
    if s == "over":
        result = "win" if over_wins else "loss"
    elif s == "under":
        result = "win" if not over_wins else "loss"
    else:
        return {"result": "pending", "realized": rv}
    return {"result": result, "realized": rv}


__all__ = ["realized_stat", "settle_prop", "SETTLE_LOGIC_VERSION"]
