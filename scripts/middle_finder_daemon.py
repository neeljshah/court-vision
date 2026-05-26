"""middle_finder_daemon.py — continuous cross-book middling / arbitrage scanner.

Loops every --interval-sec, reads the latest snapshot per (book, player, stat)
from data/lines/<today>_<book>.csv, pairs OVER@A with UNDER@B on the same
(player, stat) where lineB > lineA — i.e. an actual outcome between lineA and
lineB wins BOTH legs (the "middle"). Filters by minimum middle width and
worst-case juice. Free arbs (both sides positive American odds) are flagged
URGENTLY — that's a guaranteed +EV regardless of result.

Optional bonus: cross-references the model's q50 prediction; if the predicted
median lands inside the middle band, the opportunity is double-flagged as
model-confirmed (>=10% expected hit rate via the calibrated q10/q90 gaussian).

Output:
    data/cache/middles_live.json   (atomic write each tick)

CLI:
    python scripts/middle_finder_daemon.py \\
        --interval-sec 30 --min-width 0.5 --max-juice-each-side -135
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import signal
import sys
import time
from datetime import datetime, date as _date
from math import erf, sqrt

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

OUT_JSON = os.path.join(PROJECT_DIR, "data", "cache", "middles_live.json")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
BOOKS = ("fd", "bov", "pin")

# Model is optional: if importable, we add the model-confirmed flag.
try:
    from src.prediction.prop_pergame import (  # noqa: E402
        STATS as MODEL_STATS, build_prediction_row, predict_pergame,
    )
    from src.prediction.prop_quantiles import (  # noqa: E402
        predict_pergame_quantiles,
    )
    from src.prediction.quantile_calibration import (  # noqa: E402
        apply as apply_quantile_calibration,
    )
    _MODEL_OK = True
except Exception as _exc:  # pragma: no cover - model is optional
    MODEL_STATS = ()
    build_prediction_row = None
    predict_pergame = None
    predict_pergame_quantiles = None
    apply_quantile_calibration = None
    _MODEL_OK = False


# ---------------------------------------------------------------------------
# CSV loading — robust to Bovada schema drift (10 or 11 cols).
# ---------------------------------------------------------------------------
_CANON = ["captured_at", "book", "game_id", "player_id", "player_name",
          "stat", "line", "over_price", "under_price", "start_time"]


def _read_lines_csv(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return rows
        for row in reader:
            if len(row) == 10:
                d = dict(zip(_CANON, row))
            elif len(row) == 11:
                d = {
                    "captured_at": row[0], "book": row[1],
                    "game_id": row[2], "player_id": row[3],
                    "player_name": row[4],
                    "stat": row[6], "line": row[7],
                    "over_price": row[8], "under_price": row[9],
                    "start_time": row[10],
                }
            else:
                continue
            rows.append(d)
    return rows


def _to_int(s):
    if s is None or s == "" or s == "None":
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _to_float(s):
    if s is None or s == "" or s == "None":
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00").split("+")[0])
    except Exception:
        return None


def load_latest_snapshots(date_str, lines_dir=LINES_DIR, books=BOOKS):
    """Return dict[(player, stat)][book] -> list of {line, over_price, under_price}.

    For each (book, player, stat, line) keep only the latest captured_at.
    """
    index = {}
    for book in books:
        path = os.path.join(lines_dir, f"{date_str}_{book}.csv")
        rows = _read_lines_csv(path)
        # latest per (player, stat, line, side) — keep both sides
        latest = {}
        for r in rows:
            line = _to_float(r.get("line"))
            if line is None:
                continue
            key = (r.get("player_name", "").strip(),
                   r.get("stat", "").strip().lower(),
                   round(line, 2))
            if not key[0] or not key[1]:
                continue
            ts = _parse_dt(r.get("captured_at"))
            cur = latest.get(key)
            if cur is None or (ts is not None and (cur["_ts"] is None
                                                    or ts > cur["_ts"])):
                latest[key] = {
                    "_ts": ts,
                    "line": line,
                    "over_price": _to_int(r.get("over_price")),
                    "under_price": _to_int(r.get("under_price")),
                }
        for (player, stat, _line), v in latest.items():
            pkey = (player, stat)
            bdict = index.setdefault(pkey, {})
            blist = bdict.setdefault(book, [])
            blist.append({
                "line": v["line"],
                "over_price": v["over_price"],
                "under_price": v["under_price"],
            })
    return index


# ---------------------------------------------------------------------------
# Middle detection.
# ---------------------------------------------------------------------------
def american_to_decimal(odds):
    if odds is None:
        return None
    o = int(odds)
    if o > 0:
        return 1 + o / 100.0
    if o < 0:
        return 1 + 100.0 / (-o)
    return None


def implied_prob(odds):
    if odds is None:
        return None
    o = int(odds)
    if o > 0:
        return 100.0 / (o + 100)
    if o < 0:
        return (-o) / ((-o) + 100)
    return None


def is_free_arb(over_price, under_price):
    """Both legs positive American odds => guaranteed +EV regardless of result."""
    if over_price is None or under_price is None:
        return False
    return over_price > 0 and under_price > 0


def arb_profit_pct(over_price, under_price):
    """Sum-of-implied-probs based: if <1.0 you have a true arb. Returns the
    risk-free return % if you split stakes proportionally; None otherwise."""
    po = implied_prob(over_price)
    pu = implied_prob(under_price)
    if po is None or pu is None:
        return None
    s = po + pu
    if s >= 1.0:
        return None
    return (1.0 / s - 1.0) * 100.0


def find_middles(index, min_width=0.5, max_juice_each_side=-135):
    """Scan the latest-snapshot index for cross-book middles.

    A middle is: book_A OVER X paired with book_B UNDER Y, where Y > X.
    A 0.5-wide middle (e.g. OVER 24.5 / UNDER 25.5) is the most common case.
    The 'gap' (Y - X) is what we hit on if the actual lands in (X, Y).

    Filters:
        - book_A != book_B
        - gap >= min_width (default 0.5)
        - over_price >= max_juice_each_side AND under_price >= max_juice_each_side
          (e.g. -135 means we tolerate down to -135 on each leg)

    Returns a list of dicts sorted by (free_arb desc, width desc).
    """
    middles = []
    for (player, stat), books_dict in index.items():
        overs = []   # (book, line, price)
        unders = []
        for book, rows in books_dict.items():
            for r in rows:
                if r["over_price"] is not None:
                    overs.append((book, r["line"], r["over_price"]))
                if r["under_price"] is not None:
                    unders.append((book, r["line"], r["under_price"]))
        for (bo, lo, po) in overs:
            for (bu, lu, pu) in unders:
                if bo == bu:
                    continue
                width = lu - lo
                if width < min_width:
                    continue
                # exclude absurd alt-line "fake" middles
                if width > 10.0:
                    continue
                worst = min(po, pu)
                if worst < max_juice_each_side:
                    continue
                free = is_free_arb(po, pu)
                arb_pct = arb_profit_pct(po, pu)
                middles.append({
                    "player": player,
                    "stat": stat,
                    "over_book": bo,
                    "over_line": lo,
                    "over_price": po,
                    "under_book": bu,
                    "under_line": lu,
                    "under_price": pu,
                    "middle_width": round(width, 2),
                    "worst_price": worst,
                    "free_arb": free,
                    "arb_profit_pct": arb_pct,
                })
    middles.sort(key=lambda m: (not m["free_arb"], -m["middle_width"],
                                  -m["worst_price"]))
    return middles


# ---------------------------------------------------------------------------
# Model-confirmed flag.
# ---------------------------------------------------------------------------
def _norm_cdf(z):
    return 0.5 * (1 + erf(z / sqrt(2)))


def _model_band_prob(stat, qint, lo, hi):
    """Probability that the actual outcome lands in (lo, hi] under the
    calibrated quantile band approximated as Gaussian with sigma = (q90-q10)/(2*1.2816)."""
    if qint is None:
        return None
    q10, q50, q90 = qint.get("q10"), qint.get("q50"), qint.get("q90")
    if q10 is None or q90 is None or q50 is None:
        return None
    cal_q10, cal_q90 = apply_quantile_calibration(stat, q10, q50, q90)
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    z_hi = (hi - q50) / sigma
    z_lo = (lo - q50) / sigma
    return _norm_cdf(z_hi) - _norm_cdf(z_lo)


def annotate_model_confirmed(middles, predictor, min_band_prob=0.10):
    """For each middle, ask the predictor for q10/q50/q90 of the player's stat
    and compute the probability the actual outcome lands in the middle band.
    If >= min_band_prob, set model_confirmed=True."""
    cache = {}
    for m in middles:
        key = (m["player"], m["stat"])
        if key not in cache:
            cache[key] = predictor(m["player"], m["stat"])
        qint = cache[key]
        band_prob = _model_band_prob(m["stat"], qint, m["over_line"],
                                      m["under_line"]) if qint else None
        m["model_band_prob"] = band_prob
        m["model_confirmed"] = bool(band_prob is not None
                                      and band_prob >= min_band_prob)
    return middles


# ---------------------------------------------------------------------------
# Atomic write.
# ---------------------------------------------------------------------------
def atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp." + str(os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Daemon loop.
# ---------------------------------------------------------------------------
_STOP = False


def _on_signal(signum, frame):
    global _STOP
    _STOP = True


def _today_str():
    return _date.today().isoformat()


class _RealModelPredictor:
    """Lazy NBA prop model predictor. Caches per-player prediction rows."""

    def __init__(self, season="2024-25"):
        self.season = season
        self.gamelog_dir = os.path.join(PROJECT_DIR, "data", "nba")
        self.model_dir = os.path.join(PROJECT_DIR, "data", "models")
        self._row_cache = {}
        self._pid_cache = {}

    def _resolve_pid(self, name):
        if name in self._pid_cache:
            return self._pid_cache[name]
        try:
            from nba_api.stats.static import players
            import unicodedata

            def _strip(s):
                n = unicodedata.normalize("NFKD", str(s))
                return "".join(c for c in n if not unicodedata.combining(c)).lower()
            needle = _strip(name)
            pid = None
            for p in players.get_players():
                if _strip(p["full_name"]) == needle:
                    pid = int(p["id"]); break
            if pid is None:
                for p in players.get_players():
                    if needle in _strip(p["full_name"]):
                        pid = int(p["id"]); break
            self._pid_cache[name] = pid
            return pid
        except Exception:
            self._pid_cache[name] = None
            return None

    def __call__(self, player, stat):
        if stat not in MODEL_STATS:
            return None
        pid = self._resolve_pid(player)
        if pid is None:
            return None
        prow = self._row_cache.get(pid)
        if prow is None:
            try:
                prow = build_prediction_row(pid, "NBA", self.season,
                                             is_home=True, rest_days=2.0,
                                             gamelog_dir=self.gamelog_dir)
            except Exception:
                prow = None
            self._row_cache[pid] = prow
        if prow is None:
            return None
        try:
            return predict_pergame_quantiles(stat, prow, self.model_dir)
        except Exception:
            return None


def run_once(date_str, min_width, max_juice, predictor=None,
              min_band_prob=0.10):
    index = load_latest_snapshots(date_str)
    middles = find_middles(index, min_width=min_width,
                            max_juice_each_side=max_juice)
    if predictor is not None:
        middles = annotate_model_confirmed(middles, predictor,
                                            min_band_prob=min_band_prob)
    return middles, index


def loop(interval_sec, min_width, max_juice, max_iters=None,
          use_model=True, min_band_prob=0.10, out_json=OUT_JSON, log=print):
    predictor = None
    if use_model and _MODEL_OK:
        try:
            predictor = _RealModelPredictor()
        except Exception as exc:
            log(f"[warn] model init failed: {exc}; continuing without model.")
            predictor = None
    stats = {"ticks": 0, "total_middles": 0, "max_middles_in_tick": 0,
              "free_arbs_total": 0, "model_confirmed_total": 0}
    signal.signal(signal.SIGTERM, _on_signal)
    try:
        signal.signal(signal.SIGINT, _on_signal)
    except Exception:
        pass
    while not _STOP:
        t0 = time.time()
        try:
            middles, index = run_once(_today_str(), min_width, max_juice,
                                        predictor=predictor,
                                        min_band_prob=min_band_prob)
        except Exception as exc:
            log(f"[err] tick failed: {exc}")
            middles = []
            index = {}
        n_free = sum(1 for m in middles if m.get("free_arb"))
        n_conf = sum(1 for m in middles if m.get("model_confirmed"))
        stats["ticks"] += 1
        stats["total_middles"] += len(middles)
        stats["max_middles_in_tick"] = max(stats["max_middles_in_tick"],
                                             len(middles))
        stats["free_arbs_total"] += n_free
        stats["model_confirmed_total"] += n_conf
        payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "tick": stats["ticks"],
            "n_pairs_scanned": sum(
                sum(len(rows) for rows in bd.values())
                for bd in index.values()
            ),
            "n_player_stats": len(index),
            "config": {"min_width": min_width, "max_juice_each_side": max_juice,
                        "model_confirmed_threshold": min_band_prob},
            "n_middles": len(middles),
            "n_free_arbs": n_free,
            "n_model_confirmed": n_conf,
            "middles": middles,
        }
        try:
            atomic_write_json(out_json, payload)
        except Exception as exc:
            log(f"[err] atomic write failed: {exc}")
        log(f"[tick {stats['ticks']}] middles={len(middles)} "
            f"free_arbs={n_free} model_confirmed={n_conf} "
            f"(took {time.time() - t0:.2f}s)")
        if max_iters is not None and stats["ticks"] >= max_iters:
            break
        # interruptible sleep
        for _ in range(int(interval_sec * 10)):
            if _STOP:
                break
            time.sleep(0.1)
    return stats


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interval-sec", type=float, default=30.0)
    p.add_argument("--min-width", type=float, default=0.5)
    p.add_argument("--max-juice-each-side", type=int, default=-135,
                    help="Worst American odds tolerated on either leg "
                         "(e.g. -135).")
    p.add_argument("--no-model", action="store_true",
                    help="Skip model-confirmed annotation.")
    p.add_argument("--model-band-prob", type=float, default=0.10,
                    help="Min model band probability for model_confirmed flag.")
    p.add_argument("--max-iters", type=int, default=None,
                    help="If set, exit after N ticks (for testing).")
    p.add_argument("--out-json", type=str, default=OUT_JSON)
    args = p.parse_args(argv)

    stats = loop(args.interval_sec, args.min_width, args.max_juice_each_side,
                  max_iters=args.max_iters, use_model=not args.no_model,
                  min_band_prob=args.model_band_prob, out_json=args.out_json)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
