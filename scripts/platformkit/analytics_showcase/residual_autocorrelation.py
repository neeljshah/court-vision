"""Within-game residual autocorrelation: do the model's errors persist across a game?

For every graded in-game series (grouped by game_id x side, ordered by ts) in the
joined corpora, computes the lag-1 sample autocorrelation of the signed residual
r_t = prob_t - outcome, for both the model and the market, then reports the
DISTRIBUTION of that per-game lag-1 autocorr across games (mean, median,
quartiles, share positive, share >= 0.9), model vs market, plus ONE chart.

Honest scope -- what this is and is NOT:
  * The outcome label is TERMINAL and constant within a game, so the residual
    series is prob_t minus a constant; its lag-1 autocorrelation therefore equals
    the serial correlation of the probability PATH itself. Strong positive
    autocorrelation is EXPECTED (consecutive win-prob updates barely move).
  * The exhibit's point is exactly that: it quantifies how far from independent
    within-game rows are. High autocorr => the effective number of independent
    observations per game is far below the row count, so any per-row Brier /
    count-based confidence interval OVERSTATES the sample size. This is a
    variance-of-estimate caveat, DESCRIPTIVE_ONLY, edge_claimed=False. It is NOT
    a signal, an edge, or a $/ROI claim of any kind.

Declared floors (a game-side series is used only if BOTH hold):
  * >= N_MIN rows after ordering by ts (default 10).
  * residual variance > VAR_EPS; a flat path has an undefined lag-1 autocorr and
    is counted as "flat" (skipped), never as 0.

Corpora: data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (mlb_clean is a
byte-identical duplicate of mlb and is absent from the reused SPORTS map).
Only these keys are consumed per row: game_id, side, ts, model_prob, market_prob,
outcome. atlas_factory's compact-card helpers are deliberately not used here: this
is a standalone distribution chart (like its sibling error-anatomy modules), not a
2-4 panel entity card, and the card size-guard (<=60KB) would reject a full figure.

Usage:
    python -m scripts.platformkit.analytics_showcase.residual_autocorrelation
    python -m scripts.platformkit.analytics_showcase.residual_autocorrelation --check
"""
import argparse
import json
import os
import statistics
from collections import defaultdict

try:  # -m package invocation (check_all) vs bare-script invocation
    from scripts.platformkit.analytics_showcase.state_conditioned_calibration import (
        SPORTS, load_records)
except ImportError:
    from state_conditioned_calibration import SPORTS, load_records

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_JSON = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase", "out", "residual_autocorrelation.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "residual_autocorrelation.png")

N_MIN = 10          # min rows in a game-side series to compute lag-1 autocorr
VAR_EPS = 1e-9      # residual variance <= this => flat path, autocorr undefined


def lag1_autocorr(series):
    """Standard lag-1 sample autocorrelation of a numeric series.
    Returns None if fewer than 2 points or (near) zero variance."""
    n = len(series)
    if n < 2:
        return None
    mean = sum(series) / n
    denom = sum((x - mean) ** 2 for x in series)
    if denom <= VAR_EPS:
        return None
    numer = sum((series[t] - mean) * (series[t + 1] - mean) for t in range(n - 1))
    return numer / denom


def group_series(recs):
    """Group rows into ordered residual series keyed by (game_id, side).
    residual r_t = prob_t - terminal outcome; rows ordered by ts (ISO -> lexical).
    Returns {(game_id, side): {"model": [r_t...], "market": [r_t...]}}."""
    by_key = defaultdict(list)
    for r in recs:
        gid, y = r.get("game_id"), r.get("outcome")
        if gid is None or y is None:
            continue
        by_key[(gid, r.get("side"))].append(r)
    out = {}
    for key, rows in by_key.items():
        rows.sort(key=lambda r: r.get("ts") or "")
        model, market = [], []
        for r in rows:
            y = r["outcome"]
            mp, kp = r.get("model_prob"), r.get("market_prob")
            if mp is not None:
                model.append(mp - y)
            if kp is not None:
                market.append(kp - y)
        out[key] = {"model": model, "market": market}
    return out


def per_game_autocorr(series_by_key):
    """Per-game lag-1 autocorr lists for model and market, with skip accounting
    (low_n = below N_MIN rows; flat = undefined because residual variance ~0)."""
    vals = {"model": [], "market": []}
    skip = {"model": {"low_n": 0, "flat": 0}, "market": {"low_n": 0, "flat": 0}}
    for srcs in series_by_key.values():
        for src in ("model", "market"):
            s = srcs[src]
            if len(s) < N_MIN:
                skip[src]["low_n"] += 1
                continue
            r1 = lag1_autocorr(s)
            if r1 is None:
                skip[src]["flat"] += 1
            else:
                vals[src].append(r1)
    return vals, skip


def dist_stats(values):
    n = len(values)
    if n == 0:
        return {"n_games": 0}
    stats = {
        "n_games": n,
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "share_positive": round(sum(v > 0 for v in values) / n, 4),
        "share_ge_0_9": round(sum(v >= 0.9 for v in values) / n, 4),
    }
    if n >= 2:
        q = statistics.quantiles(values, n=4)
        stats["q25"], stats["q75"] = round(q[0], 4), round(q[2], 4)
    return stats


