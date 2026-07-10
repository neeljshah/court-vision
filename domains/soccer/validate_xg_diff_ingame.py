"""domains.soccer.validate_xg_diff_ingame -- mechanisms.md #29: does the
as-of minute-level cumulative real-xG diff (asof_ingame.parquet) beat a
(goal-diff, minute)-only in-game base on held-out home-win Brier?

Reuses the repo's existing rigorous in-game gate machinery
(scripts.platformkit.gate_run_soccer_statsbomb: leak-free chronological
50/50 train/test split per minute-snapshot, DM test clustered by match_id,
degenerate-base guard) instead of re-deriving a base -- the goal-diff->
win-prob logistic base IS the (score, minute) baseline the mechanism asks
for. Checked at 3 minute snapshots (30/60/75) for robustness rather than
one; only the mechanisms-ledger row + honest multi-minute x 2-corpus
verdict framing is new.

Leak audit: xg_diff_asof is folded strictly minute<=t (ingest_statsbomb_
events.py); the base refits per minute-snapshot on a chronological
train/test split of MATCHES (not rows within a match), so no row from a
test match's own future informs its own base fit. 2 independent corpora
(A=EPL 2015/16 men, B=FA WSL pooled women) -- an affirmative needs a
majority of minutes to ship in BOTH corpora, else PROVISIONAL.

Run: python -m domains.soccer.validate_xg_diff_ingame
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from domains.soccer.knowledge._data import LEDGER_PATH
from scripts.platformkit.gate_run_soccer_statsbomb import (
    _INGAME, _META, _gate_corpus, _ingame_frame,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

EPS = 0.05
COL = "xg_diff_asof"
MINUTES = (30, 60, 75)
HYPOTHESIS = "xg_diff_asof_adds_to_score_minute_ingame_base"


def _corpus_wins(c: Dict[str, Any]) -> bool:
    return bool(c["feat_better"] and c["dm_p"] < EPS and not c["base_degenerate"])


def run(seed: int = 0) -> Dict[str, Any]:
    meta = pd.read_parquet(_META)
    ing = pd.read_parquet(_INGAME)
    per_minute: List[Dict[str, Any]] = []
    for i, minute in enumerate(MINUTES):
        a = _gate_corpus(_ingame_frame(meta, ing, "A", minute, seed + 2 * i), COL, EPS)
        b = _gate_corpus(_ingame_frame(meta, ing, "B", minute, seed + 2 * i + 1), COL, EPS)
        per_minute.append({"minute": minute, "a": a, "b": b,
                            "a_wins": _corpus_wins(a), "b_wins": _corpus_wins(b)})

    both_win = [m for m in per_minute if m["a_wins"] and m["b_wins"]]
    any_win = [m for m in per_minute if m["a_wins"] or m["b_wins"]]
    any_degen = any(m["a"]["base_degenerate"] or m["b"]["base_degenerate"] for m in per_minute)
    if any_degen:
        verdict = "NOT_TESTABLE"
    elif len(both_win) >= (len(MINUTES) // 2 + 1):
        verdict = "CONFIRMED"
    elif any_win:
        verdict = "PROVISIONAL"  # ships at some minutes/one corpus, not a majority-both
    else:
        verdict = "NULL_LOCAL"

    deltas = [m["a"]["brier_delta"] for m in per_minute] + [m["b"]["brier_delta"] for m in per_minute]
    ps = [m["a"]["dm_p"] for m in per_minute] + [m["b"]["dm_p"] for m in per_minute]
    n_total = sum(m["a"]["n"] + m["b"]["n"] for m in per_minute)
    note = " | ".join(
        "min%d A:n=%d %.6f->%.6f p=%.4g wins=%s B:n=%d %.6f->%.6f p=%.4g wins=%s" % (
            m["minute"], m["a"]["n"], m["a"]["brier_base"], m["a"]["brier_feat"], m["a"]["dm_p"], m["a_wins"],
            m["b"]["n"], m["b"]["brier_base"], m["b"]["brier_feat"], m["b"]["dm_p"], m["b_wins"])
        for m in per_minute)
    row = {
        "hypothesis": HYPOTHESIS, "sport": "soccer", "n": int(n_total), "verdict": verdict,
        "effect": None if any(d != d for d in deltas) else round(min(deltas), 7),
        "p": round(max(ps), 6), "note": note,
        "corpus": "statsbomb_asof_ingame__A_B__min30_60_75", "edge_claimed": False,
    }
    append_jsonl_atomic(LEDGER_PATH, row)
    return row


def main() -> int:
    r = run()
    print("%-42s %-14s n=%-6d effect=%s p=%s" % (
        r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"]))
    print(r["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: corpus-win logic + majority-both threshold."""
    win = {"feat_better": True, "dm_p": 0.001, "base_degenerate": False}
    lose = {"feat_better": False, "dm_p": 0.9, "base_degenerate": False}
    assert _corpus_wins(win) is True
    assert _corpus_wins(lose) is False
    assert (len(MINUTES) // 2 + 1) == 2  # majority of 3 minutes is 2
    print("self-check OK")
