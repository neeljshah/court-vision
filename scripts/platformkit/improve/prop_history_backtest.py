"""scripts.platformkit.improve.prop_history_backtest -- feed the PROP ratchet from the
on-disk historical gamelogs so it gets better from OLD games (no live games needed).

THE GAP: the live prop_calibration_ratchet only learns from settled LIVE prop bets, which
trickle in slowly (offseason -> INSUFFICIENT_DATA). But ~200k historical NBA player-game
rows already sit on disk. This module builds a LEAK-FREE historical (model_prob, outcome)
corpus from those gamelogs and runs it through the SAME ratchet -> a REAL SHIP/HOLD/REJECT
calibration verdict from history, with no live games.

LEAK-FREE BY CONSTRUCTION: for player game N the model uses ONLY games < N. The line is
the player's prior season-to-date MEDIAN (a stable, book-like number); the model is a
recency-weighted Gaussian over the last RECENT_W prior games (mirrors the production
prop_surface 'recency_gaussian' method). p_over = P(X > line), X ~ N(recent_mean, recent_std).
The realized stat at game N decides over/under. Half-point lines -> no pushes.

RUNS-ALL-NIGHT / honest replication: each fold samples a FRESH random subset of players
(rotating seed) -> an INDEPENDENT corpus each cycle. Accumulating folds is exactly the
">= 2 independent corpora; single-fold lifts are artifacts" discipline -- the meta-verdict
sharpens overnight as more folds land. NOT an infinite edge machine: it converges to the
honest calibration verdict for the recency-Gaussian prop method.

HONESTY: calibration != edge; no $ field. The historical corpus is written to its OWN file
(prop_history_corpus.jsonl), NEVER the live units ledger -- these are backtest rows, not
bets. PROPOSE/RECORD only (verdict -> prop_improve_ledger.jsonl, tagged source=history);
never arms serving / flips a flag / writes data/registry/. No historical prop CLOSE exists
-> market_prob=None (the market controls honestly skip). Build only under scripts/platformkit/;
<=300 LOC; ASCII. CLI: python -m scripts.platformkit.improve.prop_history_backtest
Per-file test: scripts/platformkit/improve/test_prop_history_backtest.py
"""
from __future__ import annotations

import glob
import json
import logging
import math
import random
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("prop_history_backtest")

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_GAMELOG_DIR = _REPO / "data" / "nba"
DEFAULT_CORPUS = _REPO / "data" / "frontend" / "prop_history_corpus.jsonl"

STATS = ("PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV")
RECENT_W = 10          # recency window for the model mean/std (leak-free, prior games only)
MIN_HISTORY = 12       # need this many prior games before a player-game is usable
_STD_FLOOR = 0.5       # avoids a degenerate (zero-variance) prob
_SQRT2 = math.sqrt(2.0)
_CLIP = 1e-6


def _parse_date(s: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(s).strip(), "%b %d, %Y")
    except (ValueError, TypeError):
        return None


def _p_over(mean: float, std: float, line: float) -> float:
    """P(X > line), X ~ N(mean, std). 1 - Phi(z) = 0.5 * erfc(z / sqrt 2)."""
    z = (line - mean) / max(std, _STD_FLOOR)
    return min(1.0 - _CLIP, max(_CLIP, 0.5 * math.erfc(z / _SQRT2)))


def _round_half(x: float) -> float:
    return round(x * 2.0) / 2.0


def _recency_mean_std(prior_vals: Sequence[float]) -> tuple:
    recent = list(prior_vals[-RECENT_W:])
    mean = statistics.mean(recent)
    std = statistics.pstdev(recent) if len(recent) > 1 else 0.0
    return float(mean), float(max(std, _STD_FLOOR))


def _load_player_dated(path: str) -> List[tuple]:
    """Return [(date, row), ...] sorted ASCENDING (oldest first) for leak-free order."""
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("gamelog read failed %s: %s", path, exc)
        return []
    if not isinstance(rows, list):
        return []
    dated = [(d, r) for r in rows if isinstance(r, dict)
             for d in (_parse_date(r.get("GAME_DATE")),) if d is not None]
    dated.sort(key=lambda t: t[0])
    return dated


