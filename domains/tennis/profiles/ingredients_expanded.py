"""domains.tennis.profiles.ingredients_expanded -- ingredient builders for
the 39 EXPANDED tennis attributes (court side, set-number, momentum,
tiebreak, second-serve aggression, game-point conversion, plus the
match_stats x surface-bucket window family). REUSES the SAME charting_points
base filter, match-id parsing (_charting_match_ids/_id_frame) and entity
mapping (_entity_from_underscored) as ingredients.py / prereg_point_
mechanisms.py -- no reimplementation.

WITHIN-GAME POINT INDEX (court side): consecutive charting_points rows
sharing (match_id, set1, set2, gm1, gm2) ARE one game's points in file
order (verified on real data this session -- score_state advances
monotonically row-by-row within a group, e.g. 0-0 -> 15-0 -> 30-0 -> ...).
Standard tennis rule: the server serves from the deuce (right) court on
EVEN points played so far in the game (0-indexed) and the ad (left) court
on ODD points, for the WHOLE game including past deuce (score labels alone
can't do this -- "40-40" recurs every deuce cycle) -- so idx%2 alone
determines side. DERIVABLE, not BLOCKED.

TIEBREAK DETECTION: score_state fails the standard 0/15/30/40/AD parse but
both tokens ARE raw integers (declared TB signature; both corpora carry
raw-integer TB scores). CAVEAT: the opening 0-0 point of a tiebreak is
label-identical to a normal game's first point and is NOT distinguishable
this way -- undercounts n by ~1/breaker, immaterial at the declared floors.

Windows: same YYYY / career_to_2026 convention as ingredients.py.
NETWORK: zero.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.asof_return import _derive_realized_return
from domains.tennis.name_aliases import normalize_name
from domains.tennis.prereg_point_mechanisms import REPO_ROOT, STANDARD, _charting_match_ids, _id_frame
from domains.tennis.profiles.ingredients import CAREER_WINDOW, _entity_from_underscored

_ATP_MATCHES = REPO_ROOT / "data/domains/tennis/matches.parquet"
_WTA_MATCHES = REPO_ROOT / "data/domains/tennis/wta_matches.parquet"
_MATCH_STATS = REPO_ROOT / "data/domains/tennis/match_stats.parquet"

_MATCH_AGG_COLS = {
    "ace_rate": "ace_rate", "df_rate": "df_rate", "first_serve_in": "1st_in_pct",
    "first_serve_win": "1st_win_pct", "second_serve_win": "2nd_win_pct", "bp_saved": "bp_saved_pct",
}


def _base(chart_raw: pd.DataFrame, need_server: bool = True) -> pd.DataFrame:
    """Shared point filter: real date, valid point_winner (and valid server, unless
    a caller wants return-role rows too)."""
    mask = (chart_raw["date_source"] != "missing") & chart_raw["point_winner"].isin((1, 2))
    if need_server:
        mask &= chart_raw["server"].isin((1, 2))
    return chart_raw[mask].copy()


def _with_ids(d: pd.DataFrame) -> pd.DataFrame:
    idf = _id_frame(_charting_match_ids(d["match_id"]))
    return d.merge(idf, on="match_id", how="left")


def _server_entity(d: pd.DataFrame) -> pd.DataFrame:
    """Adds entity_id/entity_name/won/year for the SERVER of each row (needs _with_ids first)."""
    server = d["server"].astype(int)
    name = np.where(server == 1, d["p1_id"], d["p2_id"])
    ent = pd.Series(name, index=d.index).map(_entity_from_underscored)
    d["entity_id"] = [t[0] for t in ent]
    d["entity_name"] = [t[1] for t in ent]
    d["won"] = (d["point_winner"].astype(int) == server.to_numpy()).astype(int)
    d["year"] = pd.to_datetime(d["date"]).dt.year
    return d


def _score_parts(d: pd.DataFrame) -> pd.DataFrame:
    parts = d["score_state"].astype(str).str.split("-", n=1, expand=True)
    d["before_srv"], d["before_ret"] = parts[0].to_numpy(), parts[1].to_numpy()
    return d


def courtside_points(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id/entity_name/year/side/won, side in {deuce,ad} from idx%2 (idx = within-
    game point index, see module docstring)."""
    d = _with_ids(_base(chart_raw))
    d["idx"] = d.groupby(["match_id", "set1", "set2", "gm1", "gm2"], sort=True).cumcount()
    d = _server_entity(d)
    d["side"] = np.where(d["idx"] % 2 == 0, "deuce", "ad")
    return d[["entity_id", "entity_name", "year", "side", "won"]]


