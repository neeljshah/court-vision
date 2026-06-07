"""_courtvision_form.py — last-5 / last-10 / season medians per player x stat.

Aggregates data/player_quarter_stats.parquet (per-game per-quarter stats)
into last-N + season medians for each player x stat pair. Cached on first
load; lookup is O(1) afterwards.

Public:
    get_form_lookup() -> dict[(player_id_str, stat_lower), {l5, l10, season}]
    attach_form(bets) -> None       # mutates bets in place
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_PARQUET = Path(__file__).resolve().parent.parent / "data" / "player_quarter_stats.parquet"
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _median_arr(arr) -> Optional[float]:
    """Fast median on a numpy array or list, skipping NaNs.

    Avoids the heavy pandas Series.median() dispatch (~0.08ms each × 12K calls
    = ~1s).  np.nanmedian on a small float array is ~5µs — 16× faster.
    """
    if arr is None or len(arr) == 0:
        return None
    a = np.asarray(arr, dtype=float)
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return None
    return round(float(np.median(a)), 2)


@lru_cache(maxsize=1)
def get_form_lookup() -> dict:
    """Return {(player_id_str, stat_lower): {l5, l10, season}} dict."""
    if not _PARQUET.exists():
        log.warning("player_quarter_stats.parquet not found at %s", _PARQUET)
        return {}
    try:
        df = pd.read_parquet(_PARQUET)
    except Exception as exc:
        log.warning("failed to read player_quarter_stats.parquet: %s", exc)
        return {}
    if df.empty:
        return {}
    # Roll up per-quarter rows to per-game per-player.
    agg = {c: "sum" for c in _STATS if c in df.columns}
    if "min" in df.columns:
        agg["min"] = "sum"
    game = df.groupby(["player_id", "game_id"], as_index=False).agg(agg)
    if "game_id" in game.columns:
        # game_id format like '0022400001' — sort lexicographically approximates
        # chronological order within a season (early IDs = early in season).
        game = game.sort_values(["player_id", "game_id"])
    # Pre-select only the stat columns that exist so we can do a single
    # .to_numpy() call per player group (one 2-D array) rather than N
    # separate .to_numpy() calls per stat — avoids the 4K pandas Series
    # constructor overhead that was eating ~0.3s on the prior profiling run.
    stat_cols = [s for s in _STATS if s in game.columns]
    out: dict = {}
    for pid, sub in game.groupby("player_id"):
        sub = sub.tail(120)  # cap memory; rolling window typically << 120 games
        # Single extraction of all stat columns into a contiguous float64 matrix.
        # Shape: (n_games, n_stats). Pandas to_numpy on a multi-column slice
        # is one native call, not N separate ones.
        mat = sub[stat_cols].to_numpy(dtype=float)  # (n, len(stat_cols))
        pid_str = str(pid)
        for i, stat in enumerate(stat_cols):
            vals = mat[:, i]            # 1-D view, no copy
            last5_vals = vals[-5:]
            last10_vals = vals[-10:]
            last5_clean = last5_vals[~np.isnan(last5_vals)]
            out[(pid_str, stat)] = {
                "l5": _median_arr(last5_vals),
                "l10": _median_arr(last10_vals),
                "season": _median_arr(vals),
                "spark": [float(x) for x in last5_clean],
            }
    log.info("form lookup built: %d (player x stat) entries from %d games",
             len(out), len(game))
    return out


def attach_form(bets: list[dict]) -> None:
    """Populate L5/L10/season medians + spark_last5; refresh narrative."""
    if not bets:
        return
    lookup = get_form_lookup()
    if not lookup:
        return
    for b in bets:
        pid = str(b.get("player_id") or "")
        stat = (b.get("prop_stat") or "").lower()
        rec = lookup.get((pid, stat))
        if not rec:
            continue
        if b.get("last_5_median") is None:
            b["last_5_median"] = rec["l5"]
        if b.get("last_10_median") is None:
            b["last_10_median"] = rec["l10"]
        if b.get("season_median") is None:
            b["season_median"] = rec["season"]
        if not b.get("spark_last5"):
            b["spark_last5"] = rec.get("spark", [])
        # Divergence guard: flag bets where the model's q50 is wildly out of
        # line with recent form. Fires when model projects much less / much
        # more than the player's L5 typical. Often catches stale model state
        # (player traded mid-season, role change, returning from injury).
        q50 = b.get("q50")
        l5 = b.get("last_5_median")
        season = b.get("season_median")
        if q50 is not None and l5 is not None and l5 > 0:
            ratio = float(q50) / max(float(l5), 0.5)
            # Use a generous floor (0.5) so tiny rate stats (BLK, STL) where
            # L5 is often 0 don't trip false positives.
            min_anchor_abs = 1.5 if stat in ("pts", "reb", "ast") else 0.6
            if l5 >= min_anchor_abs and ratio <= 0.5:
                b["form_divergence"] = "low"
                b["form_divergence_text"] = (
                    f"Model projects {q50:g} vs L5 typical {l5:g}. "
                    "Check for role change / injury status before betting."
                )
            elif l5 >= min_anchor_abs and ratio >= 2.0:
                b["form_divergence"] = "high"
                b["form_divergence_text"] = (
                    f"Model projects {q50:g} vs L5 typical {l5:g}. "
                    "Unusual upside call — sanity-check minutes/usage."
                )
        narrative = _smart_narrative(b)
        if narrative:
            b["narrative_text"] = narrative


_STAT_FULL = {"PTS": "points", "REB": "rebounds", "AST": "assists",
              "FG3M": "three-pointers made", "STL": "steals",
              "BLK": "blocks", "TOV": "turnovers"}


def _smart_narrative(b: dict) -> str | None:
    """Compose a richer narrative grounded in projection + market-gap signals.

    Drops L5/season-median chatter (audience doesn't trust rolling splits and
    the model already absorbs them) in favor of: q50 vs line, model vs market
    hit-rate gap, minutes/pace context, and injury watch.
    """
    name = b.get("player_name"); stat_u = (b.get("prop_stat") or "").upper()
    opp = b.get("opp"); side = b.get("side"); line = b.get("line"); q50 = b.get("q50")
    if not all((name, stat_u, opp, side, q50 is not None, line is not None)):
        return None
    stat_word = _STAT_FULL.get(stat_u, stat_u.lower())
    arrow = "above" if q50 > line else "below"
    edge_abs = abs(q50 - line)
    parts = [
        f"Model projects {name} for {q50:.1f} {stat_word} vs {opp} "
        f"— {edge_abs:.2f} {arrow} the {line:g} line, so we take the {side}."
    ]
    model_prob = b.get("model_prob"); market_prob = b.get("market_prob")
    if model_prob is not None and market_prob is not None:
        gap_pp = (float(model_prob) - float(market_prob)) * 100.0
        parts.append(
            f"Model hits this {float(model_prob)*100:.0f}% of the time vs "
            f"market-implied {float(market_prob)*100:.0f}% — {gap_pp:+.1f}pp edge."
        )
    ctx_bits: list[str] = []
    mp = b.get("minutes_proj")
    pp = b.get("pace_proj")
    if mp is not None:
        ctx_bits.append(f"min proj {mp:g}")
    if pp is not None:
        ctx_bits.append(f"pace {pp:g}")
    if ctx_bits:
        parts.append("Context: " + " · ".join(ctx_bits) + ".")
    inj = (b.get("injury_status") or "").strip()
    if inj and inj.upper() not in ("ACTIVE", ""):
        parts.append(f"Injury watch: {inj}.")
    best_book = b.get("best_book"); best_price = b.get("best_price")
    if best_book and best_price is not None:
        price_s = f"+{best_price}" if best_price > 0 else str(best_price)
        parts.append(f"Best price: {best_book} at {price_s}.")
    return " ".join(parts)
