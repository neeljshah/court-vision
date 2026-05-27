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

import pandas as pd

log = logging.getLogger(__name__)

_PARQUET = Path(__file__).resolve().parent.parent / "data" / "player_quarter_stats.parquet"
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _median(s: pd.Series) -> Optional[float]:
    s = s.dropna()
    if s.empty:
        return None
    return round(float(s.median()), 2)


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
    out: dict = {}
    for pid, sub in game.groupby("player_id"):
        sub = sub.tail(120)  # cap memory; rolling window typically << 120 games
        for stat in _STATS:
            if stat not in sub.columns:
                continue
            series = sub[stat]
            last5 = series.tail(5).dropna().tolist()
            out[(str(pid), stat)] = {
                "l5": _median(series.tail(5)),
                "l10": _median(series.tail(10)),
                "season": _median(series),
                "spark": [float(x) for x in last5],
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
        narrative = _smart_narrative(b)
        if narrative:
            b["narrative_text"] = narrative


def _smart_narrative(b: dict) -> str | None:
    """Compose a richer narrative using the populated form data."""
    name = b.get("player_name"); stat_u = (b.get("prop_stat") or "").upper()
    opp = b.get("opp"); side = b.get("side"); line = b.get("line"); q50 = b.get("q50")
    if not all((name, stat_u, opp, side, q50 is not None, line is not None)):
        return None
    l5 = b.get("last_5_median"); l10 = b.get("last_10_median"); s = b.get("season_median")
    parts = [f"{name} projects to {q50:.1f} {stat_u} vs {opp} "
             f"({'OVER' if side == 'OVER' else 'UNDER'} {line:g})."]
    if l5 is not None and s is not None:
        if side == "OVER" and l5 > s + 0.5:
            parts.append(f"L5 median {l5:g} sits above season {s:g} — hot streak supports the OVER.")
        elif side == "UNDER" and l5 < s - 0.5:
            parts.append(f"L5 median {l5:g} sits below season {s:g} — cold spell supports the UNDER.")
        elif l5 is not None and l10 is not None and abs(l5 - l10) > 1.0:
            trend = "trending up" if l5 > l10 else "trending down"
            parts.append(f"L5 {l5:g} vs L10 {l10:g} — {trend} into this matchup.")
        else:
            l10_s = f"{l10:g}" if l10 is not None else "-"
            parts.append(f"L5 {l5:g} / L10 {l10_s} / season {s:g}.")
    inj = (b.get("injury_status") or "").strip()
    if inj and inj.upper() not in ("ACTIVE", ""):
        parts.append(f"Injury watch: {inj}.")
    return " ".join(parts)
