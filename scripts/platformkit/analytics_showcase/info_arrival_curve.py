"""Market information-arrival curve: model-vs-market Brier delta by game-time
checkpoint, from ingame_grade_joined corpora (mlb, soccer_intl).

Reads data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl. Parses
inning (mlb) / minute (soccer_intl) out of state_summary, buckets rows into
game-time checkpoints, and computes per-checkpoint Brier for: our model,
the live market, and a naive score-only baseline (logistic on score diff,
no time-remaining/model signal at all).

Story: does the market's calibration gap to our model shrink, grow, or stay
flat as the game progresses? This is a MEASUREMENT of information absorption
over time, not a $ edge claim -- see docs/JOB_EVIDENCE_PACKET.md and
.claude/rules/no-edge-claims.md.

PRIOR ART: arXiv 2606.07811 already runs the same instrument (contract-minute
market vs state-only-model vs outcome join, NBA, 409k rows) and finds a 0.64
response-per-benchmark-move contemporaneous absorption rate. Our contribution
here is NOT a new method -- it's the same measurement applied to MLB/soccer
corpora we actually hold, framed as a checkpoint curve rather than a single
regression coefficient. VERDICT: INCREMENTAL.
"""
import glob
import json
import math
import re
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT_JSON = "scripts/platformkit/analytics_showcase/out/info_arrival_curve.json"
OUT_PNG = "docs/img/info_arrival_curve.png"
CORPORA = {
    "mlb": "data/cache/ingame_grade_joined/mlb/*.jsonl",
    "soccer_intl": "data/cache/ingame_grade_joined/soccer_intl/*.jsonl",
}
SCORE_RE = re.compile(r"home_score=([\d.]+) away_score=([\d.]+)")
INNING_RE = re.compile(r"inning=(\d+)")
MINUTE_RE = re.compile(r"minute=(\d+)")


def brier(probs, outcomes):
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)


def naive_prob(home_score, away_score, k=0.35):
    # ponytail: score-diff-only logistic, no clock/state -- the "dumbest
    # possible" state-only baseline, deliberately weaker than model_prob.
    diff = home_score - away_score
    return 1.0 / (1.0 + math.exp(-k * diff))


def checkpoint(sport, state_summary):
    if sport == "mlb":
        m = INNING_RE.search(state_summary)
        return int(m.group(1)) if m else None
    m = MINUTE_RE.search(state_summary)
    if not m:
        return None
    minute = int(m.group(1))
    return min(minute // 5, 18) * 5  # 5-min buckets, capped at 90+


def load_rows(sport, pattern):
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
                ss = rec.get("state_summary", "")
                cp = checkpoint(sport, ss)
                if cp is None:
                    continue
                sm = SCORE_RE.search(ss)
                if not sm:
                    continue
                hs, aws = float(sm.group(1)), float(sm.group(2))
                rows.append((cp, rec["model_prob"], rec["market_prob"], rec["outcome"], naive_prob(hs, aws)))
    return rows


def by_checkpoint(rows):
    grouped = defaultdict(lambda: {"model_p": [], "market_p": [], "outcome": [], "naive_p": []})
    for cp, mp, mkp, o, np in rows:
        g = grouped[cp]
        g["model_p"].append(mp)
        g["market_p"].append(mkp)
        g["outcome"].append(o)
        g["naive_p"].append(np)
    out = {}
    for cp, g in sorted(grouped.items()):
        n = len(g["outcome"])
        if n < 5:
            continue
        model_b = brier(g["model_p"], g["outcome"])
        market_b = brier(g["market_p"], g["outcome"])
        out[cp] = {
            "n": n,
            "model_brier": round(model_b, 4),
            "market_brier": round(market_b, 4),
            "naive_brier": round(brier(g["naive_p"], g["outcome"]), 4),
            "market_minus_model_brier": round(market_b - model_b, 4),
        }
    return out


def plot(results, out_path):
    sports = list(results.keys())
    fig, axes = plt.subplots(1, len(sports), figsize=(6 * len(sports), 4.5), squeeze=False)
    for i, sport in enumerate(sports):
        cps = sorted(results[sport].keys())
        delta = [results[sport][c]["market_minus_model_brier"] for c in cps]
        n = [results[sport][c]["n"] for c in cps]
        ax = axes[0][i]
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.plot(cps, delta, marker="o")
        for x, y, cnt in zip(cps, delta, n):
            ax.annotate(f"n={cnt}", (x, y), textcoords="offset points", xytext=(0, 6), fontsize=7)
        xlabel = "inning" if sport == "mlb" else "minute (5-min bucket)"
        ax.set_xlabel(xlabel)
        ax.set_ylabel("market Brier - model Brier (>0: market behind)")
        ax.set_title(f"{sport}: info-arrival curve")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


NOVELTY = {
    "verdict": "INCREMENTAL",
    "closest_prior_work": (
        "arXiv 2606.07811 (~Jun 2026), 'When Do Markets Fully Process Public "
        "Information? Evidence from Real-Time Prediction Markets' -- Kalshi/NBA, "
        "contract-minute market vs state-only-model vs outcome join, 409,512 rows, "
        "finds 0.64-for-one contemporaneous absorption of a 1-minute state move."
    ),
    "how_ours_differs": (
        "Same core instrument (paired model/market/outcome Brier by game-time "
        "checkpoint). Ours applies it to MLB (inning) and soccer_intl (5-min "
        "bucket) corpora we actually hold, with a naive score-only baseline "
        "included for context. Not a new method -- do not claim first-ever."
    ),
}


def main():
    results = {}
    for sport, pattern in CORPORA.items():
        rows = load_rows(sport, pattern)
        if not rows:
            continue
        results[sport] = by_checkpoint(rows)

    payload = {"checkpoints": results, "novelty": NOVELTY}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    plot(results, OUT_PNG)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_PNG}")
    for sport, cps in results.items():
        print(f"-- {sport} --")
        for cp, stats in cps.items():
            print(cp, stats)


def _check():
    # ponytail: smallest self-check -- brier on a hand-worked toy case + naive_prob shape
    b = brier([0.9, 0.1], [1.0, 0.0])
    assert abs(b - 0.01) < 1e-9, b
    assert naive_prob(0, 0) == 0.5
    assert naive_prob(5, 0) > 0.8
    assert checkpoint("mlb", "home_score=1.0 away_score=0.0 inning=3 half=top") == 3
    assert checkpoint("soccer_intl", "home_score=0.0 away_score=0.0 minute=47") == 45
    print("self-check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        main()
