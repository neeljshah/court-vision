"""live_bet_ranker.py — real-time bet ranker daemon (R16 E2).

Polls the latest book snapshots every --interval-sec, runs the prop_pergame
model on tonight's slate (cached after first tick), prices every (player,
stat, book, side) tuple, ranks by EV, sizes with 0.25-fractional Kelly,
detects line moves between ticks, flags stale snapshots, and stops at
game tip-off (detected via quarter_box q1 file arrival).

Outputs (atomic temp+rename so safe to read mid-write):
    data/cache/live_bets/<isodate>_<slate>.json
    vault/Predictions/<date>_<slate>_live.md
    vault/Improvements/live_bet_ranker.log (append, single line per tick)

State:
    data/cache/live_bets/<slate>_state.json   — last_lines, model preds cache
    data/cache/live_bets/placed_bets.json     — cooldown tracker

Run:
    python scripts/live_bet_ranker.py \\
        --slate sas_okc_2026-05-26 \\
        --interval-sec 30 \\
        --bankroll 1000
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from math import erf, sqrt
from typing import Any

import pandas as pd

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


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# --------- constants / config ----------
DEFAULT_BANKROLL = 1000.0
DEFAULT_INTERVAL = 30
KELLY_FRACTION = 0.25
PER_BET_CAP = 0.05
SLATE_CAP = 0.25
MIN_EDGE_PCT = 0.5
MAX_ODDS_ABS = 400
MIN_PRICE_PROB = 0.20
STALE_THRESHOLD_SEC = 300  # 5 min
LINE_MOVE_PT = 0.5         # line moved >=0.5pt => arrow
ODDS_MOVE_PCT = 0.10       # odds moved >=10% => arrow
EDGE_COLLAPSE_DROP = 3.0   # edge dropped >=3pp from prior tick => alert
SEASON = "2024-25"

# Slate registry — extend as new games are tracked
SLATES: dict[str, dict[str, Any]] = {
    "sas_okc_2026-05-26": {
        "date": "2026-05-26",
        "label": "SAS @ OKC Game 7 WCF",
        "game_ids": ["25830906", "1631142204", "35639109"],  # bov/pin/fd
        # NBA Stats game_id(s) used by the tip detector + quarter_box
        # scanner. Playoffs use the 004... prefix.
        "nba_game_ids": ["0042400317"],
        "sas_players": [
            "Victor Wembanyama", "De'Aaron Fox", "Devin Vassell",
            "Stephon Castle", "Keldon Johnson", "Dylan Harper",
            "Julian Champagnie", "Jared McCain",
        ],
        "okc_players": [
            "Shai Gilgeous-Alexander", "Jalen Williams", "Chet Holmgren",
            "Luguentz Dort", "Cason Wallace", "Alex Caruso",
            "Isaiah Hartenstein", "Jaylin Williams", "Luke Kornet",
        ],
        "sas_home": False,
        "okc_home": True,
        "sas_opp": "OKC",
        "okc_opp": "SAS",
    },
}


# --------- odds math (mirrors probe_R15) ----------
def american_to_decimal(odds):
    if odds is None or pd.isna(odds):
        return None
    o = int(float(odds))
    return 1 + (o / 100.0) if o > 0 else 1 + (100.0 / -o)


def american_payout(odds, stake=1.0):
    o = int(float(odds))
    return stake * (o / 100.0) if o > 0 else stake * (100.0 / -o)


def implied_prob(odds):
    o = int(float(odds))
    return 100.0 / (o + 100) if o > 0 else (-o) / ((-o) + 100)


def kelly_fraction(prob, odds):
    if prob is None or odds is None or pd.isna(odds):
        return 0.0
    b = american_payout(odds, 1.0)
    p = prob
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


# --------- atomic write ----------
def atomic_write_json(path: str, payload: dict) -> None:
    """Write JSON via temp file + rename so readers never see a partial write."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".tmp_", suffix=".json",
        dir=os.path.dirname(path) or ".",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        # On POSIX os.replace is atomic; on Windows it overwrites atomically too.
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def atomic_write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".tmp_", suffix=".md",
        dir=os.path.dirname(path) or ".",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


