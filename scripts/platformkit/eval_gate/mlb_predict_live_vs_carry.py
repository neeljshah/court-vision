"""scripts.platformkit.eval_gate.mlb_predict_live_vs_carry -- S447 STEP 1 (REPORT ONLY).
AMENDMENT 1 fix 1b: chargeable naming, corpus-keyed state, integer-microsecond receipts,
counted-not-crashed refusals, finite-probability validation, calendar-day cutoffs, absolute
A9 paths. Loader + as-of-corpus helpers live in mlb_predict_live_vs_carry_io.py (LOC cap).

Measures whether domains.mlb.predictor.MLBPredictor.predict_live is ahead of, behind, or
indistinguishable from the unconditioned PREGAME CARRY that live_loop.py actually serves for
MLB today (repricer_router.py has no mlb surface; every MLB live tick is served
_pregame_carry -- see live_loop.py:237-243). This module answers the CANDIDATE question
offline; it does not touch the served path and does not wire a surface (STEP 2 is a
PROPOSED diff, not applied here).

TWO CELLS (never one pooled number, per SPENT-WINDOW, docs/evidence/CORPUS_DATA_CARDS
_2026-09-22.md C2): `historical_descriptive` over mlb_segmented_r3 (chargeable False, no
verdict key, ever) and `forward` over the 2026-09-25+ capture (chargeable True; the
orchestrator decides whether to actually spend the one K at landing time, not this module).
gate_a0's cluster bootstrap + thresholds are imported unedited, never reinvented.

Paired-difference sign convention: brier_live minus brier_carry; NEGATIVE means live is
ahead of the carry (lower Brier). Calibration language only.

INVARIANTS: never edit src/, kernel/, domains/mlb/predictor.py, gate_a0*, live_loop.py,
repricer_router.py (import-only); no fit in this module; ASCII; <=300 LOC; no network.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from domains.mlb.predictor import MLBPredictor, _corpus_path
from scripts.platformkit.eval_gate.mlb_predict_live_vs_carry_io import (
    CorpusStartBeforeTick, HIST_CORPUS, REASON_UNPARSEABLE, get_asof_predictor,
    ingest_forward_bytes, load_historical, record_identity, resolve_cutoff_date, validate_state,
)
from scripts.platformkit.eval_gate.mlb_predict_live_vs_carry_report import (
    forward_cell, historical_cell, mid_reference,
)
from scripts.platformkit.execution.venue_time import parse_venue_time
from scripts.platformkit.ingame.gate_a0_ingame_vs_market import N_BOOT, SEED, N_MIN_GAMES

REASON_NO_PRIOR = "no_prior"
REASON_INVALID_CARRY = "invalid_carry"
REASON_DUP_OR_OOO = "duplicate_or_out_of_order_receipt"
REASON_INVALID_RECEIPT = "invalid_receipt_time"
REASON_UNSETTLED = "unsettled"
REASON_INVALID_PROBABILITY = "invalid_probability"
REASON_INVALID_OUTCOME = "invalid_outcome"
REASON_INVALID_MID = "invalid_mid"
REASON_MID_AFTER_STATE = "book_receipt_after_state"
REASON_CORPUS_START = "corpus_start_before_tick"
REASON_FORWARD_BEFORE_WINDOW = "forward_before_window"
FORWARD_WINDOW_START = "2026-09-25"  # first charged forward night (AMENDMENT 6 item b)

_MODEL_VIEW_KEYS = ("game_date", "home", "away", "inning", "half", "home_score",
                    "away_score", "corpus_unit")  # AMENDMENT 8 item a: never outcome/carry/mid


def _model_view(row: Dict[str, Any]) -> Dict[str, Any]:
    """The ONLY fields the prediction function ever sees (AMENDMENT 8 item a, the no-hindsight
    boundary): a predictor closing over `row["outcome"]`, `row["carry"]`, or `row["mid"]` hits a
    KeyError here instead of silently scoring on a settled/priced value it must never see."""
    return {k: row.get(k) for k in _MODEL_VIEW_KEYS}


def _receipt_micros(value: Any) -> Optional[int]:
    """Integer microseconds via parse_venue_time (item d): Z / +00:00 / -05:00 are one
    clock; unparseable input yields None (refused by the caller, never crashed). AMENDMENT 4
    item b: the microsecond-scaled value is range-checked BEFORE round/int -- a finite epoch
    (e.g. 1e308) that overflows float range when scaled (-> inf) refuses here instead of
    round()/int() raising OverflowError."""
    epoch = parse_venue_time(value)
    if epoch is None:
        return None
    scaled = epoch * 1_000_000
    return None if not math.isfinite(scaled) else int(round(scaled))


def _valid_prob(value: Any) -> Optional[float]:
    """Finite float in [0, 1] (item f); AMENDMENT 7 item c: bool and any non-numeric raw type
    (e.g. a numeric-looking string) are rejected BEFORE conversion, exactly as _valid_outcome
    already does -- carry=True or mid='0.5' must never silently coerce into a score."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    return f if math.isfinite(f) and 0.0 <= f <= 1.0 else None


