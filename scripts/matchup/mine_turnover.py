"""
Mine the HEAD-TO-HEAD turnover-rate matchup signal for NYK vs SAS.

SIGNAL: turnover rate in the matchup. For each team we compute its OFFENSIVE
turnover rate (tov / poss) vs the opponent vs. vs-all-others, poss-weighted.

mechanic = tov_share

A team's OFFENSIVE turnover rate vs an opponent is jointly produced by:
  - that team's own ball-security (generic team quality), AND
  - the opponent's defensive ball-pressure / steal-generation (generic opp D).
By computing (rate vs THIS opp) / (rate vs ALL OTHER opps) we net out the
team's OWN quality. What remains is the RESIDUAL matchup effect, which is
mostly the opponent's defense -- exactly the thing the sim's generic
opponent-defense already prices. We flag that double-count.

NYK perspective for margin:
  - NYK offensive tov UP vs SAS  -> hurts NYK (lose possessions)
  - SAS offensive tov UP vs NYK  -> helps NYK (NYK forces SAS TOs)
The net residual margin = effect of (SAS extra TOs) minus (NYK extra TOs).
"""
import json
import os
import pandas as pd

REPO = r"C:\Users\neelj\nba-ai-system"
TG = os.path.join(REPO, "data", "cache", "team_system", "team_game.parquet")
OUTDIR = os.path.join(REPO, "data", "cache", "team_system", "matchup")
OUT = os.path.join(OUTDIR, "turnover.json")

K = 6  # team-level shrink constant


def poss_weighted_tov_rate(df):
    """offensive turnovers per possession, poss-weighted."""
    poss = df["poss"].sum()
    tov = df["tov"].sum()
    return tov / poss if poss > 0 else float("nan"), poss, tov


def matchup_mult(df, team, opp):
    """raw multiplier = (off tov rate vs opp) / (off tov rate vs all others)."""
    t = df[df["team"] == team]
    vs_opp = t[t["opp"] == opp]
    vs_oth = t[t["opp"] != opp]
    r_opp, p_opp, to_opp = poss_weighted_tov_rate(vs_opp)
    r_oth, p_oth, to_oth = poss_weighted_tov_rate(vs_oth)
    raw = r_opp / r_oth if r_oth > 0 else float("nan")
    n = len(vs_opp)
    return {
        "raw": raw,
        "rate_vs_opp": r_opp,
        "rate_vs_oth": r_oth,
        "n_games": n,
        "poss_vs_opp": p_opp,
        "poss_vs_oth": p_oth,
        "tov_vs_opp": int(to_opp),
        "tov_vs_oth": int(to_oth),
    }


def shrink(raw, n, k):
    w = n / (n + k)
    return 1 + w * (raw - 1), w


