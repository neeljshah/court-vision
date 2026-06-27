"""scripts.platformkit.odds_provider.oddsapi_close_corpus -- turn the backfilled
multi-snapshot odds into a per-game CLOSE corpus the AI learns from.

The backfill (oddsapi_team_backfill) records many pregame snapshots per game (line
evolution). For calibration we want THE CLOSE = the latest pregame snapshot per
(event, market). This module extracts that, joins realized outcomes, and emits the
SAME state shape market_coverage.corpora produces -- (game_id, home, away, state_ts,
outcome, devig_close_prob) -- so the existing edge-finder / recalibrator / eval-gate
consume it WITHOUT change. It directly fills the MLB seam that was `DATA_LIMITED`
(mlb_ml_states returned [] -- no joinable local close); now we have the devigged
Pinnacle close keyed by date+team.

This is the "old data" leg. The SAME extractor reads live-captured close JSONL too,
so the self-improve loop blends historical + live and keeps recalibrating on its own.

Calibration only -- the devigged close is the benchmark, never a $ / ROI claim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.odds_provider.team_resolver import canonical  # noqa: E402

LINES_DIR = ROOT / "data" / "external" / "historical_lines"
DOMAINS = ROOT / "data" / "domains"


# ---- close selection (pure; testable on canned rows) ---------------------- #

def select_closes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per (event_id|date+teams, market) keep THE CLOSE: the row with the latest
    snapshot_ts that is still strictly pregame (snapshot_ts < commence_time) AND
    carries a Pinnacle anchor devig. In-play / un-anchored rows are dropped."""
    best: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        if not r.get("anchor_devig"):
            continue
        ts, ct = r.get("snapshot_ts"), r.get("commence_time")
        if ts and ct and not (ts < ct):       # ISO strings compare chronologically
            continue                            # not pregame -> not a close
        eid = r.get("event_id") or f"{r.get('date')}|{r.get('home')}|{r.get('away')}"
        key = (eid, r.get("market"))
        cur = best.get(key)
        if cur is None or (ts or "") > (cur.get("snapshot_ts") or ""):
            best[key] = r
    return list(best.values())


