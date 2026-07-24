"""Verdict flip anatomy -- dissect the claim families that changed their mind.

Pure reshaping of ONE already-committed artifact (fwd_claim_scoreboard.json):
pulls out the 5 flipped claim families and walks each one's verdict history in
order, plus the 7 retracted families and what killed them. No new data, no new
science -- just an honest re-statement of mind-changes already on the record.

Why this matters: a claim family that flips (NULL -> CONFIRMED, or the reverse)
looks alarming out of context. In a system that preregisters hypotheses and
re-tests them as more data arrives, a flip is the self-grading process working
-- not a sign the earlier verdict was careless.

DESCRIPTIVE_ONLY, edge_claimed=False -- no $/ROI claim, no new corpus.

Usage:
    python -m scripts.platformkit.analytics_showcase.verdict_flip_anatomy
    python -m scripts.platformkit.analytics_showcase.verdict_flip_anatomy --check
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_JSON = os.path.join(SHOWCASE, "out", "fwd_claim_scoreboard.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "verdict_flip_anatomy.json")


def _parse_ts(s):
    if not s or s == "undated":
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_lived(first_seen, last_seen):
    a, b = _parse_ts(first_seen), _parse_ts(last_seen)
    if a is None or b is None:
        return None
    return (b - a).days


def _one_line(verdict_sequence, history):
    first, last = history[0], history[-1]
    return (f"First {verdict_sequence[0]} on n={first['n']} ({first['corpus']}), "
            f"then {verdict_sequence[-1]} on n={last['n']} ({last['corpus']}).")


def _what_killed_it(history):
    last = history[-1]
    return f"{last['verdict']} on corpus '{last['corpus']}' (n={last['n']}, effect={last['effect']})"


def _build_flips(flipped_families):
    flips = []
    for f in flipped_families:
        steps = [
            {"verdict": h["verdict"], "status": h["status"], "corpus": h["corpus"],
             "n": h["n"], "effect": h["effect"], "run_ts": h["run_ts"]}
            for h in f["history"]
        ]
        flips.append({
            "sport": f["sport"],
            "hypothesis": f["hypothesis"],
            "current_status": f["current_status"],
            "verdict_sequence": f["verdict_sequence"],
            "steps": steps,
            "one_line": _one_line(f["verdict_sequence"], f["history"]),
        })
    return flips


def _build_retracted(families):
    retracted = []
    for f in families:
        if f.get("current_status") != "retracted":
            continue
        retracted.append({
            "sport": f["sport"],
            "hypothesis": f["hypothesis"],
            "first_run_ts": f["first_seen"],
            "last_run_ts": f["last_seen"],
            "days_lived": _days_lived(f["first_seen"], f["last_seen"]),
            "n_history_rows": len(f["history"]),
            "what_killed_it": _what_killed_it(f["history"]),
        })
    return retracted


def build():
    with open(IN_JSON, encoding="utf-8") as f:
        source = json.load(f)

    families = source["families"]
    flipped_families = source["flipped_families"]
    by_status = source["summary"]["by_status"]

    flips = _build_flips(flipped_families)
    retracted = _build_retracted(families)

    n_history_rows_total = sum(len(f["history"]) for f in families)
    n_with_run_ts = sum(1 for f in families for h in f["history"] if h["run_ts"])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (f"{len(flipped_families)} claim families changed their verdict as more "
                      "data arrived; here is each mind-change, in sequence."),
        "method": ("These are our own preregistered re-tests: verdict history per claim family "
                   "(sport x hypothesis) ordered by run_ts, current status = last entry. A verdict "
                   "flip means the system re-tested and updated its own earlier claim as more or "
                   "re-cleaned data arrived -- that is the process working, not a bug."),
        "source_artifact": "scripts/platformkit/analytics_showcase/out/fwd_claim_scoreboard.json",
        "summary": {
            "n_families": source["summary"]["n_families"],
            "verified": by_status.get("verified", 0),
            "null": by_status.get("null", 0),
            "retracted": by_status.get("retracted", 0),
            "not_testable": by_status.get("not_testable", 0),
            "provisional": by_status.get("provisional", 0),
        },
        "flips": flips,
        "retracted": retracted,
        "dating_coverage": {
            "n_history_rows_total": n_history_rows_total,
            "n_with_run_ts": n_with_run_ts,
            "note": ("run_ts is present on only some rows; undated flips show sequence "
                      "without dates."),
        },
        "confounds": [
            "5 flips is a small, anecdotal set -- this is qualitative case study, not a rate.",
            "run_ts is missing on many history rows, so 'days-lived' is a lower bound and "
            "some flips are undated.",
            "a flip reflects more/re-cleaned data arriving, NOT that the earlier verdict was "
            "careless.",
        ],
    }
    if not retracted and by_status.get("retracted", 0) > 0:
        payload["retracted_note"] = (
            "source summary counts retracted families but none could be derived by "
            "current_status=='retracted' -- emitting empty list rather than guessing.")

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _print_summary(payload):
    print(payload["headline"])
    print(f"n_flips={len(payload['flips'])}  n_retracted={len(payload['retracted'])}")
    dc = payload["dating_coverage"]
    print(f"dating_coverage: {dc['n_with_run_ts']}/{dc['n_history_rows_total']} history rows have run_ts")
    for fl in payload["flips"]:
        print(f"  [{fl['sport']}] {fl['hypothesis']}: {' -> '.join(fl['verdict_sequence'])}")


def check():
    payload = build()
    with open(IN_JSON, encoding="utf-8") as f:
        source = json.load(f)

    assert len(payload["flips"]) == len(source["flipped_families"]), "flip count mismatch"

    hist_by_key = {(f["sport"], f["hypothesis"]): f["history"] for f in source["families"]}
    for fl in payload["flips"]:
        key = (fl["sport"], fl["hypothesis"])
        assert key in hist_by_key, key
        assert len(fl["steps"]) == len(hist_by_key[key]), (key, "step count mismatch")

    by_status = source["summary"]["by_status"]
    s = payload["summary"]
    assert s["n_families"] == source["summary"]["n_families"], "n_families mismatch"
    for k in ("verified", "null", "retracted", "not_testable", "provisional"):
        assert s[k] == by_status.get(k, 0), (k, s[k], by_status.get(k, 0))

    for r in payload["retracted"]:
        dl = r["days_lived"]
        assert dl is None or (isinstance(dl, int) and dl >= 0), (r["hypothesis"], dl)

    def _no_nan(x):
        if isinstance(x, float):
            assert not math.isnan(x) and not math.isinf(x)
        elif isinstance(x, dict):
            for v in x.values():
                _no_nan(v)
        elif isinstance(x, list):
            for v in x:
                _no_nan(v)

    _no_nan(payload)
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        _print_summary(p)
