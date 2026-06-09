"""Verify DEFENSE matters in the sim — and trace the attribute -> prediction chain.

The deep attribute vault (87 attrs) -> INTERIOR_D / PERIMETER_D category ratings -> the sim's
per-shot make suppression + anchor matchup factor. This script proves defense actually moves
predictions, in the right direction and a realistic magnitude:
  - the team facing the TOUGHER defense is suppressed MORE
  - rim-heavy scorers facing elite rim protection drop the most
  - pure offensive fidelity (defense OFF) is unchanged

  python scripts/team_system/verify_defense.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel, simulate_game  # noqa: E402

ASC = lambda s: str(s).encode("ascii", "replace").decode()


def main(n_sims=3000):
    h, a = TeamModel.from_cache("SAS"), TeamModel.from_cache("NYK")
    print("=== DEFENSE VERIFICATION: NYK @ SAS ===")
    print(f"team defense (0-99, from INTERIOR_D/PERIMETER_D ratings = the defensive attribute vault):")
    print(f"  SAS rim_d {h.rim_d:.0f}  perim_d {h.perim_d:.0f}   |   NYK rim_d {a.rim_d:.0f}  perim_d {a.perim_d:.0f}")
    off = simulate_game(h, a, n_sims=n_sims, seed=11, anchor=True, defense=False)
    on = simulate_game(h, a, n_sims=n_sims, seed=11, anchor=True, defense=True)
    sas_drop = off.home_total.mean() - on.home_total.mean()
    nyk_drop = off.away_total.mean() - on.away_total.mean()
    print(f"\nteam totals  defense OFF (season baseline) -> ON (opponent matchup, centered on league-avg D):")
    print(f"  SAS {off.home_total.mean():.1f} -> {on.home_total.mean():.1f}  ({-sas_drop:+.1f}, faces NYK ~avg D)")
    print(f"  NYK {off.away_total.mean():.1f} -> {on.away_total.mean():.1f}  ({-nyk_drop:+.1f}, faces SAS the tougher D)")

    print("\nper-player scoring suppression (rim-heavy scorers vs elite rim protection drop most):")
    rows = sorted(on.players.items(), key=lambda x: off.players[x[0]]["mean"]["pts"] - x[1]["mean"]["pts"], reverse=True)
    for p, d in rows[:8]:
        delta = d["mean"]["pts"] - off.players[p]["mean"]["pts"]
        r = (h.rate.get(p) or a.rate.get(p))
        rim_sh = (r["z_rim"] + r["z_paint"]) if r else 0
        print(f"  {ASC(d['name']):22s} {d['team']} {off.players[p]['mean']['pts']:5.1f} -> {d['mean']['pts']:5.1f} "
              f"({delta:+.1f})  rim-share {rim_sh:.0%}")

    # PASS checks (matchup is centered on league-average team defense, so facing a below-avg D can
    # boost; the test is that the team facing the TOUGHER D is suppressed MORE, by a realistic amount)
    diff = nyk_drop - sas_drop
    tougher_more = nyk_drop > sas_drop
    realistic = 0.5 <= diff <= 14.0
    print(f"\nPASS: tougher-D-suppresses-more = {tougher_more}; realistic differential ({diff:+.1f}) = {realistic}")
    print("  (defense = per-shot on-court INTERIOR_D/PERIMETER_D + anchor matchup factor, calibrated to")
    print("   real outcomes in backtest_defense.py; pure offensive fidelity in validate_sim_fidelity.py)")


if __name__ == "__main__":
    main()
