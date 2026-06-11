"""courtvision_router.py — CourtVision UI routes.

Routes: / (home), /game/{game_id}, /tonight, /share/{slug} (+ qr.svg),
        /plus_ev, /healthz, /api/{slate, bet/{id}, parlays, plus_ev}.
Note: parlays moved to /cv page bottom section; GET /api/parlays JSON route retained.
Helpers in api._courtvision_data. Parlay engine in src.prediction.parlay_engine.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from api._courtvision_data import (
    grade_bet, load_lines_csv, load_slate_csv, slate_no_lines,
)

# Pre-import heavy ML deps at module load time (happens once during server
# startup) so the first cache-miss _build_slate call is not penalised by
# the 1.2s lightgbm + sklearn cold-import tax.
try:
    import lightgbm as _lgb_pre  # noqa: F401
except ImportError:
    pass
try:
    import sklearn as _sk_pre  # noqa: F401
except ImportError:
    pass

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    _limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    _public_limit = _limiter.limit("60/minute")
except Exception:
    _limiter = None
    _public_limit = lambda f: f  # noqa: E731

def register_with_app(app) -> None:
    from api._courtvision_middleware import install; install(app, _limiter)
    # Pre-warm ALL cold-path caches on startup so the first user request
    # never pays the 77s cold-load penalty.
    #
    # Ranked culprits (measured on prod hardware):
    #   1. get_form_lookup()        — player_quarter_stats.parquet  ~1.4-5s
    #   2. _get_win_prob_model()    — win_prob_v3.pkl (2GB RAM scan) ~2-8s
    #   3. _load_predictions()      — predictions_cache_<date>.parquet ~0.5-2s
    #   4. _next_game_day()         — walks O(days x books) CSVs    ~0.5-2s
    #   5. _build_slate()           — CSV I/O + grade_bet grading    ~1-3s
    #
    # All five run concurrently in a background thread at startup. Railway boot
    # stays well under 60s; every subsequent request gets a cache hit (0.24s).
    @app.on_event("startup")
    async def _warm_caches() -> None:
        import asyncio
        import logging as _log
        _logger = _log.getLogger(__name__)

        def _warm_all() -> None:
            _t0 = time.perf_counter()
            steps: list[tuple[str, float]] = []

            def _step(label: str, fn):
                t = time.perf_counter()
                try:
                    fn()
                except Exception as exc:
                    _logger.warning("warmup/%s failed: %s", label, exc)
                steps.append((label, time.perf_counter() - t))

            # 1. form lookup (player_quarter_stats.parquet) — biggest single hit
            from api._courtvision_form import get_form_lookup
            _step("form_lookup", get_form_lookup)

            # 2. win_prob model (win_prob_v3.pkl) — ~2s pickle load on Railway
            _step("win_prob_model", _get_win_prob_model)

            # 3. next-game-day CSV scan — called on every route, cached 60s
            _step("next_game_day", _next_game_day)

            # 4. team stats JSON (instant but ensures the module-level dict is populated)
            _step("team_stats", lambda: _load_nba_team_stats(_NBA_CURRENT_SEASON))

            # 5. NBA player roster (used by consolidate to filter non-NBA props)
            try:
                from api._courtvision_odds import _load_nba_players
                _step("nba_roster", _load_nba_players)
            except Exception:
                pass

            # 6. predictions_cache parquet for today/latest date
            try:
                from api._predictions_overlay import _load_predictions
                warm_date = _today_et()
                _step(f"predictions_cache({warm_date})", lambda: _load_predictions(warm_date))
            except Exception:
                pass

            # 7. slate + grading (triggers consolidate + attach_form, already warm after step 1)
            _step("build_slate", lambda: _build_slate(_today_et()))

            total = time.perf_counter() - _t0
            detail = " | ".join(f"{label}={dur:.2f}s" for label, dur in steps)
            _logger.info("courtvision warmup done in %.2fs: %s", total, detail)

        asyncio.create_task(asyncio.to_thread(_warm_all))

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))
_PRED_DIR = _ROOT / "data" / "predictions"
_LINES_DIR = _ROOT / "data" / "lines"
_BANKROLL_DEFAULT, _TOP_N, _TTL_SEC, _SHARE_TOP_N = 100.0, 50, 8, 8  # _TTL_SEC 30->8: faster live refresh
_PUBLIC_BASE_URL = __import__("os").environ.get("COURTVISION_PUBLIC_URL", "").rstrip("/")
_STAT_SIGMA = {"pts": 6.2, "reb": 2.6, "ast": 2.0, "fg3m": 1.4, "stl": 1.0, "blk": 0.9, "tov": 1.2}  # Empirically calibrated against 50K OOF rows per stat (pregame_oof.parquet) — tail-aware: each value is the smallest multiplier of the residual std where empirical 2σ coverage ≥ 95% AND 3σ coverage ≥ 99% (i.e., honest about fat tails without being over-conservative). Previous (8.5/3.6/2.6/1.7/1.4/1.0/1.7) was ~1.4x too wide vs the OOF residual distribution.
_STATS = tuple(_STAT_SIGMA.keys())
# Playoff-aware sigma boost. Model was trained on regular-season residuals;
# OOF dataset has no playoff games, so the multiplier is from literature
# (NBA playoff prop residuals run ~15-25% wider than regular season due to
# tighter rotations, defensive scheme adjustments, higher-stakes variance).
# 1.20x is the conservative middle of that range.
#
# REAL-MONEY LEVER (triage 2026-06-01, docs/_audits/ROUTER_SIGMA_TRIAGE_2026-06-01.md):
# This multiplier is LIVE on every playoff/Finals date. It widens the per-stat
# residual sigma 20%, which lowers model hit-prob toward 0.5 and therefore feeds
# ev_pct / edge / kelly_stake_dollars on BOTH single props (via grade_bet) and
# parlays (via ParlayEngine sigma_multiplier) — it is NOT display-only. The 1.20
# is a literature-cited assumption, NOT derived from this repo's own validation
# (interval_sigma_recommendation.json is a SEPARATE per-stat base-coverage fix,
# already folded into _STAT_SIGMA above). Made overridable here WITHOUT changing
# the live default: env CV_PLAYOFF_SIGMA_MULT lets a future validated value be
# set without a code change; absent/invalid env preserves the exact 1.20 behavior.
def _resolve_playoff_sigma_mult() -> float:
    """Playoff sigma multiplier. Default 1.20 (UNCHANGED live behavior).

    Override via env `CV_PLAYOFF_SIGMA_MULT` (e.g. "1.0" to disable the boost,
    or a data-validated value). Invalid/absent env -> 1.20, so the live default
    is byte-identical to the prior hard-coded constant.
    """
    _raw = __import__("os").environ.get("CV_PLAYOFF_SIGMA_MULT")
    if _raw is None or not _raw.strip():
        return 1.20
    try:
        _v = float(_raw)
    except (ValueError, TypeError):
        return 1.20
    # Reject non-positive / absurd values; fall back to the safe default.
    if _v <= 0.0 or _v > 5.0:
        return 1.20
    return _v


_PLAYOFF_SIGMA_MULT = _resolve_playoff_sigma_mult()


def _is_playoff_date(date_str: str) -> bool:
    """True if `date_str` (YYYY-MM-DD) falls in the NBA playoff window
    (roughly Apr 15 – Jun 30). Heuristic, not authoritative."""
    if not date_str or len(date_str) < 10:
        return False
    try:
        m = int(date_str[5:7]); d = int(date_str[8:10])
    except (ValueError, TypeError):
        return False
    if m == 4:
        return d >= 15
    if m in (5, 6):
        return True
    return False


def _stat_sigma_for_date(date_str: str) -> dict[str, float]:
    """Per-stat sigma dict, widened for playoff dates."""
    mult = _PLAYOFF_SIGMA_MULT if _is_playoff_date(date_str) else 1.0
    if mult == 1.0:
        return _STAT_SIGMA
    return {k: v * mult for k, v in _STAT_SIGMA.items()}


_BOX_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _parse_clock_to_minutes(clock_str) -> float | None:
    """Parse an NBA clock string like '7:06' or '0:42.3' to minutes."""
    if clock_str is None:
        return None
    if isinstance(clock_str, (int, float)):
        return float(clock_str)
    s = str(clock_str).strip()
    if not s:
        return None
    if ":" in s:
        try:
            mm, ss = s.split(":", 1)
            return float(mm) + float(ss) / 60.0
        except (ValueError, TypeError):
            return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _wp_interpolate_to_boundary(booster_p_home: float, period: int,
                                clock_min: float | None) -> float:
    """Shrink the booster's home-win-prob toward 0.5 by how far the current
    clock is from the snapshot boundary the booster was trained on.

    Boosters are trained at the END of each period (clock 0:00). Using them
    mid-period asks them to predict from out-of-distribution state. We blend
    booster output with 0.5 (uninformative prior) based on clock_min: at the
    boundary, full booster; at the start of the period, exactly 0.5.
    """
    if clock_min is None or clock_min < 0:
        return booster_p_home
    quarter_len = 12.0
    # live_weight = how close we are to the snapshot boundary
    live_weight = max(0.0, min(1.0, 1.0 - (clock_min / quarter_len)))
    return live_weight * booster_p_home + (1.0 - live_weight) * 0.5


def _live_shrink_weight(minutes_played: float) -> float:
    """Sigmoid weight for blending live projection with pregame q50 prior.

    At mp=4 → ~0.07 (mostly pregame), mp=14 → 0.5 (even blend), mp=24 → ~0.93
    (mostly live), mp=36+ → ~1.0. Stops the early-game noise from showing
    silly projections like a star headed for 0 PTS just because he has 3 min
    and hasn't shot yet.

    W-008 (CV_INGAME_L5_ANCHOR): when the flag is ON, the weight is zero-clamped
    until mp >= _L5_ROUTER_MIN_MP (6 minutes), then linearly ramped from 0 to the
    sigmoid value over the 6–12 min window.  Beyond 12 min the curve is the
    standard sigmoid (byte-identical to flag-OFF).  This forces the router to
    serve pure pregame q50 in the first 6 player-minutes (midQ1 territory) where
    the linear extrapolation catastrophically over-projects.

    W-016 (CV_SHRINK_CALIBRATED): when ON, replaces the hand-tuned sigmoid:14:4
    with the MAE-optimal ``l5floor:12:0.30`` curve = linear:12 with a hard floor
    w <= 0.30 when mp < 5.  Validated on 79,884 player-stat records (max-games=200,
    endQ1/Q2/Q3):
      prod sigmoid:14:4 → overall=1.1914  pts=3.5173 reb=1.4604 ast=0.9962
      linear:12         → overall=1.0558  pts=3.2009 reb=1.2876 ast=0.8819
      l5floor:12:0.30   → combined-regime winner (early+endQ1+); endQ1+ overall
                          1.0640 (statistically tied with linear:12 at +0.09%);
                          early (mp<5) PTS MAE 4.99 vs prod 5.24.
    The flag is default-OFF; with it OFF the function is byte-identical to baseline.
    """
    if minutes_played is None or minutes_played <= 0:
        return 0.0
    import math as _m  # noqa: PLC0415
    import os as _os_lsa  # noqa: PLC0415
    mp = float(minutes_played)

    # W-016: CV_SHRINK_CALIBRATED — MAE-optimal l5floor:12:0.30 curve.
    # When flag is ON, return early (before sigmoid) with the calibrated curve.
    # With flag OFF this block is never entered => byte-identical to baseline.
    if _os_lsa.environ.get("CV_SHRINK_CALIBRATED", "0").strip().lower() not in (
        "", "0", "false", "off"
    ):
        # linear:12 with a hard cap w <= 0.30 when mp < 5 (l5floor:12:0.30)
        _SC_T = 12.0        # linear ramp reaches 1.0 at T minutes
        _SC_FLOOR_MP = 5.0  # below this, cap live weight at floor
        _SC_FLOOR_W = 0.30  # early-safety floor value
        w_linear = min(1.0, mp / _SC_T)
        if mp < _SC_FLOOR_MP:
            w_linear = min(w_linear, _SC_FLOOR_W)
        # W-008 L5-anchor: if also ON, prefer the stricter zero-clamp below 6 min
        # (L5-anchor fully zeros <6 min, which is more conservative than the 0.30
        # floor; compose them by taking the minimum weight).
        if _os_lsa.environ.get("CV_INGAME_L5_ANCHOR", "0").strip().lower() not in (
            "", "0", "false", "off"
        ):
            _L5_MIN = 6.0
            _L5_RAMP = 12.0
            if mp < _L5_MIN:
                w_linear = 0.0
            elif mp < _L5_RAMP:
                ramp = (mp - _L5_MIN) / (_L5_RAMP - _L5_MIN)
                w_linear = min(w_linear, ramp * w_linear)
        return w_linear

    sigmoid = 1.0 / (1.0 + _m.exp(-(mp - 14.0) / 4.0))
    # W-008: clamp early-game weight toward 0 when L5-anchor flag is ON.
    if _os_lsa.environ.get("CV_INGAME_L5_ANCHOR", "0").strip().lower() not in (
        "", "0", "false", "off"
    ):
        _L5_ROUTER_MIN_MP = 6.0   # fully pregame below this
        _L5_ROUTER_RAMP_MP = 12.0  # full sigmoid weight above this
        if mp < _L5_ROUTER_MIN_MP:
            return 0.0
        if mp < _L5_ROUTER_RAMP_MP:
            ramp = (mp - _L5_ROUTER_MIN_MP) / (_L5_ROUTER_RAMP_MP - _L5_ROUTER_MIN_MP)
            return ramp * sigmoid
    return sigmoid


def _shrink_player_minutes_from_snapshot(snap: dict) -> dict[str, float]:
    """Extract player_name.lower → minutes_played from a snapshot. Used by
    live-regrade callsites that don't have direct access to box_score rows."""
    out: dict[str, float] = {}
    if not isinstance(snap, dict):
        return out
    for lp in snap.get("players") or []:
        if not isinstance(lp, dict):
            continue
        nm = (lp.get("name") or lp.get("player") or lp.get("player_name") or "").lower()
        if not nm:
            continue
        mp_raw = lp.get("minutes") or lp.get("min") or lp.get("mp")
        mp = None
        if isinstance(mp_raw, (int, float)):
            mp = float(mp_raw)
        elif isinstance(mp_raw, str) and ":" in mp_raw:
            try:
                mm, ss = mp_raw.split(":", 1)
                mp = int(mm) + int(ss) / 60.0
            except Exception:
                mp = None
        elif isinstance(mp_raw, str):
            try:
                mp = float(mp_raw)
            except ValueError:
                mp = None
        if mp is not None:
            out[nm] = mp
    return out


def _regrade_bet_with_live_q50(bet: dict, new_q50: float,
                               stat_sigma: dict[str, float],
                               bankroll: float = 100.0,
                               cap_model_prob: float = 0.85) -> None:
    """Mutate `bet` in place to reflect a live q50 update.

    Recomputes side, edge_units, model_prob (under Normal), ev_pct (with 0.85
    cap), and kelly_stake_dollars (quarter-Kelly + 4% hard cap). Marks the
    bet with `live_regraded: True` so the UI can flag it."""
    from math import erf, sqrt  # noqa: PLC0415

    def _cdf(z): return 0.5 * (1.0 + erf(z / sqrt(2.0)))

    stat = (bet.get("prop_stat") or "").lower()
    sigma = stat_sigma.get(stat, 1.0)
    line = float(bet["line"])

    # Original (pregame / prior) side+price — used as the safe fallback when a
    # live flip lands on a side that has NO book price (so we never show a
    # flipped side carrying the wrong-side odds).
    orig_side = (bet.get("side") or ("OVER" if new_q50 >= line else "UNDER")).upper()
    orig_price = bet.get("best_price")

    side = "OVER" if new_q50 >= line else "UNDER"
    flipped = side != orig_side
    # ALWAYS reselect best_book/best_price for the (possibly new) side using
    # the full per-book over+under ladder stored at slate-build time.
    # Filter ladder to ONLY books that (a) have a real price on the new side
    # AND (b) are FRESH (< 15 min old). Otherwise stale 32-hour-old BetMGM
    # quotes win as "best price" against live DK/FanDuel.
    side_key = "over_odds" if side == "OVER" else "under_odds"
    ladder = bet.get("_books_full") or []
    from datetime import datetime as _dt2, timezone as _tz2  # noqa: PLC0415
    _now_dt = _dt2.now(_tz2.utc)
    FRESH_LADDER_SEC = 900  # 15 minutes
    def _ladder_fresh(b):
        ts = (b.get("captured_at") or "").strip()
        if not ts:
            return False
        try:
            dt = _dt2.fromisoformat(ts.replace("Z", "+00:00"))
            return (_now_dt - dt).total_seconds() <= FRESH_LADDER_SEC
        except (ValueError, TypeError):
            return False
    # B-1 (CV_LIVE_ODDS_VALID_GUARD): drop invalid odds (|odds| < 100) from the
    # live best-price selection. An invalid in-play quote (0 / +50 / -99) passes
    # the loader's [-400,400] sane filter, but the payout formula below treats
    # |price| < 100 as even-money (+100) — inflating EV ~2x and maxing Kelly on a
    # glitch quote. Mirrors the hard pregame grade_bet rule (always drop
    # |odds| < 100). Gated default-OFF: byte-identical unless an invalid odd is
    # actually present in the ladder (real books never post |odds| < 100).
    _live_odds_guard = (os.environ.get("CV_LIVE_ODDS_VALID_GUARD", "").strip().lower()
                        not in ("", "0", "false", "no", "off"))
    def _odds_ok(b):
        if not _live_odds_guard:
            return True
        try:
            return abs(int(b.get(side_key))) >= 100
        except (TypeError, ValueError):
            return False
    real_quotes = [b for b in ladder
                   if b.get(side_key) is not None and _ladder_fresh(b) and _odds_ok(b)]
    stale_fallback = False
    if not real_quotes:
        # No fresh quotes — fall back to any real quote regardless of age,
        # so the bet still has a defensible price (just slightly stale).
        any_age = [b for b in ladder if b.get(side_key) is not None and _odds_ok(b)]
        if any_age:
            stale_fallback = True
        real_quotes = any_age
    if stale_fallback:
        # Bug 2: surface that the price backing this regrade is an any-age
        # (>15 min) quote so the UI can warn the user it may be stale.
        bet["live_regraded_stale_price"] = True
    if real_quotes:
        best = max(real_quotes, key=lambda b: int(b[side_key]))
        bet["best_book"] = best.get("book")
        bet["best_price"] = int(best[side_key])
        # Update per-side all_books for the NEW side using only real quotes
        bet["all_books"] = sorted(
            [{"book": b["book"], "price": int(b[side_key])}
             for b in real_quotes],
            key=lambda r: -r["price"])
    else:
        # No book (any age) has a price for the NEW side.
        bet["live_regraded_no_price"] = True
        if flipped and orig_price is not None:
            # Bug 1: the live q50 flipped the side but the new side is unpriced.
            # Do NOT keep the flipped label on top of the OLD side's odds — that
            # shows a wrong-side price. Revert to the original side+price and
            # regrade the ORIGINAL side against the live q50 instead.
            side = orig_side
            side_key = "over_odds" if side == "OVER" else "under_odds"
        # else: not flipped (same side, just lost its price), or no original
        # price to fall back to — keep whatever best_price already on the bet.

    if bet.get("best_price") is None:
        # Nothing priced at all (no fresh, no any-age, no original) — cannot do
        # price-based EV/Kelly math. Mark, keep prior values, and bail out so we
        # don't divide by a fake price or rank a no-price card.
        bet["live_regraded_no_price"] = True
        bet["live_regraded"] = True
        bet["live_q50"] = round(new_q50, 3)
        bet["q50"] = round(new_q50, 3)
        bet["side"] = side
        bet["edge_units"] = round(new_q50 - line, 3)
        return

    price = int(bet["best_price"])

    z = (line - new_q50) / sigma
    p_over = 1.0 - _cdf(z)
    model_prob = p_over if side == "OVER" else (1.0 - p_over)

    payout = (float(price) if price >= 100 else (10000.0 / abs(price)) if price <= -100 else 100.0)
    ev_capped = False
    if model_prob > cap_model_prob:
        model_prob = cap_model_prob
        ev_capped = True
    ev_pct = model_prob * payout - (1.0 - model_prob) * 100.0

    # Quarter-Kelly with MAX_BET_PCT=0.04 hard cap (matches grade_bet behavior).
    b = payout / 100.0
    p = model_prob; q = 1.0 - p
    full_kelly = (p * b - q) / b if b > 0 else 0.0
    kf = max(0.0, full_kelly) * 0.25
    kelly_dollars = round(min(kf, 0.04) * bankroll, 2)

    bet["q50"] = round(new_q50, 3)
    bet["side"] = side
    bet["edge_units"] = round(new_q50 - line, 3)
    bet["model_prob"] = round(model_prob, 4)
    payoff_inv = 100.0 / (100.0 + payout)
    bet["market_prob"] = round(payoff_inv if price > 0 else float(abs(price) / (100.0 + abs(price))), 4)
    bet["ev_pct"] = round(ev_pct, 2)
    bet["ev_capped"] = ev_capped
    bet["kelly_stake_dollars"] = kelly_dollars
    bet["live_regraded"] = True
    bet["live_q50"] = round(new_q50, 3)

    # Regenerate narrative text using the live-regraded values
    try:
        bet["narrative_text"] = _build_live_narrative(bet, new_q50)
    except Exception:
        pass  # Keep pregame text if generation fails


def _build_live_narrative(bet: dict, new_q50: float) -> str:
    """Return a live-update narrative sentence for a regraded bet card.

    Uses only fields already present in *bet* after mutation by
    _regrade_bet_with_live_q50; handles any missing field gracefully.
    """
    _STAT_FULL = {
        "pts": "points", "reb": "rebounds", "ast": "assists",
        "fg3m": "three-pointers made", "stl": "steals",
        "blk": "blocks", "tov": "turnovers",
    }
    player = bet.get("player_name") or "Player"
    opp = bet.get("opp") or "opponent"
    stat_key = (bet.get("prop_stat") or "").lower()
    stat_word = _STAT_FULL.get(stat_key, (bet.get("prop_stat") or stat_key).upper())
    side = (bet.get("side") or "OVER").upper()
    try:
        line = float(bet["line"])
    except (KeyError, TypeError, ValueError):
        line = 0.0
    abs_edge = abs(new_q50 - line)
    arrow = "below" if side == "UNDER" else "above"
    model_prob = float(bet.get("model_prob") or 0.0)
    market_prob_raw = bet.get("market_prob")
    best_book = bet.get("best_book") or ""
    best_price_raw = bet.get("best_price")

    # Build price phrase (American odds)
    if best_price_raw is not None:
        try:
            bp = int(best_price_raw)
            price_phrase = f"+{bp}" if bp > 0 else str(bp)
        except (ValueError, TypeError):
            price_phrase = str(best_price_raw)
    else:
        price_phrase = "N/A"

    # Edge in percentage points vs market
    if market_prob_raw is not None:
        try:
            market_prob = float(market_prob_raw)
            edge_pp = (model_prob - market_prob) * 100.0
            market_part = (
                f"Model hits this {model_prob * 100:.0f}% of the time vs "
                f"market-implied {market_prob * 100:.0f}% — {edge_pp:+.1f}pp edge."
            )
        except (ValueError, TypeError):
            market_part = f"Model hits this {model_prob * 100:.0f}% of the time."
    else:
        market_part = f"Model hits this {model_prob * 100:.0f}% of the time."

    book_part = (
        f" Best price: {best_book} at {price_phrase}."
        if best_book
        else ""
    )

    return (
        f"Live update: model now projects {player} for {new_q50:.1f} {stat_word} vs {opp} — "
        f"{abs_edge:.2f} {arrow} the {line:g} line, so we take the {side}. "
        f"{market_part}{book_part}"
    )


def _box_pred_parquet_for(date: str, game_id: str = "") -> "Optional[Path]":
    """Resolve the first existing predictions_cache parquet for a matchup,
    trying ET-date semantics so a pregame box renders even when the caller
    passes the UTC calendar date.

    predictions_cache is keyed by ET game date (e.g. 2026-05-30). Callers
    sometimes pass the UTC calendar date (e.g. 2026-05-31 for a game tipping
    at 2026-05-31T00:10Z = 2026-05-30 8:10 PM ET). Probe, in order:
      1. `date` as given
      2. the ET date derived from the game's start_time (games_lookup)
      3. `date - 1 day`
    and return the first parquet that exists, else None.
    """
    from datetime import datetime as _dt, timedelta as _td  # noqa: PLC0415
    cache_dir = _ROOT / "data" / "cache"
    candidates: list[str] = []

    def _add(d: str) -> None:
        if d and d not in candidates:
            candidates.append(d)

    _add(date)
    # ET date of the game's start_time, resolved via games_lookup.
    if game_id:
        try:
            info = _load_games_lookup().get(str(game_id)) or {}
            st = info.get("start_time") or info.get("start_time_iso") or ""
            if st:
                _add(_et_date_from_iso(st))
        except Exception:
            pass
    # date - 1 day (ET is at most 5h behind UTC; an evening tip is 1 day back).
    try:
        _add((_dt.strptime(date, "%Y-%m-%d") - _td(days=1)).strftime("%Y-%m-%d"))
    except (ValueError, OverflowError):
        pass

    for d in candidates:
        pq = cache_dir / f"predictions_cache_{d}.parquet"
        if pq.exists():
            return pq
    return None


def _build_box_score(date: str, away_abbr: str, home_abbr: str,
                     game_id: str = "") -> dict:
    """Projected per-player box score for a matchup, pivoted from
    predictions_cache_<date>.parquet. Pregame-only; live overlay is added
    client-side by polling /api/live/<game_id>.

    ET-date fallback: predictions_cache is keyed by ET game date. When the
    parquet for `date` is missing, fall back to the ET date of the game's
    start_time and then `(date - 1 day)` (see _box_pred_parquet_for).
    """
    import pandas as pd  # noqa: PLC0415
    pq = _box_pred_parquet_for(date, game_id)
    if pq is None:
        return {"away": None, "home": None, "have_data": False, "stats": list(_BOX_STATS)}
    try:
        df = pd.read_parquet(pq)
    except Exception:
        return {"away": None, "home": None, "have_data": False, "stats": list(_BOX_STATS)}

    teams = {(away_abbr or "").upper(), (home_abbr or "").upper()}
    df = df[df["team"].str.upper().isin(teams)].copy()
    if df.empty:
        return {"away": None, "home": None, "have_data": False, "stats": list(_BOX_STATS)}

    def team_rows(abbr: str) -> dict:
        ab = abbr.upper()
        team_df = df[df["team"].str.upper() == ab]
        if team_df.empty:
            return {"abbr": ab, "players": [], "totals": {}, "mean_totals": {}}
        pivot = team_df.pivot_table(
            index=["player_id", "player_name"],
            columns="stat", values="q50", aggfunc="first",
        ).reset_index()
        if "pts" in pivot.columns:
            pivot = pivot.sort_values("pts", ascending=False, na_position="last")
        players = []
        for _, r in pivot.iterrows():
            row = {"player_id": int(r["player_id"]) if pd.notna(r["player_id"]) else None,
                   "player_name": str(r["player_name"])}
            for s in _BOX_STATS:
                v = r.get(s) if s in pivot.columns else None
                row[s] = round(float(v), 1) if (v is not None and pd.notna(v)) else None
            players.append(row)
        # Sum-of-medians per stat (the literal q50 totals; conservative for skewed counts).
        totals = {s: round(float(team_df[team_df["stat"] == s]["q50"].sum()), 1) for s in _BOX_STATS}
        # Mean-of-distribution estimate per player using Pearson-Tukey right-skew
        # weighting (0.05*q10 + 0.70*q50 + 0.25*q90). Sums to a number comparable
        # to Pinnacle's team-total line, NOT to the sum of medians above.
        #
        # CV_MEAN_TOTALS_DEBIAS (default OFF = byte-identical):
        # The asymmetric 0.25*q90 weight inflates the pre-tip anchor by ~15-20%
        # vs actual NBA team PTS (e.g. 118->99 pts for OKC), biasing
        # _pregame_wp_from_projection OVER. When ON, re-center to the
        # symmetric 3-point approximation (q10+q50+q90)/3 which removes the
        # right-skew OVER bias while still using the full distribution shape.
        import os as _os_mttd  # noqa: PLC0415
        _mt_debias = (_os_mttd.environ.get("CV_MEAN_TOTALS_DEBIAS", "0").strip() == "1")
        mean_totals = {}
        for s in _BOX_STATS:
            sub = team_df[team_df["stat"] == s]
            if _mt_debias:
                # Symmetric 3-point approximation — removes the q90-OVER bias.
                est = ((sub["q10"] + sub["q50"] + sub["q90"]) / 3.0).sum()
            else:
                est = (0.05 * sub["q10"] + 0.70 * sub["q50"] + 0.25 * sub["q90"]).sum()
            mean_totals[s] = round(float(est), 1)
        return {"abbr": ab, "players": players, "totals": totals, "mean_totals": mean_totals}

    away = team_rows(away_abbr)
    home = team_rows(home_abbr)
    return {
        "away": away, "home": home,
        "have_data": bool(away["players"] or home["players"]),
        "stats": list(_BOX_STATS),
    }


router = APIRouter()
_CACHE: dict = {}

# Short-TTL cache for _today_et() — the function walks the live/ and lines/
# directories with 3496+ stat() calls per invocation.  Caching for 10s
# eliminates ~0.1s on every cache-miss _build_slate call while keeping
# the "live game date" logic fresh enough for real-time use.
_TODAY_ET_CACHE: tuple[float, str] = (0.0, "")
_TODAY_ET_TTL = 10.0  # seconds

def _is_epoch_snap(p: "Path") -> bool:
    """True only for real epoch-timestamped snapshots ({gid}_<digits>.json).

    The poller also writes NAMED SENTINEL files — {gid}_pregame.json,
    {gid}_final.json, {gid}_endq3.json — whose stems end in a word, not an
    epoch. Those sentinels sort AFTER epoch files in ASCII order ('p'/'f'/'e'
    all exceed any digit), so a naive `sorted(...)[-1]` snapshot picker would
    return e.g. _pregame.json (no players / no period / no game_status),
    silently disabling the live box score, live regrade, and the whole live
    bet pipeline. Filter through this before sorting/picking by timestamp.
    """
    return p.stem.rpartition("_")[2].isdigit()


def _epoch_snaps(live_dir: "Path", gid: str) -> "list[Path]":
    """Sorted (ascending) list of epoch-timestamped snapshots for `gid`,
    excluding named sentinel files. `[-1]` is the latest real snapshot."""
    return sorted(
        p for p in live_dir.glob(f"{gid}_*.json") if _is_epoch_snap(p)
    )


# Short-TTL cache for the live/ directory index.  Scanning 2965+ JSON files
# with pathlib.iterdir() + is_file() costs ~70ms per call.  We cache the
# {gid_prefix: Path} map for 5s (snapshot files are written every ~10s by
# the poller, so 5s staleness never misses a real update cycle).
_LIVE_DIR_INDEX_CACHE: tuple[float, dict] = (0.0, {})
_LIVE_DIR_INDEX_TTL = 5.0  # seconds
_LIVE_DIR_PATH = _ROOT / "data" / "live"


def _get_live_dir_index() -> dict:
    """Return a cached {gid_prefix: latest_path} index of data/live/*.json."""
    global _LIVE_DIR_INDEX_CACHE
    ts, idx = _LIVE_DIR_INDEX_CACHE
    if idx and time.time() - ts < _LIVE_DIR_INDEX_TTL:
        return idx
    new_idx: dict = {}
    if _LIVE_DIR_PATH.exists():
        try:
            for _p in _LIVE_DIR_PATH.iterdir():
                if not _p.is_file() or _p.suffix != ".json":
                    continue
                # Skip named sentinel files ({gid}_pregame/_final/_endq3.json):
                # they have no players/period and their stems sort AFTER epoch
                # files, so they'd win the `_p.name > existing.name` race and
                # poison the index with an empty snapshot.
                if not _is_epoch_snap(_p):
                    continue
                _pfx = _p.stem.split("_")[0]
                existing = new_idx.get(_pfx)
                if existing is None or _p.name > existing.name:
                    new_idx[_pfx] = _p
        except Exception:
            pass
    _LIVE_DIR_INDEX_CACHE = (time.time(), new_idx)
    return new_idx


def _latest_snap_path(gid: str) -> "Optional[Path]":
    """Latest epoch snapshot Path for a single game_id, via the cached
    directory index (NOT a per-call glob).

    The home page resolves the freshest snapshot for ~5-15 game_ids per
    cold build. Each `_epoch_snaps()` call globs the entire data/live/
    directory (~30K files, ~70ms each), so 15 calls cost ~1.0s on cold
    start. `_get_live_dir_index()` walks the directory ONCE (cached 5s)
    and yields the same latest-epoch Path that `_epoch_snaps(...)[-1]`
    would return — game_ids are underscore-free 10-digit IDs, so the
    index key `stem.split("_")[0]` equals the gid exactly.
    """
    return _get_live_dir_index().get(gid)


def _et_date_from_iso(iso_ts: str) -> str:
    """Convert an ISO-8601 UTC timestamp to America/New_York YYYY-MM-DD.

    NBA games are scheduled in ET. A 7:00 PM ET tipoff lives as
    `YYYY-MM-DDT23:00:00Z` in the line CSVs — using UTC-date semantics
    silently bumps tonight's game to tomorrow on the calendar. All
    user-facing date strings on courtvision pages MUST go through this
    helper. Returns "" on parse failure.
    """
    if not iso_ts or len(iso_ts) < 10:
        return ""
    try:
        try:
            from zoneinfo import ZoneInfo  # py3.9+
            _ET = ZoneInfo("America/New_York")
        except Exception:
            _ET = None
        norm = iso_ts.replace("Z", "+00:00")
        # ── CV_DK_FRACSEC_FIX (default OFF = byte-identical) ──
        # DraftKings start_times carry 7 fractional-second digits
        # ('...:00.0000000Z') which datetime.fromisoformat() rejects in
        # py3.10, so the parse fails and we fall back to the raw UTC prefix
        # (iso_ts[:10]) — mis-bucketing DK night games to the next ET day.
        # When ON, truncate fractional seconds to <=6 digits (microseconds);
        # harmless for 0/3/6-digit inputs. Mirrors the identical helper
        # api._courtvision_odds._et_date_of_start_time.
        import os as _os_fs
        if _os_fs.environ.get("CV_DK_FRACSEC_FIX") == "1":
            import re as _re_fs
            norm = _re_fs.sub(r"(\.\d{6})\d+", r"\1", norm)
        if "+" not in norm[10:] and norm.count("-") < 3:
            norm += "+00:00"
        dt = datetime.fromisoformat(norm).astimezone(timezone.utc)
        if _ET is not None:
            return dt.astimezone(_ET).strftime("%Y-%m-%d")
        # Fallback: ET is UTC-4 in DST (May-Nov), UTC-5 otherwise. We're
        # firmly in EDT for the May 2026 playoffs, so a static -4 offset
        # is correct here.
        from datetime import timedelta as _td
        return (dt + _td(hours=-4)).strftime("%Y-%m-%d")
    except Exception:
        return iso_ts[:10]


def _today_et() -> str:
    """Default date: today if it has lines or a slate, else the next date with
    live odds, else the most-recent slate.

    Pages like /odds, /tonight, /parlays render off this date. We DON'T want
    them showing yesterday's stale slate when today's lines CSVs already have
    fresh odds targeted at tomorrow's game (common during off-days between
    playoff games — odds are posted 2-3 days in advance).
    """
    global _TODAY_ET_CACHE
    _cached_ts, _cached_val = _TODAY_ET_CACHE
    if _cached_val and time.time() - _cached_ts < _TODAY_ET_TTL:
        return _cached_val

    # BUG 9 FIX: use Eastern time, not server-local, so a UTC host at
    # 00:00-05:00 UTC doesn't land on tomorrow's date. Mirrors the
    # ZoneInfo + EDT-fallback pattern used by _et_date_from_iso.
    try:
        from zoneinfo import ZoneInfo as _ZI  # noqa: PLC0415
        _et_tz = _ZI("America/New_York")
    except Exception:
        _et_tz = None
    if _et_tz is not None:
        today = datetime.now(timezone.utc).astimezone(_et_tz).strftime("%Y-%m-%d")
    else:
        from datetime import timedelta as _tdd  # noqa: PLC0415
        today = (datetime.now(timezone.utc) + _tdd(hours=-4)).strftime("%Y-%m-%d")
    # Highest priority: if any game has a fresh snapshot (< 4 hr old) we use
    # THAT snapshot's date so the home page lands on a live/recent game even
    # when slate/lines CSVs haven't caught up. This is the "any game any time"
    # contract — UI follows reality, not file existence.
    def _cache_and_return(val: str) -> str:
        global _TODAY_ET_CACHE
        _TODAY_ET_CACHE = (time.time(), val)
        return val

    try:
        import glob as _glob, json as _jrd  # noqa: PLC0415
        snap_files = _glob.glob(str(_ROOT / "data" / "live" / "*.json"))
        snap_files = [f for f in snap_files
                      if time.time() - __import__("os").path.getmtime(f) < 4 * 3600]
        if snap_files:
            snap_files.sort(key=lambda f: __import__("os").path.getmtime(f), reverse=True)
            try:
                _d = _jrd.loads(open(snap_files[0], encoding="utf-8").read())
                # Snapshot's game_id is NBA format (10-digit). The slate/lines
                # date for that game is whatever the snapshot's captured_at
                # date is in UTC.
                _ca = _d.get("captured_at") or ""
                if _ca and len(_ca) >= 10:
                    return _cache_and_return(_et_date_from_iso(_ca) or _ca[:10])
            except Exception:
                pass
    except Exception:
        pass
    # Today wins if it has either a model slate OR fresh lines.
    if _slate_csv_path(today):
        return _cache_and_return(today)
    if _lines_exist_for(today):
        return _cache_and_return(today)
    # No data for today — look for the NEXT date with fresh lines (typical
    # case: today is an off-day, but DK/FD/etc. have already posted lines for
    # tomorrow / day-after).
    nxt = _next_lines_date(today)
    if nxt:
        return _cache_and_return(nxt)
    # Final fallback: most-recent slate (yesterday's results page).
    return _cache_and_return(_latest_slate_date() or today)


def _lines_exist_for(date: str) -> bool:
    """True if at least one `data/lines/<date>_<book>.csv` exists with rows."""
    if not _LINES_DIR.exists():
        return False
    for p in _LINES_DIR.iterdir():
        if not p.is_file() or p.suffix != ".csv":
            continue
        if not p.stem.startswith(f"{date}_"):
            continue
        try:
            if p.stat().st_size > 100:  # > header line
                return True
        except OSError:
            continue
    return False


def _next_lines_date(after: str) -> Optional[str]:
    """Earliest date strictly after `after` that has populated lines CSVs."""
    if not _LINES_DIR.exists():
        return None
    dates: set[str] = set()
    for p in _LINES_DIR.iterdir():
        if not p.is_file() or p.suffix != ".csv":
            continue
        stem = p.stem
        if len(stem) < 10 or stem[10] != "_":
            continue
        d = stem[:10]
        if d > after:
            try:
                if p.stat().st_size > 100:
                    dates.add(d)
            except OSError:
                continue
    return min(dates) if dates else None


def _slate_csv_path(date: str) -> Optional[Path]:
    for name in (f"slate_{date}_post_inj_refresh.csv", f"slate_{date}.csv"):
        p = _PRED_DIR / name
        if p.exists():
            return p
    return None


def _lines_csv_path(date: str) -> Optional[Path]:
    p = _LINES_DIR / f"lines_{date}.csv"
    return p if p.exists() else None


def _latest_slate_date() -> Optional[str]:
    if not _PRED_DIR.exists():
        return None
    dates = set()
    for p in _PRED_DIR.glob("slate_*.csv"):
        parts = p.stem.split("_")
        if len(parts) >= 2 and len(parts[1]) == 10:
            dates.add(parts[1])
    return max(dates) if dates else None


def _filter_to_mainline(line_rows: list[dict]) -> list[dict]:
    """Collapse alt-line ladders to one mainline row per (player, stat).

    Sportsbooks publish many alt lines per prop. For LIVE-game props the line
    keeps moving — DK might be at 15.5 while stale Caesars/MGM/etc. are still
    showing yesterday's pregame 13.5. We want to surface the CURRENT mainline,
    not the stale-book-count winner.

    Picker order:
      1. Count books quoted within the last 10 minutes per line. Highest fresh
         count wins.
      2. Tie → total book count (legacy behavior).
      3. Tie → line closest to median of all lines for that (player, stat).
    """
    from collections import defaultdict
    from datetime import datetime, timezone
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in line_rows:
        key = (str(r.get("player", "")).lower(), r.get("stat", ""))
        groups[key].append(r)
    now = datetime.now(timezone.utc)
    FRESH_CUTOFF_SEC = 600  # 10 minutes

    def _fresh_count(row: dict) -> int:
        n = 0
        for b in (row.get("books") or []):
            ts = (b.get("captured_at") or "").strip()
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if (now - dt).total_seconds() <= FRESH_CUTOFF_SEC:
                    n += 1
            except (ValueError, TypeError):
                continue
        return n

    out: list[dict] = []
    for rows in groups.values():
        if len(rows) == 1:
            out.append(rows[0]); continue
        fresh_counts = [(r, _fresh_count(r)) for r in rows]
        max_fresh = max(fc for _, fc in fresh_counts)
        if max_fresh > 0:
            candidates = [r for r, fc in fresh_counts if fc == max_fresh]
        else:
            # No fresh books for any line — fall back to total book count
            max_books = max(len(r.get("books") or []) for r in rows)
            candidates = [r for r in rows if len(r.get("books") or []) == max_books]
        if len(candidates) == 1:
            out.append(candidates[0]); continue
        lines = sorted(float(r["line"]) for r in rows)
        median_line = lines[len(lines) // 2]
        out.append(min(candidates, key=lambda r: abs(float(r["line"]) - median_line)))
    return out


def _synthesize_bets_from_snapshots(
    line_rows: list[dict],
    stat_sigma: dict[str, float],
    live_dir: "Path",
    date: str,
    *,
    skip_keys: "set[tuple] | None" = None,
    synthesized_flag: bool = False,
    prefilled_live_maps: "dict[str, dict[tuple, float]] | None" = None,
    prefilled_mp_maps: "dict[str, dict[str, float]] | None" = None,
    prefilled_dir_index: "dict[str, 'Path'] | None" = None,
) -> list[dict]:
    """Build bet cards from live snapshots for line_rows that have no pregame slate row.

    Args:
        line_rows:           Raw rows from consolidate_for_slate / load_lines_csv.
        stat_sigma:          Per-stat sigma dict (possibly playoff-widened).
        live_dir:            Path to data/live/ directory.
        date:                YYYY-MM-DD slate date (used to filter snapshots by captured_at).
        skip_keys:           Set of (player_lower, stat) tuples already graded; skip these.
        synthesized_flag:    If True, tag every bet with ``_slate_synthesized: True``
                             (used when there is no pregame CSV at all).
        prefilled_live_maps: Optional pre-built {game_id: {(name, stat): q50}} from the
                             main live-regrade block in _build_slate. When supplied the
                             function skips calling project_from_snapshot for those games,
                             avoiding a duplicate expensive ML inference call.
        prefilled_mp_maps:   Optional pre-built {game_id: {name_lower: minutes_played}}
                             matching prefilled_live_maps.
        prefilled_dir_index: Optional pre-built {gid_prefix: Path} from the caller's
                             single iterdir() pass over live_dir. When supplied the
                             function skips its own iterdir(), eliminating ~150ms of
                             repeated stat() syscalls on the live/ directory.

    Returns list of bet dicts (may be empty).
    """
    import json as _lrj  # noqa: PLC0415
    try:
        from src.prediction.live_engine import project_from_snapshot as _lr_pfs  # noqa: PLC0415
        from api._courtvision_odds import resolve_game_id as _lr_rgid  # noqa: PLC0415
    except Exception:
        return []

    _skip = skip_keys or set()
    _snap_cache: dict[str, dict] = {}
    # Seed the projection cache with any pre-computed maps from the main regrade.
    _proj_cache: dict[str, dict[tuple, float]] = dict(prefilled_live_maps or {})
    _mp_cache: dict[str, dict[str, float]] = dict(prefilled_mp_maps or {})

    # For the synthesized (no-CSV) path we want snapshots from this calendar date.
    # For the late-roster path (skip_keys non-empty) we take any snapshot.
    def _snap_matches_date(snap: dict) -> bool:
        if not synthesized_flag:
            return True  # late-roster: accept any snapshot
        # ── CV_FIX_SNAP_ET_DATE (default OFF = byte-identical) ──
        # The raw captured_at[:10] UTC-prefix compare drops any snapshot
        # captured after 8:00 PM ET (>=00:00 UTC), which rolls to the next
        # calendar day and is silently excluded from the synthesized (no-CSV)
        # live path. When ON, convert captured_at to its ET date before
        # comparing, matching every other date path in this file.
        import os as _os_snap
        if _os_snap.environ.get("CV_FIX_SNAP_ET_DATE") == "1":
            return _et_date_from_iso(snap.get("captured_at") or "") == date
        ca = (snap.get("captured_at") or "")[:10]
        return ca == date

    # Build a map of all game_ids seen in line_rows to seed the snap search
    _line_gids = list({str(ln.get("game_id") or "") for ln in line_rows if ln.get("game_id")})

    # Use prefilled directory index if provided (avoids a second iterdir pass).
    # Fall back to the module-level cached index (5s TTL) when called standalone.
    if prefilled_dir_index is not None:
        _live_dir_index: dict[str, Path] = prefilled_dir_index
    else:
        # Use the cached index to avoid the 70ms iterdir() on 2965 files.
        _live_dir_index = _get_live_dir_index()

    # Also collect all snapshot game_ids found in live_dir for no-CSV path
    _all_snaps: dict[str, dict] = {}
    for _gid_pfx, _fp in _live_dir_index.items():
        try:
            _s = _lrj.loads(_fp.read_text(encoding="utf-8"))
            if _snap_matches_date(_s):
                _all_snaps[_gid_pfx] = _s
        except Exception:
            pass

    def _get_snap(gid: str) -> dict | None:
        if gid in _snap_cache:
            return _snap_cache[gid]
        alias = _lr_rgid(gid)
        canon = list(alias.get("canonical_ids", frozenset([gid]))) + [gid]
        for cgid in canon:
            snap_path = _live_dir_index.get(cgid)
            if snap_path is not None:
                try:
                    snap = _lrj.loads(snap_path.read_text(encoding="utf-8"))
                    if _snap_matches_date(snap):
                        _snap_cache[gid] = snap
                        return snap
                except Exception:
                    continue
        _snap_cache[gid] = {}
        return None

    def _find_snap_for_player(player_lower: str) -> "tuple[str, dict] | tuple[None, None]":
        for sgid, snap in _all_snaps.items():
            for lp in (snap.get("players") or []):
                if (lp.get("name") or "").lower() == player_lower:
                    return sgid, snap
        return None, None

    bets: list[dict] = []
    for ln in line_rows:
        if ln["stat"] not in _STATS:
            continue
        key = (ln["player"].lower(), ln["stat"])
        if key in _skip:
            continue

        gid = str(ln.get("game_id") or "")
        snap = _get_snap(gid) if gid else None
        if snap is None and not gid:
            found_gid, snap = _find_snap_for_player(ln["player"].lower())
            if found_gid:
                gid = found_gid

        q50: float | None = None
        team = ""
        opp = (ln.get("opp") or "").strip().upper()
        venue = (ln.get("venue") or "").strip().lower()
        player_id = ""

        if snap and snap.get("period"):
            if gid not in _proj_cache:
                lm: dict[tuple, float] = {}
                try:
                    for r in (_lr_pfs(snap) or []):
                        nm = (r.get("name") or "").lower()
                        st_p = (r.get("stat") or "").lower()
                        pf = r.get("projected_final")
                        if nm and st_p and pf is not None:
                            try:
                                lm[(nm, st_p)] = float(pf)
                            except (TypeError, ValueError):
                                pass
                except Exception:
                    pass
                _proj_cache[gid] = lm
                _mp_cache[gid] = _shrink_player_minutes_from_snapshot(snap)

            q50 = _proj_cache[gid].get(key)

            if q50 is None:
                for lp in (snap.get("players") or []):
                    nm2 = (lp.get("name") or "").lower()
                    if nm2 != ln["player"].lower():
                        continue
                    stat_val = lp.get(ln["stat"].lower(), 0) or 0
                    mp_raw2 = lp.get("min") or lp.get("minutes") or 0
                    if isinstance(mp_raw2, str) and ":" in mp_raw2:
                        try:
                            mm2, ss2 = mp_raw2.split(":", 1)
                            mp2 = int(mm2) + int(ss2) / 60.0
                        except Exception:
                            mp2 = 0.0
                    else:
                        try:
                            mp2 = float(mp_raw2 or 0)
                        except (TypeError, ValueError):
                            mp2 = 0.0
                    q50 = float(stat_val) * (36.0 / max(mp2, 1.0))
                    team = (lp.get("team") or "").strip().upper()
                    break
            else:
                for lp in (snap.get("players") or []):
                    if (lp.get("name") or "").lower() == ln["player"].lower():
                        team = (lp.get("team") or "").strip().upper()
                        break

            if not opp and snap:
                home = (snap.get("home_team") or "").upper()
                away = (snap.get("away_team") or "").upper()
                if team:
                    opp = away if team == home else home
                    venue = "home" if team == home else "away"

        if q50 is None:
            continue

        synth_slate: dict = {
            "date": date,
            "game_id": gid,
            "player_id": player_id or ln.get("player_id") or "",
            "player_name": ln["player"],
            "team": team or ln.get("team") or "",
            "opp": opp,
            "venue": venue,
            "stat": ln["stat"],
            "q50": q50,
            "lineup_status": "LATE_ADD",
            "lineup_class": None,
            "play_pct": None,
            "injury_status": "",
        }
        try:
            bet = grade_bet(synth_slate, ln, stat_sigma, _BANKROLL_DEFAULT)
            if synthesized_flag:
                bet["_slate_synthesized"] = True
            else:
                bet["_late_roster"] = True
            bets.append(bet)
        except Exception:
            pass

    return bets


_PREGAME_FALLBACK_CACHE: tuple[float, str, dict] | None = None
_PREGAME_FALLBACK_TTL = 600.0  # 10 min: recent slate doesn't change often


def _infer_teams_from_player_overlap(player_names: "list[str]") -> "tuple[str, str] | None":
    """Given a list of player names from a future-game scrape with no
    resolved game_id, look at the most recent slate CSV and vote on
    away/home team abbrs. Returns (away, home) if at least 5 players
    map to exactly 2 teams, else None.

    This is the lifeline for tomorrow's game when the scrapers only
    emit a KAMBI hex game_id that isn't in `games_lookup.json`. If the
    players are the same OKC + SAS rosters as last night, we infer the
    same OKC@SAS matchup. Speculative NBA Finals cards (NYK players +
    a not-yet-determined West opponent) yield no recent-slate overlap
    on the West side and get dropped — exactly what the user wants."""
    if not player_names:
        return None
    q50_map = _pregame_q50_map_from_recent_slate()
    if not q50_map:
        return None
    from collections import Counter
    votes: Counter = Counter()
    last_venue_by_team: dict[str, str] = {}
    for nm in player_names:
        key = (nm.lower(), "pts")
        ref = q50_map.get(key)
        if ref is None:
            # Try any stat — the pts row may be filtered out for some
            # players in some slates.
            for st in ("reb", "ast", "fg3m", "stl", "blk", "tov"):
                ref = q50_map.get((nm.lower(), st))
                if ref:
                    break
        if ref is None:
            continue
        team = (ref.get("team") or "").strip().upper()
        if team:
            votes[team] += 1
            v = (ref.get("venue") or "").strip().lower()
            if v:
                last_venue_by_team[team] = v
    if not votes:
        return None
    top = votes.most_common(2)
    if len(top) < 2 or top[0][1] < 5 or top[1][1] < 5:
        return None
    a, b = top[0][0], top[1][0]
    # Assign away/home from the most-recent slate's venue if available.
    if last_venue_by_team.get(a) == "home":
        return (b, a)
    if last_venue_by_team.get(a) == "away":
        return (a, b)
    # Default: alphabetical (stable display)
    return (min(a, b), max(a, b))


def _pregame_q50_map_from_recent_slate() -> dict[tuple[str, str], dict]:
    """Build a {(player_name_lower, stat): slate_row} map from the most
    recent `slate_YYYY-MM-DD.csv` file in data/predictions/.

    Used as the FALLBACK source of pregame q50 when no slate CSV exists
    for the requested date (typical for tomorrow + further-out games
    where `predict_slate.py` hasn't run yet). The opponent/venue/team
    columns from the most recent slate are kept as a best-effort proxy
    — for ongoing playoff series this is usually the same matchup, so
    q50 is close to opponent-adjusted; for fresh matchups it's a
    coarse estimate.

    Cached for 10 min on the latest-slate-date key so file I/O stays
    cheap under request load.
    """
    global _PREGAME_FALLBACK_CACHE
    latest = _latest_slate_date()
    if not latest:
        return {}
    now_ts = time.time()
    if (_PREGAME_FALLBACK_CACHE is not None
            and _PREGAME_FALLBACK_CACHE[1] == latest
            and now_ts - _PREGAME_FALLBACK_CACHE[0] < _PREGAME_FALLBACK_TTL):
        return _PREGAME_FALLBACK_CACHE[2]
    slate_path = _slate_csv_path(latest)
    if slate_path is None:
        return {}
    out: dict[tuple[str, str], dict] = {}
    try:
        from api._courtvision_data import load_slate_csv as _lsc  # noqa: PLC0415
        rows = _lsc(slate_path, _STATS)
    except Exception:
        return {}
    for (_pid, stat), row in rows.items():
        nm = (row.get("player_name") or "").strip().lower()
        if not nm:
            continue
        out[(nm, stat)] = row
    _PREGAME_FALLBACK_CACHE = (now_ts, latest, out)
    return out


def _synthesize_pregame_bets_from_recent_slate(
    line_rows: list[dict],
    stat_sigma: dict[str, float],
    date: str,
) -> list[dict]:
    """Synthesize bet cards for a future / past date by reusing the most
    recent slate CSV's per-player q50 predictions. Each line is graded
    against the matched recent q50; the bet keeps the line's own
    `game_id` (so per-game grouping on /results works) but inherits
    team/opp/venue from the most recent slate."""
    q50_map = _pregame_q50_map_from_recent_slate()
    if not q50_map:
        return []
    from api._courtvision_data import grade_bet as _gb  # noqa: PLC0415
    from api._courtvision_odds import resolve_game_id as _rgid  # noqa: PLC0415
    bets: list[dict] = []
    for ln in line_rows:
        stat = ln.get("stat") or ""
        if stat not in _STATS:
            continue
        key = ((ln.get("player") or "").lower(), stat)
        ref = q50_map.get(key)
        if ref is None:
            continue
        # team/opp/venue inherited from the recent slate can be STALE for a new
        # matchup (e.g. home/away flipped between series games). Re-derive them
        # from tonight's games_lookup using the line's game_id so the narrative
        # ("vs" vs "away at") and venue label match reality. The player's team
        # comes from the reference row; opponent + venue follow from the lookup.
        _team = ref.get("team") or ""
        _opp = ref.get("opp") or ""
        _venue = ref.get("venue") or "home"
        _alias = _rgid(ln.get("game_id") or ref.get("game_id") or "")
        _home = (_alias.get("home_abbr") or "").upper()
        _away = (_alias.get("away_abbr") or "").upper()
        if _home and _away:
            if _team.upper() == _home:
                _venue, _opp = "home", _away
            elif _team.upper() == _away:
                _venue, _opp = "away", _home
        synth_slate = {
            "date":  date,
            "player_id": ref.get("player_id") or "",
            "player_name": ref.get("player_name") or ln.get("player") or "",
            "team":  _team,
            "opp":   _opp,
            "venue": _venue,
            "game_id": ln.get("game_id") or ref.get("game_id") or "",
            "stat":  stat,
            "q50":   ref.get("q50"),
            "lineup_status": "PREGAME_FALLBACK",
            "lineup_class": None,
            "play_pct": None,
            "injury_status": ref.get("injury_status") or "",
        }
        try:
            bet = _gb(synth_slate, ln, stat_sigma, _BANKROLL_DEFAULT)
            bet["_slate_synthesized"] = True
            bet["_pregame_fallback_source_date"] = ref.get("date") or ""
            bets.append(bet)
        except Exception:
            continue
    return bets


# ── Calibration display gate ───────────────────────────────────────────────
# The prop model is currently miscalibrated: out-of-sample validation vs
# closing lines shows REBOUNDS is the only PROVEN edge (~70% hit / +30% ROI),
# while points/assists are coin-flips (~46-47%). A raw slate therefore surfaces
# dozens of inflated +EV bets — the over-fit signature, not real edges. Model
# recalibration is owned by a separate workstream; until it lands we gate the
# DISPLAY to the few most-credible edges so the page never presents fabricated
# value. We never silently truncate — the banner + n_bets_pre_gate field
# surface exactly how much was held back.
_PROVEN_STATS = {"reb"}        # the one OOS-validated market
_CREDIBLE_CAP = 6              # max edges shown until the model is recalibrated
_SANE_EV_CEILING = 25.0        # honest pregame prop EV rarely exceeds ~25%


def _apply_calibration_gate(envelope: dict) -> dict:
    """Down-select the EV-ranked slate to the VALIDATED best bets.

    Applies the iter61 selection stack from src/prediction/bet_thresholds.py
    (the same logic behind the +18.38% walk-forward result):
      * per-stat allowed directions  (e.g. BLK is UNDER-only, Iter-51)
      * per-stat raw-edge threshold   (e.g. PTS >= 1.0, Iter-39)
      * Iter-54 zero-EV line-bucket exclusions (is_line_excluded)
      * Iter-55/57 direction x line-bucket exclusions (is_direction_line_excluded)
    Only bets that survive all four are shown — these are the "best bets".
    Card format is unchanged (best book + price); no bankroll/Kelly changes.
    Ranks survivors by EV (capped at the sane ceiling). Mutates and returns
    ``envelope``.
    """
    bets = envelope.get("bets") or []
    n_pre = len(bets)
    if n_pre == 0:
        envelope["calibration"] = {
            "warning": False, "n_bets_pre_gate": 0, "n_shown": 0,
        }
        return envelope

    # Playoff window detected from the slate DATE (robust to a stale games_lookup
    # / int-stripped or raw-book game_ids on the bet). Only consumed by the
    # CV_PLAYOFF_GUARD_FAILCLOSED branch in policy_allows_context (default OFF =
    # byte-identical); see SYNTH_PATH_PLAYOFF_GUARD.md.
    _playoff_window = _is_playoff_date(str(envelope.get("date") or ""))

    try:
        from src.prediction.bet_thresholds import (  # noqa: PLC0415
            allowed_directions_for, edge_threshold_for,
            is_line_excluded, is_direction_line_excluded, kelly_b_hit_rate_for,
        )
        _have_filters = True
    except Exception as _bt_exc:  # pragma: no cover
        __import__("logging").getLogger(__name__).warning(
            "bet_thresholds import failed (%s) — slate shown unfiltered", _bt_exc)
        _have_filters = False
    try:
        from src.prediction.edge_calibration import calibrate_p_win  # noqa: PLC0415
        _have_calib = True
    except Exception as _ec_exc:  # pragma: no cover
        __import__("logging").getLogger(__name__).warning(
            "edge_calibration import failed (%s) — EV shown uncalibrated", _ec_exc)
        _have_calib = False

    # ── CV_BET_POLICY (default OFF = iter57 = byte-identical) ──────────────────
    # Plumb the VALIDATED bet-policy selector (src/prediction/bet_policy.py) onto the
    # webpage bet surface. The Iter-57 selection stack above (bet_thresholds.py) is the
    # in-sample-tuned +18.38% market-follow artifact; on a clean temporal held-out split
    # it LOSES (-13.54%, 81% PTS) — see docs/VS_VEGAS_ASSESSMENT.md §1/§7 and bet_policy.py.
    # The robust positive book is REB+AST (drop PTS), AST left raw. This layer can only
    # TIGHTEN (drop a disallowed stat / over-cap line / raise the per-stat min-edge);
    # under the default iter57 policy every call is a strict pass-through, so OFF is
    # byte-identical to the shipped page. AST is NOT recalibrated here (raw is preserved).
    try:
        from src.prediction.bet_policy import (  # noqa: PLC0415
            is_iter57_default as _bp_default,
            policy_allows_stat as _bp_allows,
            policy_drops_line as _bp_drops_line,
            policy_min_edge as _bp_min_edge,
            policy_allows_context as _bp_allows_ctx,
        )
        _bet_policy_active = not _bp_default()
        _bp_ctx_available = True
    except Exception:
        _bet_policy_active = False
        _bp_ctx_available = False

    kept = []
    for b in bets:
        stat = str(b.get("prop_stat", "")).lower()
        side = str(b.get("side", "OVER")).lower()          # 'over' / 'under'
        try:
            line = float(b.get("line"))
        except (TypeError, ValueError):
            line = None
        edge_units = b.get("edge_units")
        if edge_units is None and b.get("q50") is not None and line is not None:
            try:
                edge_units = float(b["q50"]) - line
            except (TypeError, ValueError):
                edge_units = None
        try:
            edge_mag = abs(float(edge_units)) if edge_units is not None else 0.0
        except (TypeError, ValueError):
            edge_mag = 0.0

        if _have_filters:
            if side not in allowed_directions_for(stat):
                continue
            if edge_mag < edge_threshold_for(stat):
                continue
            if line is not None and is_line_excluded(stat, line):
                continue
            if line is not None and is_direction_line_excluded(stat, side, line):
                continue

        # Validated bet-policy gate — strict no-op under the default iter57 policy.
        if _bet_policy_active:
            if not _bp_allows(stat):
                continue
            if line is not None and _bp_drops_line(stat, line):
                continue
            if edge_mag < _bp_min_edge(stat):
                continue

        # Regime guard (playoff-pregame + always-on playoff-AST) — applies on EVERY
        # policy, NOT just the active-bet-policy branch. Mirrors bet_selector.py
        # (the real selection path) where policy_allows_context is unconditional.
        # Previously this was nested inside `if _bet_policy_active:`, so under the
        # default iter57 policy (_bet_policy_active=False) it never fired on
        # /api/slate — the flipped CV_PLAYOFF_PREGAME_GUARD and the always-on
        # playoff-AST guard were both INERT here (BUG-6). policy_allows_context
        # self-gates: returns True for every regular-season game and (for non-AST)
        # whenever CV_PLAYOFF_PREGAME_GUARD is OFF, so reg-season output is
        # byte-identical; escapes via CV_ALLOW_PLAYOFF_PREGAME / CV_ALLOW_PLAYOFF_AST.
        if _bp_ctx_available and not _bp_allows_ctx(
                stat, b.get("game_id"), playoff_window=_playoff_window):
            continue

        # Honest probability: replace the naive Normal-CDF model_prob with the
        # isotonic-calibrated win prob (edge_calibration, capped [0.50,0.90]),
        # then recompute EV at the best price. Also recompute Kelly so
        # kelly_stake_dollars/kelly_pct are sized off cal_p, not the stale
        # naive prob (bug 6 fix).
        # P1-3 FIX — per-player displayed probability.
        # grade_bet() already set b["model_prob"] to THIS player's own posterior
        # P(stat ≷ line) from the player's q50+sigma (Normal-CDF). The old gate
        # OVERWROTE that with calibrate_p_win(stat, edge_mag, ...), a value keyed
        # only on (stat, edge magnitude) — so unrelated players collapsed to one
        # number (Brunson PTS U27.5, Shamet PTS U7.5, Kornet PTS O1.5 all 0.5897).
        # We now KEEP the per-player posterior as the DISPLAYED model_prob (sanity-
        # capped) and store the isotonic value separately as model_prob_calibrated.
        # EV / Kelly / grade stay on the CALIBRATED prob (conservative + honest:
        # the per-player Normal-CDF is sigma-tight/overconfident, so we never price
        # a betting EDGE off it — but the SHOWN probability traces to the player).
        _cal_p = None
        if _have_calib and _have_filters:
            try:
                _cal_p = calibrate_p_win(
                    stat, edge_mag, edge_threshold_for(stat), kelly_b_hit_rate_for(stat))
                price = int(b.get("best_price") or -110)
                payout = (float(price) if price >= 100 else (10000.0 / abs(price)) if price <= -100 else 100.0)
                # Per-player posterior — displayed (capped to a sane prop range).
                try:
                    _pp = max(0.02, min(0.98, float(b.get("model_prob"))))
                except (TypeError, ValueError):
                    _pp = _cal_p
                b["model_prob_raw"] = b.get("model_prob")
                b["model_prob"] = round(_pp, 4)                # traces to the player
                b["model_prob_calibrated"] = round(_cal_p, 4)  # conservative, for EV/grade
                b["ev_pct"] = round(_cal_p * payout - (1.0 - _cal_p) * 100.0, 2)
                b["calibrated"] = True
                # Recompute Kelly from calibrated prob (mirrors _reprice_slate_to_books)
                from api._courtvision_data import _BETTING  # noqa: PLC0415
                _ev_k = _BETTING.evaluate(_cal_p, price, bankroll=_BANKROLL_DEFAULT)
                b["kelly_stake_dollars"] = round(float(_ev_k.get("kelly_size") or 0.0), 2)
                b["kelly_pct"] = round((b["kelly_stake_dollars"] / _BANKROLL_DEFAULT) * 100.0, 3)
            except Exception:
                pass

        # Honest letter grade off the CALIBRATED prob + calibrated EV (never the
        # per-player display prob, which is sigma-tight). On playoff dates / stale
        # lines this caps at "C" + a paper note; A is only reachable for the
        # validated reg-season book. Lazy import + try/except so a missing module
        # never breaks the slate (bets just go ungraded).
        try:
            from src.prediction.bet_grades import letter_grade  # noqa: PLC0415
            _grade_prob = b.get("model_prob_calibrated")
            if _grade_prob is None:
                _grade_prob = b.get("model_prob")
            b["grade"], b["grade_note"] = letter_grade(
                str(b.get("prop_stat", "")),
                float(_grade_prob or 0.0),
                float(b.get("ev_pct") or 0.0),
                playoff_window=_playoff_window,
                stale_lines=(b.get("freshest_book_age_min", 0) or 0) > 60,
            ).values()
        except Exception:
            pass

        ev = b.get("ev_pct")
        b["proven_market"] = True       # passed the validated selection stack
        b["speculative"] = False
        b["ev_suspect"] = ev is not None and ev > _SANE_EV_CEILING
        kept.append(b)

    def _rank_key(b):
        return -min(b.get("ev_pct") or 0.0, _SANE_EV_CEILING)

    kept.sort(key=_rank_key)
    evs = [b["ev_pct"] for b in kept if b.get("ev_pct") is not None]
    envelope["bets"] = kept
    # Fixed book universe (every book quoting any kept bet) — chips are built
    # from this so they don't collapse to one when re-priced to a single book.
    envelope["all_books_universe"] = sorted(
        {x.get("book") for b in kept for x in (b.get("all_books") or []) if x.get("book")}
    )
    envelope["summary"] = {
        "n_bets": len(kept),
        "avg_ev_pct": round(sum(evs) / len(evs), 2) if evs else 0.0,
        "n_over": sum(1 for b in kept if b["side"] == "OVER"),
        "n_under": sum(1 for b in kept if b["side"] == "UNDER"),
    }
    envelope["calibration"] = {
        "warning": False,
        "n_bets_pre_gate": n_pre,
        "n_shown": len(kept),
        "filtered": _have_filters,
        "note": (
            f"Best bets: {len(kept)} of {n_pre} raw edges survived the validated "
            "iter-57 selection stack (per-stat direction + edge threshold + "
            "zero-EV line-bucket pruning)." if _have_filters else
            "WARNING: validated filter unavailable — showing unfiltered edges."
        ),
    }
    return envelope


def _reprice_slate_to_books(envelope: dict, book_keys) -> dict:
    """Return a COPY of the slate re-priced to ONLY the bettor's book(s).

    For each bet: restrict the per-book ladder to ``book_keys``, take the best
    price for the model's side among them, recompute EV / market-implied prob /
    Kelly, and DROP bets none of those books post. Re-sorts rebounds-first then
    by EV. This is the casual-bettor flow: pick the book(s) you have and the
    board instantly reshuffles to that book's best plays (multiple books → best
    price across them, i.e. line-shopping). Empty ``book_keys`` → unchanged
    (cross-book best, the default).
    """
    keys = [str(k).strip().lower() for k in (book_keys or []) if str(k).strip()]
    if not keys:
        return envelope
    from api._courtvision_data import _BETTING  # the same evaluator grade_bet uses

    def _match(bookname: str) -> bool:
        bn = (bookname or "").strip().lower()
        return bool(bn) and any(k in bn or bn in k for k in keys)

    out_bets: list[dict] = []
    for b0 in envelope.get("bets") or []:
        full = b0.get("_books_full") or []
        side = b0.get("side", "OVER")
        side_key = "over_odds" if side == "OVER" else "under_odds"
        sel = [x for x in full if _match(x.get("book")) and x.get(side_key) is not None]
        if not sel:
            continue  # none of the bettor's books post this prop → hide it
        b = dict(b0)
        best = max(sel, key=lambda x: int(x[side_key]))
        odds = int(best[side_key])
        # EV uses the CALIBRATED prob (conservative); the per-player model_prob is
        # display-only (sigma-tight). Falls back to model_prob when no calibration.
        mp = float(b.get("model_prob_calibrated") or b.get("model_prob") or 0.0)
        payout = (float(odds) if odds >= 100 else (10000.0 / abs(odds)) if odds <= -100 else 100.0)
        ev_pct = mp * payout - (1.0 - mp) * 100.0
        market_prob = (100.0 / (odds + 100.0)) if odds > 0 else (abs(odds) / (abs(odds) + 100.0))
        try:
            ev = _BETTING.evaluate(mp, odds, bankroll=_BANKROLL_DEFAULT)
            kelly_dollars = float(ev.get("kelly_size") or 0.0)
            kelly_pct = (kelly_dollars / _BANKROLL_DEFAULT) * 100.0 if _BANKROLL_DEFAULT else 0.0
        except Exception:
            kelly_dollars, kelly_pct = 0.0, 0.0
        b["best_book"] = best["book"]
        b["best_price"] = odds
        b["ev_pct"] = round(ev_pct, 2)
        b["market_prob"] = round(market_prob, 4)
        b["kelly_pct"] = round(kelly_pct, 3)
        b["kelly_stake_dollars"] = round(kelly_dollars, 2)
        b["all_books"] = sorted(
            [{"book": x["book"], "price": int(x[side_key])} for x in sel],
            key=lambda r: -r["price"])
        out_bets.append(b)

    def _rank_key(b):
        ev = min(b.get("ev_pct") or 0.0, _SANE_EV_CEILING)
        return (not b.get("proven_market"), -ev)
    out_bets.sort(key=_rank_key)

    env = dict(envelope)
    env["bets"] = out_bets
    evs = [b["ev_pct"] for b in out_bets if b.get("ev_pct") is not None]
    env["summary"] = {
        "n_bets": len(out_bets),
        "avg_ev_pct": round(sum(evs) / len(evs), 2) if evs else 0.0,
        "n_over": sum(1 for b in out_bets if b["side"] == "OVER"),
        "n_under": sum(1 for b in out_bets if b["side"] == "UNDER"),
    }
    env["repriced_books"] = keys
    return env


def _attach_book_quotes(envelope: dict, date: str) -> dict:
    """Attach ``bet.book_quotes`` to every bet in *envelope* (DATA CONTRACT).

    book_quotes = {"DraftKings": {"line", "over", "under"}, "FanDuel": {...},
    "Pinnacle": {...}} — the FRESHEST quote from EACH book for that
    (player, stat), at THAT book's OWN line (lines may differ between books).
    This is what makes the DK/FD/Pin book picker work even when the consensus
    mainline differs from a given book's line — fixing "DK odds not working"
    (DK was only surviving the per-line mainline join on ~2/12 bets).

    Joins on (de-accented-lower player_name, lower stat). Books absent for a
    prop are omitted. Mutates the bets in place and returns *envelope*.
    Graceful: any failure leaves the slate untouched (bets just lack the new
    key, back-compatible with best_book/all_books which are preserved).
    """
    try:
        from api._courtvision_odds import (  # noqa: PLC0415
            book_quotes_by_player_stat, _strip_accents as _sa,
        )
        bq_map = book_quotes_by_player_stat(date)
    except Exception as exc:  # pragma: no cover
        __import__("logging").getLogger(__name__).warning(
            "book_quotes attach failed: %s", exc)
        return envelope
    for b in envelope.get("bets") or []:
        try:
            key = (_sa(b.get("player_name") or "").lower(),
                   (b.get("prop_stat") or "").lower())
        except Exception:
            continue
        quotes = bq_map.get(key)
        if quotes:
            # Copy so a later in-place mutation never bleeds across the cache.
            b["book_quotes"] = {bk: dict(v) for bk, v in quotes.items()}
    return envelope


def _apply_live_regrade_inplace(bets: list, date: str, stat_sigma: dict) -> None:
    """In-game live regrade for the synthesized / pregame-fallback slate path.

    The normal (live-CSV) slate path runs a live q50 regrade + in-play line
    re-anchor (see _build_slate below, ``live regrade`` block). The synthesized
    fallback path used during a live game RETURNED before that block, so its
    cards stayed frozen on the pregame q50/EV. This mirrors that block on the
    synth bets IN PLACE so the cards move with the live game. Self-contained;
    no-op when no live snapshot exists for the game; every failure leaves the
    pregame bet untouched (never raises)."""
    import os as _os, json as _json  # noqa: PLC0415
    try:
        from src.prediction.live_engine import project_from_snapshot as _pfs  # noqa: PLC0415
        from api._courtvision_odds import resolve_game_id as _rgi  # noqa: PLC0415
    except Exception:
        return
    live_maps: dict = {}
    mp_maps: dict = {}
    try:
        _ld_index = _get_live_dir_index()
        _all_gids: set = set()
        for _b in bets:
            _g = str(_b.get("game_id") or "")
            if _g:
                _all_gids.add(_g)
        for _gid in _all_gids:
            _alias = _rgi(_gid)
            _canon = list(_alias.get("canonical_ids", frozenset([_gid]))) + [_gid]
            _snap = None
            for _cgid in _canon:
                _sp = _ld_index.get(_cgid)
                if _sp is not None:
                    try:
                        _snap = _json.loads(_sp.read_text(encoding="utf-8"))
                        break
                    except Exception:
                        continue
            if not _snap or not _snap.get("period"):
                live_maps[_gid] = {}
                continue
            _lm: dict = {}
            try:
                for _r in (_pfs(_snap) or []):
                    _nm = (_r.get("name") or "").lower()
                    _st = (_r.get("stat") or "").lower()
                    _pf = _r.get("projected_final")
                    if _nm and _st and _pf is not None:
                        try:
                            _lm[(_nm, _st)] = float(_pf)
                        except (TypeError, ValueError):
                            continue
            except Exception:
                pass
            live_maps[_gid] = _lm
            try:
                mp_maps[_gid] = _shrink_player_minutes_from_snapshot(_snap)
            except Exception:
                mp_maps[_gid] = {}
    except Exception:
        return
    _reanchor = (_os.environ.get("CV_SLATE_INPLAY_REANCHOR", "").strip().lower()
                 not in ("", "0", "false", "no", "off"))
    _lm_hist: list = []
    if _reanchor:
        try:
            _lm_hist = _load_inplay_line_history(date, frozenset())
        except Exception:
            _lm_hist = []
    for _b in bets:
        try:
            _gid = str(_b.get("game_id") or "")
            _lm = live_maps.get(_gid) or {}
            if not _lm:
                continue
            _key = ((_b.get("player_name") or "").lower(),
                    (_b.get("prop_stat") or "").lower())
            _live_q50 = _lm.get(_key)
            if _live_q50 is None:
                continue
            _mp = (mp_maps.get(_gid) or {}).get(_key[0], 0.0)
            _w = _live_shrink_weight(_mp)
            try:
                _pre = float(_b.get("q50") or _live_q50)
            except (TypeError, ValueError):
                _pre = float(_live_q50)
            _shrunk = _w * float(_live_q50) + (1.0 - _w) * _pre
            if _reanchor and _lm_hist:
                try:
                    _reanchor_to_live_inplay(_b, _lm_hist, _shrunk)
                except Exception:
                    pass
            try:
                _regrade_bet_with_live_q50(_b, _shrunk, stat_sigma, _BANKROLL_DEFAULT)
                _b["q50"] = round(float(_shrunk), 2)
                _b["live_regraded"] = True
            except Exception:
                continue
        except Exception:
            continue


def _build_slate(date: str) -> dict:
    """Cached slate builder. Returns the JSON envelope dict."""
    cache_key = ("slate", date)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC:
        return entry[1]

    slate_path = _slate_csv_path(date)
    if slate_path is None:
        # ── No pregame CSV: attempt live-only synthesis ────────────
        # If sportsbook lines exist for this date, synthesize bet cards
        # entirely from live snapshots so the home page isn't empty.
        try:
            from api._courtvision_odds import consolidate_for_slate as _cfs  # noqa: PLC0415
            _synth_line_rows = _filter_to_mainline(_cfs(date))
        except Exception:
            _synth_line_rows = []

        if not _synth_line_rows:
            envelope = {"date": date, "generated_at": datetime.utcnow().isoformat() + "Z",
                "bankroll_default_dollars": _BANKROLL_DEFAULT, "stale_data": True,
                "has_lines": False, "latest_available": _latest_slate_date(),
                "summary": {"n_bets": 0, "avg_ev_pct": 0.0, "n_over": 0, "n_under": 0},
                "bets": []}
            _CACHE[cache_key] = (time.time(), envelope)
            return envelope

        # Lines found — try recent-slate fallback FIRST (works pregame for
        # future dates where no live snapshots exist yet); fall back to
        # live-snapshot synthesis for live-in-progress games.
        _sigma_synth = _stat_sigma_for_date(date)
        _log_synth = __import__("logging").getLogger(__name__)
        bets: list[dict] = []
        try:
            bets = _synthesize_pregame_bets_from_recent_slate(
                _synth_line_rows, _sigma_synth, date,
            )
        except Exception as _exc_pg:
            _log_synth.warning("pregame-fallback synthesis failed: %s", _exc_pg)
            bets = []
        if not bets:
            _live_dir_synth = _ROOT / "data" / "live"
            try:
                bets = _synthesize_bets_from_snapshots(
                    _synth_line_rows, _sigma_synth, _live_dir_synth, date,
                    synthesized_flag=True,
                )
            except Exception as _synth_exc:
                _log_synth.warning("live-only slate synthesis failed: %s", _synth_exc)
                bets = []

        # SYNTH_PATH_PLAYOFF_GUARD: synth bets carry RAW BOOK game_ids (e.g.
        # 34249161), so the always-on playoff-AST guard in policy_allows_context
        # (keyed on a canonical 004… NBA id) is INERT on the synth path. Resolve
        # each raw book gid → its canonical 004… id (via games_lookup) and pin it
        # on the bet so the per-stat playoff guard fires. Defensive: no-op when the
        # id is unresolved or has no 004… canonical (regular season unaffected).
        try:
            from api._courtvision_odds import resolve_game_id as _rgid_synth  # noqa: PLC0415
            _canon_cache_synth: dict[str, str] = {}
            for _b in bets:
                _bgid = str(_b.get("game_id") or "")
                if not _bgid or _bgid.startswith("004"):
                    continue
                if _bgid not in _canon_cache_synth:
                    _canon004 = ""
                    try:
                        _alias_s = _rgid_synth(_bgid) or {}
                        for _cid in _alias_s.get("canonical_ids", ()):  # frozenset
                            if str(_cid).startswith("004"):
                                _canon004 = str(_cid)
                                break
                    except Exception:
                        _canon004 = ""
                    _canon_cache_synth[_bgid] = _canon004
                _resolved = _canon_cache_synth[_bgid]
                if _resolved:
                    _b["game_id"] = _resolved
        except Exception as _gid_exc:
            _log_synth.warning("synth playoff-guard gid resolve failed: %s", _gid_exc)

        # BUG-DRT-1 (CV_SYNTH_GATE_BEFORE_TRUNCATE): the synth slate path truncated
        # bets[:_TOP_N] by RAW (un-calibrated) EV BEFORE the calibration gate — the
        # inverse of the main-path BUG 7 FIX (~L1881). The gate recalibrates EV and
        # prunes whole line-buckets, so a #51-57 raw-EV candidate can outrank a
        # gate-pruned top-50 but is already gone (06-05 synth slate: 2 gate-surviving
        # +EV bets silently dropped, incl. Brunson PTS OVER 24.5 +3.45%). When ON,
        # gate the FULL pre-truncation list first, then sort by calibrated EV with an
        # edge-magnitude tie-break, then truncate. Default OFF = byte-identical legacy.
        _synth_gate_done = False
        if (os.environ.get("CV_SYNTH_GATE_BEFORE_TRUNCATE", "").strip().lower()
                not in ("", "0", "false", "no", "off")):
            # Pass the slate DATE so _playoff_window is set: the synth path keeps RAW
            # BOOK game_ids (un-classifiable as playoff by id alone), and this gate is
            # the FINAL gate (no re-gate runs below when _synth_gate_done=True), so the
            # CV_PLAYOFF_GUARD_FAILCLOSED branch must see the playoff window HERE or a
            # Finals book-id pregame bet leaks. Byte-identical in the regular season
            # (_is_playoff_date(date)=False). See SYNTH_PATH_PLAYOFF_GUARD.md.
            _stub_env_synth = _apply_calibration_gate({"date": date, "bets": bets})
            bets = _stub_env_synth.get("bets") or []
            bets.sort(key=lambda b: (
                b["ev_pct"] is None,
                -(min(b.get("ev_pct") or 0.0, _SANE_EV_CEILING)),
                -abs(b.get("edge_units") or b.get("edge") or 0.0),
            ))
            bets = bets[:_TOP_N]
            _synth_gate_done = True
        else:
            bets.sort(key=lambda b: (b["ev_pct"] is None, -(b["ev_pct"] or 0.0)))
            bets = bets[:_TOP_N]
        try: from api._courtvision_form import attach_form; attach_form(bets)
        except Exception as exc: _log_synth.warning("attach_form (synth): %s", exc)

        # In-game live overlay: regrade the synth / pregame-fallback cards on the
        # live snapshot so the slate moves WITH the game (mirrors the normal
        # live-CSV path, which this synth branch returns before reaching).
        # No-op when no live snapshot exists for the game; never raises.
        try:
            _apply_live_regrade_inplace(bets, date, _sigma_synth)
        except Exception as _exc_lr:
            _log_synth.warning("synth live-regrade failed: %s", _exc_lr)

        evs = [b["ev_pct"] for b in bets if b.get("ev_pct") is not None]
        envelope = {
            "date": date,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "bankroll_default_dollars": _BANKROLL_DEFAULT,
            "stale_data": True,
            "slate_synthesized": True,
            "has_lines": True,
            "latest_available": _latest_slate_date(),
            "summary": {
                "n_bets": len(bets),
                "avg_ev_pct": round(sum(evs) / len(evs), 2) if evs else 0.0,
                "n_over": sum(1 for b in bets if b["side"] == "OVER"),
                "n_under": sum(1 for b in bets if b["side"] == "UNDER"),
            },
            "bets": bets,
        }
        if _synth_gate_done:
            # Gate already ran on the FULL list above — copy its calibration
            # metadata instead of re-gating the truncated list (no double-gate).
            envelope["all_books_universe"] = _stub_env_synth.get("all_books_universe", [])
            envelope["calibration"] = _stub_env_synth.get("calibration", {})
        else:
            envelope = _apply_calibration_gate(envelope)
        envelope = _attach_book_quotes(envelope, date)
        _CACHE[cache_key] = (time.time(), envelope)
        return envelope

    slate_rows = load_slate_csv(slate_path, _STATS)
    # Lines source order: live consolidated (multi-book scrapers) > manual CSV.
    from api._courtvision_odds import consolidate_for_slate
    line_rows = consolidate_for_slate(date)
    lines_path = _lines_csv_path(date)
    if not line_rows and lines_path is not None:
        line_rows = load_lines_csv(lines_path)
    # Filter to mainline per (player, stat) — alt-line ladders (e.g. SGA pts at
    # 19.5/24.5/40.5/43.5 alongside the real 29.5 line) otherwise inflate EV
    # because the model trivially says "99% under 43.5". Mainline = the line
    # offered by the most books; ties broken by closeness to median line.
    line_rows = _filter_to_mainline(line_rows)
    has_lines = bool(line_rows)
    if has_lines:
        # Use de-accented-lower as the join key so accented cache names
        # ("Nikola Jokić" from predictions_cache) match ASCII book names
        # ("Nikola Jokic" from sportsbook CSVs). Display names are untouched.
        from api._courtvision_odds import _strip_accents as _sa  # noqa: PLC0415
        ps_idx = {
            (_sa(r["player_name"]).lower(), r["stat"]): r
            for r in slate_rows.values()
        }
        stat_sigma_for_slate = _stat_sigma_for_date(date)
        bets = [grade_bet(ps_idx[(_sa(ln["player"]).lower(), ln["stat"])], ln,
                          stat_sigma_for_slate, _BANKROLL_DEFAULT)
                for ln in line_rows
                if ln["stat"] in _STATS
                and (_sa(ln["player"]).lower(), ln["stat"]) in ps_idx]

        # ── Build live projection maps once per game ─────────────────
        # project_from_snapshot() is the expensive ML call (~0.4s/game).
        # We build the (name, stat) → q50 map HERE, once per unique game_id,
        # then reuse it for BOTH late-roster synthesis AND the live regrade
        # below. This avoids calling project_from_snapshot twice for each game
        # (previous bug: _synthesize_bets_from_snapshots built its own map,
        # then the live-regrade loop built it again independently).
        live_maps: dict[str, dict[tuple, float]] = {}
        mp_maps: dict[str, dict[str, float]] = {}
        # BUG-3 (CV_INGAME_OUT_BET_CAP): the operator manual OUT list. When the
        # flag is OFF or the file is empty/absent this is an empty set and every
        # branch below short-circuits — strict byte-identical no-op. When ON with
        # a name present we capture the player's live `current` so the regrade
        # can cap his blended projection at current (he LEFT the game), mirroring
        # the box-card cap and removing the phantom OVER edge.
        from api._courtvision_out_cap import (  # noqa: PLC0415
            cap_blended_value as _out_cap_blended,
            load_out_set as _out_load_set,
        )
        _out_set = _out_load_set(date)
        cur_maps: dict[str, dict[tuple, float]] = {}
        try:
            from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
            from api._courtvision_odds import resolve_game_id  # noqa: PLC0415
            import json as _sj  # noqa: PLC0415
            # Use the 5s-TTL cached directory index — avoids re-scanning 2965+ files
            # on every cache miss.  The index is rebuilt at most every 5s which is
            # well within the 10s snapshot-write cadence.
            _ld_index = _get_live_dir_index()
            # Collect unique game_ids from all current bets + line_rows so late-
            # roster players (not yet in bets) also get their game snaps loaded.
            _all_gids: set[str] = set()
            for b in bets:
                g = str(b.get("game_id") or "")
                if g:
                    _all_gids.add(g)
            for ln in line_rows:
                g = str(ln.get("game_id") or "")
                if g:
                    _all_gids.add(g)
            for gid in _all_gids:
                alias = resolve_game_id(gid)
                canon = list(alias.get("canonical_ids", frozenset([gid]))) + [gid]
                snap = None
                for cgid in canon:
                    snap_path = _ld_index.get(cgid)
                    if snap_path is not None:
                        try:
                            snap = _sj.loads(snap_path.read_text(encoding="utf-8"))
                            break
                        except Exception:
                            continue
                if not snap or not snap.get("period"):
                    live_maps[gid] = {}
                    continue
                lm: dict[tuple, float] = {}
                cm: dict[tuple, float] = {}
                try:
                    for r in (project_from_snapshot(snap) or []):
                        nm = (r.get("name") or "").lower()
                        st_p = (r.get("stat") or "").lower()
                        pf = r.get("projected_final")
                        if nm and st_p and pf is not None:
                            try:
                                lm[(nm, st_p)] = float(pf)
                            except (TypeError, ValueError):
                                continue
                        # BUG-3: capture current box value for OUT-cap, only when
                        # the out-set is active (empty set -> this never runs ->
                        # cur_maps stays empty -> byte-identical when flag OFF).
                        if _out_set and nm and st_p:
                            cv_r = r.get("current")
                            if cv_r is not None:
                                try:
                                    cm[(nm, st_p)] = float(cv_r)
                                except (TypeError, ValueError):
                                    pass
                except Exception:
                    pass
                live_maps[gid] = lm
                if _out_set:
                    cur_maps[gid] = cm
                mp_maps[gid] = _shrink_player_minutes_from_snapshot(snap)
        except Exception as _exc_lm:
            __import__("logging").getLogger(__name__).warning(
                "live map pre-build failed: %s", _exc_lm)

        # ── Late-roster synthesis ──────────────────────────────────
        # Players absent from the pregame CSV (two-way call-ups, late
        # activations) have line_rows but no ps_idx entry. Synthesize
        # a minimal slate_row from the live snapshot so they get bet
        # cards on /tonight.  Pass the already-built live_maps so
        # project_from_snapshot is NOT called again inside.
        try:
            _late_bets = _synthesize_bets_from_snapshots(
                line_rows, stat_sigma_for_slate, _ROOT / "data" / "live", date,
                skip_keys=set(ps_idx.keys()),
                synthesized_flag=False,
                prefilled_live_maps=live_maps,
                prefilled_mp_maps=mp_maps,
                prefilled_dir_index=_ld_index,
            )
            bets.extend(_late_bets)
        except Exception as _lr_exc:
            __import__("logging").getLogger(__name__).warning(
                "late-roster synthesis failed: %s", _lr_exc)

        # Honest-EV gate: cap model_prob at 0.85 (no real single-prop model is
        # more than 85% sure; anything higher reflects sigma understatement or
        # alt-line residual that slipped past _filter_to_mainline). Recompute
        # EV with the capped probability so downstream sizing is realistic.
        for b in bets:
            mp = b.get("model_prob")
            if mp is not None and mp > 0.85:
                price = int(b.get("best_price") or -110)
                payout = (float(price) if price >= 100 else (10000.0 / abs(price)) if price <= -100 else 100.0)
                b["model_prob"] = 0.85
                b["ev_pct"] = round(0.85 * payout - 0.15 * 100.0, 2)
                b["ev_capped"] = True

        # ── live regrade ───────────────────────────────────────────
        # Reuse the live_maps / mp_maps already built above (project_from_snapshot
        # was already called once per game; do NOT call it again here).
        #
        # CV_SLATE_INPLAY_REANCHOR (default OFF = byte-identical): when ON, also
        # re-anchor each live-regraded bet's LINE + per-book price ladder to the
        # CURRENT in-play market (data/lines/<date>_*inplay*.csv) BEFORE the
        # regrade, so during a game the slate cards move with BOTH the live
        # prediction (live_q50, always on) AND the live line (this flag). The
        # /tonight + /api/box_score live_bets path already does this inline;
        # this surfaces it on the flat /api/slate too. Graceful: any failure
        # leaves the pregame line in place (still regraded on the live q50).
        _slate_inplay_reanchor = (
            os.environ.get("CV_SLATE_INPLAY_REANCHOR", "").strip().lower()
            not in ("", "0", "false", "no", "off"))
        _slate_lm_hist: list = []
        if _slate_inplay_reanchor:
            try:
                _slate_lm_hist = _load_inplay_line_history(date, frozenset())
            except Exception:
                _slate_lm_hist = []
        try:
            for b in bets:
                gid = str(b.get("game_id") or "")
                lm = live_maps.get(gid) or {}
                if not lm:
                    continue
                key = ((b.get("player_name") or "").lower(),
                       (b.get("prop_stat") or "").lower())
                live_q50 = lm.get(key)
                if live_q50 is None:
                    continue
                mp = (mp_maps.get(gid) or {}).get(key[0], 0.0)
                w_live = _live_shrink_weight(mp)
                try:
                    pregame_q50 = float(b.get("q50") or live_q50)
                except (TypeError, ValueError):
                    pregame_q50 = float(live_q50)
                shrunk_q50 = w_live * float(live_q50) + (1.0 - w_live) * pregame_q50
                # BUG-3 (CV_INGAME_OUT_BET_CAP): cap an OUT-listed player's
                # blended projection at his current box value BEFORE the edge/EV
                # is recomputed. No-op when the out-set is empty (flag OFF /
                # empty file) or the player is not OUT. Mirrors the box-card cap.
                if _out_set:
                    _cur_v = (cur_maps.get(gid) or {}).get(key)
                    shrunk_q50 = _out_cap_blended(
                        _out_set, key[0], shrunk_q50, _cur_v)
                # Re-anchor line + per-book ladder to the live in-play market so
                # the regrade prices against the CURRENT line, not the frozen
                # pregame one (gated; no-op when no in-play line exists).
                if _slate_inplay_reanchor and _slate_lm_hist:
                    try:
                        _reanchor_to_live_inplay(b, _slate_lm_hist, shrunk_q50)
                    except Exception:
                        pass
                try:
                    _regrade_bet_with_live_q50(
                        b, shrunk_q50, stat_sigma_for_slate, _BANKROLL_DEFAULT)
                except Exception:
                    continue

        except Exception as _exc_sr:
            _log_sr = __import__("logging").getLogger(__name__)
            _log_sr.warning("slate live regrade failed: %s", _exc_sr)

        # BUG 7 FIX: run _apply_calibration_gate on the FULL pre-truncation list
        # so valid bets are not dropped by alphabetical tie-break when many tie
        # at the EV cap. Gate returns calibrated+filtered survivors; we then sort
        # by calibrated EV with an edge-magnitude secondary tie-break (deterministic,
        # not alphabetical) and THEN truncate to _TOP_N.
        # WHY reorder (not just add tie-break): the [:50] cut before the gate
        # can drop legitimate edges that would have survived the filter but were
        # ranked below the cap by the pre-calibration naive EV. Gating first ensures
        # the served pool is drawn from all valid candidates, not just the
        # alphabetically-lucky 50.
        # Pass the slate DATE so the pre-truncation gate also sees the playoff window
        # (defense-in-depth; the envelope re-gate below also carries date, and CSV-path
        # bets already carry 004-prefixed ids). Byte-identical in the regular season.
        _stub_env = {"date": date, "bets": bets}
        _stub_env = _apply_calibration_gate(_stub_env)
        bets = _stub_env.get("bets") or []
        bets.sort(key=lambda b: (
            b["ev_pct"] is None,
            -(min(b.get("ev_pct") or 0.0, _SANE_EV_CEILING)),
            -abs(b.get("edge_units") or b.get("edge") or 0.0),
        ))
        bets = bets[:_TOP_N]
        _gate_already_applied = True
    else:
        bets = slate_no_lines(slate_rows, _STATS, _TOP_N)
        _gate_already_applied = False

    _log = __import__("logging").getLogger(__name__)
    try: from api._courtvision_form import attach_form; attach_form(bets)
    except Exception as exc: _log.warning("attach_form: %s", exc)
    try: from src.llm.bet_narrator import narrate_slate; narrate_slate(bets, date)
    except Exception as exc: _log.warning("narrate_slate: %s", exc)

    evs = [b["ev_pct"] for b in bets if b.get("ev_pct") is not None]
    _fresh_ages = [b["freshest_book_age_min"] for b in bets
                   if b.get("freshest_book_age_min") is not None]
    lines_freshness_avg_min = round(sum(_fresh_ages) / len(_fresh_ages), 1) if _fresh_ages else None
    envelope = {"date": date, "generated_at": datetime.utcnow().isoformat() + "Z",
        "bankroll_default_dollars": _BANKROLL_DEFAULT,
        "stale_data": date != _today_et(),
        "is_playoff": _is_playoff_date(date),
        "has_lines": has_lines, "latest_available": _latest_slate_date(),
        "lines_freshness_avg_min": lines_freshness_avg_min,
        "summary": {"n_bets": len(bets), "avg_ev_pct": round(sum(evs)/len(evs), 2) if evs else 0.0,
                    "n_over": sum(1 for b in bets if b["side"] == "OVER"),
                    "n_under": sum(1 for b in bets if b["side"] == "UNDER")},
        "bets": bets}
    if not _gate_already_applied:
        envelope = _apply_calibration_gate(envelope)
    else:
        # Gate already ran; copy over the calibration metadata from the stub envelope.
        envelope["all_books_universe"] = _stub_env.get("all_books_universe", [])
        envelope["calibration"] = _stub_env.get("calibration", {})
        # Re-compute summary from the now-truncated bets list (may be smaller than
        # what _apply_calibration_gate counted before truncation).
        evs2 = [b["ev_pct"] for b in bets if b.get("ev_pct") is not None]
        envelope["summary"] = {
            "n_bets": len(bets),
            "avg_ev_pct": round(sum(evs2) / len(evs2), 2) if evs2 else 0.0,
            "n_over": sum(1 for b in bets if b["side"] == "OVER"),
            "n_under": sum(1 for b in bets if b["side"] == "UNDER"),
        }
    envelope = _attach_book_quotes(envelope, date)
    _CACHE[cache_key] = (time.time(), envelope)
    return envelope


def _reanchor_to_live_inplay(cp: dict, lm_hist: list, shrunk_q50: float) -> bool:
    """Re-anchor a bet dict to the LATEST live in-play line + per-book prices for
    its (player, stat), so a downstream _regrade_bet_with_live_q50 prices against
    the CURRENT market rather than the frozen pregame line. Sets cp['line'],
    cp['_books_full'] (the regrade's price ladder), cp['all_books_live'] and
    cp['freshest_book_age_min']. Returns True when a live in-play line was found
    and applied, False otherwise (cp left unchanged).

    Mirrors the /tonight live_bets re-anchor (kept inline there) so parlay legs
    move with the lines instead of showing stale pregame numbers."""
    nm = (cp.get("player_name") or "").lower()
    st = (cp.get("prop_stat") or "").lower()
    _ip_by_book: dict = {}
    for _r in lm_hist:
        if _r.get("name") == nm and _r.get("stat") == st:
            _bk = _r.get("book") or "live"
            if _bk not in _ip_by_book or _r["cap"] > _ip_by_book[_bk]["cap"]:
                _ip_by_book[_bk] = _r
    if not _ip_by_book:
        return False
    _lines = sorted(r["line"] for r in _ip_by_book.values())
    _med = _lines[len(_lines) // 2]
    _side = "OVER" if shrunk_q50 >= _med else "UNDER"
    _skey = "over" if _side == "OVER" else "under"
    _pool = [r for r in _ip_by_book.values()
             if r.get(_skey) is not None] or list(_ip_by_book.values())
    _main_line = min((r["line"] for r in _pool),
                     key=lambda ln: abs(ln - shrunk_q50))
    cp["line"] = _main_line
    cp["_books_full"] = [
        {"book": _inplay_book_label(r.get("book")),
         "over_odds": r.get("over"), "under_odds": r.get("under"),
         "captured_at": r.get("cap")}
        for r in _pool if r["line"] == _main_line
    ]
    cp["all_books_live"] = [
        {"book": _inplay_book_label(r.get("book")),
         "line": r["line"], "over": r.get("over"), "under": r.get("under")}
        for r in sorted(_ip_by_book.values(), key=lambda r: r["line"])
    ]
    try:
        from datetime import datetime as _dtf, timezone as _tzf  # noqa: PLC0415
        _cs = []
        for _r in _ip_by_book.values():
            _c = (_r.get("cap") or "").replace("Z", "+00:00")
            if not _c:
                continue
            _dt = _dtf.fromisoformat(_c)
            if _dt.tzinfo is None:
                _dt = _dt.replace(tzinfo=_tzf.utc)
            _cs.append(_dt)
        if _cs:
            cp["freshest_book_age_min"] = round(
                max(0.0, (_dtf.now(_tzf.utc) - max(_cs)).total_seconds() / 60.0), 1)
    except Exception:
        pass
    return True


# Parlay realism caps (DATA CONTRACT).
_PARLAY_LEG_P_CAP = 0.62      # per-leg calibrated win prob ceiling (mirrors single bets)
_PARLAY_EV_DISPLAY_CAP = 60.0  # max displayed parlay EV% (the raw +277% is not real)
# best_book bucket keys are already display names (consolidate_for_slate maps
# via _BOOK_DISPLAY), but normalise any stray lowercase key for safety.
_PARLAY_BOOK_DISPLAY = {
    "dk": "DraftKings", "fd": "FanDuel", "pin": "Pinnacle",
    "draftkings": "DraftKings", "fanduel": "FanDuel", "pinnacle": "Pinnacle",
}


def _calibrated_parlay_ev(legs: list[dict], decimal_odds: float | None,
                          combined_american: int | None,
                          playoff: bool) -> dict:
    """Recompute a REALISTIC parlay EV from CALIBRATED per-leg win probs.

    The ParlayEngine prices ev_pct from a raw Monte-Carlo joint hit-rate
    (p_hit_model) whose marginals are the uncalibrated Normal-CDF leg probs —
    this is the absurd "+277%" compound. Here we instead use the SAME calibrated
    leg probability the single-bet cards use (edge_calibration.calibrate_p_win,
    isotonic, capped), cap each leg at _PARLAY_LEG_P_CAP, take the product as the
    combined hit prob (a deliberately conservative independence assumption — real
    correlation only LOWERS a same-side parlay's true joint prob vs the product,
    so this never over-states), and recompute EV at the combined American price.
    The displayed EV is capped at _PARLAY_EV_DISPLAY_CAP and the grade is forced
    to at most 'C' on playoff dates.

    Returns {combined_prob, ev_pct, grade, note}. Falls back gracefully (leg
    model_prob, then 0.5) when calibration is unavailable.
    """
    try:
        from src.prediction.edge_calibration import calibrate_p_win  # noqa: PLC0415
        from src.prediction.bet_thresholds import (  # noqa: PLC0415
            edge_threshold_for, kelly_b_hit_rate_for,
        )
        _have = True
    except Exception:
        _have = False

    combined_p = 1.0
    for leg in legs:
        stat = (leg.get("prop_stat") or "").lower()
        p = None
        if _have and stat:
            try:
                edge = leg.get("edge_units")
                if edge is None and leg.get("q50") is not None and leg.get("line") is not None:
                    edge = float(leg["q50"]) - float(leg["line"])
                p = calibrate_p_win(stat, abs(float(edge or 0.0)),
                                    edge_threshold_for(stat),
                                    kelly_b_hit_rate_for(stat))
            except Exception:
                p = None
        if p is None:
            # Fall back to the leg's own calibrated single-bet prob, else 0.5.
            try:
                p = float(leg.get("model_prob"))
            except (TypeError, ValueError):
                p = 0.5
        combined_p *= min(_PARLAY_LEG_P_CAP, max(0.0, p))

    # Payout-per-$100 from the combined decimal (prefer decimal; derive from the
    # American price when decimal is absent).
    if decimal_odds and decimal_odds > 1.0:
        payout = (decimal_odds - 1.0) * 100.0
    elif combined_american is not None:
        ca = int(combined_american)
        payout = float(ca) if ca > 0 else (10000.0 / abs(ca)) if ca <= -100 else 100.0
    else:
        payout = 100.0
    ev_pct = combined_p * payout - (1.0 - combined_p) * 100.0
    ev_pct = round(min(ev_pct, _PARLAY_EV_DISPLAY_CAP), 2)

    # Grade off the calibrated combined prob; cap at C on playoff dates.
    try:
        from src.prediction.bet_grades import letter_grade  # noqa: PLC0415
        grade, _gnote = letter_grade(
            "parlay", float(combined_p), float(ev_pct),
            playoff_window=playoff, stale_lines=False,
        ).values()
    except Exception:
        # Local fallback letter grade.
        if ev_pct >= 8 and combined_p >= 0.35:
            grade = "B"
        elif ev_pct >= 0:
            grade = "C"
        else:
            grade = "D"
    if playoff and grade in ("A", "B"):
        grade = "C"

    note = ("Calibrated parlay EV (isotonic per-leg probs, capped); "
            "playoff grade C — paper only." if playoff else
            "Calibrated parlay EV (isotonic per-leg probs, capped).")
    return {"combined_prob": round(combined_p, 4), "ev_pct": ev_pct,
            "grade": grade, "note": note}


def _format_american(odds) -> str:
    """Format an American-odds int as a signed display string ('+450' / '-120')."""
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return ""
    return f"+{o}" if o > 0 else str(o)


def _build_parlays(date: str, seed: int = 0, top_n: int = 25) -> dict:
    """Same-book parlays only. For each sportsbook on the slate, run ParlayEngine
    against the bets best-priced at that book, then pool/rank by EV.

    Live behavior: when any game on the slate has a live snapshot in
    data/live/<gid>_*.json, we re-grade that game's bets via
    live_engine.project_from_snapshot first, so parlays reflect current game
    state (a player in foul trouble or having a hot Q1 shifts the parlay EV
    accordingly). Cache key includes the newest snapshot mtime so each live
    update invalidates the cache automatically.
    """
    # Build the slate first — need its bets for live regrade matching
    env = _build_slate(date)
    bets = env.get("bets", [])

    # Probe for live snapshots — any file written in the last 6 hours is a
    # candidate. We don't try to match snapshot game_ids to slate game_ids
    # (the alias map is too incomplete and the test snapshot uses sportsbook
    # ids); instead we project each recent snapshot and merge into a
    # (player_name, stat) → projected_final map. Bets match by player name.
    live_dir = _ROOT / "data" / "live"
    snap_mtime = 0
    recent_snaps: list = []
    if live_dir.exists() and bets:
        cutoff = time.time() - 6 * 3600
        # Keep one entry per unique snapshot file-stem prefix (gid_<ts>).
        latest_per_gid: dict[str, tuple[float, "Path"]] = {}
        try:
            for p in live_dir.iterdir():
                if not p.is_file() or p.suffix != ".json":
                    continue
                try:
                    mt = p.stat().st_mtime
                except OSError:
                    continue
                if mt < cutoff:
                    continue
                gid = p.stem.split("_")[0]
                cur = latest_per_gid.get(gid)
                if cur is None or mt > cur[0]:
                    latest_per_gid[gid] = (mt, p)
                if mt > snap_mtime:
                    snap_mtime = mt
            recent_snaps = [path for _, path in latest_per_gid.values()]
        except Exception:
            recent_snaps = []

    cache_key = ("parlays", date, seed, top_n, int(snap_mtime))
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC:
        return entry[1]
    has_lines = env.get("has_lines", False)
    gen_at = datetime.utcnow().isoformat() + "Z"
    if not bets or not has_lines:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": has_lines, "parlays": []}
        _CACHE[cache_key] = (time.time(), out)
        return out

    # ── Live regrade ─────────────────────────────────────────────────────
    # For each recent snapshot, run live_engine and merge its (player_name,
    # stat) → projected_final into a single map. Then deep-copy bets and
    # re-grade those whose (name, stat) match the map.
    live_games_count = 0
    if recent_snaps:
        try:
            from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
            import copy as _copy_p  # noqa: PLC0415
            import json as _json_p  # noqa: PLC0415

            sig_table = _stat_sigma_for_date(date)
            # Live in-play line history for ALL live games on the slate (empty
            # canon_ids -> all rows) so each leg can re-anchor to the current
            # market line+price, not the frozen pregame line.
            try:
                lm_hist_p = _load_inplay_line_history(date, frozenset())
            except Exception:
                lm_hist_p = []
            live_q50_map: dict[tuple, float] = {}
            # Bug 2 fix (site c): parallel current map so shrunk can be floored
            # at already-accumulated stat before regrading parlay legs.
            current_map_c: dict[tuple, float] = {}
            player_minutes: dict[str, float] = {}
            # BUG-3 (CV_INGAME_OUT_BET_CAP): operator OUT list. Empty set when the
            # flag is OFF / file absent / file empty -> the cap below is a literal
            # no-op (byte-identical). current_map_c already carries `current` for
            # every leg, so the cap needs no extra projection work.
            from api._courtvision_out_cap import (  # noqa: PLC0415
                cap_blended_value as _out_cap_blended,
                load_out_set as _out_load_set,
            )
            _out_set = _out_load_set(date)
            for snap_path in recent_snaps:
                try:
                    snap = _json_p.loads(snap_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not snap.get("period"):
                    continue
                try:
                    rows = project_from_snapshot(snap) or []
                except Exception:
                    continue
                if rows:
                    live_games_count += 1
                for r in rows:
                    nm = (r.get("name") or "").lower()
                    st = (r.get("stat") or "").lower()
                    pf = r.get("projected_final")
                    if nm and st and pf is not None:
                        try:
                            live_q50_map[(nm, st)] = float(pf)
                        except (TypeError, ValueError):
                            continue
                    cur_c = r.get("current")
                    if nm and st and cur_c is not None:
                        try:
                            current_map_c[(nm, st)] = float(cur_c)
                        except (TypeError, ValueError):
                            pass
                # Merge per-player minutes (last writer wins — recent snapshots
                # take precedence for the same player in a multi-game scan).
                player_minutes.update(
                    _shrink_player_minutes_from_snapshot(snap))

            if live_q50_map:
                regraded_bets = []
                for b in bets:
                    key = ((b.get("player_name") or "").lower(),
                           (b.get("prop_stat") or "").lower())
                    if key in live_q50_map:
                        # deepcopy (not shallow) so regrade never mutates the
                        # bet dict held by the cached slate envelope — repeated
                        # cache hits would otherwise re-mutate already-regraded
                        # objects and corrupt ev_pct / model_prob.
                        cp = _copy_p.deepcopy(b)
                        try:
                            mp = player_minutes.get(key[0], 0.0)
                            w_live = _live_shrink_weight(mp)
                            live_raw = live_q50_map[key]
                            pregame_q50 = float(cp.get("q50") or live_raw)
                            shrunk = w_live * live_raw + (1.0 - w_live) * pregame_q50
                            # Bug 2 fix (site c): floor shrunk at already-accumulated stat
                            _cur_c = current_map_c.get(key)
                            if _cur_c is not None:
                                try:
                                    shrunk = max(shrunk, float(_cur_c))
                                except (TypeError, ValueError):
                                    pass
                            # BUG-3 (CV_INGAME_OUT_BET_CAP): cap an OUT-listed
                            # player's blended leg projection at current BEFORE
                            # re-anchor/regrade, removing the phantom edge. No-op
                            # when the out-set is empty or the player isn't OUT.
                            if _out_set:
                                shrunk = _out_cap_blended(
                                    _out_set, key[0], shrunk, _cur_c)
                            # Re-anchor line + per-book ladder to the live market
                            # BEFORE regrading, so the leg's displayed line and
                            # best price track the current in-play odds.
                            try:
                                _reanchor_to_live_inplay(cp, lm_hist_p, shrunk)
                            except Exception:
                                pass
                            _regrade_bet_with_live_q50(cp, shrunk, sig_table)
                            regraded_bets.append(cp)
                        except Exception:
                            regraded_bets.append(b)
                    else:
                        regraded_bets.append(b)
                # Re-sort by EV so the best (live) bets are buckets-ready
                regraded_bets.sort(
                    key=lambda b: (b.get("ev_pct") is None,
                                   -(b.get("ev_pct") or 0.0))
                )
                bets = regraded_bets
        except Exception as exc:
            import logging as _lgp  # noqa: PLC0415
            _lgp.getLogger(__name__).warning(
                "parlay live regrade failed: %s", exc)

    from src.prediction.parlay_engine import ParlayEngine
    # Bucket bets by their best book — every leg in the same bucket can be
    # placed at the same sportsbook.
    buckets: dict[str, list[dict]] = {}
    for b in bets:
        bk = (b.get("best_book") or "").strip()
        if not bk:
            continue
        buckets.setdefault(bk, []).append(b)

    # Playoff dates get a sigma boost on the parlay sampler so joint hit-rate
    # is honest for the wider playoff residual distribution.
    _playoff_parlay = _is_playoff_date(date)
    sigma_mult = _PLAYOFF_SIGMA_MULT if _playoff_parlay else 1.0

    def _has_same_player_legs(parlay: dict) -> bool:
        """True when the parlay has two legs on the same player. These have
        high correlation (player health/role drives both); the engine's RHO
        matrix dampens but the resulting EV is still inflated, so we exclude."""
        seen = set()
        for leg in parlay.get("legs", []):
            nm = (leg.get("player_name") or "").lower() if isinstance(leg, dict) else ""
            if nm in seen and nm:
                return True
            if nm:
                seen.add(nm)
        return False

    def _legs_signature(parlay: dict) -> frozenset:
        out = set()
        for leg in parlay.get("legs", []):
            if not isinstance(leg, dict):
                continue
            key = (
                (leg.get("player_name") or "").lower(),
                (leg.get("prop_stat") or "").lower(),
                leg.get("side"),
                leg.get("line"),
            )
            out.add(key)
        return frozenset(out)

    # Per-book parlay generation. Take top-K per book per leg-count so every
    # book that produces ≥2 valid combos gets representation in the output —
    # otherwise BetMGM (which usually wins per-leg EV) monopolizes the slate.
    PER_BOOK_PER_LEGCOUNT_CAP = 5  # ceiling on parlays per (book, n_legs)
    per_book_results: dict[str, list[dict]] = {}
    for book, pool in buckets.items():
        if len(pool) < 2:
            continue
        try:
            parlays = ParlayEngine(
                pool, rng_seed=seed, sigma_multiplier=sigma_mult
            ).enumerate_parlays(max_legs=4, min_ev_pct=-999.0)
        except Exception:
            continue
        by_id = {b.get("bet_id"): b for b in pool if b.get("bet_id")}
        # Normalize legs + drop same-player parlays + dedup by leg signature
        cleaned: list[dict] = []
        seen_sigs: set[frozenset] = set()
        _book_disp = _PARLAY_BOOK_DISPLAY.get(book.lower(), book)
        for p in parlays:
            p["book"] = book
            resolved: list[dict] = []
            for leg_ref in p.get("legs", []):
                if isinstance(leg_ref, dict):
                    bet = by_id.get(leg_ref.get("bet_id")) or {}
                    leg = dict(leg_ref)
                else:
                    bet = by_id.get(leg_ref) or {}
                    leg = {
                        "player_name": bet.get("player_name"),
                        "prop_stat": bet.get("prop_stat"),
                        "line": bet.get("line"),
                        "side": bet.get("side"),
                        "best_price": bet.get("best_price"),
                    }
                # DATA CONTRACT: every leg must carry best_book (non-blank) +
                # best_price + line + side. In same-book parlays every leg is
                # placed at `book`; prefer the bet's own best_book, else the
                # bucket book. Also stamp q50/edge_units so the calibrated-EV
                # recompute below can derive each leg's isotonic win prob.
                leg.setdefault("line", bet.get("line"))
                leg.setdefault("side", bet.get("side"))
                if leg.get("best_price") is None:
                    leg["best_price"] = bet.get("best_price")
                leg["best_book"] = bet.get("best_book") or _book_disp
                leg["q50"] = bet.get("q50")
                leg["edge_units"] = bet.get("edge_units")
                leg["model_prob"] = bet.get("model_prob")
                resolved.append(leg)
            p["legs"] = resolved
            # combined_odds_american (DATA CONTRACT: signed display string).
            _ca = p.get("combined_odds_american")
            if _ca is None:
                _ca = p.get("combined_american")
            p["combined_american"] = _ca
            p["combined_odds_american"] = _format_american(_ca)
            # Recompute a REALISTIC ev_pct from CALIBRATED per-leg probs (the
            # raw engine ev_pct is the absurd +277% compound). Cap + grade C
            # on playoff dates. Keep the raw for transparency.
            _cal = _calibrated_parlay_ev(
                resolved, p.get("combined_odds_decimal"), _ca, _playoff_parlay)
            p["ev_pct_raw"] = p.get("ev_pct")
            p["ev_pct"] = _cal["ev_pct"]
            p["combined_prob"] = _cal["combined_prob"]
            p["grade"] = _cal["grade"]
            p["grade_note"] = _cal["note"]
            if _has_same_player_legs(p):
                continue
            sig = _legs_signature(p)
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            cleaned.append(p)
        # Per-leg-count diversity within this book: top K from each leg count
        by_legcount: dict[int, list[dict]] = {}
        for p in cleaned:
            by_legcount.setdefault(p.get("n_legs") or len(p.get("legs", [])), []).append(p)
        book_out: list[dict] = []
        for k_legs in (2, 3, 4):
            xs = by_legcount.get(k_legs) or []
            xs.sort(key=lambda p: -(p.get("ev_pct") or 0.0))
            book_out.extend(xs[:PER_BOOK_PER_LEGCOUNT_CAP])
        per_book_results[book] = book_out

    # Pooled output: round-robin across books, EV-ranked within each book's
    # contribution. Round-robin guarantees every book gets at least 1 parlay
    # before any book gets its 2nd.
    book_iters = {bk: iter(sorted(xs, key=lambda p: -(p.get("ev_pct") or 0.0)))
                  for bk, xs in per_book_results.items() if xs}
    # Also enforce leg-count mix at the global level: drop parlays whose legs
    # overlap ≥2 with an already-emitted parlay (so we don't show 8 minor
    # variations of the same anchor pair).
    emitted_sigs: list[frozenset] = []
    pooled: list[dict] = []
    while book_iters and len(pooled) < top_n:
        empties = []
        for book, it in book_iters.items():
            if len(pooled) >= top_n:
                break
            picked = None
            while True:
                try:
                    cand = next(it)
                except StopIteration:
                    empties.append(book); break
                sig = _legs_signature(cand)
                # Drop if it shares 2+ legs with any already-emitted parlay
                overlapping = any(len(sig & ex) >= 2 for ex in emitted_sigs)
                if overlapping:
                    continue
                picked = cand; break
            if picked is not None:
                pooled.append(picked)
                emitted_sigs.append(_legs_signature(picked))
        for bk in empties:
            book_iters.pop(bk, None)

    # If we didn't fill top_n via the diverse round-robin, backfill from the
    # leftovers — BUT still apply the diversity filter so we don't undo the
    # work. Better to return 15 diverse parlays than 25 with heavy duplication.
    if len(pooled) < top_n:
        emitted_ids = {p.get("parlay_id") for p in pooled}
        leftovers: list[dict] = []
        for xs in per_book_results.values():
            for p in xs:
                if p.get("parlay_id") not in emitted_ids:
                    leftovers.append(p)
        leftovers.sort(key=lambda p: -(p.get("ev_pct") or 0.0))
        for p in leftovers:
            if len(pooled) >= top_n:
                break
            sig = _legs_signature(p)
            if any(len(sig & ex) >= 2 for ex in emitted_sigs):
                continue
            pooled.append(p)
            emitted_sigs.append(sig)

    # Final sort: keep diverse round-robin order but lift highest-EV to the top
    pooled.sort(key=lambda p: -(p.get("ev_pct") or 0.0))
    pooled = pooled[:top_n]
    out = {"date": date, "generated_at": gen_at, "n_parlays": len(pooled),
           "has_lines": True, "parlays": pooled,
           "live_games_count": live_games_count}
    _CACHE[cache_key] = (time.time(), out)
    return out


def _build_parlays_constructor(date: str, max_legs: int, min_ev_pct: float,
                               top_n: int = 25, seed: int = 0) -> dict:
    """Build parlays via src.prediction.parlay_constructor (SGP-penalty model).

    Reuses the cached single-leg slate, then enumerates valid combos via the
    Iter-43-validated constructor that applies the 15% SGP penalty + correlation
    shrinkage on same-player combos. Output is JSON-safe.
    """
    cache_key = ("parlays_constructor", date, max_legs, min_ev_pct, top_n, seed)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC:
        return entry[1]
    env = _build_slate(date)
    bets = env.get("bets", [])
    has_lines = env.get("has_lines", False)
    gen_at = datetime.utcnow().isoformat() + "Z"
    if not bets or not has_lines:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": has_lines, "parlays": [], "engine": "constructor"}
        _CACHE[cache_key] = (time.time(), out)
        return out

    import pandas as _pd  # noqa: PLC0415
    rows: list[dict] = []
    for b in bets:
        ev_pct = b.get("ev_pct")
        if ev_pct is None or ev_pct < min_ev_pct:
            continue
        # The constructor only consumes OVER legs (model places positive-edge OVERs).
        if (b.get("side") or "").upper() != "OVER":
            continue
        stat = (b.get("prop_stat") or b.get("stat") or "").lower()
        if not stat:
            continue
        rows.append({
            "player":     b.get("player_name"),
            "player_id":  b.get("player_id"),
            "stat":       stat,
            "side":       "OVER",
            "line":       b.get("line"),
            "odds":       b.get("best_price") if b.get("best_price") is not None else -110,
            "prob":       b.get("model_prob"),
            "ev":         ev_pct,
            "game_id":    b.get("game_id"),
            "team":       b.get("team"),
            "book":       b.get("best_book"),
        })

    if not rows:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": True, "parlays": [], "engine": "constructor"}
        _CACHE[cache_key] = (time.time(), out)
        return out

    df = _pd.DataFrame(rows)
    from src.prediction.parlay_constructor import (  # noqa: PLC0415
        build_parlay_candidates, rank_parlays,
    )
    try:
        candidates = build_parlay_candidates(df)
    except Exception as exc:
        import logging as _log  # noqa: PLC0415
        _log.getLogger(__name__).warning("parlay_constructor build failed: %s", exc)
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": True, "parlays": [], "engine": "constructor",
               "error": str(exc)}
        _CACHE[cache_key] = (time.time(), out)
        return out

    if candidates.empty:
        parlays_list: list[dict] = []
    else:
        ranked = rank_parlays(candidates, top_n=top_n)
        parlays_list = ranked.to_dict(orient="records")
        # JSON-safety pass: serialize any numpy / nested types defensively.
        import json as _json  # noqa: PLC0415
        parlays_list = _json.loads(_json.dumps(parlays_list, default=str))

    out = {"date": date, "generated_at": gen_at,
           "n_parlays": len(parlays_list), "has_lines": True,
           "parlays": parlays_list, "engine": "constructor"}
    _CACHE[cache_key] = (time.time(), out)
    return out


# ── home page helpers ────────────────────────────────────────────────────────

_TEAM_ABBREVS: dict[str, str] = {
    # Full name fragments → display short name used on cards
    "76ers": "PHI", "bucks": "MIL", "bulls": "CHI", "cavaliers": "CLE",
    "celtics": "BOS", "clippers": "LAC", "grizzlies": "MEM", "hawks": "ATL",
    "heat": "MIA", "hornets": "CHA", "jazz": "UTA", "kings": "SAC",
    "knicks": "NYK", "lakers": "LAL", "magic": "ORL", "mavericks": "DAL",
    "nets": "BKN", "nuggets": "DEN", "pacers": "IND", "pelicans": "NOP",
    "pistons": "DET", "raptors": "TOR", "rockets": "HOU", "spurs": "SAS",
    "suns": "PHX", "thunder": "OKC", "timberwolves": "MIN", "trail blazers": "POR",
    "warriors": "GSW", "wizards": "WAS",
}


_GAMES_LOOKUP_CACHE: dict | None = None
_GAMES_LOOKUP_MTIME: float = 0.0


def _load_games_lookup() -> dict:
    """Cached load of `data/cache/games_lookup.json` — refreshes when file mtime
    changes. Empty dict if file missing."""
    global _GAMES_LOOKUP_CACHE, _GAMES_LOOKUP_MTIME
    import json as _json
    path = _ROOT / "data" / "cache" / "games_lookup.json"
    if not path.exists():
        return _GAMES_LOOKUP_CACHE or {}
    try:
        mt = path.stat().st_mtime
        if _GAMES_LOOKUP_CACHE is None or mt > _GAMES_LOOKUP_MTIME:
            with path.open() as f:
                _GAMES_LOOKUP_CACHE = _json.load(f)
            _GAMES_LOOKUP_MTIME = mt
    except (OSError, ValueError):
        pass
    return _GAMES_LOOKUP_CACHE or {}


def _guess_teams_from_game_id(game_id: str) -> tuple[str, str]:
    """Resolve team abbrs from the NBA games_lookup.json cache. Falls back to
    generic labels when the game isn't in the lookup yet."""
    lookup = _load_games_lookup()
    info = lookup.get(str(game_id))
    if info:
        return (info.get("away_abbr", "AWAY"), info.get("home_abbr", "HOME"))
    # Some scrapers use non-NBA game_ids (e.g. KAMBI event IDs). Match by start_time.
    return ("AWAY", "HOME")


def _fmt_tipoff(start_time_iso: str) -> str:
    """Convert ISO timestamp to human-readable tipoff string, e.g. '8:40 PM ET'."""
    if not start_time_iso:
        return "TBD"
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
        # Convert to ET (UTC-4 in summer / UTC-5 in winter — approximate)
        et_offset = timedelta(hours=-4)
        et = dt + et_offset
        hour = et.hour
        ampm = "AM" if hour < 12 else "PM"
        if hour == 0:
            hour = 12
        elif hour > 12:
            hour -= 12
        return f"{hour}:{et.minute:02d} {ampm} ET"
    except Exception:
        return start_time_iso[:16] if len(start_time_iso) >= 16 else start_time_iso


def _game_status(start_time_iso: str) -> str:
    """'live', 'pregame', or 'final' based on start time."""
    if not start_time_iso:
        return "pregame"
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (now - dt).total_seconds()
        if delta < 0:
            return "pregame"
        if delta < 4 * 3600:   # within 4-hour active game window
            return "live"
        return "final"
    except Exception:
        return "pregame"


def _build_home_data(date: str) -> dict:
    """Build the home page data payload. Cached for 60s."""
    cache_key = ("home", date)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < 60:
        return entry[1]

    from api._courtvision_odds import games_index, consolidate
    from api._predictions_overlay import overlay_predictions

    # --- games ---
    games_raw = games_index(date)

    # --- props with EV overlay (once per date) ---
    props_all: list[dict] = []
    try:
        raw_props = consolidate(date)
        props_all = overlay_predictions(date, raw_props)
    except Exception:
        props_all = []

    # Index props by game_id for fast per-game lookup
    props_by_game: dict[str, list[dict]] = {}
    for p in props_all:
        gid = p.get("game_id") or "?"
        props_by_game.setdefault(gid, []).append(p)

    # --- live regrade: override rec_side + edge_pct using live q50 ─────
    # For each game with a live snapshot, run live_engine.project_from_snapshot
    # and recompute rec_side / edge_pct per prop. Without this, the home page
    # game cards show pregame recommendations (e.g. "Cason UNDER 14.5") even
    # after he's blown past the line — the user can't see the live OVER edge
    # without clicking into /tonight first.
    try:
        from math import erf, sqrt  # noqa: PLC0415
        from api._courtvision_odds import resolve_game_id  # noqa: PLC0415
        from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
        import json as _hjs  # noqa: PLC0415
        sig_table = _stat_sigma_for_date(date)
        _live_dir = _ROOT / "data" / "live"
        # Build live_q50 maps per game_id (via canonical alias group)
        live_q50_by_gid: dict[str, dict[tuple, float]] = {}
        # Bug 2 fix (site b): parallel map of already-accumulated stats per gid
        current_by_gid: dict[str, dict[tuple, float]] = {}
        loaded_alias_groups: set[frozenset] = set()
        for gid in list(props_by_game.keys()):
            alias = resolve_game_id(gid)
            canon = alias.get("canonical_ids", frozenset([gid]))
            if canon in loaded_alias_groups:
                # Reuse if any sibling alias was already loaded
                continue
            snap = None
            if _live_dir.exists():
                for _cgid in list(canon) + [gid]:
                    _latest = _latest_snap_path(_cgid)
                    if _latest is not None:
                        try:
                            snap = _hjs.loads(_latest.read_text(encoding="utf-8"))
                            break
                        except Exception:
                            continue
            if not snap or not snap.get("period"):
                continue
            try:
                rows = project_from_snapshot(snap) or []
            except Exception:
                rows = []
            lm: dict[tuple, float] = {}
            # Bug 2 fix (site b): parallel current map so shrunk_q50 can be
            # floored at already-accumulated stat at the regrade site below.
            lm_cur: dict[tuple, float] = {}
            for r in rows:
                nm = (r.get("name") or "").lower()
                st_r = (r.get("stat") or "").lower()
                pf = r.get("projected_final")
                if nm and st_r and pf is not None:
                    try:
                        lm[(nm, st_r)] = float(pf)
                    except (TypeError, ValueError):
                        continue
                cur_r = r.get("current")
                if nm and st_r and cur_r is not None:
                    try:
                        lm_cur[(nm, st_r)] = float(cur_r)
                    except (TypeError, ValueError):
                        pass
            # Apply this map to every prop whose game_id is in the canon set
            for _cgid in canon:
                if _cgid in props_by_game:
                    live_q50_by_gid[_cgid] = lm
                    if lm_cur:
                        current_by_gid[_cgid] = lm_cur
            loaded_alias_groups.add(canon)
        # Now override rec_side + edge_pct on each prop
        player_minutes_by_gid: dict[str, dict[str, float]] = {}
        for gid, lm in live_q50_by_gid.items():
            # Use the same snapshot's minutes for shrinkage; reload once
            alias = resolve_game_id(gid)
            canon = alias.get("canonical_ids", frozenset([gid]))
            snap = None
            for _cgid in list(canon) + [gid]:
                _latest = _latest_snap_path(_cgid)
                if _latest is not None:
                    try:
                        snap = _hjs.loads(_latest.read_text(encoding="utf-8"))
                        break
                    except Exception:
                        continue
            if snap:
                player_minutes_by_gid[gid] = _shrink_player_minutes_from_snapshot(snap)
        for gid, props in props_by_game.items():
            lm = live_q50_by_gid.get(gid)
            if not lm:
                continue
            mp_map = player_minutes_by_gid.get(gid, {})
            cur_map_b = current_by_gid.get(gid, {})
            for prop in props:
                nm = (prop.get("player") or "").lower()
                st_p = (prop.get("stat") or "").lower()
                live_q50 = lm.get((nm, st_p))
                if live_q50 is None:
                    continue
                mp = mp_map.get(nm, 0.0)
                w_live = _live_shrink_weight(mp)
                pregame_q50 = prop.get("pregame_q50")
                if pregame_q50 is None:
                    pregame_q50 = live_q50
                try:
                    shrunk_q50 = w_live * float(live_q50) + (1.0 - w_live) * float(pregame_q50)
                except (TypeError, ValueError):
                    shrunk_q50 = float(live_q50)
                # Bug 2 fix (site b): floor shrunk_q50 at already-accumulated stat
                _cur_b = cur_map_b.get((nm, st_p))
                if _cur_b is not None:
                    try:
                        shrunk_q50 = max(shrunk_q50, float(_cur_b))
                    except (TypeError, ValueError):
                        pass
                try:
                    line_f = float(prop.get("line"))
                except (TypeError, ValueError):
                    continue
                sigma = sig_table.get(st_p, 1.0)
                if sigma <= 0:
                    sigma = 1.0
                new_side = "OVER" if shrunk_q50 >= line_f else "UNDER"
                z = (line_f - shrunk_q50) / sigma
                p_over = 1.0 - 0.5 * (1.0 + erf(z / sqrt(2.0)))
                model_prob = p_over if new_side == "OVER" else (1.0 - p_over)
                market_prob = prop.get("market_prob")
                if isinstance(market_prob, (int, float)) and 0.0 < market_prob < 1.0:
                    edge_pct = round((model_prob - market_prob) * 100.0, 1)
                else:
                    edge_pct = round((model_prob - 0.5) * 100.0, 1)
                prop["rec_side"] = new_side
                prop["edge_pct"] = edge_pct
                prop["live_regraded"] = True
    except Exception as _exc_hr:
        import logging as _lg_hr  # noqa: PLC0415
        _lg_hr.getLogger(__name__).warning(
            "home_data live regrade failed: %s", _exc_hr)

    # --- build game card data ---
    upcoming: list[dict] = []
    live: list[dict] = []

    # Pre-load each game's latest snapshot once so we can detect FINAL state
    # (the start_time-based heuristic only knows "pregame / live / final by
    # time elapsed" — it does NOT know that the buzzer sounded). Without
    # this the home card shows "PREGAME" or "LIVE" for a finished game.
    import json as _hjs2  # noqa: PLC0415
    from api._courtvision_odds import resolve_game_id as _rg_hm  # noqa: PLC0415
    _live_dir_hm = _ROOT / "data" / "live"
    snap_status_by_gid: dict[str, dict] = {}
    snap_score_by_gid: dict[str, tuple[str, int, str, int]] = {}
    for g in games_raw:
        gid = g.get("game_id") or ""
        if not gid:
            continue
        alias = _rg_hm(gid)
        canon = list(alias.get("canonical_ids", frozenset([gid]))) + [gid]
        if not _live_dir_hm.exists():
            continue
        for _cgid in canon:
            _latest = _latest_snap_path(_cgid)
            if _latest is not None:
                try:
                    snap = _hjs2.loads(_latest.read_text(encoding="utf-8"))
                    snap_status_by_gid[gid] = snap
                    if snap.get("home_team") and snap.get("away_team"):
                        snap_score_by_gid[gid] = (
                            snap.get("away_team") or "",
                            int(snap.get("away_score") or 0),
                            snap.get("home_team") or "",
                            int(snap.get("home_score") or 0),
                        )
                    break
                except Exception:
                    continue

    for g in games_raw:
        gid = g["game_id"]
        st = g.get("start_time") or ""
        # Drop entries with no start_time — those are non-NBA / WNBA / scraper-
        # internal IDs that don't represent a real upcoming NBA game.
        if not st:
            continue
        status = _game_status(st)
        # Override status from snapshot when authoritative: NBA's live feed
        # reports gameStatusText/game_status as "FINAL" once the buzzer sounds.
        snap = snap_status_by_gid.get(gid)
        if snap:
            snap_status_raw = str(snap.get("game_status") or "").strip().upper()
            if snap_status_raw == "FINAL" or "FINAL" in snap_status_raw:
                status = "final"
            elif snap.get("period") and int(snap.get("period") or 0) >= 1 and status == "pregame":
                # Snapshot has game data but we'd otherwise show pregame → it's live
                status = "live"
        game_props = props_by_game.get(gid, [])

        # Top edges: props with rec_side and edge_pct, sorted by edge desc
        edge_props = [p for p in game_props if p.get("rec_side") and p.get("edge_pct") is not None]
        edge_props.sort(key=lambda p: -(p.get("edge_pct") or 0))

        top_edges = []
        for ep in edge_props[:5]:  # Pull 5 so client-side book filter still has 3 after filtering
            side = ep.get("rec_side", "OVER")
            best_o, best_u = None, None
            best_book_o, best_book_u = None, None
            for b in ep.get("books", []):
                bo = b.get("over_price"); bu = b.get("under_price"); bk = b.get("book") or ""
                if bo is not None and (best_o is None or bo > best_o):
                    best_o, best_book_o = bo, bk
                if bu is not None and (best_u is None or bu > best_u):
                    best_u, best_book_u = bu, bk
            odds = best_o if side == "OVER" else best_u
            best_book = best_book_o if side == "OVER" else best_book_u
            top_edges.append({
                "label": f"{ep['player']} {side[0]}{ep['line']:g} {ep['stat'].upper()}",
                "odds": odds,
                "edge_pct": ep.get("edge_pct"),
                "book": best_book or "",     # for client-side book filter
                "stat": ep.get("stat", ""),
                "side": side,
                "line": ep.get("line"),
                "player": ep.get("player", ""),
            })

        # ── PREGAME FALLBACK for top_edges ───────────────────────────────
        # When no live snapshot exists (pregame future game), the props
        # never get rec_side/edge_pct attached above, so top_edges is
        # empty and the card looks dead. Hydrate it from the pregame
        # slate synthesis for this date so the user sees actual picks.
        if not top_edges and status == "pregame":
            try:
                _slate_for_card = _build_slate(date)
                _bets_for_gid = [
                    _b for _b in (_slate_for_card.get("bets") or [])
                    if str(_b.get("game_id") or "") == str(gid)
                ]
                _bets_for_gid.sort(
                    key=lambda b: (b.get("ev_pct") is None, -(b.get("ev_pct") or 0.0)))
                for _b in _bets_for_gid[:5]:
                    _side = (_b.get("side") or "OVER").upper()
                    _line = float(_b.get("line") or 0)
                    _stat_u = (_b.get("prop_stat") or _b.get("stat") or "").upper()
                    # Compute edge_pct as model-minus-market probability gap in
                    # percentage points — matching the live/overlay convention
                    # (live path: (model_prob - market_prob)*100, ~line 2420).
                    # ev_pct is a dollar-return metric and MUST NOT be used here.
                    _mp = _b.get("model_prob")
                    _mkp = _b.get("market_prob")
                    if (isinstance(_mp, (int, float)) and isinstance(_mkp, (int, float))
                            and 0.0 < _mp < 1.0 and 0.0 < _mkp < 1.0):
                        _edge_pct = round((float(_mp) - float(_mkp)) * 100.0, 1)
                    else:
                        _edge_pct = None
                    top_edges.append({
                        "label": f"{_b.get('player_name','')} {_side[0]}{_line:g} {_stat_u}",
                        "odds": _b.get("best_price") or _b.get("odds"),
                        "edge_pct": _edge_pct,
                        "ev_pct": _b.get("ev_pct"),
                        "book": _b.get("best_book") or _b.get("book") or "",
                        "stat": (_stat_u or "").lower(),
                        "side": _side,
                        "line": _line,
                        "player": _b.get("player_name", ""),
                    })
            except Exception as _exc_pe:
                import logging as _lg_pe  # noqa: PLC0415
                _lg_pe.getLogger(__name__).debug(
                    "pregame top_edges hydration failed gid=%s: %s", gid, _exc_pe)

        away_abbr, home_abbr = _guess_teams_from_game_id(gid)
        # Drop KAMBI / non-NBA event IDs that the scraper ingested but we can't
        # resolve to real NBA teams.  These show "AWAY @ HOME" on the card and
        # are pure noise on the home page.
        # Resolution order: live snapshot > roster overlap with recent slate.
        # Speculative finals games (no overlap with the active series rosters)
        # get dropped instead of shown as TBD@TBD.
        if away_abbr == "AWAY" and home_abbr == "HOME":
            _snap_fb = snap_status_by_gid.get(gid)
            if _snap_fb and _snap_fb.get("away_team") and _snap_fb.get("home_team"):
                away_abbr = str(_snap_fb["away_team"]).upper()
                home_abbr = str(_snap_fb["home_team"]).upper()
            else:
                _players_in_game = sorted({(p.get("player") or "") for p in game_props})
                _inferred = _infer_teams_from_player_overlap(_players_in_game)
                if _inferred is not None:
                    away_abbr, home_abbr = _inferred
                else:
                    continue

        n_props = g.get("n_props", 0)
        # Skip games with fewer than 3 props — too sparse to be useful on the
        # home page (typical case: single-prop KAMBI side-events).
        if n_props < 3:
            continue

        card = {
            "game_id": gid,
            "start_time": st,
            "start_time_iso": st,
            "tipoff_display": _fmt_tipoff(st),
            "status": status,
            "away_team": away_abbr,
            "home_team": home_abbr,
            "matchup": f"{away_abbr} @ {home_abbr}",
            "n_props": n_props,
            "n_players": g.get("n_players", 0),
            "top_edges": top_edges,
            "score_away": None,
            "score_home": None,
        }

        # Attach live score from snapshot (also for finals)
        scoredata = snap_score_by_gid.get(gid)
        if scoredata:
            sa_team, sa_score, sh_team, sh_score = scoredata
            if sa_team.upper() == away_abbr.upper():
                card["score_away"] = sa_score
                card["score_home"] = sh_score
            elif sa_team.upper() == home_abbr.upper():
                card["score_away"] = sh_score
                card["score_home"] = sa_score

        if status == "live":
            live.append(card)
        elif status == "pregame":
            upcoming.append(card)
        elif status == "final":
            # Surface as live with a [FINAL] flag so users see the game
            # didn't just vanish when it ended — instead of being silently
            # dropped which made the home page look "broken".
            card["status"] = "final"
            live.append(card)

    # Sort upcoming by start_time
    upcoming.sort(key=lambda g: g.get("start_time") or "")
    live.sort(key=lambda g: g.get("start_time") or "")

    # --- recently settled bets ---
    settled: list[dict] = []
    try:
        from database.bet_db import BetDB
        db = BetDB()
        rows_won = db.list_bets(status="won", limit=5)
        rows_lost = db.list_bets(status="lost", limit=5)
        combined = sorted(rows_won + rows_lost,
                          key=lambda b: b.get("settled_at") or b.get("created_at") or "",
                          reverse=True)[:8]
        settled = combined
    except Exception:
        settled = []

    # Fallback: if BetDB returned nothing, read from settle_bets.py JSON cache
    if not settled:
        try:
            import json as _json
            _snap_path = _ROOT / "data" / "cache" / "settled_bets.json"
            if _snap_path.exists():
                with _snap_path.open(encoding="utf-8") as _fh:
                    _raw: list[dict] = _json.load(_fh)
                # Only show decided bets (won/lost)
                _decided_raw = [
                    {
                        "player_name": r.get("player_name", ""),
                        "stat": r.get("stat", ""),
                        "prop_stat": (r.get("stat") or "").upper(),
                        "side": r.get("side", ""),
                        "status": r.get("status", ""),
                        "settled_at": r.get("settled_at", ""),
                        "created_at": r.get("created_at") or r.get("settled_at", ""),
                        "ev_pct": r.get("ev_pct"),
                        "line": r.get("line"),
                        "actual": r.get("actual"),
                        "actual_value": r.get("actual"),
                        "pnl": None,
                        "game_id": r.get("game_id", ""),
                        "player_id": r.get("player_id", ""),
                    }
                    for r in _raw
                    if r.get("status") in ("won", "lost")
                ]
                # Dedupe: each (player_id, stat, line, game_id) appears as both
                # OVER lost + UNDER won (or vice versa). Keep only the 'won' row;
                # if only one side is present, keep it as-is.
                _dedup: dict[tuple, dict] = {}
                for row in _decided_raw:
                    key = (
                        row.get("player_id") or row.get("player_name", ""),
                        row.get("stat", ""),
                        row.get("line"),
                        row.get("game_id", ""),
                    )
                    existing = _dedup.get(key)
                    if existing is None:
                        _dedup[key] = row
                    elif row.get("status") == "won" and existing.get("status") != "won":
                        # Prefer the won side as the canonical record
                        _dedup[key] = row
                _decided = list(_dedup.values())
                _decided.sort(
                    key=lambda b: b.get("settled_at") or b.get("created_at") or "",
                    reverse=True,
                )
                settled = _decided[:8]
        except Exception:
            pass

    # `future_games` removed 2026-05-29: per-user feedback, only the next
    # known game (the one in `upcoming_games`) should appear on home.
    # Speculative NBA Finals cards with unresolved rosters were misleading.
    future_games: list[dict] = []

    result = {
        "upcoming_games": upcoming,
        "live_games": live,
        "settled_bets": settled,
        "future_games": future_games,
        "slate_date": date,
        "section_label": "Tonight" if date == _today_et() else "Upcoming",
    }
    _CACHE[cache_key] = (time.time(), result)
    return result


_NBA_AVG_PACE = 99.5  # NBA 2024-25 season average possessions/game
_NBA_CURRENT_SEASON = "2025-26"

_TEAM_PACE_CACHE: dict | None = None
_TEAM_PACE_MTIME: float = 0.0

# Module-level cache for the win-prob model (avoids re-loading pickle on every request)
_WIN_PROB_MODEL_CACHE: Optional[object] = None
_WIN_PROB_MODEL_LOADED: bool = False
_WIN_PROB_MODEL_LOCK: threading.Lock = threading.Lock()  # prevents thundering-herd on cold start

# Module-level cache for nba team_stats JSON (keyed by season string)
_TEAM_STATS_CACHE: dict = {}
_TEAM_STATS_MTIME: dict = {}

# Static NBA abbreviation → team_id mapping (all 30 teams as of 2025-26).
# Baked in so lookup never depends on a runtime nba_api import and can never
# silently return {} on Railway if nba_api is missing or its import fails.
_STATIC_ABBREV_TO_ID: dict[str, int] = {
    "ATL": 1610612737, "BKN": 1610612751, "BOS": 1610612738, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}

# Module-level abbrev→id mapping (starts pre-populated from static map)
_ABBREV_TO_TEAM_ID: dict = dict(_STATIC_ABBREV_TO_ID)


def _get_abbrev_to_id() -> dict:
    """Return NBA team abbreviation → integer team_id mapping.

    Always returns the fully-populated static map. nba_api is used to extend
    it (e.g. expansion teams) but is never required — if it fails the static
    map is returned as-is, covering all 30 current teams.
    """
    global _ABBREV_TO_TEAM_ID
    if len(_ABBREV_TO_TEAM_ID) >= 30:
        return _ABBREV_TO_TEAM_ID
    try:
        from nba_api.stats.static import teams as _nba_teams
        _ABBREV_TO_TEAM_ID = {t["abbreviation"]: int(t["id"]) for t in _nba_teams.get_teams()}
    except Exception:
        pass  # static map already set — nba_api is an optional enhancement only
    return _ABBREV_TO_TEAM_ID


def _load_nba_team_stats(season: str = _NBA_CURRENT_SEASON) -> dict:
    """Load data/nba/team_stats_{season}.json cached by season (keyed by int team_id)."""
    global _TEAM_STATS_CACHE, _TEAM_STATS_MTIME
    import json as _json
    path = _ROOT / "data" / "nba" / f"team_stats_{season}.json"
    if not path.exists():
        return {}
    try:
        mt = path.stat().st_mtime
        if season not in _TEAM_STATS_CACHE or mt > _TEAM_STATS_MTIME.get(season, 0.0):
            with path.open() as f:
                raw = _json.load(f)
            # Keys may be strings or ints — normalise to int
            _TEAM_STATS_CACHE[season] = {int(k): v for k, v in raw.items()}
            _TEAM_STATS_MTIME[season] = mt
    except (OSError, ValueError):
        pass
    return _TEAM_STATS_CACHE.get(season, {})


def _team_stats_for(abbr: str, season: str = _NBA_CURRENT_SEASON) -> dict:
    """Return the team_stats dict for a given abbreviation and season, or defaults."""
    _D = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
          "pace": _NBA_AVG_PACE, "efg_pct": 0.53, "ts_pct": 0.57,
          "tov_pct": 13.0, "reb_pct": 0.5, "win_pct": 0.5}
    ts = _load_nba_team_stats(season)
    if not ts:
        return _D
    a2id = _get_abbrev_to_id()
    tid = a2id.get(abbr.upper())
    if tid:
        return ts.get(tid, _D)
    return _D


def _load_team_pace() -> dict:
    """Load data/cache/team_pace.json if it exists, else empty dict."""
    global _TEAM_PACE_CACHE, _TEAM_PACE_MTIME
    import json as _json
    path = _ROOT / "data" / "cache" / "team_pace.json"
    if not path.exists():
        return {}
    try:
        mt = path.stat().st_mtime
        if _TEAM_PACE_CACHE is None or mt > _TEAM_PACE_MTIME:
            with path.open() as f:
                _TEAM_PACE_CACHE = _json.load(f)
            _TEAM_PACE_MTIME = mt
    except (OSError, ValueError):
        pass
    return _TEAM_PACE_CACHE or {}


def _compute_pace(away_abbr: str, home_abbr: str) -> tuple[Optional[float], Optional[float]]:
    """Return (pace_away, pace_home) using real team stats.

    Priority:
    1. data/cache/team_pace.json  (manual override cache)
    2. data/nba/team_stats_{season}.json  (NBA API advanced stats — has real PACE)
    3. data/games/*.parquet  (tracking-derived pace)
    4. NBA season average (99.5) — only if all above fail
    """
    pace_map = _load_team_pace()
    if pace_map:
        away = pace_map.get(away_abbr) or pace_map.get(away_abbr.lower())
        home = pace_map.get(home_abbr) or pace_map.get(home_abbr.lower())
        if away or home:
            return (float(away) if away else _NBA_AVG_PACE,
                    float(home) if home else _NBA_AVG_PACE)

    # Tier 2: real per-team PACE from NBA advanced team stats cache
    generic = {"AWAY", "HOME", "away", "home"}
    if away_abbr not in generic and home_abbr not in generic:
        try:
            ht = _team_stats_for(home_abbr)
            at = _team_stats_for(away_abbr)
            h_pace = ht.get("pace")
            a_pace = at.get("pace")
            if h_pace and h_pace != _NBA_AVG_PACE:
                return (round(float(a_pace or _NBA_AVG_PACE), 1),
                        round(float(h_pace), 1))
        except Exception:
            pass

    # Tier 3: scan recent games parquet for pace columns
    try:
        import glob as _glob
        games_dir = _ROOT / "data" / "games"
        if games_dir.exists():
            parquets = sorted(_glob.glob(str(games_dir / "*.parquet")))[-5:]
            if parquets:
                import importlib
                pd = importlib.import_module("pandas")
                dfs = []
                for p in parquets:
                    try:
                        dfs.append(pd.read_parquet(p, columns=["team_abbr", "pace"]))
                    except Exception:
                        pass
                if dfs:
                    df = pd.concat(dfs, ignore_index=True)
                    pace_by_team = df.groupby("team_abbr")["pace"].mean().to_dict()
                    away_p = pace_by_team.get(away_abbr, _NBA_AVG_PACE)
                    home_p = pace_by_team.get(home_abbr, _NBA_AVG_PACE)
                    return (round(away_p, 1), round(home_p, 1))
    except Exception:
        pass
    # Return NBA average as sensible default
    return (_NBA_AVG_PACE, _NBA_AVG_PACE)


def _get_win_prob_model():
    """Load and cache the win-prob model (CalibratedClassifierCV from win_prob_v3.pkl).

    Returns (clf, feature_cols) tuple or (None, None) on failure.
    Module-level cache avoids re-loading the ~5MB pickle on every request.
    Thread lock (double-checked) prevents thundering-herd on cold-start: without
    it, N concurrent first-requests would each start a ~2s pickle.load in parallel,
    holding the GIL during deserialization and causing 77s page loads on Railway.
    """
    global _WIN_PROB_MODEL_CACHE, _WIN_PROB_MODEL_LOADED
    if _WIN_PROB_MODEL_LOADED:  # fast path: no lock needed once loaded
        return _WIN_PROB_MODEL_CACHE
    with _WIN_PROB_MODEL_LOCK:  # only one thread loads; others wait then hit fast path
        if _WIN_PROB_MODEL_LOADED:  # re-check under lock (double-checked locking)
            return _WIN_PROB_MODEL_CACHE
        # Perform the load under the lock so concurrent cold requests don't all
        # start a ~2s pickle.load simultaneously.
        try:
            import pickle as _pickle
            import warnings as _warn
            model_path = _ROOT / "data" / "models" / "win_prob_v3.pkl"
            if model_path.exists():
                with _warn.catch_warnings():
                    _warn.simplefilter("ignore")
                    with model_path.open("rb") as f:
                        data = _pickle.load(f)
                clf = data.get("model")
                cols = data.get("feature_cols", [])
                if clf is not None and cols:
                    _WIN_PROB_MODEL_CACHE = (clf, cols)
        except Exception:
            pass
        _WIN_PROB_MODEL_LOADED = True  # mark done (even on failure — don't retry)
    return _WIN_PROB_MODEL_CACHE


def _pregame_wp_from_projection(date: str, away_abbr: str, home_abbr: str
                                 ) -> Optional[float]:
    """Return P(home wins) derived from the projected box score's team totals.

    Used in place of the buggy win_prob_v3.pkl model (which has a documented
    polarity bug — vault/Models/Polarity Bug Audit 2026-05-27.md). This stays
    consistent with whatever projection the user sees in the box score.

    Calibration: margin shrunk ×0.30 (known role-player under-projection bias),
    Normal CDF with sigma=14 (playoff) or 13 (regular), clamped to [0.35, 0.65]
    since no honest model can be more confident than that on an NBA matchup
    without market data.
    """
    if not (away_abbr and home_abbr):
        return None
    try:
        box = _build_box_score(date, away_abbr, home_abbr)
        away_t = box.get("away") or {}; home_t = box.get("home") or {}
        proj_a = (away_t.get("mean_totals") or {}).get("pts")
        proj_h = (home_t.get("mean_totals") or {}).get("pts")
        if proj_a is None or proj_h is None:
            return None
        from math import erf, sqrt  # noqa: PLC0415
        margin = (float(proj_h) - float(proj_a)) * 0.30
        margin_sigma = 14.0 if _is_playoff_date(date) else 13.0
        z = margin / margin_sigma
        p_home = 0.5 * (1.0 + erf(z / sqrt(2.0)))
        return max(0.35, min(0.65, p_home))
    except Exception:
        return None


def _abbr_from_team_name(name: str) -> "str | None":
    n = (name or "").lower()
    for frag, ab in _TEAM_ABBREVS.items():
        if frag in n:
            return ab
    return None


def _market_home_wp(date: str, away_abbr: str, home_abbr: str) -> "float | None":
    """De-vig P(home wins) from the sharpest mainline moneyline available for the
    date (data/lines/<date>_*mainline*.csv). The market already prices injuries,
    rest and home court — for GAME outcome we defer to it rather than the raw
    box-total projection (which lacks home-court advantage)."""
    import csv as _csv  # noqa: PLC0415
    if not (away_abbr and home_abbr):
        return None
    best = None  # (captured_at, p_home)
    for fp in (_ROOT / "data" / "lines").glob(f"{date}_*mainline*.csv"):
        try:
            rows = list(_csv.DictReader(fp.open(encoding="utf-8")))
        except Exception:
            continue
        ml: dict = {}  # game_id -> {'home':(cap,price), 'away':(cap,price), 'hn','an'}
        for r in rows:
            if (r.get("market_type") or "").lower() != "moneyline":
                continue
            gid = r.get("game_id") or ""
            cap = r.get("captured_at") or ""
            side = (r.get("side") or "").lower()
            try:
                price = int(float(r.get("price")))
            except (TypeError, ValueError):
                continue
            e = ml.setdefault(gid, {"home": ("", None), "away": ("", None),
                                    "hn": r.get("home_team"), "an": r.get("away_team")})
            if side in ("home", "away") and cap >= e[side][0]:
                e[side] = (cap, price)
        for e in ml.values():
            hp, ap = e["home"][1], e["away"][1]
            if hp is None or ap is None:
                continue
            if (_abbr_from_team_name(e["hn"]) != home_abbr
                    or _abbr_from_team_name(e["an"]) != away_abbr):
                continue

            def _imp(o):
                return (100.0 / (o + 100.0)) if o > 0 else (abs(o) / (abs(o) + 100.0))
            ih, ia = _imp(hp), _imp(ap)
            ph = ih / (ih + ia) if (ih + ia) else None
            cap = max(e["home"][0], e["away"][0])
            if ph is not None and (best is None or cap > best[0]):
                best = (cap, ph)
    return best[1] if best else None


def _live_wp_continuous(live_overlay: dict, pregame_home_wp,
                        proj_home=None, proj_away=None) -> "float | None":
    """Always-updating live P(home wins), REFLECTIVE OF THE PROJECTED FINAL SCORE.

    When the box's projected final team totals are available (proj_home/away —
    which already fold in pace + the pregame prior + who's playing well), the win
    prob is driven by the PROJECTED FINAL MARGIN, so it tracks "what the final
    score will be," not just the current margin. Falls back to current margin +
    market-prorated edge when projections are absent. Sigma shrinks as the clock
    runs out (a projected lead late is far more certain than the same lead early).

    W-032 (CV_WP_RECONCILED_CALIB): when ON, recalibrates two parameters whose
    values were fitted on the W-034 reliability/ECE harness (220-game walk-forward
    pool, 3 folds):
      - sigma: 14.5 → 12.5  (tighter; matches the k=0.40 logistic baseline that
        achieves Brier=0.1683 vs 0.177 for the wider sigma; derived by equating
        the Normal-CDF form to baseline_winprob's sigmoid parametrisation).
      - w_market cap: 0.80 → 1.00  (full linear trust in the pregame market at
        tip, decaying to 0 at the buzzer; the W-034 Q1 reliability table shows the
        0.80 cap leaves predictions ~7pp over-confident in the 0.3-0.4 bin because
        the projection dominates too early; trusting the market 100% at tip shrinks
        the early-game ECE from 0.069 → ~0.055).
    With CV_WP_RECONCILED_CALIB=OFF the output is byte-identical to baseline."""
    import os as _os_lwp  # noqa: PLC0415
    from math import erf, sqrt  # noqa: PLC0415

    # W-032: read calibration flag ONCE at entry (default-OFF → baseline params).
    _calib_on = _os_lwp.environ.get(
        "CV_WP_RECONCILED_CALIB", "0"
    ).strip().lower() not in ("", "0", "false", "off")

    try:
        period = int(live_overlay.get("period") or 1)
    except (TypeError, ValueError):
        period = 1
    clock = str(live_overlay.get("clock") or "")
    try:
        mm, ss = clock.split(":")
        crem = int(mm) + float(ss) / 60.0
    except Exception:
        crem = 0.0
    rem = max(0.0, (4 - period) * 12.0 + crem) if period <= 4 else max(0.0, crem)
    if "FINAL" in str(live_overlay.get("game_status") or "").upper():
        rem = 0.0

    if proj_home is not None and proj_away is not None:
        # Projected FINAL margin — already includes pace + pregame + form.
        try:
            proj_margin = float(proj_home) - float(proj_away)
        except (TypeError, ValueError):
            proj_margin = None
    else:
        proj_margin = None
    if proj_margin is None:
        try:
            margin = int(live_overlay.get("home_score") or 0) - int(live_overlay.get("away_score") or 0)
        except (TypeError, ValueError):
            return None
        pg = min(0.97, max(0.03, float(pregame_home_wp if pregame_home_wp is not None else 0.5)))
        proj_margin = margin + (pg - 0.5) * 30.0 * (rem / 48.0)
    # Sigma = uncertainty of the PROJECTED FINAL margin. With most of the game
    # left this is wide (the projection is a guess); it tightens as minutes
    # accumulate. NBA final-margin std is ~13-14 at tip; a mid-game projection
    # still carries real error, so keep sigma generous to avoid over-confident
    # numbers from a thin projected lead.
    # W-032: calibrated sigma=12.5 (tighter, Brier-optimal from W-034 harness).
    if _calib_on:
        sigma = max(2.5, 12.5 * sqrt(max(rem, 0.4) / 48.0))
    else:
        sigma = max(2.5, 14.5 * sqrt(max(rem, 0.4) / 48.0))
    p_proj = 0.5 * (1.0 + erf((proj_margin / sigma) / sqrt(2.0)))
    # MARKET ANCHOR (decays with time left). Early/mid-game the projected margin
    # alone is far too confident for a close score — a tied game at the half must
    # sit near the pregame market price, not 35/65. So blend the projection's
    # win prob toward the pregame market wp, weighting the market by the fraction
    # of game remaining (lots left -> trust the market; little left -> the
    # near-final projected score dominates). This is the standard live-WP shape
    # and keeps the number realistic without ignoring the projection.
    # W-032: calibrated w_market cap=1.00 (full market trust at tip reduces
    # early-game over-confidence seen in W-034 Q1 reliability table).
    if pregame_home_wp is not None:
        pg = min(0.97, max(0.03, float(pregame_home_wp)))
        if _calib_on:
            w_market = max(0.0, min(1.00, rem / 48.0))
        else:
            w_market = max(0.0, min(0.80, rem / 48.0))
        p = w_market * pg + (1.0 - w_market) * p_proj
    else:
        p = p_proj
    return min(0.995, max(0.005, p))


def _pregame_home_wp(date: str, away_abbr: str, home_abbr: str):
    """Best pregame P(home wins) + its source: MARKET de-vig moneyline when
    available (sharpest, includes home court), else the box-projection proxy."""
    mk = _market_home_wp(date, away_abbr, home_abbr)
    if mk is not None:
        return float(mk), "market_devig"
    return _pregame_wp_from_projection(date, away_abbr, home_abbr), "projected_margin_shrunk"


def _compute_win_prob(game_id: str, props: list,
                      away_abbr: str = "", home_abbr: str = "") -> Optional[float]:
    """Return away-team win probability [0,1].

    Priority:
    1. win_prob_v3.pkl (CalibratedClassifierCV, 156 features) built from cached
       team_stats — fills real values for all key features, zeros for rare extras.
       Returns None if teams are unknown (generic AWAY/HOME placeholders).
    2. Moneyline no-vig proxy from props books (unlikely in player-prop data).
    3. None — template hides the section.
    """
    import numpy as _np

    # Attempt 1: model prediction from cached team stats
    generic = {"AWAY", "HOME", "away", "home", ""}
    if away_abbr not in generic and home_abbr not in generic:
        model_info = _get_win_prob_model()
        if model_info is not None:
            try:
                clf, feature_cols = model_info
                ht = _team_stats_for(home_abbr)
                at = _team_stats_for(away_abbr)

                # Build feature dict: real values for the ~25 high-importance
                # stats we have, sensible defaults for the rest.
                feats: dict = {c: 0.0 for c in feature_cols}
                feats.update({
                    "home_off_rtg":        ht.get("off_rtg", 112.0),
                    "home_def_rtg":        ht.get("def_rtg", 112.0),
                    "home_net_rtg":        ht.get("net_rtg", 0.0),
                    "home_pace":           ht.get("pace", _NBA_AVG_PACE),
                    "home_efg_pct":        ht.get("efg_pct", 0.53),
                    "home_ts_pct":         ht.get("ts_pct", 0.57),
                    "home_tov_pct":        ht.get("tov_pct", 13.0),
                    "home_rest_days":      2.0,
                    "home_back_to_back":   0.0,
                    "home_last5_wins":     round(ht.get("win_pct", 0.5) * 5, 1),
                    "home_season_win_pct": ht.get("win_pct", 0.5),
                    "away_off_rtg":        at.get("off_rtg", 112.0),
                    "away_def_rtg":        at.get("def_rtg", 112.0),
                    "away_net_rtg":        at.get("net_rtg", 0.0),
                    "away_pace":           at.get("pace", _NBA_AVG_PACE),
                    "away_efg_pct":        at.get("efg_pct", 0.53),
                    "away_ts_pct":         at.get("ts_pct", 0.57),
                    "away_tov_pct":        at.get("tov_pct", 13.0),
                    "away_rest_days":      2.0,
                    "away_back_to_back":   0.0,
                    "away_travel_miles":   1000.0,
                    "away_last5_wins":     round(at.get("win_pct", 0.5) * 5, 1),
                    "away_season_win_pct": at.get("win_pct", 0.5),
                    "net_rtg_diff":        round(ht.get("net_rtg", 0.0) - at.get("net_rtg", 0.0), 2),
                    "pace_diff":           round(ht.get("pace", _NBA_AVG_PACE) - at.get("pace", _NBA_AVG_PACE), 2),
                    "home_advantage":      1.0,
                    # L10 rolling — use season stats as proxy when not cached
                    "home_off_rtg_L10":    ht.get("off_rtg", 112.0),
                    "home_def_rtg_L10":    ht.get("def_rtg", 112.0),
                    "home_net_rtg_L10":    ht.get("net_rtg", 0.0),
                    "away_off_rtg_L10":    at.get("off_rtg", 112.0),
                    "away_def_rtg_L10":    at.get("def_rtg", 112.0),
                    "away_net_rtg_L10":    at.get("net_rtg", 0.0),
                    "home_efg_L10":        ht.get("efg_pct", 0.50),
                    "away_efg_L10":        at.get("efg_pct", 0.50),
                    "home_tov_pct_L10":    ht.get("tov_pct", 13.0) / 100,
                    "away_tov_pct_L10":    at.get("tov_pct", 13.0) / 100,
                    "home_oreb_pct_L10":   ht.get("reb_pct", 0.5) * 0.5,
                    "away_oreb_pct_L10":   at.get("reb_pct", 0.5) * 0.5,
                    # Ref defaults (league average)
                    "ref_avg_fouls":       42.0,
                    "ref_home_win_pct":    0.5,
                    "ref_fta_tendency":    0.0,
                    "ref_crew_known":      0.0,
                    # ELO defaults
                    "home_elo":            1500.0,
                    "away_elo":            1500.0,
                    "elo_differential":    0.0,
                    "home_elo_v2":         1500.0,
                    "away_elo_v2":         1500.0,
                    "elo_diff_v2":         0.0,
                    "v3_home_elo_v2":      1500.0,
                    "v3_away_elo_v2":      1500.0,
                    "v3_elo_diff_v2":      0.0,
                })

                X = _np.array([[feats.get(c, 0.0) for c in feature_cols]], dtype=_np.float32)
                prob_home = float(clf.predict_proba(X)[0][1])
                prob_away = round(1.0 - prob_home, 3)
                if 0.05 <= prob_away <= 0.95:
                    return prob_away
            except Exception:
                pass

    # Attempt 2: no-vig moneyline from any book in props
    try:
        for p in props:
            for b in p.get("books", []):
                ml_o = b.get("ml_over") or b.get("moneyline_home")
                ml_u = b.get("ml_under") or b.get("moneyline_away")
                if ml_o and ml_u:
                    def _imp(american: int) -> float:
                        if american > 0:
                            return 100 / (american + 100)
                        return -american / (-american + 100)
                    p_home = _imp(int(ml_o))
                    p_away = _imp(int(ml_u))
                    total = p_home + p_away
                    if total > 0:
                        return round(p_away / total, 3)
    except Exception:
        pass

    return None


def _build_model_total(game_props: list, home_abbr: str, away_abbr: str) -> tuple:
    """Return (model_total, model_spread) from PTS projections in game_props.

    Uses ALL props (not just recommended bets) so the total reflects the full
    roster, not only edge bets.  Deduplicates to one projection per player
    (highest model_projection wins when the same player has multiple PTS lines).
    Team split uses the model_team field attached by overlay_predictions from
    the predictions parquet (parquet carries a 'team' column).  Falls back to
    splitting the sorted PTS list in half when no team labels are present.
    Returns (None, None) when no PTS projections exist.
    model_spread = home_pts - away_pts (positive = home favored).
    """
    import logging as _log
    _logger = _log.getLogger(__name__)
    try:
        # Step 1: collect best PTS projection per player (deduplicate multiple lines)
        best_by_player: dict[str, dict] = {}
        for p in game_props:
            if (p.get("stat") or "").lower() != "pts":
                continue
            proj = p.get("model_projection")
            if proj is None:
                continue
            player = p.get("player") or ""
            existing = best_by_player.get(player)
            if existing is None or proj > (existing.get("model_projection") or 0):
                best_by_player[player] = p

        if not best_by_player:
            return (None, None)

        # Step 2: split by team using model_team (set by overlay from parquet)
        home_pts = 0.0
        away_pts = 0.0
        untagged: list[float] = []
        home_u = home_abbr.upper()
        away_u = away_abbr.upper()
        generic = {"AWAY", "HOME", "", "UNKNOWN"}

        for p in best_by_player.values():
            proj = float(p.get("model_projection") or 0)
            mt = (p.get("model_team") or "").upper()
            if mt and mt not in generic:
                if mt == home_u:
                    home_pts += proj
                elif mt == away_u:
                    away_pts += proj
                else:
                    untagged.append(proj)
            else:
                untagged.append(proj)

        # If team labels resolved both sides, distribute any untagged evenly
        if home_pts or away_pts:
            if untagged:
                half = sum(untagged) / 2.0
                home_pts += half
                away_pts += half
        else:
            # Fallback: no team labels at all — split sorted list in half
            sorted_pts = sorted(best_by_player.values(),
                                key=lambda x: x.get("player") or "")
            all_proj = [float(p.get("model_projection") or 0) for p in sorted_pts]
            half = max(len(all_proj) // 2, 1)
            away_pts = sum(all_proj[:half])
            home_pts = sum(all_proj[half:])

        total = round(home_pts + away_pts, 1)
        spread = round(home_pts - away_pts, 1)

        if total < 150 or total > 280:
            _logger.warning(
                "_build_model_total: suspicious total=%.1f for %s@%s "
                "(home=%.1f away=%.1f n_players=%d)",
                total, away_abbr, home_abbr, home_pts, away_pts, len(best_by_player),
            )

        if home_pts or away_pts:
            return (total, spread)
    except Exception:
        pass
    return (None, None)


def _build_key_players(game_props: list) -> list:
    """Top-3 players per team (6 total) by PTS model projection descending.

    Falls back to prop count when no PTS projections are available (rare case
    where predictions parquet was not generated).  Returns at most 6 names
    (top-3 away + top-3 home) ordered by projection desc.
    """
    # Best PTS projection per player
    pts_proj: dict[str, float] = {}
    pts_team: dict[str, str] = {}
    for p in game_props:
        if (p.get("stat") or "").lower() != "pts":
            continue
        proj = p.get("model_projection")
        if proj is None:
            continue
        player = p.get("player") or ""
        if not player:
            continue
        if player not in pts_proj or proj > pts_proj[player]:
            pts_proj[player] = float(proj)
            mt = (p.get("model_team") or "").upper()
            if mt:
                pts_team[player] = mt

    if pts_proj:
        # Group into two teams, pick top-3 each, return sorted by projection desc
        teams: dict[str, list] = {}
        untagged: list[tuple[float, str]] = []
        for player, proj in pts_proj.items():
            team = pts_team.get(player, "")
            if team:
                teams.setdefault(team, []).append((proj, player))
            else:
                untagged.append((proj, player))

        result = []
        # Sort each team's players by projection desc, take top 3
        for team_players in teams.values():
            team_players.sort(reverse=True)
            result.extend(name for _, name in team_players[:3])
        # Append untagged (sorted desc) filling up to 6 total
        untagged.sort(reverse=True)
        for _, name in untagged:
            if len(result) >= 6:
                break
            if name not in result:
                result.append(name)
        return result[:6]

    # Fallback: no PTS projections — use prop count as proxy
    counts: dict[str, int] = {}
    for p in game_props:
        player = p.get("player") or ""
        if player:
            counts[player] = counts.get(player, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:6]]


def _build_game_detail(game_id: str, date: str) -> dict:
    """Build game-detail page data for one game_id. Cached 60s per (game_id, date).

    Bug 1 fix — game_id alias resolution:
    DK, PointsBet, KAMBI, and oddsapi each assign different IDs to the same
    NBA matchup. We resolve the incoming game_id to its canonical set of aliases
    via games_lookup.json, then filter props by matching ANY of those IDs.
    This means /game/34201426 and /game/2734554 (both OKC@SAS) return the same
    data — which is the correct behavior: same matchup, same page.
    The URL /game/<any_alias_id> is treated as equivalent to the canonical ID.
    """
    cache_key = ("game_detail", game_id, date)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < 60:
        return entry[1]

    from api._courtvision_odds import consolidate, resolve_game_id
    from api._predictions_overlay import overlay_predictions

    # Resolve the incoming ID to its full alias set (may be a singleton when
    # the ID is not in games_lookup.json).
    alias_info = resolve_game_id(game_id)
    canonical_ids: frozenset[str] = alias_info.get("canonical_ids", frozenset([game_id]))

    props_all: list[dict] = []
    raw_props: list[dict] = []
    try:
        raw_props = consolidate(date)
        # Filter by ANY canonical alias — this collapses DK/PB/KAMBI IDs for
        # the same matchup into one unified props list.
        game_raw = [p for p in raw_props if p.get("game_id") in canonical_ids]
        if not game_raw:
            # Last-resort fallback: show all props (old behaviour).
            game_raw = raw_props
        props_all = overlay_predictions(date, game_raw)
    except Exception:
        raw_props = []
        props_all = []

    # Re-filter after overlay (overlay may add props not in game_raw).
    game_props = [p for p in props_all if p.get("game_id") in canonical_ids]
    if not game_props:
        game_props = props_all  # show all props if nothing matched

    # Start time from first matching prop
    start_time = ""
    for p in (game_props or props_all or raw_props):
        if p.get("game_id") in canonical_ids and p.get("start_time"):
            start_time = p["start_time"]
            break
    if not start_time and (game_props or props_all):
        cands = [p.get("start_time") or "" for p in (game_props or props_all)]
        start_time = next((s for s in cands if s), "")

    status = _game_status(start_time)

    # Recommended bets: has rec_side + edge_pct, sorted desc
    rec_bets_raw = [p for p in game_props if p.get("rec_side") and p.get("edge_pct") is not None]
    rec_bets_raw.sort(key=lambda p: -(p.get("edge_pct") or 0))

    rec_bets = []
    for p in rec_bets_raw[:15]:
        side = p.get("rec_side", "OVER")
        best_book = ""
        best_odds = None
        deeplink_web = ""
        for b in p.get("books", []):
            price = b.get("over_price") if side == "OVER" else b.get("under_price")
            if price is not None and (best_odds is None or price > best_odds):
                best_odds = price
                best_book = b.get("display") or b.get("book") or ""
                deeplink_web = (b.get("deeplink_over_web") if side == "OVER"
                                else b.get("deeplink_under_web")) or ""
        rec_bets.append({
            "player": p["player"],
            "stat": p["stat"],
            "line": p["line"],
            "rec_side": side,
            "edge_pct": p.get("edge_pct"),
            "kelly_pct": p.get("kelly_pct"),
            "best_odds": best_odds,
            "best_book": best_book,
            "deeplink_web": deeplink_web,
        })

    away_abbr, home_abbr = _guess_teams_from_game_id(game_id)

    # ── Intelligence: win probability + pace ──────────────────────────
    # Use projection-derived WP (consistent with box score, no polarity bug)
    # rather than the legacy team-level model.
    p_home_pre, _ = _pregame_home_wp(date, away_abbr, home_abbr)
    win_prob_away = (1.0 - p_home_pre) if p_home_pre is not None else None
    pace_away, pace_home = _compute_pace(away_abbr, home_abbr)

    # ── Key matchup hints: top-2 props by edge ────────────────────────
    key_bets = []
    for p in rec_bets_raw[:2]:
        side = p.get("rec_side", "OVER")
        key_bets.append({
            "player": p["player"],
            "stat": p["stat"].upper(),
            "line": p["line"],
            "rec_side": side,
            "edge_pct": p.get("edge_pct"),
        })

    # Pull off/def ratings for Intelligence card display
    _generic = {"AWAY", "HOME", "away", "home"}
    _ht_stats = _team_stats_for(home_abbr) if home_abbr not in _generic else {}
    _at_stats = _team_stats_for(away_abbr) if away_abbr not in _generic else {}
    off_rtg_home = round(_ht_stats["off_rtg"], 1) if _ht_stats.get("off_rtg") else None
    def_rtg_home = round(_ht_stats["def_rtg"], 1) if _ht_stats.get("def_rtg") else None
    off_rtg_away = round(_at_stats["off_rtg"], 1) if _at_stats.get("off_rtg") else None
    def_rtg_away = round(_at_stats["def_rtg"], 1) if _at_stats.get("def_rtg") else None
    # Determine pace_source label for transparency
    _pace_from_nba_stats = (
        pace_away != _NBA_AVG_PACE or pace_home != _NBA_AVG_PACE
    ) and away_abbr not in _generic and home_abbr not in _generic
    pace_source = "season_avg" if _pace_from_nba_stats else "default"

    _mt, _ms = _build_model_total(game_props, home_abbr, away_abbr)
    game_info = {
        "game_id": game_id,
        "start_time_iso": start_time,
        "tipoff_display": _fmt_tipoff(start_time),
        "status": status,
        "away_team": away_abbr,
        "home_team": home_abbr,
        "matchup": f"{away_abbr} @ {home_abbr}",
        "n_props": len(game_props),
        "n_players": len({p["player"] for p in game_props}),
        "score_away": None,
        "score_home": None,
        "clock": None,
        "win_prob_away": win_prob_away,
        "win_prob_home": round(1.0 - win_prob_away, 3) if win_prob_away is not None else None,
        "model_total": _mt,
        "model_spread": _ms,
        "key_players": _build_key_players(game_props),
        "injury_status": [],  # no live feed; source: api/_courtvision_injuries.py TBD
        "pace_away": pace_away,
        "pace_home": pace_home,
        "pace_source": pace_source,
        "off_rtg_away": off_rtg_away,
        "def_rtg_away": def_rtg_away,
        "off_rtg_home": off_rtg_home,
        "def_rtg_home": def_rtg_home,
        "injury_notes": "",
        "key_bets": key_bets,
    }

    result = {
        "game": game_info,
        "rec_bets": rec_bets,
        "has_predictions": bool(rec_bets_raw),
        "slate_date": date,
    }
    _CACHE[cache_key] = (time.time(), result)
    return result


# ── routes ───────────────────────────────────────────────────────────────────

# Short-TTL cache for the home page's default date.
# `_current_or_next_game_day()` calls `_live_game_date()`, which globs the
# entire data/live/ directory (~30K files) + reads JSON on every call — ~130ms
# UNCACHED. Since `_build_home_data` itself is fully cached, that glob was the
# ENTIRE warm cost of `/` and `/api/home.json`. The default date only changes
# when a game tips off or goes final, so a 5s memo (matching the live-dir index
# TTL) is plenty fresh for game night while removing the per-request glob.
_HOME_DEFAULT_DATE_CACHE: tuple[float, Optional[str]] = (0.0, None)
_HOME_DEFAULT_DATE_TTL = 5.0  # seconds


def _home_default_date() -> Optional[str]:
    """Cached wrapper around `_current_or_next_game_day()` for the home routes.

    Eliminates the ~130ms data/live/ glob in `_live_game_date()` on warm
    requests. Returns the exact same value `_current_or_next_game_day()` would,
    refreshed at most every 5s."""
    global _HOME_DEFAULT_DATE_CACHE
    _ts, _val = _HOME_DEFAULT_DATE_CACHE
    if _val is not None and time.time() - _ts < _HOME_DEFAULT_DATE_TTL:
        return _val
    _val = _current_or_next_game_day()
    _HOME_DEFAULT_DATE_CACHE = (time.time(), _val)
    return _val


@router.get("/", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def home(request: Request, date: str = Query(default=None)):
    """Root = the tonight games hub: a clean list of games ONLY. Click a game ->
    /cv (the full per-game page: intelligence + box score + bet cards). The old
    /tonight slate remains reachable but is no longer the landing.
    """
    if not date:
        date = _home_default_date()
    data = _build_home_data(date)
    return _TEMPLATES.TemplateResponse("home.html", {"request": request, **data})


@router.get("/api/home.json", tags=["courtvision"])
def api_home(date: Optional[str] = Query(default=None)):
    """Same payload as the home HTML page but as JSON — used by the WS live-tick
    to refresh edge cards without a full page reload."""
    if not date:
        date = _home_default_date()
    return JSONResponse(_build_home_data(date))


@router.get("/game/{game_id}", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def game_detail(game_id: str, request: Request, date: str = Query(default=None)):
    """Per-game intelligence report + ranked bets + all props."""
    if not date:
        date = _current_or_next_game_day()
    data = _build_game_detail(game_id, date)
    return _TEMPLATES.TemplateResponse("game_detail.html", {"request": request, **data})


@router.get("/api/game/{game_id}.json", tags=["courtvision"])
def api_game_detail(game_id: str, date: Optional[str] = Query(default=None)):
    """Same data as /game/{game_id} HTML page but as JSON."""
    if not date:
        date = _current_or_next_game_day()
    return JSONResponse(_build_game_detail(game_id, date))


@router.get("/tonight", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def tonight(request: Request, date: str = Query(default=None),
            side: str = Query("ALL"), min_ev: float = Query(-999.0),
            game_id: str = Query(default=""), books: str = Query(default="")):
    """Tonight's slate. Optional ?game_id= filter shows only one matchup's bets
    (this is what the homepage game cards link to — gives a per-game view using
    the same rich bet-card layout). Optional ?books=dk,fanduel re-prices the
    slate to those sportsbooks (best price among them) and re-ranks — the
    casual 'pick my book, show its best bets' flow."""
    if not date:
        date = _current_or_next_game_day()
    slate = _build_slate(date)
    _book_sel = [b for b in (books or "").split(",") if b.strip()]
    if _book_sel:
        slate = _reprice_slate_to_books(slate, _book_sel)
    side_u = (side or "ALL").upper()
    gid_filter = (game_id or "").strip()
    needs_filter = (side_u in ("OVER", "UNDER")) or (min_ev > -999.0) or bool(gid_filter)
    matchup_label = ""
    # Resolve the URL game_id (often a sportsbook id like KAMBI) to the canonical
    # set of NBA game_ids AND the matchup's team abbrs. Some bet feeds tag the
    # official NBA game_id that isn't in the alias map, so we accept either an id
    # match or a (team, opp) abbr match.
    canonical_ids: frozenset[str] = frozenset()
    alias_pair: frozenset[str] = frozenset()
    alias_away = ""
    alias_home = ""
    if gid_filter:
        from api._courtvision_odds import resolve_game_id
        alias_info = resolve_game_id(gid_filter)
        canonical_ids = alias_info.get("canonical_ids", frozenset([gid_filter]))
        alias_away = alias_info.get("away_abbr") or ""
        alias_home = alias_info.get("home_abbr") or ""
        if alias_away and alias_home:
            alias_pair = frozenset([alias_away.upper(), alias_home.upper()])

    def _gid_matches(b):
        if not gid_filter:
            return True
        if str(b.get("game_id", "")) in canonical_ids:
            return True
        if alias_pair:
            t = (b.get("team") or "").upper()
            o = (b.get("opp") or "").upper()
            if t in alias_pair and o in alias_pair:
                return True
        return False

    if needs_filter:
        bets = [b for b in slate["bets"]
                if (side_u == "ALL" or b["side"] == side_u)
                and (b.get("ev_pct") is None or b["ev_pct"] >= min_ev)
                and _gid_matches(b)]
        # If filtered to a specific game, derive matchup label from any bet
        if gid_filter and bets:
            sample = bets[0]
            home_or_away_indicator = "@" if sample.get("venue") == "away" else "vs"
            matchup_label = f"{sample.get('team','')} {home_or_away_indicator} {sample.get('opp','')}"
        slate = {**slate, "bets": bets}
    # When filtered to a single game AND a live snapshot exists, re-grade
    # the bets using live_engine q50s (so the cards reflect what the model
    # would project given current game state, not the pregame call).
    live_regrade_count = 0
    if gid_filter and slate.get("bets"):
        snap_for_game = None
        canon_for_game = list(canonical_ids) + [gid_filter]
        live_dir_chk = _ROOT / "data" / "live"
        if live_dir_chk.exists():
            for gid_chk in canon_for_game:
                m = _epoch_snaps(live_dir_chk, gid_chk)
                if m:
                    try:
                        import json as _json2  # noqa: PLC0415
                        snap_for_game = _json2.loads(m[-1].read_text(encoding="utf-8"))
                        break
                    except Exception:
                        continue
        if snap_for_game and snap_for_game.get("period"):
            try:
                from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
                proj_rows = project_from_snapshot(snap_for_game) or []
                live_map: dict[tuple, float] = {}
                for r in proj_rows:
                    nm = (r.get("name") or "").lower()
                    st = (r.get("stat") or "").lower()
                    pf = r.get("projected_final")
                    if nm and st and pf is not None:
                        try:
                            live_map[(nm, st)] = float(pf)
                        except (TypeError, ValueError):
                            continue
                player_minutes = _shrink_player_minutes_from_snapshot(snap_for_game)
                if live_map:
                    import copy as _copy  # noqa: PLC0415
                    sig_table = _stat_sigma_for_date(date)
                    # deepcopy so the live regrade never mutates the bet dicts
                    # held by the cached slate envelope (shared by reference).
                    new_bets = [_copy.deepcopy(b) for b in slate["bets"]]
                    for b in new_bets:
                        key = ((b.get("player_name") or "").lower(),
                               (b.get("prop_stat") or "").lower())
                        if key in live_map:
                            mp = player_minutes.get(key[0], 0.0)
                            w_live = _live_shrink_weight(mp)
                            live_raw = live_map[key]
                            pregame_q50 = float(b.get("q50") or live_raw)
                            shrunk = w_live * live_raw + (1.0 - w_live) * pregame_q50
                            _regrade_bet_with_live_q50(b, shrunk, sig_table)
                            live_regrade_count += 1
                    new_bets.sort(
                        key=lambda b: (b.get("ev_pct") is None,
                                       -(b.get("ev_pct") or 0.0))
                    )
                    slate = {**slate, "bets": new_bets}
            except Exception as exc:
                import logging as _lg2  # noqa: PLC0415
                _lg2.getLogger(__name__).warning(
                    "tonight live regrade failed: %s", exc)

    # When filtered to a single game, build a pregame projected box score
    # for the matchup. JS polls /api/box_score for live updates.
    box_score = None
    if gid_filter:
        away_a = alias_away
        home_a = alias_home
        # Alias lookup may be empty for some book ids — fall back to deriving
        # away/home from the bets themselves (which carry team + opp + venue).
        if not (away_a and home_a) and slate.get("bets"):
            sample = slate["bets"][0]
            t = (sample.get("team") or "").upper()
            o = (sample.get("opp") or "").upper()
            if t and o:
                if sample.get("venue") == "home":
                    home_a, away_a = t, o
                else:
                    away_a, home_a = t, o
        if away_a and home_a:
            box_score = _build_box_score(date, away_a, home_a, game_id=gid_filter)
            # Merge in any players from the live snapshot who weren't on the
            # pregame roster (mid-game call-ups). Otherwise they only appear
            # via /api/box_score (JSON) but not in the server-rendered
            # tonight.html — the JS poller only updates existing rows.
            try:
                import json as _tjs  # noqa: PLC0415
                live_dir_t = _ROOT / "data" / "live"
                live_overlay_t = None
                for _gid in (list(canonical_ids) + [gid_filter]):
                    matches_t = _epoch_snaps(live_dir_t, _gid)
                    if matches_t:
                        live_overlay_t = _tjs.loads(matches_t[-1].read_text(encoding="utf-8"))
                        break
                if live_overlay_t and box_score:
                    snap_players = live_overlay_t.get("players") or []
                    if isinstance(snap_players, list):
                        for team_key in ("away", "home"):
                            td = box_score.get(team_key) or {}
                            team_abbr_t = (td.get("abbr") or "").upper()
                            roster = td.get("players") or []
                            existing_ids_t = {str(r.get("player_id"))
                                              for r in roster
                                              if r.get("player_id") is not None}
                            existing_nm_t = {(r.get("player_name") or "").lower()
                                             for r in roster
                                             if r.get("player_name")}
                            for lp in snap_players:
                                if not isinstance(lp, dict):
                                    continue
                                if (lp.get("team") or "").upper() != team_abbr_t:
                                    continue
                                lp_id = str(lp.get("player_id") or "")
                                lp_nm = (lp.get("name") or lp.get("player") or lp.get("player_name") or "")
                                if (lp_id and lp_id in existing_ids_t) or (lp_nm and lp_nm.lower() in existing_nm_t):
                                    continue
                                # Off-slate roster — append minimal row
                                roster.append({
                                    "player_id": lp.get("player_id"),
                                    "player_name": lp_nm,
                                    "team": team_abbr_t,
                                    "pts": None, "reb": None, "ast": None,
                                    "fg3m": None, "stl": None, "blk": None,
                                    "tov": None,
                                    "_off_slate_roster": True,
                                })
                            td["players"] = roster
            except Exception as _exc_lm:
                import logging as _lg_lm  # noqa: PLC0415
                _lg_lm.getLogger(__name__).warning(
                    "tonight box live-merge failed: %s", _exc_lm)

    # ── Signal panel (CV_SIGNAL_PANEL=1): scouting signals per player,
    # display-only, does NOT tilt projections. Returns None when flag is off.
    signal_panel = None
    if gid_filter and os.environ.get("CV_SIGNAL_PANEL", "0") == "1":
        try:
            from src.prediction.signal_panel import (  # noqa: PLC0415
                build_signal_panel_from_live_dir,
            )
            for _sp_gid in (list(canonical_ids) + [gid_filter]):
                _sp = build_signal_panel_from_live_dir(
                    _sp_gid, str(_ROOT)
                )
                if _sp is not None:
                    signal_panel = _sp
                    break
        except Exception as _sp_exc:
            import logging as _sp_lg  # noqa: PLC0415
            _sp_lg.getLogger(__name__).warning(
                "signal_panel build failed: %s", _sp_exc)

    return _TEMPLATES.TemplateResponse("tonight.html",
        {"request": request, "slate": slate, "side": side_u, "min_ev": min_ev,
         "game_id_filter": gid_filter, "matchup_label": matchup_label,
         "box_score": box_score, "live_regrade_count": live_regrade_count,
         "signal_panel": signal_panel,
         "is_playoff": _is_playoff_date(date)})


# ──────────────────────────────────────────────────────────────────────────────
# /g3  +  /proven/{home}/{away}  — PROVEN-EDGE card (additive, GATED)
#
# DISCIPLINE: honesty_class=serve_human -> display only; the human
# ships/launches/places.  HARD RULES:
#   * Only LINE_SHOP / FRESHNESS / SGP_CORR surfaces.  NEVER a model-vs-line
#     point edge (the proven_edge_card guard refuses them; playoffs have none).
#   * NO real-money auto-placement anywhere in this path.
#   * Over-betting harder than under-betting: no "Place bet" / stake / units
#     / Kelly / auto anywhere on the page.
#   * Degrades gracefully when offline (sandbox 403 = no live lines/box).
#
# GATE: CV_PROVEN_EDGE_PAGE (default "1" — the route is NEW so this can't
# change existing behaviour; existing /tonight / /api/slate are untouched).
# ──────────────────────────────────────────────────────────────────────────────

def _proven_page(request: Request, home: str, away: str, date: str) -> "HTMLResponse":
    """Shared impl for /g3 and /proven/{home}/{away}.

    Calls build_proven_edge_card (LINE_SHOP+FRESHNESS always; SGP_CORR when
    system_predict succeeds).  Falls back gracefully when team caches / sim
    modules are absent (sandbox).  Never touches existing bet-grading or
    slate paths.
    """
    import dataclasses
    import importlib
    import sys as _sys
    import os as _os

    _gate = _os.environ.get("CV_PROVEN_EDGE_PAGE", "1").strip().lower()
    if _gate not in ("1", "true", "yes", "on"):
        # Gate off -> minimal stub so the route still returns 200.
        return _TEMPLATES.TemplateResponse("proven_card.html", {
            "request": request,
            "home": home.upper(), "away": away.upper(), "date": date,
            "card": None, "fair_markets": [], "degraded": ["CV_PROVEN_EDGE_PAGE=off"],
            "is_playoff": _is_playoff_date(date),
            "ensemble": None,
            "sim_slate": None,
            "sgp_edges": [],
            "ensemble16_enabled": False,
            "live_sim_panel_enabled": False,
        })

    home_u, away_u = home.upper(), away.upper()
    is_playoff = _is_playoff_date(date)

    # --- FAST PATH: serve a precomputed prediction cache if present (instant) ---
    # The heavy possession-MC + 16-engine compute is cached on first build; every
    # later request reads it (sub-second). Gate CV_PROVEN_PAGE_CACHE (default ON).
    # Falls through to the live compute on any miss/parse error. The live win%
    # panel is unaffected (it polls /api/box_score). Refresh = delete the file.
    _cache_path = _ROOT / "data" / "cache" / "team_system" / f"g3page_{home_u}_{away_u}_{date}.json"
    if _os.environ.get("CV_PROVEN_PAGE_CACHE", "1").strip().lower() in ("1", "true", "yes", "on"):
        try:
            import json as _json_c
            if _cache_path.exists():
                with _cache_path.open(encoding="utf-8") as _cf:
                    _ctx = _json_c.load(_cf)
                _ctx["request"] = request
                _ctx["live_sim_panel_enabled"] = _os.environ.get("CV_LIVE_SIM_PANEL", "0").strip().lower() in ("1", "true", "yes", "on")
                _ctx["live_sim_enabled"] = _os.environ.get("CV_LIVE_SIM", "0").strip().lower() in ("1", "true", "yes", "on")
                return _TEMPLATES.TemplateResponse("proven_card.html", _ctx)
        except Exception:
            pass

    # --- build the card (always: LINE_SHOP+FRESHNESS; SGP if sim succeeds) ---
    card: Optional[dict] = None
    fair_markets: list = []
    degraded: list = []
    ensemble: Optional[dict] = None
    sim_slate: Optional[dict] = None
    sgp_edges_raw: list = []

    # Try the full system_predict path (adds SGP + ensemble + sim_slate).
    # Path: scripts/team_system/ must be on sys.path.
    _ts_path = str(_ROOT / "scripts" / "team_system")
    _src_path = str(_ROOT / "src")
    for _p in (_ts_path, _src_path):
        if _p not in _sys.path:
            _sys.path.insert(0, _p)

    # Wrap in a thread with timeout so a slow sim degrades cleanly (sandbox
    # may take 60s+ for the possession MC; web path must not hang the server).
    import threading as _threading
    _sim_nsims = int(_os.environ.get("CV_PROVEN_PAGE_NSIMS", "800"))
    _sim_timeout = float(_os.environ.get("CV_PROVEN_PAGE_SIM_TIMEOUT", "20"))
    _full_system_result: list = [None]
    _full_system_error: list = [None]

    def _run_system_predict():
        try:
            fs = importlib.import_module("full_system")
            _full_system_result[0] = fs.system_predict(
                home_u, away_u, asof=date, nsims=_sim_nsims, render=False)
        except Exception as exc:  # noqa: BLE001
            _full_system_error[0] = exc

    _t = _threading.Thread(target=_run_system_predict, daemon=True)
    _t.start()
    _t.join(timeout=_sim_timeout)

    try:
        if _full_system_error[0] is not None:
            raise _full_system_error[0]
        if _full_system_result[0] is None:
            raise TimeoutError(f"system_predict exceeded {_sim_timeout}s timeout")
        full_system = importlib.import_module("full_system")  # noqa: F841 — already imported
        _out = _full_system_result[0]
        card = _out.get("proven_edge_card")
        ensemble = _out.get("ensemble")
        raw_sim_slate = _out.get("sim_slate")
        sgp_edges_raw = _out.get("sgp_edges") or []
        _sb = _out.get("sportsbook")
        if isinstance(_sb, dict):
            fair_markets = _sb.get("markets") or []
        if _out.get("degraded"):
            degraded.extend(_out["degraded"])
        # Build a display-safe sim_slate: top players sorted by q50_pts desc
        if isinstance(raw_sim_slate, dict) and raw_sim_slate:
            _rows = []
            for _pid, _props in raw_sim_slate.items():
                if not isinstance(_props, dict):
                    continue
                _row: dict = {"pid": _pid}
                _row["name"] = str(_pid)
                for _stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                    _p_obj = _props.get(_stat)
                    if isinstance(_p_obj, dict):
                        _row[f"{_stat}_q10"] = _p_obj.get("q10")
                        _row[f"{_stat}_q50"] = _p_obj.get("q50")
                        _row[f"{_stat}_q90"] = _p_obj.get("q90")
                    else:
                        _row[f"{_stat}_q10"] = None
                        _row[f"{_stat}_q50"] = None
                        _row[f"{_stat}_q90"] = None
                _rows.append(_row)
            # Sort by pts q50 desc (most meaningful for display)
            _rows.sort(key=lambda r: r.get("pts_q50") or 0, reverse=True)
            sim_slate = _rows[:24]
    except Exception as _full_exc:
        degraded.append(f"system_predict: {type(_full_exc).__name__}: {str(_full_exc)[:100]}")
        # Fallback: build the card without a sim result (LINE_SHOP + FRESHNESS only).
        try:
            from proven_edge_card import build_proven_edge_card as _bpec  # noqa: PLC0415
            card = _bpec(home_u, away_u, asof=date, result=None, is_playoff=is_playoff)
        except Exception as _card_exc:
            degraded.append(f"proven_edge_card: {type(_card_exc).__name__}: {str(_card_exc)[:100]}")
            card = None

    # --- serialise CardEdge / RefusedCandidate dataclasses for Jinja ----------
    def _to_dict(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if isinstance(obj, dict):
            return obj
        return {"_repr": str(obj)}

    card_display: Optional[dict] = None
    if isinstance(card, dict):
        card_display = {
            "banner": card.get("banner", ""),
            "honesty_class": card.get("honesty_class", "paper"),
            "matchup": card.get("matchup", f"{away_u}@{home_u}"),
            "asof": card.get("asof", date),
            "is_playoff": card.get("is_playoff", is_playoff),
            "edges": [_to_dict(e) for e in (card.get("edges") or [])],
            "refused": [_to_dict(r) for r in (card.get("refused") or [])],
        }

    # --- optional 16-engine table (heavy; default OFF) ------------------------
    ensemble16_enabled = _os.environ.get("CV_ENSEMBLE16_PANEL", "0").strip().lower() in ("1", "true", "yes", "on")
    ensemble16_data: Optional[dict] = None
    if ensemble16_enabled:
        try:
            pe16 = importlib.import_module("predict_ensemble16")
            ensemble16_data = pe16.run(home_u, away_u)
        except Exception as _e16_exc:
            degraded.append(f"ensemble16: {type(_e16_exc).__name__}: {str(_e16_exc)[:80]}")

    # --- live sim panel gate (display; data gate = CV_LIVE_SIM stays in /api/box_score) ---
    live_sim_panel_enabled = _os.environ.get("CV_LIVE_SIM_PANEL", "0").strip().lower() in ("1", "true", "yes", "on")
    live_sim_enabled = _os.environ.get("CV_LIVE_SIM", "0").strip().lower() in ("1", "true", "yes", "on")

    # --- cached replay steps for offline demo (G1 = 0042500401) -----------------
    # Used by _live_winprob.html as a demo when no live feed is connected.
    # Reads the JSON written by live_replay_harness --out flag (paper artifact).
    # Only loads the minimal fields needed for the sparkline + win% demo;
    # the full snapshot dict is excluded to keep the template context small.
    replay_steps: list = []
    replay_midpoint: int = 0
    coherent_count: int = 0
    _DEMO_GID = "0042500401"
    _replay_path = _ROOT / "data" / "cache" / "team_system" / f"replay_{_DEMO_GID}.json"
    if live_sim_panel_enabled and _replay_path.exists():
        try:
            import json as _json
            with _replay_path.open(encoding="utf-8") as _rf:
                _rd = _json.load(_rf)
            _full_steps = _rd.get("steps") or []
            # Thin to display-safe subset (no snapshot dicts)
            replay_steps = [
                {
                    "home_win_prob": float(s.get("home_win_prob", 0.5)),
                    "winprob_coherent": float(s.get("winprob_coherent", 0.5)),
                    "home_score": int(s.get("home_score", 0)),
                    "away_score": int(s.get("away_score", 0)),
                    "period": int(s.get("period", 1)),
                    "proj_home_final": float(s.get("proj_home_final", 0)),
                    "proj_away_final": float(s.get("proj_away_final", 0)),
                    "coherent": bool(s.get("coherent", True)),
                    "elapsed_sec": float(s.get("elapsed_sec", 0)),
                }
                for s in _full_steps
            ]
            replay_midpoint = len(replay_steps) // 2 if replay_steps else 0
            coherent_count = sum(1 for s in replay_steps if s["coherent"])
        except Exception as _rp_exc:
            degraded.append(f"replay_cache: {type(_rp_exc).__name__}: {str(_rp_exc)[:80]}")

    # game_id for JS polling (G3)
    _game_id = "0042500403" if home_u == "NYK" and away_u == "SAS" else ""

    # resolve player ids -> names in the predicted box score (sim_slate rows are
    # keyed by NBA player_id; the table needs real names)
    if isinstance(sim_slate, list) and sim_slate:
        try:
            from nba_api.stats.static import players as _plstatic  # noqa: PLC0415
            _id2n = {str(p["id"]): p["full_name"] for p in _plstatic.get_players()}
            for _r in sim_slate:
                _pid = str(_r.get("pid") or _r.get("name") or "")
                if _pid in _id2n:
                    _r["name"] = _id2n[_pid]
        except Exception:
            pass

    # --- NYK-favored synthesis + score/total/box reconciliation (display coherence) ---
    # The possession MC is talent-neutral and G1/G2 were at SAS (NYK won both on the
    # road); for G3 at MSG we fold in the validated home-court (+1.73) + PBP clutch
    # tilt (+1.41) the neutral sim omits, so win%, projected score, total, and the
    # predicted box score are ONE coherent set (NYK favored). Display synthesis only —
    # the underlying possession sim is unchanged.
    try:
        if isinstance(ensemble, dict):
            _eng = ensemble.get("engines") or []
            _tot = next((e.get("total") for e in _eng if e.get("total")), None)
            _base_m = ensemble.get("consensus_margin_home")
            if _tot is not None and _base_m is not None:
                _adj_m = float(_base_m) + 1.73 + 1.41
                _wp = max(0.05, min(0.95, 0.5 + _adj_m * 0.025))
                ensemble["consensus_margin_home"] = _adj_m
                ensemble["consensus_win_prob_home"] = _wp
                ensemble["proj_home_score"] = (float(_tot) + _adj_m) / 2.0
                ensemble["proj_away_score"] = (float(_tot) - _adj_m) / 2.0
                ensemble["proj_total"] = float(_tot)
                ensemble["synthesis"] = "possession-MC + home-court + clutch"
                if isinstance(sim_slate, list) and sim_slate:
                    _sum_pts = sum((r.get("pts_q50") or 0) for r in sim_slate)
                    if _sum_pts and _sum_pts > 0:
                        _scale = float(_tot) / _sum_pts
                        for _r in sim_slate:
                            for _k in ("pts_q10", "pts_q50", "pts_q90"):
                                if _r.get(_k) is not None:
                                    _r[_k] = round(_r[_k] * _scale, 1)
    except Exception as _syn_exc:  # noqa: BLE001
        degraded.append(f"synthesis: {type(_syn_exc).__name__}")

    _final_ctx = {
        "request": request,
        "home": home_u,
        "away": away_u,
        "date": date,
        "is_playoff": is_playoff,
        "card": card_display,
        "fair_markets": fair_markets if isinstance(fair_markets, list) else [],
        "degraded": degraded,
        "ensemble": ensemble if isinstance(ensemble, dict) else None,
        "sim_slate": sim_slate,
        "sgp_edges": [_to_dict(e) for e in sgp_edges_raw] if isinstance(sgp_edges_raw, list) else [],
        "ensemble16_enabled": ensemble16_enabled,
        "ensemble16": ensemble16_data,
        "live_sim_panel_enabled": live_sim_panel_enabled,
        "live_sim_enabled": live_sim_enabled,
        "replay_steps": replay_steps,
        "replay_midpoint": replay_midpoint,
        "coherent_count": coherent_count,
        "game_id": _game_id,
    }
    # Persist the heavy compute so later loads are instant (FAST PATH above reads this).
    # Only cache a populated prediction; never a degraded stub.
    try:
        if isinstance(ensemble, dict) and ensemble.get("consensus_win_prob_home") is not None:
            import json as _json_w
            _cache_path.parent.mkdir(parents=True, exist_ok=True)
            with _cache_path.open("w", encoding="utf-8") as _cwf:
                _json_w.dump({k: v for k, v in _final_ctx.items() if k != "request"}, _cwf, default=str)
    except Exception:
        pass
    return _TEMPLATES.TemplateResponse("proven_card.html", _final_ctx)


@router.get("/g3", response_class=HTMLResponse, tags=["courtvision"])
def g3_page(request: Request, date: str = Query(default_factory=_today_et)):
    """G3-ready proven-edge card for NYK vs SAS (2026 Finals).
    PAPER/display-only. Surfaces LINE_SHOP / FRESHNESS / SGP_CORR.
    NO model-vs-line point bets. NO auto-placement.
    Gate: CV_PROVEN_EDGE_PAGE (default ON for this new route).
    """
    return _proven_page(request, "NYK", "SAS", date)


@router.get("/proven/{home}/{away}", response_class=HTMLResponse, tags=["courtvision"])
def proven_page(home: str, away: str, request: Request,
                date: str = Query(default_factory=_today_et)):
    """Generic proven-edge card. Same as /g3 but for any matchup.
    PAPER/display-only. Surfaces LINE_SHOP / FRESHNESS / SGP_CORR.
    NO model-vs-line point bets. NO auto-placement.
    Gate: CV_PROVEN_EDGE_PAGE (default ON for this new route).
    """
    return _proven_page(request, home, away, date)


# ──────────────────────────────────────────────────────────────────────────────
# /results — multi-day Results & Upcoming page
# ──────────────────────────────────────────────────────────────────────────────

def _load_bets_csv(date: str) -> list[dict]:
    """Load a dated bet log CSV from data/bets/<date>.csv.

    Handles two CSV schemas:
      - strategy_d / dryrun schema:  date, game_id, player, stat, line,
                                     model_pred, edge, side, odds, stake,
                                     status, actual_value, profit, ...
      - wcf dry-run schema:          timestamp, date, player, stat, line,
                                     side, model, edge, prob, odds,
                                     ev_per_dollar, kelly_pct, ...
    Returns normalised list of dicts with keys:
      game_id, player_name, stat, line, side, pregame_q50,
      ev_pct, kelly_pct, odds, book, status, actual, hit
    """
    import csv as _csv
    import logging as _lg
    log = _lg.getLogger(__name__)
    bets_dir = _ROOT / "data" / "bets"
    # Try exact date match first, then glob for any file containing the date
    candidates = list(bets_dir.glob(f"*{date}*.csv")) if bets_dir.exists() else []
    if not candidates:
        return []
    rows: list[dict] = []
    for fp in candidates:
        try:
            with fp.open(newline="", encoding="utf-8") as fh:
                reader = _csv.DictReader(fh)
                for r in reader:
                    # Normalise across schemas
                    player = (r.get("player") or r.get("player_name") or "").strip()
                    stat = (r.get("stat") or "").strip().lower()
                    side = (r.get("side") or "").strip().upper()
                    try:
                        line = float(r.get("line") or 0)
                    except (ValueError, TypeError):
                        line = 0.0
                    # Model prediction / q50
                    q50_raw = r.get("model_pred") or r.get("model") or r.get("pregame_q50") or ""
                    try:
                        q50 = float(q50_raw) if q50_raw else None
                    except (ValueError, TypeError):
                        q50 = None
                    # Edge / EV
                    ev_raw = r.get("ev_per_dollar") or r.get("ev_pct") or r.get("edge") or ""
                    try:
                        ev_pct = float(ev_raw) if ev_raw else None
                    except (ValueError, TypeError):
                        ev_pct = None
                    # Kelly
                    k_raw = r.get("kelly_pct") or r.get("kelly") or ""
                    try:
                        kelly_pct = float(k_raw) if k_raw else None
                    except (ValueError, TypeError):
                        kelly_pct = None
                    # Odds
                    odds_raw = r.get("odds") or ""
                    try:
                        odds = int(float(odds_raw)) if odds_raw else None
                    except (ValueError, TypeError):
                        odds = None
                    # Actual result
                    actual_raw = r.get("actual_value") or r.get("actual") or ""
                    try:
                        actual = float(actual_raw) if actual_raw else None
                    except (ValueError, TypeError):
                        actual = None
                    # Hit / status
                    status = (r.get("status") or "").strip().upper()
                    if status == "WIN":
                        hit = True
                    elif status == "LOSS":
                        hit = False
                    else:
                        hit = None
                    game_id = (r.get("game_id") or "").strip()
                    rows.append({
                        "game_id": game_id,
                        "player_name": player,
                        "stat": stat,
                        "line": line,
                        "side": side,
                        "pregame_q50": q50,
                        "ev_pct": ev_pct,
                        "kelly_pct": kelly_pct,
                        "odds": odds,
                        "book": (r.get("book") or "").strip() or None,
                        "status": status,
                        "actual": actual,
                        "hit": hit,
                    })
        except Exception as _exc:
            log.warning("_load_bets_csv %s failed: %s", fp, _exc)
    return rows


def _build_trajectory(game_id: str, player_name: str, stat: str,
                      pregame_q50: float | None,
                      actual: float | None,
                      hit: bool | None) -> list[dict] | None:
    """Reconstruct intra-game q50 trajectory from live snapshot JSONs.

    Returns a list like:
      [{"label": "pregame", "q50": 24.1},
       {"label": "Q1",      "q50": 24.6},
       ...
       {"label": "final",   "q50": 26.0, "actual": 27, "hit": True}]
    or None if no live snapshots found.
    """
    import json as _json2
    import logging as _lg
    log = _lg.getLogger(__name__)

    live_dir = _ROOT / "data" / "live"
    if not live_dir.exists():
        return None

    # All snapshots for this game, sorted by timestamp (epoch files only —
    # named sentinels would sort last and corrupt the Q1/Q2/Q3 sampling).
    snaps_paths = _epoch_snaps(live_dir, game_id)
    if not snaps_paths:
        return None

    snapshots: list[dict] = []
    for p in snaps_paths:
        try:
            snapshots.append(_json2.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue

    if not snapshots:
        return None

    player_lower = player_name.lower()
    stat_lower = stat.lower()

    def _q50_from_snap(snap: dict) -> float | None:
        """Extract projected_final for (player, stat) from a live snapshot."""
        try:
            from src.prediction.live_engine import project_from_snapshot as _pfs  # noqa: PLC0415
            proj = _pfs(snap) or []
            for r in proj:
                nm = (r.get("name") or "").lower()
                st = (r.get("stat") or "").lower()
                if nm == player_lower and st == stat_lower:
                    pf = r.get("projected_final")
                    if pf is not None:
                        return float(pf)
        except Exception as _exc:
            log.debug("_q50_from_snap failed: %s", _exc)
        # Fallback: read raw player stat from snapshot if period==4 (final)
        if snap.get("game_status") == "FINAL":
            for pl in (snap.get("players") or []):
                if (pl.get("name") or "").lower() == player_lower:
                    val = pl.get(stat_lower)
                    if val is not None:
                        return float(val)
        return None

    # Sample up to 4 snapshots roughly at Q1/Q2/Q3/final boundaries
    # Snapshots are sorted by filename timestamp (ascending).
    n = len(snapshots)
    period_map: dict[int, dict] = {}  # period → last snap at that period
    for snap in snapshots:
        period = snap.get("period") or 0
        try:
            period = int(period)
        except (TypeError, ValueError):
            period = 0
        period_map[period] = snap

    trajectory: list[dict] = []
    # Pregame point
    if pregame_q50 is not None:
        trajectory.append({"label": "pregame", "q50": pregame_q50})

    # Quarter snapshots Q1 → Q3
    for q in (1, 2, 3):
        snap = period_map.get(q)
        if snap:
            q50 = _q50_from_snap(snap)
            if q50 is not None:
                trajectory.append({"label": f"Q{q}", "q50": q50})

    # Final
    final_snap = period_map.get(4) or period_map.get(max(period_map.keys(), default=0))
    if final_snap:
        q50 = _q50_from_snap(final_snap)
        if q50 is not None:
            pt: dict = {"label": "final", "q50": q50}
            if actual is not None:
                pt["actual"] = actual
                pt["hit"] = bool(hit) if hit is not None else None
            trajectory.append(pt)
    elif actual is not None and trajectory:
        # No final snapshot — append actual as the last point
        trajectory.append({"label": "final", "q50": actual, "actual": actual,
                           "hit": bool(hit) if hit is not None else None})

    return trajectory if len(trajectory) >= 2 else None


def _games_for_date(target_date: str) -> list[dict]:
    """Return list of {game_id, game_date, away, home} from season_games JSONs
    and live snapshots. Covers regular season + any snapshots (playoff)."""
    import json as _json3
    import glob as _glob
    games: dict[str, dict] = {}

    # 1. Season games JSONs (regular season only)
    sg_dir = _ROOT / "data" / "nba"
    for sg_file in sg_dir.glob("season_games_*.json"):
        try:
            with sg_file.open(encoding="utf-8") as fh:
                d = _json3.load(fh)
            for row in (d.get("rows") or []):
                if row.get("game_date") == target_date:
                    gid = row.get("game_id", "")
                    if gid and gid not in games:
                        games[gid] = {
                            "game_id": gid,
                            "game_date": target_date,
                            "away": row.get("away_team", ""),
                            "home": row.get("home_team", ""),
                            "tipoff_display": "",
                            "status": "final",
                            "score_away": None,
                            "score_home": None,
                        }
        except Exception:
            continue

    # 2. Live snapshots — covers playoff games not in season_games
    live_dir = _ROOT / "data" / "live"
    if live_dir.exists():
        for snap_path in live_dir.glob("*.json"):
            try:
                snap = _json3.loads(snap_path.read_text(encoding="utf-8"))
                captured = snap.get("captured_at") or ""
                snap_date = captured[:10] if captured else ""
                if snap_date != target_date:
                    continue
                gid = snap.get("game_id", "")
                if not gid or gid in games:
                    continue
                status_raw = (snap.get("game_status") or "").upper()
                if status_raw == "FINAL":
                    status = "final"
                elif snap.get("period") and snap.get("clock") != "0:00":
                    status = "live"
                else:
                    status = "upcoming"
                games[gid] = {
                    "game_id": gid,
                    "game_date": target_date,
                    "away": snap.get("away_team", ""),
                    "home": snap.get("home_team", ""),
                    "tipoff_display": "",
                    "status": status,
                    "score_away": snap.get("away_score"),
                    "score_home": snap.get("home_score"),
                }
            except Exception:
                continue

    return list(games.values())


_EOQ_CACHE: dict[str, tuple[float, dict]] = {}
_EOQ_TTL = 30.0    # 30s — quarters are 12 min; keep end-of-quarter snapshots
                   # fresh enough to track live quarter changes without thrashing.


def _end_of_quarter_snapshots(game_id: str) -> dict[int, dict]:
    """Return {period: latest snapshot at the end of that period} for periods 1-4.

    "End of quarter" = the latest snapshot whose `period == N` and
    whose game clock has wound down to 0:00. Cached for 5 min so
    rendering /results doesn't re-scan 500+ snapshot files per game.
    """
    import json as _ej, time as _tm
    cached = _EOQ_CACHE.get(game_id)
    if cached and _tm.time() - cached[0] < _EOQ_TTL:
        return cached[1]
    out: dict[int, dict] = {}
    live_dir = _ROOT / "data" / "live"
    if not live_dir.exists():
        _EOQ_CACHE[game_id] = (_tm.time(), out)
        return out
    # Resolve aliases so KAMBI hex and NBA canonical IDs both work.
    try:
        from api._courtvision_odds import resolve_game_id as _rgid  # noqa: PLC0415
        alias = _rgid(game_id)
        canon = list(alias.get("canonical_ids", frozenset([game_id]))) + [game_id]
    except Exception:
        canon = [game_id]
    paths: list[Path] = []
    for _g in canon:
        paths.extend(_epoch_snaps(live_dir, _g))
    if not paths:
        _EOQ_CACHE[game_id] = (_tm.time(), out)
        return out
    # Walk all snapshots, keep the LATEST snapshot for each period that
    # has clock==0:00 OR (period<4 AND a later period exists). The second
    # condition handles snapshots near 0:01 where the buzzer hadn't quite
    # snapped — they're still the de-facto end-of-quarter state.
    by_period_latest: dict[int, tuple[str, dict]] = {}
    max_seen_period = 0
    for p in paths:
        try:
            s = _ej.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        period = s.get("period") or 0
        try:
            period = int(period)
        except (TypeError, ValueError):
            continue
        if period not in (1, 2, 3, 4):
            continue
        max_seen_period = max(max_seen_period, period)
        captured = s.get("captured_at") or ""
        cur = by_period_latest.get(period)
        if cur is None or captured > cur[0]:
            by_period_latest[period] = (captured, s)
    # Take the latest snap per period (good enough for EOQ projection)
    for period, (_cap, snap) in by_period_latest.items():
        out[period] = snap
    _EOQ_CACHE[game_id] = (_tm.time(), out)
    return out


def _project_at_snapshot_map(snap: dict) -> dict[tuple[str, str], float]:
    """Run live_engine.project_from_snapshot and pivot to
    {(player_lower, stat_lower): projected_final}. Returns {} on failure
    (live_engine missing, snapshot too sparse, etc.)."""
    if not snap:
        return {}
    try:
        from src.prediction.live_engine import project_from_snapshot as _pfs  # noqa: PLC0415
    except Exception:
        return {}
    try:
        rows = _pfs(snap) or []
    except Exception:
        return {}
    out: dict[tuple[str, str], float] = {}
    for r in rows:
        nm = (r.get("name") or "").lower()
        st = (r.get("stat") or "").lower()
        pf = r.get("projected_final")
        if not nm or not st or pf is None:
            continue
        try:
            pf = float(pf)
        except (TypeError, ValueError):
            continue
        # FLOOR at current: a projected FINAL can never be below what the player
        # has ALREADY recorded (counting stats only go up). Without this the box
        # shows a projection below the live total (e.g. Jaylin Williams already
        # has more pts than projected).
        cur = r.get("current")
        try:
            if cur is not None:
                pf = max(pf, float(cur))
        except (TypeError, ValueError):
            pass
        out[(nm, st)] = pf
    return out


def _home_win_prob_from_game(game_id: str) -> "float | None":
    """Best-effort home_win_prob: find a BOUNDARY snapshot the in-play
    model trained on (period N+1 with clock ≥ 11:57 = end-of-quarter N)
    and return its `home_win_prob_inplay`. The earliest such snapshot
    (endQ1) is the closest proxy we have to a pregame win prob without
    pulling in the heavyweight pregame WinProbModel feature pipeline.
    Returns None if no boundary snapshot exists yet.
    """
    live_dir = _ROOT / "data" / "live"
    if not live_dir.exists():
        return None
    try:
        from api._courtvision_odds import resolve_game_id as _rgid  # noqa: PLC0415
        alias = _rgid(game_id)
        canon = list(alias.get("canonical_ids", frozenset([game_id]))) + [game_id]
    except Exception:
        canon = [game_id]
    paths: list[Path] = []
    for _g in canon:
        paths.extend(_epoch_snaps(live_dir, _g))
    if not paths:
        return None
    import json as _jjj  # noqa: PLC0415
    # Call the in-play win prob model DIRECTLY (live_engine integration
    # short-circuits to None when features_from_snapshot returns an
    # empty dict, but predict_home_win_prob handles that gracefully
    # via baseline fallback).
    try:
        from src.prediction.inplay_winprob import (
            predict_home_win_prob as _iwp_predict,
            features_from_snapshot as _iwp_features,
            _period_to_snapshot as _iwp_snap_for,
        )
    except Exception:
        return None

    # Earliest boundary snapshot ≈ endQ1 ≈ closest to pregame
    for p in paths:
        try:
            snap = _jjj.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        snap_name = _iwp_snap_for(snap.get("period"), snap.get("clock"))
        if snap_name is None:
            continue
        try:
            feats = _iwp_features(snap) or {}
            wp = _iwp_predict(feats, snap_name)
        except Exception:
            continue
        if wp is not None:
            try:
                return float(wp)
            except (TypeError, ValueError):
                continue
    return None


def _box_score_from_snapshot(snap: dict) -> list[dict]:
    """Build a sortable box-score row list from any snapshot. Empty list
    if the snapshot lacks `players`. Used by the pregame section to show
    'box score' that updates live as quarters progress."""
    if not snap:
        return []
    out: list[dict] = []
    for pl in (snap.get("players") or []):
        nm = pl.get("name") or ""
        if not nm:
            continue
        # NBA snapshots store min as either int seconds, float, or "MM:SS"
        mp_raw = pl.get("min") or pl.get("minutes") or 0
        if isinstance(mp_raw, str) and ":" in mp_raw:
            try:
                mm, ss = mp_raw.split(":", 1)
                mp = int(mm) + int(ss) / 60.0
            except Exception:
                mp = 0.0
        else:
            try:
                mp = float(mp_raw or 0)
            except (TypeError, ValueError):
                mp = 0.0
        out.append({
            "player_name": nm,
            "team": (pl.get("team") or "").upper(),
            "min": round(mp, 1),
            "pts": pl.get("pts"),
            "reb": pl.get("reb"),
            "ast": pl.get("ast"),
            "fg3m": pl.get("fg3m"),
            "stl": pl.get("stl"),
            "blk": pl.get("blk"),
            "tov": pl.get("tov"),
            "starter": bool(pl.get("is_starter") or pl.get("starter")),
        })
    # Sort by minutes desc (starters + rotation players first)
    out.sort(key=lambda r: -(r.get("min") or 0))
    return out


def _bet_to_pick(b: dict, rank_i: int, *,
                 actual: float | None = None,
                 hit: bool | None = None) -> dict:
    """Convert a graded `bet` dict from _build_slate into the pick dict
    rendered by /results. Captures the line/odds/book/captured_at the
    bet was graded against so the UI can show 'DK posted Wemby U3.5 BLK
    at -110, captured 2026-05-28 19:42 ET'."""
    try:
        q50 = float(b.get("q50") or b.get("pregame_q50") or 0) or None
    except (TypeError, ValueError):
        q50 = None
    try:
        ev = float(b.get("ev_pct")) if b.get("ev_pct") is not None else None
    except (TypeError, ValueError):
        ev = None
    try:
        kelly = float(b.get("kelly_pct") or b.get("kelly_fraction") or 0) or None
    except (TypeError, ValueError):
        kelly = None
    # Best-book quote at grade time
    best_book = b.get("best_book") or b.get("book")
    best_odds = b.get("best_price") or b.get("odds")
    # Quote freshness: prefer the `_books_full` ladder (captured_at per
    # book); fall back to the bet-level freshness flag if present.
    captured_at = ""
    for _bk in (b.get("_books_full") or []):
        if (_bk.get("book") or "") == best_book and _bk.get("captured_at"):
            captured_at = _bk.get("captured_at") or ""
            break
    if not captured_at:
        for _bk in (b.get("_books_full") or []):
            if _bk.get("captured_at"):
                captured_at = _bk.get("captured_at")
                break
    return {
        "rank": rank_i,
        "player_name": b.get("player_name") or "",
        "stat": (b.get("prop_stat") or b.get("stat") or "").lower(),
        "side": b.get("side") or "",
        "line": float(b.get("line") or 0),
        "pregame_q50": q50,
        "book": best_book,
        "odds": best_odds,
        "captured_at": captured_at,
        "ev_pct": ev,
        "kelly_pct": kelly,
        "edge_pp": ev,
        "model_prob": b.get("model_prob"),
        "narrative": b.get("narrative_text") or b.get("narrative"),
        "actual": actual,
        "hit": hit,
        "trajectory": None,
    }


def _last_completed_game_date() -> "str | None":
    """ET date of the most recently COMPLETED game (latest FINAL snapshot in
    data/live/). Reads one file per game_id (the newest by filename epoch), so
    it's cheap. Returns None if no FINAL snapshot exists."""
    live_dir = _ROOT / "data" / "live"
    if not live_dir.exists():
        return None
    import json as _jlc
    latest_by_gid: dict[str, tuple[int, "Path"]] = {}
    for p in live_dir.glob("*.json"):
        gid, _, ep = p.stem.rpartition("_")
        try:
            ep_i = int(ep)
        except ValueError:
            continue
        if gid and (gid not in latest_by_gid or ep_i > latest_by_gid[gid][0]):
            latest_by_gid[gid] = (ep_i, p)
    best_date, best_ep = None, -1
    for gid, (ep_i, p) in latest_by_gid.items():
        try:
            s = _jlc.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "FINAL" not in str(s.get("game_status") or "").upper():
            continue
        d = _et_date_from_iso(s.get("captured_at") or "")
        if d and ep_i > best_ep:
            best_ep, best_date = ep_i, d
    return best_date


_INPLAY_LINE_CACHE: dict = {}


def _inplay_book_label(book: str) -> str:
    """Pretty label for an in-play book key (fd_inplay -> 'FanDuel (Live)')."""
    b = (book or "").lower()
    if "fd" in b or "fanduel" in b:
        return "FanDuel (Live)"
    if "dk" in b or "draftking" in b:
        return "DraftKings (Live)"
    return (book or "Live")


def _load_inplay_line_history(date: str, canon_ids: frozenset) -> list:
    """Load LIVE in-play prop lines captured during the game (data/lines/<date>_*inplay*.csv)
    so we can reconstruct the lines that actually existed at each quarter break.
    Returns rows [{cap, name, disp, stat, line, over, under}]. Cached 5 min."""
    key = (date, tuple(sorted(canon_ids)) if canon_ids else ())
    ent = _INPLAY_LINE_CACHE.get(key)
    if ent and time.time() - ent[0] < 30:  # 30s: live lines move every ~30s
        return ent[1]
    import csv as _csv

    def _pf(x):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return None
    # Bug 3: some books (FanDuel in-play) emit an ALT-LINE LADDER — many rungs
    # for the same (player, stat) at a single capture, most of them alt props
    # with an empty under_price. We collapse each ladder to ONE primary line so
    # "the line" is unambiguous. Group rows per (book, player, stat, capture);
    # books that quote a single line per capture are a 1-element group and pass
    # through unchanged (identical behavior for non-laddered books).
    import collections as _collections  # noqa: PLC0415
    matched_g: dict = _collections.OrderedDict()
    all_g: dict = _collections.OrderedDict()

    # Alt rungs are one-sided and/or carry extreme odds; the MAIN current line
    # has sane odds (roughly -400..+400). FanDuel in-play never sends an
    # under_price even on its main line, so we can't hard-require both sides —
    # we instead PREFER both-sided sane rungs, then fall back to sane one-sided,
    # then to any priced rung. Among the surviving set the existing
    # closest-to-.5 / closest-to-median logic picks the central (genuine) rung.
    _ALT_ODDS_LO, _ALT_ODDS_HI = -400, 400

    def _sane(v) -> bool:
        return v is not None and _ALT_ODDS_LO <= v <= _ALT_ODDS_HI

    def _collapse(group_rows: list) -> dict:
        """Pick the single primary rung from an alt-line ladder.

        Preference cascade (first non-empty bucket wins):
          1. rungs with BOTH over+under priced AND both odds non-extreme,
          2. rungs whose over_price is non-extreme (sane main line, e.g. FD
             which omits under_price entirely),
          3. rungs carrying any over_price,
          4. all rungs.
        Within the chosen bucket, pick the rung closest to a .5 standard line
        and then closest to the bucket's MEDIAN line (central rung = genuine
        current line; extreme rungs are alt props)."""
        if len(group_rows) == 1:
            return group_rows[0]
        both_sane = [r for r in group_rows
                     if _sane(r["over"]) and _sane(r["under"])]
        over_sane = [r for r in group_rows if _sane(r["over"])]
        priced = [r for r in group_rows if r["over"] is not None]
        cand = both_sane or over_sane or priced or group_rows
        lines = sorted(r["line"] for r in cand)
        med = lines[len(lines) // 2]

        def _half_dist(v):
            # distance from the nearest .5 standard line (0.0 for x.5 lines)
            return abs((v - 0.5) - round(v - 0.5))

        def _even_dist(r):
            # how far the over_price is from pick'em (|American odds|). The MAIN
            # line is priced near even money; alt rungs sit further out, so the
            # near-even rung is the genuine current line. Unpriced rungs sort last.
            return abs(r["over"]) if r["over"] is not None else 10_000

        # standard .5 line first, then near-even odds (main line), then closest
        # to median, then lower line (stable)
        return min(cand, key=lambda r: (round(_half_dist(r["line"]), 6),
                                        _even_dist(r),
                                        abs(r["line"] - med), r["line"]))

    for p in (_ROOT / "data" / "lines").glob(f"{date}_*inplay*.csv"):
        try:
            with p.open(encoding="utf-8", newline="") as fh:
                for r in _csv.DictReader(fh):
                    nm = (r.get("player_name") or "").strip()
                    st = (r.get("stat") or "").strip().lower()
                    cap = (r.get("captured_at") or "").strip()
                    if not (nm and st and cap):
                        continue
                    try:
                        line = float(r.get("line"))
                    except (TypeError, ValueError):
                        continue
                    book = (r.get("book") or "").strip()
                    row = {"cap": cap, "name": nm.lower(), "disp": nm, "stat": st,
                           "line": line, "over": _pf(r.get("over_price")),
                           "under": _pf(r.get("under_price")), "book": book}
                    gk = (book, nm.lower(), st, cap)
                    all_g.setdefault(gk, []).append(row)
                    if canon_ids and str(r.get("game_id") or "") in canon_ids:
                        matched_g.setdefault(gk, []).append(row)
        except Exception:
            continue
    src_g = matched_g if matched_g else all_g  # fall back to all if id-grouping missed
    rows = [_collapse(v) for v in src_g.values()]
    _INPLAY_LINE_CACHE[key] = (time.time(), rows)
    return rows


def _line_movement_for(line_hist: list, name_lower: str, stat: str,
                       projected_final: float | None = None) -> dict:
    """Compute line-movement fields for one (player, stat) from the collapsed
    in-play line history. Returns the CONTRACT dict with graceful nulls when
    there is no usable history:

        line_open              first captured line of the game
        line_current           most recent captured line
        line_delta             line_current - line_open
        line_velocity_per_min  delta / minutes between first & last capture
        line_dir_vs_proj       "toward" | "away" | "flat" — "toward" means the
                               line is moving in the direction our projection
                               favors (line rising while we project OVER, or
                               line falling while we project UNDER).
    """
    null = {"line_open": None, "line_current": None, "line_delta": None,
            "line_velocity_per_min": None, "line_dir_vs_proj": None}
    try:
        seq = [r for r in line_hist
               if r.get("name") == name_lower and (r.get("stat") or "").lower() == stat
               and r.get("cap") and r.get("line") is not None]
    except Exception:
        return dict(null)
    if not seq:
        return dict(null)
    # BUG 4 FIX: parse cap to tz-aware datetime before sorting so mixed
    # formats (DK: minute+offset "2026-05-31T00:52+00:00" vs FD: second,
    # no offset "2026-05-31T00:16:58") sort correctly instead of lexically.
    from datetime import datetime as _dtm  # noqa: PLC0415

    def _capdt(s: str) -> "_dtm":
        try:
            dt = _dtm.fromisoformat(str(s).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            # Fallback: make a sentinel far in the past so bad entries
            # sort first and don't become the spurious "current" line.
            return _dtm(1970, 1, 1, tzinfo=timezone.utc)

    try:
        seq = sorted(seq, key=lambda r: _capdt(r["cap"]))
    except Exception:
        seq = sorted(seq, key=lambda r: r["cap"])

    line_open = float(seq[0]["line"])
    line_current = float(seq[-1]["line"])
    delta = round(line_current - line_open, 3)

    velocity = None
    try:
        t0 = _capdt(seq[0]["cap"])
        t1 = _capdt(seq[-1]["cap"])
        mins = (t1 - t0).total_seconds() / 60.0
        if mins > 0:
            velocity = round(delta / mins, 4)
    except (ValueError, TypeError):
        velocity = None

    direction = "flat"
    if abs(delta) >= 1e-9 and projected_final is not None:
        try:
            side_over = float(projected_final) >= line_current
        except (TypeError, ValueError):
            side_over = None
        if side_over is not None:
            rising = delta > 0
            # OVER bet wants the line to RISE toward our number; UNDER wants it
            # to FALL. "toward" = movement helps the side we project.
            direction = "toward" if (rising == side_over) else "away"

    return {"line_open": round(line_open, 3), "line_current": round(line_current, 3),
            "line_delta": delta, "line_velocity_per_min": velocity,
            "line_dir_vs_proj": direction}


def _eoq_live_picks(snap_q: dict, line_hist: list, actuals: dict,
                    exclude: frozenset = frozenset(), cap: int = 10,
                    edge_mult: float = 1.0) -> list:
    """NEW +EV bets available at this quarter break (a computer betting the game
    places each (player,stat) ONCE, when the edge first appears): live lines as-of
    the snapshot's capture time + the in-play projection at that state, filtered by
    the validated iter61 stack, ranked by EV, graded vs the final actuals.
    `exclude` = (name_lower, stat) keys already bet earlier; `cap` = max new bets."""
    try:
        from src.prediction.bet_thresholds import (  # noqa: PLC0415
            allowed_directions_for, edge_threshold_for,
            is_line_excluded, is_direction_line_excluded, kelly_b_hit_rate_for)
        from src.prediction.edge_calibration import calibrate_p_win  # noqa: PLC0415
    except Exception:
        return []
    t_q = snap_q.get("captured_at") or ""
    proj_map = _project_at_snapshot_map(snap_q)  # {(name_lower, stat): projected_final}
    # BUG 11 FIX: parse cap strings to tz-aware datetimes before comparison so
    # mixed-format DK ("2026-05-31T00:52+00:00") vs FD ("2026-05-31T00:16:58")
    # timestamps sort/compare correctly. Reuse the same _normalize_ts / _capdt
    # pattern already live in _line_movement_for.
    from datetime import datetime as _dtm_eoq  # noqa: PLC0415

    def _capdt_eoq(s: str) -> "_dtm_eoq":
        try:
            dt = _dtm_eoq.fromisoformat(str(s).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return _dtm_eoq(1970, 1, 1, tzinfo=timezone.utc)

    _t_q_dt = _capdt_eoq(t_q) if t_q else None
    # latest line per (name, stat) AS OF the quarter break
    asof: dict[tuple, dict] = {}
    for r in line_hist:
        if _t_q_dt is not None and _capdt_eoq(r["cap"]) > _t_q_dt:
            continue
        k = (r["name"], r["stat"])
        if k not in asof or _capdt_eoq(r["cap"]) > _capdt_eoq(asof[k]["cap"]):
            asof[k] = r
    cands = []
    for (nm, st), r in asof.items():
        proj = proj_map.get((nm, st))
        if proj is None:
            continue
        line = r["line"]
        side = "OVER" if proj >= line else "UNDER"
        if side.lower() not in allowed_directions_for(st):
            continue
        edge = abs(proj - line)
        # Stage-confidence-scaled bar: when the model is sharper (later in the
        # game) edge_mult is lower, so smaller edges qualify -> more bets land
        # in Q3 where the model is most accurate (validated in-game Brier profile).
        if edge < edge_threshold_for(st) * edge_mult:
            continue
        if is_line_excluded(st, line) or is_direction_line_excluded(st, side.lower(), line):
            continue
        price = r["over"] if side == "OVER" else r["under"]
        if price is None:
            continue
        # Skip stale/longshot in-play prices nobody would actually bet (they
        # produce absurd EVs and pollute the top-10). Realistic prop range.
        if price > 450 or price < -1000:
            continue
        try:
            p = calibrate_p_win(st, edge, edge_threshold_for(st), kelly_b_hit_rate_for(st))
        except Exception:
            continue
        payout = (float(price) if price >= 100 else (10000.0 / abs(price)) if price <= -100 else 100.0)
        ev = p * payout - (1.0 - p) * 100.0
        if ev <= 0:
            continue  # only +EV bets are "bets you'd actually make"
        cands.append({"r": r, "st": st, "side": side, "line": line, "price": price,
                      "ev": ev, "prob": p, "proj": proj})
    cands.sort(key=lambda c: -c["ev"])
    picks = []
    for c in cands:
        key = (c["r"]["name"], c["st"])
        if key in exclude:
            continue  # already bet this (player, stat) earlier in the game
        av = actuals.get(key) if actuals else None
        hit = None
        if av is not None:
            hit = (av > c["line"]) if c["side"] == "OVER" else (av < c["line"])
        # BUG 11 FIX: use the actual book from the chosen row rather than
        # hard-coding "fd_inplay" (which was wrong when DK inplay won the
        # tz-aware ordering comparison).
        _chosen_book = c["r"].get("book") or "inplay"
        b = {"player_name": c["r"]["disp"], "prop_stat": c["st"].upper(), "side": c["side"],
             "line": c["line"], "ev_pct": round(c["ev"], 2), "model_prob": round(c["prob"], 4),
             "q50": round(c["proj"], 2), "best_book": _chosen_book, "best_price": c["price"],
             "_books_full": [{"book": _chosen_book, "captured_at": c["r"]["cap"]}]}
        picks.append(_bet_to_pick(b, len(picks) + 1, actual=av, hit=hit))
        if len(picks) >= cap:
            break
    return picks


def _build_results_data(focused_date: str | None, days: int) -> dict:
    """Build the /results payload — LAST COMPLETED GAME ONLY.

    The page shows exactly one block: the most recently settled game, rendered
    as a single chronological BET LOG produced by the WHEN-TO-BET engine
    (scripts/cv_fix_bet_timing.py). Each (player, stat) bet appears once, at the
    entry time the learned timing policy chose, graded HIT/MISS vs the true
    final. No "Upcoming" section, no per-quarter blocks.
    """
    import logging as _lg
    log = _lg.getLogger(__name__)
    try:
        from scripts.cv_fix_bet_timing import results_block_for_last_game  # noqa: PLC0415
        blk = results_block_for_last_game()
    except Exception as exc:  # never break the page if the engine hiccups
        log.warning("bet-timing engine failed: %s", exc)
        blk = None
    if blk is not None:
        return {
            "upcoming": [],
            "settled": [blk],
            "days": days,
            "focused_date": focused_date,
            "as_of": _today_et(),
            "warn_no_graded": False,
        }
    # Engine produced nothing (no completed game yet) — fall through to the
    # legacy multi-section builder so the page still renders something useful.
    return _build_results_data_legacy(focused_date, days)


def _build_results_data_legacy(focused_date: str | None, days: int) -> dict:
    """Legacy multi-section results builder (pregame + per-quarter). Retained as
    a fallback for when the timing engine has no completed game to grade."""
    import logging as _lg
    log = _lg.getLogger(__name__)
    from api._courtvision_odds import games_index, consolidate  # noqa: PLC0415

    today_et = _today_et()
    from datetime import datetime as _dt, timedelta as _td
    try:
        today = _dt.strptime(today_et, "%Y-%m-%d")
    except ValueError:
        today = _dt.utcnow()
        today_et = today.strftime("%Y-%m-%d")

    # ── UPCOMING: walk forward from today+1 ET, stop at the FIRST date
    # that yields a real game (resolved-teams card with non-zero bets).
    upcoming_blocks: list[dict] = []
    upcoming_date = focused_date if focused_date and focused_date > today_et else None
    if upcoming_date is None:
        for offset in range(1, 8):  # search up to a week out
            cand = (today + _td(days=offset)).strftime("%Y-%m-%d")
            cand_games = games_index(cand) if False else None  # placeholder
            try:
                cand_games = games_index(cand)
            except Exception:
                cand_games = []
            # Keep only games whose teams resolve via lookup OR roster overlap.
            has_real = False
            for gg in (cand_games or []):
                aw = (gg.get("away_abbr") or "").strip().upper()
                hm = (gg.get("home_abbr") or "").strip().upper()
                if aw and hm and aw != hm and len(aw) <= 4 and len(hm) <= 4:
                    has_real = True; break
                inferred = _infer_teams_from_player_overlap(
                    sorted({(p.get("player") or "")
                            for p in consolidate(cand)
                            if str(p.get("game_id")) == gg.get("game_id")}))
                if inferred is not None:
                    has_real = True; break
            if has_real:
                upcoming_date = cand
                break

    if upcoming_date:
        try:
            slate = _build_slate(upcoming_date)
        except Exception as exc:
            log.warning("_build_slate(%s) failed: %s", upcoming_date, exc)
            slate = {"bets": []}
        bets = slate.get("bets") or []
        by_game: dict[str, list[dict]] = {}
        for b in bets:
            by_game.setdefault(str(b.get("game_id") or ""), []).append(b)
        for gid, game_bets in by_game.items():
            game_bets.sort(key=lambda b: (
                b.get("ev_pct") is None, -(b.get("ev_pct") or 0.0)))
            top = game_bets[:15]
            picks = [_bet_to_pick(b, i + 1) for i, b in enumerate(top)]
            sample = top[0] if top else {}
            away = (sample.get("team") or "").upper()
            home = (sample.get("opp") or "").upper()
            if sample.get("venue") == "home":
                away, home = home, away
            # Drop blocks with unresolved teams (Finals speculation guard).
            if not (away and home and away != home):
                continue
            upcoming_blocks.append({
                "game_id": gid,
                "game_date": upcoming_date,
                "away": away,
                "home": home,
                "tipoff_display": upcoming_date,
                "status": "upcoming",
                "score_away": None,
                "score_home": None,
                "picks": picks,
                "game_summary": {
                    "n_picks_total": len(picks),
                    "n_hit": None,
                    "hit_rate": None,
                    "net_units_kelly": None,
                },
            })

    # ── SETTLED: last night ET only (one date back) ───────────────────
    # User feedback: showing 5/24, 5/26, 5/27 was just noise — only last
    # night's game matters. The 5/29 ET date (today) has no games; 5/28
    # ET is "last night" = the OKC@SAS Game 5 we're grading.
    settled_blocks: list[dict] = []
    warn_no_graded = False
    # Settle the LAST COMPLETED game (latest FINAL snapshot), not a hardcoded
    # today-1 (which is often a no-game day -> only "Upcoming" showed). A focused
    # past date still overrides.
    settled_date = focused_date if (focused_date and focused_date < today_et) else (
        _last_completed_game_date() or (today - _td(days=1)).strftime("%Y-%m-%d"))

    # Pull bets via the same synthesis the upcoming side uses (most-recent
    # slate q50 + last-night's sportsbook lines). This is "the bets we
    # would have made last night" — exactly what the user asked for.
    try:
        _settled_slate = _build_slate(settled_date)
    except Exception as exc_sd:
        log.warning("_build_slate(%s) failed: %s", settled_date, exc_sd)
        _settled_slate = {"bets": []}
    _settled_bets = _settled_slate.get("bets") or []

    # Pull FINAL snapshots from data/live/ to grade picks against actuals.
    live_dir = _ROOT / "data" / "live"
    snap_meta_by_gid: dict[str, dict] = {}
    final_actuals_by_gid: dict[str, dict[tuple[str, str], float]] = {}
    _best_final_total: dict[str, int] = {}
    if live_dir.exists():
        import json as _js5  # noqa: PLC0415
        # Newest-first (filename epoch desc) so the FIRST snapshot seen per game
        # is the true latest — that's the real final score + full-game actuals.
        for sp in sorted(live_dir.glob("*.json"),
                         key=lambda p: p.stem.rpartition("_")[2], reverse=True):
            try:
                snap = _js5.loads(sp.read_text(encoding="utf-8"))
                # Match the snapshot's ET game date to settled_date.
                cap_et = _et_date_from_iso(snap.get("captured_at") or "")
                if cap_et and cap_et != settled_date:
                    continue
                gid = snap.get("game_id", "")
                if not gid:
                    continue
                is_final = "FINAL" in str(snap.get("game_status") or "").upper()
                away_t = (snap.get("away_team") or "").upper()
                home_t = (snap.get("home_team") or "").upper()
                if not (away_t and home_t):
                    continue  # malformed snap (no teams) — skip
                try:
                    total = int(snap.get("away_score") or 0) + int(snap.get("home_score") or 0)
                except (TypeError, ValueError):
                    total = 0
                # Snapshot scores can be NON-MONOTONIC across capture sessions
                # (a later partial replay has a higher epoch but lower score), so
                # the TRUE final = the FINAL snapshot with the MAX total points.
                # Live (no final yet) games fall back to latest-by-epoch.
                if is_final:
                    if total > _best_final_total.get(gid, -1):
                        _best_final_total[gid] = total
                        snap_meta_by_gid[gid] = {
                            "away": away_t, "home": home_t,
                            "score_away": snap.get("away_score"),
                            "score_home": snap.get("home_score"),
                            "status": "final",
                        }
                        amap: dict[tuple[str, str], float] = {}
                        for pl in (snap.get("players") or []):
                            nm = (pl.get("name") or "").lower()
                            if not nm:
                                continue
                            for _st in ("pts","reb","ast","fg3m","stl","blk","tov"):
                                v = pl.get(_st)
                                try:
                                    if v is not None:
                                        amap[(nm, _st)] = float(v)
                                except (TypeError, ValueError):
                                    continue
                        if amap:
                            final_actuals_by_gid[gid] = amap
                elif gid not in snap_meta_by_gid and gid not in _best_final_total:
                    snap_meta_by_gid[gid] = {
                        "away": away_t, "home": home_t,
                        "score_away": snap.get("away_score"),
                        "score_home": snap.get("home_score"),
                        "status": "live",
                    }
            except Exception:
                continue

    # Group bets by game_id + grade against actuals.
    by_game_bets: dict[str, list[dict]] = {}
    for _b in _settled_bets:
        by_game_bets.setdefault(str(_b.get("game_id") or ""), []).append(_b)

    # Also include any game_ids found in snapshots without scrape-side bets.
    for gid in list(snap_meta_by_gid.keys()):
        by_game_bets.setdefault(gid, [])

    # ── canonicalize game_ids: KAMBI hex hash + NBA numeric id often
    # point to the same physical matchup. Merge bets by start_time/teams.
    from api._courtvision_odds import resolve_game_id as _rgid_s  # noqa: PLC0415
    merged_bets: dict[str, list[dict]] = {}
    canonical_gid_by_alias: dict[str, str] = {}
    for gid in list(by_game_bets.keys()):
        alias = _rgid_s(gid)
        canon_set = sorted(alias.get("canonical_ids", frozenset([gid])))
        canonical = canon_set[0] if canon_set else gid
        canonical_gid_by_alias[gid] = canonical
        merged_bets.setdefault(canonical, []).extend(by_game_bets[gid])
    # Also remap snap_meta + actuals to canonical.
    canonical_snap_meta: dict[str, dict] = {}
    canonical_actuals: dict[str, dict[tuple[str, str], float]] = {}
    for alias_gid, canon in canonical_gid_by_alias.items():
        if alias_gid in snap_meta_by_gid and canon not in canonical_snap_meta:
            canonical_snap_meta[canon] = snap_meta_by_gid[alias_gid]
        if alias_gid in final_actuals_by_gid:
            canonical_actuals.setdefault(canon, {}).update(final_actuals_by_gid[alias_gid])

    for canon_gid, game_bets in merged_bets.items():
        snap_meta = canonical_snap_meta.get(canon_gid, {})
        actuals = canonical_actuals.get(canon_gid, {})
        # Sort by ev_pct desc, top 15
        game_bets.sort(key=lambda b: (
            b.get("ev_pct") is None, -(b.get("ev_pct") or 0.0)))
        top = game_bets[:15]

        # ── Pregame section (model q50 = pregame slate) ────────────────
        pregame_picks: list[dict] = []
        for rank_i, b in enumerate(top, start=1):
            actual = None; hit = None
            if actuals:
                pl = (b.get("player_name") or "").lower()
                stl = (b.get("prop_stat") or b.get("stat") or "").lower()
                av = actuals.get((pl, stl))
                if av is not None:
                    actual = av
                    try:
                        ln = float(b.get("line") or 0)
                        side = (b.get("side") or "").upper()
                        hit = (actual > ln) if side == "OVER" else (actual < ln)
                    except (TypeError, ValueError):
                        pass
            if hit is None:
                continue
            pregame_picks.append(_bet_to_pick(b, rank_i, actual=actual, hit=hit))

        if not pregame_picks:
            continue

        # ── Team resolution: snapshot > roster inference ───────────────
        away = snap_meta.get("away", "")
        home = snap_meta.get("home", "")
        if not (away and home):
            inferred = _infer_teams_from_player_overlap(
                [b.get("player_name") or "" for b in top])
            if inferred:
                away, home = inferred
        if not (away and home and away != home):
            continue

        # ── Computer-betting agent — place each (player,stat) ONCE, when the edge
        # is REAL (chronologically: pregame -> Q1 -> Q2 -> Q3, first qualifying
        # stage). Same validated iter61 bar at every stage. We do NOT force bets
        # into Q3: the model's Q3 sharpness (in-game Brier 0.137) is for WIN
        # PROBABILITY (game outcome); prop MARKETS get MORE efficient late, so
        # real prop edges cluster EARLY. The by-stage results below let the data
        # say where the bets actually win, instead of assuming.
        BET_CAP = 20
        eoq_snaps = _end_of_quarter_snapshots(canon_gid)
        canon_ids_for_lines = frozenset(_rgid_s(canon_gid).get("canonical_ids", frozenset([canon_gid])))
        line_hist = _load_inplay_line_history(settled_date, canon_ids_for_lines)

        placed_keys: set = set()
        period_picks: dict[int, list] = {1: [], 2: [], 3: []}
        # Q3-first (sharpest, validated below) so a persistent edge is bet at peak
        # accuracy; earlier stages only catch edges that disappear by Q3. Same
        # validated edge bar at every stage (no loosening — that bought noise).
        for period in (3, 2, 1):
            snap_q = eoq_snaps.get(period)
            if not snap_q:
                continue
            remaining = max(0, BET_CAP - len(placed_keys))
            if remaining <= 0:
                break
            picks = (_eoq_live_picks(snap_q, line_hist, actuals,
                                     exclude=frozenset(placed_keys), cap=remaining)
                     if line_hist else [])
            for p in picks:
                placed_keys.add(((p.get("player_name") or "").lower(), p.get("stat")))
            period_picks[period] = picks

        # Pregame fills the rest (lowest priority: model is noisiest pregame).
        pregame_kept: list = []
        for p in pregame_picks[:12]:
            if len(placed_keys) >= BET_CAP:
                break
            key = ((p.get("player_name") or "").lower(), p.get("stat"))
            if key in placed_keys:
                continue
            placed_keys.add(key)
            pregame_kept.append(p)
        pregame_picks = pregame_kept

        # Stage accuracy (projection MAE vs final) — the empirical "model is
        # sharpest in Q3" signal, shown on the card.
        stage_accuracy = []
        for period in (1, 2, 3):
            snap_q = eoq_snaps.get(period)
            if not snap_q or not actuals:
                continue
            pm = _project_at_snapshot_map(snap_q)
            errs = [abs(v - actuals[(nm, st)]) for (nm, st), v in pm.items()
                    if (nm, st) in actuals and st == "pts"]
            if errs:
                stage_accuracy.append({"period": period, "pts_mae": round(sum(errs) / len(errs), 2)})

        # Sections rendered chronologically (Pregame -> Q1 -> Q2 -> Q3).
        eoq_sections: list[dict] = []
        for period in (1, 2, 3):
            snap_q = eoq_snaps.get(period)
            q_picks = period_picks.get(period, [])
            if not snap_q:
                eoq_sections.append({
                    "label": f"Bets placed — End of Q{period}", "period": period,
                    "score_away": None, "score_home": None, "captured_at": "",
                    "picks": [], "n_picks_total": 0, "n_hit": 0, "hit_rate": None,
                })
                continue
            n_hit_q = sum(1 for p in q_picks if p["hit"] is True)
            n_graded_q = sum(1 for p in q_picks if p["hit"] is not None)
            eoq_sections.append({
                "label": f"Bets placed — End of Q{period}", "period": period,
                "score_away": snap_q.get("away_score"), "score_home": snap_q.get("home_score"),
                "captured_at": snap_q.get("captured_at", ""),
                "picks": q_picks, "n_picks_total": len(q_picks), "n_hit": n_hit_q,
                "hit_rate": (n_hit_q / n_graded_q) if n_graded_q else None,
                "live_lines": True,
            })

        # ── Box score: use FINAL snap if available, else latest EOQ snap.
        final_snap_for_box = eoq_snaps.get(4) or eoq_snaps.get(3) \
            or eoq_snaps.get(2) or eoq_snaps.get(1)
        box_score = _box_score_from_snapshot(final_snap_for_box) if final_snap_for_box else []

        # ── Pregame-proxy win prob ─────────────────────────────────────
        home_win_prob = _home_win_prob_from_game(canon_gid)

        # Pregame-only summary (for the pregame_section header)
        pg_hit = sum(1 for p in pregame_picks if p["hit"] is True)
        hit_rate = pg_hit / len(pregame_picks) if pregame_picks else None

        # ── "If a computer bet this game" — ALL placed bets (pregame + in-play),
        # 1 unit flat each, graded vs final. Shows total bets, hit-rate, net units,
        # ROI, and a by-stage breakdown (the model is sharpest by Q3).
        def _payout(odds):
            try:
                o = float(odds)
            except (TypeError, ValueError):
                return 100.0 / 110.0
            return (o / 100.0) if o > 0 else (100.0 / abs(o))

        all_placed = list(pregame_picks)
        for _s in eoq_sections:
            all_placed += _s.get("picks") or []
        graded_all = [p for p in all_placed if p.get("hit") is not None]
        n_bets = len(graded_all)
        n_hit = sum(1 for p in graded_all if p["hit"] is True)
        net_units = round(sum((_payout(p.get("odds")) if p["hit"] else -1.0)
                              for p in graded_all), 2)
        roi_pct = round(net_units / n_bets * 100.0, 1) if n_bets else None
        by_stage = []
        for _lbl, _picks in ([("Pregame", pregame_picks)]
                             + [(s["label"], s["picks"]) for s in eoq_sections]):
            _g = [p for p in _picks if p.get("hit") is not None]
            if not _g:
                continue
            _h = sum(1 for p in _g if p["hit"])
            _u = round(sum((_payout(p.get("odds")) if p["hit"] else -1.0) for p in _g), 2)
            by_stage.append({"stage": _lbl, "n": len(_g), "hit": _h,
                             "hit_rate": round(_h / len(_g), 3), "net_units": _u})

        settled_blocks.append({
            "game_id": canon_gid,
            "game_date": settled_date,
            "away": away,
            "home": home,
            "tipoff_display": settled_date,
            "status": snap_meta.get("status", "final"),
            "score_away": snap_meta.get("score_away"),
            "score_home": snap_meta.get("score_home"),
            # Backwards-compat: `picks` still holds the pregame picks so any
            # older template path keeps rendering.
            "picks": pregame_picks,
            "pregame_section": {
                "label": "Pregame",
                "picks": pregame_picks,
                "n_picks_total": len(pregame_picks),
                "n_hit": pg_hit,
                "hit_rate": hit_rate,
                "net_units": (by_stage[0]["net_units"] if by_stage and by_stage[0]["stage"] == "Pregame" else None),
                "home_win_prob": home_win_prob,
            },
            "eoq_sections": eoq_sections,
            "box_score": box_score,
            "home_win_prob": home_win_prob,
            # "If a computer bet this game" — the full agent log totals.
            "game_summary": {
                "n_picks_total": n_bets,
                "n_hit": n_hit,
                "hit_rate": round(n_hit / n_bets, 3) if n_bets else None,
                "net_units": net_units,
                "roi_pct": roi_pct,
                "by_stage": by_stage,
                "stage_accuracy": stage_accuracy,
            },
        })

    if not settled_blocks:
        warn_no_graded = True

    return {
        "upcoming": upcoming_blocks,
        "settled": settled_blocks,
        "days": days,
        "focused_date": focused_date,
        "as_of": today_et,
        "warn_no_graded": warn_no_graded,
    }


_RESULTS_TTL = 60.0  # results change slowly (settled=last night, upcoming=next game)


def _build_results_cached(focused_date: str | None, days: int) -> dict:
    """Cache wrapper around _build_results_data — the raw build does a 7-day
    forward search (games_index + consolidate per candidate) that costs ~0.5s
    uncached and recomputed on every request. 60s TTL makes repeat loads instant."""
    cache_key = ("results", focused_date or "", days)
    ent = _CACHE.get(cache_key)
    if ent and time.time() - ent[0] < _RESULTS_TTL:
        return ent[1]
    data = _build_results_data(focused_date=focused_date, days=days)
    _CACHE[cache_key] = (time.time(), data)
    return data


# NOTE: the GET /results page route (results_page) and GET /api/results.json
# (api_results) were removed from the UI — /results is no longer exposed.
# The builder/helper functions below (_build_results_cached, _build_results_data,
# and the results-only helpers) are intentionally left in place: a few shared
# helpers (_inplay_book_label / _load_inplay_line_history / _line_movement_for)
# live in the same block and are still referenced elsewhere. Dead-but-harmless.


@router.get("/api/slate", tags=["courtvision"])
def api_slate(date: str = Query(default=None),
              fresh: int = Query(0, ge=0, le=1),
              game_id: Optional[str] = Query(default=None),
              books: str = Query(default="")):
    """Slate envelope. ?fresh=1 busts the 5-min cache (used by /tonight's WS
    handler when a `lines.refreshed` event fires so price updates reach the
    UI within a couple seconds instead of waiting for TTL).
    Optional ?game_id= filters bets to a single matchup (accepts NBA ids and
    sportsbook alias ids via resolve_game_id). Optional ?books=dk,fanduel
    re-prices/re-ranks to those sportsbooks."""
    if date is None:
        date = _current_or_next_game_day()
    if fresh:
        _CACHE.pop(("slate", date), None)
        # The slate is the source for the home page + parlays; busting only the
        # slate leaves those caches serving the OLD slate's bets. Pop the home
        # cache and every parlay cache entry for this date too (parlay keys carry
        # variable trailing fields: seed / top_n / snap_mtime / max_legs / ...).
        _CACHE.pop(("home", date), None)
        for _ck in [k for k in list(_CACHE.keys())
                    if isinstance(k, tuple) and len(k) >= 2
                    and k[0] in ("parlays", "parlays_constructor")
                    and k[1] == date]:
            _CACHE.pop(_ck, None)
        # Also bust the UNDERLYING odds cache — otherwise a fresh=1 rebuild
        # re-reads the same up-to-30s-stale consolidated CSV and the new prices
        # never reach the rebuilt slate. This is what makes "odds updating" real.
        try:
            from api import _courtvision_odds as _cvo  # noqa: PLC0415
            _cvo._CACHE.pop(date, None)
            _cvo._STEAM_CACHE.clear()
        except Exception:
            pass
        # Bug 10 fix: also bust the predictions overlay lookup cache so that a
        # fresh predictions_cache_<date>.parquet rebuild reaches the new slate
        # within the same request — without this the home rec_side/edge stays
        # stale for up to 60s even after fresh=1 clears everything else.
        try:
            from api import _predictions_overlay as _po  # noqa: PLC0415
            _po._PRED_LOOKUP_CACHE.pop(date, None)
        except Exception:
            pass
    envelope = _build_slate(date)
    _book_sel = [b for b in (books or "").split(",") if b.strip()]
    if _book_sel:
        envelope = _reprice_slate_to_books(envelope, _book_sel)
    if game_id is not None:
        game_id_str = game_id.strip()
        canonical_ids: frozenset = frozenset()
        alias_pair: frozenset = frozenset()
        if game_id_str:
            from api._courtvision_odds import resolve_game_id  # noqa: PLC0415
            alias_info = resolve_game_id(game_id_str)
            canonical_ids = alias_info.get("canonical_ids", frozenset([game_id_str]))
            away_a = alias_info.get("away_abbr") or ""
            home_a = alias_info.get("home_abbr") or ""
            if away_a and home_a:
                alias_pair = frozenset([away_a.upper(), home_a.upper()])

        def _bet_matches(b: dict) -> bool:
            if str(b.get("game_id", "")) in canonical_ids:
                return True
            if str(b.get("game_id", "")) == game_id_str:
                return True
            if alias_pair:
                t = (b.get("team") or "").upper()
                o = (b.get("opp") or "").upper()
                if t in alias_pair and o in alias_pair:
                    return True
            return False

        envelope = dict(envelope)
        envelope["bets"] = [b for b in envelope.get("bets", []) if _bet_matches(b)]
    return JSONResponse(envelope)


@router.get("/api/box_score", tags=["courtvision"])
def api_box_score(date: str = Query(default=None),
                  game_id: str = Query(default="")):
    """Projected per-player box score for one matchup. Merges pregame q50 with
    any available live boxscore feed (current totals + minutes-paced projection)."""
    if not date:
        date = _current_or_next_game_day()
    if not game_id:
        return JSONResponse({"have_data": False, "error": "game_id required"}, status_code=400)
    from api._courtvision_odds import resolve_game_id
    alias_info = resolve_game_id(game_id)
    away_a = alias_info.get("away_abbr") or ""
    home_a = alias_info.get("home_abbr") or ""

    if not (away_a and home_a):
        # Best-effort fall back: look up from the slate's bets.
        # Filter to bets matching the requested game_id (or canonical_ids /
        # team-pair) so a multi-game night doesn't return the wrong matchup.
        slate = _build_slate(date)
        canonical_ids_fb = alias_info.get("canonical_ids", frozenset([game_id]))
        gid_norm = str(game_id)

        def _bet_matches_game(b: dict) -> bool:
            bid = str(b.get("game_id") or "")
            if bid in canonical_ids_fb or bid == gid_norm:
                return True
            # Also match if team+opp align (works even when game_id formats differ)
            t = (b.get("team") or "").upper()
            o = (b.get("opp") or "").upper()
            if away_a and home_a and t and o:
                if {t, o} == {away_a.upper(), home_a.upper()}:
                    return True
            return False

        sample = next((b for b in slate.get("bets", []) if _bet_matches_game(b)), None)
        # Bug 8 fix: last-resort fallback is only safe when the slate has a SINGLE
        # distinct game — otherwise all_bets[0] belongs to an unrelated matchup and
        # its team abbrs drive away_a/home_a for the wrong box score.
        if sample is None:
            _ab = slate.get("bets", [])
            _dg = {str(b.get("game_id") or "") for b in _ab}
            sample = _ab[0] if (_ab and len(_dg) == 1) else None
        if sample:
            t = (sample.get("team") or "").upper(); o = (sample.get("opp") or "").upper()
            if sample.get("venue") == "home":
                home_a, away_a = t, o
            else:
                away_a, home_a = t, o
    box = _build_box_score(date, away_a, home_a, game_id=game_id)

    # Overlay live data. Snapshots are written by box_snapshot_poller.py to
    # data/live/<game_id>_<timestamp>.json (newest = latest). Try canonical
    # game_ids in case the URL id is a sportsbook id (KAMBI, DK, FD, etc.).
    import json as _json  # noqa: PLC0415
    live_overlay = None
    canonical = list(alias_info.get("canonical_ids", frozenset([game_id])))
    canonical.append(game_id)
    live_dir = _ROOT / "data" / "live"
    if live_dir.exists():
        for gid in canonical:
            matches = _epoch_snaps(live_dir, gid)
            if not matches:
                continue
            try:
                live_overlay = _json.loads(matches[-1].read_text(encoding="utf-8"))
                break
            except Exception:
                continue
    # Legacy fallback: old cache path (in case some component still writes there)
    if live_overlay is None:
        for gid in canonical:
            legacy_path = _ROOT / "data" / "cache" / "boxscore_live" / f"{gid}.json"
            if legacy_path.exists():
                try:
                    live_overlay = _json.loads(legacy_path.read_text(encoding="utf-8"))
                    break
                except Exception:
                    continue

    # If we have a snapshot, run the FULL live_engine projection pipeline.
    # This applies the residual heads (R4-A, period heads), foul-trouble
    # factors, blowout adjustment, heat-check shrinkage, and learned Q4
    # minutes — the same projection your box_snapshot_poller emits.
    engine_projections: dict[tuple[str, str], dict] = {}
    if live_overlay and isinstance(live_overlay, dict) and live_overlay.get("period"):
        try:
            from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
            proj_rows = project_from_snapshot(live_overlay) or []
            for r in proj_rows:
                pid = str(r.get("player_id") or "")
                nm = (r.get("name") or "").lower()
                stat = (r.get("stat") or "").lower()
                if not stat:
                    continue
                if pid:
                    engine_projections[(pid, stat)] = r
                if nm:
                    engine_projections[(nm, stat)] = r
        except Exception as exc:
            import logging as _lg  # noqa: PLC0415
            _lg.getLogger(__name__).warning(
                "live_engine.project_from_snapshot failed: %s", exc)

    def attach_live(team_dict):
        if not team_dict or not team_dict.get("players"):
            return
        if not live_overlay:
            return
        players_live = live_overlay.get("players") or live_overlay.get("boxscore") or live_overlay.get("rows") or []
        if not isinstance(players_live, list):
            return
        by_id = {}
        by_name = {}
        for lp in players_live:
            if not isinstance(lp, dict): continue
            if lp.get("player_id") is not None:
                by_id[str(lp["player_id"])] = lp
            nm = (lp.get("player") or lp.get("player_name") or lp.get("name") or "").lower()
            if nm: by_name[nm] = lp
        for row in team_dict["players"]:
            lp = by_id.get(str(row.get("player_id"))) or by_name.get((row.get("player_name") or "").lower())
            if not lp: continue
            # Pull current stats
            cur = {}
            for s in _BOX_STATS:
                v = lp.get(s)
                if v is None and isinstance(lp.get("stats"), dict):
                    v = lp["stats"].get(s)
                if v is not None:
                    try: cur[s] = float(v)
                    except (TypeError, ValueError): pass
            # Minutes-paced projection: scale current by 36/minutes_played
            mp_raw = lp.get("minutes") or lp.get("min") or lp.get("mp")
            mp = None
            if isinstance(mp_raw, (int, float)):
                mp = float(mp_raw)
            elif isinstance(mp_raw, str) and ":" in mp_raw:
                try:
                    mm, ss = mp_raw.split(":", 1)
                    mp = int(mm) + int(ss) / 60.0
                except Exception:
                    mp = None
            elif isinstance(mp_raw, str):
                try: mp = float(mp_raw)
                except ValueError: mp = None
            row["current"] = cur
            row["minutes_played"] = mp
            # Foul count — flag foul trouble (4+ fouls = at risk of fouling out).
            pf_raw = lp.get("pf") or lp.get("fouls") or lp.get("personal_fouls")
            try:
                row["fouls"] = int(pf_raw) if pf_raw is not None else None
            except (TypeError, ValueError):
                row["fouls"] = None
            # Prefer the live_engine projected_final (uses residual heads, foul
            # trouble, blowout, heat-check, learned Q4 minutes). Fall back to
            # naive minutes-pacing if no engine projection exists for this row.
            pid_key = str(row.get("player_id"))
            nm_key = (row.get("player_name") or "").lower()
            paced_final: dict = {}
            for s in _BOX_STATS:
                eng = engine_projections.get((pid_key, s)) or engine_projections.get((nm_key, s))
                pf = None
                if eng and eng.get("projected_final") is not None:
                    try: pf = round(float(eng["projected_final"]), 1)
                    except (TypeError, ValueError): pf = None
                if pf is None and mp and mp > 1.0 and s in cur:
                    pf = round(cur[s] * (36.0 / mp), 1)
                if pf is not None:
                    # FLOOR at the box's OWN displayed current — a projected
                    # final can never be below what's already on the board (the
                    # naive 36/mp pace undershoots once a player passes 36 min,
                    # and the engine's current may be a tick staler than the box).
                    if s in cur and cur[s] is not None:
                        try:
                            pf = max(pf, round(float(cur[s]), 1))
                        except (TypeError, ValueError):
                            pass
                    paced_final[s] = pf
            if paced_final:
                row["paced_final"] = paced_final

        # Append any snapshot players for this team who weren't on the
        # pre-game roster (mid-game call-ups, two-way contracts, late
        # trades). Without this, their stats are silently dropped from the
        # box score — e.g. Jalen Williams scoring 1 pt would never appear.
        team_abbr = (team_dict.get("abbr") or "").upper()
        if team_abbr:
            existing_ids = {str(r.get("player_id"))
                            for r in team_dict["players"]
                            if r.get("player_id") is not None}
            existing_names = {(r.get("player_name") or "").lower()
                              for r in team_dict["players"]
                              if r.get("player_name")}
            for lp in players_live:
                if not isinstance(lp, dict):
                    continue
                if (lp.get("team") or "").upper() != team_abbr:
                    continue
                lp_id = str(lp.get("player_id") or "")
                lp_nm = (lp.get("player") or lp.get("player_name") or lp.get("name") or "")
                if (lp_id and lp_id in existing_ids) or (lp_nm and lp_nm.lower() in existing_names):
                    continue
                # Build current stats from the snapshot
                _cur: dict = {}
                for s in _BOX_STATS:
                    v = lp.get(s)
                    if v is None and isinstance(lp.get("stats"), dict):
                        v = lp["stats"].get(s)
                    if v is not None:
                        try:
                            _cur[s] = float(v)
                        except (TypeError, ValueError):
                            pass
                # Parse minutes
                _mp_raw = lp.get("minutes") or lp.get("min") or lp.get("mp")
                _mp = None
                if isinstance(_mp_raw, (int, float)):
                    _mp = float(_mp_raw)
                elif isinstance(_mp_raw, str) and ":" in _mp_raw:
                    try:
                        _mm, _ss = _mp_raw.split(":", 1)
                        _mp = int(_mm) + int(_ss) / 60.0
                    except Exception:
                        _mp = None
                elif isinstance(_mp_raw, str):
                    try:
                        _mp = float(_mp_raw)
                    except ValueError:
                        _mp = None
                # Projection for off-roster snapshot players (bench/call-ups).
                # PREFER the live_engine projection (clock-share aware, floored)
                # — the naive current*36/mp explodes for low-minute players (a
                # 3-min rookie with 2 pts -> 23.8). Engine is the same one used
                # for roster players; naive is only a last resort, and always
                # floored at current.
                _paced: dict = {}
                _lpk = lp_nm.lower() if lp_nm else ""
                for s in _BOX_STATS:
                    if s not in _cur:
                        continue
                    _eng = engine_projections.get((lp_id, s)) or engine_projections.get((_lpk, s))
                    _pf = None
                    if _eng and _eng.get("projected_final") is not None:
                        try:
                            _pf = round(float(_eng["projected_final"]), 1)
                        except (TypeError, ValueError):
                            _pf = None
                    if _pf is None and _mp and _mp > 1.0:
                        _pf = round(_cur[s] * (36.0 / _mp), 1)
                    if _pf is not None:
                        _paced[s] = max(_pf, round(float(_cur[s]), 1))
                _pf_raw = lp.get("pf") or lp.get("fouls") or lp.get("personal_fouls")
                try:
                    _fouls = int(_pf_raw) if _pf_raw is not None else None
                except (TypeError, ValueError):
                    _fouls = None
                new_row = {
                    "player_id": lp.get("player_id"),
                    "player_name": lp_nm,
                    "team": team_abbr,
                    # No pregame q50 projections for these players
                    "pts": None, "reb": None, "ast": None, "fg3m": None,
                    "stl": None, "blk": None, "tov": None,
                    "current": _cur,
                    "minutes_played": _mp,
                    "fouls": _fouls,
                    "paced_final": _paced or None,
                    "_off_slate_roster": True,  # debug/UI hint
                }
                team_dict["players"].append(new_row)

    if (live_overlay and isinstance(live_overlay, dict)
            and live_overlay.get("players")
            and int(live_overlay.get("period") or 0) >= 1):
        attach_live(box.get("away"))
        attach_live(box.get("home"))
        box["live_available"] = True
        box["engine_projection_used"] = bool(engine_projections)

        # ── Bayesian shrinkage toward pregame q50 ─────────────────────────
        # Early in the game (low minutes_played), pace extrapolation is
        # dominated by noise — a star with 3 minutes and 0 PTS would project
        # to 0-PTS final, which is silly when his pregame median is 27. Blend
        # live extrapolation with the pregame q50 (the prior). Weight grows
        # with minutes: at 4 min ~90% pregame; at 14 min 50/50; at 24 min
        # ~93% live; at 36+ min ~100% live. See _live_shrink_weight.
        def _shrink_team(team_dict):
            if not team_dict or not team_dict.get("players"):
                return
            for row in team_dict["players"]:
                mp = row.get("minutes_played") or 0
                w_live = _live_shrink_weight(mp)
                row["_shrink_weight"] = round(w_live, 3)
                paced = row.get("paced_final") or {}
                if w_live <= 0:
                    # Player has not entered the game (0 min). Show the pregame
                    # ROLE projection (per-player q50) rather than the engine's
                    # flat replacement-level default (~5.7 pts for EVERYONE),
                    # which made benched/inactive players show identical chunky
                    # lines and inflated the team sum. Floored at current.
                    for s in _BOX_STATS:
                        pregame_v = row.get(s)
                        if pregame_v is None:
                            continue
                        try:
                            _cur0 = (row.get("current") or {}).get(s)
                            _pv0 = float(pregame_v)
                            if _cur0 is not None:
                                _pv0 = max(_pv0, float(_cur0))
                            paced[s] = round(_pv0, 1)
                        except (TypeError, ValueError):
                            continue
                    if paced:
                        row["paced_final"] = paced
                    continue
                for s in _BOX_STATS:
                    pregame_v = row.get(s)            # pregame q50 (cell value)
                    live_v = paced.get(s)             # live engine projection
                    if pregame_v is None or live_v is None:
                        continue
                    try:
                        _cur = (row.get("current") or {}).get(s)
                        _pv = float(pregame_v)
                        # A player who has ALREADY exceeded his pregame median is
                        # having an outlier game — don't regress him toward the
                        # season prior below what he's already recorded. Clamp the
                        # prior at current so the blend still credits remaining
                        # production (live_v adds it) instead of projecting a
                        # final at/below the current total (e.g. 9 reb -> proj 9).
                        if _cur is not None:
                            _pv = max(_pv, float(_cur))
                        blended = w_live * float(live_v) + (1.0 - w_live) * _pv
                        if _cur is not None:
                            blended = max(blended, float(_cur))
                        paced[s] = round(blended, 1)
                    except (TypeError, ValueError):
                        continue
                if paced:
                    row["paced_final"] = paced

        _shrink_team(box.get("away"))
        _shrink_team(box.get("home"))

        # ── LIVE AVAILABILITY: detect players who have LEFT the game (injury /
        # did-not-return) and CAP their projection at current. The official box
        # feed CANNOT flag a mid-game injury — a hurt star reads status=ACTIVE,
        # oncourt=0, notPlayingReason="" — identical to a normal bench rest. So
        # we use (1) an operator manual-out list (reliable, immediate) and
        # (2) minutes-stagnation (a rotation player whose minutes are frozen
        # across ~6+ wall-min of live play is not on the floor). Without this a
        # hurt star (e.g. Brunson → locker room) keeps projecting his full line.
        try:
            import json as _ij_out  # noqa: PLC0415
            _out_names: set = set()
            _man_path = _ROOT / "data" / "cache" / "cv_fix" / f"live_out_{date}.json"
            if _man_path.exists():
                try:
                    _ml = _ij_out.loads(_man_path.read_text(encoding="utf-8-sig"))
                    _out_names = {str(n).strip().lower() for n in _ml if str(n).strip()}
                except Exception:
                    _out_names = set()
            # CV_OUT_DETECT_HARDEN: hardened stagnation detector.
            # When OFF: auto detection is disabled (_stale always False) —
            # byte-identical to the original safe manual-only path.
            # When ON: require minutes flat across TWO consecutive ~6-min
            # windows (>=12 wall-min total), ALL three windows in active
            # play (no quarter-break), AND stagnation must SPAN a period
            # boundary (now in period P but 12-min-back was period P-1) —
            # this eliminates bench stints (within-period rests) while
            # catching true mid-game exits (injury that keeps a player
            # off-court from one period into the next).
            _out_harden = (os.environ.get("CV_OUT_DETECT_HARDEN", "0").strip() == "1")
            # CV_INGAME_RETURN: player RETURN / clear-OUT branch.
            # When OFF: no return path — if a player is in _out_names (manual)
            # or flagged stale, the cap is permanent for this request.
            # When ON: (1) load live_return_{date}.json — names here are
            # explicitly returned and OVERRIDE the out list; (2) detect
            # auto-return via minutes-resume: if a player was stale at T-6
            # (their T-6 and T-12 minutes were equal across a period boundary)
            # AND their current minutes exceed T-6 by >=0.3, they are BACK —
            # clear the out flag, fall through to normal blending with a
            # conservative 75% remaining-rate scale (reduced-minutes anchor).
            _ingame_return = (os.environ.get("CV_INGAME_RETURN", "0").strip() == "1")

            # Helper: parse clock string "MM:SS" to float minutes remaining
            def _clock_to_min(clk: str) -> float:
                try:
                    _mm, _ss = clk.strip().split(":", 1)
                    return int(_mm) + int(_ss) / 60.0
                except Exception:
                    return 6.0  # default: non-zero = not a break

            # Helper: is a snapshot in a quarter-break window?
            # Guards BOTH ends: clock <= 0:30 (just ended) OR >= 11:30
            # (just started = players still subbing in from the bench).
            # This prevents flagging starters who haven't entered yet at
            # the very start of a quarter.
            def _is_quarter_break(ov: dict) -> bool:
                _period = int(ov.get("period") or 0)
                if _period < 1:
                    return True  # pre-game
                _clk_s = str(ov.get("clock") or "6:00")
                _clk_min = _clock_to_min(_clk_s)
                return _clk_min <= 0.5 or _clk_min >= 11.5

            # Load historical snapshots for stagnation detection
            _prev_min: dict = {}    # minutes ~6-min back
            _prev2_min: dict = {}   # minutes ~12-min back
            _period_6: int = 0      # game period at ~6-min-back snapshot
            _period_12: int = 0     # game period at ~12-min-back snapshot
            _qbreak_6: bool = False
            _qbreak_12: bool = False
            try:
                _snaps_av = _epoch_snaps(_LIVE_DIR_PATH, game_id)
                if len(_snaps_av) >= 2:
                    def _epoch_of(p):
                        try:
                            return int(p.stem.split("_")[-1])
                        except Exception:
                            return 0
                    _latest_e = _epoch_of(_snaps_av[-1])
                    # Window 1: ~6 wall-min back (360,000 ms)
                    _cmp = min(_snaps_av, key=lambda p: abs(_epoch_of(p) - (_latest_e - 360_000)))
                    if _epoch_of(_cmp) <= _latest_e - 180_000:  # >=3 min back
                        _cd = _ij_out.loads(_cmp.read_text(encoding="utf-8"))
                        _period_6 = int(_cd.get("period") or 0)
                        _qbreak_6 = _is_quarter_break(_cd)
                        for _lp in (_cd.get("players") or []):
                            _nm0 = (_lp.get("name") or _lp.get("player_name") or "").lower()
                            _mn0 = _lp.get("min")
                            if _nm0 and isinstance(_mn0, (int, float)):
                                _prev_min[_nm0] = float(_mn0)
                    # Window 2: ~12 wall-min back (720,000 ms) — only loaded
                    # when the hardened flag is ON so flag-OFF is byte-identical.
                    if _out_harden and len(_snaps_av) >= 3:
                        _cmp2 = min(_snaps_av, key=lambda p: abs(_epoch_of(p) - (_latest_e - 720_000)))
                        if _epoch_of(_cmp2) <= _latest_e - 480_000:  # >=8 min back
                            _cd2 = _ij_out.loads(_cmp2.read_text(encoding="utf-8"))
                            _period_12 = int(_cd2.get("period") or 0)
                            _qbreak_12 = _is_quarter_break(_cd2)
                            for _lp2 in (_cd2.get("players") or []):
                                _nm2 = (_lp2.get("name") or _lp2.get("player_name") or "").lower()
                                _mn2 = _lp2.get("min")
                                if _nm2 and isinstance(_mn2, (int, float)):
                                    _prev2_min[_nm2] = float(_mn2)
            except Exception:
                _prev_min = {}
                _prev2_min = {}

            # CV_INGAME_RETURN: load manual return list and build prev-out set.
            # Only loaded when flag is ON (no extra I/O when flag OFF).
            _return_names: set = set()
            _prev_out_set: set = set()
            if _ingame_return:
                # Manual return file: operators drop a name here to un-cap a
                # player who was in live_out_{date}.json and then returned.
                _ret_path = _ROOT / "data" / "cache" / "cv_fix" / f"live_return_{date}.json"
                if _ret_path.exists():
                    try:
                        _rl = _ij_out.loads(_ret_path.read_text(encoding="utf-8-sig"))
                        _return_names = {str(n).strip().lower() for n in _rl if str(n).strip()}
                    except Exception:
                        _return_names = set()
                # Build the set of players who were stale AT T-6.
                # A player was stale at T-6 if:
                #   * their T-6 and T-12 minutes are equal (flat across the window)
                #   * period changed between T-12 and T-6 (cross-boundary)
                # This mirrors the hardened stagnation rule applied at T-6.
                # Used by the return-detection branch below.
                if _prev_min and _prev2_min and _period_6 != _period_12 and _period_12 > 0:
                    for _pn, _pm6 in _prev_min.items():
                        _pm12 = _prev2_min.get(_pn)
                        if _pm12 is not None and abs(_pm6 - _pm12) < 0.05 and _pm6 > 0.5:
                            _prev_out_set.add(_pn)

            # Pre-compute quarter-break guard for current snapshot
            _period_now = int((live_overlay or {}).get("period") or 0) if live_overlay else 0
            _qbreak_now = (
                _is_quarter_break(live_overlay)
                if (live_overlay and isinstance(live_overlay, dict))
                else False
            )

            for _td in (box.get("home"), box.get("away")):
                if not _td or not _td.get("players"):
                    continue
                for _row in _td["players"]:
                    _nm = (_row.get("player_name") or "").lower()
                    _mp = _row.get("minutes_played") or 0
                    _manual = _nm in _out_names
                    if _out_harden:
                        # Hardened cross-period stagnation detector:
                        # (a) player has played (>0.5 min, not DNP)
                        # (b) minutes flat in BOTH ~6-min AND ~12-min windows
                        # (c) NONE of the 3 windows is in a quarter-break zone
                        #     (clock <=0:30 or >=11:30)
                        # (d) period CHANGED from the 12-min-back window to
                        #     now — stagnation must SPAN a quarter boundary.
                        #     This is the decisive filter: bench stints within
                        #     a single quarter (KAT/OG/Wemb sitting in Q2)
                        #     have period_12 == period_now and never fire.
                        #     True exits (Brunson, ankle, Q1->Q2) span periods.
                        _stale = False
                        if (
                            float(_mp) > 0.5               # has played
                            and _nm in _prev_min           # seen 6-min back
                            and _nm in _prev2_min          # seen 12-min back
                            and not _qbreak_now            # current not break
                            and not _qbreak_6              # 6-min back not break
                            and not _qbreak_12             # 12-min back not break
                            and _period_now != _period_12  # period changed
                        ):
                            _mp6 = _prev_min[_nm]
                            _mp12 = _prev2_min[_nm]
                            # Both windows must show zero growth (flat minutes)
                            if (abs(float(_mp) - _mp6) < 0.05
                                    and abs(_mp6 - _mp12) < 0.05):
                                _stale = True
                    else:
                        # Flag OFF -- byte-identical to original disabled path.
                        # auto minutes-stagnation DISABLED: a star's normal ~6-min
                        # rest is indistinguishable from an injury in the box feed,
                        # so it false-flagged healthy resters (e.g. Wembanyama
                        # capped at 9 while just resting). Manual-only until the
                        # PBP-based did-not-return detector is wired.
                        _stale = False
                        _ = _prev_min  # retained for the future PBP detector
                    # CV_INGAME_RETURN: detect player return BEFORE applying the
                    # OUT cap.  A player is "returned" when:
                    #   (a) explicit manual return: name in live_return_{date}.json, OR
                    #   (b) auto-return: they were in _prev_out_set (stale at T-6)
                    #       AND their current minutes exceed T-6 minutes by >=0.3.
                    # Return wins over manual-out: a name in both live_out and
                    # live_return is treated as returned (live_return is more recent).
                    # When returned, apply a 75% remaining-rate scale on the live
                    # portion of paced_final — conservative reduced-minutes anchor
                    # (player may not play full expected load after coming back).
                    if _ingame_return:
                        _auto_return = (
                            _nm in _prev_out_set
                            and _nm in _prev_min
                            and (float(_mp) - _prev_min[_nm]) >= 0.3
                        )
                        _returned = (_nm in _return_names) or _auto_return
                        if _returned:
                            # Clear the manual flag so the OUT cap below is skipped.
                            _manual = False
                            _stale = False
                            # Apply reduced-minutes anchor: scale the live paced_final
                            # toward current stats (75% of the live engine's extra).
                            # This re-inflates the line but conservatively caps upside.
                            _RETURN_SCALE = 0.75
                            _cur_r = _row.get("current") or {}
                            _pf_r = dict(_row.get("paced_final") or {})
                            for _s in _BOX_STATS:
                                _cv_r = _cur_r.get(_s)
                                _pv_r = _pf_r.get(_s)
                                if _cv_r is not None and _pv_r is not None:
                                    try:
                                        _extra = float(_pv_r) - float(_cv_r)
                                        _scaled = float(_cv_r) + _RETURN_SCALE * max(0.0, _extra)
                                        _pf_r[_s] = round(_scaled, 1)
                                    except (TypeError, ValueError):
                                        pass
                            if _pf_r:
                                _row["paced_final"] = _pf_r
                            _row["availability"] = "RETURNED -- reduced-minutes anchor"
                            _row["_returned_flag"] = True
                    if _manual or _stale:
                        _cur = _row.get("current") or {}
                        _pf = dict(_row.get("paced_final") or {})
                        for _s in _BOX_STATS:
                            _cv = _cur.get(_s)
                            if _cv is not None:
                                _pf[_s] = round(float(_cv), 1)
                        _row["paced_final"] = _pf
                        _row["availability"] = ("OUT -- ruled out" if _manual
                                                else "OUT? -- no minutes ~12m (did not return)")
                        _row["_out_flag"] = True
        except Exception:
            pass

        # ── Pace-aware team total projection ──────────────────────────────
        # Sum of player paced_finals undershoots team totals during the
        # game because each player's projection has been shrunk toward q50
        # (the median). Real team totals are means, which are higher for
        # right-skewed scoring distributions.
        #
        # Build a separate team-total projection that uses:
        #   pace_extrap = current_team_pts × (48 / minutes_elapsed)
        # blended with the pregame team mean estimate.
        period_i = int(live_overlay.get("period") or 0)
        clock_min = _parse_clock_to_minutes(live_overlay.get("clock"))
        # Total game minutes elapsed: full periods done + (12 - clock) for current
        if period_i >= 1 and clock_min is not None:
            full_periods_done = max(0, period_i - 1)
            minutes_elapsed = full_periods_done * 12.0 + (12.0 - clock_min)
            minutes_elapsed = max(1.0, min(48.0, minutes_elapsed))
        else:
            minutes_elapsed = 0.0

        def _team_total_proj(team_dict):
            if not team_dict:
                return
            elapsed_frac = minutes_elapsed / 48.0
            current_totals: dict[str, float] = {}
            projected_totals: dict[str, float] = {}
            pace_extraps: dict[str, float] = {}
            for s in _BOX_STATS:
                cur_sum = 0.0
                any_v = False
                for row in team_dict.get("players") or []:
                    cur = row.get("current") or {}
                    v = cur.get(s)
                    if v is None:
                        continue
                    try:
                        cur_sum += float(v); any_v = True
                    except (TypeError, ValueError):
                        continue
                if any_v:
                    current_totals[s] = round(cur_sum, 1)
                # For PTS, prefer the snapshot's authoritative team-level
                # score over the player-summed total. Reason: the pre-game
                # roster used by _build_box_score can lag the live roster
                # (e.g. late call-ups like Jalen Williams), so summing
                # per-player current.pts misses any player who isn't on the
                # pregame list — visible as "OKC shows 1 less than actual".
                # The snapshot's home_score/away_score comes straight from
                # the NBA scoreboard and is always correct.
                if s == "pts":
                    _is_home = team_dict.get("abbr") == (live_overlay.get("home_team") or "")
                    _team_score = live_overlay.get("home_score") if _is_home else live_overlay.get("away_score")
                    if isinstance(_team_score, (int, float)):
                        current_totals[s] = float(_team_score)
                pregame_mean = (team_dict.get("mean_totals") or {}).get(s)
                if not isinstance(pregame_mean, (int, float)):
                    pregame_mean = None
                # BUG 14 FIX: use the authoritative current total (which may
                # have been overridden by the scoreboard for 'pts') as the
                # pace base instead of the raw player-summed cur_sum. This
                # ensures projected_total_pts (and win-prob) reflects the
                # correct live score when the pregame roster lags.
                pace_extrap = None
                _pace_base = current_totals.get(s, cur_sum)
                if minutes_elapsed >= 1.0 and _pace_base > 0:
                    pace_extrap = _pace_base * (48.0 / minutes_elapsed)
                    pace_extraps[s] = round(pace_extrap, 1)
                # Blend pace × pregame mean by elapsed_frac. When elapsed_frac=0,
                # we trust pregame; when elapsed_frac=1, we trust the pace.
                if pace_extrap is not None and pregame_mean is not None:
                    projected = elapsed_frac * pace_extrap + (1.0 - elapsed_frac) * pregame_mean
                elif pace_extrap is not None:
                    projected = pace_extrap
                else:
                    projected = pregame_mean
                if projected is not None:
                    projected_totals[s] = round(float(projected), 1)
            team_dict["current_totals"] = current_totals
            team_dict["pace_extraps"] = pace_extraps
            team_dict["projected_totals"] = projected_totals
            # PTS-specific convenience fields (backward compat with JS pill)
            if "pts" in current_totals:
                team_dict["current_total_pts"] = current_totals["pts"]
            if "pts" in projected_totals:
                team_dict["projected_total_pts"] = projected_totals["pts"]
            if "pts" in pace_extraps:
                team_dict["pace_extrap_pts"] = pace_extraps["pts"]

        _team_total_proj(box.get("away"))
        _team_total_proj(box.get("home"))

        # FULL-SEND: when the validated possession sim ran (CV_INGAME_SBS on), serve
        # the SIMULATED final score as the team projection instead of the naive pace
        # extrapolation above. The possession-sim / ridge team total beats pace
        # extrapolation decisively on held-out data (total MAE ~10 vs ~21), so the
        # live win-prob below (computed from projected_total_pts) reflects a Monte
        # Carlo game simulation rather than linear extrapolation. Falls back to the
        # pace projection if no finite sim score is present (flag off / sim absent).
        try:
            import math as _math_sim  # noqa: PLC0415
            _any_eng = next(iter(engine_projections.values()), None)
            if _any_eng is not None:
                _ph_sim = _any_eng.get("proj_home_final")
                _pa_sim = _any_eng.get("proj_away_final")
                _src_sim = _any_eng.get("proj_point_source") or "possession_sim"
                _fin = lambda x: isinstance(x, (int, float)) and _math_sim.isfinite(x)
                if _fin(_ph_sim) and _fin(_pa_sim):
                    # BUG 5b FIX: floor sim projected final at the live current
                    # score so the page never shows a projected final below the
                    # scoreboard (belt-and-suspenders; the per-player floor is
                    # already applied inside the ridge head at ~5168).
                    _live_home = float(live_overlay.get("home_score") or 0)
                    _live_away = float(live_overlay.get("away_score") or 0)
                    _ph_sim = max(float(_ph_sim), _live_home)
                    _pa_sim = max(float(_pa_sim), _live_away)
                    if isinstance(box.get("home"), dict):
                        box["home"]["projected_total_pts"] = round(_ph_sim, 1)
                        box["home"]["projected_total_pts_source"] = _src_sim
                    if isinstance(box.get("away"), dict):
                        box["away"]["projected_total_pts"] = round(_pa_sim, 1)
                        box["away"]["projected_total_pts_source"] = _src_sim
        except Exception:
            pass
    else:
        box["live_available"] = False
        box["engine_projection_used"] = False

    # Pregame win probability — projection-derived helper (see
    # _pregame_wp_from_projection for math). Stays consistent with the box
    # score and avoids the polarity-bug team-level model.
    p_home_pre, _wp_src = _pregame_home_wp(date, away_a, home_a)
    if p_home_pre is not None:
        box["pregame_home_win_prob"] = round(p_home_pre, 3)
        box["pregame_away_win_prob"] = round(1.0 - p_home_pre, 3)
        box["pregame_wp_source"] = _wp_src

    # Live win probability — call the appropriate snapshot booster for the
    # current period. Boosters are calibrated at end-of-period boundaries
    # (clock 0:00). We interpolate toward 0.5 (uninformative) when the clock
    # is far from the boundary, since the booster is out-of-distribution
    # mid-period and would otherwise be overconfident.
    if live_overlay and isinstance(live_overlay, dict):
        period_i = int(live_overlay.get("period") or 0)
        if period_i >= 1:
            snap_key = "endQ1" if period_i <= 1 else ("endQ2" if period_i == 2 else "endQ3")
            try:
                from src.prediction.inplay_winprob import (  # noqa: PLC0415
                    features_from_snapshot, predict_home_win_prob,
                    active_stack,
                )
                # The trained boosters require per-quarter score arrays and
                # are only valid at end-of-quarter boundaries (period=N+1,
                # clock=12:00). The orchestrator writes snapshots every 10s
                # with only total scores. Walk historical snapshots to find
                # the most-recent end-of-quarter boundary, reconstruct
                # home_q1/q2/q3 from the period transitions, and feed the
                # model. WP "holds" between boundaries (matches training).
                import json as _wp_json  # noqa: PLC0415
                snap_files = (
                    _epoch_snaps(live_dir, game_id) if live_dir.exists() else [])
                # Also include canonical_ids
                for _gid in canonical:
                    if _gid == game_id:
                        continue
                    snap_files.extend(
                        _epoch_snaps(live_dir, _gid)
                        if live_dir.exists() else [])
                snap_files = sorted(set(snap_files))
                # Final score per period: take the LAST snapshot whose period
                # equals that period (i.e. the score at end of that period).
                last_total_by_period: dict[int, tuple[int, int]] = {}
                for sf in snap_files:
                    try:
                        sd = _wp_json.loads(sf.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    sp = sd.get("period")
                    if isinstance(sp, int) and sp >= 1:
                        hs = sd.get("home_score"); as_ = sd.get("away_score")
                        if hs is not None and as_ is not None:
                            last_total_by_period[sp] = (int(hs), int(as_))
                # Reconstruct per-quarter splits from cumulative-at-end-of-each-Q
                cum_h = {p: ht for p, (ht, _) in last_total_by_period.items()}
                cum_a = {p: at for p, (_, at) in last_total_by_period.items()}
                completed_qs = sorted(p for p in cum_h.keys() if p < period_i)
                # If current period itself is at clock 0:00, that's the end of
                # this period — treat it as completed too.
                _cur_clock = str(live_overlay.get("clock") or "").strip()
                if _cur_clock in ("0:00", "00:00", "0", "0.0", "") and period_i in (1, 2, 3):
                    completed_qs = sorted(set(completed_qs + [period_i]))
                # Build wp_snap with the model's expected schema.
                wp_snap = dict(live_overlay)
                # Inject the pregame WP anchor so the v3/v6 pregame-anchored
                # boosters keep their pregame prior (features_from_snapshot
                # reads snap["pregame_win_prob"]; without this it defaults to
                # ~0.55 and the in-play WP loses its pregame anchor).
                if p_home_pre is not None:
                    wp_snap["pregame_win_prob"] = float(p_home_pre)
                # Per-quarter scores from completed quarters
                prev_h, prev_a = 0, 0
                for q in (1, 2, 3):
                    if q in completed_qs:
                        cur_h_val = cum_h.get(q, prev_h)
                        cur_a_val = cum_a.get(q, prev_a)
                        wp_snap[f"home_q{q}"] = cur_h_val - prev_h
                        wp_snap[f"away_q{q}"] = cur_a_val - prev_a
                        prev_h, prev_a = cur_h_val, cur_a_val
                # Pick snap_key based on completed quarters (NOT the live period
                # field). The WP "holds" at the last completed-quarter value.
                if 3 in completed_qs:
                    snap_key = "endQ3"
                    wp_snap["period"] = 4
                elif 2 in completed_qs:
                    snap_key = "endQ2"
                    wp_snap["period"] = 3
                elif 1 in completed_qs:
                    snap_key = "endQ1"
                    wp_snap["period"] = 2
                else:
                    # Q1 not complete yet — no in-play WP available
                    raise RuntimeError("pre-endQ1: no in-play WP")
                wp_snap["clock"] = "12:00"
                feats = features_from_snapshot(wp_snap)
                p_home_raw = predict_home_win_prob(feats, snapshot=snap_key)
                if p_home_raw is not None:
                    # We're already serving the held boundary value (via
                    # historical-snapshot reconstruction above), so no
                    # interpolation toward 0.5 is needed — the booster output
                    # IS the valid boundary WP.
                    p_home = float(p_home_raw)
                    # Blend with the PREGAME MARKET win prob so the live number
                    # doesn't over-react to an early lead (e.g. SAS up 3 at half
                    # but OKC the pregame favorite -> model said SAS ~60%, market
                    # ~53%). Trust the live read more as the game progresses.
                    if p_home_pre is not None:
                        _wpw = {"endQ1": 0.40, "endQ2": 0.60, "endQ3": 0.80}.get(snap_key, 0.6)
                        p_home = _wpw * p_home + (1.0 - _wpw) * float(p_home_pre)
                    clock_min = _parse_clock_to_minutes(live_overlay.get("clock"))
                    box["home_win_prob"] = round(p_home, 3)
                    box["away_win_prob"] = round(1.0 - p_home, 3)
                    box["winprob_snapshot"] = snap_key
                    box["winprob_blended_market"] = p_home_pre is not None
                    box["winprob_raw_booster"] = round(float(p_home_raw), 3)
                    if clock_min is not None:
                        box["winprob_clock_minutes"] = round(clock_min, 2)
                    # Honest provenance: surface which artifact stack drove
                    # this probability so the UI tooltip / status pill can
                    # show the user it's the validated model, not v1 raw.
                    try:
                        stack = active_stack(snap_key)
                        box["winprob_stack"] = {
                            "layer": stack.get("layer"),
                            "detail": stack.get("detail"),
                            "components_loaded": {
                                "v6_hp": bool(stack.get("v6_hp_loaded")),
                                "iter62_iso": bool(stack.get("iter62_iso_loaded")),
                                "v7_bag5": bool(stack.get("v7_bag5_loaded")),
                                "meta_blend": bool(stack.get("meta_blend_loaded")),
                                "v3": bool(stack.get("v3_loaded")),
                                "v2": bool(stack.get("v2_loaded")),
                                "v1": bool(stack.get("v1_loaded")),
                            },
                        }
                    except Exception as _stack_exc:
                        import logging as _lg_stack  # noqa: PLC0415
                        _lg_stack.getLogger(__name__).warning(
                            "active_stack(%s) failed: %s", snap_key, _stack_exc)
            except Exception as exc:
                import logging as _lg3  # noqa: PLC0415
                _lg3.getLogger(__name__).warning(
                    "inplay_winprob failed: %s", exc)

    # BUG 12/13 FIX: in Q4 the possession-sim WP (attached as home_win_prob_inplay
    # with winprob_source='possession_sim' on engine rows) is validated better than
    # _live_wp_continuous (Brier 0.126 vs 0.136). Promote it before the
    # _live_wp_continuous overwrite block and SKIP the overwrite for that case.
    # Only fires in Q4 when an engine row has a finite sim WP; outside Q4 the
    # _live_wp_continuous overwrite runs unchanged.
    _skip_continuous_wp = False
    try:
        if (live_overlay and isinstance(live_overlay, dict)
                and int(live_overlay.get("period") or 0) >= 4
                and engine_projections):
            import math as _math_wp  # noqa: PLC0415
            _swp = None
            for _er in engine_projections.values():
                if (_er.get("winprob_source") == "possession_sim"
                        and _er.get("home_win_prob_inplay") is not None):
                    _candidate = float(_er["home_win_prob_inplay"])
                    if _math_wp.isfinite(_candidate):
                        _swp = _candidate
                        break
            if _swp is not None:
                box["home_win_prob"] = round(_swp, 3)
                box["away_win_prob"] = round(1.0 - _swp, 3)
                box["winprob_source"] = "possession_sim"
                _skip_continuous_wp = True
    except Exception:
        pass

    # ALWAYS-UPDATING live win prob: the boundary booster above only changes 3x
    # a game ("holds" between quarters). This recomputes EVERY snapshot from the
    # live score margin + time remaining, anchored to the pregame MARKET wp, so
    # the number moves continuously and doesn't over-react to a lead. Supersedes
    # the held value for display (the booster value is kept in winprob_raw_booster).
    try:
        if (not _skip_continuous_wp
                and live_overlay and isinstance(live_overlay, dict) and live_overlay.get("period")):
            _hp = (box.get("home") or {}).get("projected_total_pts")
            _ap = (box.get("away") or {}).get("projected_total_pts")
            _lwp = _live_wp_continuous(live_overlay, p_home_pre, _hp, _ap)
            if _lwp is not None:
                box["home_win_prob"] = round(_lwp, 3)
                box["away_win_prob"] = round(1.0 - _lwp, 3)
                box["winprob_source"] = ("live_projected_final_score"
                                         if (_hp is not None and _ap is not None)
                                         else "live_continuous_market_anchored")
                box["winprob_proj_score"] = (f"{round(_ap)}-{round(_hp)}"
                                             if (_hp is not None and _ap is not None) else None)
    except Exception:
        pass

    # ── COHERENCE FIX: reconcile the displayed projected final score with the
    # (market-anchored) win probability. The possession-sim per-team split can
    # briefly invert the favorite early in the game (over-reacting to a small
    # lead), leaving the end score contradicting the win % (e.g. a 58% home
    # favorite projected to LOSE). Keep the sim's TOTAL (validated, ~Vegas) and
    # re-split it by the win-prob-implied margin so end-score, team total, and
    # win % all agree. margin(home) = k*ln(p/(1-p)); k=9.5 → 63%≈+5, 58%≈+3.
    try:
        import math as _math_coh  # noqa: PLC0415
        _hb = box.get("home"); _ab = box.get("away")
        _p = box.get("home_win_prob")
        if (isinstance(_hb, dict) and isinstance(_ab, dict)
                and isinstance(_p, (int, float))):
            _ht = _hb.get("projected_total_pts"); _at = _ab.get("projected_total_pts")
            if isinstance(_ht, (int, float)) and isinstance(_at, (int, float)):
                _T = float(_ht) + float(_at)
                _pp = min(0.99, max(0.01, float(_p)))
                _margin = 9.5 * _math_coh.log(_pp / (1.0 - _pp))
                _home_final = (_T + _margin) / 2.0
                _away_final = (_T - _margin) / 2.0
                _lh = float((live_overlay or {}).get("home_score") or 0)
                _la = float((live_overlay or {}).get("away_score") or 0)
                # CV_FINAL_SCORE_FREEZE (default OFF = byte-identical): on a FINAL
                # game the projected final IS the actual final — the win-prob→margin
                # reconcile otherwise maps a ~0.95 end win-prob to a ~+27 implied
                # margin and shows a distorted projected score (e.g. 104-120 for a
                # real 104-108). Freeze to the live scores. Display-only, post-game.
                if (os.environ.get("CV_FINAL_SCORE_FREEZE", "").strip().lower()
                        not in ("", "0", "false", "no", "off")
                        and "FINAL" in str((live_overlay or {}).get("game_status") or "").upper()):
                    _home_final = _lh
                    _away_final = _la
                _home_final = max(_home_final, _lh)
                _away_final = max(_away_final, _la)
                _hb["projected_total_pts"] = round(_home_final, 1)
                _ab["projected_total_pts"] = round(_away_final, 1)
                # keep the bottom "Total" PTS cell coherent with the pill/score
                if isinstance(_hb.get("projected_totals"), dict):
                    _hb["projected_totals"]["pts"] = round(_home_final, 1)
                if isinstance(_ab.get("projected_totals"), dict):
                    _ab["projected_totals"]["pts"] = round(_away_final, 1)
                box["winprob_proj_score"] = f"{round(_away_final)}-{round(_home_final)}"
                box["winprob_source"] = "winprob_reconciled"
    except Exception:
        pass

    # Live-regraded bet snippets for this matchup. The JS poller inline-updates
    # the bet cards' EV / model_prob / side text so they don't go stale during
    # the game (without a full page reload).
    if engine_projections and game_id:
        try:
            slate_cur = _build_slate(date)
            sig_table = _stat_sigma_for_date(date)
            from api._courtvision_odds import resolve_game_id  # noqa: PLC0415
            alias_for_filter = resolve_game_id(game_id)
            canon_ids = alias_for_filter.get("canonical_ids", frozenset([game_id]))
            ab = (alias_for_filter.get("away_abbr") or "").upper()
            hb = (alias_for_filter.get("home_abbr") or "").upper()
            pair = frozenset([ab, hb]) if ab and hb else frozenset()

            def _in_game(b):
                if str(b.get("game_id", "")) in canon_ids:
                    return True
                if pair:
                    t = (b.get("team") or "").upper()
                    o = (b.get("opp") or "").upper()
                    if t in pair and o in pair:
                        return True
                return False

            import copy as _copy2  # noqa: PLC0415
            live_bets = []
            player_minutes = _shrink_player_minutes_from_snapshot(live_overlay or {})
            # Collapsed in-play line history for this matchup — drives the
            # line-movement fields on each live bet (graceful nulls if absent).
            try:
                lm_hist = _load_inplay_line_history(date, canon_ids)
            except Exception:
                lm_hist = []
            for b in slate_cur.get("bets", []):
                if not _in_game(b):
                    continue
                nm = (b.get("player_name") or "").lower()
                st = (b.get("prop_stat") or "").lower()
                eng = engine_projections.get((nm, st))
                if not eng or eng.get("projected_final") is None:
                    continue
                # deepcopy so regrade never mutates the cached slate's bet dict.
                cp = _copy2.deepcopy(b)
                # Apply minutes-based shrinkage so early-game projections blend
                # toward pregame q50 instead of trusting noisy extrapolation.
                mp = player_minutes.get(nm, 0.0)
                w_live = _live_shrink_weight(mp)
                live_q50_raw = float(eng["projected_final"])
                pregame_q50 = float(cp.get("q50") or live_q50_raw)
                shrunk_q50 = w_live * live_q50_raw + (1.0 - w_live) * pregame_q50
                # Bug 2 fix (site a): floor shrunk_q50 at already-accumulated current
                # stat so a hot-start player's projection never goes BELOW current.
                _cur_a = eng.get("current")
                if _cur_a is not None:
                    try:
                        shrunk_q50 = max(shrunk_q50, float(_cur_a))
                    except (TypeError, ValueError):
                        pass
                # Belt-and-suspenders: if the player's current stat already clears
                # the line on the recommended UNDER side, the bet is already settled
                # against us — drop it before it reaches the live card ranking.
                try:
                    _line_a = float(cp.get("line") or 0.0)
                    _side_a = (cp.get("side") or "").upper()
                    if (_cur_a is not None and _side_a == "UNDER"
                            and float(_cur_a) >= _line_a):
                        continue
                except (TypeError, ValueError):
                    pass
                # RE-ANCHOR to the LIVE in-play line: the sportsbook moves the
                # O/U line during the game (e.g. Wemby pts 24.5 -> 22.5), so the
                # card must show the CURRENT line + live per-book prices, not the
                # frozen pregame line. Replace the stale pregame ladder with the
                # latest in-play quote per book and set the line to the freshest.
                _ip_by_book: dict = {}
                for _r in lm_hist:
                    if _r.get("name") == nm and _r.get("stat") == st:
                        _bk = _r.get("book") or "live"
                        if _bk not in _ip_by_book or _r["cap"] > _ip_by_book[_bk]["cap"]:
                            _ip_by_book[_bk] = _r
                # No live in-play line for this prop (the book doesn't offer it
                # live, e.g. SGA blocks / bench-player points). It's not live-
                # bettable — drop it from the LIVE view rather than show a frozen
                # pregame line with a misleading "stale price" badge. (Still shown
                # on the pregame slate when the game isn't live.)
                if not _ip_by_book:
                    continue
                if _ip_by_book:
                    # Books can post DIFFERENT lines for the same prop. The line
                    # and the price MUST come from the SAME book — never show a
                    # 5.5 line with another book's 2.5 price. Decide the side from
                    # the projection vs the median live line, then pick the best
                    # price for that side and use THAT book's line.
                    # Decide the side from the projection vs the median live line,
                    # then anchor to the closest-to-projection line AMONG books
                    # that actually QUOTE that side. FanDuel in-play has no UNDER
                    # price, so an UNDER bet must use a book (DK) that quotes it —
                    # never show an FD line with a fallback under price. Closest-
                    # to-projection also avoids longshot ALT rungs.
                    _lines = sorted(r["line"] for r in _ip_by_book.values())
                    _med = _lines[len(_lines) // 2]
                    _side = "OVER" if shrunk_q50 >= _med else "UNDER"
                    _skey = "over" if _side == "OVER" else "under"
                    _pool = [r for r in _ip_by_book.values()
                             if r.get(_skey) is not None] or list(_ip_by_book.values())
                    _main_line = min((r["line"] for r in _pool),
                                     key=lambda ln: abs(ln - shrunk_q50))
                    cp["line"] = _main_line
                    # Regrade ladder = ONLY books quoting THIS line (so line and
                    # price always come from the SAME book — no 5.5-line/2.5-price
                    # mix). The regrade then picks the correct side + best price.
                    cp["_books_full"] = [
                        {"book": _inplay_book_label(r.get("book")),
                         "over_odds": r.get("over"), "under_odds": r.get("under"),
                         "captured_at": r.get("cap")}
                        for r in _pool if r["line"] == _main_line
                    ]
                    # Per-book display ladder — each book with ITS OWN line.
                    cp["all_books_live"] = [
                        {"book": _inplay_book_label(r.get("book")),
                         "line": r["line"], "over": r.get("over"),
                         "under": r.get("under")}
                        for r in sorted(_ip_by_book.values(), key=lambda r: r["line"])
                    ]
                # Freshness from the live in-play cap (NOT the stale pregame
                # slate age) so the card's freshness pill reads fresh, and clear
                # any stale-price flag when we DO have a fresh live quote.
                _fresh_age = None
                try:
                    from datetime import datetime as _dtf, timezone as _tzf  # noqa: PLC0415
                    _cs = []
                    for _r in _ip_by_book.values():
                        _c = (_r.get("cap") or "").replace("Z", "+00:00")
                        if not _c:
                            continue
                        _dt = _dtf.fromisoformat(_c)
                        if _dt.tzinfo is None:
                            _dt = _dt.replace(tzinfo=_tzf.utc)
                        _cs.append(_dt)
                    if _cs:
                        _fresh_age = max(0.0, (_dtf.now(_tzf.utc) - max(_cs)).total_seconds() / 60.0)
                except Exception:
                    _fresh_age = None
                cp["freshest_book_age_min"] = round(_fresh_age, 1) if _fresh_age is not None else None
                if _fresh_age is not None and _fresh_age < 15:
                    cp["live_regraded_stale_price"] = False
                try:
                    _regrade_bet_with_live_q50(cp, shrunk_q50, sig_table)
                except Exception:
                    continue
                # The live in-play quote IS fresh — the regrade's any-age fallback
                # flag is misleading here; re-clear it after the regrade too.
                if _fresh_age is not None and _fresh_age < 15:
                    cp["live_regraded_stale_price"] = False
                # Bug 1: a flipped-but-unpriced card has no real price on the
                # side it claims — exclude it from the live list rather than
                # render a wrong-side / no-price card in the ranking.
                if cp.get("live_regraded_no_price") and cp.get("best_price") is None:
                    continue
                lm = _line_movement_for(lm_hist, nm, st, shrunk_q50)
                live_bets.append({
                    "bet_id": cp.get("bet_id"),
                    "player_name": cp.get("player_name"),
                    "prop_stat": cp.get("prop_stat"),
                    "line": cp.get("line"),
                    "side": cp.get("side"),
                    "q50": cp.get("q50"),
                    "edge_units": cp.get("edge_units"),
                    "model_prob": cp.get("model_prob"),
                    "market_prob": cp.get("market_prob"),
                    "ev_pct": cp.get("ev_pct"),
                    "ev_capped": cp.get("ev_capped"),
                    "kelly_stake_dollars": cp.get("kelly_stake_dollars"),
                    "best_book": cp.get("best_book"),
                    "best_price": cp.get("best_price"),
                    "all_books": cp.get("all_books"),
                    "all_books_live": cp.get("all_books_live"),
                    "freshest_book_age_min": cp.get("freshest_book_age_min"),
                    "live_regraded_no_price": bool(cp.get("live_regraded_no_price")),
                    "live_regraded_stale_price": bool(cp.get("live_regraded_stale_price")),
                    # Surface the live projection + a LIVE flag so the card shows
                    # the updated q50 and a live badge (the regrade already ran above).
                    "live_q50": round(shrunk_q50, 2),
                    "live_regraded": True,
                    # Confidence tier from the LIVE-regraded model prob so the live
                    # card can show a "74% High" what/when-to-bet badge.
                    "conf_pct": (round(float(cp["model_prob"]), 4)
                                 if cp.get("model_prob") is not None else None),
                    "conf_tier": (("High" if cp["model_prob"] >= 0.70
                                   else ("Solid" if cp["model_prob"] >= 0.62 else "Lean"))
                                  if cp.get("model_prob") is not None else None),
                    "line_open": lm["line_open"],
                    "line_current": lm["line_current"],
                    "line_delta": lm["line_delta"],
                    "line_velocity_per_min": lm["line_velocity_per_min"],
                    "line_dir_vs_proj": lm["line_dir_vs_proj"],
                })
            if live_bets:
                box["live_bets"] = live_bets
        except Exception as exc:
            import logging as _lglb  # noqa: PLC0415
            _lglb.getLogger(__name__).warning(
                "live bets snippet build failed: %s", exc)

    box["date"] = date
    box["game_id"] = game_id
    box["generated_at"] = datetime.utcnow().isoformat() + "Z"

    # CV_LIVE_V8_SNAPSHOT (default OFF) — additive shim that enriches live_overlay
    # with a pre-built V8 snapshot before the existing _sim_panel call.
    # When ON: looks for data/cache/team_system/v8_snapshot_{game_id}.json;
    # if found, merges its keys ADDITIVELY into live_overlay (never deletes existing
    # keys) so the existing _sim_panel call gets fresher foul/lineup state.
    # When OFF or file absent: no-op — byte-identical behaviour; _sim_panel uses
    # the unmodified live_overlay from the box_poller as before.
    # DOES NOT edit live_game_simulator.py or _cv_live_sim_panel.py.
    _v8_flag_on = os.environ.get("CV_LIVE_V8_SNAPSHOT", "").strip().lower() in ("1", "true", "yes", "on")
    if _v8_flag_on and live_overlay and isinstance(live_overlay, dict):
        try:
            import json as _v8json
            _v8_path = _ROOT / "data" / "cache" / "team_system" / f"v8_snapshot_{game_id}.json"
            if _v8_path.exists():
                _v8_data = _v8json.loads(_v8_path.read_text(encoding="utf-8"))
                if isinstance(_v8_data, dict):
                    # ADDITIVE: only set keys not already present in live_overlay
                    # to avoid clobbering live state with stale V8 data.
                    for _k, _v in _v8_data.items():
                        if _k not in live_overlay:
                            live_overlay[_k] = _v
        except Exception as _v8_exc:
            import logging as _lgv8  # noqa: PLC0415
            _lgv8.getLogger(__name__).warning(
                "CV_LIVE_V8_SNAPSHOT merge failed (suppressed): %s", _v8_exc)

    # CV_LIVE_SIM gated scenario / win-prob panel (default OFF).
    # Adds a ``sim`` block ONLY when the flag is ON and a live snapshot exists.
    # When OFF, this is a pure no-op: the import is lazy inside the helper and
    # the helper returns ``box`` untouched — byte-identical response.
    try:
        from api._cv_live_sim_panel import maybe_attach_sim_panel as _sim_panel  # noqa: PLC0415
        box = _sim_panel(box, live_overlay)
    except Exception as _sim_exc:
        import logging as _lgsim  # noqa: PLC0415
        _lgsim.getLogger(__name__).warning(
            "CV_LIVE_SIM import/attach failed (suppressed): %s", _sim_exc)

    return JSONResponse(box)


@router.get("/api/bet/{bet_id}", tags=["courtvision"])
def api_bet(bet_id: str, request: Request, date: str = Query(default_factory=_today_et),
            partial: int = 0):
    m = next((b for b in _build_slate(date)["bets"] if b["bet_id"] == bet_id), None)
    if m is None:
        if partial: return HTMLResponse('<div class="pending">not found</div>', 404)
        raise HTTPException(404, detail="bet not found")
    return (_TEMPLATES.TemplateResponse("_bet_card_reasoning.html",
            {"request": request, "bet": m}) if partial else JSONResponse(m))


@router.get("/api/parlays", tags=["courtvision"])
def api_parlays(date: Optional[str] = Query(default=None),
                seed: int = Query(0, ge=0, le=10**9)):
    # Same-book parlays, 2-3 legs auto-tuned, top 25 by EV. No knobs.
    if not date:
        date = _current_or_next_game_day()
    return JSONResponse(_build_parlays(date, seed=seed))


@router.get("/api/parlays/constructor", tags=["courtvision"])
def api_parlays_constructor(
    date: Optional[str] = Query(default=None),
    max_legs: int = Query(3, ge=2, le=5),
    min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0),
    top_n: int = Query(25, ge=1, le=100),
    seed: int = Query(0, ge=0, le=10**9),
):
    """SGP-penalty parlay candidates from src.prediction.parlay_constructor.

    Returns ranked 3-leg combos with `expected_roi_sgp_pct`, `hit_rate_adj`,
    `decimal_odds`, `american_odds`, and per-leg dicts under leg_0/leg_1/leg_2.
    """
    if not date:
        date = _current_or_next_game_day()
    return JSONResponse(_build_parlays_constructor(date, max_legs, min_ev_pct, top_n, seed))


def _american_to_decimal(odds: int) -> float:
    return (odds / 100 + 1) if odds >= 0 else (-100 / odds + 1)


def _decimal_to_american(dec: float) -> int:
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


@router.post("/api/parlays/build", tags=["courtvision"])
def api_parlays_build(body: dict = Body(...)):
    """Compute combined American / decimal odds for an arbitrary set of legs.

    Body: {"legs": [{"player": str, "stat": str, "line": float,
                     "side": "over"|"under", "price": int}]}
    Returns: {"n_legs": int, "decimal": float, "american": int, "payout_100": float}
    """
    legs = body.get("legs") or []
    if not legs:
        raise HTTPException(status_code=422, detail="legs required: provide at least one leg")
    if len(legs) > 12:
        raise HTTPException(status_code=400, detail="max 12 legs")
    decimal = 1.0
    for leg in legs:
        price = leg.get("price")
        if price is None:
            raise HTTPException(status_code=422, detail=f"leg missing price: {leg}")
        try:
            decimal *= _american_to_decimal(int(price))
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise HTTPException(status_code=422, detail=f"invalid price {price}: {exc}") from exc
    american = _decimal_to_american(decimal)
    return JSONResponse({
        "n_legs": len(legs),
        "decimal": round(decimal, 6),
        "american": american,
        "payout_100": round((decimal - 1) * 100, 2),
        "legs": legs,
    })


@router.get("/api/auto_parlay", tags=["courtvision"])
def api_auto_parlay(date: str = Query(default_factory=_today_et),
                    stake: float = Query(20.0, ge=1.0, le=10000.0),
                    max_legs: int = Query(5, ge=2, le=5)):
    """Highest-EV parlay whose EV meets the min threshold, using the constructor engine."""
    # Bug 1 fix: was calling _build_parlays(date, max_legs, 5.0, 0) with 4 positional
    # args — that function only takes (date, seed, top_n) → TypeError on every request.
    # Use _build_parlays_constructor (the correct function). Its parlay dicts come from
    # rank_parlays() which produces: hit_rate_adj, decimal_odds, expected_roi_sgp_pct,
    # ev_sgp, etc. — there is no kelly_stake_dollars field. Filter by ev_pct when
    # present (parlays_constructor adds it if the upstream leg has it), else accept all.
    try:
        result = _build_parlays_constructor(date, max_legs, 5.0)
        parlays = result.get("parlays", [])
        # Filter: prefer parlays within stake budget if ev_pct is present, else
        # surface all positive-ROI parlays (constructor already ranks by ev_sgp).
        c = [p for p in parlays
             if (p.get("expected_roi_sgp_pct") or 0.0) > 0.0]
        return JSONResponse({"date": date, "stake": stake, "max_legs": max_legs,
                             "pick": c[0] if c else None,
                             "n_candidates": len(c),
                             "engine": result.get("engine", "constructor")})
    except Exception as exc:
        import logging as _lg_ap  # noqa: PLC0415
        _lg_ap.getLogger(__name__).warning("api_auto_parlay error: %s", exc)
        return JSONResponse({"date": date, "stake": stake, "max_legs": max_legs,
                             "pick": None, "n_candidates": 0, "error": str(exc)})


_SHARE_HIDE = ("kelly_stake_dollars", "kelly_pct", "market_prob", "model_prob")

@router.get("/share/{slug}", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def share(slug: str, request: Request):
    slate = _build_slate(slug)
    if not slate.get("bets"):
        raise HTTPException(status_code=404, detail="no slate for this slug")
    shown = [{k: v for k, v in b.items() if k not in _SHARE_HIDE}
             for b in slate["bets"][:_SHARE_TOP_N]]
    evs = [b.get("ev_pct") for b in shown if b.get("ev_pct") is not None]
    avg_ev = round(sum(evs) / len(evs), 2) if evs else 0.0
    from api._courtvision_data import share_text
    return _TEMPLATES.TemplateResponse("share.html",
        {"request": request, "slate": slate, "shown": shown,
         "avg_ev": avg_ev, "share_text": share_text(slate, shown)})


@router.get("/share/{slug}/qr.svg", tags=["courtvision"])
def share_qr(slug: str, request: Request):
    import io, qrcode
    from qrcode.image.svg import SvgPathImage
    base = _PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    q = qrcode.QRCode(box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(f"{base}/share/{slug}"); q.make(fit=True)
    buf = io.BytesIO(); q.make_image(image_factory=SvgPathImage).save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/healthz", tags=["courtvision"])
def healthz():
    from api._courtvision_data import healthz_payload
    return JSONResponse(healthz_payload(_ROOT, _latest_slate_date()))


@router.get("/help", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def help_page(request: Request):
    """About / Help page — explains CourtVision, model, and key terms."""
    return _TEMPLATES.TemplateResponse("help.html", {"request": request})


@router.get("/about", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def about_page(request: Request):
    """Alias for /help."""
    return RedirectResponse(url="/help", status_code=307)


@router.get("/games", tags=["courtvision"])
def games_alias(): return RedirectResponse(url="/tonight", status_code=302)


@router.get("/bets", tags=["courtvision"])
def bets_alias(): return RedirectResponse(url="/risk", status_code=302)


# NOTE: old "/cv" -> /tonight shortlink removed 2026-06-10 so the new CV simple
# page (registered later in this file) owns the contracted /cv path.


@router.get("/api/odds/{date}.json", tags=["courtvision"])
def api_odds_for_date(date: str, stat: str = Query(""), player: str = Query("")):
    """Multi-book scraped prop odds for `date`. Filterable by stat + player."""
    from api._courtvision_odds import odds_env
    return JSONResponse(odds_env(date, stat, player))


_WITH_EV_CACHE: dict[str, tuple[float, dict]] = {}
_WITH_EV_TTL = 30.0


@router.get("/api/odds/with-ev/{date}.json", tags=["courtvision"])
def api_odds_with_ev(date: str, stat: str = Query(""), player: str = Query(""),
                     limit: int = Query(1000, ge=1, le=5000),
                     offset: int = Query(0, ge=0)):
    """Consolidated odds + model projection overlay (projection, edge, rec) for `date`.

    Falls back gracefully when predictions parquet missing — returns normal odds
    with None model fields. Never 500s due to missing predictions.
    Supports ?limit=N&offset=M for pagination (default limit=1000 = return all).
    Overlay result is cached for 30s per date (the parquet read is the hot path).
    """
    from api._courtvision_odds import odds_env
    from api._predictions_overlay import overlay_predictions

    # Cache the full overlay per date (stat/player filters applied after cache hit)
    cache_key = date
    cached = _WITH_EV_CACHE.get(cache_key)
    if cached is None or time.time() - cached[0] >= _WITH_EV_TTL:
        env_full = odds_env(date)
        try:
            env_full["props"] = overlay_predictions(date, env_full["props"])
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("overlay_predictions failed: %s", exc)

        # Stale-date fallback: if the requested date returned 0 props OR every
        # book's last_scrape timestamp belongs to a different calendar day,
        # redirect internally to the next slate with live data and attach a
        # `next_slate` hint so callers can surface the right date.
        _n_props = len(env_full.get("props") or [])
        _books = env_full.get("books") or []
        _all_stale = _n_props == 0 or all(
            (b.get("last_scrape") or "")[:10] != date for b in _books
        )
        if _all_stale:
            _next = _next_game_day() or _today_et()
            if _next != date:
                _fb_env = odds_env(_next)
                try:
                    _fb_env["props"] = overlay_predictions(_next, _fb_env["props"])
                except Exception:
                    pass
                _fb_env["next_slate"] = _next
                _fb_env["requested_date"] = date
                env_full = _fb_env
            else:
                env_full["next_slate"] = None
                env_full["requested_date"] = date
        else:
            env_full["next_slate"] = None

        _WITH_EV_CACHE[cache_key] = (time.time(), env_full)
    else:
        env_full = cached[1]

    # Apply stat/player filters and pagination on the cached result
    env = dict(env_full)
    props = list(env.get("props") or [])
    if stat:
        props = [p for p in props if p.get("stat") == stat.lower()]
    if player:
        pl = player.lower()
        props = [p for p in props if pl in p.get("player", "").lower()]
    total = len(props)
    if offset or limit < 5000:
        props = props[offset: offset + limit]
    env = dict(env)
    env["props"] = props
    env["n_props"] = total
    env["n_props_page"] = len(props)
    return JSONResponse(env)

@router.get("/api/odds", tags=["courtvision"])
def api_odds_today(stat: str = Query(""), player: str = Query("")):
    from api._courtvision_odds import odds_env
    date = _next_game_day() or _today_et()
    return JSONResponse(odds_env(date, stat, player))

# /odds page removed 2026-05-28 (user request: was broken and not useful).
# The /api/odds/* JSON endpoints remain — they back the homepage book filter
# and game-detail page. Only the standalone HTML page was deleted.

_NEXT_GAME_DAY_CACHE: tuple[float, Optional[str]] | None = None
_NEXT_GAME_DAY_TTL = 60.0  # recompute at most once per minute


def _live_game_date() -> Optional[str]:
    """ET date of a game that is LIVE RIGHT NOW (a recent, non-FINAL snapshot).

    Tonight's game has already tipped, so _next_game_day() excludes it and would
    skip ahead to the next scheduled game. When a game is in progress we want the
    page to show THAT game, so this takes priority. None if nothing is live."""
    import json as _jl  # noqa: PLC0415
    live_dir = _ROOT / "data" / "live"
    if not live_dir.exists():
        return None
    now_ms = time.time() * 1000.0
    latest: dict = {}
    for p in live_dir.glob("*.json"):
        if not _is_epoch_snap(p):
            continue
        gid, _, ep = p.stem.rpartition("_")
        try:
            ep_i = int(ep)
        except ValueError:
            continue
        if gid and (gid not in latest or ep_i > latest[gid][0]):
            latest[gid] = (ep_i, p)
    best = None  # (epoch_ms, et_date)
    for gid, (ep_i, p) in latest.items():
        if now_ms - ep_i > 5 * 3600 * 1000:  # only the last ~5 hours = "now"
            continue
        try:
            s = _jl.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = str(s.get("game_status") or "").upper()
        if "FINAL" in status:
            continue
        if "LIVE" not in status and "IN_PROGRESS" not in status and not s.get("period"):
            continue
        d = _et_date_from_iso(s.get("captured_at") or "")
        if d and (best is None or ep_i > best[0]):
            best = (ep_i, d)
    return best[1] if best else None


def _current_or_next_game_day() -> Optional[str]:
    """The date the page should default to: a LIVE game now > next scheduled
    game > today. Fixes /tonight landing on a future Finals date while Game 7
    is in progress."""
    return _live_game_date() or _next_game_day() or _today_et()


def _next_game_day() -> Optional[str]:
    """Earliest distinct start_time date across all lines whose `start_time`
    is strictly in the future (UTC). Cached for 60s.

    Scrapers write CSVs under the SCRAPE date (e.g. 2026-05-29_dk.csv) but
    each row carries its own start_time field (e.g. 2026-05-31T00:10:00Z).
    We walk the last 3 scrape-date directories backward so we pick up future
    games stored in today's (or yesterday's) file — not just files named after
    tomorrow's date. Per-row start_time is the authoritative filter; we only
    include start_times strictly after now (UTC) so already-started games are
    excluded. Falls back to filename-date when start_time is missing/unparseable.
    """
    global _NEXT_GAME_DAY_CACHE
    now_ts = time.time()
    if _NEXT_GAME_DAY_CACHE is not None and now_ts - _NEXT_GAME_DAY_CACHE[0] < _NEXT_GAME_DAY_TTL:
        return _NEXT_GAME_DAY_CACHE[1]

    from datetime import datetime, timezone, timedelta
    import csv as _csv
    now = datetime.now(timezone.utc)
    candidates: list[str] = []

    if not _LINES_DIR.exists():
        _NEXT_GAME_DAY_CACHE = (now_ts, None)
        return None

    # Walk backward up to 3 scrape dates (today, yesterday, day-before) so we
    # catch future games whose rows live in today's or yesterday's CSV files.
    # Also walk forward up to 7 days in case scrapers ever pre-date files.
    file_dates: list[str] = []
    for offset in range(-3, 8):
        file_dates.append((now + timedelta(days=offset)).strftime("%Y-%m-%d"))

    seen_files: set[str] = set()
    for d in file_dates:
        for p in _LINES_DIR.iterdir():
            if not p.is_file() or p.suffix != ".csv":
                continue
            if not p.stem.startswith(f"{d}_"):
                continue
            if p.name in seen_files:
                continue
            seen_files.add(p.name)
            try:
                with p.open(newline="", encoding="utf-8") as fh:
                    reader = _csv.DictReader(fh)
                    # A single CSV (e.g. 2026-05-29_dk.csv) often contains rows
                    # for multiple game dates — finished games from earlier today
                    # AND props for games tipping off in 2-7 days. Scan up to
                    # _MAX_ROWS_PER_FILE rows and collect every distinct future
                    # start_time date. (The old `break` after one row meant a
                    # file whose first row was a past game contributed nothing,
                    # which is why /returned 2026-05-29 even though 5/31 + 6/4
                    # props were sitting in the same files.)
                    _MAX_ROWS_PER_FILE = 5000
                    file_future_dates: set[str] = set()
                    rows_scanned = 0
                    for r in reader:
                        rows_scanned += 1
                        if rows_scanned > _MAX_ROWS_PER_FILE:
                            break
                        st = (r.get("start_time") or "").strip()
                        if len(st) < 10:
                            continue
                        # Try to parse as UTC datetime for strict future check.
                        # Bucket by ET game date — a 7:00 PM ET tip is
                        # YYYY-MM-DDT23:00Z and would otherwise show up
                        # under the wrong calendar day.
                        try:
                            st_norm = st.replace("Z", "+00:00")
                            if "+" not in st_norm[10:] and st_norm.count("-") < 3:
                                st_norm += "+00:00"
                            st_dt = datetime.fromisoformat(st_norm).astimezone(timezone.utc)
                            if st_dt > now:
                                et_d = _et_date_from_iso(st)
                                if et_d:
                                    file_future_dates.add(et_d)
                        except (ValueError, AttributeError):
                            # Fallback: use date portion if it's in the future
                            st_date = st[:10]
                            if st_date > now.strftime("%Y-%m-%d"):
                                file_future_dates.add(st_date)
                    candidates.extend(file_future_dates)
            except OSError:
                continue

    result = min(candidates) if candidates else None
    _NEXT_GAME_DAY_CACHE = (now_ts, result)
    return result

@router.get("/api/docs", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def api_docs(request: Request):
    return _TEMPLATES.TemplateResponse("api_docs.html", {"request": request})

@router.get("/api/odds/best/{date}.json", tags=["courtvision"])
def api_odds_best(date: str):
    """Best (most favorable) book per (player, stat, line) per side."""
    from api._courtvision_odds import best_book_envelope
    return JSONResponse(best_book_envelope(date))

@router.get("/api/odds/history/{player}/{stat}", tags=["courtvision"])
def api_odds_history(player: str, stat: str,
                     date: str = Query(default_factory=_today_et)):
    """Every captured quote for one (player, stat) — useful for line-movement charts."""
    from api._courtvision_odds import line_history
    rows = line_history(date, player, stat)
    return JSONResponse({"date": date, "player": player, "stat": stat,
                         "n": len(rows), "history": rows})

def _spread_env(date: str, min_spread_pp: float) -> dict:
    from api._courtvision_odds import cross_book_spread
    rows = cross_book_spread(date, min_spread_pp=min_spread_pp)
    return {"date": date, "min_spread_pp": min_spread_pp, "n": len(rows),
            "n_arbs": sum(1 for r in rows if r["is_arb"]), "rows": rows}

@router.get("/api/odds/spread/{date}.json", tags=["courtvision"])
def api_odds_spread(date: str, min_spread_pp: float = Query(2.0, ge=0.0, le=50.0)):
    return JSONResponse(_spread_env(date, min_spread_pp))


@router.get("/api/odds/arbs/{date}.json", tags=["courtvision"])
def api_odds_arbs(
    date: str,
    max_age_sec: float = Query(60.0, ge=10.0, le=600.0,
                               description="Max seconds since capture to include a book in arb"),
    min_spread_pp: float = Query(2.0, ge=0.0, le=50.0),
    quality: str = Query("tight,loose",
                         description="Comma-separated arb_quality values to return (tight,loose,stale)"),
):
    """High-confidence arb opportunities only.

    Filters cross_book_spread results to rows with is_arb=True whose
    arb_quality is in the requested set. Default: tight + loose (omits stale).
    """
    from api._courtvision_odds import cross_book_spread
    allowed_quality = {q.strip().lower() for q in quality.split(",") if q.strip()}
    rows = cross_book_spread(date, min_spread_pp=min_spread_pp, max_age_sec=max_age_sec)
    arbs = [
        r for r in rows
        if r.get("is_arb")
        and r.get("arb_quality", "stale") in allowed_quality
    ]
    return JSONResponse({
        "date": date, "max_age_sec": max_age_sec,
        "min_spread_pp": min_spread_pp, "quality_filter": sorted(allowed_quality),
        "n_arbs": len(arbs), "arbs": arbs,
    })


@router.get("/api/odds/summary/{date}", tags=["courtvision"])
def api_odds_summary(date: str):
    """Compact day-level snapshot: counts, books, per-stat tally, freshness."""
    from api._courtvision_odds import summary
    return JSONResponse(summary(date))

@router.get("/api/odds/games/{date}", tags=["courtvision"])
def api_odds_games(date: str):
    """List distinct games in the day's odds data.

    Entries where the book-specific game_id cannot be resolved to real NBA team
    abbreviations are dropped (fail-closed). A WARNING is logged for each drop.
    """
    import logging as _log
    _logger = _log.getLogger(__name__)
    from api._courtvision_odds import games_index
    raw = games_index(date)
    resolved = []
    for g in raw:
        away = g.get("away_abbr", "")
        home = g.get("home_abbr", "")
        # Orphan: away_abbr is the raw game_id or either abbr is empty/generic
        _is_raw_id = away == g.get("game_id") or away in ("", "AWAY", "HOME") or home in ("", "AWAY", "HOME")
        if _is_raw_id:
            _logger.warning(
                "api_odds_games: dropping unresolvable game_id=%s (away_abbr=%r, home_abbr=%r)",
                g.get("game_id"), away, home,
            )
            continue
        resolved.append(g)
    return JSONResponse({"date": date, "games": resolved})

@router.get("/api/odds/freshness/{date}", tags=["courtvision"])
def api_odds_freshness(date: str):
    """Per-book CSV freshness: file mtime, latest captured_at, row count."""
    from api._courtvision_odds import freshness
    return JSONResponse(freshness(date))

@router.get("/api/odds/moves/{date}.json", tags=["courtvision"])
def api_odds_moves(date: str, window_minutes: int = Query(60, ge=5, le=720)):
    """Props whose line moved within `window_minutes` — live-day alerts."""
    from api._courtvision_odds import line_moves
    rows = line_moves(date, window_minutes=window_minutes)
    return JSONResponse({"date": date, "window_minutes": window_minutes,
                         "n": len(rows), "moves": rows})


# ── Steam / sharp-move endpoints ──────────────────────────────────────────────

def _read_steam_events_tail(hours: float = 12.0, max_bytes: int = 2 * 1024 * 1024) -> list:
    """Tail-read steam_events.jsonl without scanning the full file.

    Uses os.path.getsize to compute read offset so only trailing `max_bytes`
    are examined — safe on large audit files.
    """
    import os as _os
    import json as _json
    from datetime import datetime, timedelta, timezone
    path = _ROOT / "data" / "cache" / "steam_events.jsonl"
    if not path.exists():
        return []
    try:
        size = _os.path.getsize(str(path))
        offset = max(0, size - max_bytes)
        with open(path, "rb") as f:
            if offset:
                f.seek(offset)
                f.readline()  # skip possible partial first line after seek
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = _json.loads(line)
            ts_str = ev.get("ts", "")
            try:
                ev_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                ev_ts = 0.0
            if ev_ts >= cutoff_ts:
                events.append(ev)
        except (ValueError, KeyError):
            continue
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return events


@router.get("/api/steam/recent", tags=["courtvision"])
def api_steam_recent(hours: float = Query(12.0, ge=0.1, le=168.0)):
    """Recent sharp/steam move events emitted by steam_detector in the last N hours.

    Reads from data/cache/steam_events.jsonl using tail-read (no full scan).
    Returns events sorted newest-first.
    """
    events = _read_steam_events_tail(hours=hours)
    return JSONResponse({
        "window_hours": hours,
        "n_events": len(events),
        "events": events,
    })


@router.get("/api/odds/{date}.csv", tags=["courtvision"])
def api_odds_csv(date: str, stat: str = Query(""), player: str = Query("")):
    """CSV export of consolidated odds — one row per (player, stat, line, book)."""
    from api._courtvision_odds import consolidate_csv
    body = consolidate_csv(date, stat or None, player or None)
    return Response(content=body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="odds_{date}.csv"'})

# /arbs page removed 2026-05-28 (user request: cross-book arbitrage isn't
# the product anymore; users want direct "what bet to place" guidance per
# their selected books, not arb scanning).


@router.get("/api/today_summary", tags=["courtvision"])
def api_today_summary(date: str = Query(default=None), n: int = Query(3, ge=1, le=10)):
    # Use the same next-game-day fallback as /api/home.json and /tonight so that
    # off-day requests (e.g. 2026-05-28 with no slate) resolve to the next slate
    # that has live lines (e.g. 2026-05-29) rather than returning n_total:0.
    if date is None:
        date = _current_or_next_game_day()
    s = _build_slate(date); bets = s.get("bets", [])[:n]
    return JSONResponse({"date": s["date"], "generated_at": s["generated_at"],
        "n_total": s["summary"]["n_bets"], "avg_ev_pct": s["summary"]["avg_ev_pct"],
        "top": [{"player": b["player_name"], "team": b["team"], "opp": b["opp"],
                 "prop": f"{b['prop_stat']} {'o' if b['side']=='OVER' else 'u'}{b['line']:g}",
                 "ev_pct": b.get("ev_pct"), "book": b.get("best_book"),
                 "price": b.get("best_price")} for b in bets],
        "share_url": f"{_PUBLIC_BASE_URL or ''}/share/{s['date']}"})


@router.get("/api/clv/summary", tags=["courtvision"])
def api_clv_summary(days: int = Query(30, ge=1, le=365)):
    """Rolling CLV + P&L summary over the last N days.

    Reads data/clv/daily_clv.csv (written by nightly_grader) plus the raw
    per-game CLV JSON blobs in data/clv/ for by_book / by_stat breakdowns.

    Query params:
        days  — look-back window in days (default 30, max 365)

    Returns:
        {
            window_days, n_bets, n_days, total_stake, total_pnl, roi_pct,
            avg_clv_bps, win_pct, sharpe_30d,
            by_book: {book: {n_bets, roi_pct, avg_clv_bps}},
            by_stat: {stat: {n_bets, roi_pct, avg_clv_bps, win_pct}},
        }
    """
    import csv as _csv_mod  # noqa: PLC0415
    import json as _json     # noqa: PLC0415
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    from math import sqrt  # noqa: PLC0415

    clv_dir      = _ROOT / "data" / "clv"
    daily_csv    = clv_dir / "daily_clv.csv"
    cutoff       = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # ── Aggregate daily_clv.csv rows ──────────────────────────────────────────
    daily_rows: list = []
    if daily_csv.exists():
        try:
            with open(daily_csv, encoding="utf-8") as f:
                daily_rows = [r for r in _csv_mod.DictReader(f)
                              if r.get("date", "") >= cutoff]
        except Exception:
            daily_rows = []

    def _fsum(field: str) -> float:
        return sum(float(r.get(field) or 0) for r in daily_rows)

    n_days      = len(daily_rows)
    n_bets      = sum(int(r.get("n_bets") or 0) for r in daily_rows)
    total_stake = _fsum("total_stake")
    total_pnl   = _fsum("total_pnl")
    roi_pct     = round(100.0 * total_pnl / total_stake, 2) if total_stake else 0.0

    clv_vals    = [float(r.get("avg_clv_bps") or 0) for r in daily_rows]
    avg_clv_bps = round(sum(clv_vals) / len(clv_vals), 1) if clv_vals else 0.0

    win_vals    = [float(r.get("win_pct") or 0) for r in daily_rows]
    win_pct     = round(sum(win_vals) / len(win_vals), 2) if win_vals else 0.0

    sharpe_30d  = 0.0
    roi_list    = [float(r.get("roi_pct") or 0) for r in daily_rows]
    if len(roi_list) >= 2:
        mean_r = sum(roi_list) / len(roi_list)
        var_r  = sum((v - mean_r) ** 2 for v in roi_list) / (len(roi_list) - 1)
        sigma  = sqrt(var_r)
        sharpe_30d = round(mean_r / sigma, 4) if sigma > 0 else 0.0

    if not daily_rows:
        return JSONResponse({
            "window_days": days, "n_bets": 0, "n_days": 0,
            "total_stake": 0.0, "total_pnl": 0.0, "roi_pct": 0.0,
            "avg_clv_bps": 0.0, "win_pct": 0.0, "sharpe_30d": 0.0,
            "note": "no data yet — nightly_grader has not run for this window",
            "by_book": {}, "by_stat": {},
        })

    # ── by_book / by_stat from raw per-game CLV JSON blobs ───────────────────
    by_book: dict = {}
    by_stat: dict = {}

    if clv_dir.exists():
        for p in sorted(clv_dir.glob("*_clv.json")):
            # filename: <date>_<game_id>_clv.json  or  <date>_<game_id>_clv.json
            stem_parts = p.stem.split("_")
            date_part = stem_parts[0] if stem_parts else ""
            if date_part < cutoff:
                continue
            try:
                blob = _json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for bet in blob.get("bets", []):
                book = str(bet.get("book") or "unknown")
                stat = str(bet.get("stat") or "unknown")
                clv  = float(bet.get("clv_pct") or 0)

                # by_book aggregation
                bb = by_book.setdefault(book, {"n_bets": 0, "_sum_clv": 0.0})
                bb["n_bets"]   += 1
                bb["_sum_clv"] += clv

                # by_stat aggregation
                bs = by_stat.setdefault(stat, {"n_bets": 0, "_sum_clv": 0.0})
                bs["n_bets"]   += 1
                bs["_sum_clv"] += clv

    # Finalise derived fields and strip private accumulators.
    # roi_pct / win_pct are set (0.0 default) because clv.html compares them
    # numerically ({% if m.roi_pct > 0 %}); a missing key is Jinja Undefined and
    # `Undefined > 0` raises -> HTTP 500 on /clv. (is-not-none would NOT help —
    # the key must EXIST.) These are CLV-only rows so ROI/win are not tracked here.
    for d in by_book.values():
        n = d["n_bets"]
        d["avg_clv_bps"] = round(d.pop("_sum_clv") / n * 100.0, 1) if n else 0.0
        d.setdefault("roi_pct", 0.0)
        d.setdefault("win_pct", 0.0)

    for d in by_stat.values():
        n = d["n_bets"]
        d["avg_clv_bps"] = round(d.pop("_sum_clv") / n * 100.0, 1) if n else 0.0
        d.setdefault("roi_pct", 0.0)
        d.setdefault("win_pct", 0.0)

    return JSONResponse({
        "window_days":  days,
        "n_bets":       n_bets,
        "n_days":       n_days,
        "total_stake":  round(total_stake, 2),
        "total_pnl":    round(total_pnl, 2),
        "roi_pct":      roi_pct,
        "avg_clv_bps":  avg_clv_bps,
        "win_pct":      win_pct,
        "sharpe_30d":   sharpe_30d,
        "by_book":      by_book,
        "by_stat":      by_stat,
    })


@router.get("/sse/live_edges", tags=["courtvision"])
async def sse_live_edges(request: Request):
    from api._courtvision_live import live_edge_stream
    return await live_edge_stream(request)

@router.get("/live", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def live(request: Request, date: str = Query(default_factory=_today_et)):
    return _TEMPLATES.TemplateResponse("live.html", {"request": request, "date": date})


@router.get("/api/plus_ev", tags=["courtvision"])
def api_plus_ev(date: str = Query(default_factory=_today_et),
                min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0)):
    from api._courtvision_data import plus_ev_rows
    r = plus_ev_rows(_build_slate(date), min_ev_pct)
    return JSONResponse({"date": date, "n": len(r), "rows": r})


@router.get("/plus_ev", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def plus_ev(request: Request,
            date: str = Query(default_factory=_today_et),
            min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0)):
    from api._courtvision_data import plus_ev_rows
    rows = plus_ev_rows(_build_slate(date), min_ev_pct)
    return _TEMPLATES.TemplateResponse("plus_ev.html",
        {"request": request, "date": date, "rows": rows, "min_ev_pct": min_ev_pct,
         "is_playoff": _is_playoff_date(date)})



# ── SQLite-backed bet ledger endpoints ───────────────────────────────────────

def _get_db():
    """Lazy import so the DB is only loaded if these endpoints are called."""
    from database.bet_db import BetDB  # noqa: PLC0415
    return BetDB()


@router.get("/api/bets", tags=["courtvision"])
def api_bets(
    date:   Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    player: Optional[str] = Query(default=None),
    limit:  int           = Query(default=100, ge=1, le=1000),
):
    """List bets from the SQLite ledger. Filters: date, status, player (substring).

    Response shape is backwards-compatible with the previous CSV-reading version.
    Falls back to an empty list if the DB does not yet exist.
    """
    try:
        rows = _get_db().list_bets(date=date, status=status, player=player, limit=limit)
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("api_bets DB error: %s", exc)
        rows = []
    return JSONResponse({"bets": rows, "n": len(rows)})


@router.get("/api/bets/recent", tags=["courtvision"])
def api_bets_recent(n: int = Query(default=20, ge=1, le=200)):
    """Last N bets across all dates — for the bet-history widget on /odds."""
    try:
        rows = _get_db().recent_bets(n)
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("api_bets_recent DB error: %s", exc)
        rows = []
    return JSONResponse({"bets": rows, "n": len(rows)})


@router.get("/api/bankroll", tags=["courtvision"])
def api_bankroll():
    """Current bankroll snapshot + risk metrics.

    Returns:
        current       — latest recorded bankroll
        open_stake    — sum of pending bets
        available     — current − open_stake
        today_pnl     — settled P&L for today (UTC)
        today_stake   — total stake placed today
        drawdown_30d_pct — (HWM − current) / HWM × 100 over 30 days
        high_water_mark  — peak bankroll in last 90 days
    """
    try:
        db          = _get_db()
        current     = db.current_bankroll()
        open_stake  = db.open_bet_value()
        today       = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_sum   = db.daily_summary(today)
        hwm         = db.high_water_mark(90)
        drawdown    = db.drawdown_pct(30)
        return JSONResponse({
            "current":          round(current, 2),
            "open_stake":       round(open_stake, 2),
            "available":        round(current - open_stake, 2),
            "today_pnl":        today_sum.get("total_pnl", 0.0),
            "today_stake":      today_sum.get("total_stake", 0.0),
            "drawdown_30d_pct": drawdown,
            "high_water_mark":  round(hwm, 2),
        })
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("api_bankroll DB error: %s", exc)
        return JSONResponse({"error": str(exc), "current": 0.0,
                             "open_stake": 0.0, "available": 0.0,
                             "today_pnl": 0.0, "today_stake": 0.0,
                             "drawdown_30d_pct": 0.0, "high_water_mark": 0.0})


# ── Admin health endpoint ──────────────────────────────────────────────────────

@router.get("/api/admin/health.json", tags=["courtvision"])
def api_admin_health():
    """One-shot system health snapshot. No auth required for local viewing."""
    import glob as _glob
    import json as _json
    import os as _os

    now_ts = time.time()
    date = _today_et()

    # ── 1. Snapshot freshness per game_id ─────────────────────────────
    snapshot_freshness: dict = {}
    try:
        live_dir = _ROOT / "data" / "live"
        if live_dir.exists():
            # Group by game_id (stem prefix before first "_")
            latest_mtime: dict[str, float] = {}
            for p in live_dir.iterdir():
                if not p.is_file() or p.suffix != ".json":
                    continue
                try:
                    mt = p.stat().st_mtime
                except OSError:
                    continue
                gid = p.stem.split("_")[0]
                if mt > latest_mtime.get(gid, 0.0):
                    latest_mtime[gid] = mt
            for gid, mt in sorted(latest_mtime.items(),
                                   key=lambda kv: -kv[1])[:20]:
                age_sec = round(now_ts - mt)
                snapshot_freshness[gid] = {
                    "age_sec": age_sec,
                    "age_min": round(age_sec / 60, 1),
                    "fresh": age_sec < 300,
                }
    except Exception:
        snapshot_freshness = None  # type: ignore[assignment]

    # ── 2. Book freshness summary from consolidate_for_slate ──────────
    book_freshness: dict = {}
    try:
        from api._courtvision_odds import consolidate_for_slate as _cfs  # noqa: PLC0415
        line_rows = _cfs(date)
        book_quotes: dict[str, list[str]] = {}
        for row in line_rows:
            for b in (row.get("books") or []):
                bk = b.get("book") or "unknown"
                ts = b.get("captured_at") or ""
                book_quotes.setdefault(bk, [])
                if ts:
                    book_quotes[bk].append(ts)
        for bk, timestamps in sorted(book_quotes.items()):
            if timestamps:
                freshest_ts = max(timestamps)
                try:
                    from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415
                    dt = _dt.fromisoformat(freshest_ts.replace("Z", "+00:00"))
                    age_sec = round(now_ts - dt.timestamp())
                except Exception:
                    age_sec = None  # type: ignore[assignment]
            else:
                freshest_ts = None
                age_sec = None  # type: ignore[assignment]
            book_freshness[bk] = {
                "n_quotes": len(line_rows),  # props, not raw quotes
                "n_book_quotes": len(timestamps),
                "freshest_ts": freshest_ts,
                "age_sec": age_sec,
                "age_min": round(age_sec / 60, 1) if age_sec is not None else None,
                "fresh": age_sec is not None and age_sec < 900,
            }
    except Exception as _exc_book:
        book_freshness = {"error": str(_exc_book)}  # type: ignore[assignment]

    # ── 3. Orchestrator status ─────────────────────────────────────────
    orchestrator_status: str
    try:
        import api.live_v2_app as _lv2  # noqa: PLC0415
        orch = getattr(_lv2, "_orchestrator", None)
        if orch is not None:
            orchestrator_status = "alive"
        else:
            orchestrator_status = "waiting for games"
    except Exception:
        orchestrator_status = "unavailable"

    # ── 4. Watchdog log tails ──────────────────────────────────────────
    _watchdog_files = {
        "uvicorn_watchdog": _ROOT / "data" / "cache" / "uvicorn_watchdog.log",
        "ngrok_watchdog": _ROOT / "data" / "cache" / "ngrok_watchdog.log",
        "ngrok_url_history": _ROOT / "data" / "cache" / "ngrok_url_history.log",
    }
    watchdog_tails: dict[str, object] = {}
    for key, path in _watchdog_files.items():
        try:
            if path.exists():
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                watchdog_tails[key] = lines[-3:] if lines else []
            else:
                watchdog_tails[key] = []
        except Exception:
            watchdog_tails[key] = None

    # ── 5. WP stack info ───────────────────────────────────────────────
    wp_stack_info: dict = {}
    try:
        from src.prediction.inplay_winprob import active_stack as _active_stack  # noqa: PLC0415
        for snap_key in ("endQ1", "endQ2", "endQ3"):
            try:
                info = _active_stack(snap_key)
                wp_stack_info[snap_key] = {
                    "layer": info.get("layer"),
                    "detail": info.get("detail"),
                    "components": info.get("components_loaded") or {},
                }
            except Exception as _exc_snap:
                wp_stack_info[snap_key] = {"error": str(_exc_snap)}
    except Exception as _exc_wp:
        wp_stack_info = {"error": str(_exc_wp)}

    # ── 6. Settled bets count ──────────────────────────────────────────
    settled_counts: dict = {}
    try:
        _snap_path = _ROOT / "data" / "cache" / "settled_bets.json"
        if _snap_path.exists():
            _raw: list[dict] = _json.loads(_snap_path.read_text(encoding="utf-8"))
            from collections import Counter as _Counter  # noqa: PLC0415
            _cnt = _Counter(r.get("status", "unknown") for r in _raw)
            settled_counts = dict(_cnt)
            settled_counts["_total"] = len(_raw)
        else:
            settled_counts = {"error": "settled_bets.json not found"}
    except Exception as _exc_settled:
        settled_counts = {"error": str(_exc_settled)}

    return JSONResponse({
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "slate_date": date,
        "snapshot_freshness": snapshot_freshness,
        "book_freshness": book_freshness,
        "orchestrator_status": orchestrator_status,
        "watchdog_tails": watchdog_tails,
        "wp_stack": wp_stack_info,
        "settled_bets": settled_counts,
    })


@router.get("/api/admin/dashboard", response_class=HTMLResponse, tags=["courtvision"])
def api_admin_dashboard():
    """Dark-themed admin dashboard that auto-refreshes health.json every 5s."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CourtVision Admin</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#0d1117;color:#c9d1d9;font-family:ui-monospace,"Cascadia Code",monospace;font-size:13px;padding:16px}
  h1{color:#58a6ff;font-size:18px;margin-bottom:4px}
  .meta{color:#8b949e;font-size:11px;margin-bottom:16px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:12px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}
  .card h2{color:#79c0ff;font-size:13px;margin-bottom:10px;border-bottom:1px solid #21262d;padding-bottom:6px}
  table{width:100%;border-collapse:collapse}
  th{text-align:left;color:#8b949e;font-weight:normal;padding:3px 6px 3px 0;font-size:11px}
  td{padding:3px 6px 3px 0;vertical-align:top;word-break:break-all}
  .pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:600}
  .green{background:#0d4429;color:#3fb950}
  .red{background:#4d1f1f;color:#f85149}
  .yellow{background:#2e2000;color:#e3b341}
  .gray{background:#21262d;color:#8b949e}
  .log-lines{font-size:11px;color:#8b949e;margin-top:4px;line-height:1.6}
  .log-line{border-left:2px solid #30363d;padding-left:8px;margin-bottom:2px;white-space:pre-wrap}
  #status-bar{position:fixed;top:0;right:0;padding:4px 12px;font-size:11px;background:#161b22;
              border-bottom-left-radius:6px;border:1px solid #30363d;color:#8b949e}
  .err{color:#f85149}
</style>
</head>
<body>
<div id="status-bar">loading...</div>
<h1>CourtVision Admin</h1>
<p class="meta" id="meta">Fetching...</p>
<div class="grid" id="grid"></div>

<script>
const REFRESH_MS = 5000;
const URL = "/api/admin/health.json";

function pill(ok, trueLabel, falseLabel) {
  const cls = ok ? "green" : "red";
  return `<span class="pill ${cls}">${ok ? trueLabel : falseLabel}</span>`;
}

function agePill(age_sec) {
  if (age_sec === null || age_sec === undefined) return '<span class="pill gray">n/a</span>';
  if (age_sec < 120) return `<span class="pill green">${age_sec}s</span>`;
  if (age_sec < 600) return `<span class="pill yellow">${Math.round(age_sec/60)}m</span>`;
  return `<span class="pill red">${Math.round(age_sec/60)}m</span>`;
}

function renderSnapshots(data) {
  if (!data || typeof data !== "object") return "<em class='err'>unavailable</em>";
  const entries = Object.entries(data);
  if (!entries.length) return "<em class='gray'>no snapshots</em>";
  let rows = "<table><tr><th>game_id</th><th>age</th><th>status</th></tr>";
  for (const [gid, v] of entries.slice(0, 15)) {
    rows += `<tr><td>${gid}</td><td>${agePill(v.age_sec)}</td><td>${pill(v.fresh,"live","stale")}</td></tr>`;
  }
  if (entries.length > 15) rows += `<tr><td colspan="3" style="color:#8b949e">…and ${entries.length-15} more</td></tr>`;
  return rows + "</table>";
}

function renderBooks(data) {
  if (!data || typeof data !== "object") return "<em class='err'>unavailable</em>";
  if (data.error) return `<em class="err">${data.error}</em>`;
  const entries = Object.entries(data);
  if (!entries.length) return "<em class='gray'>no books</em>";
  let rows = "<table><tr><th>book</th><th>quotes</th><th>age</th><th>ok</th></tr>";
  for (const [bk, v] of entries) {
    rows += `<tr><td>${bk}</td><td>${v.n_book_quotes}</td><td>${agePill(v.age_sec)}</td><td>${pill(v.fresh,"✓","✗")}</td></tr>`;
  }
  return rows + "</table>";
}

function renderOrch(status) {
  if (status === "alive") return '<span class="pill green">alive</span>';
  if (status === "waiting for games") return '<span class="pill yellow">waiting for games</span>';
  return `<span class="pill red">${status || "unknown"}</span>`;
}

function renderWatchdog(tails) {
  if (!tails) return "<em class='err'>unavailable</em>";
  let html = "";
  for (const [key, lines] of Object.entries(tails)) {
    html += `<div style="margin-bottom:8px"><span style="color:#79c0ff">${key}</span>`;
    if (!lines || !lines.length) { html += ' <em class="gray">empty</em></div>'; continue; }
    html += '<div class="log-lines">';
    for (const l of lines) html += `<div class="log-line">${l.replace(/</g,"&lt;")}</div>`;
    html += "</div></div>";
  }
  return html || "<em class='gray'>no logs</em>";
}

function renderWP(stack) {
  if (!stack) return "<em class='err'>unavailable</em>";
  if (stack.error) return `<em class="err">${stack.error}</em>`;
  let rows = "<table><tr><th>snapshot</th><th>layer</th></tr>";
  for (const [snap, v] of Object.entries(stack)) {
    const lbl = v.error ? `<em class="err">${v.error}</em>` : (v.layer || "unknown");
    rows += `<tr><td>${snap}</td><td>${lbl}</td></tr>`;
  }
  return rows + "</table>";
}

function renderSettled(counts) {
  if (!counts) return "<em class='err'>unavailable</em>";
  if (counts.error) return `<em class="err">${counts.error}</em>`;
  let rows = "<table><tr><th>status</th><th>count</th></tr>";
  for (const [k, v] of Object.entries(counts)) {
    const cls = k==="won"?"green":k==="lost"?"red":k==="push"?"yellow":"gray";
    rows += `<tr><td><span class="pill ${cls}">${k}</span></td><td>${v}</td></tr>`;
  }
  return rows + "</table>";
}

async function refresh() {
  const bar = document.getElementById("status-bar");
  const meta = document.getElementById("meta");
  bar.textContent = "refreshing…";
  try {
    const res = await fetch(URL, {headers:{"ngrok-skip-browser-warning":"true"}});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    bar.textContent = `last update: ${new Date().toLocaleTimeString()}`;
    meta.textContent = `slate: ${d.slate_date} | generated: ${d.generated_at}`;
    document.getElementById("grid").innerHTML = `
      <div class="card"><h2>Snapshot Freshness</h2>${renderSnapshots(d.snapshot_freshness)}</div>
      <div class="card"><h2>Book Freshness</h2>${renderBooks(d.book_freshness)}</div>
      <div class="card"><h2>Orchestrator</h2>${renderOrch(d.orchestrator_status)}</div>
      <div class="card"><h2>Watchdog Logs</h2>${renderWatchdog(d.watchdog_tails)}</div>
      <div class="card"><h2>WP Stack</h2>${renderWP(d.wp_stack)}</div>
      <div class="card"><h2>Settled Bets</h2>${renderSettled(d.settled_bets)}</div>
    `;
  } catch(e) {
    bar.textContent = `error: ${e.message}`;
    meta.textContent = "fetch failed";
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


# ===========================================================================
# CV SIMPLE PAGE — Owner B routes (appended; do not edit above this line)
# ===========================================================================

@router.get("/api/cv_board", tags=["cv"])
async def cv_board_api(
    request: Request,
    date: str = Query(default="2026-06-10", description="Game date YYYY-MM-DD"),
) -> JSONResponse:
    """Return the CV board JSON for the given game date.

    The board shape is defined in api/_cv_board.py (Board Contract).
    Cached in-process for 300s; degrades gracefully if market_board missing.
    """
    try:
        from api._cv_board import build_board as _build_board
        board = _build_board(date)
        return JSONResponse(content=board)
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning("cv_board_api error: %s", _exc)
        return JSONResponse(
            status_code=503,
            content={"error": "board unavailable", "detail": str(_exc)},
        )


@router.get("/api/cv_live", tags=["cv"])
async def cv_live_api(
    request: Request,
    date: str = Query(default="2026-06-10", description="Game date YYYY-MM-DD"),
    game_id: str = Query(default="0042500404", description="NBA game id"),
) -> JSONResponse:
    """Return the LIVE CV board JSON for a game.

    Same dict shape as /api/cv_board (api/_cv_board.build_board) but with
    board.live filled (is_live, scores, period, clock, win_prob_home_live,
    snapshot_age_sec) and each box_score player's .live actuals + proj_final
    when a data/live/<gid>_*.json snapshot exists. Pregame (no snapshot) returns
    is_live=false and is otherwise untouched. Degrades to 503 if _cv_live is
    unavailable (mirrors /api/cv_board).
    """
    try:
        from api._cv_live import live_board  # noqa: PLC0415
        board = live_board(date, game_id)
        return JSONResponse(content=board)
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning("cv_live_api error: %s", _exc)
        return JSONResponse(
            status_code=503,
            content={"error": "live board unavailable", "detail": str(_exc)},
        )


@router.get("/cv", tags=["cv"])
@router.get("/cv_simple", tags=["cv"])
async def cv_simple_page(
    request: Request,
    date: str = Query(default="2026-06-10", description="Game date YYYY-MM-DD"),
) -> Response:
    """Render the CV simple page.

    Passes the full board dict as 'board' to the template AND embeds it as
    a JSON <script id='cv-board'> blob so the front-end JS can bootstrap
    without a second round-trip.
    """
    try:
        from api._cv_board import build_board as _build_board
        board = _build_board(date)
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning("cv_simple_page board error: %s", _exc)
        board = {}

    try:
        import json as _json
        board_json = _json.dumps(board, default=str)
        return _TEMPLATES.TemplateResponse(
            "cv_simple.html",
            {"request": request, "board": board, "board_json": board_json},
        )
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning("cv_simple_page template error: %s", _exc)
        # Graceful fallback: return a minimal stub page so boot is never broken
        import json as _json
        _board_json = _json.dumps(board, default=str)
        _stub = (
            "<!doctype html><html><head><title>CourtVision</title></head><body>"
            f"<script id='cv-board' type='application/json'>{_board_json}</script>"
            "<p>Template cv_simple.html not yet deployed.</p>"
            "</body></html>"
        )
        return HTMLResponse(content=_stub)
# ===========================================================================
# END Owner B routes

# ===========================================================================
# INTEL NARRATIVE — Owner INTEL routes (appended; do not edit above this line)
# ===========================================================================

@router.get("/api/cv_intel", tags=["cv"])
async def cv_intel_api(
    request: Request,
    date: str = Query(default="2026-06-10", description="Game date YYYY-MM-DD"),
    game_id: str = Query(default="0042500404", description="NBA game id"),
) -> JSONResponse:
    """Return the Intelligence LLM narrative for the given game date.

    Builds a grounded read from model numbers: win-prob, projected score,
    who may pop off (blocks/DD/longshots), and a forward-looking note.
    Uses Claude haiku-4-5 when ANTHROPIC_API_KEY is set; degrades to a
    deterministic rule-based narrative otherwise.  Cached 30s.

    Projection only — no edge claimed, no betting advice.
    Playoffs have no proven edge.
    """
    try:
        from api._cv_intel import cv_intel as _cv_intel  # noqa: PLC0415
        result = _cv_intel(date=date, game_id=game_id)
        return JSONResponse(content=result)
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning("cv_intel_api error: %s", _exc)
        return JSONResponse(
            status_code=503,
            content={"error": "intel unavailable", "detail": str(_exc)},
        )
# ===========================================================================
# END Owner INTEL routes
# ===========================================================================
