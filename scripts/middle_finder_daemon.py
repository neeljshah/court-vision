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

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False

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
# CSV loading — robust to Bovada schema drift (10 / 11 / 12 cols).
# R19_L1: 12-col schema adds `is_alt_line` (true/false string). Older 10/11-col
# rows are treated as primary (is_alt_line=false) for back-compat.
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
            header = next(reader)
        except StopIteration:
            return rows
        # Detect column index of is_alt_line from header, if present.
        try:
            alt_idx = header.index("is_alt_line")
        except ValueError:
            alt_idx = None
        for row in reader:
            if len(row) == 10:
                d = dict(zip(_CANON, row))
                d["is_alt_line"] = "false"  # legacy default
            elif len(row) == 11:
                d = {
                    "captured_at": row[0], "book": row[1],
                    "game_id": row[2], "player_id": row[3],
                    "player_name": row[4],
                    "stat": row[6], "line": row[7],
                    "over_price": row[8], "under_price": row[9],
                    "start_time": row[10],
                    "is_alt_line": "false",  # legacy 11-col default
                }
            elif len(row) == 12:
                # New schema: captured_at, book, game_id, player_id,
                # player_name, team, stat, line, over_price, under_price,
                # market_status, is_alt_line. `start_time` lives in
                # market_status slot under new schema; keep both keys for
                # back-compat downstream.
                d = {
                    "captured_at": row[0], "book": row[1],
                    "game_id": row[2], "player_id": row[3],
                    "player_name": row[4],
                    "stat": row[6], "line": row[7],
                    "over_price": row[8], "under_price": row[9],
                    "start_time": row[10],
                    "market_status": row[10],
                    "is_alt_line": (row[alt_idx] if alt_idx is not None
                                     and alt_idx < len(row) else row[11]),
                }
            else:
                continue
            rows.append(d)
    return rows


def _is_alt_truthy(v):
    """Lenient bool-parse for the is_alt_line column (csv values come in as
    'true'/'false' strings, may also be empty for legacy rows)."""
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("true", "1", "yes", "y", "t")


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


