"""
line_timing.py — Closing-line prediction (task 16.7-01).

Predicts where a prop/game line will close, so the system can fire early
(value capture) or wait (avoid a bad fill).  A gradient-boosted regression
maps pre-tip market features to the expected closing price.

Training rows come from data/output/line_timing_history.json — a labelled
log of observed (features, closing_price) pairs.  Until that history
accumulates, train()/evaluate() also accept injected rows for testing.

Public API
----------
    build_training_data(history_path)      -> list[dict]
    train(rows, model_path)                -> dict   (metrics incl. mae)
    evaluate(rows, model_path)             -> dict   ({mae, rmse, n})
    predict_closing_price(features)        -> float
    load_model(model_path)                 -> dict
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sys
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_HISTORY_PATH = os.path.join(_OUTPUT_DIR, "line_timing_history.json")
_MODEL_PATH   = os.path.join(_MODEL_DIR, "line_timing.pkl")

# Features the closing-price model consumes.  Order is significant — it is
# baked into the serialised bundle and reused at inference time.
FEATURE_COLUMNS = [
    "open_price",
    "time_to_game",
    "lineup_news",
    "public_pct",
    "sharp_pct",
    "line_velocity",
]
_TARGET = "closing_price"

# Minimum labelled rows before a regression is meaningful.
_MIN_ROWS = 20

log = logging.getLogger(__name__)

_CACHED_BUNDLE: Optional[dict] = None


# ── training data ─────────────────────────────────────────────────────────────

def build_training_data(history_path: Optional[str] = None) -> List[Dict]:
    """Load labelled (features, closing_price) rows from the history log.

    The history log is appended to as lines are observed closing across the
    season.  Returns [] when the log is absent — a real but empty dataset is
    a valid (if untrainable) state, not an error.
    """
    path = history_path or _HISTORY_PATH
    if not os.path.exists(path):
        log.info("line_timing history not found (%s) — no training rows yet", path)
        return []
    try:
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read line_timing history: %s", exc)
        return []

    rows: List[Dict] = []
    for rec in records:
        if rec.get(_TARGET) is None or rec.get("open_price") is None:
            continue
        rows.append(rec)
    log.info("line_timing: %d labelled rows from %s", len(rows), path)
    return rows


def record_line_observation(record: Dict, history_path: Optional[str] = None) -> None:
    """Append one observed (features + closing_price) record to the history log."""
    path = history_path or _HISTORY_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing: List[Dict] = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:  # noqa: BLE001
            existing = []
    existing.append(record)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def _xy(rows: List[Dict]):
    """Split rows into an (X, y) pair of plain Python lists."""
    X, y = [], []
    for r in rows:
        feat = []
        ok = True
        for col in FEATURE_COLUMNS:
            val = r.get(col)
            if val is None:
                val = 0.0
            try:
                feat.append(float(val))
            except (TypeError, ValueError):
                ok = False
                break
        target = r.get(_TARGET)
        if not ok or target is None:
            continue
        X.append(feat)
        y.append(float(target))
    return X, y


# ── training ──────────────────────────────────────────────────────────────────

def train(
    rows: Optional[List[Dict]] = None,
    model_path: Optional[str] = None,
    *,
    test_size: float = 0.25,
    seed: int = 42,
) -> dict:
    """Train the closing-price regression and serialise it.

    Args:
        rows:       Labelled training rows.  If None, loaded via build_training_data.
        model_path: Destination pkl (default: data/models/line_timing.pkl).

    Returns:
        Metrics dict: {n_rows, n_train, n_test, mae, rmse}.

    Raises:
        ValueError: when fewer than _MIN_ROWS labelled rows are available.
    """
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.model_selection import train_test_split

    rows = rows if rows is not None else build_training_data()
    model_path = model_path or _MODEL_PATH

    X, y = _xy(rows)
    if len(X) < _MIN_ROWS:
        raise ValueError(
            f"line_timing training set has {len(X)} rows (< {_MIN_ROWS}); "
            f"accumulate more closed lines before training."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed
    )
    model = GradientBoostingRegressor(
        n_estimators=150, max_depth=3, learning_rate=0.1, random_state=seed
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))
    rmse = float(mean_squared_error(y_test, preds) ** 0.5)

    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": {
            "n_rows": len(X),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
        },
    }
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(bundle, f)

    global _CACHED_BUNDLE
    _CACHED_BUNDLE = bundle
    log.info("line_timing trained: closing-price MAE=%.4f over %d held-out lines -> %s",
             mae, len(X_test), model_path)
    return bundle["metrics"]


def evaluate(rows: Optional[List[Dict]] = None, model_path: Optional[str] = None) -> dict:
    """Score the trained model on historical rows and log the MAE.

    Returns {mae, rmse, n}.  Used to satisfy the acceptance criterion that
    the closing-price model is evaluated on historical line data.
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    rows = rows if rows is not None else build_training_data()
    bundle = load_model(model_path)
    X, y = _xy(rows)
    if not X:
        log.warning("line_timing evaluate: no rows — MAE undefined")
        return {"mae": None, "rmse": None, "n": 0}

    preds = bundle["model"].predict(X)
    mae = float(mean_absolute_error(y, preds))
    rmse = float(mean_squared_error(y, preds) ** 0.5)
    log.info("line_timing evaluation: closing-price MAE=%.4f, RMSE=%.4f over %d historical lines",
             mae, rmse, len(X))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "n": len(X)}


