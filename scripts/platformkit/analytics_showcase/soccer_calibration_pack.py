"""Soccer calibration pack: soccer_intl parity for the showcase.

Three views on the same row-level joined grade corpus (data/cache/ingame_grade_joined/soccer_intl,
n~9k rows): (1) Murphy decomposition model-vs-market (reuses murphy_decomposition.py), (2)
minute-bucket ECE for the model, (3) disagreement-bucket outcome-agreement (reuses the
market_disagreement_profile.py bucket scheme). edge_claimed=False, calibration-only.

Honest framing: this corpus is far smaller than mlb/nba (~9k rows vs 100k+), so CIs are wide
and single-fold reads are not durable -- the panel prints whatever the data actually says,
without smoothing over a market-leads result.

Usage:
    python -m scripts.platformkit.analytics_showcase.soccer_calibration_pack
    python -m scripts.platformkit.analytics_showcase.soccer_calibration_pack --check
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from scripts.platformkit.analytics_showcase.murphy_decomposition import load_rows, murphy_decompose

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "soccer_calibration_pack.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "soccer_calibration_pack.png")
SPORT = "soccer_intl"
MINUTE_BUCKETS = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 91)]
DISAGREE_BUCKETS = [(0.0, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1.0001)]
DISAGREE_LABELS = ["<.02", ".02-.05", ".05-.10", ">=.10"]
N_ECE_BINS = 10


def _minute_of(row):
    m = re.search(r"minute=(\d+)", row.get("state_summary") or "")
    return int(m.group(1)) if m else None


def minute_ece(rows):
    """Per-minute-bucket |mean_p - mean_y| ECE for model_prob, weighted by bucket n."""
    out = []
    total_n = 0
    weighted = 0.0
    for lo, hi in MINUTE_BUCKETS:
        in_bucket = [r for r in rows if r.get("model_prob") is not None and _minute_of(r) is not None and lo <= _minute_of(r) < hi]
        n = len(in_bucket)
        if n == 0:
            out.append({"minute_lo": lo, "minute_hi": hi, "n": 0})
            continue
        mean_p = sum(r["model_prob"] for r in in_bucket) / n
        mean_y = sum(r["outcome"] for r in in_bucket) / n
        ece = abs(mean_p - mean_y)
        out.append({"minute_lo": lo, "minute_hi": hi, "n": n, "mean_p": round(mean_p, 4),
                     "mean_y": round(mean_y, 4), "ece": round(ece, 4)})
        total_n += n
        weighted += n * ece
    overall = round(weighted / total_n, 4) if total_n else None
    return {"buckets": out, "overall_weighted_ece": overall, "n": total_n}


def _model_right(p, m, y):
    de = abs(p - y) - abs(m - y)
    if de < 0:
        return 1
    if de > 0:
        return 0
    return None


def disagreement_buckets(rows):
    out = []
    for (lo, hi), label in zip(DISAGREE_BUCKETS, DISAGREE_LABELS):
        in_b = [r for r in rows if r.get("market_prob") is not None and lo <= abs(r["model_prob"] - r["market_prob"]) < hi]
        n = len(in_b)
        if n == 0:
            out.append({"bucket": label, "n": 0})
            continue
        model_brier = sum((r["model_prob"] - r["outcome"]) ** 2 for r in in_b) / n
        market_brier = sum((r["market_prob"] - r["outcome"]) ** 2 for r in in_b) / n
        calls = [_model_right(r["model_prob"], r["market_prob"], r["outcome"]) for r in in_b]
        decided = [c for c in calls if c is not None]
        agree_rate = round(sum(decided) / len(decided), 4) if decided else None
        out.append({"bucket": label, "n": n, "model_brier": round(model_brier, 6),
                     "market_brier": round(market_brier, 6), "model_wins_rate": agree_rate})
    return out


def make_plot(result):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # panel 1: reliability diagram model vs market
    ax = axes[0]
    murphy = result["murphy"]
    for field, label, marker in [("model_prob", "model", "o"), ("market_prob", "market", "s")]:
        dec = murphy.get(field)
        if not dec:
            continue
        xs = [b["mean_p"] for b in dec["bins"] if b["n"] > 0]
        ys = [b["mean_y"] for b in dec["bins"] if b["n"] > 0]
        ax.plot(xs, ys, marker=marker, label=f"{label} (Brier={dec['brier']:.4f})")
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1, label="perfect")
    ax.set_title("Murphy reliability: model vs market")
    ax.set_xlabel("mean predicted prob")
    ax.set_ylabel("mean observed outcome")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.legend(fontsize=7)

    # panel 2: minute-bucket ECE
    ax = axes[1]
    mece = result["minute_ece"]["buckets"]
    labels = [f"{b['minute_lo']}-{b['minute_hi']}" for b in mece]
    vals = [b.get("ece") for b in mece]
    xs_idx = range(len(labels))
    ax.bar([i for i, v in zip(xs_idx, vals) if v is not None], [v for v in vals if v is not None], color="steelblue")
    ax.set_xticks(list(xs_idx))
    ax.set_xticklabels(labels, rotation=45, fontsize=7)
    ax.set_title(f"Model ECE by minute bucket (weighted={result['minute_ece']['overall_weighted_ece']})")
    ax.set_xlabel("minute")
    ax.set_ylabel("|mean_p - mean_y|")

    # panel 3: disagreement buckets - model vs market brier
    ax = axes[2]
    db = result["disagreement_buckets"]
    labels = [b["bucket"] for b in db]
    model_b = [b.get("model_brier") for b in db]
    market_b = [b.get("market_brier") for b in db]
    x = range(len(labels))
    w = 0.35
    ax.bar([i - w / 2 for i in x if model_b[i] is not None], [v for v in model_b if v is not None], width=w, label="model")
    ax.bar([i + w / 2 for i in x if market_b[i] is not None], [v for v in market_b if v is not None], width=w, label="market")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_title("Brier by |model-market| disagreement bucket")
    ax.set_xlabel("|model_prob - market_prob|")
    ax.legend(fontsize=7)

    fig.suptitle(f"Soccer (intl) calibration pack -- n={result['n_rows']} rows, edge_claimed=False")
    fig.text(0.5, 0.01,
              "Source: data/cache/ingame_grade_joined/soccer_intl. Smaller corpus than mlb/nba -- wider CIs.",
              ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def build_honest_note(result):
    murphy = result["murphy"]
    m, k = murphy.get("model_prob"), murphy.get("market_prob")
    lines = [f"soccer_intl corpus: n={result['n_rows']} rows -- far smaller than mlb/nba, wider CIs, single-fold reads not durable."]
    if m and k:
        gap = m["brier"] - k["brier"]
        lines.append(f"Murphy: model Brier {m['brier']:.4f} vs market {k['brier']:.4f} (gap={gap:+.4f}); "
                      f"{'market leads' if gap > 1e-4 else ('model leads' if gap < -1e-4 else 'effectively tied')}.")
    mece = result["minute_ece"]["overall_weighted_ece"]
    if mece is not None:
        lines.append(f"Minute-bucket ECE (weighted): {mece:.4f}.")
    return " ".join(lines)


def run():
    rows = load_rows(SPORT)
    result = {"edge_claimed": False, "sport": SPORT, "n_rows": len(rows)}
    if not rows:
        result["skipped_reason"] = "no rows found"
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return result

    result["murphy"] = {
        "model_prob": murphy_decompose(rows, "model_prob"),
        "market_prob": murphy_decompose(rows, "market_prob"),
    }
    result["minute_ece"] = minute_ece(rows)
    result["disagreement_buckets"] = disagreement_buckets(rows)
    result["honest_note"] = build_honest_note(result)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    plotted = make_plot(result)
    result["plot_written"] = plotted
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


def check():
    """Tiny self-check: minute_ece on a synthetic perfectly-calibrated bucket -> ece ~0."""
    rows = [{"model_prob": 0.6, "outcome": 1.0 if i % 5 < 3 else 0.0, "state_summary": "minute=10"} for i in range(50)]
    res = minute_ece(rows)
    b0 = res["buckets"][0]
    assert b0["n"] == 50, b0
    assert abs(b0["mean_y"] - 0.6) < 1e-9, b0
    assert abs(b0["ece"]) < 1e-9, b0
    print("soccer_calibration_pack self-check OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({"n_rows": res["n_rows"], "plot_written": res.get("plot_written"),
                           "honest_note": res.get("honest_note")}, indent=2))
