"""Mine the shot_mix head-to-head matchup signal for NYK vs SAS.

SIGNAL: does the shot DIET shift in the matchup?
  rim_fga/fga (rim rate) and fg3a/fga (three rate) vs the opponent vs vs-others, per team.
Mechanic = shot_mix.

Raw matchup multiplier = (stat vs THIS opp) / (stat vs ALL OTHER opps), poss-weighted.
Shrink: shrunk = 1 + w*(raw-1), w = n/(n+K), K=6.
Net margin effect in pts/100 computed from the rim<->three reallocation, NYK perspective.
"""
import json
import os
import numpy as np
import pandas as pd

REPO = r"C:\Users\neelj\nba-ai-system"
TG = os.path.join(REPO, "data", "cache", "team_system", "team_game.parquet")
OUT_DIR = os.path.join(REPO, "data", "cache", "team_system", "matchup")
OUT = os.path.join(OUT_DIR, "shot_mix.json")

K = 6

df = pd.read_parquet(TG)

# League-average points-per-attempt by zone, for converting a shot-diet shift into pts/100.
# Use the full team_game corpus to estimate eFG-style value per attempt.
# rim PPA from rim_fgm/rim_fga (2pt makes -> 2 pts); three PPA from fg3m/fg3a (3 pts).
lg_rim_fg = df["rim_fgm"].sum() / df["rim_fga"].sum()
lg_3_fg = df["fg3m"].sum() / df["fg3a"].sum()
lg_rim_ppa = 2.0 * lg_rim_fg
lg_3_ppa = 3.0 * lg_3_fg
# Non-rim two value (mid/paint) as a fallback "where three attempts come from": use overall 2pt-minus-rim.
fg2a = df["fga"] - df["fg3a"]
fg2m = df["fgm"] - df["fg3m"]
nonrim_2a = (df["fga"] - df["fg3a"] - df["rim_fga"]).clip(lower=0)
# approximate non-rim 2pt makes
nonrim_2m = (fg2m - df["rim_fgm"]).clip(lower=0)
lg_nonrim2_ppa = 2.0 * (nonrim_2m.sum() / max(nonrim_2a.sum(), 1))

print("LEAGUE PPA: rim=%.3f three=%.3f nonrim2=%.3f" % (lg_rim_ppa, lg_3_ppa, lg_nonrim2_ppa))


def poss_weighted_rate(sub, num_col):
    """poss-weighted mean of (num_col / fga): weight each game by poss, rate = num/fga."""
    rate = sub[num_col] / sub["fga"]
    w = sub["poss"]
    return float(np.average(rate, weights=w))


def analyze(team, opp):
    t = df[df["team"] == team]
    vs = t[t["opp"] == opp]
    others = t[t["opp"] != opp]
    n = len(vs)
    w = n / (n + K)

    res = {"team": team, "opp": opp, "n_games": n, "w": w}
    for label, col in [("rim", "rim_fga"), ("three", "fg3a")]:
        r_vs = poss_weighted_rate(vs, col)
        r_oth = poss_weighted_rate(others, col)
        raw = r_vs / r_oth if r_oth else float("nan")
        shrunk = 1 + w * (raw - 1)
        res[label] = {
            "rate_vs": r_vs,
            "rate_others": r_oth,
            "raw": raw,
            "shrunk": shrunk,
        }
    # absolute fga/poss to estimate shots reallocated
    res["fga_per_poss_vs"] = float(np.average(vs["fga"] / vs["poss"], weights=vs["poss"]))
    res["fga_per_poss_others"] = float(np.average(others["fga"] / others["poss"], weights=others["poss"]))
    return res


nyk = analyze("NYK", "SAS")
sas = analyze("SAS", "NYK")

print("\n==== NYK vs SAS ====")
for k in ("rim", "three"):
    d = nyk[k]
    print("  %-6s rate vs SAS=%.4f vs others=%.4f  raw=%.3f  shrunk=%.3f  (n=%d w=%.2f)"
          % (k, d["rate_vs"], d["rate_others"], d["raw"], d["shrunk"], nyk["n_games"], nyk["w"]))
print("  fga/poss vs SAS=%.3f vs others=%.3f" % (nyk["fga_per_poss_vs"], nyk["fga_per_poss_others"]))

print("\n==== SAS vs NYK ====")
for k in ("rim", "three"):
    d = sas[k]
    print("  %-6s rate vs NYK=%.4f vs others=%.4f  raw=%.3f  shrunk=%.3f  (n=%d w=%.2f)"
          % (k, d["rate_vs"], d["rate_others"], d["raw"], d["shrunk"], sas["n_games"], sas["w"]))
print("  fga/poss vs NYK=%.3f vs others=%.3f" % (sas["fga_per_poss_vs"], sas["fga_per_poss_others"]))