def _player_rows(player_id: str, dated: List[tuple], stats: Sequence[str]) -> List[Dict[str, Any]]:
    """Leak-free settled-prop rows for one player (game N model uses only games < N)."""
    out: List[Dict[str, Any]] = []
    for n in range(MIN_HISTORY, len(dated)):
        prior = [t[1] for t in dated[:n]]
        game, gdate = dated[n][1], dated[n][0]
        for stat in stats:
            pv = [float(p[stat]) for p in prior if isinstance(p.get(stat), (int, float))]
            rv = game.get(stat)
            if len(pv) < MIN_HISTORY or not isinstance(rv, (int, float)):
                continue
            line = _round_half(statistics.median(pv))
            mean, std = _recency_mean_std(pv)
            realized = float(rv)
            if realized == line:
                continue  # half-point line -> rare; never a fabricated push
            out.append({
                "sport": "nba", "market_type": "prop", "status": "settled",
                "model_prob": round(_p_over(mean, std, line), 6),
                "market_prob": None,  # no historical prop close -> honest None
                "prop_side": "over",
                "outcome": "win" if realized > line else "loss",
                "line": line, "realized_stat": realized,
                "prop_player": player_id, "prop_stat": stat.lower(),
                "ts": gdate.strftime("%Y-%m-%dT00:00:00"),
                "bet_id": "hist|nba|%s|%s|%s|%s" % (
                    player_id, stat, gdate.strftime("%Y%m%d"), line),
                "market": "prop|%s|%s|%s|over" % (player_id, stat.lower(), line),
                "clv_status": "no_close", "edge_claimed": False, "executed": False,
            })
    return out


def _player_id(path: str) -> str:
    base = Path(path).stem  # gamelog_<id>_<season>
    parts = base.split("_")
    return parts[1] if len(parts) > 1 else base


def build_history_corpus(*, seed: int = 0, max_rows: int = 3000,
                         stats: Sequence[str] = STATS,
                         gamelog_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Build a LEAK-FREE historical settled-prop corpus from a FRESH random player sample.

    Samples enough players (rotating *seed*) to reach ~max_rows, builds per-player leak-free
    rows, caps + sorts chronologically. A different seed -> an independent fold."""
    gdir = Path(gamelog_dir) if gamelog_dir else _GAMELOG_DIR
    files = sorted(f for f in glob.glob(str(gdir / "gamelog_*.json")) if "backup" not in f)
    if not files:
        return []
    rng = random.Random(seed)
    rng.shuffle(files)
    rows: List[Dict[str, Any]] = []
    for f in files:
        if len(rows) >= max_rows:
            break
        rows.extend(_player_rows(_player_id(f), _load_player_dated(f), stats))
    rows.sort(key=lambda r: r["ts"])
    rows = rows[:max_rows]
    return rows


def write_corpus(rows: Sequence[Dict[str, Any]], path: Optional[Path] = None) -> Path:
    path = Path(path) if path else DEFAULT_CORPUS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def run_history_fold(*, seed: int = 0, max_rows: int = 3000,
                     corpus_path: Optional[Path] = None,
                     ledger_path: Optional[Path] = None,
                     gamelog_dir: Optional[Path] = None,
                     append: bool = True) -> Dict[str, Any]:
    """Build one historical fold + run the prop ratchet on it; record the tagged verdict.

    Writes the corpus to its OWN file (never the live units ledger) and the verdict to the
    prop_improve_ledger tagged source=history + fold_seed. Never raises."""
    from scripts.platformkit.improve import prop_calibration_ratchet as R
    corpus_path = Path(corpus_path) if corpus_path else DEFAULT_CORPUS
    try:
        rows = build_history_corpus(seed=seed, max_rows=max_rows, gamelog_dir=gamelog_dir)
        write_corpus(rows, corpus_path)
        rec = R.improve_cycle("nba", clv_path=corpus_path, append=False)
        rec["source"] = "history"
        rec["fold_seed"] = seed
        rec["n_rows"] = len(rows)
        if append:
            R._append(Path(ledger_path) if ledger_path else R.DEFAULT_PROP_LEDGER, rec)
        return rec
    except Exception as exc:  # noqa: BLE001 -- a fold error must never sink the caller/loop
        return {"status": "error", "source": "history", "fold_seed": seed,
                "reason": "%s: %s" % (type(exc).__name__, exc)}


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Historical leak-free prop calibration backtest.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-rows", type=int, default=3000)
    a = ap.parse_args(argv)
    rec = run_history_fold(seed=a.seed, max_rows=a.max_rows, append=True)
    print()
    print("PROP HISTORY BACKTEST -- leak-free recency-Gaussian calibration on old gamelogs")
    print("-" * 78)
    print("seed=%s n_rows=%s verdict=%s" % (
        a.seed, rec.get("n_rows"), rec.get("verdict", rec.get("status"))))
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
    "DEFAULT_CORPUS", "STATS", "MIN_HISTORY",
]


if __name__ == "__main__":
    raise SystemExit(_main())
