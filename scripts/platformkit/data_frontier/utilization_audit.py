"""scripts.platformkit.data_frontier.utilization_audit -- cross-sport stat/
artifact utilization census. Generalizes mlb_utilization_audit.py to NBA,
WNBA, tennis, soccer (MLB keeps its own committed tool; this one imports and
reuses its schema-read + git-grep guts rather than duplicating them).

Same cheap-by-construction method per sport: schema census of representative
on-disk corpora (parquet/jsonl, metadata/small-sample reads only) cross-
referenced against a git-grep consumption trace. One addition MLB's tool
didn't need: a consumer_categories bucket per column (live/ingame, pregame,
answers, sim/composition, attribute_registry) via cheap path-substring
matching on the used_in hit list -- lets "unwired" be read at a glance per
consumer surface, not just USED/UNUSED.

CORPORA lists below are a snapshot per sport (2026-07-10 audit) --
representative file per family, sibling season/league files share a schema.
Not a discovery crawler (ponytail: same tradeoff as the MLB tool -- re-run
manually / extend the list as new corpora land).

Output: data/frontend/ops/<sport>_stat_utilization.json (local-only, gitignored).
CLI: python -m scripts.platformkit.data_frontier.utilization_audit --sport nba
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.data_frontier.mlb_utilization_audit import (
    consumers_for,
    schema_for,
)

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "frontend" / "ops"

SPORT_ROOTS: Dict[str, List[str]] = {
    "nba": ["domains/basketball_nba", "scripts/platformkit"],
    "wnba": ["domains/basketball_wnba", "scripts/platformkit"],
    "tennis": ["domains/tennis", "scripts/platformkit"],
    "soccer": ["domains/soccer", "scripts/platformkit"],
}

SPORT_CORPORA: Dict[str, List[Tuple[str, str]]] = {
    "nba": [
        ("data/domains/basketball_nba/asof_features.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_features_ext.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_box_extra.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_box_extra_ext.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_defender_rollup.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_player_adv.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_quarter_shape.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_runvar.parquet", "parquet"),
        ("data/domains/basketball_nba/asof_team_adv.parquet", "parquet"),
        ("data/domains/basketball_nba/atlas_player_position.parquet", "parquet"),
        ("data/domains/basketball_nba/defender_matchup_states.parquet", "parquet"),
        ("data/domains/basketball_nba/espn_boxscores.parquet", "parquet"),
        ("data/domains/basketball_nba/player_boxscores.parquet", "parquet"),
        ("data/domains/basketball_nba/games.parquet", "parquet"),
        ("data/domains/basketball_nba/linescores.parquet", "parquet"),
        ("data/domains/basketball_nba/odds.parquet", "parquet"),
        ("data/domains/basketball_nba/positional_weight_rows.parquet", "parquet"),
        ("data/domains/basketball_nba/postmortem.parquet", "parquet"),
        # 80-artifact intelligence layer: player/team atlas family (44 files,
        # all censused here -- schema-only reads are cheap regardless of count)
        ("data/cache/atlas_player_catch_shoot_vs_pullup.parquet", "parquet"),
        ("data/cache/atlas_player_clutch_scoring.parquet", "parquet"),
        ("data/cache/atlas_player_defensive_profile.parquet", "parquet"),
        ("data/cache/atlas_player_durability_load.parquet", "parquet"),
        ("data/cache/atlas_player_form_streak_dynamics.parquet", "parquet"),
        ("data/cache/atlas_player_foul_drawing.parquet", "parquet"),
        ("data/cache/atlas_player_foul_tendency.parquet", "parquet"),
        ("data/cache/atlas_player_ft_profile.parquet", "parquet"),
        ("data/cache/atlas_player_isolation_profile.parquet", "parquet"),
        ("data/cache/atlas_player_matchup_splits.parquet", "parquet"),
        ("data/cache/atlas_player_monthly_form.parquet", "parquet"),
        ("data/cache/atlas_player_pace_fit.parquet", "parquet"),
        ("data/cache/atlas_player_pick_and_roll_profile.parquet", "parquet"),
        ("data/cache/atlas_player_playmaking_network.parquet", "parquet"),
        ("data/cache/atlas_player_post_up_profile.parquet", "parquet"),
        ("data/cache/atlas_player_quarter_shape_fatigue.parquet", "parquet"),
        ("data/cache/atlas_player_rebounding_profile.parquet", "parquet"),
        ("data/cache/atlas_player_rest_b2b_splits.parquet", "parquet"),
        ("data/cache/atlas_player_score_margin_splits.parquet", "parquet"),
        ("data/cache/atlas_player_scoring_creation.parquet", "parquet"),
        ("data/cache/atlas_player_shot_clock_scoring.parquet", "parquet"),
        ("data/cache/atlas_player_shot_profile.parquet", "parquet"),
        ("data/cache/atlas_player_situational_splits.parquet", "parquet"),
        ("data/cache/atlas_player_spacing_gravity.parquet", "parquet"),
        ("data/cache/atlas_player_transition_scoring.parquet", "parquet"),
        ("data/cache/atlas_player_turnover_profile.parquet", "parquet"),
        ("data/cache/atlas_player_usage_role.parquet", "parquet"),
        ("data/cache/atlas_player_vs_scheme_splits.parquet", "parquet"),
        ("data/cache/atlas_team_bench_production.parquet", "parquet"),
        ("data/cache/atlas_team_clutch_team.parquet", "parquet"),
        ("data/cache/atlas_team_defensive_scheme.parquet", "parquet"),
        ("data/cache/atlas_team_ft_foul_environment.parquet", "parquet"),
        ("data/cache/atlas_team_halfcourt_offense.parquet", "parquet"),
        ("data/cache/atlas_team_lineup_synergy.parquet", "parquet"),
        ("data/cache/atlas_team_matchup_adjustments.parquet", "parquet"),
        ("data/cache/atlas_team_offensive_scheme.parquet", "parquet"),
        ("data/cache/atlas_team_pace_identity.parquet", "parquet"),
        ("data/cache/atlas_team_paint_defense.parquet", "parquet"),
        ("data/cache/atlas_team_rebounding_scheme.parquet", "parquet"),
        ("data/cache/atlas_team_rotation_patterns.parquet", "parquet"),
        ("data/cache/atlas_team_three_pt_defense.parquet", "parquet"),
        ("data/cache/atlas_team_transition_defense.parquet", "parquet"),
        ("data/cache/atlas_team_transition_halfcourt_splits.parquet", "parquet"),
        ("data/cache/atlas_team_turnover_forcing.parquet", "parquet"),
    ],
    "tennis": [
        ("data/domains/tennis/asof_features.parquet", "parquet"),
        ("data/domains/tennis/asof_hold.parquet", "parquet"),
        ("data/domains/tennis/asof_hold_wta.parquet", "parquet"),
        ("data/domains/tennis/asof_return.parquet", "parquet"),
        ("data/domains/tennis/asof_meta.parquet", "parquet"),
        ("data/domains/tennis/asof_setdetail.parquet", "parquet"),
        ("data/domains/tennis/asof_setdetail_wta.parquet", "parquet"),
        ("data/domains/tennis/atlas_h2h.parquet", "parquet"),
        ("data/domains/tennis/atlas_playstyles.parquet", "parquet"),
        ("data/domains/tennis/serve_return_profiles.parquet", "parquet"),
        ("data/domains/tennis/serve_return_matchup_pairing.parquet", "parquet"),
        ("data/domains/tennis/matches.parquet", "parquet"),
        ("data/domains/tennis/wta_matches.parquet", "parquet"),
        ("data/domains/tennis/espn_matches.parquet", "parquet"),
        ("data/domains/tennis/players.parquet", "parquet"),
        ("data/domains/tennis/schedule_density.parquet", "parquet"),
        ("data/domains/tennis/travel_scouting.parquet", "parquet"),
        ("data/domains/tennis/odds.parquet", "parquet"),
        ("data/domains/tennis/postmortem.parquet", "parquet"),
        ("data/cache/ingame/tennis_states__atp.parquet", "parquet"),
        ("data/cache/ingame/tennis_states__wta.parquet", "parquet"),
        ("data/cache/ingame/tennis_gamestate__atp.parquet", "parquet"),
        ("data/cache/ingame/tennis_gamestate__wta.parquet", "parquet"),
        ("data/cache/ingame/tennis_setdetail__atp.parquet", "parquet"),
        ("data/cache/ingame/tennis_setdetail__wta.parquet", "parquet"),
    ],
    "soccer": [
        ("data/domains/soccer/asof_features.parquet", "parquet"),
        ("data/domains/soccer/asof_xg_proxy.parquet", "parquet"),
        ("data/domains/soccer/espn_club_priors.parquet", "parquet"),
        ("data/domains/soccer/espn_matchstats.parquet", "parquet"),
        ("data/domains/soccer/espn_player_stats.parquet", "parquet"),
        ("data/domains/soccer/match_stats.parquet", "parquet"),
        ("data/domains/soccer/matches.parquet", "parquet"),
        ("data/domains/soccer/odds.parquet", "parquet"),
        ("data/domains/soccer/referee_card_foul_profiles.parquet", "parquet"),
        ("data/domains/soccer/style_fingerprints.parquet", "parquet"),
        ("data/domains/soccer/style_matchup_pairing.parquet", "parquet"),
        ("data/domains/soccer/postmortem.parquet", "parquet"),
        ("data/cache/ingame/soccer_states__eng1.parquet", "parquet"),
        ("data/cache/ingame/soccer_shotstates__eng1.parquet", "parquet"),
        ("data/cache/ingame/soccer_shotxgstates__eng1.parquet", "parquet"),
        ("data/cache/ingame/soccer_cardstates__combo_eng_ger.parquet", "parquet"),
    ],
    "wnba": [
        ("data/domains/wnba/espn_scoreboard.parquet", "parquet"),
        ("data/domains/wnba/injuries.parquet", "parquet"),
        ("data/domains/wnba/linescores.parquet", "parquet"),
        ("data/domains/wnba/player_boxscores.parquet", "parquet"),
        ("data/domains/wnba/referee_crew_foul_rate.parquet", "parquet"),
        ("data/domains/wnba/arena_attendance_context.parquet", "parquet"),
        ("data/domains/wnba/elo_refresh_rows.parquet", "parquet"),
        ("data/domains/wnba/elo_refresh_harness_rows.parquet", "parquet"),
        ("data/domains/wnba/cdn_backfill_states.parquet", "parquet"),
        ("data/domains/wnba/schedule_density.parquet", "parquet"),
    ],
}

# hit-path substring -> consumer category (task ask: live/pregame/answers/sim).
# A hit can land in >1 bucket -- e.g. an asof_-named file under composition/.
CONSUMER_CATEGORY_TOKENS: Dict[str, List[str]] = {
    "live_ingame": ["ingame", "live_", "repricer", "match_engine", "winprob", "in_game"],
    "pregame": ["asof_", "pregame", "predictor", "elo", "prior"],
    "answers": ["platformkit/answers", "platformkit\\answers", "profiles/ask", "resolver_registry", "answers/contracts"],
    "sim_composition": ["composition", "concepts", "_sim", "montecarlo", "monte_carlo"],
    "attribute_registry": ["attribute_registry", "build_profiles", "ingredients_"],
}


def categorize_hits(hits: List[str]) -> List[str]:
    """Bucket used_in git-grep hit lines (file:line:content) into consumer
    categories by cheap path/line substring match. Sorted, deduped."""
    cats = set()
    for h in hits:
        low = h.lower()
        for cat, tokens in CONSUMER_CATEGORY_TOKENS.items():
            if any(t in low for t in tokens):
                cats.add(cat)
    return sorted(cats)


def build_inventory(sport: str) -> List[Dict[str, object]]:
    corpora = SPORT_CORPORA[sport]
    roots = SPORT_ROOTS[sport]
    seen: Dict[str, Dict[str, object]] = {}
    for rel_path, kind in corpora:
        for name, dtype, cov in schema_for(rel_path, kind):
            row = seen.setdefault(
                name, {"column": name, "dtype": dtype, "corpora": [], "coverage_pct_sample": cov}
            )
            row["corpora"].append(rel_path)
    rows = []
    for name, row in sorted(seen.items()):
        hits = consumers_for(name, roots=roots)
        row["used_in"] = hits
        row["status"] = "USED" if hits else "UNUSED"
        row["consumer_categories"] = categorize_hits(hits)
        rows.append(row)
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Cross-sport stat/artifact utilization census.")
    ap.add_argument("--sport", required=True, choices=sorted(SPORT_CORPORA))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    rows = build_inventory(a.sport)
    out_fp = Path(a.out) if a.out else _OUT_DIR / f"{a.sport}_stat_utilization.json"
    out_fp.parent.mkdir(parents=True, exist_ok=True)
    out_fp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    used = sum(1 for r in rows if r["status"] == "USED")
    print(json.dumps(
        {"sport": a.sport, "total_columns": len(rows), "used": used, "unused": len(rows) - used, "out": str(out_fp)},
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["SPORT_CORPORA", "SPORT_ROOTS", "build_inventory", "categorize_hits", "main"]
