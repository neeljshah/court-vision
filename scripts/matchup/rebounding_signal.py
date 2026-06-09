"""
Head-to-head MATCHUP rebounding signal for NYK-vs-SAS possession sim.

Computes each team's rebounding edge vs THIS opponent vs vs ALL OTHER opponents,
poss-weighted, then shrinks (K=6 on 4 H2H games) and converts to a net margin
effect in pts/100 from NYK perspective.

mechanic = oreb (offensive-rebound multiplier node in the sim)

Rebounding shares within a single team_game row:
  - team OREB% = oreb / (oreb + opp_dreb)        # offensive glass for that team
  - team DREB% = dreb / (dreb + opp_oreb)         # defensive glass for that team
    opp_oreb is taken from the OTHER team's row for the same game (gid).

We build the multiplier on the OFFENSIVE rebound share (the 'oreb' mechanic),
which is the controllable lever the sim node modifies. The matchup multiplier is:
    raw = OREB%(team vs THIS opp, poss-weighted) / OREB%(team vs ALL OTHER opps)
This nets out the team's own baseline glass quality, so it is the RESIDUAL
matchup effect (does NYK crash the offensive glass vs SAS beyond its norm?).
"""
import json
import os
import pandas as pd

ROOT = r"C:\Users\neelj\nba-ai-system"
TG = os.path.join(ROOT, "data", "cache", "team_system", "team_game.parquet")
OUTDIR = os.path.join(ROOT, "data", "cache", "team_system", "matchup")
OUT = os.path.join(OUTDIR, "rebounding.json")

NYK, SAS = "NYK", "SAS"
K = 6  # team-level shrink

df = pd.read_parquet(TG)

# NOTE: this two-team cache only has NYK/SAS rows, so the opponent's offensive
# rebounds (needed for DREB%) are ONLY available for the 8 H2H rows -- there is no
# CLE/BOS/etc row. => DREB% vs-others is NOT computable from this dataset, so we
# do NOT build a DREB multiplier (it would be an inf/garbage split). The OREB side
# IS fully valid because opp_dreb is a column present in EVERY row.
#
# We DO compute the team's H2H defensive-glass share descriptively (oreb allowed)
# using the opponent's H2H row, purely for the notes -- never as a vs-others ratio.

# per-game OFFENSIVE rebound share (valid for all rows; opp_dreb always present)
df["oreb_den"] = df["oreb"] + df["opp_dreb"]
df["oreb_pct"] = df["oreb"] / df["oreb_den"]


def pw(sub, num_col, den_col):
    """Possession-weighted share = sum(num)/sum(den) (collapses small-game noise)."""
    return sub[num_col].sum() / sub[den_col].sum()


def split_share(team, opp, num_col, den_col):
    t = df[df["team"] == team]
    vs = t[t["opp"] == opp]
    others = t[t["opp"] != opp]
    return pw(vs, num_col, den_col), pw(others, num_col, den_col), len(vs)


def report(team, opp):
    o_vs, o_oth, n = split_share(team, opp, "oreb", "oreb_den")
    raw_o = o_vs / o_oth
    w = n / (n + K)
    sh_o = 1 + w * (raw_o - 1)
    return dict(team=team, opp=opp, n=n, w=w,
                oreb_vs=o_vs, oreb_oth=o_oth, raw_oreb=raw_o, shrunk_oreb=sh_o)


nyk = report(NYK, SAS)
sas = report(SAS, NYK)

# Descriptive H2H defensive-glass (oreb allowed) for notes only -- the opp's H2H
# offensive rebounds = the OTHER team's oreb in the same 4 games.
hh_nyk_oreb = df[(df["team"] == NYK) & (df["opp"] == SAS)]["oreb"].sum()
hh_sas_oreb = df[(df["team"] == SAS) & (df["opp"] == NYK)]["oreb"].sum()
hh_nyk_dreb = df[(df["team"] == NYK) & (df["opp"] == SAS)]["dreb"].sum()
hh_sas_dreb = df[(df["team"] == SAS) & (df["opp"] == NYK)]["dreb"].sum()
# NYK DREB% in H2H = nyk_dreb / (nyk_dreb + sas_oreb)
nyk_h2h_drebpct = hh_nyk_dreb / (hh_nyk_dreb + hh_sas_oreb)
sas_h2h_drebpct = hh_sas_dreb / (hh_sas_dreb + hh_nyk_oreb)

print("=== REBOUNDING MATCHUP SIGNAL (NYK vs SAS) ===")
print("(DREB% vs-others NOT computable: cache has only NYK/SAS rows -> no opp oreb)")
for r in (nyk, sas):
    print(f"\n{r['team']} vs {r['opp']}  (n={r['n']}, w={r['w']:.3f})")
    print(f"  OREB%  vs-opp={r['oreb_vs']:.4f}  vs-others={r['oreb_oth']:.4f}  "
          f"raw={r['raw_oreb']:.4f}  shrunk={r['shrunk_oreb']:.4f}")