def classify_market_tier(rows, csv_alt_present=False):
    """R20_M1: classify a (player, stat, book) ladder into primary vs alt rungs.

    The Bov scraper already writes `is_alt_line` (R19_L1), but:
      * legacy on-disk CSVs for ANY book may be missing the column, and
      * FD / Pin scrapers DO NOT write the flag — they emit ladders too
        (e.g. FD writes SGA pts at 19.5, 24.5, 29.5 all as primary-looking
        rows). Without re-classification at load time, the arb engine pairs
        FD-OVER-19.5 with Pin-UNDER-28.5 and reports a bogus 'free arb'.

    Heuristic (book-agnostic, used WHENEVER `csv_alt_present=False`):
      1. If only one rung exists, it is `primary`.
      2. Otherwise, score each rung by (in order, lower = better):
           a. is_one_sided (two-sided rungs always beat one-sided).
           b. R24_Q1: |line - ladder_median_line| — the realistic anchor
              sits near the cluster center; alt rungs fan out around it.
              This is the primary tiebreaker (was previously fourth),
              because a symmetric edge alt rung (e.g. 3.5 @ -115/-115)
              can game a spread-only score.
           c. |over_implied - under_implied| (balance) — carried forward.
           d. |over_implied + under_implied - 1| (total vig) — final
              tiebreaker so the lower-vig rung wins on a perfect tie.
      3. If a rung is missing one side (no over OR no under price), it
         cannot be primary (single-sided ladder rungs are alts).

    When `csv_alt_present=True`, trust the CSV column (writer already
    classified) — only fill in the `market_tier` string equivalent.

    Mutates `rows` in place: each row gets `is_alt_line: bool` and
    `market_tier: 'primary'|'alt'`. Returns the same list for chaining.
    """
    if not rows:
        return rows

    # Trust writer-side classification when present.
    if csv_alt_present:
        for r in rows:
            alt = bool(r.get("is_alt_line"))
            r["is_alt_line"] = alt
            r["market_tier"] = "alt" if alt else "primary"
        return rows

    def _vig(r):
        po = implied_prob(r.get("over_price"))
        pu = implied_prob(r.get("under_price"))
        if po is None or pu is None:
            # Single-sided rung: cannot be primary.
            return (9.99, 9.99)
        return (abs(po + pu - 1.0), abs(po - pu))

    if len(rows) == 1:
        rows[0]["is_alt_line"] = False
        rows[0]["market_tier"] = "primary"
        return rows

    numeric_lines = [float(r["line"]) for r in rows if r.get("line") is not None]
    median = (sorted(numeric_lines)[len(numeric_lines) // 2]
              if numeric_lines else 0.0)

    def _score(r):
        # R24_Q1: distance-from-ladder-median is the PRIMARY tiebreaker,
        # ahead of spread/vig. R20_M1's spread-first ordering picked the
        # wrong rung when a low-line symmetric alt rung (e.g. 3.5 PTS at
        # -115/-115 for an NBA SF) had a perfectly-balanced 0 spread that
        # beat the realistic mid-ladder line. The book's true anchor sits
        # near the cluster median; alt rungs fan out around it. So:
        #   1. is_one_sided: two-sided rungs always beat one-sided
        #      (preserves the existing FD over-only safety net).
        #   2. distance_from_ladder_median: rung closest to the cluster
        #      center wins (NEW — fixes Vassell + Dort cases).
        #   3. spread |over_prob - under_prob|: balance tiebreaker
        #      (carried forward from R20_M1).
        #   4. total_vig |over_prob + under_prob - 1|: final tiebreaker
        #      so the lower-vig rung wins on a clean distance+spread tie
        #      (the test_R24_Q1 even-rung-count expectation).
        v = _vig(r)
        line_val = float(r.get("line") or 0.0)
        one_sided = 1 if (r.get("over_price") is None
                          or r.get("under_price") is None) else 0
        return (one_sided, abs(line_val - median), v[1], v[0])

    primary = min(rows, key=_score)
    # Guard: primary must have BOTH sides priced. If the winning rung is
    # one-sided (vig sentinel 9.99), no rung qualifies as primary — mark all
    # as alt so the arb engine ignores the whole cluster (safe default).
    primary_has_both = (primary.get("over_price") is not None
                        and primary.get("under_price") is not None)
    for r in rows:
        is_alt = (not primary_has_both) or (r is not primary)
        r["is_alt_line"] = is_alt
        r["market_tier"] = "alt" if is_alt else "primary"
    return rows


def load_latest_snapshots(date_str, lines_dir=LINES_DIR, books=BOOKS):
    """Return dict[(player, stat)][book] -> list of
    {line, over_price, under_price, is_alt_line, market_tier}.

    For each (book, player, stat, line) keep only the latest captured_at.
    R19_L1: `is_alt_line` is propagated into the index so the arb engine can
    filter ladder rungs out of cross-book joins.
    R20_M1: AFTER loading, run `classify_market_tier` per (player, stat, book)
    cluster so FD/Pin/legacy-bov ladders (which lack the CSV column) get
    correctly tagged. This is what fixes the PTS-OVER-3.5 false-arb bug.
    """
    index = {}
    # Track whether each book's CSV actually has the is_alt_line column
    # so we know whether to trust it or re-classify.
    book_has_alt_col = {}
    for book in books:
        path = os.path.join(lines_dir, f"{date_str}_{book}.csv")
        rows = _read_lines_csv(path)
        # Detect if any row has a non-default is_alt_line value (i.e. the
        # writer actually classified). _read_lines_csv defaults to "false"
        # for legacy rows, so we look for ANY "true" as the signal that the
        # column is being populated.
        has_alt_col = any(_is_alt_truthy(r.get("is_alt_line")) for r in rows)
        book_has_alt_col[book] = has_alt_col
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
                    "is_alt_line": _is_alt_truthy(r.get("is_alt_line")),
                }
        for (player, stat, _line), v in latest.items():
            pkey = (player, stat)
            bdict = index.setdefault(pkey, {})
            blist = bdict.setdefault(book, [])
            blist.append({
                "is_alt_line": v.get("is_alt_line", False),
                "line": v["line"],
                "over_price": v["over_price"],
                "under_price": v["under_price"],
            })

    # R20_M1: per-(player,stat,book) cluster — classify market_tier. For
    # books where the writer flagged is_alt_line in-row, trust it. For
    # books that didn't (FD/Pin always, legacy-bov before R19_L1 rewrite),
    # apply the vig-based heuristic.
    for pkey, bdict in index.items():
        for book, rows in bdict.items():
            classify_market_tier(rows, csv_alt_present=book_has_alt_col.get(book, False))
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


