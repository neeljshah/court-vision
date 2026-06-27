"""scripts.platformkit.prop_edge -- CONVERGENCE: prop lines x our model -> board.

Joins scraped sportsbook/DFS prop lines to our per-player count distributions and
emits a RANKED, tier-labelled board of CANDIDATE edges. SPORT-DISPATCHED: a per-
sport config (prop_edge_config.SportPropConfig) supplies the engine fn, gamelog
df/parquet, resolver, providers, calibration cache + canonical-stat set. soccer_intl
keeps its leak-free dispersion / club-prior / OPPONENT-multiplier levers; mlb prices
via prop_engine_mlb (exposure=None -> the engine PROJECTS exposure) with those soccer-
only levers OFF. HONESTY (binding): name resolution is the top risk (a wrong match
fabricates a fake edge). tier is "MODEL_VIEW" unless OOS-calibration promotes it.
NEVER raises / fabricates.

Per-file test: python -m pytest scripts/platformkit/test_prop_edge.py -q
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from domains.soccer import dispersion as soccer_dispersion
from domains.soccer import prop_engine  # noqa: F401  monkeypatch target (soccer path)
from domains.soccer.player_rates import CONFIDENCE_N_EFF, player_rate
from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.odds_shop import devig_twoway, ev_vs_price
from scripts.platformkit import prop_edge_config
from scripts.platformkit import prop_tiering
from scripts.platformkit import soccer_team_map  # noqa: F401  monkeypatch target

logger = logging.getLogger(__name__)

_SUPPORTED = set(prop_edge_config.supported_sports())

# MLB reliability gate: require this many leak-free prior exposures (PA for batters,
# BF for pitchers, starts for Outs) behind a rate before calling an MLB edge
# "reliable". Thin priors are shown but DEMOTED (ev_flag uncalibrated_thin), mirroring
# the soccer CONFIDENCE_N_EFF discipline -- a 1-PA "rate" must never look trustworthy.
_MLB_RELIABLE_N = 30

_HONEST_NOTE = prop_edge_config.HONEST_NOTE


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


# Bounded prop fetch. Dead/blocked book scrapers (DraftKings 404, PrizePicks 403,
# BetMGM 400) must never hang the props prediction tick past its cadence -- that is
# what was flapping the m13 tick (supervisor restart loop). Providers are fetched
# CONCURRENTLY under one wall-clock deadline; a provider that exceeds it is recorded
# as "timeout" and skipped, never blocking the board. Tune via PROP_FETCH_DEADLINE_S.
_PROP_FETCH_DEADLINE_S = _env_float("PROP_FETCH_DEADLINE_S", 30.0)


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _load_df(parquet_path: str):
    """Read a sport's gamelog parquet. (df, reason); df None on any failure."""
    try:
        import pandas as pd  # local guarded import
    except Exception as exc:  # noqa: BLE001
        return None, "pandas unavailable (%s)" % type(exc).__name__
    if not os.path.exists(parquet_path):
        return None, "parquet not found: %s" % parquet_path
    try:
        df = pd.read_parquet(parquet_path)
    except Exception as exc:  # noqa: BLE001
        return None, "parquet read failed (%s)" % type(exc).__name__
    if df is None or len(df) == 0:
        return None, "parquet empty"
    return df, None


