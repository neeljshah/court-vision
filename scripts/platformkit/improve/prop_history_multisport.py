"""scripts.platformkit.improve.prop_history_multisport -- EXTEND the leak-free historical
prop-calibration ratchet to MLB / tennis / soccer, reusing the exact NBA as-of pattern.

THE GAP (same as prop_history_backtest, other sports): the live prop ratchet only learns
from settled LIVE prop bets, which trickle in slowly. But each sport already has per-player
per-game counting stats on disk (MLB batting gamelogs, tennis serve stats, soccer shots).
This module turns those into a LEAK-FREE (model_prob, outcome) prop corpus and runs it
through the SAME prop_calibration_ratchet -> a real SHIP/HOLD/REJECT/INSUFFICIENT verdict
per sport, with no live games.

LEAK-FREE BY CONSTRUCTION (identical to the NBA module): for player game N the model uses
ONLY games < N. The line is the player's prior-to-date MEDIAN (a stable, book-like number);
the model is a recency-weighted Gaussian over the last RECENT_W prior games. p_over =
P(X > line). The realized stat at game N decides over/under; half-point lines -> no pushes.

HONEST: calibration != edge; no $ field; market_prob=None (no historical prop close). Each
sport writes its OWN corpus file (prop_history_corpus_<sport>.jsonl), NEVER the live units
ledger. PROPOSE/RECORD only (verdict -> prop_improve_ledger.jsonl tagged source=history +
sport). Where the on-disk data is genuinely thin (e.g. a World-Cup-only soccer table) the
ratchet honestly returns INSUFFICIENT_DATA -- a SUCCESS, not a failure. Never arms serving /
flips a flag / writes data/registry/. Build only under scripts/platformkit/; <=300 LOC; ASCII.
CLI: python -m scripts.platformkit.improve.prop_history_multisport --sport mlb --seed 1
Per-file test: scripts/platformkit/improve/test_prop_history_multisport.py
"""
from __future__ import annotations

import logging
import random
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.improve.prop_history_backtest import (
    _p_over, _recency_mean_std, _round_half,
)

logger = logging.getLogger("prop_history_multisport")

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_DOMAINS = _REPO / "data" / "domains"
_FRONTEND = _REPO / "data" / "frontend"


def _corpus_path(sport: str) -> Path:
    return _FRONTEND / ("prop_history_corpus_%s.jsonl" % str(sport).lower())


def _isnum(x: Any) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and x != x)


# --- per-sport long-frame loaders: each returns {player_id: [(date_str, {stat: val}), ...]}
# sorted ASCENDING by date (leak-free order). Missing data -> {} -> honest INSUFFICIENT_DATA.

def _dated_from_long(records: List[tuple]) -> Dict[str, List[tuple]]:
    """records: list of (player_id, date_str, stat_dict). Group + sort ascending."""
    by_pid: Dict[str, List[tuple]] = {}
    for pid, ds, sd in records:
        if pid is None or ds is None:
            continue
        by_pid.setdefault(str(pid), []).append((str(ds), sd))
    for pid in by_pid:
        by_pid[pid].sort(key=lambda t: t[0])
    return by_pid


def _read_parquet(path: Path):
    try:
        import pandas as pd  # local import: heavy dep, keep module import cheap
        if not path.exists():
            return None
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("parquet read failed %s: %s", path, exc)
        return None


def _date_str(v: Any) -> Optional[str]:
    try:
        import pandas as pd
        ts = pd.to_datetime(v, errors="coerce")
        if ts is None or ts != ts:  # NaT
            return None
        return ts.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _load_mlb(stats: Sequence[str]) -> Dict[str, List[tuple]]:
    df = _read_parquet(_DOMAINS / "mlb" / "player_gamelogs.parquet")
    if df is None or df.empty:
        return {}
    if "is_pitcher" in df.columns:
        df = df[df["is_pitcher"] == False]  # noqa: E712 -- batting props only
    recs: List[tuple] = []
    for r in df.itertuples(index=False):
        d = r._asdict()
        sd = {s: float(d[s]) for s in stats if s in d and _isnum(d[s])}
        recs.append((d.get("player_id"), _date_str(d.get("date")), sd))
    return _dated_from_long(recs)


