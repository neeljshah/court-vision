"""scripts.platformkit.ingame.ingame_clv_aggregate -- honest multi-game in-game CLV aggregator.

Pools per-game in-game CLV across many settled grade files and reads ONE honest verdict.
This is the SIMPLE CLV-arm-only aggregator (no DM test, no outcome-Brier arm) that the BACKLOG
task ig-clv-aggregate specifies. It is intentionally thinner than inplay_aggregate_grade (which
adds the full two-arm DM/outcome-Brier pool); this module is the fast, CLV-only, queryable view.

REUSES, never rebuilds:
  * per-game grade  -> live_grade.grade_game (which calls inplay_clv_replay.replay_series,
    leak-free: the model only ever sees series[:i+1]; the close is the last tick).
  * discovery       -> same data/cache/ingame_grade/<sport>/*.jsonl layout as live_grade.

POOL VERDICT (CLV arm, honest):
  Requires >= MIN_GAMES games with at least one scored tick AND >= MIN_TOTAL_TICKS pooled ticks.
  Below either threshold -> INSUFFICIENT_DATA (honest "can't tell yet", NEVER a fabricated beat).
  With enough data:
    BEAT   : pooled mean CLV > +eps AND the game-clustered bootstrap 95% CI lower bound > 0.
    BEHIND : pooled mean CLV < -eps.
    MATCH  : otherwise (within noise).
  edge_claimed is ALWAYS False: this is a calibration measurement, never an execution claim.
  NO $ / roi / pnl / stake / bankroll / profit field. UNITS / PROBABILITY only.

SYNTHETIC-PAIR RECOVERY (the test contract):
  A planted CLV can be recovered by building synthetic per-game grade files where model_prob
  consistently leads the market in the right direction (positive CLV) or the wrong direction
  (negative CLV). Below MIN_GAMES the verdict is INSUFFICIENT_DATA regardless of raw signal.
  With >=MIN_GAMES games carrying a planted CLV > eps -> BEAT (or BEHIND if planted < -eps).
  With >=MIN_GAMES market-copy games (model == market) -> pooled mean_clv = 0.0 -> MATCH.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no network at import;
no data/registry write; no flag flip; never edits src/ kernel/ live_grade.py / inplay_clv_replay.py.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_clv_aggregate.py -q
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame import live_grade as lg
from scripts.platformkit.forward_capture import inplay_clv_replay as ic

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/ingame_clv_aggregate.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"

# Honest minimums -- one or few games is variance, not signal.
MIN_GAMES: int = 5           # distinct games with >=1 scored tick
MIN_TOTAL_TICKS: int = 40    # pooled scored ticks across all games
EPS_DEFAULT: float = ic.EPS_DEFAULT   # 0.005 probability units
_BOOTSTRAP_ITERS: int = 2_000


# --------------------------------------------------------------------------------------- #
# discovery                                                                               #
# --------------------------------------------------------------------------------------- #
def discover_grade_files(grade_dir: Optional[Path] = None,
                         sport: Optional[str] = None) -> List[Path]:
    """List per-game grade files under data/cache/ingame_grade/<sport>/*.jsonl, sorted.

    If sport is given, only that sport's subdir is scanned. Hidden files (leading _) are
    skipped. Never raises; a missing dir yields [].
    """
    base = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    if not base.is_dir():
        return []
    sub_dirs: List[Path]
    if sport:
        sub_dirs = [base / sport.lower()]
    else:
        sub_dirs = [d for d in sorted(base.iterdir()) if d.is_dir()]
    out: List[Path] = []
    for d in sub_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.jsonl")):
            if not f.name.startswith("_"):
                out.append(f)
    return out


# --------------------------------------------------------------------------------------- #
# per-game grade (wraps live_grade.grade_game)                                            #
# --------------------------------------------------------------------------------------- #
def grade_one(path: Path, *,
              eps: float = EPS_DEFAULT,
              min_ticks: int = ic.MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Grade ONE game via the EXISTING leak-free live_grade.grade_game.

    Returns a slim dict: {game_id, mean_clv, n_ticks, settle_ts, per_game_verdict}.
    n_ticks == 0 means the file had no valid pairs; those games are excluded from the pool.
    Never raises.
    """
    g = lg.grade_game(str(path), eps=eps, min_ticks=min_ticks)
    settle_ts = _settle_ts(path)
    return {
        "game_id": str(g.get("game_id", path.stem)),
        "mean_clv": float(g.get("mean_clv", 0.0)),
        "n_ticks": int(g.get("n_ticks_scored", 0)),
        "settle_ts": settle_ts,
        "per_game_verdict": str(g.get("verdict", "INSUFFICIENT_DATA")),
    }


def _settle_ts(path: Path) -> str:
    """Last row ts from the grade file; '' when unavailable."""
    last = ""
    if not path.is_file():
        return last
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("ts"):
                last = str(rec["ts"])
    return last


# --------------------------------------------------------------------------------------- #
# game-clustered bootstrap CI                                                             #
# --------------------------------------------------------------------------------------- #
def _cluster_bootstrap_ci(per_game_clv: Sequence[float], *,
                           iters: int = _BOOTSTRAP_ITERS,
                           seed: int = 42) -> Tuple[float, float]:
    """95% CI for pooled mean CLV by resampling GAMES (the cluster) with replacement.

    Game-clustered: each draw resamples whole games so within-game tick correlations do not
    inflate apparent precision. Returns (lo, hi). Single game -> (mean, mean) forcing the
    caller toward INSUFFICIENT_DATA rather than a spurious CI.
    """
    vals = [float(v) for v in per_game_clv]
    g = len(vals)
    if g == 0:
        return (0.0, 0.0)
    if g == 1:
        return (vals[0], vals[0])
    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(iters):
        sample = [vals[rng.randrange(g)] for _ in range(g)]
        means.append(sum(sample) / g)
    means.sort()
    lo = means[int(0.025 * (iters - 1))]
    hi = means[int(0.975 * (iters - 1))]
    return (lo, hi)


# --------------------------------------------------------------------------------------- #
# the aggregator                                                                          #
# --------------------------------------------------------------------------------------- #
def aggregate(grade_dir: Optional[Path] = None, *,
              sport: Optional[str] = None,
              paths: Optional[Sequence[Path]] = None,
              eps: float = EPS_DEFAULT,
              min_games: int = MIN_GAMES,
              min_total_ticks: int = MIN_TOTAL_TICKS,
              min_ticks: int = ic.MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Pool many settled games into ONE honest CLV verdict. NEVER raises.

    Discovers (or takes injected) per-game grade files, grades each through the EXISTING
    leak-free live_grade.grade_game, then pools with a game-clustered bootstrap CI.

    Below min_games games with scored ticks OR below min_total_ticks pooled ticks:
      -> verdict = INSUFFICIENT_DATA (honest; never a fabricated beat).
    With enough data:
      BEAT   : pooled mean CLV > +eps AND game-clustered bootstrap 95% CI lower bound > 0.
      BEHIND : pooled mean CLV < -eps.
      MATCH  : within noise.

    Returns a dict with verdict in {BEAT, MATCH, BEHIND, INSUFFICIENT_DATA},
    units='probability', edge_claimed=False. No $ field.
    """
    files = list(paths) if paths is not None else discover_grade_files(grade_dir, sport)
    all_grades = [grade_one(Path(p), eps=eps, min_ticks=min_ticks) for p in files]

    # Only include games that produced at least one scored tick (0-tick = no evidence).
    scored = [g for g in all_grades if g["n_ticks"] > 0]
    n_games = len(scored)
    total_ticks = sum(g["n_ticks"] for g in scored)
    per_game_clv = [g["mean_clv"] for g in scored]
    pooled_mean = sum(per_game_clv) / n_games if n_games else 0.0

    ci_lo, ci_hi = _cluster_bootstrap_ci(per_game_clv)

    # CLV-over-time series for the UI: per-game CLV ordered by settle time.
    ordered = sorted(scored, key=lambda g: (str(g["settle_ts"]), str(g["game_id"])))
    clv_series = [
        {"game_id": g["game_id"], "settle_ts": g["settle_ts"],
         "mean_clv": round(g["mean_clv"], 6), "n_ticks": g["n_ticks"]}
        for g in ordered
    ]

    enough = n_games >= int(min_games) and total_ticks >= int(min_total_ticks)
    if not enough:
        verdict = "INSUFFICIENT_DATA"
    elif pooled_mean < -eps:
        verdict = "BEHIND"
    elif pooled_mean > eps and ci_lo > 0.0:
        verdict = "BEAT"
    else:
        verdict = "MATCH"

    return {
        "verdict": verdict,
        "n_games": int(n_games),
        "total_ticks_scored": int(total_ticks),
        "pooled_mean_clv": float(pooled_mean),
        "clv_ci95": [float(ci_lo), float(ci_hi)],
        "clv_series": clv_series,
        "per_game": [
            {"game_id": g["game_id"], "mean_clv": round(g["mean_clv"], 6),
             "n_ticks": g["n_ticks"], "per_game_verdict": g["per_game_verdict"]}
            for g in scored
        ],
        "min_games": int(min_games),
        "min_total_ticks": int(min_total_ticks),
        "eps": float(eps),
        "units": "probability",
        "edge_claimed": False,
        "label": "measurement only -- in-game CLV in probability space, no currency",
    }


def format_report(result: Dict[str, Any]) -> str:
    """ASCII summary of the pooled verdict. No $ figure -- CLV is probability space."""
    lo, hi = result.get("clv_ci95", [0.0, 0.0])
    lines = [
        "=== Multi-game in-game CLV aggregate (honest) ===",
        "verdict        : %s" % result.get("verdict"),
        "n_games        : %d" % result.get("n_games", 0),
        "total_ticks    : %d" % result.get("total_ticks_scored", 0),
        "pooled_mean_clv: %+.5f  (probability space; + = beat the close)" % (
            result.get("pooled_mean_clv", 0.0)),
        "clv_ci95       : [%+.5f, %+.5f]  (game-clustered bootstrap 95%%)" % (lo, hi),
        "units          : probability (CLV / calibration only -- never dollars)",
        "edge_claimed   : False",
    ]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_GRADE_DIR", "MIN_GAMES", "MIN_TOTAL_TICKS", "EPS_DEFAULT",
    "discover_grade_files", "grade_one", "aggregate", "format_report",
]