print(f"\nH2H DREB% (descriptive only): NYK={nyk_h2h_drebpct:.4f}  SAS={sas_h2h_drebpct:.4f}")

# --- net margin effect in pts/100 (NYK perspective) ---
# An offensive rebound is roughly a second-chance possession. Extra OREB% over
# baseline -> extra possessions -> extra points. Convert via league OREB rate and
# value-per-possession.
# Approx: each 1% of OREB% on ~ (FGA+0.44*FTA) misses ~ a fraction of a possession.
# Use a simple, defensible conversion:
#   delta_oreb_share (shrunk) -> change in offensive rebounds per 100 missed-shot ops.
# We estimate missed-shot opportunities per 100 poss and value each ORB at ~1.05 pts
# (second-chance points per possession ~ league avg ortg per 100 / 100).

# league-ish baselines from the data
PPP = df["pts"].sum() / df["poss"].sum()          # points per possession (~1.13)
# offensive rebound opportunities per 100 poss for each team's offense = the denominator
# (oreb+opp_dreb) per 100 poss, vs OTHERS (baseline volume).


def orb_ops_per100(team, opp):
    t = df[(df["team"] == team) & (df["opp"] != opp)]
    return 100.0 * t["oreb_den"].sum() / t["poss"].sum()


def second_chance_value(team_rec, opp):
    """pts/100 from the team's OREB% matchup deviation (offense side)."""
    ops = orb_ops_per100(team_rec["team"], opp)          # ORB opportunities /100
    base_pct = team_rec["oreb_oth"]
    dpct = team_rec["shrunk_oreb"] - 1.0                 # fractional change in OREB%
    extra_orb = ops * base_pct * dpct                    # extra off rebounds /100
    return extra_orb * PPP                               # each extra ORB ~ a poss worth PPP


# NYK offensive glass vs SAS (helps NYK), SAS offensive glass vs NYK (hurts NYK).
nyk_off = second_chance_value(nyk, SAS)
sas_off = second_chance_value(sas, NYK)
residual = nyk_off - sas_off  # NYK perspective: + helps NYK

print(f"\nPPP (league-ish) = {PPP:.4f}")
print(f"NYK off-glass vs SAS  -> {nyk_off:+.3f} pts/100 (helps NYK)")
print(f"SAS off-glass vs NYK  -> {sas_off:+.3f} pts/100 (subtract; helps SAS)")
print(f"NET residual (NYK perspective) = {residual:+.3f} pts/100")

# Use OREB shrunk multipliers as the sim 'oreb' node multipliers.
mult_nyk = nyk["shrunk_oreb"]
mult_sas = sas["shrunk_oreb"]

notes = (
    "Signal = offensive-rebound (oreb) matchup multiplier. raw = OREB% vs-opp / "
    "OREB% vs-others, poss-weighted (nets out each team's own baseline glass). "
    "Shrunk K=6 on 4 H2H games (w=0.40). DOUBLE-COUNT: the sim already applies "
    "generic opponent INTERIOR_D/PERIMETER_D and a _matchup_mult on opponent rim/perim "
    "defense -- but those govern SHOT-MAKING suppression, NOT rebound allocation. The "
    "oreb node is a separate mechanic, so this residual does NOT directly overlap the "
    "generic shooting-defense the sim has. HOWEVER rebounding and shot quality are "
    "correlated (better D -> more contested/long misses -> different OREB), and on only "
    "4 games the deviation is noise-dominated. Recommend wiring at heavy shrink (or "
    "shrink_more) rather than full strength."
)

os.makedirs(OUTDIR, exist_ok=True)
result = dict(
    signal="rebounding",
    mechanic="oreb",
    mult_nyk=round(mult_nyk, 5),
    mult_sas=round(mult_sas, 5),
    raw_nyk=round(nyk["raw_oreb"], 5),
    raw_sas=round(sas["raw_oreb"], 5),
    n_games=int(nyk["n"]),
    residual_pts_per100=round(residual, 4),
    notes=notes,
    detail=dict(
        nyk_oreb_vs=round(nyk["oreb_vs"], 5), nyk_oreb_others=round(nyk["oreb_oth"], 5),
        sas_oreb_vs=round(sas["oreb_vs"], 5), sas_oreb_others=round(sas["oreb_oth"], 5),
        nyk_h2h_drebpct=round(nyk_h2h_drebpct, 5), sas_h2h_drebpct=round(sas_h2h_drebpct, 5),
        dreb_vs_others="uncomputable: cache has only NYK/SAS rows (no opp oreb)",
        shrink_w=round(nyk["w"], 4), K=K, ppp=round(PPP, 4),
        nyk_off_pts100=round(nyk_off, 4), sas_off_pts100=round(sas_off, 4),
    ),
)
with open(OUT, "w") as f:
    json.dump(result, f, indent=2)
print(f"\nWROTE {OUT}")
print(json.dumps(result, indent=2))