# --------- line CSV reader (handles Bovada 10/11/12-col schema drift) ------
# R19_L1: 12-col schema adds `is_alt_line` (true/false). Older rows default
# to is_alt_line=False (primary), keeping legacy ranking behavior unchanged.
def _read_lines_csv(path: str) -> pd.DataFrame:
    import csv as _csv
    canon = ["captured_at", "book", "game_id", "player_id",
             "player_name", "stat", "line", "over_price",
             "under_price", "start_time", "is_alt_line"]
    rows = []
    if not os.path.exists(path):
        return pd.DataFrame(columns=canon)
    with open(path, encoding="utf-8") as f:
        reader = _csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return pd.DataFrame(columns=canon)
        try:
            alt_idx = header.index("is_alt_line")
        except ValueError:
            alt_idx = None
        for row in reader:
            if len(row) == 10:
                d = dict(zip(canon[:-1], row))
                d["is_alt_line"] = "false"
            elif len(row) == 11:
                d = {
                    "captured_at": row[0], "book": row[1],
                    "game_id": row[2], "player_id": row[3],
                    "player_name": row[4],
                    "stat": row[6], "line": row[7],
                    "over_price": row[8], "under_price": row[9],
                    "start_time": row[10],
                    "is_alt_line": "false",
                }
            elif len(row) == 12:
                d = {
                    "captured_at": row[0], "book": row[1],
                    "game_id": row[2], "player_id": row[3],
                    "player_name": row[4],
                    "stat": row[6], "line": row[7],
                    "over_price": row[8], "under_price": row[9],
                    "start_time": row[10],
                    "is_alt_line": (row[alt_idx] if alt_idx is not None
                                     and alt_idx < len(row) else row[11]),
                }
            else:
                continue
            rows.append(d)
    df = pd.DataFrame(rows, columns=canon)
    if df.empty:
        return df
    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce", utc=True)
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    df["over_price"] = pd.to_numeric(df["over_price"], errors="coerce")
    df["under_price"] = pd.to_numeric(df["under_price"], errors="coerce")
    df["is_alt_line"] = df["is_alt_line"].astype(str).str.strip().str.lower().isin(
        ["true", "1", "yes", "y", "t"]
    )
    return df


def load_books_for_date(date_str: str) -> tuple[dict[str, pd.DataFrame], dict[str, datetime]]:
    """Return (book -> latest-snapshot DataFrame, book -> most-recent captured_at)."""
    out, latest = {}, {}
    for book in ("fd", "bov", "pin"):
        path = os.path.join(PROJECT_DIR, "data", "lines",
                            f"{date_str}_{book}.csv")
        df = _read_lines_csv(path)
        if df.empty:
            continue
        df = df.dropna(subset=["captured_at"])
        if df.empty:
            continue
        # latest snapshot per (player_name, stat, line) — same logic as probe_R15
        df = df.sort_values("captured_at").drop_duplicates(
            subset=["player_name", "stat", "line"], keep="last"
        )
        out[book] = df
        latest[book] = df["captured_at"].max().to_pydatetime()
    return out, latest