def build_verdict(result):
    lines = []
    for sport, e in result["sports"].items():
        m, k = e["model"], e["market"]
        if not m.get("n_games") or not k.get("n_games"):
            continue
        lines.append(
            f"{sport}: median within-game lag-1 residual autocorr = model {m['median']:.3f} "
            f"(n={m['n_games']} games), market {k['median']:.3f} (n={k['n_games']}); "
            f"share>=0.9 model {m['share_ge_0_9']:.2f} vs market {k['share_ge_0_9']:.2f}."
        )
    if not lines:
        return "No sport had a usable game-side series meeting the floors."
    return " ".join(lines) + (" High positive values confirm within-game rows are far from "
                              "independent (effective sample size << row count); DESCRIPTIVE_ONLY, "
                              "no edge/ROI claim.")


def make_chart(sports, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    present = [s for s, e in sports.items()
               if e.get("autocorr_values", {}).get("model") or e.get("autocorr_values", {}).get("market")]
    if not present:
        return False
    fig, axes = plt.subplots(1, len(present), figsize=(5.2 * len(present), 4.2), sharey=True)
    if len(present) == 1:
        axes = [axes]
    bins = [(-1.0 + i / 10.0) for i in range(21)]  # 20 bins over [-1, 1]
    for ax, sport in zip(axes, present):
        raw = sports[sport]["autocorr_values"]
        for src, color in (("model", "#1f77b4"), ("market", "#b3452c")):
            v = raw.get(src) or []
            if not v:
                continue
            med = statistics.median(v)
            ax.hist(v, bins=bins, alpha=0.55, color=color,
                    label=f"{src} (n={len(v)}, med={med:.3f})")
            ax.axvline(med, color=color, linestyle="--", linewidth=1)
        ax.set_title(sport)
        ax.set_xlabel("within-game lag-1 residual autocorrelation")
        ax.set_xlim(-1, 1)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("number of games")
    fig.suptitle("Within-game residual autocorrelation: model vs market  [DESCRIPTIVE_ONLY]")
    fig.text(0.5, 0.005,
             "Source: data/cache/ingame_grade_joined/{mlb,soccer_intl}. residual r_t = prob_t - terminal outcome; "
             f"floors: n>={N_MIN} rows/game, var>{VAR_EPS}. High +autocorr => within-game rows not independent. "
             "edge_claimed=False.",
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)
    return True


def run():
    result = {
        "edge_claimed": False,
        "descriptive_only": True,
        "method": ("lag-1 sample autocorrelation of within-game signed residual "
                   "(prob_t - terminal outcome), per (game_id, side) series ordered by ts"),
        "floors": {"min_rows_per_game": N_MIN, "min_residual_variance": VAR_EPS},
        "story": ("Within-game residuals are strongly positively autocorrelated for both model "
                  "and market because the outcome is terminal-constant and the probability path "
                  "is smooth; the exhibit quantifies how far from independent within-game rows "
                  "are (effective sample size << row count). DESCRIPTIVE_ONLY, no edge/ROI claim."),
        "sports": {},
        "skipped": [{"sport": "mlb_clean", "reason": "byte-identical duplicate of mlb -- absent from reused SPORTS map"}],
    }
    for sport in SPORTS:
        files, recs = load_records(sport)
        if not files:
            result["skipped"].append({"sport": sport, "reason": "no jsonl files found"})
            continue
        series = group_series(recs)
        vals, skip = per_game_autocorr(series)
        result["sports"][sport] = {
            "n_files": len(files),
            "n_records": len(recs),
            "n_series": len(series),
            "model": {**dist_stats(vals["model"]), "skipped": skip["model"]},
            "market": {**dist_stats(vals["market"]), "skipped": skip["market"]},
            "autocorr_values": {"model": [round(v, 4) for v in vals["model"]],
                                "market": [round(v, 4) for v in vals["market"]]},
        }

    result["verdict"] = build_verdict(result)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    result["plot_written"] = make_chart(result["sports"], OUT_PNG) if result["sports"] else False
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def check():
    """Self-check: pure autocorr logic (sign, magnitude, undefined guard), the
    grouping/residual/skip accounting, then --check's contract that run() writes
    non-empty outputs."""
    assert lag1_autocorr([i * 0.01 for i in range(60)]) > 0.9, "smooth ramp should be near +1"
    assert lag1_autocorr([0, 1, 0, 1, 0, 1]) < -0.8, "alternating should be near -1"
    assert lag1_autocorr([0.5] * 8) is None, "flat series has undefined lag-1 autocorr"
    assert lag1_autocorr([0.5]) is None, "series shorter than 2 is undefined"

    recs = [{"game_id": "g", "side": "home", "ts": f"t{i:02d}", "model_prob": 0.5 + 0.01 * i,
             "market_prob": 0.5, "outcome": 1.0} for i in range(14)]
    series = group_series(recs)
    assert list(series.keys()) == [("g", "home")], series.keys()
    vals, skip = per_game_autocorr(series)
    assert len(vals["model"]) == 1 and vals["model"][0] > 0.5, vals  # rising path => strong +autocorr
    assert skip["market"]["flat"] == 1, skip  # flat market residual counted flat, not as 0

    result = run()
    assert result["sports"], "no sports produced output"
    assert os.path.exists(OUT_JSON) and os.path.getsize(OUT_JSON) > 0, "JSON output missing/empty"
    assert os.path.exists(OUT_PNG) and os.path.getsize(OUT_PNG) > 0, "PNG output missing/empty"
    print("OK: residual_autocorrelation self-check passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({"verdict": res["verdict"], "plot_written": res["plot_written"],
                          "sports": {s: {"n_records": d["n_records"], "n_series": d["n_series"],
                                         "model_median": d["model"].get("median"),
                                         "market_median": d["market"].get("median")}
                                     for s, d in res["sports"].items()}}, indent=2))
