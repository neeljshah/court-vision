"""Read and score the local inputs for the closing-decay showcase."""
from __future__ import annotations

import glob
import json
import math
import os
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LH_DIR = os.path.join(REPO_ROOT, "data", "cache", "line_history")
MAX_HORIZON_H = 72.0
MIN_N_POWERED = 20

# sport -> (outcome parquet, mode). mode 'home_win' reads that column;
# 'scores' derives home_win from home_score>away_score (completed rows only).
JOINABLE: Dict[str, Tuple[str, str]] = {
    "wnba": (os.path.join(REPO_ROOT, "data", "domains", "wnba", "espn_scoreboard.parquet"), "home_win"),
    "soccer_intl": (os.path.join(REPO_ROOT, "data", "domains", "soccer_intl", "espn_finals.parquet"), "scores"),
}


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_home_snapshots(sport: str) -> Tuple[Dict[str, List[Tuple[float, float]]], Optional[str], Dict[str, Any]]:
    """Load valid pregame home-side moneyline snapshots for one sport."""
    by_game: Dict[str, List[Tuple[float, float]]] = {}
    max_cap: Optional[datetime] = None
    min_cap: Optional[datetime] = None
    n_files = 0
    for path in glob.glob(os.path.join(LH_DIR, sport, "*.jsonl")):
        n_files += 1
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("market_type") != "moneyline" or d.get("side") != "home":
                    continue
                p = d.get("devigged_prob")
                gid = d.get("game_id")
                if p is None or gid in (None, "", "0"):
                    continue
                ct = _parse_dt(d.get("commence_time"))
                cap = _parse_dt(d.get("captured_at"))
                if ct is None or cap is None:
                    continue
                if max_cap is None or cap > max_cap:
                    max_cap = cap
                if min_cap is None or cap < min_cap:
                    min_cap = cap
                horizon = (ct - cap).total_seconds() / 3600.0
                if horizon < 0.0 or horizon > MAX_HORIZON_H:
                    continue
                by_game.setdefault(str(gid), []).append((horizon, float(p)))
    as_of = max_cap.date().isoformat() if max_cap else None
    window: Dict[str, Any] = {
        "source": "data/cache/line_history/%s/*.jsonl (captured_at of every snapshot read)" % sport,
        "first_captured_at": min_cap.date().isoformat() if min_cap else None,
        "last_captured_at": as_of,
        "span_days": (round((max_cap - min_cap).total_seconds() / 86400.0, 1)
                      if (min_cap and max_cap) else None),
        "n_daily_files": n_files,
        "note": ("This is the FULL local capture window, not a season. Counts below are large "
                 "because capture is dense (many books x many ticks per game), not because the "
                 "history is long."),
    }
    return by_game, as_of, window


def load_outcomes(sport: str) -> Dict[str, int]:
    """Return ESPN event IDs mapped to settled binary home-win outcomes."""
    import pandas as pd

    path, mode = JOINABLE[sport]
    df = pd.read_parquet(path)
    out: Dict[str, int] = {}
    for _, r in df.iterrows():
        eid = str(r["event_id"])
        if mode == "home_win":
            hw = r.get("home_win")
            if hw is None or (isinstance(hw, float) and math.isnan(hw)):
                continue
            out[eid] = int(hw)
        else:
            if not bool(r.get("completed", True)):
                continue
            hs, as_ = r.get("home_score"), r.get("away_score")
            if hs is None or as_ is None or (isinstance(hs, float) and math.isnan(hs)):
                continue
            out[eid] = int(hs > as_)
    return out


def bucket_prob(snaps: List[Tuple[float, float]], window: Tuple[float, float]) -> Optional[float]:
    """Return the median probability in a horizon window, or ``None``."""
    lo, hi = window
    ps = [p for h, p in snaps if lo <= h < hi]
    return statistics.median(ps) if ps else None


def score_bucket(pairs: List[Tuple[float, int]]) -> Dict[str, Any]:
    """Score a probability/outcome bucket with Brier and log-loss."""
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    brier = sum((p - y) ** 2 for p, y in pairs) / n
    ll = 0.0
    for p, y in pairs:
        pc = min(max(p, 1e-6), 1.0 - 1e-6)
        ll += -(y * math.log(pc) + (1 - y) * math.log(1.0 - pc))
    return {
        "n": n,
        "brier": round(brier, 6),
        "logloss": round(ll / n, 6),
        "mean_prob": round(sum(p for p, _ in pairs) / n, 4),
        "underpowered": n < MIN_N_POWERED,
    }