# --------- model wrapper (lazy import + cache) ----------
class ModelCache:
    """Caches predictions per player. Predictions only change when injury
    status changes — we re-check availability every N ticks via the
    injury_availability module (which itself caches API calls)."""

    def __init__(self, slate_cfg: dict, gamelog_dir: str, model_dir: str):
        self.cfg = slate_cfg
        self.gamelog_dir = gamelog_dir
        self.model_dir = model_dir
        self.preds: dict[str, dict] = {}
        self.last_factor: dict[str, float] = {}
        self._loaded = False
        # lazy imports to keep test surface light
        self._build_pred = None
        self._predict_point = None
        self._predict_q = None
        self._apply_cal = None
        self._get_avail = None
        self._resolve_pid = None
        self._STATS = None

    def _lazy_import(self):
        if self._loaded:
            return
        from src.prediction.prop_pergame import (
            STATS, build_prediction_row, predict_pergame,
        )
        from src.prediction.prop_quantiles import (
            predict_pergame_quantiles,
        )
        from src.prediction.quantile_calibration import (
            apply as apply_quantile_calibration,
        )
        from src.prediction.injury_availability import (
            get_availability_factor,
        )
        self._STATS = STATS
        self._build_pred = build_prediction_row
        self._predict_point = predict_pergame
        self._predict_q = predict_pergame_quantiles
        self._apply_cal = apply_quantile_calibration
        self._get_avail = get_availability_factor
        self._loaded = True

    def _resolve(self, name: str) -> int | None:
        try:
            from nba_api.stats.static import players
        except Exception:
            return None
        import unicodedata
        def _strip(s):
            n = unicodedata.normalize("NFKD", str(s))
            return "".join(c for c in n if not unicodedata.combining(c)).lower()
        needle = _strip(name)
        cands = players.get_players()
        for p in cands:
            if _strip(p["full_name"]) == needle:
                return int(p["id"])
        for p in cands:
            if needle in _strip(p["full_name"]):
                return int(p["id"])
        return None

    def predict_player(self, name: str, opp: str, is_home: bool,
                         force_refresh_injury: bool = False) -> dict | None:
        self._lazy_import()
        if (not force_refresh_injury) and name in self.preds:
            return self.preds[name]
        pid = self._resolve(name)
        if pid is None:
            return None
        prow = self._build_pred(pid, opp, SEASON, is_home=is_home,
                                 rest_days=2.0, gamelog_dir=self.gamelog_dir)
        if prow is None:
            return None
        try:
            factor = self._get_avail(player_id=pid, player_name=name)
        except Exception:
            factor = 1.0
        if force_refresh_injury and name in self.preds \
                and self.last_factor.get(name) == factor:
            return self.preds[name]
        out = {}
        for s in self._STATS:
            try:
                point = self._predict_point(s, prow, self.model_dir)
                qint = self._predict_q(s, prow, self.model_dir)
                if point is None or qint is None:
                    continue
                if factor == 0.0:
                    out[s] = {"point": 0.0, "q10": 0.0, "q50": 0.0,
                              "q90": 0.0, "availability_factor": 0.0}
                    continue
                point_adj = float(point) * factor
                qadj = {k: (float(v) * factor) if isinstance(v, (int, float))
                        else v for k, v in qint.items()}
                out[s] = {
                    "point": point_adj,
                    "q10": qadj.get("q10"),
                    "q50": qadj.get("q50"),
                    "q90": qadj.get("q90"),
                    "availability_factor": factor,
                }
            except Exception:
                continue
        if not out:
            return None
        self.preds[name] = out
        self.last_factor[name] = factor
        return out


# iter-28 risk-reducing fix: counting stats that need a sigma floor.
# BLK / STL / FG3M have low base rates and skew-toward-zero quantile heads
# that can produce collapsed sigma -> fake high edges (see Wemby BLK U 2.5
# case, q10=0 q50=2.04 q90=1.14 -> sigma=0.445, edge=+51%).
_COUNTING_STAT_SIGMA_FLOOR = {"blk", "stl", "fg3m"}

# iter-28 risk-reducing fix: edge cap. Anything above this absolute pp
# diverts to a review tray rather than firing as a live bet.
EDGE_CAP_PP = 25.0
EDGE_REVIEW_TRAY_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "pretip_review_tray.jsonl"
)


