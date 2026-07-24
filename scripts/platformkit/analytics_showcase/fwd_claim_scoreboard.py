"""Forward-graded claim scoreboard: every claim family's post-publication track record.

The product IS the self-grading. From the per-sport validation ledgers
(domains/<sport>/knowledge/validation_ledger.jsonl) this builds, for each claim
family (sport x hypothesis), its verdict history over time, first-seen date,
and current status -- verified / null / not_testable / retracted / provisional.
Families whose verdict FLIPPED across runs (e.g. confirmed -> failed replication,
or null -> confirmed) are surfaced explicitly: an honest retraction is the whole
point, not a blemish.

Headline honest ratio = nulls-or-worse vs confirms across families. A system that
only ever "confirmed" would be lying; the ratio is the credibility receipt.

edge_claimed=False. This is a calibration/honesty exhibit, not a betting signal.

Data source: 4 git-tracked ledgers (present on a fresh clone). On the off chance
they are absent, --check falls back to verifying the committed out/ artifact.

Usage:
    python -m scripts.platformkit.analytics_showcase.fwd_claim_scoreboard
    python -m scripts.platformkit.analytics_showcase.fwd_claim_scoreboard --check
"""
import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

try:  # -m package invocation (check_all) vs bare-script invocation
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_JSON = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase", "out", "fwd_claim_scoreboard.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "fwd_claim_scoreboard.png")
SPORTS = ["basketball_nba", "mlb", "soccer", "tennis"]

# Canonical status for every ledger verdict token seen in the corpus. Anything
# unmapped falls to "other" so a new token is visible, never silently dropped.
STATUS_MAP = {
    "CONFIRMED_LOCAL": "verified",
    "CONFIRMED_LOCAL_incl_2026_OOS": "verified",
    "REPLICATED": "verified",
    "ARTIFACT_CONFIRMED": "verified",
    "NULL": "null",
    "NULL_LOCAL": "null",
    "NOT_TESTABLE": "not_testable",
    "NOT_REPLICABLE_NO_CORPUS": "not_testable",
    "FAILED_REPLICATION": "retracted",
    "REJECT": "retracted",
    "PROVISIONAL": "provisional",
    "PARTIAL": "provisional",
}
STATUS_ORDER = ["verified", "provisional", "null", "not_testable", "retracted", "other"]
# ponytail: undated rows (pre-squash, no run_ts) sort before dated ones with this
# sentinel -- earliest-unknown. Real run_ts strings are ISO and sort lexically.
UNDATED = ""


def _ledger_path(sport: str) -> str:
    return os.path.join(ROOT, "domains", sport, "knowledge", "validation_ledger.jsonl")


def load_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sport in SPORTS:
        path = _ledger_path(sport)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("hypothesis") and d.get("verdict"):
                    d["sport"] = sport  # ponytail: trust the dir we read from, not the row's own (drifted) label
                    rows.append(d)
    return rows


def status_of(verdict: str) -> str:
    return STATUS_MAP.get(verdict, "other")


