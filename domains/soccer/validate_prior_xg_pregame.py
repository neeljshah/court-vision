"""domains.soccer.validate_prior_xg_pregame -- mechanisms.md #28: does the
strictly-prior trailing EW real-xG diff (asof_pregame.parquet) beat the
existing goals-based EW-Poisson pregame base on held-out home-win Brier?

Reuses the repo's existing rigorous pregame gate machinery
(scripts.platformkit.gate_run_soccer_statsbomb: leak-free chronological
50/50 train/test split, DM test clustered by match_id, degenerate-base
guard) instead of re-deriving a baseline or split design -- this IS the
"existing soccer pregame baseline" the mechanism asks for. Only the
mechanisms-ledger row + honest 2-corpus verdict framing is new here.

Leak audit: xg_prior_diff is a STRICTLY-PRIOR trailing EW mean (built by
ingest_statsbomb_events.py, snapshot-before-update); the base is a
strictly-prior expanding Poisson fit; train/test is a chronological split.
No same-match/same-day leakage. 2 independent corpora (A=EPL 2015/16 men,
B=FA WSL pooled women) -- an affirmative needs BOTH to ship, else PROVISIONAL.

Run: python -m domains.soccer.validate_prior_xg_pregame
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from domains.soccer.knowledge._data import LEDGER_PATH
from scripts.platformkit.gate_run_soccer_statsbomb import (
    _META, _PREGAME, _gate_corpus, _pregame_frame,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

EPS = 0.05
COL = "xg_prior_diff"
HYPOTHESIS = "prior_xg_pregame_beats_goals_poisson_base"


def _corpus_wins(c: Dict[str, Any]) -> bool:
    return bool(c["feat_better"] and c["dm_p"] < EPS and not c["base_degenerate"])


def run(seed: int = 0) -> Dict[str, Any]:
    meta = pd.read_parquet(_META)
    pre = pd.read_parquet(_PREGAME)
    a = _gate_corpus(_pregame_frame(meta, pre, "A", seed), COL, EPS)
    b = _gate_corpus(_pregame_frame(meta, pre, "B", seed + 1), COL, EPS)
    a_wins, b_wins = _corpus_wins(a), _corpus_wins(b)
    if a["base_degenerate"] or b["base_degenerate"]:
        verdict = "NOT_TESTABLE"
    elif a_wins and b_wins:
        verdict = "CONFIRMED"
    elif a_wins or b_wins:
        verdict = "PROVISIONAL"  # single-corpus affirmative only, not replicated
    else:
        verdict = "NULL_LOCAL"
    row = {
        "hypothesis": HYPOTHESIS, "sport": "soccer",
        "n": int(a["n"]) + int(b["n"]), "verdict": verdict,
        "effect": None if any(x != x for x in (a["brier_delta"], b["brier_delta"]))
                  else round(min(a["brier_delta"], b["brier_delta"]), 7),
        "p": round(max(a["dm_p"], b["dm_p"]), 6),
        "note": ("split-half A(EPL): n=%d brier %.6f->%.6f dm_p=%.4g wins=%s | "
                 "B(WSL): n=%d brier %.6f->%.6f dm_p=%.4g wins=%s"
                 % (a["n"], a["brier_base"], a["brier_feat"], a["dm_p"], a_wins,
                    b["n"], b["brier_base"], b["brier_feat"], b["dm_p"], b_wins)),
        "corpus": "statsbomb_asof_pregame__A_B", "edge_claimed": False,
    }
    append_jsonl_atomic(LEDGER_PATH, row)
    return row


def main() -> int:
    r = run()
    print("%-42s %-14s n=%-6d effect=%s p=%s -- %s" % (
        r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: corpus-win + verdict thresholds behave."""
    win = {"feat_better": True, "dm_p": 0.001, "base_degenerate": False}
    lose = {"feat_better": False, "dm_p": 0.9, "base_degenerate": False}
    degen = {"feat_better": True, "dm_p": 0.001, "base_degenerate": True}
    assert _corpus_wins(win) is True
    assert _corpus_wins(lose) is False
    assert _corpus_wins(degen) is False
    print("self-check OK")