def _valid_outcome(value: Any) -> Optional[int]:
    """Exactly 0 or 1, int/float only (AMENDMENT 3 item a): str and bool are rejected BEFORE
    any numeric test -- "0"/"1" and False/True all refuse as invalid_outcome; int(0.5)
    silently becoming 0, or int("1") silently succeeding, is exactly the bug this closes."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    if not math.isfinite(f) or f not in (0.0, 1.0):
        return None
    return int(f)


def build_predict_live_fn(games_df: pd.DataFrame,
                           predictor_factory: Callable[[pd.DataFrame], Any] = MLBPredictor
                           ) -> Callable[[Dict[str, Any]], float]:
    """The REAL candidate: predict_live fed offline from an as-of Elo (games[date < D])."""
    cache: Dict[str, Any] = {}

    def _fn(row: Dict[str, Any]) -> float:
        predictor = get_asof_predictor(games_df, resolve_cutoff_date(row), cache, predictor_factory)
        out = predictor.predict_live(row["home"], row["away"], int(row["inning"]), row["half"],
                                      int(row["home_score"]), int(row["away_score"]))
        return float(out["p_home_win"])
    return _fn


def process_rows(rows: List[Dict[str, Any]], predict_live_fn: Callable[[Dict[str, Any]], float]
                  ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Single pass (streams inputs). Carry + receipt state are keyed by (corpus, game_id)
    (item c) so a historical and a forward row for the same game_id never collide. Every
    row is scored or refused by a named reason (never crashed -- items e/f/i); nothing is
    filtered by its outcome or by which arm looks better."""
    refusals: Dict[str, int] = {}

    def _refuse(reason: str) -> None:
        refusals[reason] = refusals.get(reason, 0) + 1

    last_receipt: Dict[Any, int] = {}
    game_carry: Dict[Any, float] = {}
    scored: List[Dict[str, Any]] = []
    for row in rows:
        row = validate_state(row)  # normalised row (AMENDMENT 3 item b), or None
        if row is None:
            _refuse(REASON_UNPARSEABLE)  # AMENDMENT 2 item b / AMENDMENT 3 item c
            continue
        corpus = row.get("corpus", "forward")
        if corpus == "forward" and row["game_date"] < FORWARD_WINDOW_START:
            _refuse(REASON_FORWARD_BEFORE_WINDOW)  # AMENDMENT 6 item b: charged window floor
            continue
        key = (corpus, row["game_id"])

        t = _receipt_micros(row.get("receipt"))
        if t is None:
            _refuse(REASON_INVALID_RECEIPT)
            continue
        prev = last_receipt.get(key)
        if prev is not None and t <= prev:
            _refuse(REASON_DUP_OR_OOO)
            continue
        last_receipt[key] = t

        if key not in game_carry:
            raw_carry = row.get("carry")
            if raw_carry is None:
                _refuse(REASON_NO_PRIOR)
                continue
            carry = _valid_prob(raw_carry)
            if carry is None:
                _refuse(REASON_INVALID_CARRY)
                continue
            game_carry[key] = carry

        if row.get("outcome") is None:
            _refuse(REASON_UNSETTLED)
            continue
        y = _valid_outcome(row["outcome"])
        if y is None:
            _refuse(REASON_INVALID_OUTCOME)
            continue

        try:
            p_live = _valid_prob(predict_live_fn(_model_view(row)))
        except CorpusStartBeforeTick:
            _refuse(REASON_CORPUS_START)
            continue
        except KeyError:  # AMENDMENT 8 item a: a redacted field (outcome/carry/mid) was
            _refuse(REASON_INVALID_PROBABILITY)  # never scored, refused and counted instead
            continue
        if p_live is None:
            _refuse(REASON_INVALID_PROBABILITY)
            continue

        raw_mid = row.get("mid")
        mid = _valid_prob(raw_mid) if raw_mid is not None else None
        if raw_mid is not None and mid is None:
            _refuse(REASON_INVALID_MID)
        mid_receipt = row.get("mid_receipt")
        if mid is not None and mid_receipt is not None:
            book_t = _receipt_micros(mid_receipt)
            if book_t is None or book_t > t:
                mid = None
                _refuse(REASON_MID_AFTER_STATE)

        brier_live, brier_carry = (p_live - y) ** 2, (game_carry[key] - y) ** 2
        scored.append({
            "game_id": row["game_id"], "receipt": t, "corpus": corpus,
            "corpus_unit": row.get("corpus_unit"),  # AMENDMENT 6 item a: the real unit, not the label
            "brier_live": brier_live, "brier_carry": brier_carry,
            "paired_diff": brier_live - brier_carry,  # AMENDMENT 5 item a / Q9: per-unit series
            "carry": game_carry[key],
            "state": {"home": row["home"], "away": row["away"], "inning": row["inning"],
                      "half": row["half"], "home_score": row["home_score"],
                      "away_score": row["away_score"], "game_date": row["game_date"]},
            "mid": mid,
        })
    return scored, refusals


