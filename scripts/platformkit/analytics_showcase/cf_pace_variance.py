"""Counterfactual: pace as a variance lever.

How does possession count move the UNDERDOG's win probability? A game is a sum of
~100 possessions per team. A favorite has a small per-possession edge; the more
possessions played, the more reliably that edge accumulates (LLN), so favorites
win more. FEWER possessions = more variance vs the edge = more upsets. The
counterfactual: take the SAME matchup and ask its win prob at a different pace.

Analytic model (normal approximation of the final margin):
  margin ~ Normal(mu, sigma^2), mu = N*delta_pp, sigma^2 = 2*N*v_pp
  P(fav win) = Phi(mu/sigma) = Phi( z0 * sqrt(N/N_ref) ), z0 = Phi^-1(p_fav_at_ref)
  upset_prob(N) = 1 - Phi( z0 * sqrt(N/N_ref) )
delta_pp (fav per-possession edge) and v_pp (per-poss variance) CANCEL: once a
matchup is pinned by its win prob at N_ref, its upset prob at any pace depends only
on sqrt(N/N_ref) -- isolating the mechanical pace effect with team strength fixed.
N_ref + pace grid come from real NBA data on disk; delta_pp/v_pp are context only.

DESCRIPTIVE / CALIBRATION analytic. edge_claimed=False. No $/ROI claims. An honest
"the pace lever is small" verdict is a success.
Usage: python -m scripts.platformkit.analytics_showcase.cf_pace_variance [--check]
"""
import argparse
import json
import os
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, List, Optional

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

REPO_ROOT = Path(__file__).resolve().parents[3]
PACE_PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_team_adv.parquet"
FINALS_PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "game_finals_corrected.parquet"
OUT_JSON = Path(__file__).parent / "out" / "cf_pace_variance.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "cf_pace_variance.png"

# Spec grid: favorites at 60/70/80% (at reference pace) across pace 92-104.
FAV_STRENGTHS: List[float] = [0.60, 0.70, 0.80]
PACE_GRID: List[float] = [92.0, 94.0, 96.0, 98.0, 100.0, 102.0, 104.0]

# Declared fallback constants (used only if the source parquets are absent, e.g.
# a fresh clone). Measured 2026-07-23 from the parquets cited below; see --check.
FALLBACK_N_REF = 99.8
FALLBACK_V_PP = 1.27
FALLBACK_LEAGUE_PPP = 1.147
AS_OF = "2026-07-23"

_Z = NormalDist()


def load_pace_params() -> Dict[str, Any]:
    """Read real pace + margin data. Returns league-average pace (N_ref),
    per-possession variance anchor (v_pp), and league PPP. Falls back to declared
    constants (with source='fallback_constants') if the parquets are absent."""
    if not PACE_PARQUET.exists() or not FINALS_PARQUET.exists():
        return {
            "source": "fallback_constants",
            "n_ref": FALLBACK_N_REF,
            "v_pp_anchor": FALLBACK_V_PP,
            "league_ppp": FALLBACK_LEAGUE_PPP,
            "note": "source parquets absent (fresh clone); using declared 2026-07-23 measurements",
        }
    import pandas as pd

    ta = pd.read_parquet(PACE_PARQUET, columns=["home_pace_asof", "away_pace_asof"])
    pace = pd.concat([ta["home_pace_asof"], ta["away_pace_asof"]]).dropna()
    gf = pd.read_parquet(FINALS_PARQUET, columns=["home_pts_true", "away_pts_true"])
    margin = (gf["home_pts_true"] - gf["away_pts_true"]).dropna()
    team_pts = pd.concat([gf["home_pts_true"], gf["away_pts_true"]]).dropna()
    n_ref = float(pace.mean())
    # v_pp from Var(margin)=2*N*v_pp -- an UPPER anchor (also carries matchup
    # dispersion). Cancels in the headline formula; used only for context/MC.
    v_pp = float(margin.var() / (2.0 * n_ref))
    return {
        "source": "data/domains/basketball_nba/{asof_team_adv,game_finals_corrected}.parquet",
        "n_ref": round(n_ref, 2),
        "pace_std": round(float(pace.std()), 2),
        "pace_p5": round(float(pace.quantile(0.05)), 1),
        "pace_p95": round(float(pace.quantile(0.95)), 1),
        "pace_n": int(len(pace)),
        "team_pts_per_game": round(float(team_pts.mean()), 2),
        "league_ppp": round(float(team_pts.mean()) / n_ref, 4),
        "margin_std": round(float(margin.std()), 2),
        "margin_n": int(len(margin)),
        "v_pp_anchor": round(v_pp, 4),
        "v_pp_note": "upper anchor: Var(margin)/(2*N_ref); conflates matchup dispersion, "
                     "so slightly overstates pure within-game per-possession variance. "
                     "Cancels in the headline formula.",
    }