def _log_to_review_tray(record: dict) -> None:
    """Append one JSON line to the pretip review tray. Best-effort: any IO
    error here must NEVER bubble up to the ranker hot loop."""
    try:
        os.makedirs(os.path.dirname(EDGE_REVIEW_TRAY_PATH), exist_ok=True)
        with open(EDGE_REVIEW_TRAY_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


def model_hit_prob(point_pred, q10, q50, q90, line, side,
                     stat=None, calibrator=None):
    if q10 is None or q90 is None or point_pred is None:
        return None
    if calibrator is not None and stat is not None:
        cal_q10, cal_q90 = calibrator(stat, q10, q50 or point_pred, q90)
    else:
        cal_q10, cal_q90 = q10, q90
    # iter-28 risk-reducing fix: quantile sanity guard. If the trained
    # quantile heads return an inverted interval (commonly q90 < q50 on
    # floor-bound counting stats), widen q90 to a conservative honest
    # range. This preserves the q50 point prediction but blows up sigma
    # so we don't price a fake-tight interval. If widening can't restore
    # ordering, return None so the caller skips this bet entirely.
    q50_eff = q50 if q50 is not None else point_pred
    inverted = False
    if not (cal_q10 <= q50_eff <= cal_q90):
        inverted = True
        if cal_q10 <= q50_eff:
            # only the upper tail is broken; widen using the larger of
            # the existing upper span, the lower span (mirrored), or 1.0.
            widened_upper = q50_eff + max(
                cal_q90 - q50_eff, q50_eff - cal_q10, 1.0
            )
            cal_q90 = widened_upper
        else:
            # lower tail also inverted - bail out, the model is unusable here
            return None
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    # iter-28 risk-reducing fix: sigma floor for low-base-rate counting
    # stats (BLK / STL / FG3M). Even non-inverted quantile bands from
    # these heads can be unrealistically tight against an integer prop
    # line, so enforce a per-stat minimum spread.
    if stat is not None and str(stat).lower() in _COUNTING_STAT_SIGMA_FLOOR:
        floor_sigma = max(0.4 * float(q50_eff or 0), 0.5)
        sigma = max(sigma, floor_sigma)
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf_at_line
    prob = p_over if side == "OVER" else 1 - p_over
    # Stash the inversion flag + post-fix sigma on a function attribute so
    # the caller can log to the review tray if edge ends up capped. We
    # avoid changing the return signature to keep ranking math untouched.
    model_hit_prob._last_meta = {
        "inverted_quantiles": inverted,
        "sigma_used": sigma,
        "q50_used": q50_eff,
        "q10_in": q10,
        "q90_in": q90,
    }
    return prob


# Initialize the metadata cache so callers can read it safely.
model_hit_prob._last_meta = {}


# --------- pre-tip / cooldown / state ----------
try:
    from scripts import game_tip_detector as _tip_det
except Exception:  # pragma: no cover - circular safety net
    _tip_det = None


def is_pretip(slate_cfg: dict) -> bool:
    """Return True iff the slate is still pre-tip.

    Fuses two signals:
      1. Quarter_box file presence — any ``<game_id>_q1.json`` in
         ``<PROJECT_DIR>/data/cache/quarter_box/`` means the game has
         tipped. (Local to this module so tests can monkey-patch
         ``PROJECT_DIR``.)
      2. ``game_tip_detector.is_pregame`` — scheduled tip-time +
         5-minute grace window. Triggers when the q1 file is delayed
         but the wall-clock confirms tip-off occurred.
    """
    qbox = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
    nba_ids = slate_cfg.get("nba_game_ids") or slate_cfg.get("game_ids", [])
    # Signal 1: quarter_box presence.
    if os.path.isdir(qbox):
        for gid in nba_ids:
            for fn in os.listdir(qbox):
                if gid in fn and fn.endswith("_q1.json"):
                    return False
    # Signal 2: tip-time + grace (only if a real NBA game_id is wired).
    if _tip_det is not None and slate_cfg.get("nba_game_ids"):
        for gid in slate_cfg["nba_game_ids"]:
            if not _tip_det.is_pregame(
                gid, game_date=slate_cfg.get("date")
            ):
                return False
    return True


def in_play_handoff_payload(slate_cfg: dict) -> dict:
    """Lightweight stub: when a slate transitions to in-play, return
    the metadata an in-play ranker would need — current quarter and a
    pointer to the end-of-quarter WP models (R10_M5 + R12_F1).

    Full in-play bet generation is future work (R17_J6+). This stub
    exists so the daemon can write a clean transition log line and
    downstream consumers know which model to query next.
    """
    nba_ids = slate_cfg.get("nba_game_ids") or slate_cfg.get("game_ids", [])
    current_q = None
    if _tip_det is not None:
        for gid in nba_ids:
            q = _tip_det.in_play_quarter(gid)
            if q is not None:
                current_q = q
                break
    next_target = {
        "q1": "endQ1_winprob",
        "q2": "endQ2_winprob",
        "q3": "endQ3_winprob",
        "q4": "final_winprob",
    }.get(current_q or "q1", "endQ1_winprob")
    return {
        "phase": "IN_PLAY",
        "current_quarter": current_q,
        "next_prediction_target": next_target,
        "wp_model_paths": [
            "data/models/winprob_endQ1.pkl",  # R10_M5
            "data/models/winprob_endQ2.pkl",
            "data/models/winprob_endQ3.pkl",
            "data/models/winprob_final.pkl",  # R12_F1
        ],
        "nba_game_ids": nba_ids,
    }


def load_state(state_path: str) -> dict:
    if not os.path.exists(state_path):
        return {"prior_lines": {}, "prior_edges": {}}
    try:
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"prior_lines": {}, "prior_edges": {}}


def load_placed(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("placed_keys", []))
    except Exception:
        return set()


