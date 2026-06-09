"""
Mine ONE head-to-head matchup signal for the NYK-vs-SAS possession sim.

SIGNAL = off_efficiency : each team's OFFENSIVE efficiency (ortg = pts/poss*100)
vs the SPECIFIC opponent, expressed as a RESIDUAL multiplier:
    raw_mult = ortg(team vs THIS opp) / ortg(team vs ALL OTHER opps)
(poss-weighted).  This nets out the team's own offensive quality, so what is
left is "does this team's offense play better/worse against this particular
opponent than against everyone else".

Mechanic = off_xfg  (scale the team's expected FG / scoring efficiency node).

DOUBLE-COUNT WARNING handled below: the sim ALREADY suppresses offense via the
opponent's GENERIC defense (per-shot INTERIOR_D/PERIMETER_D + anchor matchup_mult
centered at league-avg D=65).  Our raw_mult, being (vs-opp / vs-others), is
exactly the offense-vs-THIS-opp relative to offense-vs-the-field.  That ratio
STILL contains the opponent's generic defensive quality (SAS's generic D depresses
EVERY offense it faces, and shows up in NYK's vs-SAS number too).  So part of this
signal overlaps what the sim already applies.  We quantify and discuss netting.
"""
import json
import os
import numpy as np
import pandas as pd

