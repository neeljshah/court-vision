"""live_feed.py -- real games -> model predictions + PM market matching.

Game sources: MockGamesSource/JSONFileSource/NBAScoreboardSource/MLBStatsAPISource.
build_predictions() -> ledger-ready dicts.
active_pairs() -> model-vs-PM pair rows; [] when no live PM market matches a game.

Kalshi + Polymarket are keyless REST feeds; return [] on offseason (honest empty).
No $ field anywhere. clv_status=INSUFFICIENT_DATA always.

Matching order: (1) game_id, (2) canonical team-name key, (3) raw-upper fallback,
(4) per-game binary "Will TEAM win?" via _parse_binary_contract.
Path-4 rejects futures/championship/series/title contracts: a season-long YES price
must NEVER be compared to a per-game model prob.
"""
from __future__ import annotations

import logging
import pathlib as _pathlib
import re as _re
import sys as _sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_HERE = _pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_HERE), str(_ROOT)):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from game_sources import (  # noqa: F401
    MLB_NAME_TO_ABBR, Game, GameSource, JSONFileSource, MLBStatsAPISource,
    MockGamesSource, NBAScoreboardSource, collect_games,
)
from pm_providers import (  # noqa: F401
    PMProvider, KalshiPMProvider, PolymarketPMProvider, _default_pm_providers,
    _odds_event_to_pm_market, _single_binary_to_pm_market,
)

logger = logging.getLogger(__name__)
_FORBIDDEN_KEYS: frozenset = frozenset({"dollar_pnl", "pnl_usd", "dollar",
                                        "pnl", "roi", "profit", "dollar_stake"})


def _canonical_key(sport: str, name: str) -> str:
    """Short code or full name -> stable canonical key. Never raises."""
    try:
        from scripts.platformkit.odds_provider.team_resolver import canonical
        return canonical(sport, name)
    except Exception:
        pass
    tok = _re.sub(r"[^a-z0-9 ]", " ", str(name).lower()).split()
    return "%s:%s" % (str(sport).lower(), tok[-1] if tok else "")


def _matchup_canonical_key(sport: str, home: str, away: str) -> str:
    """Stable three-part matchup key using canonical team names."""
    return "%s|%s|%s" % (_canonical_key(sport, home),
                         _canonical_key(sport, away),
                         str(sport).lower())


# Binary win-phrase patterns (searched in lowercase market title / question).
_BINARY_WIN_PATTERNS = (
    _re.compile(r"will\s+(.+?)\s+win\b"),
    _re.compile(r"(.+?)\s+to\s+win\b"),
    _re.compile(r"(.+?)\s+wins?\b"),
)

# Futures gate: titles containing any of these words describe a season-long or
# multi-game contract. Their YES price is NOT a per-game win probability and must
# not be paired against a single-game model prob in active_pairs Path-4.
_FUTURES_EXCLUDE_RE = _re.compile(
    r"\b(championship|title|series|finals|mvp|division|conference|season|trophy"
    r"|playoff|postseason|superbowl|stanley.cup|world.series|world.cup"
    r"|pennant|gold.glove|cy.young|heisman)\b"
)


def _parse_binary_contract(
    title: str, yes_prob: float, sport: str,
    slate_home: str, slate_away: str,
) -> Optional[Tuple[float, str]]:
    """Resolve a per-game "Will TEAM win?" binary -> (yes_prob, "home"|"away").

    Returns None when:
    - yes_prob is outside (0, 1)
    - the title contains futures/championship/series phrasing (_FUTURES_EXCLUDE_RE)
    - no win pattern matches
    - extracted team does not canonical-match either slate side
    Never raises.
    """
    if not (0.0 < yes_prob < 1.0):
        return None
    low = str(title).lower().strip()
    if _FUTURES_EXCLUDE_RE.search(low):  # reject season-long / futures contracts
        return None
    extracted: Optional[str] = None
    for pat in _BINARY_WIN_PATTERNS:
        m = pat.search(low)
        if m:
            extracted = m.group(1).strip()
            break
    if not extracted:
        return None
    extracted = _re.sub(r"[?!.]+$", "", extracted).strip()
    ext_key = _canonical_key(sport, extracted)
    if ext_key == _canonical_key(sport, slate_home):
        return (yes_prob, "home")
    if ext_key == _canonical_key(sport, slate_away):
        return (yes_prob, "away")
    return None