def _load_soccer(stats: Sequence[str]) -> Dict[str, List[tuple]]:
    df = _read_parquet(_DOMAINS / "soccer" / "espn_player_stats.parquet")
    if df is None or df.empty:
        return {}
    recs: List[tuple] = []
    for r in df.itertuples(index=False):
        d = r._asdict()
        sd = {s: float(d[s]) for s in stats if s in d and _isnum(d[s])}
        recs.append((d.get("player_id"), _date_str(d.get("date")), sd))
    return _dated_from_long(recs)


def _load_tennis(stats: Sequence[str]) -> Dict[str, List[tuple]]:
    """Melt match_stats (per-event p1_/p2_ serve stats) joined to matches (date, ids) into
    one per-player-per-match row each. stat names are the bare suffixes, e.g. 'ace','df'."""
    ms = _read_parquet(_DOMAINS / "tennis" / "match_stats.parquet")
    mt = _read_parquet(_DOMAINS / "tennis" / "matches.parquet")
    if ms is None or mt is None or ms.empty or mt.empty:
        return {}
    try:
        m = mt[["event_id", "date", "p1_id", "p2_id"]].merge(ms, on="event_id", how="inner")
    except Exception as exc:  # noqa: BLE001
        logger.debug("tennis merge failed: %s", exc)
        return {}
    recs: List[tuple] = []
    for r in m.itertuples(index=False):
        d = r._asdict()
        ds = _date_str(d.get("date"))
        for side, pid_key in (("p1", "p1_id"), ("p2", "p2_id")):
            sd = {s: float(d["%s_%s" % (side, s)]) for s in stats
                  if ("%s_%s" % (side, s)) in d and _isnum(d["%s_%s" % (side, s)])}
            recs.append((d.get(pid_key), ds, sd))
    return _dated_from_long(recs)


# sport -> (loader, stats, min_history). min_history is the per-stat prior-game floor; thin
# sports (soccer World Cup) naturally fall below the ratchet's n>=60 -> INSUFFICIENT_DATA.
SPORT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "mlb": {"loader": _load_mlb,
            "stats": ("hits", "totalBases", "rbi", "runs", "strikeOuts"), "min_history": 12},
    "tennis": {"loader": _load_tennis, "stats": ("ace", "df"), "min_history": 10},
    "soccer": {"loader": _load_soccer,
               "stats": ("totalShots", "shotsOnTarget", "foulsCommitted"), "min_history": 4},
}

MULTISPORT_SPORTS = tuple(SPORT_CONFIGS.keys())


def sport_stat_pairs() -> List[tuple]:
    """Flat (sport, stat) list across all configs -- the per-stat fold rotation for the loop
    so the meta-aggregator can report a replicated verdict per (sport, stat), not just ALL."""
    pairs: List[tuple] = []
    for sport, cfg in SPORT_CONFIGS.items():
        for stat in cfg["stats"]:
            pairs.append((sport, stat))
    return pairs


def _player_rows(sport: str, player_id: str, dated: List[tuple],
                 stats: Sequence[str], min_history: int,
                 only_stat: Optional[str] = None) -> List[Dict[str, Any]]:
    """Leak-free settled-prop rows for one player (game N model uses only games < N).
    Mirrors prop_history_backtest._player_rows exactly, generalized over stat names."""
    use_stats = [only_stat] if only_stat else list(stats)
    out: List[Dict[str, Any]] = []
    for n in range(min_history, len(dated)):
        prior = [t[1] for t in dated[:n]]
        gdate, game = dated[n][0], dated[n][1]
        for stat in use_stats:
            pv = [float(p[stat]) for p in prior if _isnum(p.get(stat))]
            rv = game.get(stat)
            if len(pv) < min_history or not _isnum(rv):
                continue
            line = _round_half(statistics.median(pv))
            mean, std = _recency_mean_std(pv)
            realized = float(rv)
            if realized == line:
                continue  # half-point line -> never a fabricated push
            out.append({
                "sport": sport, "market_type": "prop", "status": "settled",
                "model_prob": round(_p_over(mean, std, line), 6),
                "market_prob": None,  # no historical prop close -> honest None
                "prop_side": "over",
                "outcome": "win" if realized > line else "loss",
                "line": line, "realized_stat": realized,
                "prop_player": str(player_id), "prop_stat": stat.lower(),
                "ts": "%sT00:00:00" % gdate,
                "bet_id": "hist|%s|%s|%s|%s|%s" % (
                    sport, player_id, stat, gdate.replace("-", ""), line),
                "market": "prop|%s|%s|%s|over" % (player_id, stat.lower(), line),
                "clv_status": "no_close", "edge_claimed": False, "executed": False,
            })
    return out