# ── inference ─────────────────────────────────────────────────────────────────

def load_model(model_path: Optional[str] = None, *, use_cache: bool = True) -> dict:
    """Load the serialised closing-price model bundle (process-cached)."""
    global _CACHED_BUNDLE
    model_path = model_path or _MODEL_PATH
    if use_cache and _CACHED_BUNDLE is not None:
        return _CACHED_BUNDLE
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"line_timing model not found: {model_path} — run line_timing.train() first"
        )
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)
    if use_cache:
        _CACHED_BUNDLE = bundle
    return bundle


def predict_closing_price(features: Dict, model_path: Optional[str] = None) -> float:
    """Predict the closing price for one line given its pre-tip features."""
    bundle = load_model(model_path)
    cols = bundle["feature_columns"]
    row = [[float(features.get(c, 0.0) or 0.0) for c in cols]]
    return float(bundle["model"].predict(row)[0])


def clear_cache() -> None:
    """Drop the process-level model cache (used by tests after retraining)."""
    global _CACHED_BUNDLE
    _CACHED_BUNDLE = None


# ── steam detection (task 16.7-02) ───────────────────────────────────────────

# A qualifying steam move: > 0.5 pt Pinnacle move inside a 5-minute window.
STEAM_MOVE_THRESHOLD = 0.5    # points
STEAM_WINDOW_MINUTES = 5.0    # minutes


def _parse_ts(value):
    """Parse an ISO-8601 string (or pass through a datetime) to datetime."""
    from datetime import datetime as _dt
    if hasattr(value, "year"):
        return value
    return _dt.fromisoformat(str(value).replace("Z", "+00:00"))


