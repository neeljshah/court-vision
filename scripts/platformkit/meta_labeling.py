"""Meta-labeling sizer SCAFFOLD (Lopez de Prado): a secondary model over a primary.

The primary model already decided WHICH side to take.  The secondary (meta) model
only answers "how often is that decision right, given the context it was made in?"
and maps that probability to a size in UNITS via capped fractional Kelly.

This is CALIBRATION plumbing, not an edge claim: a well-ranked p_correct says the
sizer knows which of its own decisions are shaky, nothing about money.  Nothing here
trains until the paper decision ledger has >= MIN_LABELED_ROWS settled rows -- below
that every entry point returns an INSUFFICIENT status object instead of a model, on
purpose.  It starts COLLECTING now and trains later.

Features are strictly as-of entry (prob/price/strategy/hour known at decision time);
the label is the only thing that reads the outcome.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

MIN_LABELED_ROWS = 200
DEFAULT_FLOOR = 0.55  # below this meta probability the sizer stands down (0 units)
DEFAULT_KELLY_CAP = 0.25
N_PROB_BUCKETS = 5
_MIN_PER_CLASS = 3  # CalibratedClassifierCV cv=3 needs this many of each label

_WIN_TOKENS = {"win", "won", "true", "1", "hit", "yes", "correct"}
_LOSS_TOKENS = {"loss", "lost", "lose", "false", "0", "miss", "no", "wrong"}
_VOID_TOKENS = {"push", "void", "cancelled", "canceled", "no_action", "pending", "open"}

Status = Dict[str, Any]


def _insufficient(note: str, n_labeled: int = 0, **extra: Any) -> Status:
    """The honest "not enough settled decisions yet" object every caller must handle."""
    out: Status = {"status": "INSUFFICIENT", "n_labeled": int(n_labeled),
                   "required": MIN_LABELED_ROWS,
                   "rows_needed": max(0, MIN_LABELED_ROWS - int(n_labeled)),
                   "note": note}
    out.update(extra)
    return out


def _label(side: Any, outcome: Any) -> Optional[int]:
    """1 if the primary decision was right, 0 if wrong, None if unsettled/void."""
    if outcome is None:
        return None
    if isinstance(outcome, bool):
        return int(outcome)
    text = str(outcome).strip().lower()
    if not text or text in _VOID_TOKENS:
        return None
    if text in _WIN_TOKENS:
        return 1
    if text in _LOSS_TOKENS:
        return 0
    if side is None or str(side).strip() == "":
        return None
    return int(text == str(side).strip().lower())


def _hour(ts: Any) -> Optional[int]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).hour
    except (TypeError, ValueError):
        return None


def _norm(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize one ledger record; None when the as-of fields are unusable."""
    try:
        prob = float(rec["prob_at_entry"])
        price = float(rec["market_price_at_entry"])
    except (KeyError, TypeError, ValueError):
        return None
    hour = _hour(rec.get("ts"))
    if hour is None or not (0.0 <= prob <= 1.0) or not math.isfinite(price):
        return None
    return {"ts": rec.get("ts"), "market": rec.get("market"), "side": rec.get("side"),
            "strategy": str(rec.get("strategy") or "unknown"), "prob": prob,
            "price": price, "hour": hour, "size_units": rec.get("size_units"),
            "label": _label(rec.get("side"), rec.get("outcome"))}


