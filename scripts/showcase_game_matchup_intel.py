"""showcase_game_matchup_intel.py — run + print game matchup intelligence.

Builds game_preview dossiers for a set of contrasting real matchups, prints the
full matchup intelligence (team clash, pace/style, key individual matchups,
scheme + player edges), the ranked top-5 edges, and the deterministic
"how-this-game-plays" narrative for each. Pure showcase — writes nothing.
"""
from __future__ import annotations

import json
import sys

from src.intel import team_report as _tr
from src.intel.game_preview import build_game_preview, resolve_roster

# (home, away, why-this-matchup) — SAS@OKC is the full-data game; rest contrast.
MATCHUPS = [
    ("OKC", "SAS", "full-data game: SGA off-dribble vs SAS perimeter D; Wemby paint/reb vs OKC"),
    ("IND", "ORL", "fast (IND) vs slow (ORL) — pace clash"),
    ("BOS", "MEM", "strong defense/high-3pt (BOS) vs fast offense (MEM)"),
    ("DEN", "MIN", "Jokic paint/playmaking vs MIN elite interior D"),
]


def _num(x, nd=1):
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return x


def print_preview(p):
    m = p["matchup_report"]
    tc = m["team_clash"]
    print("=" * 78)
    print(f"  {p['label']}   (date={p.get('date')})")
    print("=" * 78)

    comp = p["completeness"]
    print(f"COVERAGE: home_team={comp.get('home_team_coverage_pct')}%  "
          f"away_team={comp.get('away_team_coverage_pct')}%  "
          f"n_home_players={comp.get('n_home_players')}  "
          f"n_away_players={comp.get('n_away_players')}  "
          f"rosters_auto={comp.get('rosters_auto_resolved')}")

    # --- pace / style ---
    ps = m["pace_style"]
    print("\n-- PACE / STYLE --")
    print(f"  home {ps['home']['tricode']}: pace={_num(ps['home']['pace_pg'])} "
          f"id={ps['home']['pace_identity']}  |  away {ps['away']['tricode']}: "
          f"pace={_num(ps['away']['pace_pg'])} id={ps['away']['pace_identity']}")
    print(f"  projected_possessions={ps['projected_possessions_estimate']}  "
          f"tempo_battle={ps['tempo_battle']}  controller={ps['tempo_controller']}")
    if ps.get("note"):
        print(f"  note: {ps['note']}")
    if ps.get("transition_note"):
        print(f"  transition: {ps['transition_note']}")

    # --- team clash: off vs def both directions ---
    print("\n-- TEAM CLASH (offense vs defense) --")
    for k in ("home_offense_vs_away_defense", "away_offense_vs_home_defense"):
        d = tc[k]
        print(f"  {d['offense']} OFF (rtg={_num(d['off_rtg'])}, efg={_num(d['off_efg'],3)}) "
              f"vs {d['defense']} DEF (rtg={_num(d['def_rtg'])}, "
              f"scheme={d['def_coverage_scheme']}, rim_allowed={_num(d['def_rim_fg_pct_allowed'],3)}, "
              f"3p_allowed={_num(d['def_opp_3p_pct_allowed'],3)})")
    rb = tc["rebounding_battle"]
    print(f"  REB: {p['home']} oreb={_num(rb.get('home_oreb_pct'),3)}/dreb={_num(rb.get('home_dreb_pct'),3)} "
          f"({rb.get('home_reb_identity')})  |  {p['away']} oreb={_num(rb.get('away_oreb_pct'),3)}/"
          f"dreb={_num(rb.get('away_dreb_pct'),3)} ({rb.get('away_reb_identity')})")

    # --- key individual matchups ---
    print("\n-- KEY INDIVIDUAL MATCHUPS (offense player vs likely defender) --")
    for im in m["key_individual_matchups"][:6]:
        op = im["offense_player"]
        ld = im.get("likely_defender") or {}
        ldn = ld.get("player_name") or "(none)"
        print(f"  [{im['edge_score']:+.2f} {im['edge_side']:>8}] {op['name']} "
              f"({op['archetype']}, {op['team']}) vs {ldn} ({ld.get('archetype')})")
        for f in im["factors"][:2]:
            print(f"        - {f}")

    # --- scheme edges ---
    print("\n-- SCHEME EDGES --")
    if not m["scheme_edges"]:
        print("  (none fired)")
    for e in m["scheme_edges"][:5]:
        print(f"  [{e['magnitude']:.3f}] {e['description']}")

    # --- player edges ---
    print("\n-- PLAYER EDGES (skill vs opposing-team weakness) --")
    if not m["player_edges"]:
        print("  (none fired)")
    for e in m["player_edges"][:6]:
        print(f"  [{e['magnitude']:.3f}] {e['description']}")

    # --- TOP-5 EDGES (merged ranked) ---
    print("\n-- TOP-5 EDGES (merged, magnitude-ranked) --")
    for e in p["top_edges"]:
        print(f"  [{e['rank']}] ({e['edge_class']}) {e.get('description')}  "
              f"(mag={_num(e.get('magnitude'),3)})")

    # --- keys to the game ---
    print("\n-- KEYS TO THE GAME --")
    for t, ks in p["keys_to_the_game"].items():
        print(f"  {t}:")
        for k in ks:
            print(f"    - {k}")

    # --- narrative ---
    print("\n-- HOW THIS GAME PROJECTS TO PLAY --")
    print("  " + m["game_projection"])

    # --- predictive candidates (unvalidated) ---
    print("\n-- UNVALIDATED PREDICTIVE CANDIDATES (flagged for honest gate) --")
    for c in p["predictive_candidates"][:6]:
        print(f"  * [{c['status']}] {c['candidate_type']} {c.get('direction')}"
              f"{(' ' + str(c.get('stat'))) if c.get('stat') else ''}: {c.get('rationale')}")
    print()


def main():
    atlases = _tr.load_team_atlases()
    team_ctx = _tr.build_league_context(atlases)
    previews = []
    for home, away, why in MATCHUPS:
        print(f"\n### building {away} @ {home} — {why}", file=sys.stderr)
        try:
            p = build_game_preview(home, away, team_ctx=team_ctx, atlases=atlases)
            previews.append((why, p))
        except Exception as ex:
            import traceback
            print(f"FAILED {away}@{home}: {ex}", file=sys.stderr)
            traceback.print_exc()
    for why, p in previews:
        print_preview(p)
    return previews


if __name__ == "__main__":
    main()