def find_middles(index, min_width=0.5, max_juice_each_side=-135,
                  allow_alt_lines=False):
    """Scan the latest-snapshot index for cross-book middles.

    A middle is: book_A OVER X paired with book_B UNDER Y, where Y > X.
    A 0.5-wide middle (e.g. OVER 24.5 / UNDER 25.5) is the most common case.
    The 'gap' (Y - X) is what we hit on if the actual lands in (X, Y).

    Filters:
        - book_A != book_B
        - gap >= min_width (default 0.5)
        - over_price >= max_juice_each_side AND under_price >= max_juice_each_side
          (e.g. -135 means we tolerate down to -135 on each leg)
        - R19_L1: BOTH legs must be primary (is_alt_line=False) unless
          `allow_alt_lines=True`. Bovada's alt-line ladder routinely produces
          rungs with both-positive American odds (e.g. PTS over 3.5 +120 /
          under 25.5 +110 across books) that look like free arbs but are
          actually two independent skewed-juice rungs — pairing them across
          books gives a bogus "guaranteed +EV" signal. Primary-only joins
          eliminate this entire class of false positives.

    Returns a list of dicts sorted by (free_arb desc, width desc).
    """
    middles = []
    for (player, stat), books_dict in index.items():
        overs = []   # (book, line, price)
        unders = []
        for book, rows in books_dict.items():
            for r in rows:
                # R20_M1: primary-only join unless caller explicitly opts in.
                # Tier check is the strict version: market_tier must equal
                # 'primary' (or be missing — back-compat for legacy callers
                # that build rows manually without the tier column). The
                # is_alt_line check remains as a defense-in-depth fallback.
                if not allow_alt_lines:
                    if r.get("is_alt_line"):
                        continue
                    tier = r.get("market_tier")
                    if tier is not None and tier != "primary":
                        continue
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


# ---------------------------------------------------------------------------
# R26_S7 — free-arb critical alert wire (with local dedup fallback).
#
# A true free arb (`free_arb=True` AND surviving the R20_M1 + R24_Q1
# primary-only classifier in `find_middles`) is a guaranteed +EV event
# that may materialize at 2am with no operator awake. We fire a CRITICAL
# alert via R21_N3's `alert()` so it lands in the vault ledger + critical
# stack + Discord (if configured).
#
# Dedup: same arb persisting across many 30s ticks must not spam. The
# canonical key is `free_arb:{player}:{stat}`. R26_S5 is an upstream
# rate-limit/dedup module shipping in parallel — if importable, we delegate
# to it; otherwise we use a process-local TTL dedup so behaviour is
# identical with or without R26_S5 merged. Default TTL: 30 minutes
# (re-fire if the arb is still live half an hour later — a rare and
# operator-worthy event).
# ---------------------------------------------------------------------------
FREE_ARB_DEDUP_TTL_SEC = 30 * 60  # 30 min — re-fire if still live after that


def _free_arb_dedup_key(middle):
    """Canonical dedup key for a free-arb middle. R26_S5 will key on the
    same string when it ships, so a single tag-prefix is the contract."""
    return (f"free_arb:{middle.get('player', '?')}:"
            f"{middle.get('stat', '?')}")


def _free_arb_alert_message(middle):
    """Build the spec-mandated headline for a free-arb middle.

    Format (single line — vault ledger / Discord title compatible):
        FREE ARB: {player} {stat} — {over_book} OVER {over_line}@{over_price}
        / {under_book} UNDER {under_line}@{under_price}
    """
    ev_pct = middle.get("arb_profit_pct")
    ev_str = f"+{ev_pct:.2f}%" if isinstance(ev_pct, (int, float)) else "n/a"
    width = middle.get("middle_width", 0.0)
    try:
        width_str = f"{float(width):.1f}"
    except (TypeError, ValueError):
        width_str = str(width)
    headline = (
        f"FREE ARB: {middle.get('player', '?')} "
        f"{middle.get('stat', '?')} — "
        f"{middle.get('over_book', '?')} OVER "
        f"{middle.get('over_line', '?')}@{middle.get('over_price', '?')} / "
        f"{middle.get('under_book', '?')} UNDER "
        f"{middle.get('under_line', '?')}@{middle.get('under_price', '?')}"
    )
    body = f"Width: {width_str}, EV: {ev_str}"
    return headline, body


def _try_r26_s5_dedup(key, ttl_sec):
    """Try to delegate to R26_S5's dedup if it's merged; return either
    (True, False) — allowed-and-handled, (False, False) — suppressed, or
    (None, True) — module not present, caller must use local fallback.

    Contract assumed for R26_S5 (matches `free_arb:` tag prefix):
        from src.alerts.alert_dedup import should_fire
        should_fire(key: str, ttl_sec: int) -> bool
    Any other shape => fall back to local dedup.
    """
    try:
        from src.alerts import alert_dedup  # type: ignore
    except Exception:
        return (None, True)
    fn = getattr(alert_dedup, "should_fire", None)
    if fn is None or not callable(fn):
        return (None, True)
    try:
        ok = bool(fn(key, ttl_sec))
        return (ok, False)
    except Exception:
        return (None, True)


def _local_dedup_should_fire(key, state, ttl_sec, now=None):
    """Process-local TTL dedup: returns True iff `key` hasn't fired in
    the last `ttl_sec` seconds; updates `state` in place on True.

    `state` is a plain dict {key: last_fired_monotonic_seconds} owned by
    the caller (so loop() can keep its own bucket across ticks)."""
    t = now if now is not None else time.monotonic()
    last = state.get(key)
    if last is not None and (t - last) < ttl_sec:
        return False
    state[key] = t
    return True


