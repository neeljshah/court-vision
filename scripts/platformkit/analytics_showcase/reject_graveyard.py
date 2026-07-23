"""Analytics over the signal reject ledger (scripts/platformkit/reject_ledger.py):
verdicts by reason category, by sport, over time.

Reads the ledger's FULL recorded history (reject_ledger.load(), every row ever
appended) -- NOT graveyard() which collapses to latest-verdict-per-signal. The
gap between those two counts is disclosed explicitly in the output (a signal
retested multiple times contributes one row per test to history, one row to
the graveyard).

A REJECT/DEFER/etc is honest market-efficiency evidence, not a failure. No
$/edge/ROI claim. Source: data/frontend/reject_ledger.jsonl (via reject_ledger.py).

Usage:
    python -m scripts.platformkit.analytics_showcase.reject_graveyard
    python -m scripts.platformkit.analytics_showcase.reject_graveyard --check
"""
import argparse
import collections
import json
import os
import re

from scripts.platformkit.reject_ledger import load, graveyard, REJECT_VERDICTS
from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "reject_graveyard.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "reject_graveyard.png")

# ponytail: ordered regex bins over the free-text `reason` field -- good enough to group
# 804 rows into a readable bar chart; upgrade to a taxonomy field on the ledger schema if
# reason text ever gets noisier.
REASON_CATEGORIES = [
    ("asof_reclaim_sweep", re.compile(r"asof reclaim sweep", re.I)),
    ("seed_stability", re.compile(r"seed-stability", re.I)),
    ("insufficient_corpora", re.compile(r"fewer than \d+ corpora", re.I)),
    ("calibration_only_unproven", re.compile(r"UNPROVEN.*CALIBRATION", re.I)),
    ("cross_corpus_adjudication", re.compile(r"cross-corpus", re.I)),
    ("conformal_width", re.compile(r"conformal", re.I)),
    ("wf_ablation", re.compile(r"WF folds|ablation", re.I)),
    ("prescreen_delta", re.compile(r"prescreen: held-out delta", re.I)),
    ("leak_free_wf_gate", re.compile(r"leak-free WF gate", re.I)),
    ("sealed_holdout", re.compile(r"sealed-holdout", re.I)),
    ("planted_null", re.compile(r"family_frozen|planted-null", re.I)),
    ("discovered_transform", re.compile(r"discovered transform", re.I)),
]


def categorize(reason):
    for label, pat in REASON_CATEGORIES:
        if pat.search(reason or ""):
            return label
    return "other" if reason else "no_reason_given"


def build():
    history = load()  # full recorded history, every verdict row ever appended
    latest = graveyard()  # latest verdict per (sport, signal), rejects only

    reject_rows = [r for r in history if r.get("verdict") in REJECT_VERDICTS]

    by_reason = collections.Counter(categorize(r.get("reason", "")) for r in reject_rows)
    by_sport = collections.Counter(r.get("sport", "?") for r in history)
    by_verdict = collections.Counter(r.get("verdict", "?") for r in history)

    by_day = collections.Counter(str(r.get("ts", ""))[:10] for r in reject_rows if r.get("ts"))
    days = sorted(d for d in by_day if d)
    cum = []
    running = 0
    for d in days:
        running += by_day[d]
        cum.append({"date": d, "rejects_that_day": by_day[d], "cumulative_rejects": running})

    return {
        "source": "scripts/platformkit/reject_ledger.py (data/frontend/reject_ledger.jsonl)",
        "note": "A REJECT/DEFER is honest market-efficiency evidence, not a failure. No $/edge/ROI claim.",
        "full_history_row_count": len(history),
        "latest_per_signal_graveyard_count": len(latest),
        "history_vs_latest_disclosure": (
            f"{len(history)} total recorded verdict rows across all reruns, vs "
            f"{len(latest)} distinct (sport, signal) currently sitting on a REJECT-family "
            f"verdict as of their latest test -- the gap is signals retested multiple times "
            f"(asof-reclaim sweeps, re-gating) plus rows whose latest verdict flipped to SHIP."
        ),
        "reject_row_count": len(reject_rows),
        "verdicts_by_type": dict(sorted(by_verdict.items(), key=lambda kv: -kv[1])),
        "rejects_by_reason_category": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
        "history_rows_by_sport": dict(sorted(by_sport.items(), key=lambda kv: -kv[1])),
        "cumulative_rejects_over_time": cum,
        "edge_claimed": False,
    }


def render_png(result, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import datetime

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    reasons = result["rejects_by_reason_category"]
    labels = list(reasons.keys())
    counts = list(reasons.values())
    ax1.barh(labels, counts, color="#C44E52")
    ax1.invert_yaxis()
    ax1.set_xlabel("reject rows")
    ax1.set_title(f"Rejects by reason category (n={result['reject_row_count']})")

    cum = result["cumulative_rejects_over_time"]
    dates = [datetime.date.fromisoformat(c["date"]) for c in cum]
    running = [c["cumulative_rejects"] for c in cum]
    ax2.plot(dates, running, color="#4C72B0", linewidth=2)
    ax2.set_ylabel("cumulative rejects")
    ax2.set_title("Cumulative rejects over time (full history)")
    ax2.tick_params(axis="x", rotation=45)

    fig.suptitle(
        f"Signal reject graveyard -- {result['full_history_row_count']} full-history rows "
        f"vs {result['latest_per_signal_graveyard_count']} latest-per-signal",
        fontsize=11,
    )
    fig.text(0.5, 0.01, result["note"], ha="center", fontsize=8, color="gray")
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    result = build()

    if args.check and result["full_history_row_count"] == 0:
        # local ledger (data/frontend/reject_ledger.jsonl, gitignored) absent --
        # e.g. on a fresh clone. Fall back to verifying the committed artifact.
        def validate(d):
            assert d["full_history_row_count"] > 0
            assert d["latest_per_signal_graveyard_count"] > 0
            assert d["full_history_row_count"] >= d["latest_per_signal_graveyard_count"]
        verify_recorded_artifact(OUT_JSON, validate, "reject_graveyard")
        return

    if args.check:
        assert result["full_history_row_count"] > 0
        assert result["latest_per_signal_graveyard_count"] > 0
        assert result["full_history_row_count"] >= result["latest_per_signal_graveyard_count"]
        assert sum(result["rejects_by_reason_category"].values()) == result["reject_row_count"]
        assert sum(result["history_rows_by_sport"].values()) == result["full_history_row_count"]
        print("reject_graveyard --check OK:", result["full_history_row_count"], "history rows,",
              result["latest_per_signal_graveyard_count"], "latest-per-signal")
        return

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    render_png(result, OUT_PNG)
    print("wrote", OUT_JSON)
    print("wrote", OUT_PNG)
    print("full_history_row_count:", result["full_history_row_count"])
    print("latest_per_signal_graveyard_count:", result["latest_per_signal_graveyard_count"])
    print("verdicts_by_type:", result["verdicts_by_type"])
    print("rejects_by_reason_category:", result["rejects_by_reason_category"])


if __name__ == "__main__":
    main()
