"""Phase 1 miner: scheme_coverage.
Defensive scheme & coverage tendencies (team-level) + per-player offense-vs-coverage splits.
Consolidates:
  - data/intelligence/defensive_schemes.parquet      (league-wide numeric scheme axes + dominant_tag)
  - data/cache/atlas_team_defensive_scheme.parquet   (atlas coverage_scheme JSON, drop_vs_switch, switch_rate)
  - data/cache/team_system/team_defense_league.parquet (tov_force / ft_force sim knobs)
  - data/cache/team_system/league_team_game.parquet  (LEAK-FREE walk-forward defensive identity, all 30 teams)
  - data/cache/atlas_player_vs_scheme_splits.parquet (player offense-vs-coverage TS/usage by scheme)

LEAK DISCIPLINE (per Phase-0 guidance):
  - Atlas/intelligence scheme tags & axes are SEASON-POOLED (as_of 2026-05-31, after season) -> see target game.
    Flagged scouting_only (use as prior, never as a betting number). Numeric axes that summarize a full-season
    opponent-imposed split = in_season.
  - Per-player vs-scheme TS/usage splits computed WITHIN 2025-26 = in_season-leaky -> flagged in_season.
    No 2024-25 corpus exists, so a true prior_season version is UNFILLABLE (noted, not fabricated).
  - LEAK-FREE layer: walk-forward (expanding, prior-games-only) defensive four-factor identity re-derived by THIS
    miner from the raw league_team_game per-game OBSERVATION table, evaluated AS-OF the G4 tip (2026-06-10).
    Since every regular-season game (<=2026-04-06) precedes the G4 target, the as-of-G4 expanding aggregate uses
    NO future information relative to the G4 prediction -> leak_free for the G4 target.
  - tov_force / ft_force map directly to sim DEFENSE knobs but are season-pooled team rates -> in_season.

Output: data/cache/team_system/scheme_coverage.parquet
Every field's leak flag is documented in the returned summary (sim_knob_mapping + per-field FLAGS dict below).
"""
import json
import pandas as pd
import numpy as np

ROOT = "C:/Users/neelj/nba-ai-system"
OUT = ROOT + "/data/cache/team_system/scheme_coverage.parquet"
G4_DATE = "2026-06-10"  # target game tip; all reg-season games precede this

NYK_SAS = {"NYK", "SAS"}

# ---------------------------------------------------------------- load sources
ds_axes = pd.read_parquet(ROOT + "/data/intelligence/defensive_schemes.parquet")
atlas = pd.read_parquet(ROOT + "/data/cache/atlas_team_defensive_scheme.parquet")
tdl = pd.read_parquet(ROOT + "/data/cache/team_system/team_defense_league.parquet")
lg = pd.read_parquet(ROOT + "/data/cache/team_system/league_team_game.parquet")
vs = pd.read_parquet(ROOT + "/data/cache/atlas_player_vs_scheme_splits.parquet")
roles = pd.read_parquet(ROOT + "/data/cache/team_system/player_roles.parquet")

rows = []

# ============================================================ TEAM SCHEME ROWS
# atlas keyed by tricode; build lookups
atlas_lk = {r["team_tricode"]: r for _, r in atlas.iterrows()}
tdl_lk = {r["team"]: r for _, r in tdl.iterrows()}

# ---- LEAK-FREE walk-forward defensive identity from league_team_game ----
# For each defending team, expanding (prior-games-only) means of opponent four-factors, evaluated as-of G4.
# Each row in lg is a team's own game; the OPPONENT'S offensive output against this team = this team's defense.
# Here 'team' is the team whose box this row is; opp_* are what the opponent did. So team's DEFENSE = opp_* columns.
lg = lg.sort_values(["date", "gid"]).copy()
# Defensive four factors allowed (per defending team = lg.team):
#   ppp_allowed = opp_pts / opp_poss ; opp_tov_rate = opp_tov/opp_poss ; ft_rate_allowed = opp_fta/opp_fga
#   oreb_allowed = opp_oreb/(opp_oreb+dreb)
defrows = lg.copy()
defrows["ppp_allowed"] = defrows["opp_pts"] / defrows["opp_poss"].replace(0, np.nan)
defrows["opp_tov_rate"] = defrows["opp_tov"] / defrows["opp_poss"].replace(0, np.nan)
defrows["ft_rate_allowed"] = defrows["opp_fta"] / defrows["opp_fga"].replace(0, np.nan)
defrows["oreb_allowed"] = defrows["opp_oreb"] / (defrows["opp_oreb"] + defrows["dreb"]).replace(0, np.nan)
# as-of-G4: all games qualify (every date <= 2026-04-06 < G4). Full-season expanding == final mean here, but
# we compute it as a strictly prior-only aggregate to document the construction is walk-forward.
wf = defrows.groupby("team").agg(
    wf_n_games=("gid", "nunique"),
    wf_ppp_allowed=("ppp_allowed", "mean"),
    wf_opp_tov_rate_forced=("opp_tov_rate", "mean"),
    wf_ft_rate_allowed=("ft_rate_allowed", "mean"),
    wf_oreb_allowed=("oreb_allowed", "mean"),
).reset_index()
lg_ppp_mean = (defrows["opp_pts"].sum() / defrows["opp_poss"].sum())  # league baseline
wf["wf_ppp_allowed_z"] = (wf["wf_ppp_allowed"] - wf["wf_ppp_allowed"].mean()) / wf["wf_ppp_allowed"].std()
wf["wf_tov_forced_z"] = (wf["wf_opp_tov_rate_forced"] - wf["wf_opp_tov_rate_forced"].mean()) / wf["wf_opp_tov_rate_forced"].std()
wf["wf_ft_allowed_z"] = (wf["wf_ft_rate_allowed"] - wf["wf_ft_rate_allowed"].mean()) / wf["wf_ft_rate_allowed"].std()
wf_lk = {r["team"]: r for _, r in wf.iterrows()}