def make_default_predict_fn() -> Callable[[str, str, str], dict]:
    """Return predict(sport, home, away) -> model result dict. Heavy first call."""
    from scripts.platformkit.predictor_jd import _build_predictor  # lazy
    cache: Dict[str, object] = {}

    def predict(sport: str, home: str, away: str) -> dict:
        pred = cache.get(sport)
        if pred is None:
            pred = _build_predictor(sport)
            cache[sport] = pred
        if pred is None:
            return {}
        return pred.predict(home, away)  # type: ignore[attr-defined]
    return predict


def build_predictions(games: Sequence[Game],
                      predict_fn: Callable[[str, str, str], dict],
                      pred_ts: str, layer: str = "pregame",
                      market: str = "ml") -> List[dict]:
    """Run each real game through the model -> ledger-ready prediction dicts."""
    out: List[dict] = []
    for g in games:
        try:
            res = predict_fn(g.sport, g.home, g.away) or {}
        except Exception:
            continue
        p = res.get("p_home_win", res.get("p1_match_win"))
        if p is None:
            continue
        out.append({
            "sport": g.sport, "layer": layer, "market": market,
            "home": g.home, "away": g.away, "calibrated_prob": float(p),
            "game_id": g.game_id, "game_date": g.game_date, "pred_ts": pred_ts,
            "inputs": {"source": "live_feed", "start_iso": g.start_iso},
        })
    return out


