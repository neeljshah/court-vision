"""Market convergence: do the model and the market AGREE more, and does
predictive uncertainty COLLAPSE, as a game progresses?

Companion to info_arrival_curve.py. That module measures each forecaster's
Brier gap to the OUTCOME by game-time checkpoint. This one is outcome-free: it
tracks two properties of the forecasts THEMSELVES per checkpoint --

  * gap  = mean |model_prob - market_prob|  (disagreement between the two
           estimators; does it narrow, widen, or stay flat over game time?)
  * entropy = mean Bernoulli entropy H(p) in bits, for the market prob and the
           model prob (predictive sharpness; how fast does uncertainty resolve?)

Inputs (reused, field-selective): info_arrival_curve.load_rows reads only
model_prob / market_prob / outcome / state_summary out of
data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl and parses the
inning (mlb) / 5-min bucket (soccer_intl) checkpoint. We consume its rows and
IGNORE the outcome -- gap and entropy are properties of the forecast pair, not
of the result.

SCOPE / FLOORS (declared, not tuned):
  * A checkpoint is reported only at n >= MIN_N (=30) rows. info_arrival_curve
    uses n>=5; we are deliberately more conservative for a stable mean.
  * Entropy in bits (log2): 1.0 = max uncertainty at p=0.5, 0.0 = certain.
  * Single-fold June-July 2026 corpus; no CIs; single reads are not durable.
  * Input globs are read relative to cwd via the reused loader, so run from the
    repo root (the `python -m ...` executor does).

HONEST FRAMING: entropy decaying toward 0 late in a game is EXPECTED (scores
diverge -> p -> 0/1), not a discovery -- it is reported as context. The
descriptive point of interest is whether the model-market gap narrows as public
information accumulates. DESCRIPTIVE_ONLY, edge_claimed=False. No $/ROI/edge
claim -- truth source docs/JOB_EVIDENCE_PACKET.md, .claude/rules/no-edge-claims.md.

NOVELTY: standard instrument. Agreement between two probabilistic forecasters
and Shannon-entropy decay over event time are textbook descriptive measures;
the only contribution is applying them to the MLB/soccer_intl joined corpora we
hold. Do not claim a new method.
"""
import argparse
import json
import math
import os
from collections import defaultdict
from statistics import mean, median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:  # package-qualified (python -m ...) with bare-script fallback
    from scripts.platformkit.analytics_showcase.info_arrival_curve import load_rows, CORPORA
except ImportError:  # pragma: no cover - bare-script invocation from the showcase dir
    from info_arrival_curve import load_rows, CORPORA

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "market_convergence.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "market_convergence.png")
MIN_N = 30  # declared floor: rows per checkpoint to report