def main():
    df = pd.read_parquet(TG)
    os.makedirs(OUTDIR, exist_ok=True)

    NYK, SAS = "NYK", "SAS"

    # OFFENSIVE turnover-rate multipliers (each team's own off TO rate vs the opp)
    nyk = matchup_mult(df, NYK, SAS)   # NYK off TOs vs SAS
    sas = matchup_mult(df, SAS, NYK)   # SAS off TOs vs NYK

    n = min(nyk["n_games"], sas["n_games"])

    s_nyk, w_nyk = shrink(nyk["raw"], nyk["n_games"], K)
    s_sas, w_sas = shrink(sas["raw"], sas["n_games"], K)

    # ----- margin effect in pts/100 (NYK perspective) -----
    # Extra off-TOs per 100 poss = (rate_vs_opp - rate_vs_oth) * 100, SHRUNK.
    # Use shrunk rates: rate_eff = rate_oth * shrunk_mult.
    nyk_rate_eff = nyk["rate_vs_oth"] * s_nyk
    sas_rate_eff = sas["rate_vs_oth"] * s_sas
    nyk_extra_to_per100 = (nyk_rate_eff - nyk["rate_vs_oth"]) * 100.0
    sas_extra_to_per100 = (sas_rate_eff - sas["rate_vs_oth"]) * 100.0

    # A turnover is a possession yielding ~0 pts vs an expected ~1.10-1.15 pts.
    # Use a points-per-possession value for a lost possession. League PPP ~1.12.
    # We value a turnover at the team's own scoring value (lost) AND the
    # opponent often scores off the live-ball steal. Conservative: net value
    # of a turnover ~= 1.0 pts (lost possession ~1.12 minus the offense's TO
    # would-be-low-value chains, plus transition bump roughly cancels). We use
    # a single PPP_LOST that nets the swing.
    PPP_LOST = 1.10  # pts not scored on a turned-over possession

    # NYK extra TOs HURT NYK; SAS extra TOs HELP NYK.
    # net margin (NYK persp) = +(SAS extra TOs * PPP) - (NYK extra TOs * PPP)
    residual_pts_per100 = (sas_extra_to_per100 - nyk_extra_to_per100) * PPP_LOST

    notes = (
        "OFFENSIVE turnover rate (tov/poss) vs opp / vs others, poss-weighted, "
        "shrunk K=6. A team's off TO rate vs an opp is mostly the OPPONENT's "
        "ball-pressure defense -- the SAME generic opponent-defense the sim "
        "already applies (interior/perimeter D suppression + _matchup_mult on "
        "opp rim_d/perim_d). So this signal HEAVILY overlaps the sim's generic "
        "opp-D. On 4 H2H games both raws are noise-dominated (w~0.40). "
        "Recommend reject/shrink_more: it double-counts opponent defense and "
        "the residual is within sampling noise. "
        f"NYK off TO rate vs SAS {nyk['rate_vs_opp']:.4f} vs others "
        f"{nyk['rate_vs_oth']:.4f} (raw {nyk['raw']:.3f}); SAS off TO rate vs "
        f"NYK {sas['rate_vs_opp']:.4f} vs others {sas['rate_vs_oth']:.4f} "
        f"(raw {sas['raw']:.3f})."
    )

    result = {
        "signal": "turnover",
        "mechanic": "tov_share",
        "mult_nyk": round(s_nyk, 4),
        "mult_sas": round(s_sas, 4),
        "raw_nyk": round(nyk["raw"], 4),
        "raw_sas": round(sas["raw"], 4),
        "n_games": int(n),
        "residual_pts_per100": round(residual_pts_per100, 3),
        "notes": notes,
    }

    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)

    # ----- diagnostics -----
    print("=== TURNOVER MATCHUP SIGNAL (NYK vs SAS) ===")
    print("[offensive TO rate = tov/poss; raw = vs-opp / vs-others]")
    print()
    print("NYK (off TOs vs SAS):")
    print(f"  vs SAS:    n={nyk['n_games']} poss={nyk['poss_vs_opp']:.1f} "
          f"tov={nyk['tov_vs_opp']} rate={nyk['rate_vs_opp']:.4f}")
    print(f"  vs others: n={len(df[(df.team==NYK)&(df.opp!=SAS)])} "
          f"poss={nyk['poss_vs_oth']:.1f} tov={nyk['tov_vs_oth']} "
          f"rate={nyk['rate_vs_oth']:.4f}")
    print(f"  raw mult={nyk['raw']:.4f}  w={w_nyk:.3f}  shrunk={s_nyk:.4f}")
    print()
    print("SAS (off TOs vs NYK):")
    print(f"  vs NYK:    n={sas['n_games']} poss={sas['poss_vs_opp']:.1f} "
          f"tov={sas['tov_vs_opp']} rate={sas['rate_vs_opp']:.4f}")
    print(f"  vs others: n={len(df[(df.team==SAS)&(df.opp!=NYK)])} "
          f"poss={sas['poss_vs_oth']:.1f} tov={sas['tov_vs_oth']} "
          f"rate={sas['rate_vs_oth']:.4f}")
    print(f"  raw mult={sas['raw']:.4f}  w={w_sas:.3f}  shrunk={s_sas:.4f}")
    print()
    print(f"NYK extra off-TOs / 100 (shrunk): {nyk_extra_to_per100:+.3f}")
    print(f"SAS extra off-TOs / 100 (shrunk): {sas_extra_to_per100:+.3f}")
    print(f"PPP_LOST={PPP_LOST}")
    print(f"residual_pts_per100 (NYK persp): {residual_pts_per100:+.3f}")
    print()

    # cross-check using opp_tov column (defense view) for consistency
    # NYK forcing SAS TOs == SAS off tov vs NYK; verify via NYK rows opp_tov
    nyk_rows_vs_sas = df[(df.team == NYK) & (df.opp == SAS)]
    forced = nyk_rows_vs_sas["opp_tov"].sum()
    print(f"[cross-check] SAS TOs in H2H from NYK rows opp_tov: {forced} "
          f"vs from SAS rows tov: {sas['tov_vs_opp']}")
    print()
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
