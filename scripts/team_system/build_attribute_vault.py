"""Deep attribute vault — 150+ context-adjusted 0-99 attributes per player.

"Every aspect of basketball" as a normalized attribute, sourced from the FULL-SEASON
league-wide signal layer (data/cache/signals/*) so stars (SGA/Jokic/Luka) have real data,
not the NYK/SAS-partial box rates. Each attribute is a league percentile (0-99) of a
meaningful basketball measure, volume-gated (low-sample -> 50 prior) and, where the signal
supports it, already context-adjusted (defense is opponent-adjusted; efficiency is
usage-adjusted). These feed the role-aware category ratings + OVERALL (build_player_ratings).

Output: data/cache/team_system/attribute_vault.parquet  (one row per player, ~150 attr cols)
  python scripts/team_system/build_attribute_vault.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
SIG = os.path.join(ROOT, "data", "cache", "signals")

# (out_attr, domain, source_col, invert, gate_col, gate_min) -> league percentile 0-99.
# domains: sp=scoring_profile pm=playmaking dm=defense_matchup rb=rebounding
#          sc=shotclock_leverage si=situational_splits du=durability cj=correlation_joint
#          ir=ingame_rotation ra=rates(team_system) at=attributes(physical) ro=roles
SPEC = [
    # --- FINISHING (rim/paint/contact) ---
    ("fin_rim_pct", "sp", "shotloc_rim_fg_pct", False, "shotloc_rim_fga", 40),
    ("fin_rim_volume", "sp", "shotloc_rim_shot_share", False, "shotloc_total_fga", 100),
    ("fin_paint_pct", "sp", "shotloc_paint_nonra_fg_pct", False, "shotloc_paint_nonra_fga", 25),
    ("fin_drive_pct", "sp", "trk_drive_fg_pct", False, "trk_drives_per_g", 2),
    ("fin_drive_pts", "sp", "trk_drive_pts_per_drive", False, "trk_drives_per_g", 2),
    ("fin_contact_ft", "sp", "fta_per_36", False, None, None),
    ("fin_transition", "sp", "syn_transition_ppp", False, None, None),
    ("fin_2nd_chance", "rb", "pts_2nd_chance_pg", False, None, None),
    ("fin_paint_pts", "sp", "bkdn_pct_pts_paint", False, None, None),
    # --- SHOOTING (3 / mid / FT, volume + accuracy) ---
    ("shoot_corner3", "sp", "shotloc_corner3_fg_pct", False, "shotloc_corner3_fga", 15),
    ("shoot_above3", "sp", "shotloc_above3_fg_pct", False, "shotloc_above3_fga", 40),
    ("shoot_catch_shoot3", "sp", "trk_catch_shoot_fg3_pct", False, "trk_catch_shoot_fg3a", 1.0),
    ("shoot_catch_shoot_efg", "sp", "trk_catch_shoot_efg_pct", False, "trk_catch_shoot_fga", 1.5),
    ("shoot_mid", "sp", "shotloc_midrange_fg_pct", False, "shotloc_midrange_fga", 25),
    ("shoot_ft", "sp", "ft_pct", False, "fta_pg", 1),
    ("shoot_3_volume", "sp", "shotloc_above3_shot_share", False, "shotloc_total_fga", 100),
    ("shoot_offdribble3", "sp", "sc_unassisted_share_3pm", False, None, None),
    ("shoot_pts_from_3", "sp", "bkdn_pct_pts_3pt", False, None, None),
    # --- PLAYMAKING / PASSING ---
    ("play_ast_pct", "pm", "ast_pct_bbref", False, None, None),
    ("play_ast_per_pass", "pm", "ast_per_pass", False, "passes_made_pg", 20),
    ("play_potential_ast", "pm", "potential_ast_pg", False, None, None),
    ("play_secondary_ast", "pm", "secondary_ast_pg", False, None, None),
    ("play_pts_created", "pm", "ast_pts_created_pg", False, None, None),
    ("play_drive_kick", "pm", "drive_and_kick_pg", False, None, None),
    ("play_screen_ast", "pm", "screen_ast_pg", False, None, None),
    ("play_creation_conv", "pm", "creation_conversion", False, None, None),
    ("play_ato", "pm", "ato_season", False, None, None),
    ("play_ball_security", "pm", "tov_pct_bbref", True, None, None),
    ("play_passes_volume", "pm", "passes_made_pg", False, None, None),
    # --- SHOT CREATION / HANDLE / SELF-OFFENSE ---
    ("crea_usage", "ra", "use_per_min", False, "mpg", 8),
    ("crea_unassisted2", "sp", "sc_unassisted_share_2pm", False, None, None),
    ("crea_iso_ppp", "sp", "syn_iso_ppp", False, None, None),
    ("crea_pnr_ppp", "sp", "syn_pnr_bh_ppp", False, None, None),
    ("crea_post_ppp", "sp", "syn_postup_ppp", False, None, None),
    ("crea_drives_vol", "sp", "trk_drives_per_g", False, None, None),
    ("crea_late_clock_ts", "sc", "late_clock_ts_pct", False, "late_clock_shots_pg", 1),
    ("crea_drive_pts_share", "sp", "sc_drive_pts_share", False, None, None),
    # --- SCORING (volume + efficiency, usage-aware) ---
    ("score_volume", "cj", "vol_pts_pctile", False, None, None),
    ("score_spotup_ppp", "sp", "syn_spotup_ppp", False, None, None),
    # --- REBOUNDING ---
    ("reb_oreb_pct", "rb", "oreb_pct_s", False, "n_games", 5),
    ("reb_dreb_pct", "rb", "dreb_pct_s", False, "n_games", 5),
    ("reb_total_pct", "rb", "reb_pct_s", False, "n_games", 5),
    ("reb_box_outs", "rb", "box_outs_pg", False, None, None),
    ("reb_contested", "rb", "contested_shots_pg", False, None, None),
    # --- INTERIOR DEFENSE / RIM PROTECTION (opp-adjusted) ---
    ("intd_block", "dm", "block_per100", False, "poss_defended", 50),
    ("intd_stops", "dm", "stops_index", True, "poss_defended", 80),     # <1 suppresses -> invert
    ("intd_fg_suppress", "dm", "fg_suppression", True, "poss_defended", 80),
    ("intd_contested", "rb", "contested_shots_pg", False, None, None),
    # --- PERIMETER DEFENSE (opp-adjusted) ---
    ("perd_steal", "ra", "stl_per_min", False, "mpg", 8),
    ("perd_stops", "dm", "stops_index", True, "poss_defended", 80),
    ("perd_fg3_suppress", "dm", "fg3_allowed", True, "poss_defended", 50),
    ("perd_versatility", "dm", "switch_per100", False, "poss_defended", 50),
    ("perd_foul_disc", "dm", "foul_per100", True, "poss_defended", 50),
    # --- BASKETBALL IQ / CLUTCH / CONSISTENCY ---
    ("clutch_fg", "sc", "clutch_fg_pct", False, "clutch_gp", 8),
    ("clutch_pts36", "sc", "clutch_pts_per36", False, "clutch_gp", 8),
    ("clutch_plusminus", "sc", "clutch_plus_minus", False, "clutch_gp", 5),
    ("clutch_ft", "sc", "clutch_ft_pct", False, "clutch_gp", 5),
    ("clutch_3", "sc", "clutch_fg3_pct", False, "clutch_gp", 8),
    ("iq_q4_tilt", "sc", "q4_pts_tilt", False, "qs_n_games", 10),
    ("iq_foul_disc", "si", "foul_out_rate", True, "foul_n_games", 10),
    ("iq_foul_trouble", "si", "foul_trouble_rate_l10", True, "foul_n_games", 10),
    ("iq_late_clock_rate", "sc", "late_clock_rate", True, None, None),
    # --- FORM / CONSISTENCY (reliability of the night-to-night output) ---
    ("form_consistency_pts", "fo", "std_pts", True, "n_games", 10),
    ("form_trend_pts", "fo", "slope_pts", False, "n_games", 10),
    ("form_hot_pts", "fo", "ewma_pts", False, "n_games", 10),
    # --- SITUATIONAL RESILIENCE (context: rest / venue / score state) ---
    ("sit_b2b_resilience", "si", "efg_b2b_minus_2plus", False, "b2b_n_games_rest", 5),
    ("sit_road_scoring", "si", "road_pts_pg", False, "home_n_games", 8),
    ("sit_trail_efg", "si", "trail_efg", False, "trail_n_games", 8),
    ("sit_q4_scoring", "si", "q4_pts", False, "n_games_pqs", 10),
    # --- MOTOR / DURABILITY / AVAILABILITY ---
    ("motor_minutes", "du", "high_min_rate_2024_25", False, None, None),
    ("motor_box_outs", "rb", "box_outs_pg", False, None, None),
    ("durab_avail", "du", "avail_rate_l3seas", False, None, None),
    ("durab_peak", "du", "years_from_peak", True, None, None),
    ("durab_minload", "du", "min_mpg_2024_25", False, None, None),
    # --- DEFENSE breadth ---
    ("perd_matchup_load", "dm", "n_assignments_any", False, "poss_defended", 80),
    ("perd_blocks_per100", "dm", "block_per100", False, "poss_defended", 50),
    # --- PHYSICAL ---
    ("phys_height", "at", "height_in", False, None, None),
    ("phys_weight", "at", "weight_lb", False, None, None),
    ("phys_size_pos", "at", "size_z", False, None, None),
    ("phys_strength", "at", "strength_z", False, None, None),
    ("phys_agility", "at", "agility_proxy", False, None, None),
    ("phys_youth", "at", "age", True, None, None),
]


def _pctl(vals, invert=False):
    vals = np.asarray(vals, float)
    out = np.full(len(vals), 50.0)
    m = ~np.isnan(vals)
    if m.sum() >= 5:
        ref = np.sort(vals[m])
        r = np.searchsorted(ref, vals[m], side="right") / len(ref)
        out[m] = np.clip(1 + 98 * (1 - r if invert else r), 1, 99)
    return out


def _latest(df, key):
    """Latest season per player, forward-filled so a NaN in the newest season (e.g. the
    stale 2025-26 advanced-rebounding gap) falls back to the most recent non-null value."""
    if "season" in df.columns:
        df = df.sort_values("season")
        vcols = [c for c in df.columns if c != key]
        df[vcols] = df.groupby(key)[vcols].ffill()
        df = df.groupby(key).tail(1)
    return df.set_index(key)


def main():
    ra = pd.read_parquet(os.path.join(TS, "player_rates.parquet")).rename(columns={"pid": "player_id"})
    at = pd.read_parquet(os.path.join(TS, "player_attributes.parquet")).rename(columns={"pid": "player_id"})
    ro = pd.read_parquet(os.path.join(TS, "player_roles.parquet")).rename(columns={"pid": "player_id"})
    D = {"ra": ra.set_index("player_id"), "at": at.set_index("player_id"), "ro": ro.set_index("player_id")}
    for k, fn, key in [("sp", "scoring_profile", "player_id"), ("pm", "playmaking", "player_id"),
                       ("dm", "defense_matchup", "def_player_id"), ("rb", "rebounding", "player_id"),
                       ("sc", "shotclock_leverage", "player_id"), ("si", "situational_splits", "player_id"),
                       ("du", "durability_availability", "player_id"), ("cj", "correlation_joint", "player_id"),
                       ("fo", "form_trajectory", "player_id"), ("ir", "ingame_rotation", "player_id")]:
        fp = os.path.join(SIG, fn + ".parquet")
        if os.path.exists(fp):
            d = _latest(pd.read_parquet(fp), key)
            if key != "player_id":
                d.index.name = "player_id"
            D[k] = d

    # base index = every player with any signal (so stars not in partial rates are included)
    idx = set(ra.player_id)
    for k in ("sp", "pm", "dm", "rb"):
        if k in D:
            idx |= set(D[k].index)
    base = pd.DataFrame(index=sorted(idx)); base.index.name = "player_id"
    name = ra.set_index("player_id").player
    for k in ("sp", "pm", "du"):
        if k in D and "player_name" in D[k].columns:
            name = name.combine_first(D[k].player_name)
    base["player"] = name.reindex(base.index)
    base["team"] = ra.set_index("player_id").team.reindex(base.index)
    base["mpg"] = ra.set_index("player_id").mpg.reindex(base.index)

    for out, dom, col, inv, gcol, gmin in SPEC:
        if dom not in D or col not in D[dom].columns:
            base[out] = 50.0
            continue
        s = D[dom][col].reindex(base.index).astype(float)
        if gcol and gcol in D[dom].columns:
            g = D[dom][gcol].reindex(base.index).astype(float)
            s = s.where(g >= gmin)                      # gate: low-volume -> NaN -> 50 prior
        base[out] = _pctl(s.values, invert=inv)

    # --- computed / context-adjusted specials ---
    rr = D["ra"].reindex(base.index)
    ppm = (rr.pts_pg / rr.mpg.clip(lower=1))
    den = 2 * rr.use_per_min * (rr.shot_share + rr.ft_share)
    ts = np.where(den > 0, ppm / den, np.nan)
    base["score_ppm"] = _pctl(ppm.values)               # scoring rate
    base["score_ts"] = _pctl(ts)                        # raw efficiency
    # usage-adjusted efficiency: TS residual after linear fit on usage (high-usage eff is harder)
    u = rr.use_per_min.values.astype(float)
    m = ~np.isnan(ts) & ~np.isnan(u)
    if m.sum() > 30:
        b1, b0 = np.polyfit(u[m], np.asarray(ts)[m], 1)
        resid = np.asarray(ts) - (b0 + b1 * u)
        base["score_ts_usage_adj"] = _pctl(resid)
    else:
        base["score_ts_usage_adj"] = base["score_ts"]
    # shot-diet diversity (3-level scorer): entropy across rim/mid/3 shares
    sh = D.get("sp")
    if sh is not None:
        z = sh.reindex(base.index)
        parts = np.vstack([z.get(c, pd.Series(np.nan, base.index)).values for c in
                           ["shotloc_rim_shot_share", "shotloc_midrange_shot_share", "shotloc_above3_shot_share"]]).T
        parts = np.clip(parts, 1e-6, None); parts = parts / parts.sum(1, keepdims=True)
        ent = -(parts * np.log(parts)).sum(1)
        base["score_diversity"] = _pctl(np.where(np.isfinite(ent), ent, np.nan))
    # consistency as coefficient of variation (std/mean), so a 27-ppg star isn't dinged for
    # larger raw variance than a 6-ppg bench player. Low CV -> reliable -> high rating.
    fo = D.get("fo")
    if fo is not None and "std_pts" in fo.columns:
        f = fo.reindex(base.index)
        cv = f["std_pts"] / f["ewma_pts"].clip(lower=1.0)
        base["form_consistency_pts"] = _pctl(cv.where(f["n_games"] >= 10).values, invert=True)

    attr_cols = [c for c in base.columns if c not in ("player", "team", "mpg")]
    base.reset_index().to_parquet(os.path.join(TS, "attribute_vault.parquet"), index=False)

    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print(f"DONE: attribute_vault for {len(base)} players, {len(attr_cols)} attributes.")
    print("Sample attributes:", ", ".join(attr_cols[:12]), "...")
    show = ["score_ppm", "score_ts_usage_adj", "crea_iso_ppp", "play_ast_pct", "shoot_above3",
            "intd_block", "intd_stops", "perd_stops", "reb_dreb_pct", "phys_height"]
    for nm in ["Wembanyama", "Brunson", "Fox", "Gilgeous", "Jokic", "Doncic"]:
        row = base[base.player.astype(str).str.contains(nm, case=False, na=False)]
        if len(row):
            r = row.iloc[0]
            print(f"  {asc(r.player):20s} " + " ".join(f"{a.split('_',1)[1][:6]}{int(r[a]):>3d}" for a in show))
        else:
            print(f"  {nm:20s} (not found by name)")


if __name__ == "__main__":
    main()
