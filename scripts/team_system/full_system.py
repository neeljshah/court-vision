"""full_system.py -- the COMPOSITION SPINE for the NBA paper system.

Discipline (read before editing):
  * COMPOSES existing modules; it NEVER reimplements or edits them.
  * honesty_class = "paper" / "serve" -- projections + the PROVEN-edge card
    (never a point-model edge) + a paper board. NO real-money placement.
  * EFFICIENCY: the heavy possession sim runs exactly ONCE (one prop_engine.run).
    The SAME GameSimResult feeds props + market_catalog + sgp_edge_scanner +
    proven_edge_card + (optionally) the V9 board. predict_ensemble runs ONCE.
  * Every downstream module is imported defensively (try/except) so a module
    that is still being built degrades to a status string instead of crashing.

Gate: the optional board render is behind CV_FULL_SYSTEM_BOARD (default OFF).
With render=False (default) and the gate unset, behaviour is the lean path.

Public API
----------
    system_predict(home, away, asof=None, nsims=8000, render=False) -> dict
    system_live_replay(gid) -> dict
    print_summary(out) -> None   # clean console summary of either dict

Validate:  python scripts/team_system/full_system.py --validate
Board green: python -m pytest tests/test_sim_engine.py -q
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional

# Replicate the path discipline the team_system modules use so flat imports
# (`from sportsbook_engine import ...`, `from sim.fast_sim import ...`) resolve.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

HONESTY_CLASS = "paper"
_BOARD_GATE = "CV_FULL_SYSTEM_BOARD"


def _board_enabled() -> bool:
    return os.environ.get(_BOARD_GATE, "0").strip().lower() in ("1", "true", "yes", "on")


def _try(label: str, fn):
    """Run fn(); on any failure return a degrade marker instead of raising."""
    try:
        return fn(), None
    except Exception as e:  # noqa: BLE001 -- graceful degrade is the contract
        return None, f"[{label} unavailable: {type(e).__name__}: {str(e)[:120]}]"


# ---------------------------------------------------------------------------
# system_predict -- ONE sim feeds everything
# ---------------------------------------------------------------------------
def system_predict(
    home: str,
    away: str,
    asof: Optional[str] = None,
    nsims: int = 8000,
    render: bool = False,
) -> Dict[str, Any]:
    """Single coherent paper dict from ONE possession sim + ONE ensemble read.

    Flow (no re-sim anywhere downstream):
        1. prop_engine.run(...)            -> the ONE heavy GameSimResult `res`
        2. prop_engine.player_props(d)     -> per-player prop slate (reads res)
        3. predict_ensemble._clock_engine  -> cheap independent trajectory view;
           the possession consensus row is derived from `res` (NO 2nd heavy sim)
        4. market_catalog.price_markets(res, None)   -> fair priced menu
        5. portfolio_optimizer.build_portfolio(res, markets)  -> paper portfolio
        6. sgp_edge_scanner.scan_sgp_edges(res)      -> ranked SGP structure
        7. proven_edge_card.build_proven_edge_card(..., result=res) -> honest card
        8. (render or gate) board_data.build_board(..., _result=res) + board_render

    Returns
    -------
    {
      "matchup", "asof", "nsims", "honesty_class",
      "ensemble":          {...} | degrade-str,
      "sim_slate":         {pid: props} | degrade-str,
      "sportsbook":        {"markets": [...], "portfolio": {...}} | degrade-str,
      "sgp_edges":         [SgpEdge,...] | degrade-str,
      "proven_edge_card":  {...} | degrade-str,
      "board_html":        str | None,
      "degraded":          [labels...],
    }
    """
    home, away = home.upper(), away.upper()
    out: Dict[str, Any] = {
        "matchup": f"{away}@{home}", "asof": asof, "nsims": nsims,
        "honesty_class": HONESTY_CLASS, "degraded": [],
    }

    # --- 1. THE ONE heavy sim -------------------------------------------------
    from prop_engine import run as _prop_run, player_props as _player_props
    res = _prop_run(home, away, nsims, asof, False)   # GameSimResult (the spine)
    out["_has_result"] = res is not None

    # --- 2. per-player prop slate (reads res) --------------------------------
    slate, err = _try("sim_slate", lambda: {pid: _player_props(d) for pid, d in res.players.items()})
    out["sim_slate"] = slate if err is None else err
    if err:
        out["degraded"].append("sim_slate")

    # --- 3. ensemble consensus: clock engine (cheap) + possession from `res` --
    def _ensemble():
        import numpy as np
        import predict_ensemble as pe
        from sim.basketball_sim import TeamModel
        m = res.home_total - res.away_total
        poss = {
            "engine": "possession_mc",
            "win_prob_home": float((m > 0).mean()),
            "margin_home": float(m.mean()),
            "total": float((res.home_total + res.away_total).mean()),
        }
        # cheap independent trajectory engine (its own small sim -- NOT the heavy one)
        h = TeamModel.from_cache(home)
        a = TeamModel.from_cache(away)
        clk = pe._clock_engine(h, a, n=2000)
        rows = [poss, {k: clk[k] for k in ("engine", "win_prob_home", "margin_home", "total")}]
        cons_wp = float(np.mean([r["win_prob_home"] for r in rows]))
        return {
            "engines": rows,
            "consensus_win_prob_home": cons_wp,
            "consensus_margin_home": float(np.mean([r["margin_home"] for r in rows])),
            "disagreement_winprob": float(abs(rows[0]["win_prob_home"] - rows[1]["win_prob_home"])),
        }
    ens, err = _try("ensemble", _ensemble)
    out["ensemble"] = ens if err is None else err
    if err:
        out["degraded"].append("ensemble")

    # --- 4 + 5. priced menu + paper portfolio (read res) ----------------------
    def _sportsbook():
        from market_catalog import price_markets
        from portfolio_optimizer import build_portfolio
        markets = price_markets(res, None)          # fair prices only (no book lines)
        portfolio = build_portfolio(res, markets, bankroll=100.0)
        return {"markets": markets, "portfolio": portfolio, "n_markets": len(markets)}
    sb, err = _try("sportsbook", _sportsbook)
    out["sportsbook"] = sb if err is None else err
    if err:
        out["degraded"].append("sportsbook")

    # --- 6. SGP edge structure (reads res) ------------------------------------
    sgp, err = _try("sgp_edges", lambda: __import__("sgp_edge_scanner").scan_sgp_edges(res, top_n=8))
    out["sgp_edges"] = sgp if err is None else err
    if err:
        out["degraded"].append("sgp_edges")

    # --- 7. PROVEN-edge card (reads res; refuses model-vs-line edges) ---------
    def _card():
        from proven_edge_card import build_proven_edge_card
        return build_proven_edge_card(home, away, asof=asof, result=res, sgp_top_n=8)
    card, err = _try("proven_edge_card", _card)
    out["proven_edge_card"] = card if err is None else err
    if err:
        out["degraded"].append("proven_edge_card")

    # --- 8. optional V9 board (gated/flagged; injects res -> NO re-sim) --------
    out["board_html"] = None
    if render or _board_enabled():
        def _board():
            from board_data import build_board
            from board_render import render_board
            board = build_board(home, away, nsims=nsims, asof=asof, demo=True, _result=res)
            return render_board(board)
        html, err = _try("board", _board)
        out["board_html"] = html if err is None else None
        if err:
            out["degraded"].append("board")
    out.pop("_has_result", None)
    return out


# ---------------------------------------------------------------------------
# system_live_replay -- V8 harness + live_winprob -> paper live read
# ---------------------------------------------------------------------------
def system_live_replay(gid: str) -> Dict[str, Any]:
    """Compose the V8 live harness + live_winprob into a paper live board read.

    Walks a completed game's PBP leak-free (replay_game), then summarises the
    final ReplayStep through a live_winprob coherence check. honesty_class=serve.
    Returns {gid, honesty_class, n_steps, final_step{...}, winprob_check, degraded}.
    """
    out: Dict[str, Any] = {"gid": gid, "honesty_class": "serve", "degraded": []}

    steps, err = _try("live_replay", lambda: __import__("live_replay_harness").replay_game(gid, n_sims=200))
    if err is not None:
        out["live_replay"] = err
        out["degraded"].append("live_replay")
        out["n_steps"] = 0
        return out

    out["n_steps"] = len(steps)
    if not steps:
        out["final_step"] = None
        return out

    last = steps[-1]
    out["final_step"] = {
        "action_idx": last.action_idx, "period": last.period,
        "sec_remaining": last.sec_remaining,
        "home_score": last.home_score, "away_score": last.away_score,
        "proj_home_final": last.proj_home_final, "proj_away_final": last.proj_away_final,
        "home_win_prob": last.home_win_prob, "winprob_coherent": last.winprob_coherent,
        "coherent": last.coherent,
    }

    def _wp():
        from live_winprob import live_win_prob
        margin = last.home_score - last.away_score
        return live_win_prob(margin, last.sec_remaining)
    wp, err = _try("live_winprob", _wp)
    out["winprob_check"] = wp if err is None else err
    if err:
        out["degraded"].append("live_winprob")
    return out


# ---------------------------------------------------------------------------
# Clean printed summary
# ---------------------------------------------------------------------------
def print_summary(out: Dict[str, Any]) -> None:
    """Terse console summary for either system_predict or system_live_replay."""
    print("=" * 64)
    if "matchup" in out:
        print(f"FULL SYSTEM (paper)  {out['matchup']}  nsims={out['nsims']}  asof={out['asof']}")
        print(f"honesty_class={out['honesty_class']}")
        ens = out.get("ensemble")
        if isinstance(ens, dict):
            print(f"  ensemble: P(home)={ens['consensus_win_prob_home']:.3f} "
                  f"margin={ens['consensus_margin_home']:+.1f} "
                  f"disagree={ens['disagreement_winprob']:.3f}")
        else:
            print(f"  ensemble: {ens}")
        sl = out.get("sim_slate")
        print(f"  sim_slate: {len(sl)} players" if isinstance(sl, dict) else f"  sim_slate: {sl}")
        sb = out.get("sportsbook")
        if isinstance(sb, dict):
            port = sb.get("portfolio", {})
            n_bets = len(port.get("bets", [])) if isinstance(port, dict) else 0
            print(f"  sportsbook: {sb['n_markets']} markets | portfolio {n_bets} paper bets")
        else:
            print(f"  sportsbook: {sb}")
        sg = out.get("sgp_edges")
        print(f"  sgp_edges: {len(sg)} ranked" if isinstance(sg, list) else f"  sgp_edges: {sg}")
        card = out.get("proven_edge_card")
        if isinstance(card, dict):
            print(f"  proven_edge_card: {len(card.get('edges', []))} edges, "
                  f"{len(card.get('refused', []))} refused (no point-model edge)")
        else:
            print(f"  proven_edge_card: {card}")
        print(f"  board_html: {'rendered' if out.get('board_html') else 'not rendered'}")
    else:
        print(f"LIVE REPLAY (paper)  gid={out['gid']}  honesty_class={out['honesty_class']}")
        print(f"  steps={out['n_steps']}")
        fs = out.get("final_step")
        if fs:
            print(f"  final: P{fs['period']} {fs['sec_remaining']:.0f}s "
                  f"{fs['home_score']}-{fs['away_score']}  "
                  f"P(home)={fs['home_win_prob']:.3f} (coherent={fs['coherent']})")
            wc = out.get("winprob_check")
            if isinstance(wc, float):
                print(f"  live_winprob check: {wc:.3f}")
    if out.get("degraded"):
        print(f"  degraded modules: {', '.join(out['degraded'])}")
    print("=" * 64)


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Full-system spine (paper).")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--nsims", type=int, default=8000)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--live", default=None, help="game id -> run system_live_replay")
    ap.add_argument("--validate", action="store_true", help="fast smoke (small nsims)")
    a = ap.parse_args(argv)

    if a.live:
        print_summary(system_live_replay(a.live))
        return 0
    nsims = 400 if a.validate else a.nsims
    out = system_predict(a.home, a.away, asof=a.asof, nsims=nsims, render=a.render)
    print_summary(out)
    if a.validate:
        ok = isinstance(out.get("sim_slate"), dict) and len(out["sim_slate"]) > 0
        print(f"VALIDATE: {'PASS' if ok else 'FAIL'} (degraded={out['degraded']})")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
