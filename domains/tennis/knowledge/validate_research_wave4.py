"""domains.tennis.knowledge.validate_research_wave4 -- research-wave-4
UNTESTED row #39 (within-tournament ace-rate drift by round, a surface-
speed-drift proxy) from domains/tennis/knowledge/mechanisms.md, seeded by
226391a3. Mirrors wave2/wave3's run/run_split_half shape.

Premise-check (this session, fresh reads): `matches.parquet` (ATP-only,
30,616 rows, the SAME scope #39's premise-check text cites -- deliberately
NOT `load_matches()`'s ATP+WTA concat, to stay inside the exact corpus that
was premise-checked) joined to `match_stats.parquet` (59,312 rows, columns
`event_id`/`p1_ace_rate`/`p2_ace_rate` confirmed) via `event_id`: 100% join
coverage (30,616/30,616), confirmed round-bucket sizes early=22,873/
late=4,827 (RR/BR excluded as ambiguous), and 675 distinct `tourney_id`
values with >=3 matches in BOTH buckets -- all four numbers reproduce #39's
premise-check text exactly.

Design: paired-by-`tourney_id` unit (not paired-by-match) -- one
(late-round-mean minus early-round-mean) combined-ace-rate gap per
qualifying `tourney_id`, one-sample t-test of that gap array against 0
(equivalent to a paired t-test between the two per-tournament mean series).
Split-half by `tourney_id` PARITY (even/odd of an md5 hash of the
`tourney_id` string, since `tourney_id` is not guaranteed numeric across
ATP), per #39's own declared test-spec text -- the >=2-independent-groups
evidence the honesty bar requires behind an affirmative verdict.

Leak audit: same-tournament, already-played rounds only (no as-of/forecast
ingredient, no cross-tournament pooling) -- same structural/contemporaneous
leak posture as wave3's #37/#38.

Run: python -m domains.tennis.knowledge.validate_research_wave4
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

import pandas as pd
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, TENNIS_DIR, load_match_stats
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_TOURNEYS = 50          # declared floor, this validator (mirrors wave3's MIN_BREAKS pattern)
MIN_EFFECT_39 = 0.01        # declared bar, mechanisms.md #39: |eff|>=0.01 (ace-rate points)
EARLY_ROUNDS = {"R128", "R64", "R32", "R16"}
LATE_ROUNDS = {"QF", "SF", "F"}


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and p != p):  # NaN-safe
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _load_joined() -> pd.DataFrame:
    """ATP-only matches.parquet (30,616 rows -- the exact scope #39's
    premise check cites) joined to match_stats.parquet on event_id."""
    m = pd.read_parquet(TENNIS_DIR / "matches.parquet")
    ms = load_match_stats()
    j = m.merge(ms[["event_id", "p1_ace_rate", "p2_ace_rate"]], on="event_id", how="inner")
    j["ace_rate"] = (j["p1_ace_rate"] + j["p2_ace_rate"]) / 2.0
    j["bucket"] = j["round"].where(j["round"].isin(EARLY_ROUNDS), None)
    j.loc[j["round"].isin(LATE_ROUNDS), "bucket"] = "late"
    j.loc[j["round"].isin(EARLY_ROUNDS), "bucket"] = "early"
    return j


def _tourney_gaps(j: pd.DataFrame) -> pd.Series:
    """Per-`tourney_id` (late-mean minus early-mean) combined-ace-rate gap,
    restricted to tourney_ids with >=3 matches in BOTH buckets."""
    sub = j.dropna(subset=["bucket", "ace_rate"])
    counts = sub.groupby(["tourney_id", "bucket"]).size().unstack(fill_value=0)
    qualifying = counts[(counts.get("early", 0) >= 3) & (counts.get("late", 0) >= 3)].index
    means = sub[sub["tourney_id"].isin(qualifying)].groupby(["tourney_id", "bucket"])["ace_rate"].mean().unstack()
    return (means["late"] - means["early"]).dropna()


def surface_speed_drift_by_round(j: pd.DataFrame, hyp: str = "surface_speed_drift_by_round") -> Dict[str, Any]:
    gaps = _tourney_gaps(j)
    n = len(gaps)
    if n < MIN_TOURNEYS:
        return {"hypothesis": hyp, "n": n, "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d qualifying tourney_ids (>=3 matches both buckets)" % MIN_TOURNEYS}
    t, p = stats.ttest_1samp(gaps.to_numpy(), 0.0)
    eff = float(gaps.mean())
    return {"hypothesis": hyp, "n": n, "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, MIN_EFFECT_39),
            "note": "late-round mean ace rate minus early-round mean ace rate, paired by tourney_id "
                    "(n=%d qualifying tournaments), one-sample t=%.3f" % (n, t)}


def _tourney_half(tourney_id: str) -> bool:
    """True="A", False="B" -- even/odd of an md5 hash of the tourney_id
    string (not assumed numeric across ATP)."""
    return int(hashlib.md5(str(tourney_id).encode("ascii", "replace")).hexdigest(), 16) % 2 == 0


def _stamp_and_write(rows: List[Dict[str, Any]], corpus: str) -> List[Dict[str, Any]]:
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = corpus
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def run() -> List[Dict[str, Any]]:
    j = _load_joined()
    return _stamp_and_write([surface_speed_drift_by_round(j)], "matches_match_stats")


def run_split_half() -> List[Dict[str, Any]]:
    """Even/odd tourney_id-hash split -- the >=2-independent-groups evidence
    the honesty bar requires behind an affirmative (CONFIRMED_LOCAL)
    verdict, per #39's own declared test-spec text."""
    j = _load_joined()
    half_of = j["tourney_id"].map(_tourney_half)
    rows: List[Dict[str, Any]] = []
    for half, is_a in (("A", True), ("B", False)):
        rows.append(surface_speed_drift_by_round(
            j[half_of == is_a], "surface_speed_drift_by_round__split_%s" % half))
    return _stamp_and_write(rows, "matches_match_stats__split_half")


def main() -> int:
    for r in run() + run_split_half():
        print("%-42s %-14s n=%-6s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    assert _tourney_half("100") != _tourney_half("101")  # different hashes typically split
    print("self-check OK")