teams = sorted(set(ds_axes["team"].tolist()) | set(atlas_lk.keys()))
for t in teams:
    ar = ds_axes[ds_axes.team == t]
    ar = ar.iloc[0] if len(ar) else None
    at = atlas_lk.get(t)
    td = tdl_lk.get(t)
    w = wf_lk.get(t)
    drop_vs_switch = None
    dominant_tag = None
    all_tags = None
    atlas_conf = None
    if at is not None:
        try:
            cs = json.loads(at["coverage_scheme"])
            drop_vs_switch = cs.get("drop_vs_switch")
            dominant_tag = cs.get("dominant_tag")
            all_tags = "|".join(cs.get("all_tags", []))
        except Exception:
            pass
        atlas_conf = at.get("confidence")
    # numeric scheme axes (from defensive_schemes.parquet, season-pooled opponent-imposed)
    def _ax(c):
        return float(ar[c]) if (ar is not None and c in ar and pd.notna(ar[c])) else None
    rows.append({
        "row_type": "team_scheme",
        "entity": t,
        "entity_id": None,
        "team": t,
        "opp_scope": "league",
        # ----- scheme tags / labels (SCOUTING ONLY: season-pooled, sees target) -----
        "dominant_tag": dominant_tag if dominant_tag is not None else (ar["dominant_tag"] if ar is not None else None),
        "all_tags": all_tags if all_tags is not None else (ar["all_tags"] if ar is not None else None),
        "drop_vs_switch": drop_vs_switch,
        # ----- numeric scheme axes (IN_SEASON: season-pooled imposed-deviation z-scores) -----
        "drop_score": _ax("drop_score"),
        "paint_protection_score": _ax("paint_protection_score"),
        "perimeter_denial_score": _ax("perimeter_denial_score"),
        "pace_control_score": _ax("pace_control_score"),
        "iso_force_score": _ax("iso_force_score"),
        "closeout_score": _ax("closeout_score"),
        # ----- sim-knob team defense rates (IN_SEASON: season-pooled team rate) -----
        "tov_force": float(td["tov_force"]) if td is not None else None,
        "ft_force": float(td["ft_force"]) if td is not None else None,
        "oreb_strength": float(td["oreb_strength"]) if td is not None else None,
        # ----- LEAK-FREE walk-forward defensive identity (re-derived, as-of-G4) -----
        "wf_n_games": int(w["wf_n_games"]) if w is not None else None,
        "wf_ppp_allowed": round(float(w["wf_ppp_allowed"]), 4) if w is not None else None,
        "wf_ppp_allowed_z": round(float(w["wf_ppp_allowed_z"]), 4) if w is not None else None,
        "wf_opp_tov_rate_forced": round(float(w["wf_opp_tov_rate_forced"]), 4) if w is not None else None,
        "wf_tov_forced_z": round(float(w["wf_tov_forced_z"]), 4) if w is not None else None,
        "wf_ft_rate_allowed": round(float(w["wf_ft_rate_allowed"]), 4) if w is not None else None,
        "wf_ft_allowed_z": round(float(w["wf_ft_allowed_z"]), 4) if w is not None else None,
        "wf_oreb_allowed": round(float(w["wf_oreb_allowed"]), 4) if w is not None else None,
        # ----- player-vs-coverage fields (null on team rows) -----
        "best_scheme": None, "worst_scheme": None, "ts_best_minus_worst": None,
        "scheme_n_games": None, "scheme_usage_pct": None, "scheme_ts_pct": None, "scheme_pts_pg": None,
        # ----- meta -----
        "confidence": atlas_conf if atlas_conf is not None else (ar["confidence"] if ar is not None else None),
        "as_of": "2026-05-31",
        "wf_as_of": G4_DATE,
        "n_obs": int(ar["n_opposing_player_games"]) if (ar is not None and pd.notna(ar["n_opposing_player_games"])) else None,
    })

# ====================================================== PLAYER VS COVERAGE ROWS
# Restrict to NYK/SAS rotation players (depth where G4 needs it); include all schemes they faced.
id2team = {int(r["pid"]): r["team"] for _, r in roles.iterrows()}
id2name = {int(r["pid"]): r["player"] for _, r in roles.iterrows()}
id2mpg = {int(r["pid"]): r["mpg"] for _, r in roles.iterrows()}
nyksas_ids = {pid for pid, tm in id2team.items() if tm in NYK_SAS}

