"""board_data.py — V9 PAPER board data assembler (gated CV_PAPER_BOARD).

Calls the V7 sportsbook engine + V8 live harness + CLV capture READ-ONLY and
assembles ONE board dict. No engine is edited; no real-money path is touched
(no log_bet / record_clv / bet_log.json / golive). honesty_class="paper".
Importing is side-effect-free; nothing runs until build_board() is invoked.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# sys.path bootstrap identical to sportsbook_engine.py lines 28-32 (HERE + ROOT/src)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

__all__ = ["build_board", "is_enabled", "CAVEAT", "DEFAULT_BANKROLL", "MIN_EDGE"]

CAVEAT = (
    "PAPER -- no real money. Playoffs have NO proven edge. "
    "ROI requires real captured prices + proven forward CLV."
)
MIN_EDGE = 0.03
DEFAULT_BANKROLL = 100.0


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def is_enabled(force: bool = False) -> bool:
    """Gate CV_PAPER_BOARD in {1,true,yes,on} OR force."""
    if force:
        return True
    return os.environ.get("CV_PAPER_BOARD", "0").strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Internal helpers — all READ-ONLY
# ---------------------------------------------------------------------------

def _sportsbook(
    home: str,
    away: str,
    nsims: int,
    asof: Optional[str],
    bankroll: float,
    paper_lines: Optional[Dict],
    demo: bool,
    _result: Any,
) -> Dict:
    """Call run_engine (or stub path when _result injected)."""
    from sportsbook_engine import run_engine, synth_paper_lines
    from market_catalog import price_markets, ontology_count
    from portfolio_optimizer import build_portfolio
    from sim.sgp_from_sim import joint_prob, Leg
    import numpy as np

    if _result is not None:
        # Test injection: bypass GPU by replicating the run_engine body on the stub.
        result = _result
        if demo and paper_lines is None:
            paper_lines = synth_paper_lines(result)
        markets = price_markets(result, paper_lines)
        n_concrete = len(markets)
        n_types = len({m["market_type"] for m in markets})
        onto = ontology_count(result)
        # SGP baskets (minimal: one same-player basket from top home scorer)
        sgp: List[Dict] = []
        try:
            home_pids = [
                pid for pid, d in result.players.items()
                if d["team"] == result.home_tri
            ]
            if len(home_pids) >= 1:
                home_sorted = sorted(
                    home_pids,
                    key=lambda p: -float(np.median(result.players[p]["samples"]["pts"])),
                )
                p1 = home_sorted[0]
                nm1 = result.players[p1]["name"]

                def _med(pid: int, stat: str) -> float:
                    return float(np.median(result.players[pid]["samples"][stat]))

                def _lne(pid: int, stat: str) -> float:
                    return round(_med(pid, stat) * 2) / 2

                legs = [Leg(int(p1), "pts", _lne(p1, "pts")), Leg(int(p1), "reb", _lne(p1, "reb"))]
                j, ind, lift = joint_prob(result, legs)
                sgp.append({
                    "label": f"SAME-PLAYER {nm1} pts & reb",
                    "joint": j, "independent": ind, "lift": lift,
                    "legs": [(lg.pid, lg.stat, lg.line, lg.over) for lg in legs],
                })
        except Exception:
            pass
        portfolio = build_portfolio(result, markets, bankroll=bankroll)
        return {
            "result": result, "markets": markets, "n_concrete": n_concrete,
            "n_types": n_types, "ontology_count": onto, "sgp": sgp,
            "portfolio": portfolio, "paper_lines": paper_lines,
            "honesty_class": "paper", "caveat": CAVEAT,
        }

    return run_engine(
        home=home, away=away, nsims=nsims, asof=asof,
        paper_lines=paper_lines, bankroll=bankroll, demo=demo,
    )


def _ensemble_consensus(home: str, away: str) -> Optional[Dict]:
    """Replicate predict_ensemble fusion READ-ONLY (no main(), no War Room fold)."""
    try:
        import glob
        import importlib.util
        import numpy as np
        import pandas as pd
        from sim.basketball_sim import TeamModel
        from sim import clutch_adjust as ca
        from predict_ensemble import _load_engines, _possession_engine, _clock_engine, _phi

        tm_home = TeamModel.from_cache(home)
        tm_away = TeamModel.from_cache(away)
        ctx = {"neutral_site": False}

        preds: List[Dict] = []
        for name, m in _load_engines():
            try:
                p = m.predict(home, away, ctx)
                p["engine"] = p.get("engine", name)
                preds.append(p)
            except Exception:
                pass

        preds.append(_possession_engine(tm_home, tm_away))
        preds.append(_clock_engine(tm_home, tm_away))

        if not preds:
            return None

        margins = [p["margin_home"] for p in preds]
        sds = [p["margin_sd"] for p in preds]
        totals = [p["total"] for p in preds]
        margins_arr = np.array(margins)
        sds_arr = np.array(sds)
        totals_arr = np.array(totals)

        eq_margin = float(margins_arr.mean())
        w = 1.0 / np.maximum(sds_arr, 1e-6) ** 2; w = w / w.sum()
        iv_margin = float((w * margins_arr).sum())
        pooled_sd = float(np.sqrt((w * sds_arr ** 2).sum()))
        eq_total = float(totals_arr.mean())
        engine_spread = float(margins_arr.std())

        eq_wp = _phi(eq_margin / max(pooled_sd, 1e-6))
        iv_wp = _phi(iv_margin / max(pooled_sd, 1e-6))

        # clutch overlay
        tg_path = os.path.join(_ROOT, "data", "cache", "team_system", "team_game.parquet")
        clutch_wp = eq_wp
        if os.path.exists(tg_path):
            try:
                tg = pd.read_parquet(tg_path)
                tilt = ca.clutch_tilt(home, away, tg)
                rng = np.random.default_rng(7)
                sim_margins = rng.normal(eq_margin, max(pooled_sd, 1e-6), 50000)
                adj = ca.adjust_margin(sim_margins.copy(), tilt)
                clutch_wp = float((adj > 0).mean())
            except Exception:
                pass

        proj_h = eq_total / 2 + eq_margin / 2
        proj_a = eq_total / 2 - eq_margin / 2

        lean_home = int((margins_arr > 0).sum())
        n_engines = len(preds)
        consensus_text = (
            f"{lean_home}/{n_engines} engines lean {home}; "
            f"disagreement {engine_spread:.1f} pts "
            f"(range {margins_arr.min():+.1f} to {margins_arr.max():+.1f})"
        )

        return {
            "engines": [
                {
                    "engine": p["engine"],
                    "win_prob_home": p["win_prob_home"],
                    "margin_home": p["margin_home"],
                    "total": p.get("total", 0.0),
                    "margin_sd": p["margin_sd"],
                    "n_models": p.get("n_models", 0),
                    "n_signals": p.get("n_signals", 0),
                    "notes": p.get("notes", ""),
                }
                for p in preds
            ],
            "eq_margin": eq_margin,
            "eq_wp": eq_wp,
            "iv_margin": iv_margin,
            "iv_wp": iv_wp,
            "eq_total": eq_total,
            "pooled_sd": pooled_sd,
            "engine_spread": engine_spread,
            "clutch_wp": clutch_wp,
            "proj_h": proj_h,
            "proj_a": proj_a,
            "consensus_text": consensus_text,
        }
    except Exception:
        return None


def _breakout_watch(result: Any) -> List[Dict]:
    """Top-6 non-stars by breakout p20 from player_props."""
    from prop_engine import player_props
    rows: List[Dict] = []
    for pid, d in result.players.items():
        try:
            props = player_props(d)
            med_pts = props.get("_med_pts", 0.0)
            if med_pts >= 18:
                continue  # skip stars
            bk = props.get("breakout", {})
            rows.append({
                "name": d.get("name", str(pid)),
                "team": d.get("team", ""),
                "p20": bk.get("p20", 0.0),
                "p30": bk.get("p30", 0.0),
                "ceiling": bk.get("ceiling", 0.0),
                "thr": bk.get("thr", 20.0),
                "prob": bk.get("prob", 0.0),
            })
        except Exception:
            continue
    rows.sort(key=lambda r: -r["p20"])
    return rows[:6]


def _plain_english(markets: List[Dict], max_n: int = 8) -> List[Dict]:
    """Translate flagged edges (edge>=MIN_EDGE AND ev>0) to plain-English sentences."""
    from prop_engine import LABEL

    candidates = [
        m for m in markets
        if m.get("edge") is not None
        and m["edge"] >= MIN_EDGE
        and (m.get("ev") or 0.0) > 0.0
    ]
    candidates.sort(key=lambda m: -(m.get("edge") or 0.0))
    candidates = candidates[:max_n]

    out: List[Dict] = []
    for m in candidates:
        edge = float(m.get("edge") or 0.0)
        if edge < 0.04:
            strength = "tiny"
        elif edge < 0.07:
            strength = "small"
        else:
            strength = "notable"

        stat_raw = m.get("stat") or ""
        stat_label = LABEL.get(stat_raw, stat_raw.upper())
        model_prob = float(m.get("model_prob") or 0.0)
        book_prob = float(m.get("book_prob") or 0.0)
        fair_am = m.get("fair_american") or 0
        book_odds = m.get("book_odds") or 0
        ev = float(m.get("ev") or 0.0)
        line = m.get("line")
        side = m.get("side", "over")
        entity_name = m.get("entity_name", m.get("entity", ""))
        line_str = f"{line:.1f}" if line is not None else "?"

        sentence = (
            f"Model gives {entity_name} {stat_label} {side} {line_str} "
            f"a {model_prob:.0%} chance "
            f"vs the book's implied {book_prob:.0%} -- a {strength} paper edge "
            f"(fair {fair_am:+d}, book {book_odds:+d}). "
            f"Playoffs = no proven edge; paper only."
        )

        out.append({
            "sentence": sentence,
            "entity_name": entity_name,
            "market_type": m.get("market_type", ""),
            "stat": stat_raw,
            "line": line,
            "side": side,
            "model_prob": model_prob,
            "book_prob": book_prob,
            "edge": edge,
            "book_odds": book_odds,
            "ev": ev,
            "strength": strength,
            "caveat": "Playoffs = no proven edge; paper only.",
        })
    return out


def _guardrail_portfolio(port: Dict, bankroll: float, max_bet_pct: float = 0.04) -> Dict:
    """Re-frame portfolio with guardrail framing (NEVER inflates stakes)."""
    guarded_bets = []
    for b in port.get("bets", []):
        bet_d = dict(b) if isinstance(b, dict) else b.__dict__.copy() if hasattr(b, "__dict__") else {}
        stake = float(bet_d.get("stake", 0.0))
        kelly_pct = float(bet_d.get("kelly_pct", 0.0))
        stake_pct_display = round(stake / bankroll * 100, 2) if bankroll > 0 else 0.0
        confirm_phrase = f"Type CONFIRM to stake ${stake:.2f}"
        bet_d["stake_pct_display"] = stake_pct_display
        bet_d["confirm_phrase"] = confirm_phrase
        guarded_bets.append(bet_d)

    return {
        "bets": guarded_bets,
        "total_stake": float(port.get("total_stake", 0.0)),
        "n_candidates": int(port.get("n_candidates", 0)),
        "bankroll": bankroll,
        "max_stake_pct": max_bet_pct,
        "honesty_class": "paper",
        "guardrail_note": (
            "Default stakes are tiny (<=4% bankroll). "
            "Over-betting requires explicit confirmation."
        ),
    }


def _live_section(game_id: str, fracs: tuple) -> Optional[Dict]:
    """Replay a cached game and sample checkpoints at frac points of elapsed time."""
    try:
        from live_replay_harness import (
            load_pbp, load_box, replay_game, reconcile as _reconcile,
        )
        # Validate files exist — raises FileNotFoundError if absent
        load_pbp(game_id)
        load_box(game_id)

        steps = replay_game(
            gid=game_id,
            backend="rog",
            n_sims=200,
            seed=42,
            step="possession",
        )
        if not steps:
            return None

        total_elapsed = max(s.elapsed_sec for s in steps)
        checkpoints = []
        for frac in fracs:
            target = frac * total_elapsed
            nearest = min(steps, key=lambda s: abs(s.elapsed_sec - target))
            checkpoints.append({
                "pct": round(frac * 100),
                "period": nearest.period,
                "clock_sec": round(nearest.clock_sec, 1),
                "home_score": nearest.home_score,
                "away_score": nearest.away_score,
                "proj_home_final": nearest.proj_home_final,
                "proj_away_final": nearest.proj_away_final,
                "home_win_prob": nearest.home_win_prob,
                "winprob_coherent": nearest.winprob_coherent,
                "coherent": nearest.coherent,
                "reprice_ms": nearest.reprice_ms,
            })

        recon = _reconcile(steps, game_id)
        reprice_times = [s.reprice_ms for s in steps if s.reprice_ms > 0]
        median_reprice_ms = float(sorted(reprice_times)[len(reprice_times) // 2]) if reprice_times else 0.0

        return {
            "game_id": game_id,
            "available": True,
            "checkpoints": checkpoints,
            "reconcile": recon,
            "median_reprice_ms": median_reprice_ms,
            "note": (
                "Replays COMPLETED game PBP leak-free "
                "(snapshot through step k only). Diagnostic, not a live feed."
            ),
        }
    except (FileNotFoundError, Exception):
        return None


def _clv_section(market: Optional[str], port: Dict) -> Dict:
    """Read CLV log (read-only) and build the paper bankroll/CLV section."""
    try:
        from clv_capture import open_close
        df = open_close(market)
        if df is None or (hasattr(df, "__len__") and len(df) == 0):
            raise ValueError("empty")

        n_pairs = int((df["snap_ts_open"] != df["snap_ts_close"]).sum())
        rows = []
        for _, row in df.head(25).iterrows():
            clv_cents = float(row.get("over_price_close", 0.0) or 0.0) - float(row.get("over_price_open", 0.0) or 0.0)
            moved = bool(str(row.get("snap_ts_open", "")) != str(row.get("snap_ts_close", "")))
            rows.append({
                "game": row.get("game", ""),
                "market": row.get("market", ""),
                "selection": row.get("selection", ""),
                "line": row.get("line", None),
                "book": row.get("book", ""),
                "open_price": row.get("over_price_open", None),
                "close_price": row.get("over_price_close", None),
                "clv_cents": round(clv_cents, 2),
                "moved": moved,
            })
        return {
            "open_close_pairs": len(df),
            "n_real_moves": n_pairs,
            "rows": rows,
            "clv_available": True,
            "paper_scoreboard": _paper_scoreboard(port),
            "note": (
                "Prop CLV is structurally un-gradable until the live daemon captures "
                "open->close. Game lines carry open/close."
            ),
        }
    except Exception:
        return {
            "open_close_pairs": 0,
            "n_real_moves": 0,
            "rows": [],
            "clv_available": False,
            "paper_scoreboard": _paper_scoreboard(port),
            "note": (
                "No CLV log yet. Run clv_capture.py --ingest-cached to populate. "
                "Prop CLV is structurally un-gradable until the live daemon captures open->close."
            ),
        }


def _paper_scoreboard(port: Dict) -> Dict:
    """Synthetic scoreboard — all bets PENDING, grades nothing."""
    bets_out = []
    for b in port.get("bets", []):
        bd = dict(b) if isinstance(b, dict) else b.__dict__.copy() if hasattr(b, "__dict__") else {}
        bets_out.append({
            "selection": bd.get("entity_name", ""),
            "market": bd.get("market_type", ""),
            "line": bd.get("line"),
            "side": bd.get("side", ""),
            "stake": float(bd.get("stake", 0.0)),
            "result": "PENDING",
            "pnl": 0.0,
        })
    return {
        "total_stake": float(port.get("total_stake", 0.0)),
        "total_pnl": 0.0,
        "roi": None,
        "bets": bets_out,
        "note": (
            "All PENDING -- paper board grades nothing. "
            "Real ROI needs forward CLV."
        ),
    }


# ---------------------------------------------------------------------------
# Public: build_board
# ---------------------------------------------------------------------------

def build_board(
    home: str = "NYK",
    away: str = "SAS",
    nsims: int = 3000,
    asof: Optional[str] = None,
    *,
    bankroll: float = DEFAULT_BANKROLL,
    paper_lines: Optional[Dict[str, Dict]] = None,
    demo: bool = True,
    live_game_id: Optional[str] = None,
    live_k_fracs: tuple = (0.25, 0.50, 0.75, 0.95),
    clv_market: Optional[str] = "player_assists",
    _result: Any = None,
) -> Dict[str, Any]:
    """Return the board dict (all sections). Sourced by CALLING the engines."""
    generated_utc = datetime.now(timezone.utc).isoformat()

    # --- Core sportsbook section ---
    sb = _sportsbook(home, away, nsims, asof, bankroll, paper_lines, demo, _result)
    result = sb["result"]
    markets: List[Dict] = sb["markets"]

    # --- Ensemble consensus (skip when _result injected for test speed) ---
    ensemble = None if _result is not None else _ensemble_consensus(home, away)

    # --- Team lines (spread/moneyline/team_total/game_total, over/yes side only) ---
    team_lines = [
        {
            "market_type": m["market_type"],
            "entity_name": m.get("entity_name", m.get("entity", "")),
            "line": m.get("line"),
            "side": m.get("side", ""),
            "model_prob": m.get("model_prob", 0.0),
            "fair_american": m.get("fair_american", 0),
        }
        for m in markets
        if m.get("market_type") in ("team_total", "spread", "moneyline", "game_total")
        and m.get("side") in ("over", "yes")
    ]

    # --- Top 12 player singles by model_prob (over) ---
    player_mkts = [
        m for m in markets
        if str(m.get("entity", "")).isdigit()
        and m.get("side") == "over"
        and str(m.get("market_type", "")).endswith("_ou")
    ]
    player_mkts.sort(key=lambda m: -(m.get("model_prob") or 0.0))
    top_props = [
        {
            "entity_name": m.get("entity_name", m.get("entity", "")),
            "market_type": m.get("market_type", ""),
            "stat": m.get("stat", ""),
            "line": m.get("line"),
            "side": m.get("side", ""),
            "model_prob": m.get("model_prob", 0.0),
            "fair_american": m.get("fair_american", 0),
        }
        for m in player_mkts[:12]
    ]

    # --- Breakout watch ---
    breakout_watch = _breakout_watch(result)

    # --- SGP ---
    sgp = sb.get("sgp", [])

    # --- Pregame section ---
    pregame = {
        "ensemble": ensemble,
        "team_lines": team_lines,
        "top_props": top_props,
        "breakout_watch": breakout_watch,
        "sgp": sgp,
    }

    # --- Plain-English edges ---
    edges_plain_english = _plain_english(markets)

    # --- Guardrail portfolio ---
    portfolio = _guardrail_portfolio(sb["portfolio"], bankroll)

    # --- Live section ---
    live = _live_section(live_game_id, live_k_fracs) if live_game_id else None

    # --- CLV / bankroll section ---
    bankroll_clv = _clv_section(clv_market, sb["portfolio"])

    # --- Guardrails ---
    guardrails = {
        "default_bankroll": DEFAULT_BANKROLL,
        "max_stake_pct": 0.04,
        "over_bet_requires_confirm": True,
        "under_bet_default": True,
        "honesty_class": "paper",
        "rules": [
            "Default bankroll is $100 (small, not $1000).",
            "Maximum bet is 4% of bankroll per market.",
            "Over-betting requires explicit CONFIRM text; pass/under is the default.",
            "No real money is placed; this is a paper board only.",
            "Playoffs have NO proven betting edge.",
            "ROI requires proven forward CLV from real captured prices.",
        ],
    }

    return {
        "meta": {
            "home": home,
            "away": away,
            "matchup": f"{away}@{home}",
            "nsims": nsims,
            "asof": asof,
            "bankroll": bankroll,
            "honesty_class": "paper",
            "generated_utc": generated_utc,
            "n_concrete": sb["n_concrete"],
            "n_types": sb["n_types"],
            "ontology_count": sb["ontology_count"],
        },
        "banners": [
            {"level": "critical", "text": "PAPER -- no real money is placed."},
            {"level": "critical", "text": "Playoffs: NO proven betting edge. The closing line beats the model in playoffs."},
            {"level": "warn",     "text": "ROI requires proven FORWARD CLV (real captured open->close prices). None claimed here."},
        ],
        "pregame": pregame,
        "edges_plain_english": edges_plain_english,
        "portfolio": portfolio,
        "live": live,
        "bankroll_clv": bankroll_clv,
        "guardrails": guardrails,
        "caveat": CAVEAT,
        "honesty_class": "paper",
    }


# ---------------------------------------------------------------------------
# __main__ — build NYK vs SAS board, print section keys + counts
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    print("CV_PAPER_BOARD gate:", is_enabled())
    print(f"Building board: NYK vs SAS, nsims=1500, demo=True ...")
    board = build_board(home="NYK", away="SAS", nsims=1500, demo=True)
    print(f"\n=== BOARD SECTIONS ===")
    for key, val in board.items():
        if key == "meta":
            print(f"  meta: {json.dumps(val, default=str)}")
        elif key == "banners":
            print(f"  banners: {len(val)} banners")
        elif key == "pregame":
            pg = val
            ens = pg.get("ensemble")
            n_engines = len(ens["engines"]) if ens and "engines" in ens else 0
            print(f"  pregame:")
            print(f"    ensemble: {n_engines} engines, eq_wp={ens['eq_wp']:.3f}" if ens else "    ensemble: None (cache missing)")
            print(f"    team_lines: {len(pg.get('team_lines', []))}")
            print(f"    top_props: {len(pg.get('top_props', []))}")
            print(f"    breakout_watch: {len(pg.get('breakout_watch', []))}")
            print(f"    sgp: {len(pg.get('sgp', []))}")
        elif key == "edges_plain_english":
            print(f"  edges_plain_english: {len(val)} edge sentences")
            for e in val[:3]:
                print(f"    - {e['sentence'][:90]}...")
        elif key == "portfolio":
            print(f"  portfolio: {len(val.get('bets', []))} bets, total_stake=${val.get('total_stake', 0.0):.2f}, bankroll=${val.get('bankroll', 0.0):.0f}")
        elif key == "live":
            if val is None:
                print(f"  live: None (no live_game_id supplied)")
            else:
                print(f"  live: game_id={val['game_id']}, checkpoints={len(val.get('checkpoints', []))}")
        elif key == "bankroll_clv":
            print(f"  bankroll_clv: clv_available={val.get('clv_available')}, pairs={val.get('open_close_pairs')}, scoreboard_bets={len(val.get('paper_scoreboard', {}).get('bets', []))}")
        elif key == "guardrails":
            print(f"  guardrails: {len(val.get('rules', []))} rules, max_stake_pct={val.get('max_stake_pct')}")
        elif key in ("caveat", "honesty_class"):
            print(f"  {key}: {val}")
    print(f"\nSection keys: {list(board.keys())}")
