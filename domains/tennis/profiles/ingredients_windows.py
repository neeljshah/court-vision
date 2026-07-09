"""domains.tennis.profiles.ingredients_windows -- ingredient builders for the
WINDOW + OPPONENT-TIER tennis attribute multiplier: per-year match_agg
windows (year_YYYY, GAME-DATED for the leak-free prior-window gate),
opponent-rank-tier splits (top-20 / outside-top-50), and a last-10-matches
FORM snapshot. REUSES the match_stats+matches/wta_matches join
(ingredients_expanded._MATCH_AGG_COLS), asof_hold._derive_realized /
asof_return._derive_realized_return (same realized-stat formulas
serve_return_profiles.py uses), and name_aliases entity keying -- no
reimplementation of any of that machinery.

WINDOW NAMING: year_YYYY (NOT the bare "YYYY" ingredients.py /
ingredients_expanded.py use elsewhere in this package) -- the ONE format
scripts.platformkit.intel_weighting.claim_features.window_to_season(
style="plain") recognizes (_PLAIN_YEAR_RE = ^year_(\\d{4})$), so a year_2024
row is directly consumable by the prior-season-only leak-free gate as "2024"
with zero downstream schema change. year_YYYY rows are the PREDICTIONS-
FACING multiplier: a year_2024 value can condition a 2025 match; career_to_
2026 or last10 rows cannot (the gate refuses any window it can't resolve to
a season strictly prior to the eval season).

opp_rank comes from matches.parquet/wta_matches.parquet's OWN p1_rank/
p2_rank of the OTHER participant in that match -- rows with a missing
opponent rank are DROPPED from tier classification, never guessed.

NETWORK: zero.
"""
from __future__ import annotations

import pandas as pd

from domains.tennis.asof_hold import _derive_realized
from domains.tennis.asof_return import _derive_realized_return
from domains.tennis.name_aliases import normalize_name
from domains.tennis.prereg_point_mechanisms import REPO_ROOT
from domains.tennis.profiles.ingredients_expanded import _MATCH_AGG_COLS

_ATP_MATCHES = REPO_ROOT / "data/domains/tennis/matches.parquet"
_WTA_MATCHES = REPO_ROOT / "data/domains/tennis/wta_matches.parquet"
_MATCH_STATS = REPO_ROOT / "data/domains/tennis/match_stats.parquet"

WINDOW_YEARS = tuple(range(2015, 2026))  # 2015-2025 inclusive, task-declared


def match_agg_long_with_rank() -> pd.DataFrame:
    """One row per (match, participant): entity_id/entity_name/year/date +
    opp_rank (the OTHER participant's rank for that match) + the 7
    MATCH_AGG_METRICS values + serve_pts_won (asof_hold realized rate, for
    the FORM window). Near-mirror of ingredients_expanded.match_agg_long()
    with opp_rank/date/serve_pts_won added -- kept as its own loader rather
    than editing that tested function's return shape."""
    ms = pd.read_parquet(_MATCH_STATS)
    frames = []
    for path in (_ATP_MATCHES, _WTA_MATCHES):
        m = pd.read_parquet(path)
        cols = ["event_id", "date", "surface", "p1_name", "p2_name", "p1_rank", "p2_rank"]
        j = ms.merge(m[cols], on="event_id", how="inner")
        j = _derive_realized(j)
        j = _derive_realized_return(j)
        j["year"] = pd.to_datetime(j["date"]).dt.year
        for me, opp in (("p1", "p2"), ("p2", "p1")):
            row = {
                "entity_id": j[f"{me}_name"].map(lambda n: normalize_name(str(n), source="sackmann")),
                "entity_name": j[f"{me}_name"], "year": j["year"], "date": j["date"],
                "opp_rank": j[f"{opp}_rank"],
                "return_pts_won": j[f"{me}_return_won_realized"],
                "serve_pts_won": j[f"{me}_svpts_won_realized"],
            }
            for metric, suffix in _MATCH_AGG_COLS.items():
                row[metric] = j[f"{me}_{suffix}"]
            frames.append(pd.DataFrame(row))
    return pd.concat(frames, ignore_index=True)


def year_window_rollup(long_df: pd.DataFrame, metric: str, floor: int) -> pd.DataFrame:
    """entity_id/entity_name/window/value/n -- per-year mean of `metric`,
    window='year_<YYYY>', restricted to WINDOW_YEARS, floored on
    n_matches >= floor. A match's year is its OWN calendar year (from
    matches.parquet date) -- a 2019 match never rolls into year_2020."""
    d = long_df.dropna(subset=[metric])
    d = d[d["year"].isin(WINDOW_YEARS)]
    g = d.groupby(["entity_id", "entity_name", "year"], as_index=False).agg(
        value=(metric, "mean"), n=(metric, "count"))
    g = g[g["n"] >= floor].copy()
    g["window"] = "year_" + g["year"].astype(int).astype(str)
    return g[["entity_id", "entity_name", "window", "value", "n"]]


def opponent_tier_rollup(long_df: pd.DataFrame, metric: str, floor: int) -> pd.DataFrame:
    """entity_id/entity_name/tier/value/n -- career mean of `metric` split by
    opponent rank tier (tier='top20': opp_rank<=20; tier='outside_top50':
    opp_rank>50), floored per tier independently. Rows with a NaN opp_rank
    are excluded from BOTH tiers (missing rank != any particular tier)."""
    d = long_df.dropna(subset=[metric, "opp_rank"])
    parts = []
    for tier, mask in (("top20", d["opp_rank"] <= 20), ("outside_top50", d["opp_rank"] > 50)):
        sub = d[mask]
        g = sub.groupby(["entity_id", "entity_name"], as_index=False).agg(
            value=(metric, "mean"), n=(metric, "count"))
        g = g[g["n"] >= floor].copy()
        g["tier"] = tier
        parts.append(g)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["entity_id", "entity_name", "value", "n", "tier"])


def form_last10(long_df: pd.DataFrame, metric: str, floor: int) -> pd.DataFrame:
    """entity_id/entity_name/value/n -- mean of `metric` over each player's
    most recent `floor` matches by date (players with fewer than `floor`
    metric-non-null matches total are excluded, never padded)."""
    d = long_df.dropna(subset=[metric, "date"]).sort_values("date")
    from_end = d.groupby(["entity_id", "entity_name"]).cumcount(ascending=False)
    tail = d[from_end < floor]
    g = tail.groupby(["entity_id", "entity_name"], as_index=False).agg(
        value=(metric, "mean"), n=(metric, "count"))
    return g[g["n"] >= floor]