def bet_key(b: dict) -> str:
    return f"{b['player']}|{b['stat']}|{b['side']}|{b['book']}|{b['line']}"


# --------- core tick ----------
def run_tick(slate_id: str, bankroll: float, cache: ModelCache,
              prior_state: dict, placed: set[str],
              tick_idx: int) -> dict:
    """Execute one ranking pass. Returns the payload dict (which is also
    persisted atomically by the caller)."""
    cfg = SLATES[slate_id]
    date_str = cfg["date"]
    tick_t0 = time.time()

    pretip = is_pretip(cfg)

    books, latest = load_books_for_date(date_str)
    now = datetime.now(timezone.utc)
    stale_books = {
        b: ((now - t).total_seconds() > STALE_THRESHOLD_SEC)
        for b, t in latest.items()
    }

    # Roster -> predictions (cached after first tick)
    roster = [(p, "SAS", cfg["sas_opp"], cfg["sas_home"])
              for p in cfg["sas_players"]] + \
             [(p, "OKC", cfg["okc_opp"], cfg["okc_home"])
              for p in cfg["okc_players"]]
    # Refresh injury status every ~10 ticks (5 min @ 30s)
    force_refresh = (tick_idx > 0) and (tick_idx % 10 == 0)
    for name, _team, opp, is_home in roster:
        try:
            cache.predict_player(name, opp, is_home,
                                  force_refresh_injury=force_refresh)
        except Exception:
            continue
    preds = cache.preds

    # Build per-player/stat/book line snapshot
    line_idx: dict = {}
    for book, df in books.items():
        for _, r in df.iterrows():
            pname = r["player_name"]
            stat = r["stat"]
            line_idx.setdefault(pname, {}).setdefault(stat, {}) \
                .setdefault(book, []).append({
                    "line": r["line"],
                    "over_price": r.get("over_price"),
                    "under_price": r.get("under_price"),
                    "captured_at": r["captured_at"],
                })

    prior_lines = prior_state.get("prior_lines", {})
    prior_edges = prior_state.get("prior_edges", {})

    bets = []
    n_evaluated = 0
    line_moves = []
    edge_collapses = []

    for pname, stats_dict in line_idx.items():
        pdata = preds.get(pname)
        if pdata is None:
            continue
        for stat, book_dict in stats_dict.items():
            mdl = pdata.get(stat)
            if mdl is None or mdl.get("availability_factor", 1.0) == 0.0:
                continue
            point = mdl["point"]
            q10 = mdl["q10"]
            q50 = mdl["q50"]
            q90 = mdl["q90"]
            for book, rows in book_dict.items():
                for r in rows:
                    line = float(r["line"])
                    for side, price_col in (("OVER", "over_price"),
                                              ("UNDER", "under_price")):
                        price = r.get(price_col)
                        if price is None or pd.isna(price):
                            continue
                        odds = int(float(price))
                        if abs(odds) > MAX_ODDS_ABS:
                            continue
                        impl = implied_prob(odds)
                        if impl < MIN_PRICE_PROB:
                            continue
                        prob = model_hit_prob(
                            point, q10, q50, q90, line, side,
                            stat=stat, calibrator=cache._apply_cal,
                        )
                        if prob is None:
                            continue
                        n_evaluated += 1
                        net = american_payout(odds, 1.0)
                        ev = prob * net - (1 - prob) * 1.0
                        kf_full = kelly_fraction(prob, odds)
                        kf_used = min(kf_full * KELLY_FRACTION, PER_BET_CAP)
                        stake = round(kf_used * bankroll, 2)
                        # line-move detection
                        key = f"{pname}|{stat}|{book}|{side}"
                        prev = prior_lines.get(key)
                        arrow = ""
                        if prev:
                            try:
                                dl = line - float(prev["line"])
                                dop = (odds - int(prev["odds"])) / max(
                                    abs(int(prev["odds"])), 1
                                )
                                if abs(dl) >= LINE_MOVE_PT:
                                    arrow = "↑LINE" if dl > 0 else "↓LINE"
                                elif abs(dop) >= ODDS_MOVE_PCT:
                                    arrow = "↑ODDS" if dop > 0 else "↓ODDS"
                                if arrow:
                                    line_moves.append({
                                        "key": key,
                                        "from_line": float(prev["line"]),
                                        "to_line": line,
                                        "from_odds": int(prev["odds"]),
                                        "to_odds": odds,
                                        "arrow": arrow,
                                    })
                            except Exception:
                                pass
                        edge_pct = (prob - impl) * 100
                        # iter-28 risk-reducing fix: edge cap. Anything
                        # whose absolute edge exceeds EDGE_CAP_PP routes
                        # to the pretip review tray and is skipped from
                        # the ranked output. The kelly / EV math itself
                        # is untouched - we just decline to fire the bet.
                        if abs(edge_pct) > EDGE_CAP_PP:
                            meta = getattr(model_hit_prob, "_last_meta", {}) or {}
                            _log_to_review_tray({
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "player": pname,
                                "stat": stat,
                                "side": side,
                                "book": book,
                                "line": line,
                                "odds": odds,
                                "implied_prob": impl,
                                "model_prob": prob,
                                "edge_pct_raw": edge_pct,
                                "edge_cap_pp": EDGE_CAP_PP,
                                "q10": q10,
                                "q50": q50,
                                "q90": q90,
                                "inverted_quantiles": meta.get(
                                    "inverted_quantiles"
                                ),
                                "sigma_used": meta.get("sigma_used"),
                                "reason": "edge_cap_exceeded",
                            })
                            continue
                        prev_edge = prior_edges.get(bet_key({
                            "player": pname, "stat": stat,
                            "side": side, "book": book, "line": line,
                        }))
                        if (prev_edge is not None
                                and prev_edge >= MIN_EDGE_PCT
                                and edge_pct <= prev_edge - EDGE_COLLAPSE_DROP):
                            edge_collapses.append({
                                "player": pname, "stat": stat,
                                "side": side, "book": book,
                                "from_edge_pct": round(prev_edge, 2),
                                "to_edge_pct": round(edge_pct, 2),
                            })
                        b = {
                            "player": pname,
                            "stat": stat,
                            "side": side,
                            "book": book,
                            "line": line,
                            "model_q50": round(point, 2),
                            "model_q10": round(q10, 2) if q10 is not None else None,
                            "model_q90": round(q90, 2) if q90 is not None else None,
                            "odds": odds,
                            "implied_prob": round(impl, 4),
                            "model_prob": round(prob, 4),
                            "edge_pct": round(edge_pct, 2),
                            "ev_per_dollar": round(ev, 4),
                            "kelly_pct_used": round(kf_used * 100, 2),
                            "kelly_stake_$": stake,
                            "line_move": arrow,
                            "stale": stale_books.get(book, False),
                        }
                        bets.append(b)

    # Sort and apply slate cap
    bets.sort(key=lambda x: x["ev_per_dollar"], reverse=True)
    pos = [b for b in bets if b["edge_pct"] >= MIN_EDGE_PCT]
    # Filter placed-bet cooldown
    pos = [b for b in pos if bet_key(b) not in placed]
    cap_dollars = SLATE_CAP * bankroll
    capped, total = [], 0.0
    for b in pos:
        if total + b["kelly_stake_$"] <= cap_dollars:
            capped.append(b)
            total += b["kelly_stake_$"]
        else:
            remaining = max(0.0, cap_dollars - total)
            if remaining >= 5.0:
                b2 = dict(b)
                b2["kelly_stake_$"] = round(remaining, 2)
                capped.append(b2)
                total += remaining
            break

    # Build new prior_lines / prior_edges (for next tick)
    new_prior_lines = {}
    new_prior_edges = {}
    for b in bets:
        new_prior_lines[f"{b['player']}|{b['stat']}|{b['book']}|{b['side']}"] = {
            "line": b["line"], "odds": b["odds"],
        }
        new_prior_edges[bet_key(b)] = b["edge_pct"]

    top = capped[0] if capped else None
    payload = {
        "slate_id": slate_id,
        "label": cfg["label"],
        "captured_at": now.isoformat(),
        "tick_idx": tick_idx,
        "tick_latency_ms": int((time.time() - tick_t0) * 1000),
        "pretip": pretip,
        "bankroll": bankroll,
        "books_used": list(books.keys()),
        "stale_books": [b for b, s in stale_books.items() if s],
        "n_props_evaluated": n_evaluated,
        "n_positive_ev": len(pos),
        "top_edge_pct": top["edge_pct"] if top else None,
        "top_bet_str": (
            f"{top['player']} {top['stat'].upper()} {top['side']} "
            f"{top['line']:.1f} @ {top['book']} {top['odds']:+d}"
            if top else None
        ),
        "total_recommended_exposure_$": round(total, 2),
        "ranked_bets": capped,
        "line_moves_this_tick": line_moves,
        "edge_collapses_this_tick": edge_collapses,
        "n_placed_cooldown": len(placed),
        "new_state": {
            "prior_lines": new_prior_lines,
            "prior_edges": new_prior_edges,
        },
    }
    return payload


