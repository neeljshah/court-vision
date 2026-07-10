"""domains.basketball_nba.knowledge.validate_q3_state -- Q3-state mechanism
seeds for the B11 handoff: sim2's global-worst PIT/CRPS bucket is P3|m3
(period 3, off-relative margin bucket 3 -- `_MARGIN_EDGES = (-15,-8,-3,3,8,15)`
in domains/basketball_nba/sim2/possession_model.py means bucket 3 is the
CLOSE band, off_margin in [-3, 3)). This module seeds 2 hypotheses that could
explain why that bucket is hardest to calibrate, using ONLY on-disk realized
quarter scores (no live PBP granularity exists locally at sub-quarter
resolution, so "entering Q3 close" is approximated by |first_half_margin|<3,
the SAME 3-point edge the sim bucket itself uses).

Two independent season corpora (`linescores.parquet` 2025-26, 1,313 games;
`linescores_2024_25.parquet` 2024-25, 1,321 games) give a genuine >=2-corpus
replication check, not split-half of one season.

  (a) q3_margin_vs_halftime_deficit -- is a team's Q3 own-margin correlated
      with its own first-half margin (own_q1+own_q2 - opp_q1-opp_q2)? A
      first-half-realized feature (legitimate in-game state, available at
      halftime -- not a live-mid-Q3 feature).
  (b) q3_volatility_close_halftime -- restricted to games close at half
      (|first_half_margin|<3, the sim's own margin-bucket-3 edge), is Q3's
      own-quarter-points stdev higher than Q2's and Q4's (Levene, same
      close-game subset both quarters)?

Descriptive/mechanism checks only -- neither is a live per-game feature.
No $/edge claimed. ASCII only.

Run: python -m domains.basketball_nba.knowledge.validate_q3_state
Test: python -m pytest domains/basketball_nba/knowledge/test_validate_q3_state.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_EFFECT_R = 0.15          # pearson r bar, matches the rest of this ledger
MIN_VOL_RATIO = 1.10         # Q3 stdev must exceed the comparison quarter's by >=10%
CLOSE_HALF_EDGE = 3.0        # matches sim2's own margin-bucket-3 edge exactly

_REPO = Path(__file__).resolve().parents[3]
_CORPORA = {
    "2025_26": _REPO / "data" / "domains" / "basketball_nba" / "linescores.parquet",
    "2024_25": _REPO / "data" / "domains" / "basketball_nba" / "linescores_2024_25.parquet",
}
_QCOLS = ("q1", "q2", "q3", "q4")


def _fmt_p(p: Optional[float]) -> str:
    return "nan" if (p is None or (isinstance(p, float) and np.isnan(p))) else "%.4g" % p


def team_game_quarters(linescores: pd.DataFrame, corpus: str) -> pd.DataFrame:
    """Long format, one row per (game, team side): own q1..q4 margins vs the
    opponent that game, first_half_margin, tagged with which corpus it came
    from. Pure own_quarter - opp_quarter, same convention as
    asof_quarter_shape.py::_derive_realized (not reused directly -- that
    helper only exposes the aggregated first/second-half + q1/q4 columns,
    not per-quarter q2/q3, both of which this module needs)."""
    h = {q: pd.to_numeric(linescores[f"home_{q}"], errors="coerce") for q in _QCOLS}
    a = {q: pd.to_numeric(linescores[f"away_{q}"], errors="coerce") for q in _QCOLS}
    date = pd.to_datetime(linescores["date"])
    rows = []
    for side, me, opp, team_col in (("home", h, a, "home_abbr"), ("away", a, h, "away_abbr")):
        d = pd.DataFrame({
            "date": date, "team": linescores[team_col], "side": side, "corpus": corpus,
            "q1_margin": me["q1"] - opp["q1"], "q2_margin": me["q2"] - opp["q2"],
            "q3_margin": me["q3"] - opp["q3"], "q4_margin": me["q4"] - opp["q4"],
        })
        d["first_half_margin"] = d["q1_margin"] + d["q2_margin"]
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def load_all_corpora() -> pd.DataFrame:
    frames = []
    for corpus, path in _CORPORA.items():
        if not path.exists():
            continue
        frames.append(team_game_quarters(pd.read_parquet(path), corpus))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _verdict_replicated(per_corpus_confirmed: Dict[str, Optional[bool]]) -> str:
    vals = list(per_corpus_confirmed.values())
    if all(v is None for v in vals):
        return "NOT_TESTABLE"
    if all(v is True for v in vals):
        return "REPLICATED"
    if any(v is True for v in vals):
        return "PARTIAL"
    return "NULL"


def q3_margin_vs_halftime_deficit(tg: pd.DataFrame) -> Dict[str, Any]:
    per_corpus: Dict[str, Any] = {}
    confirmed: Dict[str, Optional[bool]] = {}
    for corpus, d in tg.groupby("corpus"):
        d2 = d.dropna(subset=["first_half_margin", "q3_margin"])
        if len(d2) < 10:
            per_corpus[corpus] = {"r": None, "p": None, "n": int(len(d2))}
            confirmed[corpus] = None
            continue
        r, p = stats.pearsonr(d2["first_half_margin"], d2["q3_margin"])
        per_corpus[corpus] = {"r": round(float(r), 4), "p": float(p), "n": int(len(d2))}
        confirmed[corpus] = bool(p < ALPHA and abs(r) >= MIN_EFFECT_R)
    verdict = _verdict_replicated(confirmed)
    note = "; ".join(
        "%s: r=%s p=%s n=%s" % (c, v["r"], _fmt_p(v["p"]), v["n"]) for c, v in sorted(per_corpus.items()))
    return {
        "hypothesis": "q3_margin_vs_halftime_deficit", "verdict": verdict,
        "per_corpus": per_corpus,
        "note": "pearson r(first_half_margin, q3_margin) per corpus; negative=reversion "
                "(bigger halftime deficit -> bigger Q3 recovery), positive=persistence. " + note,
    }


def _quarter_std_compare(sub: pd.DataFrame, col_a: str, col_b: str) -> Dict[str, Any]:
    a, b = sub[col_a].dropna(), sub[col_b].dropna()
    if len(a) < 10 or len(b) < 10:
        return {"p": None, "std_a": None, "std_b": None, "n": int(min(len(a), len(b)))}
    _, p = stats.levene(a, b)
    return {"p": float(p), "std_a": round(float(a.std()), 3), "std_b": round(float(b.std()), 3),
            "n": int(min(len(a), len(b)))}


def q3_volatility_close_halftime(tg: pd.DataFrame) -> Dict[str, Any]:
    per_corpus: Dict[str, Any] = {}
    confirmed: Dict[str, Optional[bool]] = {}
    for corpus, d in tg.groupby("corpus"):
        close = d[d["first_half_margin"].abs() < CLOSE_HALF_EDGE].dropna(
            subset=["q2_margin", "q3_margin", "q4_margin"])
        vs_q2 = _quarter_std_compare(close, "q3_margin", "q2_margin")
        vs_q4 = _quarter_std_compare(close, "q3_margin", "q4_margin")
        per_corpus[corpus] = {"n_close_rows": int(len(close)), "vs_q2": vs_q2, "vs_q4": vs_q4}
        if vs_q2["p"] is None or vs_q4["p"] is None:
            confirmed[corpus] = None
            continue
        ok_q2 = vs_q2["p"] < ALPHA and vs_q2["std_a"] > vs_q2["std_b"] * MIN_VOL_RATIO
        ok_q4 = vs_q4["p"] < ALPHA and vs_q4["std_a"] > vs_q4["std_b"] * MIN_VOL_RATIO
        confirmed[corpus] = bool(ok_q2 and ok_q4)
    verdict = _verdict_replicated(confirmed)
    note = "; ".join(
        "%s: n_close=%d Q3std=%s vs Q2std=%s (p=%s), vs Q4std=%s (p=%s)"
        % (c, v["n_close_rows"], v["vs_q2"]["std_a"], v["vs_q2"]["std_b"], _fmt_p(v["vs_q2"]["p"]),
           v["vs_q4"]["std_b"], _fmt_p(v["vs_q4"]["p"]))
        for c, v in sorted(per_corpus.items()))
    return {
        "hypothesis": "q3_volatility_close_halftime", "verdict": verdict,
        "per_corpus": per_corpus,
        "note": "Levene test, Q3 own-quarter-points stdev vs Q2/Q4, restricted to games close at "
                "half (|first_half_margin|<%.0f, the sim's own margin-bucket-3 edge). " % CLOSE_HALF_EDGE + note,
    }


def run() -> List[Dict[str, Any]]:
    tg = load_all_corpora()
    rows = [
        q3_margin_vs_halftime_deficit(tg),
        q3_volatility_close_halftime(tg),
    ]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "linescores_2024_25+2025_26_team_game_quarters"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-14s %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict_replicated({"a": True, "b": True}) == "REPLICATED"
    assert _verdict_replicated({"a": True, "b": False}) == "PARTIAL"
    assert _verdict_replicated({"a": False, "b": False}) == "NULL"
    assert _verdict_replicated({"a": None, "b": None}) == "NOT_TESTABLE"
    print("self-check OK")


__all__ = [
    "team_game_quarters", "load_all_corpora", "q3_margin_vs_halftime_deficit",
    "q3_volatility_close_halftime", "run", "main", "ALPHA", "MIN_EFFECT_R",
    "MIN_VOL_RATIO", "CLOSE_HALF_EDGE",
]