def binary_entropy(p):
    """Shannon entropy of Bernoulli(p) in bits; 0 at (or beyond) the certain
    endpoints. Guards p<=0 / p>=1 so log2(0) never fires."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def by_checkpoint(rows, min_n):
    """rows = (cp, model_prob, market_prob, outcome, naive) tuples from
    info_arrival_curve.load_rows. Outcome/naive are intentionally unused."""
    grouped = defaultdict(lambda: {"gap": [], "ent_mkt": [], "ent_mdl": [], "mkt_p": [], "mdl_p": []})
    for cp, mdl_p, mkt_p, _outcome, _naive in rows:
        g = grouped[cp]
        g["gap"].append(abs(mdl_p - mkt_p))
        g["ent_mkt"].append(binary_entropy(mkt_p))
        g["ent_mdl"].append(binary_entropy(mdl_p))
        g["mkt_p"].append(mkt_p)
        g["mdl_p"].append(mdl_p)
    out = {}
    for cp, g in sorted(grouped.items()):
        n = len(g["gap"])
        if n < min_n:
            continue
        out[cp] = {
            "n": n,
            "mean_gap": round(mean(g["gap"]), 4),
            "median_gap": round(median(g["gap"]), 4),
            "mean_entropy_market_bits": round(mean(g["ent_mkt"]), 4),
            "mean_entropy_model_bits": round(mean(g["ent_mdl"]), 4),
            "mean_market_prob": round(mean(g["mkt_p"]), 4),
            "mean_model_prob": round(mean(g["mdl_p"]), 4),
        }
    return out


def summarize(cps_dict):
    """First-vs-last-reported-checkpoint deltas -- the honest one-liner numbers
    (direction not presupposed; whatever the data shows)."""
    cps = sorted(cps_dict)
    if len(cps) < 2:
        return {"note": "fewer than 2 checkpoints above floor -- no first/last delta"}
    f, l = cps_dict[cps[0]], cps_dict[cps[-1]]
    return {
        "first_checkpoint": cps[0],
        "last_checkpoint": cps[-1],
        "gap_first": f["mean_gap"],
        "gap_last": l["mean_gap"],
        "gap_delta_last_minus_first": round(l["mean_gap"] - f["mean_gap"], 4),
        "entropy_market_first_bits": f["mean_entropy_market_bits"],
        "entropy_market_last_bits": l["mean_entropy_market_bits"],
        "entropy_market_delta_last_minus_first": round(
            l["mean_entropy_market_bits"] - f["mean_entropy_market_bits"], 4),
    }


def plot(results, out_path):
    sports = [s for s in results if results[s]]
    if not sports:
        return False
    fig, axes = plt.subplots(1, len(sports), figsize=(6.2 * len(sports), 4.6), squeeze=False)
    for i, sport in enumerate(sports):
        cps = sorted(results[sport])
        gap = [results[sport][c]["mean_gap"] for c in cps]
        ent_m = [results[sport][c]["mean_entropy_market_bits"] for c in cps]
        ent_d = [results[sport][c]["mean_entropy_model_bits"] for c in cps]
        n = [results[sport][c]["n"] for c in cps]
        ax = axes[0][i]
        (l1,) = ax.plot(cps, gap, marker="o", color="tab:blue", label="mean |model-market| (gap)")
        ax.set_ylim(bottom=0)
        for x, y, cnt in zip(cps, gap, n):
            ax.annotate(f"n={cnt}", (x, y), textcoords="offset points", xytext=(0, 6), fontsize=6)
        ax.set_ylabel("mean |model_prob - market_prob| (gap)", color="tab:blue")
        ax.tick_params(axis="y", labelcolor="tab:blue")
        ax2 = ax.twinx()
        (l2,) = ax2.plot(cps, ent_m, marker="s", color="tab:orange", label="market entropy (bits)")
        (l3,) = ax2.plot(cps, ent_d, marker="^", linestyle="--", color="tab:red", label="model entropy (bits)")
        ax2.set_ylim(0, 1.02)
        ax2.set_ylabel("mean Bernoulli entropy (bits)", color="tab:orange")
        ax2.tick_params(axis="y", labelcolor="tab:orange")
        ax.set_xlabel("inning" if sport == "mlb" else "minute (5-min bucket)")
        ax.set_title(f"{sport}: market convergence")
        ax.legend(handles=[l1, l2, l3], fontsize=7, loc="upper right")
    fig.suptitle("Market convergence: model-market gap + predictive entropy over game time (DESCRIPTIVE_ONLY)", fontsize=10)
    fig.text(0.5, 0.005,
             "Source: data/cache/ingame_grade_joined/{mlb,soccer_intl}. edge_claimed=False. "
             "Entropy decay toward 0 as scores diverge is expected, reported as context.",
             ha="center", fontsize=6, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return True


def run():
    results, summaries = {}, {}
    for sport, pattern in CORPORA.items():
        rows = load_rows(sport, pattern)
        if not rows:
            continue
        cps = by_checkpoint(rows, MIN_N)
        results[sport] = cps
        summaries[sport] = summarize(cps) if cps else {"note": "no checkpoints above floor"}

    plot_written = plot(results, OUT_PNG)
    payload = {
        "edge_claimed": False,
        "descriptive_only": True,
        "story": (
            "Outcome-free convergence view: mean |model_prob - market_prob| (gap) and "
            "mean Bernoulli entropy (market + model, bits) per game-time checkpoint. "
            "Tracks whether the two forecasters agree more and whether predictive "
            "uncertainty collapses as the game resolves."
        ),
        "floors": {
            "min_rows_per_checkpoint": MIN_N,
            "entropy_units": "bits (log2); 1.0 max at p=0.5, 0.0 certain",
            "note": "entropy decay late in a game is expected (p->0/1), not a finding",
        },
        "novelty": {
            "verdict": "STANDARD_INSTRUMENT",
            "detail": (
                "Forecaster agreement + Shannon-entropy decay over event time are "
                "textbook descriptive measures; contribution is only the application "
                "to the mlb/soccer_intl joined corpora. Not a new method."
            ),
        },
        "min_n": MIN_N,
        "plot_written": plot_written,
        "checkpoints": results,
        "summary": summaries,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def check():
    """Pure-logic asserts, then a real run that must produce NONZERO outputs."""
    # entropy: max at 0.5, zero at/beyond the certain endpoints
    assert abs(binary_entropy(0.5) - 1.0) < 1e-9
    assert binary_entropy(1.0) == 0.0 and binary_entropy(0.0) == 0.0
    assert binary_entropy(1.5) == 0.0 and binary_entropy(-0.2) == 0.0  # clamp guard
    # gap: identical forecasts -> 0 gap, p=0.5 -> 1.0 bit entropy
    toy = [(1, 0.5, 0.5, 1.0, 0.5)] * (MIN_N + 10)
    bc = by_checkpoint(toy, MIN_N)
    assert bc[1]["mean_gap"] == 0.0, bc
    assert abs(bc[1]["mean_entropy_market_bits"] - 1.0) < 1e-9, bc
    # below-floor checkpoint is dropped, not reported
    assert by_checkpoint([(2, 0.6, 0.4, 1.0, 0.5)] * (MIN_N - 1), MIN_N) == {}

    payload = run()
    total = sum(len(v) for v in payload["checkpoints"].values())
    assert total > 0, "no checkpoints above floor -- outputs empty"
    assert os.path.exists(OUT_JSON) and os.path.getsize(OUT_JSON) > 0
    assert os.path.exists(OUT_PNG) and os.path.getsize(OUT_PNG) > 0
    n_sports = len([s for s in payload["checkpoints"] if payload["checkpoints"][s]])
    print("OK: market_convergence self-check passed (%d checkpoints across %d sports)" % (total, n_sports))


def main():
    payload = run()
    print("wrote", OUT_JSON)
    print("wrote", OUT_PNG, "(plot_written=%s)" % payload["plot_written"])
    for sport, s in payload["summary"].items():
        print("--", sport, "--", json.dumps(s))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    if ap.parse_args().check:
        check()
    else:
        main()
