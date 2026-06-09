"""Register 42 new DERIVED signals — scouting/joint layer expansion, 2026-06-08.

HONESTY POLICY (enforced at design time):
  - All signals tagged honesty_class=SCOUTING or JOINT
  - consumer = scouting | joint | ingame  (NOT point-model — these do not move the marginal)
  - bet_wireable = False for all
  - No OOS validation claimed; layer contribution stated clearly
  - Domain: 6 new facet families:
      [interaction]    attribute interaction terms (size×skill, role×form, etc.)
      [facet_delta]    recency-vs-season deltas per stat
      [role_split]     role-conditioned rate splits (by archetype)
      [matchup_facet]  per-matchup facet deltas
      [lineup_pair]    pair-level joint signals
      [scheme_load]    team-scheme-specific player load signals

Run: python scripts/register_derived_signals_2026_06_08.py
Idempotent: re-running registers 0 new rows (all IDs already present).
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
from registry.store import Registry  # noqa: E402


def _sid(name: str) -> str:
    """Deterministic signal_id from human name (sha1 prefix = 24 hex chars)."""
    h = hashlib.sha1(name.encode()).hexdigest()[:23]
    return f"sig_{h}"


NOW = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
BUILDER = "register_derived_signals_2026_06_08.py"


def _row(
    name: str,
    grain: str,
    entity_scope: str,
    domain_tags: list,
    source: str,
    formula_ast: str,
    consumer: str,
    ev_tier: str,
    note_extra: str = "",
    causal_sign: str = "none",
    quantity: str = "",
    legacy_name: str = "",
    artifact_path: str = "",
) -> dict:
    note = f"ev_tier={ev_tier};consumer={consumer}"
    if note_extra:
        note += f";{note_extra}"
    return dict(
        signal_id=_sid(name),
        grain=grain,
        entity_scope=entity_scope,
        domain_tags=domain_tags,
        source=source,
        formula_ast=formula_ast,
        transform_chain="z_score",
        asof_fn="season_end",
        causal_sign=causal_sign,
        input_hash="",
        honesty_class="SCOUTING",
        bet_wireable=False,
        status="defined",
        gateA_rel=None,
        gateA_fdr_q=None,
        gateX_verdict=None,
        judge_sign_ok=None,
        judge_engine_ortho=None,
        family_key=domain_tags[0] if domain_tags else "",
        n=None,
        coverage_pct=None,
        created_utc=NOW,
        builder=BUILDER,
        artifact_path=artifact_path,
        legacy_name=legacy_name,
        note=note,
        declared_sign=None,
        measured_sign=None,
        quantity=quantity,
    )


SIGNALS: list[dict] = []

# ============================================================
# 1. ATTRIBUTE INTERACTION SIGNALS [interaction]
#    Source: atlas_player_usage_role × atlas_player_defensive_profile
#            atlas_player_spacing_gravity × player_roles
#    Consumer: scouting | joint
#    Contribution: enriches descriptive layer; LLM context for role-conditioned narratives
# ============================================================

SIGNALS += [
    _row(
        name="interaction.size_x_rim_protect",
        grain="s",
        entity_scope="player",
        domain_tags=["interaction"],
        source="player_attributes.height_z_lg × atlas_player_defensive_profile.rim_protection",
        formula_ast="height_z_lg * rim_protection",
        consumer="scouting",
        ev_tier="C",
        note_extra="big+rim-protect archetype interaction; 0 for perimeter players",
        causal_sign="positive",
        quantity="interaction_score",
        legacy_name="player.interaction.size_x_rim_protect",
    ),
    _row(
        name="interaction.usage_x_efficiency",
        grain="s",
        entity_scope="player",
        domain_tags=["interaction"],
        source="player_roles.usage_pct × scoring_profile.trk_drive_pts_per_drive",
        formula_ast="usage_pct * (true_shooting_approx)",
        consumer="scouting",
        ev_tier="C",
        note_extra="unicorn signal: high-usage AND efficient; separates creator from ball-stopper",
        causal_sign="positive",
        quantity="usage_efficiency_product",
        legacy_name="player.interaction.usage_x_efficiency",
    ),
    _row(
        name="interaction.spacing_x_playmaking",
        grain="s",
        entity_scope="player",
        domain_tags=["interaction"],
        source="atlas_player_spacing_gravity.gravity_score × atlas_player_playmaking_network.ast_pts_created",
        formula_ast="gravity_score * ast_pts_created",
        consumer="joint",
        ev_tier="B",
        note_extra="floor-general + gravity = drive-and-kick multiplier; feeds correlation_joint",
        causal_sign="positive",
        quantity="gravity_x_creation",
        legacy_name="player.interaction.spacing_x_playmaking",
    ),
    _row(
        name="interaction.height_x_shot_creation",
        grain="s",
        entity_scope="player",
        domain_tags=["interaction"],
        source="player_attributes.height_in × atlas_player_scoring_creation.unassisted_share_2pm",
        formula_ast="height_in * unassisted_share_2pm",
        consumer="scouting",
        ev_tier="C",
        note_extra="tall self-creators (Luka/KD-archetype) vs tall passers; scouting differentiation",
        causal_sign="positive",
        quantity="tall_creator_index",
        legacy_name="player.interaction.height_x_shot_creation",
    ),
    _row(
        name="interaction.role_x_q4_usage",
        grain="s|q",
        entity_scope="player",
        domain_tags=["interaction"],
        source="player_roles.archetype × situational_splits.q4_pts",
        formula_ast="archetype_encoded * q4_pts_share",
        consumer="scouting",
        ev_tier="B",
        note_extra="Q4 usage by archetype tier; clutch share concentrated in LEAD_GUARD/FLOOR_GENERAL",
        causal_sign="positive",
        quantity="role_q4_usage_score",
        legacy_name="player.interaction.role_x_q4_usage",
    ),
    _row(
        name="interaction.rim_pressure_x_foul_draw",
        grain="s",
        entity_scope="player",
        domain_tags=["interaction"],
        source="player_roles.rim_pressure × atlas_player_foul_drawing.foul_drawing",
        formula_ast="rim_pressure * foul_drawing",
        consumer="joint",
        ev_tier="B",
        note_extra="rim-attacker AND draws fouls = FT line mover; joint FTM/PTS interaction",
        causal_sign="positive",
        quantity="rim_foul_index",
        legacy_name="player.interaction.rim_pressure_x_foul_draw",
    ),
    _row(
        name="interaction.perimeter_d_x_steal_rate",
        grain="s",
        entity_scope="player",
        domain_tags=["interaction"],
        source="player_roles.perimeter_d × player_rates.stl_per_min",
        formula_ast="perimeter_d * stl_per_min",
        consumer="scouting",
        ev_tier="C",
        note_extra="elite perimeter D + steal tendency = two-way wing archetype signal",
        causal_sign="positive",
        quantity="twoway_wing_index",
        legacy_name="player.interaction.perimeter_d_x_steal_rate",
    ),
    _row(
        name="interaction.playmaking_x_tov_rate",
        grain="s",
        entity_scope="player",
        domain_tags=["interaction"],
        source="atlas_player_playmaking_network.ast_to_tov × player_rates.tov_share",
        formula_ast="ast_to_tov * (1 - tov_share_normalized)",
        consumer="scouting",
        ev_tier="C",
        note_extra="pure-facilitator vs risky-playmaker axis; LLM narrative context",
        causal_sign="positive",
        quantity="clean_creator_score",
        legacy_name="player.interaction.playmaking_x_tov_rate",
    ),
]

# ============================================================
# 2. RECENCY-VS-SEASON DELTA SIGNALS [facet_delta]
#    Source: form_trajectory (l5/l10 vs season mean)
#    Consumer: ingame | scouting
#    Contribution: captures hot/cold streaks that the season-level model misses;
#                  descriptive context for LLM scouting reads; NOT a proven marginal lift
# ============================================================

for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
    SIGNALS.append(
        _row(
            name=f"facet_delta.l5_vs_season_{stat}",
            grain="l5|s",
            entity_scope="player",
            domain_tags=["facet_delta"],
            source=f"form_trajectory.l5_{stat} - form_trajectory.ewma_{stat}",
            formula_ast=f"l5_{stat} - ewma_{stat}",
            consumer="ingame",
            ev_tier="B",
            note_extra=f"hot/cold read: l5 vs EWMA season baseline for {stat}; sign=+hot/-cold",
            causal_sign="positive",
            quantity=f"{stat}_recency_delta",
            legacy_name=f"player.facet_delta.l5_vs_season_{stat}",
        )
    )
    SIGNALS.append(
        _row(
            name=f"facet_delta.slope_vs_std_{stat}",
            grain="s",
            entity_scope="player",
            domain_tags=["facet_delta"],
            source=f"form_trajectory.slope_{stat} / (form_trajectory.std_{stat} + 0.01)",
            formula_ast=f"slope_{stat} / (std_{stat} + eps)",
            consumer="scouting",
            ev_tier="C",
            note_extra=f"normalized trend strength for {stat}: rising consistently vs volatile riser",
            causal_sign="positive",
            quantity=f"{stat}_trend_z",
            legacy_name=f"player.facet_delta.slope_vs_std_{stat}",
        )
    )

# ============================================================
# 3. ROLE-CONDITIONED RATE SPLITS [role_split]
#    Source: player_roles.archetype × player_rates (per-min rates)
#    Consumer: scouting | joint
#    Contribution: archetype-specific baselines for joint shape / parlay pool conditioning
# ============================================================

SIGNALS += [
    _row(
        name="role_split.lead_guard_ast_rate_delta",
        grain="s",
        entity_scope="player",
        domain_tags=["role_split"],
        source="player_rates.ast_per_min WHERE archetype=LEAD_GUARD|FLOOR_GENERAL",
        formula_ast="ast_per_min - archetype_mean_ast_per_min",
        consumer="joint",
        ev_tier="B",
        note_extra="LEAD_GUARD above/below archetype AST rate; guides AST correlation pool",
        causal_sign="positive",
        quantity="lead_guard_ast_delta",
        legacy_name="player.role_split.lead_guard_ast_rate_delta",
    ),
    _row(
        name="role_split.three_d_wing_reb_rate_delta",
        grain="s",
        entity_scope="player",
        domain_tags=["role_split"],
        source="player_rates.dreb_per_min WHERE archetype=THREE_D_WING",
        formula_ast="dreb_per_min - archetype_mean_dreb_per_min",
        consumer="joint",
        ev_tier="B",
        note_extra="wing above/below archetype DREB rate; outlier 3D wings can be hidden REB value",
        causal_sign="positive",
        quantity="three_d_wing_reb_delta",
        legacy_name="player.role_split.three_d_wing_reb_rate_delta",
    ),
    _row(
        name="role_split.primary_big_blk_rate_delta",
        grain="s",
        entity_scope="player",
        domain_tags=["role_split"],
        source="player_rates.blk_per_min WHERE archetype=PRIMARY_BIG|ANCHOR_BIG",
        formula_ast="blk_per_min - archetype_mean_blk_per_min",
        consumer="scouting",
        ev_tier="C",
        note_extra="big above/below archetype BLK rate; rim-protect vs mismatch-prone bigs",
        causal_sign="positive",
        quantity="big_blk_delta",
        legacy_name="player.role_split.primary_big_blk_rate_delta",
    ),
    _row(
        name="role_split.bench_scorer_vol_pts_delta",
        grain="s",
        entity_scope="player",
        domain_tags=["role_split"],
        source="player_rates.use_per_min WHERE archetype=BENCH_SCORER",
        formula_ast="use_per_min - archetype_mean_use_per_min",
        consumer="scouting",
        ev_tier="C",
        note_extra="bench scorer usage spike indicator; +delta = getting starter-level shots",
        causal_sign="positive",
        quantity="bench_scorer_usage_delta",
        legacy_name="player.role_split.bench_scorer_vol_pts_delta",
    ),
    _row(
        name="role_split.scoring_guard_fg3_rate_delta",
        grain="s",
        entity_scope="player",
        domain_tags=["role_split"],
        source="player_rates.fg3_rate WHERE archetype=SCORING_GUARD|OFF_GUARD",
        formula_ast="fg3_rate - archetype_mean_fg3_rate",
        consumer="scouting",
        ev_tier="C",
        note_extra="scoring guard 3PA rate vs archetype mean; high = pull-up heavy vs spot-up heavy",
        causal_sign="positive",
        quantity="guard_3pa_rate_delta",
        legacy_name="player.role_split.scoring_guard_fg3_rate_delta",
    ),
    _row(
        name="role_split.connector_wing_ast_tov_delta",
        grain="s",
        entity_scope="player",
        domain_tags=["role_split"],
        source="player_rates.ast_per_min WHERE archetype=CONNECTOR_WING",
        formula_ast="(ast_per_min / (tov_share + eps)) - archetype_mean_ato",
        consumer="scouting",
        ev_tier="C",
        note_extra="connector wing A:T ratio vs peers; above-arch = upgrade playmaker",
        causal_sign="positive",
        quantity="connector_wing_ato_delta",
        legacy_name="player.role_split.connector_wing_ast_tov_delta",
    ),
]

# ============================================================
# 4. PER-MATCHUP FACET DELTAS [matchup_facet]
#    Source: defense_matchup.stops_index × player role/scoring signals
#    Consumer: scouting | joint
#    Contribution: matchup-specific context for LLM game reads and joint pricing guidance;
#                  NOT a proven pregame point-model feature (all such tests rejected OOS)
# ============================================================

SIGNALS += [
    _row(
        name="matchup_facet.pts_vs_elite_defenders",
        grain="s",
        entity_scope="player",
        domain_tags=["matchup_facet"],
        source="coverage_faced_allseasons WHERE def_stops_index < 0.90",
        formula_ast="ppp_vs_elite - ppp_vs_avg",
        consumer="scouting",
        ev_tier="C",
        note_extra="PPP delta vs top-10pct defenders vs average; scouting guard durability",
        causal_sign="positive",
        quantity="pts_elite_def_delta",
        legacy_name="player.matchup_facet.pts_vs_elite_defenders",
    ),
    _row(
        name="matchup_facet.pts_vs_big_switchers",
        grain="s",
        entity_scope="player",
        domain_tags=["matchup_facet"],
        source="atlas_team_defensive_scheme.switch_rate × scoring_profile.syn_iso_ppp",
        formula_ast="iso_ppp_vs_switch_heavy - iso_ppp_vs_drop_heavy",
        consumer="scouting",
        ev_tier="C",
        note_extra="ISO scorer vs switch-heavy vs drop coverage; LLM scheme-sensitivity note",
        causal_sign="positive",
        quantity="iso_vs_switch_delta",
        legacy_name="player.matchup_facet.pts_vs_big_switchers",
    ),
    _row(
        name="matchup_facet.reb_vs_team_oreb_strength",
        grain="s",
        entity_scope="player",
        domain_tags=["matchup_facet"],
        source="rebounding.oreb_pct_s × team_defense_league.oreb_strength",
        formula_ast="player_oreb_pct - opp_oreb_strength_normalized",
        consumer="scouting",
        ev_tier="C",
        note_extra="OREB rate vs opponent's rebound-suppression tendency; context for REB props",
        causal_sign="positive",
        quantity="oreb_matchup_delta",
        legacy_name="player.matchup_facet.reb_vs_team_oreb_strength",
    ),
    _row(
        name="matchup_facet.ast_vs_tov_forcing_defense",
        grain="s",
        entity_scope="player",
        domain_tags=["matchup_facet"],
        source="playmaking.ast_l10 × team_defense_league.tov_force",
        formula_ast="ast_pct - opp_tov_force_normalized",
        consumer="scouting",
        ev_tier="C",
        note_extra="playmaker AST rate vs turnover-forcing defense; LLM pressure narrative",
        causal_sign="positive",
        quantity="ast_tov_force_delta",
        legacy_name="player.matchup_facet.ast_vs_tov_forcing_defense",
    ),
    _row(
        name="matchup_facet.fg3m_vs_perimeter_closeout",
        grain="s",
        entity_scope="player",
        domain_tags=["matchup_facet"],
        source="scoring_profile.trk_catch_shoot_fg3_pct × team_defense_league.coverage_tendency",
        formula_ast="cs_fg3_pct - opp_perimeter_closeout_pressure",
        consumer="scouting",
        ev_tier="C",
        note_extra="catch-shoot 3P% vs opp perimeter scheme pressure; scouting 3P context",
        causal_sign="positive",
        quantity="cs3_vs_closeout_delta",
        legacy_name="player.matchup_facet.fg3m_vs_perimeter_closeout",
    ),
    _row(
        name="matchup_facet.ft_vs_foul_suppression",
        grain="s",
        entity_scope="player",
        domain_tags=["matchup_facet"],
        source="atlas_player_foul_drawing × team_defense_league.ft_force",
        formula_ast="fta_pg - opp_ft_force_normalized * foul_draw_rate",
        consumer="scouting",
        ev_tier="C",
        note_extra="FT generation vs opponent FT-suppression (Wemby-type defense); LLM note",
        causal_sign="positive",
        quantity="fta_vs_ft_suppress_delta",
        legacy_name="player.matchup_facet.ft_vs_foul_suppression",
    ),
]

# ============================================================
# 5. LINEUP PAIR SYNERGY SIGNALS [lineup_pair_joint]
#    Source: lineup_pair_trio + player_roles + correlation_joint
#    Consumer: joint | scouting
#    Contribution: enriches the joint/SGP layer with observed pair tendencies;
#                  feeds corr-model archetype pool for drive-and-kick pairs
# ============================================================

SIGNALS += [
    _row(
        name="lineup_pair_joint.creator_shooter_drive_kick_rate",
        grain="s",
        entity_scope="lineup",
        domain_tags=["lineup_pair_joint"],
        source="playmaking.drive_and_kick_pg WHERE pair includes shooter archetype",
        formula_ast="drive_and_kick_pg * paired_shooter_cs_fg3_pct",
        consumer="joint",
        ev_tier="B",
        note_extra="creator-shooter pair: drives that end in partner catch-shoot 3PA; joint FG3M context",
        causal_sign="positive",
        quantity="drive_kick_3pa_pair",
        legacy_name="lineup.pair_joint.creator_shooter_drive_kick_rate",
    ),
    _row(
        name="lineup_pair_joint.pnr_handler_roll_completion",
        grain="s",
        entity_scope="lineup",
        domain_tags=["lineup_pair_joint"],
        source="lineup_pair_trio.pnr_handler_share × atlas_player_rebounding_profile.oreb_rate_mean",
        formula_ast="pnr_handler_share * roll_man_rim_fg_pct",
        consumer="joint",
        ev_tier="B",
        note_extra="PnR handler+roll pair completion rate; roll man FG2M conditional on handler drive",
        causal_sign="positive",
        quantity="pnr_completion_rate",
        legacy_name="lineup.pair_joint.pnr_handler_roll_completion",
    ),
    _row(
        name="lineup_pair_joint.two_man_net_vs_archetype_expected",
        grain="s",
        entity_scope="lineup",
        domain_tags=["lineup_pair_joint"],
        source="lineup_pair_trio.net - archetype_pooled_expected_net",
        formula_ast="pair_net_rtg - (arch1_mean_impact + arch2_mean_impact)",
        consumer="joint",
        ev_tier="B",
        note_extra="pair net above archetype-expected; catches genuine chemistry effects vs selection bias",
        causal_sign="positive",
        quantity="pair_net_residual",
        legacy_name="lineup.pair_joint.two_man_net_vs_archetype_expected",
    ),
    _row(
        name="lineup_pair_joint.defensive_pair_stops_index",
        grain="s",
        entity_scope="lineup",
        domain_tags=["lineup_pair_joint"],
        source="defense_matchup.stops_index WHERE two defenders share same lineup",
        formula_ast="min(stops_idx_p1, stops_idx_p2) * coverage_complementarity",
        consumer="scouting",
        ev_tier="C",
        note_extra="two-defender wall: both elite AND complementary (perimeter+rim or size+speed)",
        causal_sign="negative",
        quantity="def_pair_wall_score",
        legacy_name="lineup.pair_joint.defensive_pair_stops_index",
    ),
    _row(
        name="lineup_pair_joint.spacing_pair_gravity_sum",
        grain="s",
        entity_scope="lineup",
        domain_tags=["lineup_pair_joint"],
        source="atlas_player_spacing_gravity.gravity_score × 2 players in pair",
        formula_ast="gravity_p1 + gravity_p2",
        consumer="scouting",
        ev_tier="C",
        note_extra="dual-gravity pair: two shooters who force defense to respect space simultaneously",
        causal_sign="positive",
        quantity="pair_spacing_gravity_sum",
        legacy_name="lineup.pair_joint.spacing_pair_gravity_sum",
    ),
]

# ============================================================
# 6. TEAM-SCHEME-SPECIFIC PLAYER LOAD SIGNALS [scheme_load]
#    Source: atlas_team_offensive_scheme × player_rates
#    Consumer: scouting | joint
#    Contribution: contextualizes player load within team-system read;
#                  enriches LLM scheme-sensitivity layer
# ============================================================

SIGNALS += [
    _row(
        name="scheme_load.player_usage_in_pnr_heavy_offense",
        grain="s",
        entity_scope="player",
        domain_tags=["scheme_load"],
        source="atlas_team_offensive_scheme.pnr × player_rates.use_per_min",
        formula_ast="use_per_min * team_pnr_freq_normalized",
        consumer="scouting",
        ev_tier="C",
        note_extra="handler usage boost in PnR-heavy offense; non-handler usage dilution",
        causal_sign="positive",
        quantity="pnr_system_usage",
        legacy_name="player.scheme_load.usage_in_pnr_heavy",
    ),
    _row(
        name="scheme_load.player_3pa_in_drive_kick_system",
        grain="s",
        entity_scope="player",
        domain_tags=["scheme_load"],
        source="atlas_team_offensive_scheme.drive_rate × scoring_profile.trk_catch_shoot_fg3a",
        formula_ast="cs_fg3a_pg * team_drive_rate_normalized",
        consumer="scouting",
        ev_tier="C",
        note_extra="catch-shoot 3PA amplified in high-drive systems (NYK/SAS style); scouting only",
        causal_sign="positive",
        quantity="drive_system_3pa",
        legacy_name="player.scheme_load.3pa_in_drive_kick",
    ),
    _row(
        name="scheme_load.player_transition_load_in_pace_system",
        grain="s",
        entity_scope="player",
        domain_tags=["scheme_load"],
        source="atlas_team_pace_identity.transition_rate × atlas_player_transition_scoring.pbp_volume",
        formula_ast="player_transition_poss_pg * team_pace_z",
        consumer="scouting",
        ev_tier="C",
        note_extra="player transition volume conditioned on team pace identity; fast-break dependency",
        causal_sign="positive",
        quantity="transition_system_load",
        legacy_name="player.scheme_load.transition_in_pace_system",
    ),
    _row(
        name="scheme_load.iso_load_in_halfcourt_offense",
        grain="s",
        entity_scope="player",
        domain_tags=["scheme_load"],
        source="atlas_team_offensive_scheme.iso_rate × atlas_player_isolation_profile.frequency",
        formula_ast="player_iso_freq * team_iso_rate_z",
        consumer="scouting",
        ev_tier="C",
        note_extra="ISO scorer load in ball-stopping offense; LLM scheme-sensitivity note context",
        causal_sign="positive",
        quantity="iso_system_load",
        legacy_name="player.scheme_load.iso_in_halfcourt",
    ),
    _row(
        name="scheme_load.post_load_vs_three_heavy_defense",
        grain="s",
        entity_scope="player",
        domain_tags=["scheme_load"],
        source="atlas_player_post_up_profile.post_up_ppp × atlas_team_three_pt_defense.opp_fg3_pct_allowed",
        formula_ast="post_ppp * opp_3pt_emphasis_z",
        consumer="scouting",
        ev_tier="C",
        note_extra="post player vs 3-pt-emphasis defense that cheats off; post load opportunity signal",
        causal_sign="positive",
        quantity="post_vs_3heavy_def",
        legacy_name="player.scheme_load.post_vs_3heavy_defense",
    ),
    _row(
        name="scheme_load.ft_environment_player_draw_rate",
        grain="s",
        entity_scope="player",
        domain_tags=["scheme_load"],
        source="atlas_team_ft_foul_environment.ft_drawn × atlas_player_foul_drawing",
        formula_ast="player_fta_pg_normalized * team_ft_drawn_rate",
        consumer="scouting",
        ev_tier="C",
        note_extra="player FT draw in team FT-friendly vs FT-suppressing environment; lines context",
        causal_sign="positive",
        quantity="ft_env_player_rate",
        legacy_name="player.scheme_load.ft_env_player_draw",
    ),
]

# ============================================================
# 7. CROSS-SEASON DRIFT / CONSISTENCY [drift]
#    Source: form_trajectory slopes × player_attributes (age/exp)
#    Consumer: scouting
#    Contribution: aging-curve / consistency narrative for scouting reads
# ============================================================

SIGNALS += [
    _row(
        name="drift.pts_slope_vs_age_expected",
        grain="s",
        entity_scope="player",
        domain_tags=["drift"],
        source="form_trajectory.slope_pts vs player_attributes.age aging_curve_residual",
        formula_ast="slope_pts - aging_curve_expected_slope(age, pos)",
        consumer="scouting",
        ev_tier="C",
        note_extra="rising faster or declining slower than age-position curve; breakout/fade flag",
        causal_sign="positive",
        quantity="pts_age_curve_residual",
        legacy_name="player.drift.pts_slope_vs_age_expected",
    ),
    _row(
        name="drift.minutes_consistency_cross_season",
        grain="s",
        entity_scope="player",
        domain_tags=["drift"],
        source="player_rates.mpg vs previous season player_rates.mpg",
        formula_ast="mpg_current - mpg_prior",
        consumer="scouting",
        ev_tier="C",
        note_extra="YoY minutes stability; negative = role reduction; LLM context for prop sizing",
        causal_sign="positive",
        quantity="mpg_yoy_delta",
        legacy_name="player.drift.minutes_consistency_cross_season",
    ),
    _row(
        name="drift.usage_trajectory_last3",
        grain="s",
        entity_scope="player",
        domain_tags=["drift"],
        source="form_trajectory.slope_pts as proxy for usage trajectory",
        formula_ast="slope_pts / season_mean_pts",
        consumer="scouting",
        ev_tier="C",
        note_extra="normalized usage trajectory over L3 seasons; climbing vs fading arc",
        causal_sign="positive",
        quantity="usage_traj_z",
        legacy_name="player.drift.usage_trajectory_last3",
    ),
]


def main() -> None:
    r = Registry("signal_registry")
    before = len(r)
    result = r.register_many(SIGNALS)
    after = len(r)
    added = after - before
    print(f"register_derived_signals_2026_06_08: registered {result['registered']} new, "
          f"skipped {result['skipped']} (already present). "
          f"Registry: {before} -> {after} (+{added}).")
    # Print summary by domain_tag
    df = r.all()
    # Summarize by family_key
    fk_counts = {}
    for row in SIGNALS:
        fk = row.get("family_key", "?")
        fk_counts[fk] = fk_counts.get(fk, 0) + 1
    print("\nNew signals by domain:")
    for fk, cnt in sorted(fk_counts.items()):
        print(f"  [{fk}] {cnt}")
    print(f"\nTotal new signals defined: {len(SIGNALS)}")
    print(f"Total registry size after: {after}")


if __name__ == "__main__":
    main()