def load_closes(sport: str, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read {sport}_team_strength.jsonl (+ any live-capture file) -> closes."""
    p = path or (LINES_DIR / f"{sport}_team_strength.jsonl")
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return select_closes(rows)


# ---- outcome join -> corpora-compatible states ---------------------------- #

def _home_prob(close: Dict[str, Any]) -> Optional[float]:
    """Devigged P(home win) from an h2h close (names aligned to home_team)."""
    dev = close.get("anchor_devig") or {}
    names, probs = dev.get("names") or [], dev.get("probs") or []
    home = close.get("home")
    if home in names:
        return float(probs[names.index(home)])
    return None


def to_home_win_states(closes: List[Dict[str, Any]],
                       result_prob_of_home: Callable[[Dict[str, Any]], Optional[int]],
                       sport: str) -> List[Dict[str, Any]]:
    """Join h2h closes to realized home-win outcomes -> walk-forward states.

    `result_prob_of_home(close)` returns 1 (home won) / 0 (home lost) / None (no
    result or unjoinable). Draws (soccer) are excluded from the 2-way home-win frame.
    """
    states: List[Dict[str, Any]] = []
    h2h = [c for c in closes if c.get("market") == "h2h"]
    h2h.sort(key=lambda c: str(c.get("commence_time") or ""))
    for i, c in enumerate(h2h):
        ph = _home_prob(c)
        if ph is None:
            continue
        y = result_prob_of_home(c)
        if y is None:
            continue
        ct = str(c.get("commence_time") or c.get("date") or "")
        states.append({
            "game_id": f"{sport}-{c.get('date')}-{c.get('home')}-{c.get('away')}",
            "home": str(c.get("home")), "away": str(c.get("away")),
            # unique monotonic ts so walk_forward purge/embargo never collapses the sample
            "state_ts": f"{ct[:10]}T00:{i % 60:02d}:{i // 60 % 60:02d}",
            "outcome": int(y), "devig_close_prob": float(ph),
        })
    return states


# ---- per-sport realized-result lookups ------------------------------------ #

def _game_dates(close: Dict[str, Any]) -> List[str]:
    """Candidate YYYYMMDD keys for a game: the commence UTC date AND the prior day
    (ESPN dates games by local ET, so a late UTC-night game is the previous ET day)."""
    from datetime import datetime, timedelta
    ct = str(close.get("commence_time") or "")
    base = (ct[:10] or str(close.get("date") or "")).replace("-", "")[:8]
    out = [base]
    try:
        out.append((datetime.strptime(base, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d"))
    except ValueError:
        pass
    return out


def _mlb_result_fn(root: Path) -> Callable[[Dict[str, Any]], Optional[int]]:
    import pandas as pd
    box = pd.read_parquet(root / "espn_boxscores.parquet")
    box = box.dropna(subset=["home_score", "away_score"]).copy()
    box["d"] = box["date"].astype(str).str[:8]            # YYYYMMDD int -> str
    idx: Dict[tuple, int] = {}
    for _, r in box.iterrows():
        k = (r["d"], canonical("mlb", str(r["home_abbr"])), canonical("mlb", str(r["away_abbr"])))
        idx[k] = int(float(r["home_score"]) > float(r["away_score"]))

    def fn(c: Dict[str, Any]) -> Optional[int]:
        home, away = canonical("mlb", str(c.get("home"))), canonical("mlb", str(c.get("away")))
        for d in _game_dates(c):
            if (d, home, away) in idx:
                return idx[(d, home, away)]
        return None
    return fn


def _soccer_result_fn(root: Path) -> Callable[[Dict[str, Any]], Optional[int]]:
    import pandas as pd
    res = pd.read_parquet(root / "results.parquet")
    res = res.dropna(subset=["home_score", "away_score"]).copy()
    res["d"] = pd.to_datetime(res["date"], errors="coerce").dt.strftime("%Y%m%d")
    idx: Dict[tuple, int] = {}
    for _, r in res.iterrows():
        if r["home_score"] == r["away_score"]:
            continue                                       # draw -> not a home-win label
        k = (r["d"], canonical("soccer", str(r["home_team"])), canonical("soccer", str(r["away_team"])))
        idx[k] = int(float(r["home_score"]) > float(r["away_score"]))

    def fn(c: Dict[str, Any]) -> Optional[int]:
        home, away = canonical("soccer", str(c.get("home"))), canonical("soccer", str(c.get("away")))
        for d in _game_dates(c):
            if (d, home, away) in idx:
                return idx[(d, home, away)]
        return None
    return fn


_RESULT_FNS: Dict[str, Callable[[Path], Callable[[Dict[str, Any]], Optional[int]]]] = {
    "mlb": _mlb_result_fn,
    "soccer_intl": _soccer_result_fn,
}
_RESULT_ROOT = {"mlb": DOMAINS / "mlb", "soccer_intl": DOMAINS / "soccer_intl"}


def build_states(sport: str) -> List[Dict[str, Any]]:
    """Full pipeline: backfilled closes JOIN realized outcomes -> corpora states.
    A corpora.py-compatible builder -- feeds edge_finder / recalibrator directly."""
    closes = load_closes(sport)
    if sport not in _RESULT_FNS:
        return []
    result_fn = _RESULT_FNS[sport](_RESULT_ROOT[sport])
    return to_home_win_states(closes, result_fn, sport)


def _brier(states: List[Dict[str, Any]]) -> Optional[float]:
    if not states:
        return None
    return sum((s["devig_close_prob"] - s["outcome"]) ** 2 for s in states) / len(states)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Build a devigged-close calibration corpus from backfill.")
    ap.add_argument("--sport", default="mlb", choices=sorted(_RESULT_FNS))
    args = ap.parse_args(argv)
    closes = load_closes(args.sport)
    states = build_states(args.sport)
    n_h2h = sum(1 for c in closes if c.get("market") == "h2h")
    out = {
        "sport": args.sport, "closes_total": len(closes), "closes_h2h": n_h2h,
        "labeled_states": len(states),
        "home_win_base_rate": round(sum(s["outcome"] for s in states) / len(states), 4) if states else None,
        "close_brier": round(_brier(states), 5) if states else None,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
