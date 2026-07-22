"""Honesty exhibit: verdict-distribution across all domain validation ledgers
+ the interaction_factory ledger. Reads only, computes nothing new -- every
count here comes straight off the verdict field already in each ledger row.

The point of the chart: nulls dwarf confirms. That's the honesty story, not
a bug in the pipeline.

Usage:
    python -m scripts.platformkit.analytics_showcase.honesty_exhibit
    python -m scripts.platformkit.analytics_showcase.honesty_exhibit --check
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_JSON = OUT_DIR / "honesty_exhibit.json"
IMG_PATH = ROOT / "docs" / "img" / "honesty_exhibit.png"

LEDGERS = [
    ("nba", ROOT / "domains" / "basketball_nba" / "knowledge" / "validation_ledger.jsonl"),
    ("mlb", ROOT / "domains" / "mlb" / "knowledge" / "validation_ledger.jsonl"),
    ("soccer", ROOT / "domains" / "soccer" / "knowledge" / "validation_ledger.jsonl"),
    ("tennis", ROOT / "domains" / "tennis" / "knowledge" / "validation_ledger.jsonl"),
    ("interaction_factory", ROOT / "data" / "cache" / "intel_claims" / "interaction_factory_ledger.jsonl"),
]

# verdict strings actually observed in these ledgers (inspected 2026-07-22),
# bucketed into the 5 categories the exhibit reports.
BUCKETS = {
    "confirmed": {
        "CONFIRMED_LOCAL", "REPLICATED", "ARTIFACT_CONFIRMED",
        "CONFIRMED_LOCAL_incl_2026_OOS", "SURVIVES_PREREG_PROVISIONAL",
    },
    "null": {"NULL_LOCAL", "NULL", "KILLED"},
    "not_testable": {"NOT_TESTABLE", "NOT_REPLICABLE_NO_CORPUS", "REPLICATION_BLOCKED"},
    "failed_replication": {"FAILED_REPLICATION", "FAILED_REPLICATION_POWER_ANNOTATED", "REJECT"},
}


def _bucket(verdict: str) -> str:
    for name, members in BUCKETS.items():
        if verdict in members:
            return name
    return "other"


def _read_verdicts(path: Path) -> Counter:
    c = Counter()
    if not path.exists():
        return c
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            c[_bucket(d.get("verdict", "MISSING"))] += 1
    return c


def build() -> dict:
    order = ["confirmed", "null", "not_testable", "failed_replication", "other"]
    sports = []
    for name, path in LEDGERS:
        counts = _read_verdicts(path)
        total = sum(counts.values())
        sports.append({
            "sport": name,
            "source": str(path.relative_to(ROOT)),
            "total": total,
            **{k: counts.get(k, 0) for k in order},
        })
    total_confirmed = sum(s["confirmed"] for s in sports)
    total_null = sum(s["null"] for s in sports)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
        "bucket_order": order,
        "headline": (
            f"nulls ({total_null}) outnumber confirms ({total_confirmed}) "
            f"{total_null / max(total_confirmed, 1):.1f}x -- we publish our nulls"
        ),
        "sports": sports,
    }


def _plot(data: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = data["bucket_order"]
    colors = {
        "confirmed": "#2ca02c",
        "null": "#7f7f7f",
        "not_testable": "#bcbd22",
        "failed_replication": "#d62728",
        "other": "#9467bd",
    }
    sports = data["sports"]
    labels = [s["sport"] for s in sports]

    fig, ax = plt.subplots(figsize=(10, 6))
    bottoms = [0] * len(sports)
    for bucket in order:
        vals = [s[bucket] for s in sports]
        ax.bar(labels, vals, bottom=bottoms, label=bucket, color=colors[bucket])
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    for i, s in enumerate(sports):
        ax.text(i, s["total"] + max(bottoms) * 0.01, str(s["total"]), ha="center", fontsize=9)

    ax.set_ylabel("verdict count")
    ax.set_title("Validation ledger verdicts by domain -- honesty at scale")
    ax.legend(loc="upper right", fontsize=8)
    ax.annotate(
        data["headline"],
        xy=(0.5, -0.15), xycoords="axes fraction",
        ha="center", fontsize=10, style="italic",
    )
    fig.tight_layout()
    IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG_PATH, dpi=130)
    plt.close(fig)


def main(check: bool = False):
    data = build()
    if check:
        assert data["sports"], "no ledgers read"
        assert sum(s["total"] for s in data["sports"]) > 0, "all ledgers empty"
        print("check ok:", json.dumps({s["sport"]: s["total"] for s in data["sports"]}))
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _plot(data)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {IMG_PATH}")
    print(data["headline"])


if __name__ == "__main__":
    import sys
    main(check="--check" in sys.argv)