def render_md(payload: dict, slate_cfg: dict) -> str:
    lines = []
    lines.append(f"# {slate_cfg['label']} — LIVE Bet Ranker\n")
    lines.append(f"_Updated: {payload['captured_at']}_  ")
    lines.append(f"_Tick: {payload['tick_idx']} "
                 f"({payload['tick_latency_ms']} ms)_  ")
    if payload["pretip"]:
        lines.append("**Status:** PREGAME (pre-tip, surfacing pregame bets)  \n")
    else:
        lines.append("**Status:** GAME LIVE — pregame bets suppressed  \n")
    if payload["stale_books"]:
        lines.append(f"**STALE books (>5min old):** "
                     f"{', '.join(payload['stale_books'])}  \n")
    lines.append(f"**Props evaluated:** {payload['n_props_evaluated']}  ")
    lines.append(f"**Positive-EV:** {payload['n_positive_ev']}  ")
    lines.append(f"**Total recommended exposure:** "
                 f"${payload['total_recommended_exposure_$']:.2f}  ")
    if payload["line_moves_this_tick"]:
        lines.append(f"**Line moves this tick:** "
                     f"{len(payload['line_moves_this_tick'])}  ")
    if payload["edge_collapses_this_tick"]:
        lines.append(f"**Edge collapses:** "
                     f"{len(payload['edge_collapses_this_tick'])}  ")
    lines.append("\n## Top Ranked Bets\n")
    lines.append(
        "| # | Player | Stat | Side | Book | Line | q50 | Edge % | "
        "Stake $ | Move | Stale |"
    )
    lines.append("|--|--|--|--|--|--|--|--|--|--|--|")
    for i, b in enumerate(payload["ranked_bets"][:20], 1):
        lines.append(
            f"| {i} | {b['player']} | {b['stat'].upper()} | {b['side']} | "
            f"{b['book']} | {b['line']:.1f} | {b['model_q50']:.2f} | "
            f"{b['edge_pct']:+.2f}% | ${b['kelly_stake_$']:.2f} | "
            f"{b['line_move'] or '—'} | "
            f"{'STALE' if b['stale'] else '—'} |"
        )
    if payload["edge_collapses_this_tick"]:
        lines.append("\n## Edge Collapses (heads-up)\n")
        for ec in payload["edge_collapses_this_tick"][:10]:
            lines.append(
                f"- {ec['player']} {ec['stat'].upper()} {ec['side']} "
                f"@ {ec['book']}: {ec['from_edge_pct']:+.2f}% → "
                f"{ec['to_edge_pct']:+.2f}%"
            )
    return "\n".join(lines)