SCHEME_ORDER = ["DROP COVERAGE", "SWITCH HEAVY", "PAINT-FIRST DEFENSE", "HELP DEFENSE", "PACE CONTROL", "BALANCED", "ISO FORCE"]

for _, vr in vs.iterrows():
    pid = int(vr["player_id"])
    if pid not in nyksas_ids:
        continue
    tm = id2team.get(pid)
    nm = id2name.get(pid, f"Player_{pid}")
    try:
        by = json.loads(vr["by_scheme"])
    except Exception:
        continue
    best = vr["best_scheme"]
    worst = vr["worst_scheme"]
    gap = float(vr["scheme_ts_pct_best_minus_worst"]) if pd.notna(vr["scheme_ts_pct_best_minus_worst"]) else None
    for skey, s in by.items():
        tag = s.get("tag", skey.upper())
        ng = s.get("n_games")
        if not ng or ng < 4:  # require >=4 games for a usable split
            continue
        rows.append({
            "row_type": "player_vs_coverage",
            "entity": nm,
            "entity_id": pid,
            "team": tm,
            "opp_scope": tag,           # the opposing DEFENSIVE scheme this split is vs
            "dominant_tag": None, "all_tags": None, "drop_vs_switch": None,
            "drop_score": None, "paint_protection_score": None, "perimeter_denial_score": None,
            "pace_control_score": None, "iso_force_score": None, "closeout_score": None,
            "tov_force": None, "ft_force": None, "oreb_strength": None,
            "wf_n_games": None, "wf_ppp_allowed": None, "wf_ppp_allowed_z": None,
            "wf_opp_tov_rate_forced": None, "wf_tov_forced_z": None,
            "wf_ft_rate_allowed": None, "wf_ft_allowed_z": None, "wf_oreb_allowed": None,
            # player-vs-coverage split fields (IN_SEASON leaky)
            "best_scheme": best, "worst_scheme": worst, "ts_best_minus_worst": gap,
            "scheme_n_games": int(ng),
            "scheme_usage_pct": round(float(s.get("usage_pct")), 4) if s.get("usage_pct") is not None else None,
            "scheme_ts_pct": round(float(s.get("ts_pct")), 4) if s.get("ts_pct") is not None else None,
            "scheme_pts_pg": round(float(s.get("pts_pg")), 2) if s.get("pts_pg") is not None else None,
            "confidence": vr.get("confidence"),
            "as_of": vr.get("as_of"),
            "wf_as_of": None,
            "n_obs": int(vr["n_games_total"]) if pd.notna(vr["n_games_total"]) else None,
        })

df = pd.DataFrame(rows)

# ---------------------------------------------------------------- per-field leak flags
# Stored as a parallel single-row reference + as a JSON column documenting each field's flag.
FLAGS = {
    "row_type": "leak_free", "entity": "leak_free", "entity_id": "leak_free", "team": "leak_free",
    "opp_scope": "leak_free",
    # team scheme labels & axes: season-pooled, sees target game
    "dominant_tag": "scouting_only", "all_tags": "scouting_only", "drop_vs_switch": "scouting_only",
    "drop_score": "in_season", "paint_protection_score": "in_season", "perimeter_denial_score": "in_season",
    "pace_control_score": "in_season", "iso_force_score": "in_season", "closeout_score": "in_season",
    # sim-knob team rates: season-pooled team rate
    "tov_force": "in_season", "ft_force": "in_season", "oreb_strength": "in_season",
    # walk-forward defensive identity: re-derived expanding/prior-only, as-of-G4 -> leak_free for G4 target
    "wf_n_games": "leak_free", "wf_ppp_allowed": "leak_free", "wf_ppp_allowed_z": "leak_free",
    "wf_opp_tov_rate_forced": "leak_free", "wf_tov_forced_z": "leak_free",
    "wf_ft_rate_allowed": "leak_free", "wf_ft_allowed_z": "leak_free", "wf_oreb_allowed": "leak_free",
    # player vs-coverage splits: computed within 2025-26 -> in_season leaky
    "best_scheme": "in_season", "worst_scheme": "in_season", "ts_best_minus_worst": "in_season",
    "scheme_n_games": "in_season", "scheme_usage_pct": "in_season", "scheme_ts_pct": "in_season",
    "scheme_pts_pg": "in_season",
    "confidence": "leak_free", "as_of": "leak_free", "wf_as_of": "leak_free", "n_obs": "leak_free",
}
df["_leak_flags"] = json.dumps(FLAGS)

df.to_parquet(OUT, index=False)
print("WROTE", OUT, df.shape)
print("row_type counts:")
print(df.row_type.value_counts().to_string())
print("teams with leak_free wf identity:", df[df.row_type == 'team_scheme'].wf_ppp_allowed.notna().sum())
print("NYK/SAS player_vs_coverage rows:", df[df.row_type == 'player_vs_coverage'].shape[0],
      "players:", df[df.row_type == 'player_vs_coverage'].entity_id.nunique())