def active_pairs(now: float, *, sources: Optional[Sequence[GameSource]] = None,
                 predict_fn: Optional[Callable[[str, str, str], dict]] = None,
                 pm_providers: Optional[Sequence[PMProvider]] = None,
                 tier: str = "model_vs_pm") -> List[dict]:
    """Return model-vs-PM pair rows; [] when no live PM market matches a game.

    Row keys: market_id sport home away game_id model_prob pm_prob tier
    clv_status captured_at. No $ fields ever.
    """
    _sources = list(sources) if sources is not None else [
        JSONFileSource(), MLBStatsAPISource()]
    games = collect_games(_sources)
    if not games:
        return []
    if predict_fn is None:
        try:
            predict_fn = make_default_predict_fn()
        except Exception:
            predict_fn = None  # type: ignore[assignment]
    model_probs: Dict[str, float] = {}
    game_meta: Dict[str, dict] = {}
    for g in games:
        if predict_fn is None:
            continue
        try:
            res = predict_fn(g.sport, g.home, g.away) or {}
        except Exception:
            continue
        p = res.get("p_home_win", res.get("p1_match_win"))
        if p is None:
            continue
        gkey = g.game_id or ("%s|%s|%s" % (g.sport, g.home, g.away))
        model_probs[gkey] = float(p)
        game_meta[gkey] = {"sport": g.sport, "home": g.home, "away": g.away,
                           "game_id": g.game_id, "start_iso": g.start_iso}
    if not model_probs:
        return []
    _providers = list(pm_providers) if pm_providers is not None else \
        _default_pm_providers()
    pm_markets: List[dict] = []
    for prov in _providers:
        try:
            pm_markets.extend(prov.fetch_markets())
        except Exception:
            continue
    pm_by_gameid: Dict[str, dict] = {}
    pm_by_canonical: Dict[str, dict] = {}
    pm_by_raw: Dict[str, dict] = {}
    pm_binaries: List[dict] = []
    for m in pm_markets:
        gid = str(m.get("game_id", "")).strip()
        if gid:
            pm_by_gameid[gid] = m
        sp = str(m.get("sport", "")).lower()
        hm_raw, aw_raw = m.get("home"), m.get("away")
        if sp and hm_raw is not None and aw_raw is not None:
            hm_str, aw_str = str(hm_raw), str(aw_raw)
            pm_by_canonical.setdefault(_matchup_canonical_key(sp, hm_str, aw_str), m)
            pm_by_raw.setdefault("%s|%s|%s" % (sp, hm_str.upper(), aw_str.upper()), m)
        elif m.get("binary_title") and sp:
            pm_binaries.append(m)
    out: List[dict] = []
    _matched: set = set()

    def _emit(gkey: str, meta: dict, pm_mkt: dict, pm_prob: float) -> None:
        if gkey in _matched or not (0.0 <= pm_prob <= 1.0):
            return
        _matched.add(gkey)
        # venue stamped by providers propagates here; enables _coerce_row validation.
        venue_val = str(pm_mkt.get("venue") or "").strip().lower() or None
        row: Dict[str, object] = {
            "market_id": str(pm_mkt.get("market_id") or gkey),
            "sport": meta["sport"], "home": meta["home"], "away": meta["away"],
            "game_id": meta["game_id"], "model_prob": round(model_probs[gkey], 6),
            "pm_prob": round(pm_prob, 6), "tier": str(tier),
            "clv_status": "INSUFFICIENT_DATA", "captured_at": float(now),
            "freshness_captured_epoch": float(now),  # stale-never-green stamp
        }
        if venue_val:
            row["venue"] = venue_val
        out.append({k: v for k, v in row.items() if k not in _FORBIDDEN_KEYS})

    for gkey in model_probs:
        meta = game_meta[gkey]
        sp, hm, aw = meta["sport"].lower(), meta["home"], meta["away"]

        # Path 1: exact game_id
        pm_mkt = pm_by_gameid.get(meta["game_id"]) if meta["game_id"] else None
        if pm_mkt is not None:
            raw = pm_mkt.get("pm_prob")
            if raw is not None:
                try:
                    _emit(gkey, meta, pm_mkt, float(raw)); continue
                except (TypeError, ValueError):
                    pass

        # Path 2: canonical team-name key
        pm_mkt = pm_by_canonical.get(_matchup_canonical_key(sp, hm, aw))
        if pm_mkt is not None:
            raw = pm_mkt.get("pm_prob")
            if raw is not None:
                try:
                    _emit(gkey, meta, pm_mkt, float(raw)); continue
                except (TypeError, ValueError):
                    pass

        # Path 3: raw uppercased fallback
        pm_mkt = pm_by_raw.get("%s|%s|%s" % (sp, hm.upper(), aw.upper()))
        if pm_mkt is not None:
            raw = pm_mkt.get("pm_prob")
            if raw is not None:
                try:
                    _emit(gkey, meta, pm_mkt, float(raw)); continue
                except (TypeError, ValueError):
                    pass

        # Path 4: per-game "Will TEAM win?" binary only.
        # _parse_binary_contract rejects futures/championship/series titles so
        # a season-long YES price is never compared to a per-game model prob.
        for b in pm_binaries:
            if str(b.get("sport", "")).lower() != sp:
                continue
            title = b.get("binary_title") or ""
            yes_prob = b.get("binary_yes_prob")
            if yes_prob is None:
                continue
            try:
                result = _parse_binary_contract(title, float(yes_prob), sp, hm, aw)
            except Exception:
                continue
            if result is None:
                continue
            pm_prob_resolved, _side = result
            _emit(gkey, meta, b, pm_prob_resolved)
            break

    return out


__all__ = [
    "Game", "GameSource", "MockGamesSource", "JSONFileSource",
    "NBAScoreboardSource", "MLBStatsAPISource", "MLB_NAME_TO_ABBR",
    "collect_games", "build_predictions", "make_default_predict_fn",
    "PMProvider", "KalshiPMProvider", "PolymarketPMProvider",
    "_default_pm_providers", "active_pairs",
    "_canonical_key", "_matchup_canonical_key", "_parse_binary_contract",
    "_single_binary_to_pm_market",
]