ROOT = r"C:\Users\neelj\nba-ai-system"
TG = os.path.join(ROOT, "data", "cache", "team_system", "team_game.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "team_system", "matchup")
OUT = os.path.join(OUT_DIR, "off_efficiency.json")

K = 6  # shrink constant for team-level


def poss_weighted_ortg(sub):
    """pts/poss*100, poss-weighted across the rows in sub."""
    pts = sub["pts"].sum()
    poss = sub["poss"].sum()
    return 100.0 * pts / poss if poss > 0 else np.nan


def team_off_mult(df, team, opp):
    vs_opp = df[(df["team"] == team) & (df["opp"] == opp)]
    vs_others = df[(df["team"] == team) & (df["opp"] != opp)]
    o_opp = poss_weighted_ortg(vs_opp)
    o_oth = poss_weighted_ortg(vs_others)
    n = len(vs_opp)
    raw = o_opp / o_oth if o_oth and not np.isnan(o_oth) else np.nan
    return dict(
        ortg_vs_opp=o_opp,
        ortg_vs_others=o_oth,
        n_games=n,
        raw=raw,
        poss_vs_opp=float(vs_opp["poss"].sum()),
        poss_vs_others=float(vs_others["poss"].sum()),
    )


def shrink(raw, n, k):
    w = n / (n + k)
    return 1.0 + w * (raw - 1.0), w


def main():
    df = pd.read_parquet(TG)

    nyk = team_off_mult(df, "NYK", "SAS")
    sas = team_off_mult(df, "SAS", "NYK")
    n = nyk["n_games"]  # 4 (symmetric)

    nyk_shr, w = shrink(nyk["raw"], n, K)
    sas_shr, _ = shrink(sas["raw"], n, K)

    # ---- net margin effect in pts/100, NYK perspective ----
    # NYK margin/100 = NYK off - NYK def(=SAS off).
    # The signal moves NYK off UP if nyk_shr>1, and moves SAS off (NYK's defense
    # gives up) per sas_shr.  Net residual margin = change in NYK off minus
    # change in SAS off, evaluated at the league-baseline ortg vs-others.
    nyk_off_base = nyk["ortg_vs_others"]
    sas_off_base = sas["ortg_vs_others"]
    d_nyk_off = nyk_off_base * (nyk_shr - 1.0)      # NYK scores more/less
    d_sas_off = sas_off_base * (sas_shr - 1.0)      # SAS (NYK's opp) scores more/less
    residual_pts_per100 = d_nyk_off - d_sas_off     # + = helps NYK

    # ---- double-count overlap: how much of NYK's vs-SAS edge is just SAS's
    # generic defense (which the sim already applies)?  SAS generic D suppresses
    # the FIELD by sas_genD = league_field_ortg_vs_SAS ... but in a 2-team cache
    # we cannot see SAS vs the league.  Proxy: compare both teams' raw mults.
    # If BOTH teams' offense moves the SAME direction vs each other it'd be pace;
    # here NYK off is ~flat vs SAS while SAS off COLLAPSES vs NYK -> the residual
    # is concentrated on the SAS-collapses-vs-NYK side, which is NYK's DEFENSE
    # being specifically good vs SAS, i.e. it lives on the def node the sim
    # already models generically.

    result = {
        "signal": "off_efficiency",
        "mechanic": "off_xfg",
        "mult_nyk": round(nyk_shr, 4),
        "mult_sas": round(sas_shr, 4),
        "raw_nyk": round(nyk["raw"], 4),
        "raw_sas": round(sas["raw"], 4),
        "n_games": int(n),
        "shrink_w": round(w, 4),
        "K": K,
        "ortg": {
            "nyk_vs_sas": round(nyk["ortg_vs_opp"], 2),
            "nyk_vs_others": round(nyk["ortg_vs_others"], 2),
            "sas_vs_nyk": round(sas["ortg_vs_opp"], 2),
            "sas_vs_others": round(sas["ortg_vs_others"], 2),
        },
        "residual_pts_per100": round(residual_pts_per100, 2),
        "notes": (
            "raw = ortg(vs THIS opp)/ortg(vs ALL OTHER opps), poss-weighted, NYK & SAS "
            "rows only (2-team cache). n=4 H2H games -> heavy shrink (w=n/(n+6)=0.40). "
            "NYK off is ~flat vs SAS (raw_nyk~1); the whole signal is SAS OFFENSE "
            "COLLAPSING vs NYK (raw_sas<<1). DOUBLE-COUNT: that collapse is NYK's "
            "DEFENSE being specifically strong vs SAS -- it lives on the SAME node the "
            "sim ALREADY suppresses via generic opp-defense (INTERIOR_D/PERIMETER_D + "
            "anchor matchup_mult). The vs-opp/vs-others ratio nets out SAS's OWN "
            "offensive quality but does NOT net out NYK's generic defensive quality, "
            "which the sim re-applies. So this signal substantially OVERLAPS the sim's "
            "generic defense; wire only as the post-generic RESIDUAL (apply to SAS "
            "off_xfg the part of mult_sas not explained by NYK league-avg D), and on "
            "n=4 it is noise-dominated -> shrink_more or reject."
        ),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)

    # ascii-only prints
    print("=== off_efficiency matchup signal (NYK vs SAS) ===")
    print("n_games (H2H, each side):", n, " shrink w:", round(w, 4))
    print("-- NYK offense --")
    print("  ortg vs SAS   :", round(nyk["ortg_vs_opp"], 2),
          " (poss", round(nyk["poss_vs_opp"], 1), ")")
    print("  ortg vs others:", round(nyk["ortg_vs_others"], 2),
          " (poss", round(nyk["poss_vs_others"], 1), ")")
    print("  raw_nyk:", round(nyk["raw"], 4), " shrunk:", round(nyk_shr, 4))
    print("-- SAS offense --")
    print("  ortg vs NYK   :", round(sas["ortg_vs_opp"], 2),
          " (poss", round(sas["poss_vs_opp"], 1), ")")
    print("  ortg vs others:", round(sas["ortg_vs_others"], 2),
          " (poss", round(sas["poss_vs_others"], 1), ")")
    print("  raw_sas:", round(sas["raw"], 4), " shrunk:", round(sas_shr, 4))
    print("-- margin effect (NYK perspective) --")
    print("  d_nyk_off  :", round(d_nyk_off, 2), "pts/100")
    print("  d_sas_off  :", round(d_sas_off, 2), "pts/100 (NYK opp)")
    print("  residual   :", round(residual_pts_per100, 2), "pts/100 (+ helps NYK)")
    print("wrote:", OUT)


if __name__ == "__main__":
    main()
