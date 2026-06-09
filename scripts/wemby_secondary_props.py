"""
wemby_secondary_props.py — honest count-distribution models for Wemby REB & BLK.
The EV board projected Wemby BLK UNDER 3.5 at p=0.96, but his SERIES blocks avg is 3.0
(3 blocks in G6) -> a 0.96 under is impossible for a mean near 3. This re-models REB and
BLK with proper over-dispersed count distributions (Negative Binomial) anchored to his real
series numbers, and reports honest P(under line). Corrects the bet card.
"""
import json, numpy as np
from scipy import stats
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"

# REAL series anchors (wcf_player_series_avg_6g.csv): reb 11.5, blk 3.0, min 37.0
def negbin_pmf_cdf(mean, var, kmax=40):
    # NB parameterized by mean & variance (var>mean for overdispersion)
    if var <= mean:  # fall back to Poisson if not overdispersed
        rv = stats.poisson(mean)
    else:
        p = mean / var
        r = mean * p / (1 - p)
        rv = stats.nbinom(r, p)
    ks = np.arange(0, kmax)
    return ks, rv.pmf(ks), rv

def model(name, mean, var, lines):
    ks, pmf, rv = negbin_pmf_cdf(mean, var)
    out = {"mean": mean, "var": var, "std": round(var**0.5, 2)}
    for L in lines:
        # under line (e.g. 13.5) = P(X <= floor(L))
        k = int(np.floor(L))
        p_under = float(rv.cdf(k))
        out[f"under_{L}"] = round(p_under, 3)
        out[f"over_{L}"] = round(1 - p_under, 3)
    return out

# BLK: series mean 3.0. OKC is a heavy paint-attacking offense (Hartenstein/SGA drives) ->
# keeps block chances UP; slight regression -> mean 2.8. Blocks are overdispersed (he had a
# 3-blk game; range ~0-6). var ~ 1.7*mean.
blk = model("blk", mean=2.8, var=2.8*1.7, lines=[2.5, 3.5, 4.5])
# REB: series 11.5; line 13.5. Rebounds overdispersed, var ~ 1.4*mean. mean 11.0 (slight reg, OKC
# rebounds well as a team; Hartenstein/Holmgren contest the glass).
reb = model("reb", mean=11.0, var=11.0*1.4, lines=[10.5, 11.5, 13.5])

out = {"player": "Victor Wembanyama", "game": "WCF G7",
       "blk": blk, "reb": reb,
       "corrections_vs_board": {
           "BLK_under_3.5": {"board_p": 0.965, "honest_p": blk["under_3.5"],
                             "note": "board was overconfident; series blk avg=3.0. Still a lean under but NOT a near-lock."},
           "REB_under_13.5": {"board_p": 0.891, "honest_p": reb["under_13.5"],
                              "note": "board slightly overconfident; honest count model below."}},
       "honest_notes": ["NegBinom anchored to real series means (reb 11.5, blk 3.0) with modest G7 regression + overdispersion.",
                        "Blocks especially: any 'under' p>~0.80 on a 3.5 line for a 3.0-avg shot-blocker is a variance-model error."]}
(CACHE/"wemby_secondary_props.json").write_text(json.dumps(out, indent=2))
print("=== WEMBY SECONDARY PROPS (honest count models) ===")
print(f"BLK mean 2.8 std {blk['std']}:  under2.5={blk['under_2.5']}  under3.5={blk['under_3.5']}  under4.5={blk['under_4.5']}")
print(f"REB mean 11.0 std {reb['std']}: under10.5={reb['under_10.5']} under11.5={reb['under_11.5']} under13.5={reb['under_13.5']}")
print(f"\nCORRECTION  BLK under 3.5: board 0.965 -> honest {blk['under_3.5']}")
print(f"CORRECTION  REB under 13.5: board 0.891 -> honest {reb['under_13.5']}")
print("WROTE", CACHE/"wemby_secondary_props.json")