def run_daemon(slate_id: str, interval: int, bankroll: float,
                max_ticks: int | None = None,
                stop_at_tip: bool = True,
                log_path: str | None = None) -> dict:
    cfg = SLATES[slate_id]
    out_json = os.path.join(PROJECT_DIR, "data", "cache", "live_bets",
                              f"{cfg['date']}_{slate_id}.json")
    out_md = os.path.join(PROJECT_DIR, "vault", "Predictions",
                            f"{cfg['date']}_{slate_id}_live.md")
    state_path = os.path.join(PROJECT_DIR, "data", "cache", "live_bets",
                                f"{slate_id}_state.json")
    placed_path = os.path.join(PROJECT_DIR, "data", "cache", "live_bets",
                                 "placed_bets.json")
    if log_path is None:
        log_path = os.path.join(PROJECT_DIR, "vault", "Improvements",
                                  "live_bet_ranker.log")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger(f"live_bet_ranker.{slate_id}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(sh)

    cache = ModelCache(
        cfg,
        gamelog_dir=os.path.join(PROJECT_DIR, "data", "nba"),
        model_dir=os.path.join(PROJECT_DIR, "data", "models"),
    )
    state = load_state(state_path)
    placed = load_placed(placed_path)

    tick_idx = 0
    summary = {
        "ticks_observed": 0,
        "n_positive_ev_per_tick": [],
        "line_moves_detected": 0,
        "tick_latency_ms": [],
    }
    pid = os.getpid()
    logger.info(f"START pid={pid} slate={slate_id} interval={interval}s "
                f"bankroll=${bankroll}")
    try:
        while True:
            # R19_L3 heartbeat
            _r19_hb('live_bet_ranker')
            t_start = time.time()
            try:
                payload = run_tick(slate_id, bankroll, cache, state,
                                     placed, tick_idx)
            except Exception as exc:
                logger.exception(f"tick {tick_idx} ERROR: {exc}")
                tick_idx += 1
                if max_ticks is not None and tick_idx >= max_ticks:
                    break
                time.sleep(max(0, interval - (time.time() - t_start)))
                continue

            # Pre-tip cutoff: if game has started, stop pregame surfacing
            if stop_at_tip and not payload["pretip"]:
                # Suppress pregame bets — emit empty ranked_bets + flag
                payload["ranked_bets"] = []
                payload["n_positive_ev"] = 0
                payload["top_bet_str"] = None
                payload["top_edge_pct"] = None
                payload["status"] = "tipoff_reached_pregame_suppressed"

            # Atomic write
            atomic_write_json(out_json, payload)
            atomic_write_text(out_md, render_md(payload, cfg))

            # Persist state for next tick
            state = payload.pop("new_state")
            atomic_write_json(state_path, state)

            # Log line per tick (concise)
            top_str = payload.get("top_bet_str") or "—"
            logger.info(
                f"tick={tick_idx} n_props={payload['n_props_evaluated']} "
                f"pos_ev={payload['n_positive_ev']} "
                f"top_edge={payload['top_edge_pct']} "
                f"top={top_str} "
                f"moves={len(payload['line_moves_this_tick'])} "
                f"latency_ms={payload['tick_latency_ms']}"
            )

            summary["ticks_observed"] += 1
            summary["n_positive_ev_per_tick"].append(payload["n_positive_ev"])
            summary["line_moves_detected"] += len(payload["line_moves_this_tick"])
            summary["tick_latency_ms"].append(payload["tick_latency_ms"])

            # Stop after tip if requested
            if stop_at_tip and not payload["pretip"]:
                # Emit a structured transition log entry so downstream
                # consumers (vault, dashboards) can pivot to the in-play
                # ranker output.
                handoff = in_play_handoff_payload(SLATES[slate_id])
                logger.info(
                    "TIPOFF detected — handoff to IN_PLAY mode: "
                    f"current_q={handoff['current_quarter']} "
                    f"next_target={handoff['next_prediction_target']}"
                )
                transition_path = os.path.join(
                    PROJECT_DIR, "data", "cache", "live_bets",
                    f"{slate_id}_handoff.json",
                )
                atomic_write_json(transition_path, {
                    "slate": slate_id,
                    "transitioned_at": datetime.now(timezone.utc).isoformat(),
                    **handoff,
                })
                logger.info(
                    "TIPOFF reached — daemon exiting (pregame stops)."
                )
                break

            tick_idx += 1
            if max_ticks is not None and tick_idx >= max_ticks:
                break

            # Sleep to the next tick boundary
            elapsed = time.time() - t_start
            time.sleep(max(0, interval - elapsed))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — daemon exiting cleanly.")
    finally:
        logger.info(f"STOP pid={pid} ticks={summary['ticks_observed']}")
        for h in list(logger.handlers):
            try:
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)
    summary["daemon_pid"] = pid
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slate", required=True,
                     help="slate id (e.g. sas_okc_2026-05-26)")
    ap.add_argument("--interval-sec", type=int, default=DEFAULT_INTERVAL)
    ap.add_argument("--bankroll", type=float, default=DEFAULT_BANKROLL)
    ap.add_argument("--max-ticks", type=int, default=None,
                     help="run for N ticks then exit (default: forever)")
    ap.add_argument("--no-stop-at-tip", action="store_true")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    if args.slate not in SLATES:
        raise SystemExit(f"unknown slate '{args.slate}'. "
                          f"known: {list(SLATES.keys())}")
    summary = run_daemon(
        slate_id=args.slate,
        interval=args.interval_sec,
        bankroll=args.bankroll,
        max_ticks=args.max_ticks,
        stop_at_tip=(not args.no_stop_at_tip),
        log_path=args.log,
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