def build_history_corpus(sport: str, *, seed: int = 0, max_rows: int = 3000,
                         only_stat: Optional[str] = None) -> List[Dict[str, Any]]:
    """Build a LEAK-FREE historical settled-prop corpus for one sport from a FRESH random
    player sample (rotating seed -> an independent fold). Empty when data is thin."""
    cfg = SPORT_CONFIGS.get(str(sport).lower())
    if cfg is None:
        return []
    by_pid = cfg["loader"](cfg["stats"])
    if not by_pid:
        return []
    pids = sorted(by_pid.keys())
    rng = random.Random(seed)
    rng.shuffle(pids)
    rows: List[Dict[str, Any]] = []
    for pid in pids:
        if len(rows) >= max_rows:
            break
        rows.extend(_player_rows(sport, pid, by_pid[pid], cfg["stats"],
                                 int(cfg["min_history"]), only_stat=only_stat))
    rows.sort(key=lambda r: r["ts"])
    return rows[:max_rows]


def write_corpus(rows: Sequence[Dict[str, Any]], path: Path) -> Path:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def run_history_fold(sport: str, *, seed: int = 0, max_rows: int = 3000,
                     only_stat: Optional[str] = None,
                     corpus_path: Optional[Path] = None,
                     ledger_path: Optional[Path] = None,
                     append: bool = True) -> Dict[str, Any]:
    """Build one historical fold for `sport` + run the prop ratchet on it; record the tagged
    verdict. Own corpus file (never the live units ledger); verdict tagged source=history +
    sport + fold_seed in prop_improve_ledger. Never raises."""
    from scripts.platformkit.improve import prop_calibration_ratchet as R
    sp = str(sport).lower()
    corpus_path = Path(corpus_path) if corpus_path else _corpus_path(sp)
    try:
        rows = build_history_corpus(sp, seed=seed, max_rows=max_rows, only_stat=only_stat)
        write_corpus(rows, corpus_path)
        rec = R.improve_cycle(sp, clv_path=corpus_path, append=False)
        rec["source"] = "history"
        rec["fold_seed"] = seed
        rec["n_rows"] = len(rows)
        if only_stat:
            rec["stat"] = str(only_stat).lower()
        if append:
            R._append(Path(ledger_path) if ledger_path else R.DEFAULT_PROP_LEDGER, rec)
        return rec
    except Exception as exc:  # noqa: BLE001 -- a fold error must never sink the caller/loop
        return {"status": "error", "source": "history", "sport": sp, "fold_seed": seed,
                "reason": "%s: %s" % (type(exc).__name__, exc)}


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Multi-sport leak-free prop calibration backtest.")
    ap.add_argument("--sport", default="mlb", choices=list(MULTISPORT_SPORTS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-rows", type=int, default=3000)
    ap.add_argument("--stat", default=None)
    a = ap.parse_args(argv)
    rec = run_history_fold(a.sport, seed=a.seed, max_rows=a.max_rows,
                           only_stat=a.stat, append=True)
    print()
    print("PROP HISTORY BACKTEST (multisport) -- leak-free recency-Gaussian calibration")
    print("-" * 78)
    print("sport=%s seed=%s stat=%s n_rows=%s verdict=%s" % (
        a.sport, a.seed, a.stat, rec.get("n_rows"), rec.get("verdict", rec.get("status"))))
    ro = rec.get("readout") or {}
    print("raw_brier=%s raw_ece=%s base_rate=%s" % (
        ro.get("raw_brier"), ro.get("raw_ece"), ro.get("base_rate")))
    print("delta_brier=%s dm_p=%s null_shipped=%s" % (
        rec.get("delta_brier"), rec.get("dm_p"), rec.get("null_shipped")))
    print("reason:", str(rec.get("reason", ""))[:120])
    print("calibration != edge; PROPOSE/RECORD only; no $; not a bet.")
    return 0


__all__ = [
    "build_history_corpus", "write_corpus", "run_history_fold",
    "SPORT_CONFIGS", "MULTISPORT_SPORTS", "sport_stat_pairs",
]


if __name__ == "__main__":
    raise SystemExit(_main())