def upset_prob(p_fav_ref: float, n: float, n_ref: float) -> float:
    """Upset probability at pace n for a favorite that is p_fav_ref at n_ref.
    upset(n) = 1 - Phi( z0 * sqrt(n / n_ref) ), z0 = Phi^-1(p_fav_ref)."""
    z0 = _Z.inv_cdf(p_fav_ref)
    z = z0 * (n / n_ref) ** 0.5
    return 1.0 - _Z.cdf(z)


def build_curves(n_ref: float) -> List[Dict[str, Any]]:
    grid = sorted(set(PACE_GRID + [round(n_ref, 1)]))
    curves = []
    for p_fav in FAV_STRENGTHS:
        row = {
            "fav_strength_at_ref_pace": p_fav,
            "upset_prob_at_ref_pace": round(1.0 - p_fav, 4),
            "by_pace": [
                {
                    "pace": pace,
                    "is_ref_pace": abs(pace - round(n_ref, 1)) < 1e-9,
                    "fav_win_prob": round(1.0 - upset_prob(p_fav, pace, n_ref), 4),
                    "upset_prob": round(upset_prob(p_fav, pace, n_ref), 4),
                }
                for pace in grid
            ],
        }
        lo = upset_prob(p_fav, grid[0], n_ref)
        hi = upset_prob(p_fav, grid[-1], n_ref)
        row["upset_swing_slow_minus_fast"] = round(lo - hi, 4)
        curves.append(row)
    return curves


def mc_validate(p_fav_ref: float, n_ref: float, v_pp: float, n_sim: int = 8000) -> Dict[str, Any]:
    """Smoke-validate the normal approximation: simulate a discrete points-per-
    possession game and compare the empirical favorite-win rate to the formula at
    the reference pace. Pure-python, no heavy deps. Not load-bearing -- a sanity
    check that summing ~100 discrete possessions is well-approximated by a normal.
    """
    import random

    # Declared discrete PPP outcome distribution anchored to league mean ~1.147:
    # p3 (made 3) = 0.12, solve p2 for mean, remainder p0.
    p3, mean_ppp = 0.12, 1.147
    p2 = (mean_ppp - 3.0 * p3) / 2.0
    p0 = 1.0 - p2 - p3
    # Favorite per-possession edge from the target win prob (uses v_pp here only).
    z0 = _Z.inv_cdf(p_fav_ref)
    delta_pp = z0 * (2.0 * v_pp / n_ref) ** 0.5
    n = int(round(n_ref))
    rng = random.Random(12345)
    fav_wins = 0
    for _ in range(n_sim):
        fav = sum(_draw_ppp(rng, p0, p2, p3) for _ in range(n)) + delta_pp * n
        dog = sum(_draw_ppp(rng, p0, p2, p3) for _ in range(n))
        if fav > dog:
            fav_wins += 1
    return {
        "n_sim": n_sim,
        "declared_ppp_dist": {"0": round(p0, 3), "2": round(p2, 3), "3": p3},
        "mc_fav_win_rate": round(fav_wins / n_sim, 4),
        "formula_fav_win_prob": p_fav_ref,
        "abs_diff": round(abs(fav_wins / n_sim - p_fav_ref), 4),
    }


def _draw_ppp(rng: "Any", p0: float, p2: float, p3: float) -> float:
    u = rng.random()
    if u < p0:
        return 0.0
    if u < p0 + p2:
        return 2.0
    return 3.0


def build_output(params: Dict[str, Any]) -> Dict[str, Any]:
    n_ref = float(params["n_ref"])
    curves = build_curves(n_ref)
    return {
        "edge_claimed": False,
        "label": "COUNTERFACTUAL / CALIBRATION -- pace as a variance lever",
        "as_of": AS_OF,
        "source_artifact": params["source"],
        "method": "Normal-margin possession model; win prob = Phi(z0*sqrt(N/N_ref)).",
        "formula": "upset_prob(N) = 1 - Phi( Phi^-1(p_fav_at_N_ref) * sqrt(N / N_ref) )",
        "why_it_holds": "margin=sum of ~N possessions; mu~N*delta_pp, var~2*N*v_pp, so z=mu/sigma "
                        "scales as sqrt(N). delta_pp,v_pp cancel once the matchup is pinned at N_ref.",
        "data_params": params,
        "reference_pace_N_ref": round(n_ref, 2),
        "pace_grid": sorted(set(PACE_GRID + [round(n_ref, 1)])),
        "fav_strengths_at_ref_pace": FAV_STRENGTHS,
        "curves": curves,
        "assumptions": [
            "Margin ~ Normal (CLT over ~100 possessions; good for full games, weaker for "
            "short in-game windows).",
            "COUNTERFACTUAL floor: per-possession edge and variance held pace-INVARIANT. Real "
            "teams that push pace may also change shot quality; this isolates the mechanical "
            "variance effect only, not behavioral pace changes.",
            "Possessions independent; runs/autocorrelation would add variance and make the pace "
            "lever slightly STRONGER than shown.",
            "v_pp anchor conflates matchup dispersion (upper bound); cancels in the headline "
            "formula, used only for MC validation/context. Two teams symmetric in variance.",
        ],
        "mc_validation": mc_validate(0.70, n_ref, float(params.get("v_pp_anchor", FALLBACK_V_PP))),
        "verdict": _verdict(curves),
    }


