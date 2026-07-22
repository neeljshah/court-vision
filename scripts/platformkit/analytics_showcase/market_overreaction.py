"""Market over/underreaction spectrum: bucket consecutive in-game market-price
moves by size, compare the moved-to price against the subsequent realized
outcome frequency in each bucket -- a magnitude-bucketed overreaction test.

Reads data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (same corpora
as info_arrival_curve.py). Groups by game_id, sorts by ts, computes
consecutive-row market_prob deltas, buckets by |delta|, and within each
bucket reports mean moved-to price vs mean realized outcome. moved_to_price
> outcome_rate means the move overshot (overreaction); moved_to_price <
outcome_rate means it undershot (underreaction).

This is a MEASUREMENT of price-move calibration by move size, not a $ edge
claim -- see docs/JOB_EVIDENCE_PACKET.md and .claude/rules/no-edge-claims.md.

PRIOR ART: Moskowitz (2021, J. Finance) already runs the magnitude-bucketed
overreaction test cross-sport (NBA/NFL/MLB/NHL/soccer) via open-to-close
movement vs outcome, finding ~50% mean-reversion. Choi & Hui (2014, JEBO) run
the in-play version on soccer goals, finding underreaction to moderate
surprises and overreaction to extreme ones. Our contribution is NOT a new
method -- it's the same bucketed-move-vs-outcome instrument applied
in-game (consecutive-row granularity, not event-triggered) to the MLB/
soccer_intl corpora we hold. VERDICT: INCREMENTAL.
"""
import glob
import json
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT_JSON = "scripts/platformkit/analytics_showcase/out/market_overreaction.json"
OUT_PNG = "docs/img/market_overreaction.png"
CORPORA = {
    "mlb": "data/cache/ingame_grade_joined/mlb/*.jsonl",
    "soccer_intl": "data/cache/ingame_grade_joined/soccer_intl/*.jsonl",
}
BUCKET_EDGES = [0.0, 0.01, 0.03, 0.06, 0.10, 1.01]
BUCKET_LABELS = ["0-1pt", "1-3pt", "3-6pt", "6-10pt", "10pt+"]


def bucket_of(abs_delta):
    for i in range(len(BUCKET_EDGES) - 1):
        if BUCKET_EDGES[i] <= abs_delta < BUCKET_EDGES[i + 1]:
            return BUCKET_LABELS[i]
    return BUCKET_LABELS[-1]


def load_games(pattern):
    games = defaultdict(list)
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
                if rec.get("market_prob") is None or rec.get("outcome") is None or not rec.get("ts") or not rec.get("game_id"):
                    continue
                games[rec["game_id"]].append(rec)
    for gid in games:
        games[gid].sort(key=lambda r: r["ts"])
    return games


def moves(games):
    # ponytail: consecutive-row deltas within a game, not event-triggered --
    # a coarser grain than Choi & Hui's goal-triggered buckets.
    out = []
    for gid, rows in games.items():
        for i in range(1, len(rows)):
            prev, cur = rows[i - 1], rows[i]
            delta = cur["market_prob"] - prev["market_prob"]
            out.append((abs(delta), cur["market_prob"], cur["outcome"]))
    return out


def by_bucket(move_rows):
    grouped = defaultdict(lambda: {"moved_to": [], "outcome": []})
    for abs_delta, moved_to_price, outcome in move_rows:
        b = grouped[bucket_of(abs_delta)]
        b["moved_to"].append(moved_to_price)
        b["outcome"].append(outcome)
    out = {}
    for label in BUCKET_LABELS:
        g = grouped.get(label)
        if not g or len(g["outcome"]) < 5:
            continue
        n = len(g["outcome"])
        moved_to = sum(g["moved_to"]) / n
        outcome_rate = sum(g["outcome"]) / n
        out[label] = {
            "n": n,
            "moved_to_price": round(moved_to, 4),
            "outcome_rate": round(outcome_rate, 4),
            "moved_to_minus_outcome": round(moved_to - outcome_rate, 4),
        }
    return out


def plot(results, out_path):
    sports = [s for s in results if results[s]]
    if not sports:
        return
    fig, axes = plt.subplots(1, len(sports), figsize=(6 * len(sports), 4.5), squeeze=False)
    for i, sport in enumerate(sports):
        labels = [l for l in BUCKET_LABELS if l in results[sport]]
        diff = [results[sport][l]["moved_to_minus_outcome"] for l in labels]
        n = [results[sport][l]["n"] for l in labels]
        ax = axes[0][i]
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.bar(labels, diff)
        for x, (y, cnt) in enumerate(zip(diff, n)):
            ax.annotate(f"n={cnt}", (x, y), textcoords="offset points", xytext=(0, 4 if y >= 0 else -12), fontsize=7, ha="center")
        ax.set_xlabel("|market move| bucket (prob points)")
        ax.set_ylabel("moved-to price - outcome rate (>0: overreaction)")
        ax.set_title(f"{sport}: overreaction spectrum")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


NOVELTY = {
    "verdict": "INCREMENTAL",
    "closest_prior_work": (
        "Moskowitz (2021, Journal of Finance), 'Asset Pricing and Sports "
        "Betting' -- cross-sport (NBA/NFL/MLB/NHL/soccer) magnitude-bucketed "
        "price-move-vs-outcome test, ~50% open-to-close reversion. Choi & Hui "
        "(2014, JEBO) run the in-play soccer version, event-triggered by "
        "goals, finding underreaction to moderate surprises and overreaction "
        "to extreme ones."
    ),
    "how_ours_differs": (
        "Same bucketed-move-vs-outcome instrument, applied at consecutive-row "
        "(not event-triggered) grain in-game, to MLB + soccer_intl corpora we "
        "hold. Not a new method -- do not claim first-ever."
    ),
}


def main():
    results = {}
    for sport, pattern in CORPORA.items():
        games = load_games(pattern)
        if not games:
            results[sport] = {"status": "no_data", "reason": "no rows with game_id+ts+market_prob+outcome"}
            continue
        move_rows = moves(games)
        if not move_rows:
            results[sport] = {"status": "no_data", "reason": "no consecutive-row pairs within any game"}
            continue
        results[sport] = by_bucket(move_rows)

    payload = {"buckets": results, "novelty": NOVELTY}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    plottable = {s: r for s, r in results.items() if isinstance(r, dict) and r.get("status") != "no_data"}
    plot(plottable, OUT_PNG)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_PNG}")
    for sport, buckets in results.items():
        print(f"-- {sport} --")
        print(buckets)


def _check():
    # ponytail: smallest self-check -- bucket edges + a hand-worked overreaction case
    assert bucket_of(0.005) == "0-1pt"
    assert bucket_of(0.02) == "1-3pt"
    assert bucket_of(0.5) == "10pt+"
    rows = [(0.02, 0.9, 1.0)] * 3 + [(0.02, 0.9, 0.0)] * 3  # moved to 0.9 always, outcome 50%
    b = by_bucket(rows)
    assert b["1-3pt"]["moved_to_minus_outcome"] == 0.4, b
    print("self-check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        main()
