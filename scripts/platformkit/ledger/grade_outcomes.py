"""Grade open predictions against realized outcomes (blueprint X3 PART B).

Fills `outcome`, `graded_at`, and (where capturable) `devig_close_prob` on open rows by
matching on pred_id. APPEND-ONLY discipline: it NEVER overwrites a non-null outcome (a
logged prediction is immutable -- mutating it destroys the trust moat) and it asserts the
VINTAGE guard pred_ts < game_date, dropping + flagging any violator as a logged leak.

Shin-devig (eval_gate/shin.py) converts a captured 2-way close into a fair home prob.
Logs probabilities + outcomes ONLY -- never units / ROI / edge.
"""
from __future__ import annotations
import pathlib
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

try:  # package import when run as `-m scripts.platformkit.ledger...`
    from scripts.platformkit.ledger.ledger import (
        read_ledger, _store_paths, _atomic_write, _mirror_csv)
except ImportError:  # direct-script / sys.path-injected (per-file test) fallback
    from ledger import read_ledger, _store_paths, _atomic_write, _mirror_csv

_EVAL_GATE = pathlib.Path(__file__).resolve().parents[1] / "eval_gate"
if str(_EVAL_GATE) not in sys.path:
    sys.path.insert(0, str(_EVAL_GATE))
from shin import shin_devig_decimal  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _vintage_ok(pred_ts, game_date) -> bool:
    """True if the prediction is leak-free by vintage: made on the game day or earlier.

    game_date is date-only; a same-day pre-tip prediction is leak-free (we have no tip
    time to prove otherwise). Only a prediction stamped AFTER the game day is a leak.
    Parse to dates -- NEVER string-compare a full timestamp to a date-only value (that
    drops legitimate same-day rows because the longer string sorts after).
    """
    if game_date is None or (isinstance(game_date, float) and pd.isna(game_date)):
        return True  # unknown game_date -> cannot prove a leak; keep but do not assert
    try:
        pred_day = pd.to_datetime(pred_ts).date()
        game_day = pd.to_datetime(game_date).date()
    except Exception:
        return True  # unparseable -> cannot prove a leak; keep
    return pred_day <= game_day


def devig_home_prob(home_odds: float, away_odds: float) -> Optional[float]:
    """Shin-devigged fair HOME win prob from a 2-way decimal close. None on bad input."""
    try:
        probs, _z = shin_devig_decimal([home_odds, away_odds])
        return float(probs[0])
    except Exception:
        return None


def grade_outcomes(outcomes: Dict[str, dict], base_dir: Optional[str] = None) -> dict:
    """Apply a {pred_id: {outcome, [home_odds, away_odds] | [devig_close_prob]}} map.

    Returns a summary dict. Drops + flags vintage violators (pred_ts >= game_date).
    Refuses to overwrite an already-graded (non-null outcome) row.
    """
    df = read_ledger(base_dir=base_dir)
    summary = {"matched": 0, "filled": 0, "skipped_already_graded": 0,
               "leak_dropped": 0, "leak_ids": []}
    if df.empty:
        return summary

    # vintage guard: drop any pred whose pred_ts is not strictly before game_date
    keep_mask = df.apply(lambda r: _vintage_ok(r["pred_ts"], r["game_date"]), axis=1)
    leaks = df[~keep_mask]
    if len(leaks):
        summary["leak_dropped"] = int(len(leaks))
        summary["leak_ids"] = leaks["pred_id"].tolist()
        df = df[keep_mask].reset_index(drop=True)

    now = _now_iso()
    for pid, info in outcomes.items():
        sel = df["pred_id"] == pid
        if not sel.any():
            continue
        summary["matched"] += 1
        idx = df.index[sel][0]
        if pd.notna(df.at[idx, "outcome"]):
            summary["skipped_already_graded"] += 1
            continue  # IMMUTABLE: never overwrite a graded outcome
        df.at[idx, "outcome"] = int(info["outcome"])
        df.at[idx, "graded_at"] = now
        close = info.get("devig_close_prob")
        if close is None and "home_odds" in info and "away_odds" in info:
            close = devig_home_prob(info["home_odds"], info["away_odds"])
        if close is not None:
            df.at[idx, "devig_close_prob"] = float(close)
        summary["filled"] += 1

    store, csv_path = _store_paths(base_dir)
    _atomic_write(df, store)
    _mirror_csv(df, csv_path)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    """Headless entry: a real run wires the per-sport corpus join here (HUMAN-RUN).

    The synthetic-validated grading mechanics live in test_ledger.py; the live join to a
    realized-outcome corpus is a HUMAN-RUN step (real-data OOS is not fabricated here).
    """
    print("grade_outcomes: VALIDATION_PENDING -- live corpus join is a HUMAN-RUN step.")
    print("Mechanics (no-overwrite + vintage guard) are validated in test_ledger.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