def set_bucket_points(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id/entity_name/year/set_bucket/won, set_bucket in {set1,set2,set3plus}
    from set1+set2+1 (sets already won by each side -> current set number)."""
    d = _server_entity(_with_ids(_base(chart_raw)))
    setnum = d["set1"].astype(int) + d["set2"].astype(int) + 1
    d["set_bucket"] = np.where(setnum == 1, "set1", np.where(setnum == 2, "set2", "set3plus"))
    return d[["entity_id", "entity_name", "year", "set_bucket", "won"]]


def game_point_points(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id/entity_name/year/won/game_point (STANDARD-scored points only).
    game_point mirrors prereg_point_mechanisms._break_point for the SERVER side:
    server one point from winning THIS game."""
    d = _score_parts(_base(chart_raw))
    keep = d["before_srv"].isin(STANDARD) & d["before_ret"].isin(STANDARD)
    d = _server_entity(_with_ids(d[keep].copy()))
    d["game_point"] = (d["before_srv"] == "AD") | ((d["before_srv"] == "40") & ~d["before_ret"].isin(("40", "AD")))
    return d[["entity_id", "entity_name", "year", "won", "game_point"]]


def _tiebreak_mask(d: pd.DataFrame) -> pd.Series:
    is_std = d["before_srv"].isin(STANDARD) & d["before_ret"].isin(STANDARD)
    is_num = d["before_srv"].str.fullmatch(r"\d+").fillna(False) & d["before_ret"].str.fullmatch(r"\d+").fillna(False)
    return ~is_std & is_num


def tiebreak_serve_points(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id/entity_name/year/won -- SERVER-perspective tiebreak points only."""
    d = _score_parts(_base(chart_raw))
    d = d[_tiebreak_mask(d)].copy()
    d = _server_entity(_with_ids(d))
    return d[["entity_id", "entity_name", "year", "won"]]


def tiebreak_points(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id/entity_name/year/won -- BOTH match participants (serve or return role
    either way), one row per tiebreak point they were involved in."""
    d = _score_parts(_base(chart_raw, need_server=False))
    d = _with_ids(d[_tiebreak_mask(d)].copy())
    d["year"] = pd.to_datetime(d["date"]).dt.year
    frames = []
    for slot, pid_col in ((1, "p1_id"), (2, "p2_id")):
        won = (d["point_winner"].astype(int) == slot).astype(int)
        ent = d[pid_col].map(_entity_from_underscored)
        frames.append(pd.DataFrame({"entity_id": [t[0] for t in ent], "entity_name": [t[1] for t in ent],
                                     "year": d["year"].to_numpy(), "won": won.to_numpy()}))
    return pd.concat(frames, ignore_index=True)


def point_sequence(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id/entity_name/year/won/event -- BOTH participants, event=True where THIS
    player won the immediately preceding point in the match (serve or return role
    either way). Relies on file row order being chronological within match_id (same
    assumption already verified for the within-game index above)."""
    d = _with_ids(_base(chart_raw, need_server=False))
    d["year"] = pd.to_datetime(d["date"]).dt.year
    frames = []
    for slot, pid_col in ((1, "p1_id"), (2, "p2_id")):
        sub = d.assign(won=(d["point_winner"].astype(int) == slot).astype(int))
        sub["prev_won"] = sub.groupby("match_id", sort=False)["won"].shift(1)
        ent = sub[pid_col].map(_entity_from_underscored)
        sub = sub.assign(entity_id=[t[0] for t in ent], entity_name=[t[1] for t in ent])
        frames.append(sub[["entity_id", "entity_name", "year", "won", "prev_won"]].dropna(subset=["prev_won"]))
    out = pd.concat(frames, ignore_index=True)
    out["event"] = out["prev_won"] == 1
    return out[["entity_id", "entity_name", "year", "won", "event"]]


def service_games(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id/entity_name/year/won(=held)/prev_broken -- one row per (match, service
    game), chronologically sorted, prev_broken=True where the SAME player's own
    PRECEDING service game in that match was lost (rows without a preceding own
    service game are dropped)."""
    d = _with_ids(_base(chart_raw))
    g = d.groupby(["match_id", "set1", "set2", "gm1", "gm2"], as_index=False, sort=True).agg(
        server=("server", "first"), game_winner=("point_winner", "last"), date=("date", "first"),
        p1_id=("p1_id", "first"), p2_id=("p2_id", "first"))
    server = g["server"].astype(int)
    name = np.where(server == 1, g["p1_id"], g["p2_id"])
    ent = pd.Series(name, index=g.index).map(_entity_from_underscored)
    g["entity_id"] = [t[0] for t in ent]
    g["entity_name"] = [t[1] for t in ent]
    g["won"] = (g["game_winner"].astype(int) == server.to_numpy()).astype(int)
    g["year"] = pd.to_datetime(g["date"]).dt.year
    prev_won = g.groupby(["match_id", "entity_id"], sort=False)["won"].shift(1)
    g["prev_broken"] = prev_won == 0
    g = g[prev_won.notna()].reset_index(drop=True)
    return g[["entity_id", "entity_name", "year", "won", "prev_broken"]]


def _won_rollup(df: pd.DataFrame, floor: int, bucket_col: str | None = None, bucket_val=None) -> pd.DataFrame:
    """entity/window won-share rollup (per-year + career, same convention as
    ingredients._window_rollup), optionally restricted to one bucket value."""
    sub = df if bucket_col is None else df[df[bucket_col] == bucket_val]
    yearly = sub.assign(window=sub["year"].astype(int).astype(str))
    career = sub.assign(window=CAREER_WINDOW)
    g = pd.concat([yearly, career], ignore_index=True).groupby(
        ["entity_id", "entity_name", "window"], as_index=False).agg(won=("won", "sum"), n=("won", "count"))
    g = g[g["n"] >= floor].copy()
    g["rate"] = g["won"] / g["n"]
    return g


def _event_vs_baseline(df: pd.DataFrame, event_mask_col: str, floor_event: int, floor_baseline: int) -> pd.DataFrame:
    """entity/window rows with event_rate (won where event_mask_col), baseline_rate
    (won over ALL rows), n_event, n_baseline, delta = event_rate - baseline_rate."""
    base = _won_rollup(df, floor_baseline).rename(columns={"n": "n_baseline", "rate": "baseline_rate"})
    ev = _won_rollup(df[df[event_mask_col]], floor_event).rename(columns={"rate": "event_rate", "n": "n_event"})
    merged = ev.merge(base[["entity_id", "entity_name", "window", "baseline_rate", "n_baseline"]],
                       on=["entity_id", "entity_name", "window"], how="inner")
    merged["delta"] = merged["event_rate"] - merged["baseline_rate"]
    return merged


def match_agg_long() -> pd.DataFrame:
    """One row per (match, participant): entity_id/entity_name/year/surface + the 7
    match_stats window metrics (6 precomputed rate cols reused verbatim + return_pts_won
    derived via asof_return._derive_realized_return, REUSED verbatim from
    serve_return_profiles.py's own join pattern)."""
    ms = pd.read_parquet(_MATCH_STATS)
    frames = []
    for path in (_ATP_MATCHES, _WTA_MATCHES):
        m = pd.read_parquet(path)
        j = ms.merge(m[["event_id", "date", "surface", "p1_name", "p2_name"]], on="event_id", how="inner")
        j = _derive_realized_return(j)
        j["year"] = pd.to_datetime(j["date"]).dt.year
        for me in ("p1", "p2"):
            row = {"entity_id": j[f"{me}_name"].map(lambda n: normalize_name(str(n), source="sackmann")),
                   "entity_name": j[f"{me}_name"], "year": j["year"], "surface": j["surface"],
                   "return_pts_won": j[f"{me}_return_won_realized"]}
            for metric, suffix in _MATCH_AGG_COLS.items():
                row[metric] = j[f"{me}_{suffix}"]
            frames.append(pd.DataFrame(row))
    return pd.concat(frames, ignore_index=True)


def match_agg_windowed(long_df: pd.DataFrame, metric: str, bucket: str, floor: int) -> pd.DataFrame:
    """entity/window rollup of one match_agg metric restricted to one surface bucket
    ("Overall" = no surface restriction), floored on n_matches >= floor."""
    d = long_df if bucket == "Overall" else long_df[long_df["surface"] == bucket]
    d = d.dropna(subset=[metric])
    yearly = d.assign(window=d["year"].astype(int).astype(str))
    career = d.assign(window=CAREER_WINDOW)
    g = pd.concat([yearly, career], ignore_index=True).groupby(
        ["entity_id", "entity_name", "window"], as_index=False).agg(value=(metric, "mean"), n=(metric, "count"))
    return g[g["n"] >= floor]
