"""domains.tennis.asof_pbp -- LEAK-FREE as-of trailing point-by-point features.

Takes the per-(match, player) raw point aggregates from ingest_sackmann_pbp and
turns each into a STRICTLY-PRIOR trailing rate over the player's PRIOR matches
only, via the hardened scripts.platformkit.asof_common.walk_forward_asof
primitive (snapshot-before-update; debut -> NaN; no-future-leak assertion built in).

A match NEVER sees its own points: the as-of value for player P in match M is the
expanding mean of P's stat over matches strictly before M. The match WIN is the
LABEL only, produced separately by attach_label(); it is never an input feature.

To gate vs the surface-Elo base we emit, per match, the p1-minus-p2 DIFFERENCE of
each as-of trailing rate (matching the existing tennis_setdetail_gate convention),
plus n_prior coverage for the degenerate-base / coverage guards.

PURE pandas/numpy + asof_common. No src/kernel/api imports. ASCII only.
CALIBRATION only -- NO $ EDGE; vs_close UNPROVEN.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.asof_common import (  # noqa: E402
    AsofSpec, ExpandingMean, walk_forward_asof,
)

# The point-derived stats we carry into as-of trailing rates.
ASOF_STATS = [
    "bp_save_pct", "bp_convert_pct", "pressure_win_pct",
    "serve1_win_pct", "short_rally_win_pct", "long_rally_win_pct",
    "decider_pts_win_pct",
]


def build_match_player_long(agg: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Join per-(match,player) aggregates to match metadata -> long event table.

    Output one row per (match_id, player) with: date, round, the global player_id,
    each raw stat, and the match WINNER (for the label only). Requires matches to
    carry player ids/names + a date and (winner | p1_won) field.
    """
    m = matches.copy()
    # tolerate a few common column spellings without editing the manifest
    date_col = next((c for c in ("date", "Date", "tourney_date") if c in m.columns), None)
    if date_col is None:
        raise ValueError("matches missing a date column")
    m["_date"] = pd.to_datetime(m[date_col], errors="coerce")
    rnd = next((c for c in ("round", "Round", "match_num", "MatchNum") if c in m.columns), None)
    m["_round"] = m[rnd].astype(str) if rnd else ""

    p1id = next((c for c in ("p1_id", "P1Id", "player1id") if c in m.columns), None)
    p2id = next((c for c in ("p2_id", "P2Id", "player2id") if c in m.columns), None)
    p1nm = next((c for c in ("player1", "Player 1", "p1_name", "P1Name") if c in m.columns), None)
    p2nm = next((c for c in ("player2", "Player 2", "p2_name", "P2Name") if c in m.columns), None)

    def _pid(slot: int):
        idc = p1id if slot == 1 else p2id
        nmc = p1nm if slot == 1 else p2nm
        if idc is not None:
            return m[idc].astype(str)
        if nmc is not None:
            return m[nmc].astype(str).str.strip().str.lower()
        raise ValueError("matches missing both player id and name columns")

    # winner -> p1_won label
    win = next((c for c in ("winner", "Winner", "PlayerWon") if c in m.columns), None)
    if win is not None:
        m["_p1_won"] = (pd.to_numeric(m[win], errors="coerce") == 1).astype("Int64")
    else:
        m["_p1_won"] = pd.NA

    meta = pd.DataFrame({
        "match_id": m["match_id"].astype(str),
        "_date": m["_date"], "_round": m["_round"],
        "pid1": _pid(1), "pid2": _pid(2), "p1_won": m["_p1_won"],
    })

    a = agg.copy()
    a["match_id"] = a["match_id"].astype(str)
    long_rows = []
    for slot in (1, 2):
        sub = a[a["player"] == slot].merge(meta, on="match_id", how="inner")
        sub["player_id"] = sub["pid1"] if slot == 1 else sub["pid2"]
        sub["slot"] = slot
        long_rows.append(sub)
    long = pd.concat(long_rows, ignore_index=True)
    return long


def build_asof(long: pd.DataFrame, stats: Sequence[str] = ASOF_STATS) -> pd.DataFrame:
    """Run the leak-free walk-forward pass; one as-of+n_prior column per stat.

    Returns a per-(match_id, slot) frame. Uses one ExpandingMean accumulator per
    player_id, shared across the player's appearances (slot-blind), snapshotting
    strictly prior to updating with the current match's stat.
    """
    # event_id must be unique per (match, slot) row; walk_forward keys state by player_id.
    work = long.copy()
    work["event_id"] = work["match_id"].astype(str) + "::" + work["slot"].astype(str)
    out = work[["event_id", "match_id", "slot", "player_id", "p1_won", "_date"]].copy()
    for stat in stats:
        if stat not in work.columns:
            continue
        spec = AsofSpec(
            sort_keys=["_date", "match_id", "slot"],
            slots=[("player_id", stat, f"{stat}")],
            id_col="event_id",
        )
        res = walk_forward_asof(work, spec, ExpandingMean)
        out = out.merge(res, on="event_id", how="left")
    return out


def to_match_diff(asof_long: pd.DataFrame, stats: Sequence[str] = ASOF_STATS) -> pd.DataFrame:
    """Pivot per-(match,slot) as-of rows into per-match p1-minus-p2 DIFF features.

    Output one row per match_id: each ``<stat>_asof_diff``, each ``<stat>_n_prior_min``
    (the min of both players' prior counts, for the coverage/degenerate guard), the
    p1_won label, and the date. This is the gate-ready table.
    """
    s1 = asof_long[asof_long["slot"] == 1].set_index("match_id")
    s2 = asof_long[asof_long["slot"] == 2].set_index("match_id")
    common = s1.index.intersection(s2.index)
    s1, s2 = s1.loc[common], s2.loc[common]
    out = pd.DataFrame(index=common)
    out["p1_won"] = pd.to_numeric(s1["p1_won"], errors="coerce")
    out["date"] = s1["_date"].values
    for stat in stats:
        ac, nc = f"{stat}_asof", f"{stat}_n_prior"
        if ac in s1.columns and ac in s2.columns:
            out[f"{stat}_asof_diff"] = s1[ac].values - s2[ac].values
            out[f"{stat}_n_prior_min"] = np.minimum(
                s1[nc].fillna(0).values, s2[nc].fillna(0).values)
    return out.reset_index().rename(columns={"index": "match_id"})