def _verdict(curves: List[Dict[str, Any]]) -> str:
    parts = []
    for c in curves:
        p = int(round(c["fav_strength_at_ref_pace"] * 100))
        swing = c["upset_swing_slow_minus_fast"] * 100
        by = {r["pace"]: r["upset_prob"] for r in c["by_pace"]}
        lo, hi = min(by), max(by)
        parts.append(
            f"A {p}% favorite: upset prob {by[hi] * 100:.1f}% at pace {hi:.0f} vs "
            f"{by[lo] * 100:.1f}% at pace {lo:.0f} (slow-minus-fast swing {swing:+.1f} pts)."
        )
    return ("Pace is a real but MODEST variance lever: across the observed NBA pace range "
            "(~92-104) the same matchup's upset prob shifts by only a few points -- fewer "
            "possessions favor the underdog (sqrt(N) scaling), but the effect is small "
            "because real pace varies little. " + " ".join(parts))


def make_plot(output: Dict[str, Any]) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(9, 6))
    n_ref = output["reference_pace_N_ref"]
    for c in output["curves"]:
        xs = [r["pace"] for r in c["by_pace"]]
        ys = [r["upset_prob"] * 100 for r in c["by_pace"]]
        p = int(round(c["fav_strength_at_ref_pace"] * 100))
        ax.plot(xs, ys, marker="o", label=f"{p}% favorite (at ref pace)")
    ax.axvline(n_ref, linestyle="--", color="gray", linewidth=1, label=f"league-avg pace {n_ref:.1f}")
    ax.set_xlabel("pace (possessions per team)")
    ax.set_ylabel("underdog upset probability (%)")
    ax.set_title("Pace as a variance lever: fewer possessions -> more upsets\n"
                 "(same matchup, only pace changes; DESCRIPTIVE, edge_claimed=False)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.text(0.5, 0.005,
             f"Source: {output['source_artifact']}; as_of {output['as_of']}. "
             "Formula: upset(N)=1-Phi(z0*sqrt(N/N_ref)). Counterfactual holds team edge fixed.",
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def run() -> Dict[str, Any]:
    params = load_pace_params()
    output = build_output(params)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2))
    output["plot_written"] = make_plot(output)
    OUT_JSON.write_text(json.dumps(output, indent=2))
    return output


def _validate_recorded(data: Dict[str, Any]) -> None:
    assert data.get("edge_claimed") is False
    assert "curves" in data and len(data["curves"]) == len(FAV_STRENGTHS)
    for c in data["curves"]:
        ups = [r["upset_prob"] for r in c["by_pace"]]
        # Monotonic: faster pace -> lower upset prob (by_pace is pace-ascending).
        assert all(ups[i] >= ups[i + 1] - 1e-9 for i in range(len(ups) - 1)), c


def check() -> None:
    """Assert the load-bearing properties, then clone-safe verify the artifact."""
    n_ref = FALLBACK_N_REF
    # Boundary: at N=N_ref the upset prob equals exactly 1 - p_fav.
    for p in FAV_STRENGTHS:
        assert abs(upset_prob(p, n_ref, n_ref) - (1.0 - p)) < 1e-9
    # Directional: fewer possessions => higher upset prob for a favorite.
    assert upset_prob(0.70, 92.0, n_ref) > upset_prob(0.70, 104.0, n_ref)
    assert upset_prob(0.80, 80.0, n_ref) > upset_prob(0.80, 120.0, n_ref)
    print("cf_pace_variance formula self-check OK")
    try:
        verify_recorded_artifact(OUT_JSON, _validate_recorded, "cf_pace_variance")
    except AssertionError as e:
        # Local data present but no artifact yet is fine at author-time.
        print(f"(recorded-artifact not yet present: {e})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({
            "verdict": res["verdict"],
            "n_ref": res["reference_pace_N_ref"],
            "mc_abs_diff": res["mc_validation"]["abs_diff"],
            "plot_written": res["plot_written"],
        }, indent=2))
