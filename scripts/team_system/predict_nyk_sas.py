"""GPU prediction driver — the full NYK/SAS game prediction from the possession sim.

Runs the GPU-vectorized possession engine (role-aware usage, assist network, on-court defense,
home/road context, anchored marginals) for the next Finals game and emits the whole coherent slate:
win probability, projected score / spread / total, and per-player props (pts/reb/ast with
q10/q50/q90) — defense-adjusted for the matchup. Folds a `## Sim Prediction` block into the War Room.

  python scripts/team_system/predict_nyk_sas.py --home NYK --away SAS --nsims 20000
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import device, simulate_game_fast  # noqa: E402
from availability import out_ids_for, report as avail_report  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREVIEW = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
START, END = "<!-- SIGNALS:sim-prediction START -->", "<!-- SIGNALS:sim-prediction END -->"
ASC = lambda s: str(s).encode("ascii", "replace").decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=20000); ap.add_argument("--neutral", action="store_true")
    ap.add_argument("--asof", default=None, help="date (YYYY-MM-DD) for the same-day availability feed")
    ap.add_argument("--no-availability", action="store_true", help="ignore the injury feed (legacy behavior)")
    ap.add_argument("--out-home", default="", help="extra OUT player ids for home (comma-sep), e.g. what-if")
    ap.add_argument("--out-away", default="", help="extra OUT player ids for away (comma-sep)")
    ap.add_argument("--no-fold", action="store_true", help="don't write the slate into the War Room (what-if runs)")
    a = ap.parse_args()
    # SAME-DAY AVAILABILITY (freshness lever): pull OUT players from the injury feed + any what-if ids
    oh = set() if a.no_availability else out_ids_for(a.home, a.asof)
    oa = set() if a.no_availability else out_ids_for(a.away, a.asof)
    oh |= {int(x) for x in a.out_home.split(",") if x.strip()}
    oa |= {int(x) for x in a.out_away.split(",") if x.strip()}
    if not a.no_availability:
        print(f"=== same-day availability (feed as-of {a.asof or 'latest'}) ===")
        avail_report(a.home, a.asof); avail_report(a.away, a.asof)
    if a.out_home or a.out_away:
        print(f"  what-if OUT: {a.home}{sorted(oh)} {a.away}{sorted(oa)}")
    home, away = TeamModel.from_cache(a.home, out_ids=oh), TeamModel.from_cache(a.away, out_ids=oa)
    ctx = {"neutral_site": a.neutral}
    res = simulate_game_fast(home, away, n_sims=a.nsims, seed=2026, anchor=True, defense=True, context=ctx)

    hs, as_ = res.home_total, res.away_total
    wp = res.home_win_prob
    proj_h, proj_a = np.median(hs), np.median(as_)
    print(f"=== SIM PREDICTION: {a.away} @ {a.home}  (device {device()}, {a.nsims} sims) ===")
    print(f"win prob: {a.home} {wp:.0%} / {a.away} {1 - wp:.0%}")
    print(f"projected: {a.home} {proj_h:.0f}  {a.away} {proj_a:.0f}  | spread {a.home} {proj_h - proj_a:+.1f}  "
          f"| total {proj_h + proj_a:.0f}")
    print(f"\nplayer props (pts/reb/ast q10-q50-q90; defense-adjusted for the matchup):")

    def q(s, lo=0.1, mid=0.5, hi=0.9):
        return np.quantile(s, lo), np.quantile(s, mid), np.quantile(s, hi)

    rows = sorted(res.players.items(), key=lambda x: -x[1]["mean"]["pts"])
    table = ["| Player | Tm | PTS (q10-q50-q90) | REB | AST |", "|---|---|---|---|---|"]
    for p, d in rows:
        if d["mean"]["pts"] < 6:
            continue
        pl, pm, ph = q(d["samples"]["pts"]); rl, rm, rh = q(d["samples"]["reb"]); al, am, ah = q(d["samples"]["ast"])
        print(f"  {ASC(d['name']):22s} {d['team']}  {pl:4.0f}-{pm:4.0f}-{ph:4.0f}   "
              f"{rm:4.1f} ({rl:.0f}-{rh:.0f})   {am:4.1f} ({al:.0f}-{ah:.0f})")
        table.append(f"| {ASC(d['name'])} | {d['team']} | {pm:.0f} ({pl:.0f}-{ph:.0f}) | "
                     f"{rm:.1f} ({rl:.0f}-{rh:.0f}) | {am:.1f} ({al:.0f}-{ah:.0f}) |")

    blk = (f"{START}\n\n## Sim Prediction ({a.away} @ {a.home})\n*GPU possession Monte Carlo "
           f"({a.nsims} sims): role-aware usage + assist network + on-court defense + home/road, "
           f"anchored marginals. Coherent slate — props, total, spread, win prob all from one sim.*\n\n"
           f"**Win prob:** {a.home} {wp:.0%} / {a.away} {1 - wp:.0%}  ·  "
           f"**Projected:** {a.home} {proj_h:.0f}-{proj_a:.0f} {a.away} "
           f"(spread {a.home} {proj_h - proj_a:+.1f}, total {proj_h + proj_a:.0f})\n\n"
           f"> ⚠️ The **total runs high** (the anchor over-predicts team totals ~+4.5/team on a "
           f"playoff-weighted backtest — two elite defenses in the playoffs score below their "
           f"season-anchored level; calibration §8c). Trust the **win prob and spread** (the bias "
           f"largely cancels in the difference), not the raw total, for O/U.\n\n"
           + "\n".join(table) + f"\n\n{END}\n")
    if os.path.exists(PREVIEW) and not a.no_fold:
        txt = open(PREVIEW, encoding="utf-8").read()
        if START in txt:
            txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
        open(PREVIEW, "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)
        print(f"\nfolded ## Sim Prediction into {os.path.relpath(PREVIEW, ROOT)}")


if __name__ == "__main__":
    main()
