"""Monte Carlo simulator for tonight's NBA props (2026-05-26 OKC vs SAS, Game 5 WCF).

V1 scope: independent per-player Normal samples shrunk toward series average.
Uses 1000 sims, computes empirical P(over)/P(under) for each posted Pin line,
joint event probabilities, and per-prop divergence vs simple normal-approx.

Inputs:
  - data/cache/intel_2026-05-26/slate_fresh_2026-05-26.parquet (q10/q50/q90/sigma)
  - data/lines/2026-05-26_pin.csv (posted lines)
  - data/cache/intel_2026-05-26/wcf_player_series_avg.csv (series ground truth)
  - data/cache/intel_2026-05-26/m2_game.json (team forecast)

Output: data/cache/intel_2026-05-26/mc_tonight.json

TODO: Add team-total correlation (when SGA scores a lot, OKC tends to win) via
copula on player-pts -> team-pts -> p_okc_wins.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ---------- config ----------
DATE = "2026-05-26"
N_SIMS = 1000
SHRINK_MODEL = 0.6  # weight on q50_model
SHRINK_SERIES = 0.4  # weight on series_avg
SEED = 20260526

INTEL = Path(f"data/cache/intel_{DATE}")
LINES = Path(f"data/lines/{DATE}_pin.csv")
SLATE = INTEL / f"slate_fresh_{DATE}.parquet"
SERIES = INTEL / "wcf_player_series_avg.csv"
TEAM_AGG = INTEL / "wcf_team_series_agg.json"
M2 = INTEL / "m2_game.json"
OUT = INTEL / "mc_tonight.json"


# ---------- helpers ----------
def american_to_prob(odds: float) -> float:
    if pd.isna(odds):
        return float("nan")
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def normal_p_over(line: float, mu: float, sigma: float) -> float:
    """Simple normal-approx P(stat > line)."""
    if sigma <= 0:
        return 1.0 if mu > line else 0.0
    return float(1.0 - stats.norm.cdf(line, loc=mu, scale=sigma))


def sigma_fallback(row: pd.Series) -> float:
    """Use given sigma; otherwise infer from q90-q10 gap."""
    s = row.get("sigma")
    if pd.notna(s) and s > 0:
        return float(s)
    q90 = row.get("q90")
    q10 = row.get("q10")
    if pd.notna(q90) and pd.notna(q10) and q90 > q10:
        return float((q90 - q10) / (2 * 1.2816))  # 80% CI gap
    return 1.0  # last-resort floor


# ---------- main ----------
def main() -> None:
    rng = np.random.default_rng(SEED)

    slate = pd.read_parquet(SLATE)
    lines = pd.read_csv(LINES)
    series = pd.read_csv(SERIES)
    with open(M2) as fh:
        m2 = json.load(fh)
    with open(TEAM_AGG) as fh:
        team_agg = json.load(fh)

    # Keep latest snapshot per (player, stat, line)
    lines = lines.sort_values("captured_at").drop_duplicates(
        subset=["player_name", "stat", "line"], keep="last"
    )

    # Filter active players only
    slate_active = slate[slate["status"] == "OK"].copy()

    # Series avg map: (player_name, stat) -> avg
    stat_to_col = {
        "pts": "pts_pg", "reb": "reb_pg", "ast": "ast_pg", "fg3m": "fg3m_pg",
        "stl": "stl_pg", "blk": "blk_pg", "tov": "tov_pg",
    }
    series_map: dict[tuple[str, str], float] = {}
    for _, r in series.iterrows():
        for stat, col in stat_to_col.items():
            if col in r and pd.notna(r[col]):
                series_map[(r["player_name"], stat)] = float(r[col])

    # ---------- Simulate per-player-stat samples ----------
    sims: dict[tuple[str, str], np.ndarray] = {}
    mu_used: dict[tuple[str, str], float] = {}
    sigma_used: dict[tuple[str, str], float] = {}

    for _, row in slate_active.iterrows():
        player = row["player"]
        stat = row["stat"]
        q50 = float(row["q50"])
        sig = sigma_fallback(row)
        series_avg = series_map.get((player, stat), q50)  # fall back to model

        mu = SHRINK_MODEL * q50 + SHRINK_SERIES * series_avg
        samples = rng.normal(loc=mu, scale=sig, size=N_SIMS)
        samples = np.clip(samples, 0, None)  # stats are non-negative

        # Integerize counting stats (helps with discrete prop lines)
        # Keep float to preserve sub-line resolution; round only when comparing
        sims[(player, stat)] = samples
        mu_used[(player, stat)] = mu
        sigma_used[(player, stat)] = sig

    # ---------- Per-prop empirical probabilities ----------
    prop_results: list[dict] = []
    for _, ln in lines.iterrows():
        player = ln["player_name"]
        stat = ln["stat"]
        line = float(ln["line"])
        key = (player, stat)
        if key not in sims:
            continue

        s = sims[key]
        # Standard sportsbook rule: stat > line for OVER (lines like 2.5 avoid push)
        p_over_mc = float((s > line).mean())
        p_under_mc = 1.0 - p_over_mc

        mu = mu_used[key]
        sig = sigma_used[key]
        p_over_norm = normal_p_over(line, mu, sig)
        p_under_norm = 1.0 - p_over_norm

        prop_results.append({
            "player": player,
            "stat": stat,
            "line": line,
            "over_price": float(ln["over_price"]) if pd.notna(ln["over_price"]) else None,
            "under_price": float(ln["under_price"]) if pd.notna(ln["under_price"]) else None,
            "mu_shrunk": round(mu, 4),
            "sigma": round(sig, 4),
            "p_over_mc": round(p_over_mc, 4),
            "p_under_mc": round(p_under_mc, 4),
            "p_over_norm": round(p_over_norm, 4),
            "p_under_norm": round(p_under_norm, 4),
            "divergence_over": round(p_over_mc - p_over_norm, 4),
            "ci80_low": round(float(np.quantile(s, 0.10)), 3),
            "ci80_high": round(float(np.quantile(s, 0.90)), 3),
            "ci95_low": round(float(np.quantile(s, 0.025)), 3),
            "ci95_high": round(float(np.quantile(s, 0.975)), 3),
        })

    prop_df = pd.DataFrame(prop_results)

    # ---------- Joint events ----------
    joints: dict[str, dict] = {}

    # Helper: get sim array or None
    def g(player: str, stat: str) -> np.ndarray | None:
        return sims.get((player, stat))

    # P(SGA 30+ PTS)
    sga_pts = g("Shai Gilgeous-Alexander", "pts")
    if sga_pts is not None:
        joints["P(SGA_pts_ge_30)"] = {
            "value": round(float((sga_pts >= 30).mean()), 4),
            "interpretation": "Probability SGA scores 30+ tonight (model alone).",
        }

    # P(OKC wins) — using M2's p_home_win as marginal, but build correlated:
    # crude proxy: assume OKC wins more often when SGA scores a lot.
    # Use M2 baseline p_okc_win, then condition empirically by SGA pts bucket.
    p_okc_baseline = float(m2["predictions"]["p_home_win"])

    # Build a correlated OKC-win indicator: rank-based. Higher SGA pts -> higher
    # win prob. Use Gaussian copula with rho=0.45 (heuristic NBA prop correlation).
    rho = 0.45
    u_sga = stats.norm.ppf(stats.rankdata(sga_pts) / (len(sga_pts) + 1))
    z = rng.normal(size=N_SIMS)
    u_win_latent = rho * u_sga + np.sqrt(1 - rho**2) * z
    win_thresh = stats.norm.ppf(p_okc_baseline)
    okc_wins = u_win_latent > -win_thresh  # higher latent -> more likely win

    # Recalibrate to match p_okc_baseline exactly
    target_wins = int(round(p_okc_baseline * N_SIMS))
    top_idx = np.argsort(u_win_latent)[-target_wins:]
    okc_wins = np.zeros(N_SIMS, dtype=bool)
    okc_wins[top_idx] = True

    joints["P(SGA_30plus_AND_OKC_wins)"] = {
        "value": round(float(((sga_pts >= 30) & okc_wins).mean()), 4),
        "interpretation": (
            f"Joint: SGA 30+ PTS AND OKC wins. Built via rank-copula (rho={rho}) "
            "between SGA pts and OKC win indicator, calibrated to M2 p_home_win="
            f"{p_okc_baseline:.3f}."
        ),
    }
    joints["P(SGA_pts_ge_30_given_OKC_wins)"] = {
        "value": (
            round(float((sga_pts[okc_wins] >= 30).mean()), 4) if okc_wins.any() else None
        ),
        "interpretation": "Conditional: SGA 30+ given OKC wins (the copula effect).",
    }

    # P(Wemby triple-double: 10+ pts AND 10+ reb AND 10+ ast)
    wp = g("Victor Wembanyama", "pts")
    wr = g("Victor Wembanyama", "reb")
    wa = g("Victor Wembanyama", "ast")
    if wp is not None and wr is not None and wa is not None:
        td = (wp >= 10) & (wr >= 10) & (wa >= 10)
        joints["P(Wemby_triple_double)"] = {
            "value": round(float(td.mean()), 4),
            "p_10_pts": round(float((wp >= 10).mean()), 4),
            "p_10_reb": round(float((wr >= 10).mean()), 4),
            "p_10_ast": round(float((wa >= 10).mean()), 4),
            "interpretation": (
                "Joint independence assumption (no correlation between Wemby's "
                "categories). True P likely lower because counting stats are "
                "positively correlated via minutes/usage."
            ),
        }

    # P(Holmgren 0 PTS in Q1) — proxy: assume per-quarter pts ~ N(mu/4, sigma/2)
    # then P(Q1 pts ~ 0) via clipped sample (since stats are non-negative)
    holm = g("Chet Holmgren", "pts")
    if holm is not None:
        # Approximate Q1 contribution: a quarter of game-total, with wider relative noise
        mu_q1 = mu_used[("Chet Holmgren", "pts")] / 4.0
        sig_q1 = sigma_used[("Chet Holmgren", "pts")] / 2.0  # less variance reduction than sqrt(4)
        q1_samples = rng.normal(loc=mu_q1, scale=sig_q1, size=N_SIMS)
        q1_samples = np.clip(q1_samples, 0, None)
        # Treat <0.5 as "scored 0" (since pts are integers)
        joints["P(Holmgren_0_pts_Q1)"] = {
            "value": round(float((q1_samples < 0.5).mean()), 4),
            "interpretation": (
                "Proxy: Q1 pts ~ Normal(mu/4, sigma/2) clipped at 0, count < 0.5 "
                "as 'scored zero'. Uses no actual per-period model."
            ),
        }

    # P(OKC wins | total > 220)
    # Build team-total samples from M2: total_pts ~ Normal(201, 12.5) (rough)
    # M2 says total=211 with the actual scoreline distribution.
    # Use M2 mean + an implied sigma from its over_215 prob.
    total_mu = m2["predictions"]["total_pts"]
    # over_215 = 0.1031 -> P(Z > (215-mu)/sig) = 0.1031 -> Z = 1.265
    total_sigma = (215 - total_mu) / 1.265
    if total_sigma <= 0:
        total_sigma = 12.0
    total_samples = rng.normal(loc=total_mu, scale=total_sigma, size=N_SIMS)

    # Correlate total with okc_wins very loosely (assume independent)
    high_total = total_samples > 220
    if high_total.any():
        joints["P(OKC_wins_given_total_gt_220)"] = {
            "value": round(float(okc_wins[high_total].mean()), 4),
            "p_total_gt_220_marginal": round(float(high_total.mean()), 4),
            "interpretation": (
                "Conditional P(OKC win) when total > 220. Assumes total independent "
                "of win indicator; reality: high totals slightly favor home team."
            ),
        }
    else:
        joints["P(OKC_wins_given_total_gt_220)"] = {
            "value": None,
            "p_total_gt_220_marginal": round(float(high_total.mean()), 4),
            "interpretation": "No simulated games totaled > 220 — M2 forecasts a slow game.",
        }

    # ---------- Divergence summary ----------
    prop_df["abs_div"] = prop_df["divergence_over"].abs()
    top_div = prop_df.nlargest(5, "abs_div")[
        ["player", "stat", "line", "p_over_mc", "p_over_norm", "divergence_over"]
    ]

    # ---------- Write output ----------
    payload = {
        "meta": {
            "date": DATE,
            "n_sims": N_SIMS,
            "shrink_model": SHRINK_MODEL,
            "shrink_series": SHRINK_SERIES,
            "seed": SEED,
            "okc_baseline_p_win": p_okc_baseline,
            "total_mu": round(total_mu, 2),
            "total_sigma": round(total_sigma, 2),
            "copula_rho_sga_okcwin": rho,
        },
        "props": prop_results,
        "joint_events": joints,
        "top_divergence": top_div.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(payload, indent=2))

    # ---------- Print summary ----------
    print(f"Wrote {OUT}")
    print(f"Simulated {len(sims)} (player,stat) pairs x {N_SIMS} sims")
    print(f"Priced {len(prop_results)} posted Pin lines\n")

    print("=== Top 5 props by MC-vs-Normal divergence ===")
    print(top_div.to_string(index=False))

    print("\n=== Joint events ===")
    for name, payload in joints.items():
        val = payload.get("value")
        print(f"  {name}: {val}")

    # Tie back to V3 high-conviction picks
    high_conv = pd.read_csv(INTEL / "ev_final_high_conviction.csv")
    print("\n=== V3 high-conviction picks: normal_p vs MC_p ===")
    for _, hc in high_conv.iterrows():
        key = (hc["player"], hc["stat"])
        if key not in sims:
            continue
        s = sims[key]
        line = float(hc["line"])
        side = str(hc["side"])
        if side == "OVER":
            mc_p = float((s > line).mean())
        else:
            mc_p = float((s < line).mean())
        norm_p = float(hc["model_p"])
        print(
            f"  {hc['player']:24s} {hc['stat']:5s} {side:5s} {line:>5.1f}  "
            f"norm={norm_p:.4f}  mc={mc_p:.4f}  delta={mc_p - norm_p:+.4f}"
        )


if __name__ == "__main__":
    main()
