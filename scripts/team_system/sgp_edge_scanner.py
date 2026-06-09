"""SGP Edge Scanner — surfaces same-game-parlay correlation mispricing from the possession sim.

Discipline: honesty_class="paper". This module DISPLAYS edges + honest status tags only.
It NEVER places, sizes, or logs a real-money bet. It emits only the SGP_CORR proven edge
(VALIDATED-STRUCTURE-ROI-PENDING), ranked by how wrong book-independence is.

Hard guard (enforced in proven_edge_card.py): any point-model-vs-line candidate is
REFUSED with a recorded reason. The +18.38% was market-follow; playoff model-vs-line
grades -2% to -5% vs real closes.

Run:
    python scripts/team_system/sgp_edge_scanner.py --home NYK --away SAS --top 20
    python -c "import scripts.team_system.sgp_edge_scanner as s; s.validate(1500)"
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from sim.sgp_from_sim import Leg, joint_prob, leg_prob  # READ-ONLY import

SGP_STATUS = "VALIDATED-STRUCTURE-ROI-PENDING"


@dataclass
class SgpEdge:
    legs: list                      # list[Leg]
    labels: list                    # ["Brunson O24 pts", ...] human strings
    joint: float                    # P(all hit) from coherent samples
    independent: float              # product of marginals
    lift: float                     # joint / independent
    abs_lift_error: float           # abs(lift - 1.0)  -> ranking key
    direction: str                  # "fade" if lift<1 (independence OVER-prices the parlay)
                                    # "take" if lift>1 (independence UNDER-prices it)
    basket_type: str                # "same_player" | "teammate" | "cross_team"
    fair_decimal: float             # 1/joint
    status: str = SGP_STATUS


def _basket_type(result: Any, legs: list) -> str:
    """same_player if 1 pid; teammate if all same team; else cross_team."""
    pids = list({lg.pid for lg in legs})
    if len(pids) == 1:
        return "same_player"
    teams = {result.players[p]["team"] for p in pids if p in result.players}
    if len(teams) == 1:
        return "teammate"
    return "cross_team"


def _label(result: Any, leg: Any) -> str:
    """'<name> O<line:g> <stat>' / 'U' for unders."""
    p = result.players.get(leg.pid, {})
    name = p.get("name", str(leg.pid))
    side = "O" if leg.over else "U"
    return f"{name} {side}{leg.line:g} {leg.stat}"


def _candidate_baskets(
    result: Any,
    *,
    min_pts_mean: float = 8.0,
    max_pid: Optional[int] = None,
) -> List[Tuple[str, List[Any]]]:
    """Enumerate the structurally-interesting baskets at the sim's OWN median lines
    (each leg ~50/50 so the read isolates correlation, matching validate_joint_calibration):
      - same_player 2-leg: (pts,ast),(pts,reb),(reb,ast)  [expect lift>1 -> 'take']
      - teammate 2-leg all-over pts pairs among rotation players (mean pts>=min_pts_mean)
        [shared pie -> expect lift<1 -> 'fade' the all-over stack]
      - cross_team 2-leg pts pairs (one per team) [weakly + via game total]
    Lines = float(np.median(samples[stat])); over=True for the all-over stacks,
    over default True for same-player double-double legs.
    Returns list[(basket_type, legs:list[Leg])].
    """
    players = result.players
    pids = list(players.keys())
    if max_pid is not None:
        pids = pids[:max_pid]

    rotation = [p for p in pids if players[p]["mean"]["pts"] >= min_pts_mean]

    def med_line(pid: int, stat: str) -> float:
        return float(np.median(players[pid]["samples"][stat]))

    baskets: List[Tuple[str, List[Any]]] = []

    # --- same_player 2-leg: (pts,ast),(pts,reb),(reb,ast) — expect lift>1 ---
    for pid in rotation:
        for s1, s2 in [("pts", "ast"), ("pts", "reb"), ("reb", "ast")]:
            legs: List[Any] = [
                Leg(pid, s1, med_line(pid, s1), True),
                Leg(pid, s2, med_line(pid, s2), True),
            ]
            baskets.append(("same_player", legs))

    # --- teammate 2-leg all-over pts pairs — expect lift<1 (shared pie) ---
    team_map: dict = {}
    for p in rotation:
        t = players[p].get("team", "UNK")
        team_map.setdefault(t, []).append(p)

    for _t, members in team_map.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                p1, p2 = members[i], members[j]
                legs = [
                    Leg(p1, "pts", med_line(p1, "pts"), True),
                    Leg(p2, "pts", med_line(p2, "pts"), True),
                ]
                baskets.append(("teammate", legs))

    # --- cross_team 2-leg pts pairs (one per team) ---
    team_list = list(team_map.keys())
    if len(team_list) >= 2:
        for i in range(len(team_list)):
            for j in range(i + 1, len(team_list)):
                leads_i = team_map[team_list[i]][:3]
                leads_j = team_map[team_list[j]][:3]
                for p1 in leads_i:
                    for p2 in leads_j:
                        legs = [
                            Leg(p1, "pts", med_line(p1, "pts"), True),
                            Leg(p2, "pts", med_line(p2, "pts"), True),
                        ]
                        baskets.append(("cross_team", legs))

    return baskets


def scan_sgp_edges(result: Any, top_n: int = 20, *, min_pts_mean: float = 8.0) -> list:
    """Rank baskets by how WRONG book-independence is (abs_lift_error desc).

    For each candidate: j,ind,lift = joint_prob(result, legs);
      direction = 'fade' if lift < 1 else 'take';
    Returns top_n SgpEdge sorted by -abs_lift_error.

    Semantics surfaced to the card:
      * teammate all-over stack with lift<1  -> 'fade' (book independence OVER-prices)
      * correctly-correlated same-player combo lift>1 -> 'take' (independence UNDER-prices)

    HONEST: status=VALIDATED-STRUCTURE-ROI-PENDING on EVERY edge (no ROI claim;
    real only where a book quotes the parlay as independent legs).
    """
    candidates = _candidate_baskets(result, min_pts_mean=min_pts_mean)
    edges = []
    for btype, legs in candidates:
        try:
            j, ind, lift = joint_prob(result, legs)
        except Exception:
            continue
        if np.isnan(lift) or ind < 1e-9:
            continue
        abs_err = abs(lift - 1.0)
        direction = "fade" if lift < 1.0 else "take"
        fair_dec = 1.0 / j if j > 1e-9 else float("inf")
        labels = [_label(result, lg) for lg in legs]
        edges.append(SgpEdge(
            legs=legs,
            labels=labels,
            joint=j,
            independent=ind,
            lift=lift,
            abs_lift_error=abs_err,
            direction=direction,
            basket_type=btype,
            fair_decimal=fair_dec,
            status=SGP_STATUS,
        ))

    edges.sort(key=lambda e: e.abs_lift_error, reverse=True)
    return edges[:top_n]


def describe_scan(edges: list) -> str:
    """Multi-line table: rank | basket | joint | indep | lift | dir | status."""
    if not edges:
        return "  (no SGP edges found)"
    lines = [
        f"{'#':>3}  {'basket':<45}  {'joint':>6}  {'indep':>6}  {'lift':>6}  {'dir':<5}  status",
        "-" * 112,
    ]
    for i, e in enumerate(edges, 1):
        basket_str = " + ".join(e.labels)[:44]
        lines.append(
            f"{i:>3}  {basket_str:<45}  {e.joint:>6.1%}  {e.independent:>6.1%}"
            f"  x{e.lift:>4.2f}  {e.direction:<5}  {e.status}"
        )
    return "\n".join(lines)


def validate(n_par: int = 1500) -> None:
    """Thin pass-through to sgp_from_sim.validate_joint_calibration(n_par) so the
    scanner's structural premise is re-graded in one command (sim-joint vs independence Brier)."""
    from sim.sgp_from_sim import validate_joint_calibration
    validate_joint_calibration(n_par)


# ---------------------------------------------------------------------------
# __main__ — guarded so import for tests never runs the sim
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="SGP edge scanner")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()

    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast

    print(f"Building sim: {a.away} @ {a.home} (40000 sims) ...")
    res = simulate_game_fast(
        TeamModel.from_cache(a.home),
        TeamModel.from_cache(a.away),
        n_sims=40000,
        seed=2026,
        anchor=True,
        defense=True,
    )
    print(f"\n=== SGP edge scanner — {a.away} @ {a.home} (top {a.top}) ===")
    print(f"PAPER / DISPLAY ONLY — {SGP_STATUS}")
    print(f"Real only where a book prices SGP legs as independent (sharp books adjust).\n")
    edges = scan_sgp_edges(res, a.top)
    print(describe_scan(edges))

    if a.validate:
        print()
        validate(1500)
