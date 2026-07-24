"""Mechanism-ledger EXPORT -- surface every verdict row we already committed.

287 verdict rows live in domains/*/knowledge/validation_ledger.jsonl (4 sports)
but nothing renders them. This dumps them: per sport, every named mechanism with
its verdict, an evidence pointer (corpus + note), and as_of (run_ts if recorded);
plus per-sport and overall verdict-bucket counts.

A NULL / REJECT / NOT_TESTABLE is honest market-efficiency evidence, not a
failure. This is a measurement-hygiene artifact, not a betting product -- no
$/edge/ROI claim.

The ledgers are COMMITTED (not under data/), so --check re-derives from source on
a fresh clone. If the source is ever absent it falls back to structurally
verifying the recorded out/ artifact (house convention).

Usage:
    python -m scripts.platformkit.analytics_showcase.mechanism_ledger_export
    python -m scripts.platformkit.analytics_showcase.mechanism_ledger_export --check
"""
import argparse
import collections
import glob
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# Canonical premise-checked path only -- NOT the .pre_squash_*.bak snapshots.
LEDGER_GLOB = os.path.join(REPO_ROOT, "domains", "*", "knowledge", "validation_ledger.jsonl")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "mechanism_ledger_export.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "mechanism_ledger_export.png")

# Three-bucket normalization of the raw ledger verdict vocabulary.
CONFIRMED_VERDICTS = {"CONFIRMED_LOCAL", "CONFIRMED_LOCAL_incl_2026_OOS", "REPLICATED", "ARTIFACT_CONFIRMED"}
NOT_TESTABLE_VERDICTS = {"NOT_TESTABLE", "NOT_REPLICABLE_NO_CORPUS"}
BUCKETS = ("confirmed", "null", "not_testable")


def bucket(verdict):
    if verdict in CONFIRMED_VERDICTS:
        return "confirmed"
    if verdict in NOT_TESTABLE_VERDICTS:
        return "not_testable"
    return "null"  # NULL, NULL_LOCAL, REJECT, PARTIAL, PROVISIONAL, FAILED_REPLICATION, ...


def sport_from_path(path):
    # .../domains/<sport>/knowledge/validation_ledger.jsonl
    return os.path.basename(os.path.dirname(os.path.dirname(path)))


def load_ledgers():
    """Return {sport: [row, ...]}, sport keyed off the directory (not the row's
    'sport' field, which is occasionally absent)."""
    by_sport = collections.OrderedDict()
    for path in sorted(glob.glob(LEDGER_GLOB)):
        sport = sport_from_path(path)
        rows = by_sport.setdefault(sport, [])
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return by_sport


def evidence_pointer(row):
    corpus = row.get("corpus")
    note = row.get("note")
    parts = []
    if corpus:
        parts.append(f"corpus={corpus}")
    if row.get("n") is not None:
        parts.append(f"n={row['n']}")
    if note:
        parts.append(note)
    return "; ".join(parts) if parts else None


def export_mechanism(row):
    verdict = row.get("verdict")
    return {
        "mechanism": row.get("hypothesis"),
        "verdict": verdict,
        "bucket": bucket(verdict),
        "effect": row.get("effect"),
        "p": row.get("p"),
        "corpus": row.get("corpus"),
        "evidence": evidence_pointer(row),
        "as_of": row.get("run_ts"),  # null when the run predates run_ts stamping
        "edge_claimed": bool(row.get("edge_claimed", False)),
    }


def counts(mechanisms):
    c = collections.Counter(m["bucket"] for m in mechanisms)
    return {b: c.get(b, 0) for b in BUCKETS} | {"total": len(mechanisms)}


def build():
    by_sport_rows = load_ledgers()
    sports = {}
    overall = []
    for sport, rows in by_sport_rows.items():
        mechs = [export_mechanism(r) for r in rows]
        # Stable, readable order: confirmed first, then null, then not-testable, name-sorted.
        mechs.sort(key=lambda m: (BUCKETS.index(m["bucket"]), m["mechanism"] or ""))
        overall.extend(mechs)
        sports[sport] = {"counts": counts(mechs), "mechanisms": mechs}

    return {
        "source": "domains/*/knowledge/validation_ledger.jsonl (4 sports, premise-checked)",
        "note": (
            "Every named mechanism we have tested, with its recorded verdict and evidence "
            "pointer. A NULL/REJECT/NOT_TESTABLE is honest market-efficiency evidence, not a "
            "failure. Measurement-hygiene artifact -- no $/edge/ROI claim. as_of is the "
            "recorded run_ts (null for runs that predate run_ts stamping)."
        ),
        "verdict_buckets": {
            "confirmed": sorted(CONFIRMED_VERDICTS),
            "not_testable": sorted(NOT_TESTABLE_VERDICTS),
            "null": "everything else (NULL, NULL_LOCAL, REJECT, PARTIAL, PROVISIONAL, FAILED_REPLICATION)",
        },
        "overall_counts": counts(overall),
        "by_sport": sports,
        "edge_claimed": False,
    }


def render_png(result, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sports = list(result["by_sport"].keys())
    colors = {"confirmed": "#4C9A5B", "null": "#B0752C", "not_testable": "#8A8A8A"}
    fig, ax = plt.subplots(figsize=(10, 6))
    left = [0] * len(sports)
    for b in BUCKETS:
        vals = [result["by_sport"][s]["counts"][b] for s in sports]
        ax.barh(sports, vals, left=left, color=colors[b], label=b.replace("_", "-"))
        for i, (v, l) in enumerate(zip(vals, left)):
            if v:
                ax.text(l + v / 2, i, str(v), va="center", ha="center", fontsize=8, color="white")
        left = [l + v for l, v in zip(left, vals)]
    ax.invert_yaxis()
    ax.set_xlabel("mechanisms tested (verdict rows)")
    oc = result["overall_counts"]
    ax.set_title(
        f"Mechanism-ledger verdict distribution by sport -- {oc['total']} rows "
        f"(confirmed {oc['confirmed']} / null {oc['null']} / not-testable {oc['not_testable']})"
    )
    ax.legend(loc="lower right", fontsize=8)
    fig.text(0.5, 0.01,
             "NULL/REJECT/NOT_TESTABLE = honest market-efficiency evidence. No $/edge/ROI claim.",
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def _validate(data):
    assert data["overall_counts"]["total"] > 0, "no mechanisms exported"
    assert data["by_sport"], "no sports"
    per_sport_total = sum(v["counts"]["total"] for v in data["by_sport"].values())
    assert per_sport_total == data["overall_counts"]["total"], "sport totals != overall"
    for s, v in data["by_sport"].items():
        assert sum(v["counts"][b] for b in BUCKETS) == v["counts"]["total"], f"{s}: buckets != total"
        assert data["edge_claimed"] is False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        if glob.glob(LEDGER_GLOB):
            result = build()
            _validate(result)
            print("mechanism_ledger_export --check OK:", result["overall_counts"])
        else:
            # Fresh clone with domains/ absent -- verify the committed artifact instead.
            try:
                from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
            except ImportError:
                from _clone_safe import verify_recorded_artifact
            verify_recorded_artifact(OUT_JSON, _validate, "mechanism_ledger_export")
        return

    result = build()
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    render_png(result, OUT_PNG)
    print("wrote", OUT_JSON)
    print("wrote", OUT_PNG)
    print("overall_counts:", result["overall_counts"])
    for s, v in result["by_sport"].items():
        print(f"  {s}:", v["counts"])


if __name__ == "__main__":
    main()