def read_ledger(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Parse a jsonl paper decision ledger into normalized records (bad lines skipped)."""
    file = Path(path)
    if not file.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            norm = _norm(rec)
            if norm is not None:
                out.append(norm)
    return out


def feature_names(strategies: Sequence[str]) -> List[str]:
    base = ["edge", "abs_edge", "hour_sin", "hour_cos", "prob_bucket"]
    return base + ["strategy=" + s for s in strategies]


def vectorize(rec: Dict[str, Any], strategies: Sequence[str]) -> List[float]:
    """As-of feature vector: nothing here is known only after the decision settles."""
    edge = rec["prob"] - rec["price"]
    angle = 2.0 * math.pi * float(rec["hour"]) / 24.0
    bucket = min(int(rec["prob"] * N_PROB_BUCKETS), N_PROB_BUCKETS - 1)
    onehot = [1.0 if rec["strategy"] == s else 0.0 for s in strategies]
    return [edge, abs(edge), math.sin(angle), math.cos(angle),
            bucket / float(N_PROB_BUCKETS - 1)] + onehot


def build_training_rows(decision_ledger_path: Union[str, Path]) -> Status:
    """Ledger -> labeled feature rows.  INSUFFICIENT below MIN_LABELED_ROWS."""
    records = read_ledger(decision_ledger_path)
    strategies = sorted({r["strategy"] for r in records})
    labeled = [r for r in records if r["label"] is not None]
    rows = [{"x": vectorize(r, strategies), "y": int(r["label"]), "ts": r["ts"],
             "strategy": r["strategy"], "edge": r["prob"] - r["price"]} for r in labeled]
    common = {"n_records": len(records), "n_labeled": len(rows), "strategies": strategies,
              "feature_names": feature_names(strategies), "rows": rows}
    if len(rows) < MIN_LABELED_ROWS:
        return _insufficient("collecting: not enough settled decisions yet", **common)
    return dict(status="OK", required=MIN_LABELED_ROWS, rows_needed=0, **common)


def _rows_of(rows: Union[Status, Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if isinstance(rows, dict):
        return list(rows.get("rows") or [])
    return list(rows)


def fit_meta(rows: Union[Status, Sequence[Dict[str, Any]]]) -> Status:
    """Fit the calibrated secondary model.

    Returns INSUFFICIENT instead of a model when there are too few settled rows,
    or too few of either label to calibrate.
    """
    items = _rows_of(rows)
    if len(items) < MIN_LABELED_ROWS:
        return _insufficient("collecting: not enough settled decisions yet", n_labeled=len(items))
    counts = Counter(int(r["y"]) for r in items)
    if len(counts) < 2 or min(counts.values()) < _MIN_PER_CLASS:
        return _insufficient("label classes too thin to calibrate",
                             n_labeled=len(items), label_counts=dict(counts))
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x = [list(r["x"]) for r in items]
    y = [int(r["y"]) for r in items]
    base = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
    model.fit(x, y)
    fitted: Status = {"status": "OK", "model": model, "n_labeled": len(items),
                      "base_rate": sum(y) / float(len(y)), "label_counts": dict(counts),
                      "feature_names": rows.get("feature_names") if isinstance(rows, dict) else None,
                      "strategies": rows.get("strategies") if isinstance(rows, dict) else None}
    preds = model.predict_proba(x)[:, 1]
    fitted["in_sample_brier"] = sum((p - t) ** 2 for p, t in zip(preds, y)) / float(len(y))
    return fitted


def predict_p_correct(fitted: Status,
                      rows: Union[Status, Sequence[Dict[str, Any]]]) -> Union[Status, List[float]]:
    """P(primary decision is correct) per row, or the INSUFFICIENT object unchanged."""
    if not isinstance(fitted, dict) or fitted.get("status") != "OK":
        return fitted
    items = _rows_of(rows)
    if not items:
        return []
    return [float(p) for p in fitted["model"].predict_proba([list(r["x"]) for r in items])[:, 1]]


def size_from_meta(p_correct: Union[float, Status], kelly_cap: float = DEFAULT_KELLY_CAP,
                   floor: float = DEFAULT_FLOOR, payoff_b: float = 1.0) -> float:
    """Capped fractional Kelly on the META probability -> size in UNITS.

    0 units below `floor` (an uncertain secondary model does not size), monotone
    non-decreasing in p_correct above it, never above `kelly_cap` units.
    """
    if isinstance(p_correct, dict):  # no model yet -> no size
        return 0.0
    try:
        prob = float(p_correct)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(prob) or prob < floor or payoff_b <= 0.0:
        return 0.0
    kelly = (prob * payoff_b - (1.0 - prob)) / payoff_b
    return float(min(max(kelly, 0.0), max(kelly_cap, 0.0)))


def ledger_report(decision_ledger_path: Union[str, Path]) -> Status:
    """Coverage summary: how far the ledger is from being trainable, per strategy."""
    records = read_ledger(decision_ledger_path)
    labeled = [r for r in records if r["label"] is not None]
    stamps = sorted(str(r["ts"]) for r in records if r["ts"])
    by_strategy = {s: {"n": 0, "n_labeled": 0} for s in sorted({r["strategy"] for r in records})}
    for rec in records:
        cell = by_strategy[rec["strategy"]]
        cell["n"] += 1
        cell["n_labeled"] += int(rec["label"] is not None)
    common = {"n_records": len(records), "n_labeled": len(labeled),
              "n_unsettled": len(records) - len(labeled),
              "hit_rate": (sum(int(r["label"]) for r in labeled) / float(len(labeled))
                           if labeled else None),
              "by_strategy": by_strategy,
              "first_ts": stamps[0] if stamps else None,
              "last_ts": stamps[-1] if stamps else None,
              "path": str(decision_ledger_path)}
    if len(labeled) < MIN_LABELED_ROWS:
        return _insufficient("collecting: not enough settled decisions yet", **common)
    return dict(status="OK", required=MIN_LABELED_ROWS, rows_needed=0, **common)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Meta-labeling sizer scaffold (coverage + fit).")
    parser.add_argument("ledger", help="paper decision ledger (.jsonl)")
    parser.add_argument("--fit", action="store_true", help="attempt to fit the meta model")
    args = parser.parse_args(argv)
    report = ledger_report(args.ledger)
    print("coverage: status=%s labeled=%d/%d unsettled=%d" % (
        report["status"], report["n_labeled"], MIN_LABELED_ROWS, report["n_unsettled"]))
    if report["status"] != "OK":
        print("INSUFFICIENT: %s (need %d more settled rows)" % (
            report["note"], report["rows_needed"]))
        return 0
    if args.fit:
        fitted = fit_meta(build_training_rows(args.ledger))
        if fitted["status"] != "OK":
            print("INSUFFICIENT: %s" % fitted["note"])
        else:
            print("fit: n=%d base_rate=%.4f in_sample_brier=%.4f (calibration only)" % (
                fitted["n_labeled"], fitted["base_rate"], fitted["in_sample_brier"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
