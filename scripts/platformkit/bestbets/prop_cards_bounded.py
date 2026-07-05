"""scripts.platformkit.bestbets.prop_cards_bounded -- bounded/ranked served set.

Split out of prop_cards.py. SERVED prop-card set: ALL priced props (real bets) +
capped, ranked top-N MODEL-ONLY props per sport + an honest "N more" tally. Runs
ONCE per m13 cycle (cached for m10); per-sport work is BOUNDED via
prop_cards_sport_parallel.bucket_model_only_by_sport (2026-07-05, was unbounded).

ALWAYS-FRESH RAIL: MODEL-ONLY props do NOT depend on the external feed (PrizePicks /
Underdog). When the feed 429s, build_bounded_prop_cards FALLS BACK to model-only cards
SYNTHESIZED from the on-disk gamelog parquet (recent players x canonical stats, same
engine, line at the recent mean, honest projection, never fabricated); priced props are
a BONUS when the feed is up. build_synth_only_prop_cards + pregame_games_exist expose
that no-feed synth as the anti-flicker fill the m13 tick uses on a transient empty.
Every served row (incl synth-fallback) is stamped with circuit_skips (never dropped).

HONESTY: edge_claimed ALWAYS False; model-only carry model_only=True / no edge; priced
carry edge_vs_market (a LABELLED prob diff, NOT $). UNITS not $. RAILS: ASCII; stdlib +
repo-internal; <=300 LOC; public fns NEVER raise. Test: test_prop_cards.py."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

# Default fallbacks; real values pulled lazily from prop_cards (circular-import safe).
DEFAULT_MODEL_ONLY_CAP = 50
DEFAULT_MAX_LINES_PER_SPORT = 2500
DEFAULT_PROP_SPORTS = ("soccer_intl", "mlb")

# Recent active players to synthesize model-only cards for per sport (bounded so the
# no-network fallback stays FAST, inside m13 300s) when the feed is unavailable.
SYNTH_PLAYERS_PER_SPORT = 60

logger = logging.getLogger(__name__)

# Calibration label -> reliability rank (higher is better). Unknown -> 0.
_CALIB_RANK = {"proven": 3, "calibrated": 3, "marginal": 2, "weak": 1, "unmeasured": 0, "": 0}

# Per-sport (gamelog-column -> canonical stat) to SYNTHESIZE model-only lines from the
# parquet (line at the player's recent mean) when no feed line exists.
_SYNTH_STATS = {
    "soccer_intl": {
        "totalShots": "Shots", "shotsOnTarget": "Shots On Target",
        "foulsCommitted": "Fouls", "goalAssists": "Goal+Assist",
        "totalGoals": "Goals", "saves": "Saves",
    },
    "mlb": {
        "hits": "Hits", "totalBases": "Total Bases", "rbi": "RBIs",
        "runs": "Runs", "strikeOuts": "Batter Strikeouts",
        "pitch_strikeOuts": "Pitcher Strikeouts",
    },
}


def _rank_key(card: Dict[str, Any]):
    """Sort key: reliable, then calibration, then confidence (reverse=True -> DESC)."""
    reliable = 1 if card.get("reliable") else 0
    calib = _CALIB_RANK.get(str(card.get("calibration", "")).lower(), 0)
    try:
        conf = float(card.get("confidence") or card.get("model_prob") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    return (reliable, calib, conf)


def _half_line(value: float) -> float:
    """Nearest half-point to *value*, floored at 0.5 (honest projection line)."""
    return max(0.5, round(float(value) - 0.5) + 0.5)


def _synth_line(sport, player, team, stat, line_val, as_of, source, event_id):
    """A NO-PRICE model-only PropLine. Shared so both synth paths never drift."""
    from scripts.platformkit.odds_provider.prop_base import PropLine  # noqa: PLC0415
    return PropLine(sport=sport, event_id=event_id, match=(team or ""), player=player,
                    team=team, stat=stat, line=line_val, over_price=None,
                    under_price=None, payout_type="dfs_pickem", source=source, as_of=as_of)


def _synth_lines_for_sport(sport, as_of, n_players):
    """NO-PRICE PropLines from the parquet (recent players x stats, line at recent mean).
    NO network; pure on-disk read. Never raises -> []."""
    stat_map = _SYNTH_STATS.get(sport)
    if not stat_map:
        return []
    try:
        import pandas as pd  # local guarded import
        from scripts.platformkit import prop_edge_config  # noqa: PLC0415
        cfg = prop_edge_config.get_config(sport)
        if cfg is None:
            return []
        df = pd.read_parquet(cfg.parquet_path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("synth(%s): parquet/config unavailable: %s", sport, exc)
        return []
    if df is None or len(df) == 0 or "player" not in df.columns:
        return []
    try:
        if "date" in df.columns:
            df = df.sort_values("date")
        recent = df.tail(max(200, n_players * 12))  # most-recent -> active players
        team_col = "team" if "team" in df.columns else (
            "team_abbr" if "team_abbr" in df.columns else None)
        players = recent[["player"]].dropna().drop_duplicates()
        names = [str(p) for p in players["player"].tolist()[:n_players]]
        team_of: Dict[str, str] = {}  # last-seen team per player (matchup label)
        if team_col:
            for _idx, row in recent[["player", team_col]].dropna().iterrows():
                team_of[str(row["player"])] = str(row[team_col])
        means = _recent_means(recent, stat_map, names)
    except Exception as exc:  # noqa: BLE001
        logger.debug("synth(%s): enumerate failed: %s", sport, exc)
        return []

    lines = []
    for name in names:
        tm = team_of.get(name)
        for col, canon in stat_map.items():
            mean = means.get((name, col))
            # Skip no-signal (mean ~0) stats; _half_line centers near the recent mean.
            if mean is None or float(mean) < 0.5:
                continue
            lines.append(_synth_line(sport, name, tm, canon, _half_line(mean),
                                     as_of, "model_only_synth", "model_only_synth"))
    return lines


def _recent_means(recent, stat_map, names):
    """Per-(player, gamelog-column) recent mean for the line; existing cols only. Never raises -> {}."""
    out: Dict[Any, float] = {}
    try:
        cols = [c for c in stat_map if c in recent.columns]
        if not cols:
            return out
        sub = recent[recent["player"].astype(str).isin(set(names))]
        grp = sub.groupby(sub["player"].astype(str))[cols].mean()
        for name, row in grp.iterrows():
            for col in cols:
                val = row.get(col)
                if val is not None and val == val:  # not None / not NaN
                    out[(str(name), col)] = float(val)
    except Exception:  # noqa: BLE001
        pass
    return out


def _recenter_lines(cards, lines):
    """Re-center each line at the ENGINE projection so p_over lands near 0.5 (honest).
    New line list. Never raises -> the original lines."""
    try:
        proj_of = {(str(c.get("prop_player")), str(c.get("prop_stat"))): c["proj"]
                   for c in cards if c.get("proj") is not None}
        out = []
        for ln in lines:
            pr = proj_of.get((str(getattr(ln, "player", "")),
                              str(getattr(ln, "stat", ""))))
            if pr is None:
                continue
            out.append(_synth_line(ln.sport, ln.player, ln.team, ln.stat,
                                   _half_line(pr), ln.as_of, ln.source,
                                   ln.event_id))
        return out or lines
    except Exception:  # noqa: BLE001
        return lines


def _as_of_for(now) -> str:
    """ET calendar-day date string for *now* (or today); pure, never raises. Keeps synth
    as_of and the stale guard on the same ET boundary; UTC fallback if et_day missing."""
    from datetime import datetime, timezone
    try:
        if now is not None:
            inst = datetime.fromtimestamp(now, tz=timezone.utc)
            try:
                from scripts.platformkit.paper.et_day import now_et_day  # noqa: PLC0415
                return now_et_day(inst)
            except Exception:  # noqa: BLE001 -- et_day unavailable: UTC fallback
                return inst.date().isoformat()
    except (OSError, OverflowError, ValueError):
        pass
    try:
        from scripts.platformkit.paper.et_day import now_et_day  # noqa: PLC0415
        return now_et_day()
    except Exception:  # noqa: BLE001
        return datetime.now(tz=timezone.utc).date().isoformat()


def _synth_model_only_cards(sport: str, now, reliable: bool):
    """Synthesize MODEL-ONLY cards for *sport* WITHOUT the feed via the SAME
    build_prop_board path. TWO PASS: pass 1 harvests each engine projection, pass 2
    re-prices with the line CENTERED there so p_over is honest (~0.5). Never raises."""
    try:
        from scripts.platformkit.bestbets import prop_cards as _pc  # noqa: PLC0415
        lines = _synth_lines_for_sport(sport, _as_of_for(now), SYNTH_PLAYERS_PER_SPORT)
        if not lines:
            return []
        probe = _pc.cards_from_lines(sport, lines, now=now, reliable_only=False)  # pass 1
        centered = _recenter_lines(probe, lines)
        gated = _pc.cards_from_lines(sport, centered, now=now, reliable_only=reliable)  # pass 2
        # ANTI-FLICKER: gate can transiently zero a sport with real games (model_lam
        # jitter); serve the un-gated probe instead of a regressive 0 (still honest --
        # only the reliability LABEL differs).
        if not gated and probe:
            return _pc.cards_from_lines(sport, centered, now=now, reliable_only=False)
        return gated
    except Exception as exc:  # noqa: BLE001
        logger.debug("synth_model_only(%s) failed: %s", sport, exc)
        return []


def _rank_cap(model_only, cap_i, sport, n_more):
    """Rank+cap model-only (best first, top *cap_i*); stamps circuit_skips (idempotent
    re-stamp downstream is a harmless overwrite); records overflow in *n_more*."""
    model_only.sort(key=_rank_key, reverse=True)
    kept = model_only[:cap_i]
    extra = len(model_only) - len(kept)
    if extra > 0:
        n_more[sport] = extra
    _stamp_circuit_skips(kept, sport)
    return kept


def _cap_int(cap) -> int:
    try:
        return max(0, int(cap))
    except (TypeError, ValueError):
        return DEFAULT_MODEL_ONLY_CAP


def pregame_games_exist(now: Optional[float] = None, sports: Optional[tuple] = None) -> bool:
    """True when >=1 sport has SYNTHESIZABLE pregame props on disk (cheap NO-FEED
    check). Never raises -> False (genuinely empty)."""
    _sports = sports if sports is not None else DEFAULT_PROP_SPORTS
    as_of = _as_of_for(now)
    for sport in _sports:
        try:
            if _synth_lines_for_sport(sport, as_of, SYNTH_PLAYERS_PER_SPORT):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _stamp_circuit_skips(cards: List[Dict[str, Any]], sport: str) -> None:
    """Stamp SKIPPED_CIRCUIT entries for *sport* onto served *cards* (delegates to
    prop_cards_circuit_io; was dropped on the dead-provider/synth path). No raise."""
    try:
        from scripts.platformkit.bestbets import prop_cards_circuit_io as _pcio  # noqa: PLC0415
        _pcio.stamp_circuit_skips(cards, sport)
    except Exception:  # noqa: BLE001
        for card in cards:
            card.setdefault("circuit_skips", [])


def build_synth_only_prop_cards(now: Optional[float] = None, sports: Optional[tuple] = None,
                                cap: int = DEFAULT_MODEL_ONLY_CAP, reliable: bool = True):
    """MODEL-ONLY synth, NO feed: the honest fill for a full tick returning 0 cards while
    pregame games exist (same engine, ranked+capped). Cannot 429."""
    from scripts.platformkit.bestbets import prop_cards_sport_parallel as _spar  # noqa: PLC0415
    _sports = sports if sports is not None else DEFAULT_PROP_SPORTS
    cap_i = _cap_int(cap)
    by_sport = _spar.bucket_model_only_by_sport(
        _sports, lambda s: _synth_model_only_cards(s, now, reliable))
    served: List[Dict[str, Any]] = []
    n_more: Dict[str, int] = {}
    for sport in _sports:
        model_only = by_sport.get(sport, [])
        if model_only:
            served.extend(_rank_cap(model_only, cap_i, sport, n_more))
    return served, n_more


def build_bounded_prop_cards(now: Optional[float] = None, sports: Optional[tuple] = None,
                             cap: int = DEFAULT_MODEL_ONLY_CAP, reliable: bool = True,
                             max_lines_per_sport: int = DEFAULT_MAX_LINES_PER_SPORT):
    """BOUNDED, RANKED prop-card set + "N more" tally. ALL priced + top *cap* MODEL-ONLY
    per sport, ranked by reliability/calibration/confidence. ALWAYS-FRESH: no feed
    model-only -> SYNTHESIZE."""
    try:
        from scripts.platformkit.bestbets import prop_cards as _pc  # noqa: PLC0415
        all_cards = _pc.build_prop_cards(now=now, sports=sports, reliable_only=reliable,
                                         max_lines_per_sport=max_lines_per_sport)
        default_sports = _pc.DEFAULT_PROP_SPORTS
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_bounded_prop_cards: build_prop_cards failed: %s", exc)
        all_cards, default_sports = [], DEFAULT_PROP_SPORTS
    _sports = sports if sports is not None else default_sports
    cap_i = _cap_int(cap)
    from scripts.platformkit.bestbets import prop_cards_sport_parallel as _spar  # noqa: PLC0415
    by_sport = _spar.bucket_model_only_by_sport(_sports, lambda s: (
        [c for c in all_cards if c.get("sport") == s and c.get("model_only")]
        or _synth_model_only_cards(s, now, reliable)))
    served: List[Dict[str, Any]] = []
    n_more: Dict[str, int] = {}
    for sport in _sports:  # ALL priced survive; ranked model-only tail
        priced = [c for c in all_cards if c.get("sport") == sport and not c.get("model_only")]
        _stamp_circuit_skips(priced, sport)
        served.extend(priced + _rank_cap(by_sport.get(sport, []), cap_i, sport, n_more))
    return served, n_more


__all__ = ["build_bounded_prop_cards", "build_synth_only_prop_cards", "pregame_games_exist"]