def _gather(providers: List[Any], sport: str) -> (List[PropLine], Dict[str, str]):
    """Call each provider's fetch_props; multi-source dedup -> best price per key.

    Raw rows are concatenated across providers (keeps the source-health map honest:
    each provider's "ok (N rows)" is the count BEFORE dedup), then collapsed via
    `prop_aggregate.merge_multi_source` so each (player, stat, event_id, line)
    survives once with the HIGHEST decimal on each side. The merged row's source
    is owned by the book whose price actually won -- so a card's `best_book` names
    the real winning book, not the first provider in iteration order. This is what
    enables genuine multi-book best-line for props once sportsbook adapters
    (DraftKings / BetMGM / FanDuel) are wired alongside the DFS pick'em sources.
    """
    provs = list(providers or [])
    raw: List[PropLine] = []
    sources: Dict[str, str] = {}
    names = [getattr(p, "name", p.__class__.__name__) for p in provs]

    # Fetch every provider concurrently under ONE wall-clock deadline so a single
    # hung/blocked scraper can never stall the tick. Futures that miss the deadline
    # are abandoned (their threads finish on their own urllib timeout in the
    # background) and recorded as "timeout"; the board proceeds with what arrived.
    futs: Dict[concurrent.futures.Future, int] = {}
    done: set = set()
    if provs:
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=len(provs))
        try:
            futs = {ex.submit(p.fetch_props, sport): i for i, p in enumerate(provs)}
            done, _not_done = concurrent.futures.wait(
                futs, timeout=_PROP_FETCH_DEADLINE_S)
        finally:
            ex.shutdown(wait=False)
    fut_by_idx = {idx: fut for fut, idx in futs.items()}

    for i, _prov in enumerate(provs):
        name = names[i]
        fut = fut_by_idx.get(i)
        if fut is None or fut not in done:
            sources[name] = "timeout (>%.0fs deadline)" % _PROP_FETCH_DEADLINE_S
            continue
        try:
            res = fut.result()
        except Exception as exc:  # noqa: BLE001 -- a bad provider must not sink the board
            sources[name] = "error: %s" % type(exc).__name__
            continue
        if is_unavailable(res):
            sources[name] = res.get("reason", "unavailable")
            continue
        if not isinstance(res, list):
            sources[name] = "unexpected result shape"
            continue
        rows = [p for p in res if isinstance(p, PropLine)]
        raw.extend(rows)
        sources[name] = "ok (%d rows)" % len(rows)
    if not raw:
        return [], sources
    try:
        from scripts.platformkit.odds_provider.prop_aggregate import merge_multi_source
        lines = merge_multi_source(raw)
    except Exception as exc:  # noqa: BLE001 -- a merge bug must never sink the board
        logger.warning("prop_edge: merge_multi_source failed (%s); using raw rows", exc)
        lines = raw
    return lines, sources


def _confidence(df, player_id, stat_canon: str, as_of: str, club_prior=None) -> str:
    """ok when club-backed OR >=2 WC matches and not shrunk-to-baseline; else thin."""
    try:
        rate = player_rate(df, player_id, stat_canon, as_of, club_prior=club_prior)
    except Exception:  # noqa: BLE001
        return "thin"
    if rate.get("status") != "ok":
        return "thin"
    if float(rate.get("n_eff", 0.0) or 0.0) >= CONFIDENCE_N_EFF:
        return "ok"
    thin = int(rate.get("n_matches", 0)) < 2 or bool(rate.get("shrunk", False))
    return "thin" if thin else "ok"


def _ev_flag(confidence: str, best_ev: Any) -> str:
    """thin -> 'uncalibrated_thin'; |EV|>0.5 (model artifact) -> 'implausible'; else
    'ok'. Flags, never drops the row. Never raises."""
    if confidence == "thin":
        return "uncalibrated_thin"
    try:
        if best_ev is not None and abs(float(best_ev)) > 0.5:
            return "implausible"
    except (TypeError, ValueError):
        return "ok"
    return "ok"


def _apply_ev(edge: Dict[str, Any], line: PropLine, model_p_over: float,
              conf: str) -> None:
    """Attach EV-vs-priced fields when a two-way sportsbook price exists (e.g.
    Underdog balanced), else a model-view gap-from-0.5; then set ev_flag. Shared by
    the soccer + MLB edge paths so the two can never drift. Never raises."""
    op, up = getattr(line, "over_price", None), getattr(line, "under_price", None)
    priced = (op is not None and up is not None
              and line.payout_type == "sportsbook")
    ev_ok = False
    if priced:
        try:
            fair_over, fair_under = devig_twoway(op, up)
            ev_over = ev_vs_price(model_p_over, op)
            ev_under = ev_vs_price(1.0 - model_p_over, up)
            ev_ok = True
        except Exception as exc:  # noqa: BLE001 -- degrade to model-view, never raise
            logger.warning("priced EV failed: %s", exc)
    if ev_ok:
        best_ev, best_side = ((ev_over, "over") if ev_over >= ev_under
                              else (ev_under, "under"))
        edge.update({
            "fair_over": round(fair_over, 4), "fair_under": round(fair_under, 4),
            "ev_over": round(ev_over, 4), "ev_under": round(ev_under, 4),
            "best_ev": round(best_ev, 4), "best_side": best_side,
            "edge_basis": "ev_vs_priced",
        })
    else:
        edge["model_gap"] = round(abs(model_p_over - 0.5), 4)
        edge["edge_basis"] = "model_view"
    edge["ev_flag"] = _ev_flag(conf, edge.get("best_ev"))


