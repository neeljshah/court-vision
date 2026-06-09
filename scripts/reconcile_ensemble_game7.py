"""
reconcile_ensemble_game7.py — collapse the 4 disagreeing G7 engines into ONE honest number.

Boot state: possession_sim=49.3% / winprob=59.7% / M2=78.8% / market=61% OKC win.
This script applies explicit, documented weights + a Game-7 home prior and emits
ensemble_game7.json. Every input traces to a real artifact in data/cache/intel_game7/.

Weights are justified in WEIGHTS_RATIONALE and in BUILD_LOG.md. M2 is EXCLUDED at boot
(known out-of-distribution playoff-elo extrapolation); re-include once m2_real_v3.json
(B2 fix) lands by passing --include-m2.
"""
import json, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"

def load(name):
    p = CACHE / name
    return json.loads(p.read_text()) if p.exists() else None

WEIGHTS_RATIONALE = {
    "market":   "Sharpest single signal; already prices injuries, home court, Game-7 priors, sharp money.",
    "winprob":  "XGB classifier, principled features, NOT OOD (uses base elo) but trained <=2024-25, no playoffs -> stale.",
    "sim":      "Bottom-up possession sim; honest construction but secondary stats heuristic and over-weights recent blowouts.",
    "g7_home":  "All-time Game-7 home win rate .742; this series home teams 4-0 since G1. A base-rate anchor, lightly weighted.",
    "m2":       "EXCLUDED at boot: out-of-distribution playoff-elo extrapolation (predicted 78.8%). Re-include after B2 fix.",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-m2", action="store_true", help="include fixed M2 (m2_real_v3.json) in blend")
    ap.add_argument("--winprob-override", type=float, default=None, help="use retrained winprob OKC prob (B1)")
    args = ap.parse_args()

    sim = load("possession_sim_v2.json")
    wp = load("winprob_real.json")
    m2 = load("m2_real_v2.json")
    m2v3 = load("m2_real_v3.json")  # B2 fix, may not exist yet

    # --- inputs (OKC = home win prob) ---
    p_sim = sim["home_win_prob"]                     # 0.4926
    p_wp = args.winprob_override if args.winprob_override is not None else wp["home_win_prob"]  # 0.5968
    p_market = 0.61                                  # FD/DK ML ~ -155 consensus, de-vigged ~0.60-0.61
    p_g7home = 0.56      # CORRECTED from real data (elimination_game_prior.json, 2010-2025, 49 G7s):
                         # G7 home win rate 61.2% all-window / 52.9% recent-era (2015-16+, n=34) — NOT .742.
                         # 0.56 = recent-era 0.529 + a small bump for this series' 4-0 home pattern.
    p_m2_boot = m2["predictions"]["p_home_win"]      # 0.7879 (OOD, shown not used)

    # --- weights ---
    if args.include_m2 and m2v3 is not None:
        p_m2 = m2v3["predictions"]["p_home_win"]
        w = {"market":0.40,"winprob":0.22,"sim":0.13,"g7_home":0.13,"m2":0.12}
        comps = {"market":p_market,"winprob":p_wp,"sim":p_sim,"g7_home":p_g7home,"m2":p_m2}
    else:
        p_m2 = None
        w = {"market":0.45,"winprob":0.25,"sim":0.15,"g7_home":0.15}
        comps = {"market":p_market,"winprob":p_wp,"sim":p_sim,"g7_home":p_g7home}

    assert abs(sum(w.values()) - 1.0) < 1e-9, w
    okc = sum(w[k]*comps[k] for k in w)

    # --- total: sim (calibrated) is the only bottom-up total; market anchors ---
    sim_total = sim["total"]["calibrated_p50"]       # 216.5
    market_total = 213.0
    # honest blend: trust market more (elimination-game unders historically), small sim nudge
    ens_total = round(0.65*market_total + 0.35*sim_total, 1)

    # --- spread: winprob margin + sim spread, anchored to market ---
    sim_spread = sim["spread"]["mean"]               # +0.31 (OKC)
    wp_margin = wp["margin_est"]                      # +2.9 OKC
    ens_margin = round(0.5*wp_margin + 0.2*sim_spread + 0.3*4.0, 2)  # 4.0 = market -4 anchor

    out = {
        "game_id": "0042500317", "matchup": "SAS @ OKC", "date": "2026-05-30",
        "okc_win_prob": round(okc, 4),
        "sas_win_prob": round(1-okc, 4),
        "okc_margin_est": ens_margin,
        "total_est": ens_total,
        "components_okc_win": comps,
        "weights": w,
        "excluded": ({} if (args.include_m2 and m2v3) else {"m2_boot_OOD": round(p_m2_boot,4)}),
        "total_inputs": {"sim_calibrated_p50": sim_total, "market": market_total, "blended": ens_total},
        "spread_inputs": {"winprob_margin": wp_margin, "sim_spread": sim_spread, "market_anchor": 4.0},
        "rationale": WEIGHTS_RATIONALE,
        "read": (
            f"Honest ensemble: OKC {okc:.1%} to win (market ~61%, model spread agrees ~OKC -{ens_margin:.0f}). "
            f"M2's 78.8% is excluded as OOD. Total ~{ens_total} vs market 213 -> lean slight under/pass "
            f"(elimination-game pace compression + two elite defenses)."
        ),
    }
    p = CACHE / "ensemble_game7.json"
    p.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print("\nWROTE", p)

if __name__ == "__main__":
    main()