def _emit_ascii_json(obj: Dict[str, Any]) -> bytes:
    """ASCII JSON, sorted keys, allow_nan=False (item f) -- a non-finite value is a bug, not
    a silently-serialized null; single LF-terminated line of bytes."""
    return (json.dumps(obj, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2)
            + "\n").encode("ascii")


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--historical-corpus", default=HIST_CORPUS)
    ap.add_argument("--forward-dir", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    hist_rows, identities, refusals = load_historical(args.historical_corpus)
    fwd_rows: List[Dict[str, Any]] = []
    if args.forward_dir:
        for fp in sorted(glob.glob(f"{args.forward_dir}/*.jsonl")):
            identities.append(record_identity(fp))
            rows, counts = ingest_forward_bytes(Path(fp).read_bytes())  # AMENDMENT 4 item c
            fwd_rows.extend(rows)
            for reason, n in counts.items():
                refusals[reason] = refusals.get(reason, 0) + n

    games_path = _corpus_path(None)
    identities.append(record_identity(str(games_path)))
    games_df = pd.read_parquet(games_path)
    predict_live_fn = build_predict_live_fn(games_df)

    scored, row_refusals = process_rows(hist_rows + fwd_rows, predict_live_fn)
    for reason, n in row_refusals.items():
        refusals[reason] = refusals.get(reason, 0) + n
    hist_scored = [r for r in scored if r["corpus"] == "historical_descriptive"]
    fwd_scored = [r for r in scored if r["corpus"] == "forward"]

    result = {
        "sport": "mlb",
        "historical_descriptive": historical_cell(hist_scored),
        "forward": forward_cell(fwd_scored),
        "mid_reference": {
            "historical_descriptive": mid_reference(hist_scored),
            "forward": mid_reference(fwd_scored),
        },
        "refusals": refusals,
        "identities": identities,
        "n_boot": N_BOOT, "seed": SEED, "n_min_games": N_MIN_GAMES,
        "not_verified": ["no real run: zero forward games exist as of 2026-09-24"],
    }
    out = _emit_ascii_json(result)
    if args.out:
        Path(args.out).write_bytes(out)
    else:
        sys.stdout.buffer.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