def build_families(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group rows into claim families keyed by (sport, hypothesis). Within a
    family, order entries by (run_ts, original index) so undated pre-squash rows
    come first and the LAST entry defines the current status."""
    grouped: Dict[Tuple[str, str], List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for idx, r in enumerate(rows):
        grouped[(r["sport"], r["hypothesis"])].append((idx, r))

    families: List[Dict[str, Any]] = []
    for (sport, hyp), items in grouped.items():
        items.sort(key=lambda t: (t[1].get("run_ts") or UNDATED, t[0]))
        history = [
            {
                "verdict": r.get("verdict"),
                "status": status_of(r.get("verdict")),
                "run_ts": r.get("run_ts"),
                "corpus": r.get("corpus"),
                "n": r.get("n"),
                "effect": r.get("effect"),
            }
            for _, r in items
        ]
        dated = [h["run_ts"] for h in history if h["run_ts"]]
        distinct_statuses = {h["status"] for h in history}
        current = history[-1]["status"]
        families.append({
            "sport": sport,
            "hypothesis": hyp,
            "n_entries": len(history),
            "first_seen": min(dated) if dated else "undated",
            "last_seen": max(dated) if dated else "undated",
            "current_status": current,
            "flipped": len(distinct_statuses) > 1,
            "verdict_sequence": [h["verdict"] for h in history],
            "history": history,
        })
    families.sort(key=lambda fam: (fam["sport"], fam["hypothesis"]))
    return families


def summarize(families: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_status_per_sport: Dict[str, Dict[str, int]] = {s: defaultdict(int) for s in SPORTS}
    totals: Dict[str, int] = defaultdict(int)
    for fam in families:
        by_status_per_sport[fam["sport"]][fam["current_status"]] += 1
        totals[fam["current_status"]] += 1
    confirms = totals.get("verified", 0)
    nulls_or_worse = (totals.get("null", 0) + totals.get("not_testable", 0)
                      + totals.get("retracted", 0))
    denom = confirms if confirms else 1
    return {
        "n_families": len(families),
        "by_status": {k: totals.get(k, 0) for k in STATUS_ORDER if totals.get(k, 0)},
        "by_status_per_sport": {s: dict(v) for s, v in by_status_per_sport.items() if v},
        "confirms": confirms,
        "nulls_or_worse": nulls_or_worse,
        "honest_ratio_nulls_per_confirm": round(nulls_or_worse / denom, 3),
        "n_flipped": sum(1 for fam in families if fam["flipped"]),
    }


def make_chart(families: List[Dict[str, Any]], summary: Dict[str, Any], out_png: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {
        "verified": "#2e7d32", "provisional": "#f9a825", "null": "#9e9e9e",
        "not_testable": "#bdbdbd", "retracted": "#b3452c", "other": "#5c6bc0",
    }
    per_sport = summary["by_status_per_sport"]
    sports = [s for s in SPORTS if s in per_sport]
    fig, ax = plt.subplots(figsize=(9, 5))
    left = {s: 0 for s in sports}
    for status in STATUS_ORDER:
        widths = [per_sport.get(s, {}).get(status, 0) for s in sports]
        if not any(widths):
            continue
        ax.barh(sports, widths, left=[left[s] for s in sports],
                color=colors[status], label=status)
        for s, w in zip(sports, widths):
            left[s] += w
    ax.set_xlabel("claim families (current status)")
    ax.set_title("Forward-graded claim scoreboard: current status by sport")
    ax.legend(fontsize=8, ncol=3, loc="lower right")
    cap = (f"Source: domains/*/knowledge/validation_ledger.jsonl (as_of {summary['as_of']}). "
           f"{summary['n_families']} families, {summary['confirms']} verified, "
           f"{summary['nulls_or_worse']} null/not-testable/retracted, "
           f"{summary['n_flipped']} flipped verdict over time. Calibration/honesty exhibit, edge_claimed=False.")
    fig.text(0.5, 0.005, cap, ha="center", fontsize=6.5, color="gray", wrap=True)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def run() -> Dict[str, Any]:
    rows = load_rows()
    families = build_families(rows)
    summary = summarize(families)
    as_of = max((f["last_seen"] for f in families if f["last_seen"] != "undated"), default="undated")
    summary["as_of"] = as_of
    result: Dict[str, Any] = {
        "edge_claimed": False,
        "as_of": as_of,
        "method": ("Per claim family (sport x hypothesis) from the 4 validation ledgers: "
                   "verdict history ordered by run_ts, current status = last entry. "
                   "Families with >1 distinct status flagged flipped."),
        "story": ("The product is the self-grading. Nulls, not-testables and retractions "
                  "are kept in the ledger and counted; a system that only ever confirmed "
                  "would not be credible."),
        "n_ledger_rows": len(rows),
        "summary": summary,
        "flipped_families": [f for f in families if f["flipped"]],
        "families": families,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    if families:
        make_chart(families, summary, OUT_PNG)
    else:
        result["png_skipped_reason"] = "no claim families -- ledgers absent or empty"
    return result


def _rows_present() -> bool:
    return bool(load_rows())


def check() -> None:
    """Self-check. Probes ledger presence FIRST: run() overwrites OUT_JSON, so
    when the tracked ledgers are somehow absent we verify the committed artifact
    instead of clobbering it with an empty result."""
    if not _rows_present():
        def validate(d: Dict[str, Any]) -> None:
            assert d.get("families"), "expected at least one claim family"
            s = d["summary"]
            assert s["confirms"] + s["nulls_or_worse"] <= s["n_families"], "status counts exceed families"
        verify_recorded_artifact(OUT_JSON, validate, "fwd_claim_scoreboard")
        return
    # Invariant checks on live re-derivation.
    fams = build_families(load_rows())
    assert fams, "expected at least one claim family"
    for fam in fams:
        assert fam["current_status"] == fam["history"][-1]["status"], "current status != last entry"
        assert fam["flipped"] == (len({h["status"] for h in fam["history"]}) > 1), "flip flag mismatch"
    # run_ts ordering: dated entries within a family must be non-decreasing.
    for fam in fams:
        ts = [h["run_ts"] for h in fam["history"] if h["run_ts"]]
        assert ts == sorted(ts), f"history not time-ordered for {fam['hypothesis']}"
    result = run()
    assert os.path.exists(OUT_JSON)
    assert os.path.exists(OUT_PNG)
    assert result["summary"]["n_families"] == len(fams)
    print("OK: fwd_claim_scoreboard self-check passed "
          f"({result['summary']['n_families']} families, {result['summary']['n_flipped']} flipped)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({k: v for k, v in res.items() if k not in ("families", "flipped_families")}, indent=2)[:2500])
        print("flipped families:", [(f["sport"], f["hypothesis"], f["verdict_sequence"]) for f in res["flipped_families"]][:10])
