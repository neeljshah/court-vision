"""Static registry constants for claims_dossier_gen.py -- split out purely to
keep claims_dossier_gen.py under the 300 LOC/file rail (data, not logic).

CLAIM_ID_TO_FILE / EXTRA_VALIDATION_PATHS are a STATIC registry, not a glob
(see LANE spec) -- adding a new claim source means adding its validation path
+ claim_id prefix(es) here explicitly. A prefix that matches zero real
claim_ids silently starves that source's dossiers -- this happened once:
"nba_shooting_" never matched any of nba_shooting_claims.jsonl's 20
per-dimension ids (e.g. "nba_ts_pct_top50_2024-25"), fixed by listing each
dimension's real prefix explicitly. See
test_vault_feed.test_claim_id_to_file_prefixes_match_real_on_disk_claim_ids
for the regression guard.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Additional validation files whose VERIFIED claim_ids also feed the dossier
# (ranking-kind claims validated outside the main ops validation file).
EXTRA_VALIDATION_PATHS = [
    REPO_ROOT / "data/cache/intel_claims/tennis_hold_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/mlb_pitcher_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/soccer_intl_strength_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/tennis_h2h_index_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/catcher_framing_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/umpire_zone_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/platoon_split_claims_validation.json",
    # full-population registry additions (PROGRAM v3 item 4, lane dossier-fullpop):
    # these VERIFIED claim sources previously had no path into the dossier at all.
    REPO_ROOT / "data/cache/intel_claims/nba_quality_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/nba_fit_ingredient_claims_validation.json",
    REPO_ROOT / "data/cache/intel_claims/tennis_claims_v3_validation.json",
]

# claim_id prefix -> claims jsonl filename (only ranking claims from these files are eligible).
# nba_shooting_claims.jsonl's 20 dimension claim_ids do NOT share a common
# "nba_shooting_" prefix -- each is named per-dimension, so each is listed
# explicitly (a single non-matching prefix silently starves every NBA player
# dossier -- the exact bug this registry fixes).
CLAIM_ID_TO_FILE = {
    "nba_and_one_rate_": "nba_shooting_claims.jsonl",
    "nba_clutch_scoring_": "nba_shooting_claims.jsonl",
    "nba_cs_gravity_efg_": "nba_shooting_claims.jsonl",
    "nba_drives_per_game_": "nba_shooting_claims.jsonl",
    "nba_efg_pct_": "nba_shooting_claims.jsonl",
    "nba_fg3a_per_game_": "nba_shooting_claims.jsonl",
    "nba_fga_per_game_": "nba_shooting_claims.jsonl",
    "nba_ft_reliability_": "nba_shooting_claims.jsonl",
    "nba_gravity_score_": "nba_shooting_claims.jsonl",
    "nba_late_clock_shots_pg_": "nba_shooting_claims.jsonl",
    "nba_minutes_pg_": "nba_shooting_claims.jsonl",
    "nba_pullup_combined_freq_": "nba_shooting_claims.jsonl",
    "nba_scheme_robustness_": "nba_shooting_claims.jsonl",
    "nba_score_margin_consistency_": "nba_shooting_claims.jsonl",
    "nba_shot_quality_ts_": "nba_shooting_claims.jsonl",
    "nba_spotup_ppp_": "nba_shooting_claims.jsonl",
    "nba_ts_pct_": "nba_shooting_claims.jsonl",
    "nba_unassisted_share_2pm_": "nba_shooting_claims.jsonl",
    "nba_unassisted_share_3pm_": "nba_shooting_claims.jsonl",
    "nba_usage_rate_": "nba_shooting_claims.jsonl",
    "nba_quality_": "nba_quality_claims.jsonl",
    "nba_fit_": "nba_fit_ingredient_claims.jsonl",
    "wnba_": "wnba_claims.jsonl",
    "tennis_hold_": "tennis_hold_claims.jsonl",
    "tennis_return_": "tennis_claims_v3.jsonl",
    "tennis_setdetail_": "tennis_claims_v3.jsonl",
    "mlb_pitcher_": "mlb_pitcher_claims.jsonl",
    "soccer_intl_strength_": "soccer_intl_strength_claims.jsonl",
    "mlb_catcher_framing_": "catcher_framing_claims.jsonl",
    "tennis_h2h_dominance_": "tennis_h2h_index_claims.jsonl",
    "tennis_playstyle_": "tennis_h2h_index_claims.jsonl",
    "mlb_umpire_zone_": "umpire_zone_claims.jsonl",
    "mlb_platoon_split_": "platoon_split_claims.jsonl",
}

# entity_key values eligible for per-entity dossier sections (ranking row field
# that names the entity + the row field holding its display name).
# A None name-field means: no display-name row field exists, fall back to the
# entity_key's own id value formatted as the display name.
ENTITY_KEY_NAME_FIELD = {
    "player_id": "player_name",
    "team": "team",
    "catcher_id": "catcher_name",
    "umpire_id": "umpire_name",
    "batter": "batter_name",
    "official_id": "official_name",  # wnba_referee_crew_foul_rate_full_2026
    "pid": "player_name",  # nba_fit_archetype_profile_current
    "team_posgroup": None,  # nba_fit_role_vacancy_by_team_posgroup_current -- falls back to raw id (e.g. "NOP|BIG")
}

# Pair-keyed entity_key values (list of two id fields) -> (id_field_pair, name_field_pair).
# Rendered to a single deterministic slug "p1_vs_p2" (lower id first for determinism).
PAIR_ENTITY_KEY_NAME_FIELDS = {
    ("p1_id", "p2_id"): ("p1_name", "p2_name"),
}
