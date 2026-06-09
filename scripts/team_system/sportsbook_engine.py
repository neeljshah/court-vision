"""sportsbook_engine.py — V7 paper sportsbook integrator (gated CV_SPORTSBOOK_ENGINE).

Composes ONE coherent possession sim into the full paper book:
  market_catalog.price_markets  -> prices >=100 concrete markets from the joint samples
  sgp_from_sim.joint_prob       -> SGP joint vs product-of-marginals on correlated baskets
  portfolio_optimizer.build_portfolio -> a ranked PAPER Kelly portfolio (correlation-aware)

Everything reads ONE GameSimResult produced by prop_engine.run (which calls
simulate_game_fast(anchor=True, defense=True)).  No real-money path is ever touched:
no log_bet / record_clv / bet_log.json.  When no paper book lines are supplied the
engine prints FAIR prices only and an HONEST empty portfolio (no fabricated edge).

Gated: when CV_SPORTSBOOK_ENGINE is unset/0, the module is a no-op (the --demo CLI
flag forces it on for the demo).  The module is new + standalone -> importing it is
byte-side-effect-free; nothing runs until main() is invoked.

PAPER pricing only -- no real-money path. Playoffs have NO proven edge.
ROI requires real captured prices + proven forward CLV.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

# sys.path bootstrap mirrors prop_engine.py lines 16-17
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"
))

__all__ = ["main", "run_engine", "synth_paper_lines", "CAVEAT", "is_enabled"]

CAVEAT = (
    "PAPER pricing only -- no real-money path. "
    "Playoffs have NO proven edge. "
    "ROI requires real captured prices + proven forward CLV."
)


def is_enabled(force: bool = False) -> bool:
    """Gate: CV_SPORTSBOOK_ENGINE in {1,true,yes,on} OR force (the --demo flag)."""
    if force:
        return True
    return os.environ.get("CV_SPORTSBOOK_ENGINE", "0").strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Synthetic paper lines (demo only) — a handful of book lines around the sim
# medians, shaded to -110/+100, so the EV/edge + portfolio paths exercise
# end-to-end WITHOUT any real captured prices.  These are FAKE prices for a
# code path test, NOT a claimed edge.
# ---------------------------------------------------------------------------

def synth_paper_lines(result, n_players: int = 4) -> Dict[str, Dict]:
    """Build a small paper_lines dict around sim medians (shaded -110/+100).

    Lines are nudged slightly UNDER the sim median on the over side so the model
    prob sits above the de-vigged book prob -> a small synthetic +edge to drive
    the portfolio path.  Two-way keys (de-vigged) for player singles/combos +
    team totals; this is a fixture, not a market read.
    """
    import numpy as np
    from prop_engine import _combos, _qline

    lines: Dict[str, Dict] = {}

    # rotation by median pts desc
    rotation = sorted(
        (pid for pid, d in result.players.items()
         if float(np.median(d["samples"]["pts"])) >= 6.0),
        key=lambda pid: -float(np.median(result.players[pid]["samples"]["pts"])),
    )

    for pid in rotation[:n_players]:
        s = {k: np.asarray(v, float) for k, v in result.players[pid]["samples"].items()}
        c = _combos(s)
        ent = str(pid)
        for stat, mtype in [("pts", "pts_ou"), ("reb", "reb_ou"),
                            ("ast", "ast_ou"), ("pra", "pra_ou")]:
            arr = c[stat]
            # IMPORTANT: market_catalog prices each market at ITS OWN _qline (the sim
            # median), so model_prob(over) ~= 0.50.  To synthesize a +edge for the
            # OVER side we must (a) use the SAME line the catalog uses (_qline) and
            # (b) shade the ODDS so the de-vigged book over-prob sits BELOW 0.50
            # (over +110 / under -130 -> devig over ~0.473 -> edge ~+0.027).
            # FAKE prices for a code-path test, NOT a claimed edge.
            line = _qline(arr)
            if line < 0.5:
                continue
            lines[f"{ent}|{mtype}"] = {"line": line, "over_odds": 110, "under_odds": -130}

    # team totals (two-way) at the catalog's _qline, over shaded to value (+110/-130)
    home_total = np.asarray(result.home_total, float)
    away_total = np.asarray(result.away_total, float)
    for tri, arr in [(result.home_tri, home_total), (result.away_tri, away_total)]:
        lines[f"{tri}|team_total"] = {"line": _qline(arr), "over_odds": 110, "under_odds": -130}

    # game total (two-way)
    gt = home_total + away_total
    lines["GAME|game_total"] = {"line": _qline(gt), "over_odds": 110, "under_odds": -130}

    return lines


# ---------------------------------------------------------------------------
# SGP baskets: teammate stack (-corr), same-player pts+reb (+corr), cross-team
# ---------------------------------------------------------------------------

def _build_sgp_baskets(result):
    """Return list of (label, [Leg,...]) — Leg supports pts/reb/ast only."""
    import numpy as np
    from sim.sgp_from_sim import Leg

    home_pids = [pid for pid, d in result.players.items() if d["team"] == result.home_tri]
    away_pids = [pid for pid, d in result.players.items() if d["team"] == result.away_tri]

    def _med(pid, stat):
        return float(np.median(result.players[pid]["samples"][stat]))

    def _line(pid, stat):
        return round(_med(pid, stat) * 2) / 2

    # top-2 scorers on the home team, top scorer away
    home_sorted = sorted(home_pids, key=lambda p: -_med(p, "pts"))
    away_sorted = sorted(away_pids, key=lambda p: -_med(p, "pts"))

    baskets = []
    nm = lambda p: result.players[p]["name"]

    if len(home_sorted) >= 1:
        p = home_sorted[0]
        baskets.append((
            f"SAME-PLAYER {nm(p)} pts & reb (+corr expected)",
            [Leg(int(p), "pts", _line(p, "pts")), Leg(int(p), "reb", _line(p, "reb"))],
        ))
    if len(home_sorted) >= 2:
        p1, p2 = home_sorted[0], home_sorted[1]
        baskets.append((
            f"TEAMMATE STACK {nm(p1)} pts & {nm(p2)} pts (-corr: shared pie)",
            [Leg(int(p1), "pts", _line(p1, "pts")), Leg(int(p2), "pts", _line(p2, "pts"))],
        ))
    if home_sorted and away_sorted:
        p1, p2 = home_sorted[0], away_sorted[0]
        baskets.append((
            f"CROSS-TEAM {nm(p1)} pts & {nm(p2)} pts",
            [Leg(int(p1), "pts", _line(p1, "pts")), Leg(int(p2), "pts", _line(p2, "pts"))],
        ))
    return baskets


# ---------------------------------------------------------------------------
# Core orchestration (returns a structured dict; printing handled by main)
# ---------------------------------------------------------------------------

def run_engine(
    home: str = "NYK",
    away: str = "SAS",
    nsims: int = 3000,
    asof: Optional[str] = None,
    no_avail: bool = False,
    paper_lines: Optional[Dict[str, Dict]] = None,
    bankroll: float = 1000.0,
    demo: bool = False,
) -> Dict:
    """Produce ONE joint sim and compose catalog + SGP + portfolio.

    Returns a dict with the priced markets, ontology count, sgp baskets, and
    paper portfolio.  All honesty_class = paper.
    """
    from prop_engine import run as _run
    from market_catalog import price_markets, ontology_count
    from portfolio_optimizer import build_portfolio
    from sim.sgp_from_sim import joint_prob

    result = _run(home, away, nsims, asof, no_avail)

    if demo and paper_lines is None:
        paper_lines = synth_paper_lines(result)

    markets = price_markets(result, paper_lines)
    n_concrete = len(markets)
    n_types = len({m["market_type"] for m in markets})
    onto = ontology_count(result)

    # SGP baskets
    sgp = []
    for label, legs in _build_sgp_baskets(result):
        j, ind, lift = joint_prob(result, legs)
        sgp.append({"label": label, "joint": j, "independent": ind, "lift": lift,
                    "legs": [(lg.pid, lg.stat, lg.line, lg.over) for lg in legs]})

    # Portfolio (honest empty when no paper lines)
    portfolio = build_portfolio(result, markets, bankroll=bankroll)

    return {
        "result": result,
        "markets": markets,
        "n_concrete": n_concrete,
        "n_types": n_types,
        "ontology_count": onto,
        "sgp": sgp,
        "portfolio": portfolio,
        "paper_lines": paper_lines,
        "honesty_class": "paper",
        "caveat": CAVEAT,
    }


def _print_report(out: Dict, home: str, away: str, nsims: int) -> None:
    result = out["result"]
    markets = out["markets"]

    print(f"=== V7 PAPER SPORTSBOOK ENGINE: {away} @ {home} ({nsims} sims) ===")
    print(f"honesty_class: {out['honesty_class']}")
    print()
    print(f"Concrete markets priced: {out['n_concrete']}   "
          f"(distinct market types: {out['n_types']};  ontology_count={out['ontology_count']})")

    # --- top fair prices: most-confident player singles/combos ---
    print("\n--- Top fair prices (highest-confidence player markets) ---")
    player_mkts = [m for m in markets
                   if m["entity"].isdigit() and m["side"] == "over"
                   and m["market_type"].endswith("_ou")]
    player_mkts.sort(key=lambda m: -m["model_prob"])
    print(f"{'player':18s} {'market':9s} {'line':>6s} {'side':5s} {'model_p':>8s} {'fair':>7s}")
    for m in player_mkts[:8]:
        print(f"{m['entity_name'][:18]:18s} {m['market_type']:9s} {m['line']:6.1f} "
              f"{m['side']:5s} {m['model_prob']:8.3f} {m['fair_american']:>7d}")

    # --- team / game fair prices ---
    print("\n--- Team / game fair lines ---")
    for m in markets:
        if m["market_type"] in ("team_total", "spread", "moneyline", "game_total") and m["side"] in ("over", "yes"):
            ln = f"{m['line']:.1f}" if m["line"] is not None else "  -"
            print(f"{m['entity_name'][:18]:18s} {m['market_type']:11s} line={ln:>6s} "
                  f"model_p={m['model_prob']:.3f} fair={m['fair_american']:+d}")

    # --- SGP joint vs product-of-marginals ---
    print("\n--- Same-Game Parlay: JOINT (from coherent sim) vs PRODUCT-OF-MARGINALS ---")
    for b in out["sgp"]:
        print(f"  {b['label']}")
        print(f"     joint {b['joint']:.1%}  |  product-of-marginals {b['independent']:.1%}  "
              f"|  correlation lift x{b['lift']:.2f}")

    # --- paper portfolio ---
    port = out["portfolio"]
    print("\n--- Ranked PAPER portfolio (correlation-aware Kelly) ---")
    if not out["paper_lines"]:
        print("  No paper book lines supplied -> FAIR prices only, NO edge claimed.")
        print(f"  Portfolio: 0 bets (n_candidates={port['n_candidates']}, honesty_class={port['honesty_class']}).")
    elif not port["bets"]:
        print(f"  No +EV markets above threshold (n_candidates={port['n_candidates']}). Empty portfolio (honest).")
    else:
        print(f"{'#':>2}  {'entity':16s} {'market':11s} {'line':>6s} {'side':5s} "
              f"{'mp':>6s} {'odds':>5s} {'edge':>7s} {'ev':>7s} {'corr':>5s} {'stake$':>8s} {'k%':>5s}")
        for i, b in enumerate(port["bets"], 1):
            ln = f"{b['line']:.1f}" if b["line"] is not None else "  -"
            print(f"{i:>2}  {b['entity_name'][:16]:16s} {b['market_type']:11s} {ln:>6s} {b['side']:5s} "
                  f"{b['model_prob']:6.3f} {b['book_odds']:>5d} {b['edge']:7.4f} {b['ev']:7.4f} "
                  f"{b['corr_to_book']:5.3f} {b['stake']:8.2f} {b['kelly_pct']*100:4.1f}%")
        print(f"  Total stake: ${port['total_stake']:.2f} / ${port['bankroll']:.0f} bankroll  "
              f"| candidates={port['n_candidates']} | honesty_class={port['honesty_class']}")

    # --- optional registry artifact row (best-effort, gated, paper) ---
    _maybe_store_registry(out, home, away, nsims)

    print()
    print("FOOTER -- " + out["caveat"])


def _maybe_store_registry(out: Dict, home: str, away: str, nsims: int) -> None:
    """Best-effort artifact row behind the same gate. No-op if no registry module."""
    try:
        import registry  # type: ignore
        store = getattr(registry, "store", None)
        if store is None:
            return
        store({
            "kind": "sportsbook_engine_paper",
            "matchup": f"{away}@{home}",
            "nsims": nsims,
            "n_markets": out["n_concrete"],
            "n_types": out["n_types"],
            "n_bets": len(out["portfolio"]["bets"]),
            "honesty_class": "paper",
        })
        print("  (registry artifact row stored, honesty_class=paper)")
    except Exception:
        pass  # registry is optional


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="V7 paper sportsbook engine (gated).")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=3000)
    ap.add_argument("--asof", default=None)
    ap.add_argument("--no-availability", action="store_true")
    ap.add_argument("--paper-lines", default=None, help="optional path to a paper_lines JSON")
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--demo", action="store_true",
                    help="force the engine on + synthesize paper lines around sim medians")
    a = ap.parse_args(argv)

    if not is_enabled(force=a.demo):
        print("CV_SPORTSBOOK_ENGINE unset -- paper sportsbook engine disabled (no-op).")
        return 0

    paper_lines: Optional[Dict[str, Dict]] = None
    if a.paper_lines:
        with open(a.paper_lines, encoding="utf-8") as fh:
            paper_lines = json.load(fh)

    out = run_engine(
        home=a.home, away=a.away, nsims=a.nsims, asof=a.asof,
        no_avail=a.no_availability, paper_lines=paper_lines,
        bankroll=a.bankroll, demo=a.demo,
    )
    _print_report(out, a.home, a.away, a.nsims)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
