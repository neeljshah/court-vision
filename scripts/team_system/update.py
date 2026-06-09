"""NYK/SAS Team System — one-command updater.

Runs the full pipeline so the two-team system stays up to date after each Finals game:
  1. fetch_team_pbp     (refresh schedule + pull any new/live PBP+box from cdn.nba.com)
  2. build_team_system  (re-parse all games -> team_game / lineups / player_min / summary)
  3. fold_team_system   (refresh team notes, lineup notes, Finals War Room)
  4. build_player_rates / build_recency_rates / build_player_attributes / build_entity_effects (sim inputs)
  5. build_player_roles (archetype + propensity spine; ratings + sim consume it)
  6. build_attribute_vault (87 deep league-wide attributes)
  7. build_player_ratings  (role-aware 2K cards -> player notes)
  8. build_team_effects    (on/off + lineup impact -> player & team notes)

  python scripts/team_system/update.py            # incremental (skips cached finals)
  python scripts/team_system/update.py --refresh  # re-fetch every game too
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
REFRESH = ["--refresh"] if "--refresh" in sys.argv else []


def run(script, args=None, soft=False):
    print(f"\n=== {script} ===")
    r = subprocess.run([PY, os.path.join(HERE, script), *(args or [])])
    if r.returncode != 0:
        if soft:
            print(f"!! {script} exited {r.returncode}; continuing (soft).")
            return
        print(f"!! {script} exited {r.returncode}; stopping.")
        sys.exit(r.returncode)


def main():
    # Validated sim calibration ON for all builders/predictions (2026-06-07; mean/total-preserving,
    # board green, EDGE_GATE_2026-06-07.md). setdefault so an explicit env override still wins.
    for _f in ("CV_COUNT_NB", "CV_COUNT_STL", "CV_QUARTER_IDENTITY"):
        os.environ.setdefault(_f, "1")
    run("fetch_team_pbp.py", REFRESH)
    run("build_team_system.py")
    run("fold_team_system.py")
    # sim rate inputs + role/attribute/ratings/team-effect intelligence layer
    run("build_player_rates.py")
    run("build_recency_rates.py")     # recency-weighted rates (current regime: playoffs score below season)
    run("build_full_gamelog.py")      # full-stat gamelog + secondary_targets (Poisson rates -> calibrated blk/3pm/ftm props)
    run("build_team_defense.py")      # defensive turnover-forcing + FT/foul-environment traits -> sim multipliers
    run("build_player_attributes.py")
    run("build_entity_effects.py")
    run("build_player_roles.py")
    run("build_attribute_vault.py")
    run("build_player_ratings.py")
    run("build_team_effects.py")
    run("build_pbp_knowledge.py")    # mine every game's play-by-play (real self-create + assist network)
    # league-wide identity + PBP-detail layers (soft: don't block the core if a league source is missing)
    run("build_league_identities.py", soft=True)   # all-30 team_defense_league + league_team_game (matchup composition substrate)
    run("build_pbp_possessions.py", soft=True)     # possession foundry + origin_ppp.json (the in-game lever)
    run("build_pbp_attributes.py", soft=True)      # deep 2K attributes (shot diet x type x creation) -> player notes
    run("build_defender_matchup.py", soft=True)    # who-guards-whom suppression (gated scouting/in-game)
    # FULL per-entity effect spine + deep memory + matchup resolver (need league_team_game + vault above)
    run("build_entity_effects_full.py", soft=True) # rest/defense-tier/pace eFG spine (the "1000s of models")
    run("fold_deep_attributes.py", soft=True)      # full 87-attr vault + effect spine -> every player note
    run("build_matchup_resolution.py", soft=True)  # compose every model -> ## Matchup Resolution in War Room
    run("build_attribute_clash.py", soft=True)     # facet-by-facet A-vs-B clash from the 87-attr vault
    run("build_team_clash.py", soft=True)          # team-vs-team identity clash (pace/TO/FT/rim, head-to-head)
    run("predict_ensemble.py", soft=True)          # fuse all 7 engines -> ONE prediction (signal->model->engine->one)
    print("\nNYK/SAS team system + league identities + PBP-detail intelligence up to date.")
    # AGENTIC SIGNAL LAB: re-validate the registered signals on the fresh data (surgical gates, records verdicts)
    run("signal_orchestrator.py", soft=True)
    # ALWAYS-LEARNING ledger + board gate (snapshot beliefs, ensure learning didn't ship a regression)
    run("learn_ledger.py", soft=True)


if __name__ == "__main__":
    main()
