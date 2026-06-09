"""
parlay_joint_mc.py — correlation-aware same-game-parlay pricing off the CORRECTED showcases.
The possession sim's joint_events use uncorrected seeds (SGA 26.8 not 23.9). This Gaussian-copula
joint MC ties the corrected showcase distributions together via a shared game-script latent so
same-game parlays (and the Wemby>SGA duel) are priced on the honest marginals.
Correlations are explicit/labelled priors.
"""
import json, numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"
RNG = np.random.default_rng(20260530)
N = 300_000

wem = json.loads((CACHE/"wemby_points_showcase.json").read_text())["distribution"]
sga = json.loads((CACHE/"sga_points_showcase.json").read_text())["distribution"]
allp = json.loads((CACHE/"all_player_showcases.json").read_text())

def med_std(name, fallback_med, fallback_std):
    # pull from all_player_showcases if present
    for k, v in allp.items() if isinstance(allp, dict) else []:
        pass
    return fallback_med, fallback_std

# marginals (median, std) from corrected showcases
PLAYERS = {
    "Wemby_pts": (wem["median"], wem["std"], "SAS"),
    "SGA_pts":   (sga["median"], sga["std"], "OKC"),
    "Harper_pts": (12.7, 4.6, "SAS"),
    "Holmgren_pts": (10.5, 5.0, "OKC"),
}
# shared latents: Z_script (blowout/pace, affects everyone's minutes), Z_sas, Z_okc (team offense)
# correlation of each player's points to the latents (labelled priors)
LOAD = {  # (script_pull, own_team_offense)
    "Wemby_pts": (-0.20, 0.55),   # blowout cuts his min (neg); rises with SAS offense
    "SGA_pts":   (-0.18, 0.55),
    "Harper_pts": (-0.15, 0.45),
    "Holmgren_pts": (-0.15, 0.45),
}
TEAM = {"SAS": "Z_sas", "OKC": "Z_okc"}

z_script = RNG.standard_normal(N)
z_sas = RNG.standard_normal(N)
z_okc = RNG.standard_normal(N)
zt = {"Z_sas": z_sas, "Z_okc": z_okc}
# OKC win latent: OKC offense up & SAS offense down -> OKC win more likely; calibrate to 60.9%
win_score = 0.6*z_okc - 0.5*z_sas + RNG.standard_normal(N)*0.6
okc_win = win_score > np.quantile(win_score, 0.391)   # 60.9% OKC

draws = {}
for p, (med, std, team) in PLAYERS.items():
    a, b = LOAD[p]
    z_team = zt[TEAM[team]]
    common = a*z_script + b*z_team
    idio = np.sqrt(max(0.0, 1 - (a*a + b*b))) * RNG.standard_normal(N)
    z = common + idio
    draws[p] = med + std * z

def P(mask): return round(float(mask.mean()), 3)

results = {
    "marginals_check": {p: {"median": round(float(np.median(draws[p])),1),
                            "std": round(float(draws[p].std()),1)} for p in draws},
    "okc_win_rate_check": P(okc_win),
    "duel": {
        "P(Wemby > SGA pts)": P(draws["Wemby_pts"] > draws["SGA_pts"]),
        "P(Wemby>SGA & SAS win)": P((draws["Wemby_pts"] > draws["SGA_pts"]) & (~okc_win)),
        "note": "SAS is 3-0 in series when Wemby outscores SGA; this prices the correlated combo on honest marginals.",
    },
    "same_game_parlays": {
        "Wemby u27.5 & SGA u27.5": P((draws["Wemby_pts"]<27.5) & (draws["SGA_pts"]<27.5)),
        "Wemby o27.5 & SAS win": P((draws["Wemby_pts"]>27.5) & (~okc_win)),
        "SGA u26.5 & OKC win": P((draws["SGA_pts"]<26.5) & (okc_win)),
        "Harper o9.5 & Wemby o25": P((draws["Harper_pts"]>9.5) & (draws["Wemby_pts"]>25)),
    },
}
# fair odds helper
def fair(p):
    if p<=0 or p>=1: return "—"
    return f"+{round((1-p)/p*100)}" if p<0.5 else f"-{round(p/(1-p)*100)}"
results["fair_odds"] = {k: fair(v) for k,v in results["same_game_parlays"].items()}
results["fair_odds"]["P(Wemby>SGA & SAS win)"] = fair(results["duel"]["P(Wemby>SGA & SAS win)"])
results["correlations_used"] = {"script_pull": "blowout cuts minutes (neg, shared)",
    "team_offense_load": "0.45-0.55 to own team", "okc_win": "0.6*Z_okc - 0.5*Z_sas, calibrated to 60.9%"}
(CACHE/"parlay_joint_mc.json").write_text(json.dumps(results, indent=2))

print("=== CORRELATION-AWARE SGP (corrected marginals) ===")
print("okc_win check:", results["okc_win_rate_check"], "(target 0.391 SAS / 0.609 OKC)")
print("marginals:", {p:results['marginals_check'][p]['median'] for p in draws})
print("\nDUEL: P(Wemby>SGA) =", results["duel"]["P(Wemby > SGA pts)"],
      "| P(Wemby>SGA & SAS win) =", results["duel"]["P(Wemby>SGA & SAS win)"], "fair", results["fair_odds"]["P(Wemby>SGA & SAS win)"])
print("\nSGPs:")
for k,v in results["same_game_parlays"].items():
    print(f"  {k:32s} {v:.3f}  fair {results['fair_odds'][k]}")
print("\nWROTE", CACHE/"parlay_joint_mc.json")