def detect_steam(
    line_history: List[Dict],
    *,
    threshold: float = STEAM_MOVE_THRESHOLD,
    window_minutes: float = STEAM_WINDOW_MINUTES,
) -> Optional[dict]:
    """Scan a Pinnacle line-snapshot history for a qualifying steam move.

    A STEAM event fires when the line moves more than ``threshold`` points
    within any ``window_minutes`` span — the clearest sharp-money signal.
    Returns the first such event chronologically (so a replay detects it at
    the snapshot that completes the move, well inside the 2-minute target),
    or None when no qualifying move exists.

    Args:
        line_history:   Chronological [{"timestamp", "line"}] snapshots, e.g.
                         from pinnacle_monitor.get_line_history().
        threshold:      Minimum absolute points moved to qualify.
        window_minutes: Maximum span over which the move must occur.

    Returns:
        ``{"event": "STEAM", "direction", "velocity", "magnitude",
           "from_line", "to_line", "elapsed_minutes", "detected_at"}`` or None.
    """
    snaps = sorted(
        (s for s in line_history if s.get("line") is not None and s.get("timestamp")),
        key=lambda s: s["timestamp"],
    )
    if len(snaps) < 2:
        return None

    for j in range(1, len(snaps)):
        t_j = _parse_ts(snaps[j]["timestamp"])
        for i in range(j - 1, -1, -1):
            t_i = _parse_ts(snaps[i]["timestamp"])
            elapsed = (t_j - t_i).total_seconds() / 60.0
            if elapsed > window_minutes:
                break  # earlier snapshots are all outside the window
            move = float(snaps[j]["line"]) - float(snaps[i]["line"])
            if abs(move) > threshold and elapsed > 0:
                return {
                    "event": "STEAM",
                    "direction": "over" if move > 0 else "under",
                    "velocity": round(move / elapsed, 4),       # pts / minute
                    "magnitude": round(move, 4),                # signed pts
                    "from_line": float(snaps[i]["line"]),
                    "to_line": float(snaps[j]["line"]),
                    "elapsed_minutes": round(elapsed, 4),
                    "detected_at": str(snaps[j]["timestamp"]),
                }
    return None


# ── RLM annotation (task 16.7-04) ────────────────────────────────────────────

# Public-lean threshold: tickets % beyond this counts as a real public side.
RLM_PUBLIC_THRESHOLD = 55.0


def annotate_rlm(
    event: Optional[dict],
    public_bets_pct: float,
    *,
    public_threshold: float = RLM_PUBLIC_THRESHOLD,
) -> Optional[dict]:
    """Tag a steam event as reverse line movement (RLM) or public-driven.

    RLM is the sharp-money tell: the line moves *against* where the public
    money sits.  When the line instead follows the public lean, the move is
    public-driven and should not be treated as a sharp signal.

    Args:
        event:            A steam event from detect_steam() (or None).
        public_bets_pct:  % of public tickets on the over (0–100).
        public_threshold: Tickets % beyond which a public side is recognised.

    Returns:
        The same event dict with ``rlm`` (bool) and ``move_source``
        ("sharp" | "public" | "unknown") added; None passes through.
    """
    if event is None:
        return None
    direction = event.get("direction")
    public_over = public_bets_pct > public_threshold
    public_under = public_bets_pct < (100.0 - public_threshold)

    rlm = (public_over and direction == "under") or \
          (public_under and direction == "over")

    if (public_over and direction == "over") or (public_under and direction == "under"):
        move_source = "public"          # line followed the public — not sharp
    elif rlm:
        move_source = "sharp"           # line moved against the public — RLM
    else:
        move_source = "unknown"         # no clear public side

    event["rlm"] = bool(rlm)
    event["move_source"] = move_source
    event["public_bets_pct"] = round(float(public_bets_pct), 1)
    return event


def annotate_steam_from_action_network(
    event: Optional[dict],
    player_name: str,
    stat: str,
    *,
    public_threshold: float = RLM_PUBLIC_THRESHOLD,
) -> Optional[dict]:
    """Ingest the public lean from action_network and annotate RLM on an event.

    Degrades gracefully: if action_network is unavailable the event's ``rlm``
    is left as None rather than raising.
    """
    if event is None:
        return None
    try:
        from src.data.action_network import get_sharp_pct
        sig = get_sharp_pct(player_name, stat)
        public_bets_pct = float(sig.get("public_bets_pct", 50.0))
    except Exception as exc:  # noqa: BLE001
        log.warning("action_network unavailable (%s) — RLM left unannotated", exc)
        event["rlm"] = None
        event["move_source"] = "unknown"
        return event
    return annotate_rlm(event, public_bets_pct, public_threshold=public_threshold)


