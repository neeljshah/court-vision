"""Same-game-parlay (SGP) joint pricing straight from the possession sim's coherent samples.

The sim's whole edge over a marginal prop model is the JOINT distribution: it samples thousands of
internally-consistent games, so a player's pts/reb/ast move together (same-player), teammates share a
fixed scoring pie (negative pts-pts), and everyone correlates with the game total. A correctly-priced
SGP needs exactly that joint structure -- pricing legs as independent (the naive product of marginals)
systematically MIS-prices correlated baskets. This reads the joint probability for any set of legs directly
off the sim samples (the fraction of simulated games where ALL legs hit), and reports the CORRELATION LIFT
vs the independence product so you can see where independence is wrong.

Honest scope: the joint STRUCTURE is validated (teammate-rho -0.104 ~ real; validate_joint_calibration here
grades sim-joint vs realized on historical games). ROI is NOT claimed -- that needs real SGP price capture
(none in the repo); see project memory + feedback_edge_publish_pressure_hold_honest_line.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Leg:
    pid: int
    stat: str          # "pts" | "reb" | "ast"
    line: float
    over: bool = True

    def hit(self, samples) -> np.ndarray:
        x = samples[self.pid]["samples"][self.stat]
        return x > self.line if self.over else x < self.line


def leg_prob(result, leg: Leg) -> float:
    return float(leg.hit(result.players).mean())


def joint_prob(result, legs):
    """Return (joint, independent, lift) for a list of Legs.
    joint = P(all hit) from the coherent samples; independent = product of marginals; lift = joint/independent."""
    hits = np.ones(len(next(iter(result.players.values()))["samples"]["pts"]), dtype=bool)
    indep = 1.0
    for lg in legs:
        h = lg.hit(result.players)
        hits &= h
        indep *= float(h.mean())
    joint = float(hits.mean())
    lift = joint / indep if indep > 1e-9 else float("nan")
    return joint, indep, lift


def describe(result, legs) -> str:
    j, ind, lift = joint_prob(result, legs)
    names = []
    for lg in legs:
        nm = result.players[lg.pid]["name"]
        names.append(f"{nm} {'O' if lg.over else 'U'}{lg.line:g} {lg.stat}")
    fair = (1.0 / j) if j > 1e-9 else float("inf")
    return (f"{'  +  '.join(names)}\n   joint {j:.1%}  | independent {ind:.1%}  | "
            f"correlation lift x{lift:.2f}  | fair odds {fair:.2f}")


# ---------- leak-free joint calibration on historical games ----------
def validate_joint_calibration(n_par=3000, seed=0):
    """Over all cached NYK/SAS games, simulate each (season-anchored), draw random 2-3 leg parlays at the
    sim's OWN median lines (so each leg ~50/50, isolating the JOINT structure), and grade the predicted
    joint prob against the realized joint outcome from the actual boxscore. Compare the sim-joint model to
    the INDEPENDENCE model (product of the same marginals). Reliability + Brier; independence should be
    worse if correlation matters. NOTE: season-anchored (the game is in its own baseline) -> a mild
    in-sample lift; the relative sim-vs-independence comparison is the clean signal."""
    import json, glob, os, sys
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast
    TS = os.path.join(ROOT, "data", "cache", "team_system")
    rng = np.random.default_rng(seed)
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    # realized boxscores per game: pid -> {pts,reb,ast}
    def real_box(gid):
        bf = os.path.join(TS, "box", f"{gid}.json")
        if not os.path.exists(bf):
            return None
        bg = json.load(open(bf))["game"]; out = {}
        for tm in (bg["homeTeam"], bg["awayTeam"]):
            for p in tm.get("players", []):
                s = p.get("statistics", {})
                out[int(p["personId"])] = {
                    "pts": s.get("points", 0) or 0,
                    "reb": (s.get("reboundsOffensive", 0) or 0) + (s.get("reboundsDefensive", 0) or 0),
                    "ast": s.get("assists", 0) or 0}
        return out

    sim_brier, ind_brier, n = [], [], 0
    sim_pred, sim_real = [], []
    for gm in games:
        gid = gm["gid"]; rb = real_box(gid)
        if rb is None:
            continue
        try:
            tris = (gm["home"], gm["away"])
        except Exception:
            continue
        try:
            res = simulate_game_fast(TeamModel.from_cache(tris[0]), TeamModel.from_cache(tris[1]),
                                     n_sims=4000, seed=2026, anchor=True, defense=True)
        except Exception:
            continue
        # candidate legs: rotation players (median pts>=8) with a realized box
        cand = [p for p in res.players if p in rb and res.players[p]["mean"]["pts"] >= 8]
        if len(cand) < 4:
            continue
        for _ in range(max(1, n_par // max(1, len(games)))):
            k = int(rng.integers(2, 4))
            picks = list(rng.choice(cand, size=min(k, len(cand)), replace=False))
            legs = []
            for pid in picks:
                stat = rng.choice(["pts", "reb", "ast"])
                line = float(np.median(res.players[pid]["samples"][stat]))
                over = bool(rng.integers(0, 2))
                legs.append(Leg(int(pid), stat, line, over))
            j, ind, _ = joint_prob(res, legs)
            real_hit = all((rb[lg.pid][lg.stat] > lg.line) == lg.over for lg in legs)
            sim_brier.append((j - real_hit) ** 2); ind_brier.append((ind - real_hit) ** 2)
            sim_pred.append(j); sim_real.append(real_hit); n += 1
    print(f"=== JOINT CALIBRATION (leak-free-ish, season-anchored) ===  parlays graded n={n}")
    print(f"  sim-joint model  : Brier {np.mean(sim_brier):.4f}  | mean pred {np.mean(sim_pred):.3f}  realized {np.mean(sim_real):.3f}")
    print(f"  independence model: Brier {np.mean(ind_brier):.4f}")
    print(f"  -> sim-joint beats independence by {np.mean(ind_brier)-np.mean(sim_brier):+.4f} Brier "
          f"({'JOINT STRUCTURE HELPS' if np.mean(sim_brier) < np.mean(ind_brier) else 'no gain'})")


def fold_g3(res):
    """Fold a compact G3 SGP example table (joint vs independence) into the War Room."""
    import os, re
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    PREVIEW = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
    if not os.path.exists(PREVIEW):
        return
    M = ("<!-- SIGNALS:sgp START -->", "<!-- SIGNALS:sgp END -->")
    pid = lambda sub: next(p for p in res.players if sub.lower() in res.players[p]["name"].lower())
    examples = [
        ("Brunson 24+ pts & 6+ ast (same player, +corr)", [Leg(pid("Brunson"), "pts", 24), Leg(pid("Brunson"), "ast", 6)]),
        ("Brunson 24+ & Towns 17+ pts (teammates, -corr)", [Leg(pid("Brunson"), "pts", 24), Leg(pid("Towns"), "pts", 17)]),
        ("Brunson 24+ & Wemby 24+ pts (cross-team)", [Leg(pid("Brunson"), "pts", 24), Leg(pid("Wemban"), "pts", 24)]),
        ("Wemby 24+ pts & 11+ reb (double-double legs)", [Leg(pid("Wemban"), "pts", 24), Leg(pid("Wemban"), "reb", 11)]),
    ]
    rows = []
    for label, legs in examples:
        j, ind, lift = joint_prob(res, legs)
        rows.append(f"| {label} | {j:.0%} | {ind:.0%} | x{lift:.2f} |")
    blk = (f"{M[0]}\n\n## Same-Game Parlay (joint from the sim)\n"
           f"*Joint hit-prob read directly off the sim's coherent samples vs the naive independence product "
           f"(pricing legs as independent). Lift>1 = positively correlated (independence UNDER-prices); "
           f"lift<1 = negatively correlated, e.g. teammates sharing the scoring pie (independence OVER-prices). "
           f"Structure validated (teammate-rho -0.10 ~ real); ROI NOT claimed (needs real SGP price capture).*\n\n"
           f"| parlay | joint | independent | corr lift |\n|---|---|---|---|\n" + "\n".join(rows) + f"\n\n{M[1]}")
    txt = open(PREVIEW, encoding="utf-8").read()
    txt = re.sub(re.escape(M[0]) + r".*?" + re.escape(M[1]), blk, txt, flags=re.S) if M[0] in txt else txt.rstrip() + "\n\n" + blk + "\n"
    open(PREVIEW, "w", encoding="utf-8").write(txt)
    print(f"  folded ## Same-Game Parlay into {os.path.relpath(PREVIEW, ROOT)}")


if __name__ == "__main__":
    import os, sys
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast
    res = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                             n_sims=40000, seed=2026, anchor=True, defense=True, context={"neutral_site": False})
    pid = lambda sub: next(p for p in res.players if sub.lower() in res.players[p]["name"].lower())
    print("=== G3 SGP examples (SAS @ NYK) — joint vs independence ===")
    print(describe(res, [Leg(pid("Brunson"), "pts", 24), Leg(pid("Brunson"), "ast", 6)]))
    print(describe(res, [Leg(pid("Brunson"), "pts", 24), Leg(pid("Towns"), "pts", 17)]))
    print(describe(res, [Leg(pid("Brunson"), "pts", 24), Leg(pid("Wemban"), "pts", 24)]))
    print(describe(res, [Leg(pid("Wemban"), "pts", 24), Leg(pid("Wemban"), "reb", 11)]))
    fold_g3(res)
    print()
    if "--novalidate" not in sys.argv:
        validate_joint_calibration()
