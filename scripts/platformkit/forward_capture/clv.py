"""Forward CLV -- grade a LOGGED prediction against the REAL captured devigged close.

This is the read side of the forward-capture clock. It joins a ledger row (which carries
`pred_ts` -- the vintage clock -- and `calibrated_prob`, copied verbatim from the quant
pipeline) to a LineMoveRecord built from the forward odds archive, and reports

    clv = calibrated_prob - devig_close_prob   (PROBABILITY space, never $)

BUT ONLY for predictions whose `pred_ts` is strictly BEFORE the captured line move
(`close.captured_at`). A hindsight prediction -- one stamped at/after the close we are
grading it against -- is EXCLUDED, never graded: the strict guard is the verified
freshness.as_of_reader.assert_vintage, the same leak floor the sim/backtest uses.

HONESTY INVARIANTS (load-bearing):
  - The close is a REAL captured price (archive.build_line_moves), Shin-devigged via the
    verified eval_gate/shin.shin_devig_decimal -- never a live re-poll, never invented.
  - CLV is reported in CALIBRATION terms ONLY. There is no units / ROI / stake / edge
    figure here, and the ledger schema has no column to store one, so a $ claim cannot
    even be persisted. This module RECORDS the data that will one day prove or reject an
    edge; it claims nothing.
  - The LLM authors no number: calibrated_prob is read straight off the ledger row, the
    close is devigged arithmetic, the guard is a timestamp comparison.

Reuses, READ-ONLY (no edits to those packages):
  - freshness/as_of_reader.assert_vintage  -- the strict pred_ts < line-move guard
  - eval_gate/shin.shin_devig_decimal      -- devig the captured 2-way close
  - ledger/metrics.compute_calibration     -- aggregate CLV (Brier/ECE/DM vs close)
  - sibling forward_capture.schema / .archive -- LineMoveRecord + build_line_moves

Stdlib + numpy/pandas (via metrics). ASCII only. <=300 LOC. Per-file test: tests/test_clv.py.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

# --- reuse the verified packages READ-ONLY (sys.path inject so per-file tests work) -------
_PKIT = pathlib.Path(__file__).resolve().parents[1]          # scripts/platformkit
for _p in (_PKIT / "freshness", _PKIT / "eval_gate", _PKIT / "ledger",
           pathlib.Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from as_of_reader import assert_vintage          # noqa: E402  freshness vintage guard
from shin import shin_devig_decimal              # noqa: E402  devig the captured close

try:  # sibling forward_capture modules (authored alongside this file)
    from scripts.platformkit.forward_capture.schema import LineMoveRecord  # type: ignore  # noqa: E402
    from scripts.platformkit.forward_capture import archive as _archive    # type: ignore  # noqa: E402
except ImportError:  # direct-script / per-file-test fallback
    try:
        from schema import LineMoveRecord  # type: ignore  # noqa: E402
    except Exception:  # schema not importable in isolation -> attribute-duck-typed below
        LineMoveRecord = None  # type: ignore
    try:
        import archive as _archive  # type: ignore  # noqa: E402
    except Exception:
        _archive = None  # type: ignore


# --------------------------------------------------------------------------------------- #
# Accessors that tolerate either a LineMoveRecord dataclass or a plain dict, so clv.py is
# decoupled from the exact sibling representation (it only depends on the documented fields).
# --------------------------------------------------------------------------------------- #
def _get(rec, key, default=None):
    if rec is None:
        return default
    if isinstance(rec, dict):
        return rec.get(key, default)
    return getattr(rec, key, default)


def _close_captured_at(move) -> Optional[str]:
    """ISO timestamp of the CLOSE snapshot (the line-move time we grade vintage against)."""
    return _get(move, "close_captured_at") or _get(move, "captured_at")


def _close_devig_home(move) -> Optional[float]:
    """Devigged fair HOME prob of the close.

    Prefer a value the archive already devigged (move.devig_close_prob). Otherwise devig the
    captured 2-way decimal close (home/away prices) HERE via the verified Shin reference --
    never a live re-poll, always the real captured price.
    """
    pre = _get(move, "devig_close_prob")
    if pre is not None:
        return float(pre)
    ho = _get(move, "close_home_price", _get(move, "home_odds"))
    ao = _get(move, "close_away_price", _get(move, "away_odds"))
    if ho is None or ao is None:
        return None
    try:
        probs, _z = shin_devig_decimal([float(ho), float(ao)])
        return float(probs[0])
    except Exception:
        return None


@dataclass
class CLVResult:
    """One graded forward-CLV row. clv is in PROBABILITY space; there is no $ field."""
    pred_id: str
    pred_ts: str
    close_captured_at: str
    calibrated_prob: float
    devig_close_prob: float
    clv: float            # calibrated_prob - devig_close_prob (probability space)

    def as_record(self) -> dict:
        return {
            "pred_id": self.pred_id, "pred_ts": self.pred_ts,
            "close_captured_at": self.close_captured_at,
            "calibrated_prob": self.calibrated_prob,
            "devig_close_prob": self.devig_close_prob, "clv": self.clv,
        }


def compute_clv(pred_row: dict, move) -> Optional[CLVResult]:
    """CLV for ONE logged prediction vs ONE captured line-move close.

    Returns None (the prediction is EXCLUDED) when:
      - the close timestamp or devigged close is missing/uncapturable, or
      - the vintage guard fails: pred_ts is NOT strictly before close.captured_at
        (a hindsight prediction -- made at or after the move -- is never graded).

    The guard is freshness.as_of_reader.assert_vintage, reused verbatim: we frame the close
    capture as the {extracted_at: close_captured_at} "evidence" and assert it was NOT known
    until at/after the prediction -- i.e. the prediction predates the move. assert_vintage
    raises AssertionError('LEAK...') when extracted_at >= asof; here asof = close_captured_at
    and extracted_at = pred_ts, so it passes exactly when pred_ts < close_captured_at.
    """
    pred_ts = pred_row.get("pred_ts")
    cal = pred_row.get("calibrated_prob")
    if pred_ts is None or cal is None:
        return None
    close_at = _close_captured_at(move)
    devig = _close_devig_home(move)
    if close_at is None or devig is None:
        return None

    # STRICT vintage guard: pred_ts must be strictly before the captured close.
    # assert_vintage({extracted_at: pred_ts}, asof=close_at) raises iff pred_ts >= close_at.
    try:
        assert_vintage({"extracted_at": str(pred_ts), "player_id": pred_row.get("pred_id")},
                       str(close_at))
    except AssertionError:
        return None  # hindsight prediction -> EXCLUDED, never graded

    cal = float(cal)
    clv = cal - float(devig)
    return CLVResult(pred_id=str(pred_row.get("pred_id", "")), pred_ts=str(pred_ts),
                     close_captured_at=str(close_at), calibrated_prob=cal,
                     devig_close_prob=float(devig), clv=float(clv))


def _move_for(moves_by_key: Dict[tuple, object], pred_row: dict):
    """Locate the LineMoveRecord for a prediction by (game_id, market[, book]).

    moves_by_key is keyed by the tuple build_line_moves emits. We try the most specific key
    first (game_id, market, book) then fall back to (game_id, market) so a prediction logged
    without a book still joins the consolidated close.
    """
    gid = pred_row.get("game_id")
    mkt = pred_row.get("market")
    for key in ((gid, mkt, pred_row.get("book")), (gid, mkt)):
        if key in moves_by_key:
            return moves_by_key[key]
    return None


def _index_moves(moves) -> Dict[tuple, object]:
    """Build a {(game_id, market[, book]): move} index from a list of LineMoveRecords."""
    idx: Dict[tuple, object] = {}
    for m in moves:
        gid = _get(m, "game_id")
        mkt = _get(m, "market")
        book = _get(m, "book")
        idx[(gid, mkt, book)] = m
        idx.setdefault((gid, mkt), m)  # consolidated fallback (first book wins, deterministic)
    return idx


def grade_forward_clv(pred_rows, moves) -> List[CLVResult]:
    """Join logged predictions to captured line-moves and grade forward CLV.

    `pred_rows`: an iterable of ledger row dicts (each with pred_id/pred_ts/calibrated_prob/
                 game_id/market). `moves`: a list of LineMoveRecords (or dicts) from
                 archive.build_line_moves. Returns one CLVResult per prediction that joins a
                 move AND passes the strict vintage guard; hindsight rows are silently
                 EXCLUDED (never graded), which is the honest, leak-free behaviour.
    """
    idx = _index_moves(list(moves))
    out: List[CLVResult] = []
    for row in pred_rows:
        move = _move_for(idx, row)
        if move is None:
            continue
        res = compute_clv(row, move)
        if res is not None:
            out.append(res)
    return out


def to_grade_map(results: List[CLVResult],
                 outcomes: Optional[Dict[str, int]] = None) -> Dict[str, dict]:
    """Translate CLVResults into the ledger.grade_outcomes input map.

    Emits {pred_id: {devig_close_prob: <real captured devigged close>[, outcome: 0/1]}} so the
    EXISTING ledger/grade_outcomes writes the REAL captured close onto each row (immutably,
    no-overwrite) WITHOUT this module touching ledger internals. `outcomes` is an optional
    {pred_id: 0/1} side map merged in when realized results have landed.
    """
    outcomes = outcomes or {}
    gmap: Dict[str, dict] = {}
    for r in results:
        entry: dict = {"devig_close_prob": r.devig_close_prob}
        if r.pred_id in outcomes:
            entry["outcome"] = int(outcomes[r.pred_id])
        gmap[r.pred_id] = entry
    return gmap


def aggregate_clv(graded_ledger, sport: str, market: str,
                  window_days: Optional[int] = None,
                  now_iso: Optional[str] = None) -> dict:
    """Aggregate forward CLV over a GRADED ledger slice via the existing ledger/metrics.

    Delegates entirely to ledger.metrics.compute_calibration, which scores calibrated_prob vs
    devig_close_prob (Brier/ECE + clustered DM vs the close) for one (sport, market) and ALWAYS
    returns edge_claimed=False -- a DM p>=0.05 or thin n is an HONEST REJECT ('matches_close'),
    never a buried beat. We add the mean CLV in probability space for transparency; there is no
    $ / ROI figure anywhere.
    """
    from metrics import compute_calibration  # reuse verified aggregator READ-ONLY
    out = compute_calibration(graded_ledger, sport, market,
                              window_days=window_days, now_iso=now_iso)
    try:
        sub = graded_ledger[(graded_ledger["sport"] == sport)
                            & (graded_ledger["market"] == market)
                            & graded_ledger["devig_close_prob"].notna()
                            & graded_ledger["outcome"].notna()]
        if len(sub):
            out["mean_clv"] = float(
                (sub["calibrated_prob"] - sub["devig_close_prob"]).mean())
            out["n_clv"] = int(len(sub))
    except Exception:
        pass
    out["units"] = "probability"          # explicit: CLV is calibration, never dollars
    out["edge_claimed"] = False
    return out