def _fire_free_arb_alert(middle, dedup_state, ttl_sec=FREE_ARB_DEDUP_TTL_SEC,
                         alert_fn=None, log=print):
    """Emit a single CRITICAL alert for one free-arb middle, respecting
    dedup. Returns True iff an alert was actually fired (i.e. not deduped
    and no exception). Never raises into the caller.

    `alert_fn` overrides the imported `alert` symbol — used by tests so
    they don't need to monkeypatch the discord_webhook module.
    """
    # Guard: only fire for TRUE free arbs that survived the primary-only
    # classifier. `find_middles(allow_alt_lines=False)` (the default in
    # `run_once`) is what enforces is_real_arb here — we re-assert as
    # defence-in-depth in case a caller wires us up with allow_alt_lines.
    if not middle.get("free_arb"):
        return False
    if middle.get("is_alt_line") or (
        middle.get("market_tier") not in (None, "primary")
    ):
        return False
    op = middle.get("over_price")
    up = middle.get("under_price")
    if not (isinstance(op, int) and isinstance(up, int)
            and op > 0 and up > 0):
        # is_free_arb invariant — both legs must be positive American odds.
        return False

    key = _free_arb_dedup_key(middle)

    # 1) Try R26_S5 (if shipped). 2) Else local TTL dedup.
    ok, used_fallback = _try_r26_s5_dedup(key, ttl_sec)
    if used_fallback:
        if not _local_dedup_should_fire(key, dedup_state, ttl_sec):
            return False
    else:
        if not ok:
            return False

    headline, body = _free_arb_alert_message(middle)
    metadata = {
        "player": middle.get("player"),
        "stat": middle.get("stat"),
        "over_book": middle.get("over_book"),
        "over_line": middle.get("over_line"),
        "over_price": middle.get("over_price"),
        "under_book": middle.get("under_book"),
        "under_line": middle.get("under_line"),
        "under_price": middle.get("under_price"),
        "middle_width": middle.get("middle_width"),
        "arb_profit_pct": middle.get("arb_profit_pct"),
        "dedup_key": key,
    }
    # `alert()` doesn't take a freeform `metadata=` kwarg; encode the
    # structured payload as Discord embed fields + a metadata JSON line
    # in the body so operators and downstream parsers both get it.
    fields = [{"name": k, "value": str(v)} for k, v in metadata.items()
              if v is not None]
    full_body = f"{body}\n\nmetadata: {json.dumps(metadata, default=str)}"

    fn = alert_fn
    if fn is None:
        try:
            from src.alerts.discord_webhook import alert as _alert
            fn = _alert
        except Exception as exc:
            log(f"[warn] alert import failed: {exc}; skipping free-arb fire.")
            return False
    try:
        fn(headline, level="critical", tag="free_arb",
           source="middle_finder_daemon", body=full_body, fields=fields)
        return True
    except Exception as exc:
        log(f"[warn] free-arb alert fire failed: {exc}")
        return False


def loop(interval_sec, min_width, max_juice, max_iters=None,
          use_model=True, min_band_prob=0.10, out_json=OUT_JSON, log=print,
          dedup_ttl_sec=FREE_ARB_DEDUP_TTL_SEC, alert_fn=None,
          dedup_state=None):
    predictor = None
    if use_model and _MODEL_OK:
        try:
            predictor = _RealModelPredictor()
        except Exception as exc:
            log(f"[warn] model init failed: {exc}; continuing without model.")
            predictor = None
    # R26_S7 — local-fallback dedup bucket (used when R26_S5 isn't merged).
    if dedup_state is None:
        dedup_state = {}
    stats = {"ticks": 0, "total_middles": 0, "max_middles_in_tick": 0,
              "free_arbs_total": 0, "model_confirmed_total": 0,
              "free_arb_alerts_fired": 0}
    signal.signal(signal.SIGTERM, _on_signal)
    try:
        signal.signal(signal.SIGINT, _on_signal)
    except Exception:
        pass
    while not _STOP:
        # R19_L3 heartbeat
        _r19_hb('middle_finder_daemon')
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
        # R26_S7 — critical alert wire for free arbs (with R26_S5 dedup
        # fallback). The vault append + critical-stack push happen inside
        # `alert()` so a 2am free arb leaves a durable trail even with no
        # Discord URL configured.
        try:
            for m in (mm for mm in middles if mm.get("free_arb")):
                if _fire_free_arb_alert(m, dedup_state,
                                         ttl_sec=dedup_ttl_sec,
                                         alert_fn=alert_fn, log=log):
                    stats["free_arb_alerts_fired"] += 1
        except Exception as exc:
            log(f"[warn] free-arb alert loop failed: {exc}")
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
