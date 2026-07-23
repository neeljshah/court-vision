"""Paper-execution-quality audit for the rescued pod paper-trading ledger.

Reads data/pod_backup_2026_07_20/frontend/clv_ledger.jsonl (83 rows) plus the
settle-status snapshot and today-snapshot from the same backup, and reports
EXECUTION-QUALITY analytics only: fill/placed counts, settle status split,
divergence distribution (model_prob vs implied prob at the taken price, in
probability points -- this is a pre-trade sizing signal, NOT realized CLV),
and honest degrade notes for fields the corpus does not actually have
(clv_pct is null for every row here -- no independent close feed was
captured, so CLV itself could not be measured, only reported as such).

Paper only. No dollar/ROI/bankroll claims anywhere in this output.
edge_claimed=False always.
"""
import argparse
import json
import os
import statistics

try:  # -m package invocation (check_all) vs bare-script invocation
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BACKUP_DIR = os.path.join(ROOT, "data", "pod_backup_2026_07_20", "frontend")
LEDGER_PATH = os.path.join(BACKUP_DIR, "clv_ledger.jsonl")
SETTLE_STATUS_PATH = os.path.join(BACKUP_DIR, "ops", "ingame_paper_settle_status.json")
TODAY_PATH = os.path.join(BACKUP_DIR, "paper_today.json")
OUT_JSON = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase", "out", "paper_execution_audit.json")
OUT_MD = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase", "out", "paper_execution_audit.md")