def diet_pts_per100(team_res):
    """Net pts/100 from the SHRUNK shot-diet shift, this team's offense.
    Model: same total fga/poss; the matchup moves shot share between rim and three.
    delta_rim_share = (shrunk_rim - 1) * rate_others_rim
    delta_3_share   = (shrunk_3   - 1) * rate_others_3
    Shots gained in a zone vs league value; the offsetting shots come from the
    'neutral' non-rim-2 bucket (worst value), so each reallocated attempt's net
    value = (zone_ppa - nonrim2_ppa) * delta_share * fga_per_100poss.
    """
    fga_per100 = team_res["fga_per_poss_others"] * 100.0
    d_rim = (team_res["rim"]["shrunk"] - 1) * team_res["rim"]["rate_others"]
    d_3 = (team_res["three"]["shrunk"] - 1) * team_res["three"]["rate_others"]
    pts = (d_rim * fga_per100 * (lg_rim_ppa - lg_nonrim2_ppa)
           + d_3 * fga_per100 * (lg_3_ppa - lg_nonrim2_ppa))
    return pts, d_rim, d_3, fga_per100


nyk_pts, nyk_drim, nyk_d3, nyk_fga100 = diet_pts_per100(nyk)
sas_pts, sas_drim, sas_d3, sas_fga100 = diet_pts_per100(sas)

# NYK margin perspective: NYK offense diet effect helps NYK (+); SAS offense diet effect hurts NYK (-).
residual_pts_per100 = nyk_pts - sas_pts

print("\n==== PTS/100 DIET EFFECT ====")
print("  NYK offense diet effect: %+.3f pts/100 (d_rim_share=%+.4f d_3_share=%+.4f fga/100=%.1f)"
      % (nyk_pts, nyk_drim, nyk_d3, nyk_fga100))
print("  SAS offense diet effect: %+.3f pts/100 (d_rim_share=%+.4f d_3_share=%+.4f fga/100=%.1f)"
      % (sas_pts, sas_drim, sas_d3, sas_fga100))
print("  NET margin (NYK persp) = NYK_off - SAS_off = %+.3f pts/100" % residual_pts_per100)

# Composite single multiplier per team for the sim's shot_mix node:
# express as a rim-rate multiplier (the primary lever; three is the complement).
mult_nyk = nyk["rim"]["shrunk"]
mult_sas = sas["rim"]["shrunk"]
raw_nyk = nyk["rim"]["raw"]
raw_sas = sas["rim"]["raw"]

notes = (
    "shot_mix = rim_fga/fga and fg3a/fga vs THIS opp / vs ALL OTHER opps, poss-weighted, K=6 shrink. "
    "n=4 H2H games -> w=%.2f, heavy shrink toward 1.0. "
    "RAW rim mult NYK=%.3f (vs SAS rim rate %.3f vs others %.3f), SAS=%.3f (vs NYK %.3f vs others %.3f). "
    "RAW three mult NYK=%.3f, SAS=%.3f. "
    "Net diet pts/100 (NYK persp)=%+.3f -> tiny after shrink. "
    "LEAK-SAFE: built only from team box shot counts, no outcome/line leakage; "
    "but uses all 4 H2H incl 2 Finals games (as-of fine for sim, retrospective scouting). "
    "DOUBLE-COUNT: shot_mix is the OPPONENT-DEFENSE-INDUCED diet shift -- SAS interior D (Wemby) "
    "pushing NYK off the rim is EXACTLY the generic opponent rim_d/perim_d the sim ALREADY applies "
    "(per-shot INTERIOR_D/PERIMETER_D + anchor _matchup_mult). The residual here (vs-opp / vs-others) "
    "nets out NYK's own quality but OVERLAPS the generic opp-defense channel: a strong-interior-D team "
    "suppresses rim shots for ALL opponents, which the sim already encodes via SAS's team rim_d rating. "
    "On 4 games the residual is noise-dominated and largely redundant with the defense node."
) % (
    nyk["w"], raw_nyk, nyk["rim"]["rate_vs"], nyk["rim"]["rate_others"],
    raw_sas, sas["rim"]["rate_vs"], sas["rim"]["rate_others"],
    nyk["three"]["raw"], sas["three"]["raw"], residual_pts_per100,
)

out = {
    "signal": "shot_mix",
    "mechanic": "shot_mix",
    "mult_nyk": round(mult_nyk, 4),
    "mult_sas": round(mult_sas, 4),
    "raw_nyk": round(raw_nyk, 4),
    "raw_sas": round(raw_sas, 4),
    "n_games": int(nyk["n_games"]),
    "residual_pts_per100": round(residual_pts_per100, 3),
    "notes": notes,
    "detail": {
        "nyk_rim": nyk["rim"], "nyk_three": nyk["three"],
        "sas_rim": sas["rim"], "sas_three": sas["three"],
        "league_ppa": {"rim": lg_rim_ppa, "three": lg_3_ppa, "nonrim2": lg_nonrim2_ppa},
        "nyk_diet_pts_per100": nyk_pts, "sas_diet_pts_per100": sas_pts,
    },
}

os.makedirs(OUT_DIR, exist_ok=True)
with open(OUT, "w") as f:
    json.dump(out, f, indent=2)
print("\nWROTE", OUT)
