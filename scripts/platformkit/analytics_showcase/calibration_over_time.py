"""Monthly model-vs-market Brier/ECE drift, from ingame_grade_joined corpora.

Reads data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (mlb_clean is a
dedup of mlb, skipped -- ponytail: no need to read the same rows twice).
Writes out/calibration_over_time.json + docs/img/calibration_over_time.png.

Story: is calibration stable over calendar time, or drifting? Honest drift
disclosure (incl. any month where the model loses to market) is itself the
credibility exhibit -- see docs/JOB_EVIDENCE_PACKET.md.
"""
import glob
import json
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT_JSON = "scripts/platformkit/analytics_showcase/out/calibration_over_time.json"
OUT_PNG = "docs/img/calibration_over_time.png"
CORPORA = {
    "mlb": "data/cache/ingame_grade_joined/mlb/*.jsonl",
    "soccer_intl": "data/cache/ingame_grade_joined/soccer_intl/*.jsonl",
}
N_BINS = 10


def brier(probs, outcomes):
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)


def ece(probs, outcomes, n_bins=N_BINS):
    bins = [[] for _ in range(n_bins)]
    for p, o in zip(probs, outcomes):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, o))
    n = len(probs)
    total = 0.0
    for b in bins:
        if not b:
            continue
        conf = sum(p for p, _ in b) / len(b)
        acc = sum(o for _, o in b) / len(b)
        total += (len(b) / n) * abs(conf - acc)
    return total


def load_rows(pattern):
    rows = []
    for path in glob.glob(pattern):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("model_prob") is None or rec.get("market_prob") is None or rec.get("outcome") is None:
                    continue
                month = rec["ts"][:7]  # YYYY-MM
                rows.append((month, rec["model_prob"], rec["market_prob"], rec["outcome"]))
    return rows


def by_month(rows):
    grouped = defaultdict(lambda: {"model_p": [], "market_p": [], "outcome": []})
    for month, mp, mkp, o in rows:
        g = grouped[month]
        g["model_p"].append(mp)
        g["market_p"].append(mkp)
        g["outcome"].append(o)
    out = {}
    for month, g in sorted(grouped.items()):
        out[month] = {
            "n": len(g["outcome"]),
            "model_brier": round(brier(g["model_p"], g["outcome"]), 4),
            "market_brier": round(brier(g["market_p"], g["outcome"]), 4),
            "model_ece": round(ece(g["model_p"], g["outcome"]), 4),
            "market_ece": round(ece(g["market_p"], g["outcome"]), 4),
        }
    return out


def plot(results, out_path):
    sports = list(results.keys())
    fig, axes = plt.subplots(len(sports), 2, figsize=(11, 4 * len(sports)), squeeze=False)
    for i, sport in enumerate(sports):
        months = sorted(results[sport].keys())
        n = [results[sport][m]["n"] for m in months]
        model_b = [results[sport][m]["model_brier"] for m in months]
        market_b = [results[sport][m]["market_brier"] for m in months]
        model_e = [results[sport][m]["model_ece"] for m in months]
        market_e = [results[sport][m]["market_ece"] for m in months]

        ax = axes[i][0]
        ax.plot(months, model_b, marker="o", label="model Brier")
        ax.plot(months, market_b, marker="o", label="market Brier")
        for x, y, cnt in zip(months, model_b, n):
            ax.annotate(f"n={cnt}", (x, y), textcoords="offset points", xytext=(0, 6), fontsize=7)
        ax.set_title(f"{sport}: Brier by month")
        ax.set_ylabel("Brier (lower better)")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=8)

        ax2 = axes[i][1]
        ax2.plot(months, model_e, marker="o", label="model ECE")
        ax2.plot(months, market_e, marker="o", label="market ECE")
        ax2.set_title(f"{sport}: ECE by month")
        ax2.set_ylabel("ECE (lower better)")
        ax2.tick_params(axis="x", rotation=45)
        ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main():
    results = {}
    for sport, pattern in CORPORA.items():
        rows = load_rows(pattern)
        if not rows:
            continue
        results[sport] = by_month(rows)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    plot(results, OUT_PNG)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_PNG}")
    for sport, months in results.items():
        print(f"-- {sport} --")
        for m, stats in months.items():
            print(m, stats)


def _check():
    # ponytail: smallest self-check -- brier/ece on a hand-worked toy case
    probs = [0.9, 0.1, 0.5]
    outs = [1.0, 0.0, 1.0]
    b = brier(probs, outs)
    assert abs(b - ((0.1**2 + 0.1**2 + 0.5**2) / 3)) < 1e-9, b
    e = ece(probs, outs, n_bins=10)
    assert e >= 0
    print("self-check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        main()