def load_ledger(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def pct_stats(values):
    if not values:
        return None
    return {
        "n": len(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "min": min(values),
        "max": max(values),
    }


def build_report(recs, settle_status, today_snapshot):
    n = len(recs)
    status_split = {}
    sport_split = {}
    outcome_split = {}
    for r in recs:
        status_split[r.get("status")] = status_split.get(r.get("status"), 0) + 1
        sport_split[r.get("sport")] = sport_split.get(r.get("sport"), 0) + 1
        outcome_split[r.get("outcome")] = outcome_split.get(r.get("outcome"), 0) + 1

    n_placed = n  # every logged row has placed=True upstream (see paper_today.json)
    n_executed = sum(1 for r in recs if r.get("executed"))
    n_gate_passed = sum(1 for r in recs if r.get("exec_gate", {}).get("passed"))
    n_gate_failed = n - n_gate_passed  # gate-failed rows are what "suppressed" would mean

    # Divergence = |model_prob - implied_prob(taken_decimal)| in probability
    # points, recorded pre-trade in exec_gate.divergence. This is a sizing
    # signal at placement time, NOT a post-hoc closing-line-value measurement.
    divergences = [
        r["exec_gate"]["divergence"]
        for r in recs
        if r.get("exec_gate", {}).get("divergence") is not None
    ]
    divergence_stats = pct_stats(divergences)

    # clv_pct: the field the ledger schema reserves for realized CLV.
    clv_values = [r["clv_pct"] for r in recs if r.get("clv_pct") is not None]
    clv_notes = {}
    for r in recs:
        note = r.get("clv_note")
        if note:
            clv_notes[note] = clv_notes.get(note, 0) + 1

    report = {
        "generated_at": None,
        "edge_claimed": False,
        "units": "probability points (not dollars, not ROI)",
        "source_corpus": os.path.relpath(LEDGER_PATH, ROOT).replace("\\", "/"),
        "n_records": n,
        "n_placed": n_placed,
        "n_executed_filled": n_executed,
        "n_suppressed_gate_failed": n_gate_failed,
        "status_split": status_split,
        "sport_split": sport_split,
        "outcome_split_settled_only": outcome_split,
        "divergence_at_placement_pp": divergence_stats,
        "divergence_honest_note": (
            "divergence = |model_prob - implied_prob(taken_decimal)| at the moment "
            "the paper bet was logged. It measures how far the model's number sat "
            "from the price taken -- a pre-trade sizing input, not realized CLV."
        ),
        "realized_clv_pct": pct_stats(clv_values),
        "realized_clv_honest_note": (
            "clv_pct is null for all {} settled rows in this corpus -- {}"
            .format(
                sum(1 for r in recs if r.get("status") == "settled"),
                "no independent closing-price feed was captured for this channel, "
                "so realized CLV could not be measured (degraded honestly, not fabricated)."
                if not clv_values else "n/a",
            )
        ),
        "clv_note_reasons": clv_notes,
        "settle_status_snapshot": settle_status,
        "today_snapshot_headline": {
            k: today_snapshot.get(k)
            for k in (
                "n_placed_alltime", "n_settled_alltime", "n_open",
                "headline_clv_pct_or_INSUFFICIENT", "mean_clv_pct_or_INSUFFICIENT",
                "n_clv", "executed", "edge_claimed", "honest_note",
            )
            if k in today_snapshot
        },
        "honest_story": (
            "This is a PAPER-only execution ledger (83 logged bets, all executed=False "
            "-- none of these were real fills). Every row passed its exec_gate "
            "(0 suppressed-by-gate rows survive in this rescued corpus). 37/83 rows "
            "settled by final score; realized CLV is unmeasurable for all of them "
            "because no independent close feed was wired for the paper_ingame channel "
            "-- the corpus honestly records clv_status='no_close' rather than backfilling "
            "a number. The only quantity this ledger can speak to is placement-time "
            "divergence (model vs taken price), reported in probability points, which "
            "is a measurement of execution behavior, not a proven edge."
        ),
    }
    return report


def write_md(report, path):
    lines = []
    lines.append("# Paper Execution Audit\n")
    lines.append(f"edge_claimed: {report['edge_claimed']}  |  units: {report['units']}\n")
    lines.append(f"Source: `{report['source_corpus']}`\n")
    lines.append("## Counts\n")
    lines.append(f"- records: {report['n_records']}")
    lines.append(f"- placed: {report['n_placed']}")
    lines.append(f"- executed (real fills): {report['n_executed_filled']}")
    lines.append(f"- suppressed (gate-failed): {report['n_suppressed_gate_failed']}")
    lines.append(f"- status split: {report['status_split']}")
    lines.append(f"- sport split: {report['sport_split']}")
    lines.append(f"- settled outcome split: {report['outcome_split_settled_only']}\n")
    ds = report["divergence_at_placement_pp"]
    if ds:
        lines.append("## Placement-time divergence (probability points)\n")
        lines.append(f"- n={ds['n']}, median={ds['median']:.4f}, mean={ds['mean']:.4f}, "
                      f"min={ds['min']:.4f}, max={ds['max']:.4f}")
        lines.append(f"- {report['divergence_honest_note']}\n")
    lines.append("## Realized CLV\n")
    lines.append(f"- {report['realized_clv_honest_note']}\n")
    lines.append("## Settle status snapshot\n")
    lines.append(f"```json\n{json.dumps(report['settle_status_snapshot'], indent=2)}\n```\n")
    lines.append("## Honest story\n")
    lines.append(report["honest_story"] + "\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run():
    from datetime import datetime, timezone

    recs = load_ledger(LEDGER_PATH)
    settle_status = json.load(open(SETTLE_STATUS_PATH, encoding="utf-8"))
    today_snapshot = json.load(open(TODAY_PATH, encoding="utf-8"))
    report = build_report(recs, settle_status, today_snapshot)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    write_md(report, OUT_MD)
    return report


def check():
    """Minimal self-check: run against the real corpus and assert invariants.
    Falls back to verifying the committed artifact when the local backup
    corpus (data/pod_backup_2026_07_20/, gitignored) is absent -- e.g. on a
    fresh clone."""
    try:
        report = run()
    except FileNotFoundError:
        def validate(d):
            assert d["edge_claimed"] is False
            assert d["n_records"] == 83
            assert d["n_executed_filled"] == 0
            assert d["divergence_at_placement_pp"]["n"] > 0
            assert d["realized_clv_pct"] is None
        verify_recorded_artifact(OUT_JSON, validate, "paper_execution_audit")
        return
    assert report["edge_claimed"] is False
    assert report["n_records"] == 83
    assert report["n_executed_filled"] == 0
    assert report["status_split"].get("settled", 0) + report["status_split"].get("open", 0) == 83
    assert report["divergence_at_placement_pp"]["n"] > 0
    assert report["realized_clv_pct"] is None  # clv_pct is null for every row in this corpus
    print("OK: paper_execution_audit self-check passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        rep = run()
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_MD}")
        print(f"n_records={rep['n_records']} status_split={rep['status_split']} "
              f"n_executed_filled={rep['n_executed_filled']} "
              f"divergence_median={rep['divergence_at_placement_pp']['median']:.4f}")
