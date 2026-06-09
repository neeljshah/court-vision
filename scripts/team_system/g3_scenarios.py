"""G3 sensitivity analysis — which levers actually move the SAS @ NYK win prob, and by how much.

Each scenario perturbs ONE input to the validated possession sim and reports the win-prob/spread swing
vs base. KEY MODELING NOTE: the engine anchors each player to his per-GAME scoring, so the win prob is
a function of TALENT (anchored player pts) + MATCHUP-DEFENSE (team rim_d/perim_d) + the FT environment.
It is ~invariant to pace / turnover-rate / raw-minutes (those are re-pinned by the per-game anchor) — so a
star's foul trouble is modeled the CORRECT way here: through the matchup-defense his absence weakens + his
lost scoring, NOT through a minutes knob (which the anchor washes out). ascii-only prints.

  python scripts/team_system/g3_scenarios.py
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

N = 30000
SEED = 2026
PREVIEW = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
MARK = ("<!-- SIGNALS:g3-scenarios START -->", "<!-- SIGNALS:g3-scenarios END -->")


def sim(h, a, ctx=None):
    r = simulate_game_fast(h, a, n_sims=N, seed=SEED, anchor=True, defense=True,
                           context=ctx or {"neutral_site": False})
    return r.home_win_prob, float(np.median(r.home_total - r.away_total))


def fresh():
    return TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")


def pid(team, sub):
    return next((p for p in team.rate if sub.lower() in team.rate[p]["player"].lower()), None)


def setpts(team, sub, pts):
    p = pid(team, sub)
    if p is not None:
        team.rate[p]["pts_pg_rec"] = pts


def main():
    h, a = fresh(); base = sim(h, a)
    print(f"=== G3 SENSITIVITY: SAS @ NYK  ({N} sims) ===")
    print(f"BASE: NYK win {base[0]:.0%}  spread NYK {base[1]:+.1f}\n")
    print(f"{'scenario':40s} {'NYKwin':>7s} {'dwin':>6s} {'spread':>7s}")
    out = []

    def run(label, mut):
        h, a = fresh(); mut(h, a)            # mutate teams in place
        r = sim(h, a)
        print(f"{label:40s} {r[0]:>6.0%} {r[0]-base[0]:>+6.0%} {r[1]:>+7.1f}")
        out.append((label, r[0], r[0] - base[0], r[1]))

    def refs_off(h, a):
        h.ft_force = 1.0; a.ft_force = 1.0

    # --- star availability (modeled via matchup-D weakened + lost scoring) ---
    def wemby_foul(h, a):
        a.rim_d -= 12; a.perim_d -= 4; setpts(a, "Wemban", 13)   # ~half game in foul trouble
    run("Wemby foul trouble (~half, SAS rim_d-12)", wemby_foul)

    def wemby_dnp(h, a):
        a.rim_d -= 18; a.perim_d -= 6; setpts(a, "Wemban", 3)
    run("Wemby DNP (extreme)", wemby_dnp)

    def kat_foul(h, a):
        h.rim_d -= 5; setpts(h, "Towns", 9)
    run("KAT foul trouble (~half)", kat_foul)

    # --- star form (anchor target) ---
    run("Brunson bounce-back (+4)", lambda h, a: setpts(h, "Brunson", (h.rate[pid(h, "Brunson")].get("pts_pg_rec") or 26) + 4))
    run("Brunson cold / G1 repeat (-6)", lambda h, a: setpts(h, "Brunson", (h.rate[pid(h, "Brunson")].get("pts_pg_rec") or 26) - 6))
    run("Fox bounce-back (+5 from slump)", lambda h, a: setpts(a, "Fox", (a.rate[pid(a, "Fox")].get("pts_pg_rec") or 16) + 5))

    def sas_hot(h, a):
        for nm in ("Vassell", "Champagnie", "Harper"):
            p = pid(a, nm); setpts(a, nm, (a.rate[p].get("pts_pg_rec") or 12) + 3)
    run("SAS role shooters hot (+3 x3)", sas_hot)

    def sas_cold(h, a):
        for nm in ("Vassell", "Champagnie", "Harper"):
            p = pid(a, nm); setpts(a, nm, (a.rate[p].get("pts_pg_rec") or 12) - 3)
    run("SAS role shooters cold (-3 x3)", sas_cold)

    # --- environment ---
    run("Refs swallow whistle (FT-env off)", refs_off)

    # fold a compact table into the War Room
    if os.path.exists(PREVIEW):
        rows = "\n".join(f"| {l} | {w:.0%} | {d:+.0%} | {s:+.1f} |" for l, w, d, s in out)
        blk = (f"{MARK[0]}\n\n## G3 Sensitivity — what moves the needle\n"
               f"*One lever perturbed per row vs base (**NYK {base[0]:.0%}**, spread {base[1]:+.1f}). The engine is "
               f"talent+matchup-D+FT anchored, so it is most sensitive to star scoring and Wemby's rim protection; "
               f"it is ~invariant to pace/turnover-rate (re-pinned by the per-game anchor — a known property).*\n\n"
               f"| scenario | NYK win | swing | spread |\n|---|---|---|---|\n{rows}\n\n{MARK[1]}")
        txt = open(PREVIEW, encoding="utf-8").read()
        txt = re.sub(re.escape(MARK[0]) + r".*?" + re.escape(MARK[1]), blk, txt, flags=re.S) if MARK[0] in txt else txt.rstrip() + "\n\n" + blk + "\n"
        open(PREVIEW, "w", encoding="utf-8").write(txt)
        print(f"\nfolded ## G3 Sensitivity into {os.path.relpath(PREVIEW, ROOT)}")


if __name__ == "__main__":
    main()