# ── timing optimisation (task 16.7-03) ──────────────────────────────────────

# Minimum favourable line movement (points) that justifies delaying a fire.
FIRE_MIN_GAIN = 0.25


def get_fire_recommendation(
    bet: Dict,
    *,
    predict_fn=None,
    model_path: Optional[str] = None,
    min_gain: float = FIRE_MIN_GAIN,
) -> dict:
    """Recommend firing a bet now or waiting for a better closing line.

    Uses the closing-price model: if the line is expected to move in our
    favour by more than ``min_gain`` points, waiting captures extra value;
    otherwise the value is best locked in immediately.

    Args:
        bet:        A bet dict (direction, book_line, and any timing features).
        predict_fn: Optional callable(features)->closing_price for testing.
        model_path: Override path to line_timing.pkl.
        min_gain:   Favourable-movement threshold (points) to justify waiting.

    Returns:
        ``{"action": "fire_now"|"wait", "predicted_closing", "current_line",
           "expected_gain", "delay_minutes", "reason"}``.  Degrades to
        "fire_now" whenever no closing-price model is available.
    """
    direction = str(bet.get("direction", "over")).lower()
    current_line = bet.get("book_line")
    ttg_hours = float(bet.get("time_to_game", bet.get("time_to_game_hours", 0.0)) or 0.0)
    feats = {
        "open_price": float(current_line) if current_line is not None else 0.0,
        "time_to_game": ttg_hours,
        "lineup_news": float(bet.get("lineup_news", 0.0) or 0.0),
        "public_pct": float(bet.get("public_pct", 50.0) or 50.0),
        "sharp_pct": float(bet.get("sharp_pct", 50.0) or 50.0),
        "line_velocity": float(bet.get("line_velocity", 0.0) or 0.0),
    }

    predicted: Optional[float] = None
    if current_line is not None:
        try:
            predicted = float(predict_fn(feats)) if predict_fn is not None \
                else predict_closing_price(feats, model_path)
        except FileNotFoundError:
            predicted = None
        except Exception as exc:  # noqa: BLE001 — a bad prediction must not block firing
            log.warning("get_fire_recommendation: prediction failed (%s)", exc)
            predicted = None

    if predicted is None or current_line is None:
        return {"action": "fire_now", "predicted_closing": predicted,
                "current_line": current_line, "expected_gain": 0.0,
                "delay_minutes": 0.0,
                "reason": "no closing-line model — fire immediately"}

    # over bets want a LOWER line; under bets want a HIGHER line.
    if direction == "over":
        expected_gain = float(current_line) - predicted
    else:
        expected_gain = predicted - float(current_line)

    if expected_gain > min_gain:
        delay_minutes = round(min(max(ttg_hours * 60.0 * 0.5, 0.0), 90.0), 1)
        return {"action": "wait", "predicted_closing": round(predicted, 4),
                "current_line": float(current_line),
                "expected_gain": round(expected_gain, 4),
                "delay_minutes": delay_minutes,
                "reason": f"line expected to move {expected_gain:+.2f} pt in our favour"}

    return {"action": "fire_now", "predicted_closing": round(predicted, 4),
            "current_line": float(current_line),
            "expected_gain": round(expected_gain, 4), "delay_minutes": 0.0,
            "reason": "no favourable line movement expected — lock value now"}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Closing-line prediction")
    ap.add_argument("--train", action="store_true", help="Train on line_timing_history.json")
    ap.add_argument("--evaluate", action="store_true", help="Evaluate + log MAE")
    args = ap.parse_args()

    if args.train:
        print(json.dumps(train(), indent=2))
    if args.evaluate:
        print(json.dumps(evaluate(), indent=2))
    if not (args.train or args.evaluate):
        ap.print_help()