def _rank(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """HONESTY-FIRST + CALIBRATION-LED ranking: CALIBRATION_PROVEN reliable+ok edges
    first (by best_ev), then marginal, then the rest -- a weak-stat edge can never
    outrank a proven-stat one on raw EV alone. See prop_tiering."""
    return sorted(edges, key=prop_tiering.calibration_rank_key)


def _build_edges(cfg, sport_key, lines, df, as_of, index, priors_path):
    """Yield per-line {edge|unresolved} outs for *sport_key*. MLB delegates to
    prop_edge_mlb (engine projects exposure; no soccer levers); soccer applies the
    leak-free dispersion / opponent levers computed ONCE here. Never raises here --
    each per-line fn is itself guarded."""
    if sport_key == "mlb":
        from scripts.platformkit import prop_edge_mlb
        for line in lines:
            yield prop_edge_mlb.edge_for_line_mlb(
                cfg, line, df, as_of, index,
                apply_ev=_apply_ev, reliable_n=_MLB_RELIABLE_N)
        return
    try:  # leak-free per-stat NB dispersion, computed ONCE for the board
        dispersions = soccer_dispersion.all_dispersions(df, as_of)
    except Exception as exc:  # noqa: BLE001 -- degrade to Poisson, never raise
        logger.warning("dispersion calibration failed: %s", exc)
        dispersions = {}
    try:  # team_abbr universe for leak-free opponent mapping (light name match)
        team_abbrs = [str(a) for a in df["team_abbr"].dropna().unique()] \
            if "team_abbr" in df.columns else []
    except Exception:  # noqa: BLE001
        team_abbrs = []
    opp_cache: Dict[Any, Dict[str, float]] = {}  # (opp_abbr, as_of) -> {stat: m}
    from scripts.platformkit import prop_edge_soccer
    for line in lines:
        yield prop_edge_soccer.edge_for_line_soccer(
            cfg, line, df, as_of, index, confidence_fn=_confidence,
            apply_ev=_apply_ev, dispersions=dispersions, priors_path=priors_path,
            team_abbrs=team_abbrs, opp_cache=opp_cache)


def build_prop_board(
    sport: str,
    *,
    as_of: Optional[str] = None,
    providers: Optional[List[Any]] = None,
    df=None,
    lines_source: Optional[List[PropLine]] = None,
    priors_path=None,
    calibration_path=None,
) -> Dict[str, Any]:
    """Build the ranked prop-edge board for *sport* (SPORT-DISPATCHED via
    prop_edge_config: soccer_intl + mlb). Returns {sport, as_of, status,
    honest_note, sources, edges, unresolved, unresolved_count,
    calibration_labels}. NEVER raises. *lines_source* bypasses providers for tests;
    *df*/*providers* injectable. *priors_path* = soccer club priors (ignored for
    mlb); *calibration_path* overrides the sport's MEASURED OOS cache (absent ->
    all "unmeasured")."""
    sport_key = (sport or "").lower()
    as_of = as_of or _today_utc()
    base = {
        "sport": sport, "as_of": as_of, "status": "unknown",
        "honest_note": _HONEST_NOTE, "sources": {}, "edges": [],
        "unresolved": [], "unresolved_count": 0, "calibration_labels": {},
    }
    try:
        cfg = prop_edge_config.get_config(sport_key)
        if cfg is None:
            base["status"] = "unknown_sport"
            return base

        if df is None:
            df, reason = _load_df(cfg.parquet_path)
            if df is None:
                base["status"] = "no_data: %s" % reason
                return base

        if lines_source is not None:  # canned source wins for tests
            lines = [p for p in lines_source if isinstance(p, PropLine)]
            base["sources"] = {"injected": "ok (%d rows)" % len(lines)}
        else:
            provs = providers if providers is not None else cfg.default_providers()
            lines, sources = _gather(provs, sport_key)
            base["sources"] = sources

        index = cfg.build_name_index(df)
        cal_path = calibration_path if calibration_path is not None \
            else cfg.calibration_path
        calibration = prop_tiering.load_calibration(cal_path)
        edges: List[Dict[str, Any]] = []
        unresolved: List[Dict[str, Any]] = []
        for out in _build_edges(cfg, sport_key, lines, df, as_of, index, priors_path):
            if "edge" in out:
                edges.append(prop_tiering.apply_tier(out["edge"], calibration))
            else:
                unresolved.append(out["unresolved"])

        base["edges"], base["unresolved"] = _rank(edges), unresolved
        base["unresolved_count"], base["status"] = len(unresolved), "ok"
        base["calibration_labels"] = prop_tiering.label_distribution(base["edges"])
        return base
    except Exception as exc:  # noqa: BLE001 -- public fn must never raise
        logger.warning("build_prop_board failed: %s", exc)
        base["status"] = "error: %s" % type(exc).__name__
        return base

__all__ = ["build_prop_board"]
