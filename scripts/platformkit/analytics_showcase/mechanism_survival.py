"""Mechanism survival analytics over domains/*/knowledge/validation_ledger.jsonl
(4 sports, ~287 rows total): what share of hypotheses tested confirm, broken out
by sport and by mechanism category (keyword-bucketed on the hypothesis name).

A NULL/REJECT is honest market-efficiency evidence, not a failure. No $/edge/ROI
claim -- this is a calibration/measurement artifact, not a betting product.

Usage:
    python -m scripts.platformkit.analytics_showcase.mechanism_survival
    python -m scripts.platformkit.analytics_showcase.mechanism_survival --check
"""
import argparse
import collections
import glob
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LEDGER_GLOB = os.path.join(REPO_ROOT, "domains", "*", "knowledge", "validation_ledger.jsonl")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "mechanism_survival.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "mechanism_survival.png")

CONFIRMED_VERDICTS = {"CONFIRMED_LOCAL", "CONFIRMED_LOCAL_incl_2026_OOS", "REPLICATED"}
NOT_TESTABLE_VERDICTS = {"NOT_TESTABLE", "NOT_REPLICABLE_NO_CORPUS"}
# everything else (NULL, NULL_LOCAL, REJECT, PARTIAL, PROVISIONAL, FAILED_REPLICATION,
# ARTIFACT_CONFIRMED) counts as "tested, not confirmed" for survival purposes.

# ponytail: ordered keyword bins over the hypothesis slug -- first match wins,
# unmatched falls into the catch-all "situational" bucket. Good enough for 259
# distinct hypothesis names; upgrade to a taxonomy field on the ledger schema
# if hypothesis naming ever drifts away from these substrings.
CATEGORY_KEYWORDS = [
    ("rest_fatigue", ["rest", "fatigue", "b2b", "load", "durability", "recovery", "tired"]),
    ("travel", ["travel", "timezone", "altitude"]),
    ("streak_momentum", ["streak", "momentum", "continuity", "hot_", "cold_"]),
    ("matchup", ["matchup", "platoon", "h2h", "opponent", "specialization", "surface", "interaction"]),
    ("weather_park", ["weather", "park", "climate", "rain"]),
    ("official_referee", ["referee", "umpire", "call", "zone", "strike"]),
]
CATCHALL_CATEGORY = "situational"


def categorize(hypothesis):
    h = (hypothesis or "").lower()
    for label, keywords in CATEGORY_KEYWORDS:
        if any(kw in h for kw in keywords):
            return label
    return CATCHALL_CATEGORY


def load_ledger():
    rows = []
    for path in sorted(glob.glob(LEDGER_GLOB)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    return rows


def survival_stats(rows):
    total = len(rows)
    testable = [r for r in rows if r.get("verdict") not in NOT_TESTABLE_VERDICTS]
    confirmed = [r for r in testable if r.get("verdict") in CONFIRMED_VERDICTS]
    not_testable = total - len(testable)
    rate = round(len(confirmed) / len(testable), 4) if testable else None
    return {
        "n": total,
        "n_testable": len(testable),
        "n_confirmed": len(confirmed),
        "n_not_testable": not_testable,
        "not_testable_share": round(not_testable / total, 4) if total else None,
        "survival_rate": rate,
    }


def build():
    rows = load_ledger()

    by_sport = collections.defaultdict(list)
    by_category = collections.defaultdict(list)
    for r in rows:
        by_sport[r.get("sport", "?")].append(r)
        by_category[categorize(r.get("hypothesis"))].append(r)

    return {
        "source": "domains/*/knowledge/validation_ledger.jsonl (4 sports)",
        "note": (
            "Survival rate = share of TESTABLE hypotheses whose latest recorded verdict is "
            "CONFIRMED_LOCAL / CONFIRMED_LOCAL_incl_2026_OOS / REPLICATED. A NULL/REJECT is "
            "honest market-efficiency evidence, not a failure. No $/edge/ROI claim."
        ),
        "verdict_taxonomy": {
            "confirmed": sorted(CONFIRMED_VERDICTS),
            "not_testable": sorted(NOT_TESTABLE_VERDICTS),
            "tested_not_confirmed": "everything else (NULL, NULL_LOCAL, REJECT, PARTIAL, "
                                     "PROVISIONAL, FAILED_REPLICATION, ARTIFACT_CONFIRMED)",
        },
        "category_keyword_map": dict(CATEGORY_KEYWORDS) | {CATCHALL_CATEGORY: "catch-all (no keyword match)"},
        "overall": survival_stats(rows),
        "by_sport": {sport: survival_stats(rs) for sport, rs in sorted(by_sport.items())},
        "by_category": {cat: survival_stats(rs) for cat, rs in sorted(by_category.items(), key=lambda kv: -len(kv[1]))},
        "novelty": {
            "verdict": "N/A -- this is an internal measurement-hygiene artifact (a scoreboard over our own "
                       "hypothesis ledger), not a market-facing analytic method. No prior-art search performed; "
                       "the closest prior-art notes on file are for the market information-arrival curve "
                       "(INCREMENTAL vs arXiv 2606.07811) and the over/underreaction spectrum (INCREMENTAL vs "
                       "Moskowitz 2021 / Choi & Hui 2014) -- neither of those covers a hypothesis-survival "
                       "scoreboard, so this artifact carries no borrowed novelty claim of its own.",
        },
        "edge_claimed": False,
    }


def render_png(result, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cats = list(result["by_category"].keys())
    rates = [result["by_category"][c]["survival_rate"] or 0 for c in cats]
    ns = [result["by_category"][c]["n_testable"] for c in cats]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(cats, rates, color="#4C72B0")
    ax.invert_yaxis()
    ax.set_xlabel("survival rate (confirmed / testable)")
    ax.set_xlim(0, 1)
    for bar, n in zip(bars, ns):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2, f"n={n}", va="center", fontsize=8)
    ax.set_title(
        f"Mechanism survival by category -- overall {result['overall']['survival_rate']} "
        f"({result['overall']['n_confirmed']}/{result['overall']['n_testable']} testable)"
    )
    fig.text(0.5, 0.01, result["note"], ha="center", fontsize=7, color="gray", wrap=True)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    result = build()

    if args.check:
        assert result["overall"]["n"] > 0
        assert result["overall"]["n_testable"] <= result["overall"]["n"]
        assert sum(v["n"] for v in result["by_sport"].values()) == result["overall"]["n"]
        assert sum(v["n"] for v in result["by_category"].values()) == result["overall"]["n"]
        print("mechanism_survival --check OK:", result["overall"])
        return

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    render_png(result, OUT_PNG)
    print("wrote", OUT_JSON)
    print("wrote", OUT_PNG)
    print("overall:", result["overall"])
    print("by_sport:", result["by_sport"])


if __name__ == "__main__":
    main()
