"""scripts.platformkit.ingame.inplay_aggregate_grade -- MULTI-GAME aggregate CLV/calib grader.

The honest answer to "are we making money?" is NEVER one game (variance, not signal). This
module is the multi-game POOL that live_grade.grade_game's TODO points to: it discovers MANY
settled per-game graded series, grades each through the EXISTING leak-free P1 CLV replay
(live_grade.grade_game -> inplay_clv_replay), then POOLS with GAME-CLUSTERED statistics and
reads ONE honest verdict.

REUSES, never rebuilds:
  * per-game grade  -> live_grade.grade_game (which calls inplay_clv_replay.replay_series,
    leak-free: the model only ever sees series[:i+1]; the close is the last tick).
  * clustered DM    -> eval_gate.dm_test.diebold_mariano (the verified game-clustered SE).
  * outcome Brier   -> per-state (p - y)**2 squared-error loss diffs fed to that DM.

THE POOL VERDICT (honest, two-arm -- mirrors clv_corpus.py P1 discipline):
  A BEAT requires BOTH arms, on >= MIN_GAMES settled games AND >= MIN_TOTAL_TICKS scored ticks:
    (A) CLV arm:     pooled mean per-game CLV > eps AND its game-clustered bootstrap CI lower
                     bound > 0 (positive CLV vs the TRUE close that survives game clustering).
    (B) OUTCOME arm: a game-clustered DM on per-state OUTCOME-Brier vs the TRUE CLOSE
                     (d = loss_close - loss_model). LEAK-FREE like P1: the close is fixed
                     ONCE to the LAST captured market price per game and that final close
                     tick is EXCLUDED from the scored states (the held-out yardstick never
                     grades itself). positive => model beats the close on the OUTCOME; arm
                     fires on mean_diff > 0 AND p < alpha. A pure market-copy / shrink-
                     toward-close pool has d ~ 0 and mean_clv ~ 0 -> it CANNOT clear arm (B)
                     -> MATCH, never BEAT (the +18.38% market-follow trap is impossible here).
  BEHIND if pooled mean_clv < -eps. INSUFFICIENT_DATA if too few games/ticks, or if no settled
  outcome is available for the OUTCOME arm (honest "can't tell yet", never a fabricated beat).
  Otherwise MATCH.

THE OUTCOME ARM NEEDS A SETTLED OUTCOME per game (binary {0,1}, home win). It is read from an
explicit ``outcome`` / ``settled_outcome`` field on the grade rows if the capture path recorded
the settle. If NO game carries a settled outcome the OUTCOME arm is INSUFFICIENT and the pool
verdict is INSUFFICIENT_DATA -- we never grade outcome-Brier against a fabricated label.

HONESTY (binding): UNITS / PROBABILITY only -- there is NO $ / roi / pnl / stake / bankroll /
edge field anywhere. edge_claimed is always False. vs_close STAYS 'UNPROVEN' here -- a single
pooled window is never a vs_close proof; pool_verdict is reported separately as a measurement,
and a real vs_close upgrade only flows through clv_corpus_inject.maybe_vs_close_upgrade.
Emits a CLV-over-time series (per-game CLV ordered by settle time) for the UI -- numbers only,
measurement-only label. LEAK-FREE end to end (the per-game grade is leak-free; the close is a
held-out yardstick, never a feature).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no network at import;
no data/registry write, no flag flip; never edits live_grade.py / inplay_clv_replay.py / src /
kernel. Proposal / measurement only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_aggregate_grade.py -q
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.ingame import live_grade as lg
from scripts.platformkit.forward_capture import inplay_clv_replay as ic

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/inplay_aggregate_grade.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"

# Honest minimums -- one / few games is variance, not signal.
MIN_GAMES = 5           # distinct settled games to bind a clustered verdict
MIN_TOTAL_TICKS = 40    # pooled scored ticks across all games
EPS_DEFAULT = ic.EPS_DEFAULT
ALPHA_DEFAULT = 0.05
_BOOTSTRAP_ITERS = 2000

# Keys the settled binary outcome (home win = 1) may live under on a grade row.
_OUTCOME_KEYS = ("outcome", "settled_outcome", "home_win", "y")


def _clip01(p: float) -> float:
    return min(1.0 - 1e-6, max(1e-6, float(p)))


# --------------------------------------------------------------------------------------- #
# discovery                                                                               #
# --------------------------------------------------------------------------------------- #
def discover_grade_files(grade_dir: Optional[Path] = None,
                         sport: Optional[str] = None) -> List[Path]:
    """List settled per-game grade files: data/cache/ingame_grade/<sport>/*.jsonl, sorted.

    If sport is given, only that sport's subdir is scanned. Never raises; a missing dir
    yields []. Hidden / freshness sidecar files (leading underscore) are skipped.
    """
    base = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    if not base.is_dir():
        return []
    sub_dirs = [base / sport.lower()] if sport else [
        d for d in sorted(base.iterdir()) if d.is_dir()]
    out: List[Path] = []
    for d in sub_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.jsonl")):
            if f.name.startswith("_"):
                continue
            out.append(f)
    return out


def _settled_outcome(path: Path) -> Optional[float]:
    """Read a settled binary outcome (home win 1 / 0) from a grade file, or None.

    Scans rows for an explicit outcome field; the LAST present value wins (the settle row).
    Returns None when no row carries a settled outcome -- we never infer a label from the
    score state (that would risk grading against a non-final, fabricated outcome).
    """
    if not path.is_file():
        return None
    found: Optional[float] = None
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            for k in _OUTCOME_KEYS:
                if rec.get(k) is not None:
                    try:
                        v = float(rec[k])
                    except (TypeError, ValueError):
                        continue
                    if v in (0.0, 1.0):
                        found = v
    return found


def _settle_ts(path: Path) -> str:
    """Last row ts (settle time) for ordering the CLV-over-time series; '' if unavailable."""
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


def _outcome_losses(path: Path, outcome: float
                    ) -> Tuple[List[float], List[Any]]:
    """Per-state OUTCOME-Brier loss diffs d = loss_close - loss_model for ONE settled game.

    LEAK-FREE (mirrors the P1 keystone inplay_clv_replay / aggregate_clv_to_corpus
    game_to_settled): the CLOSE is fixed ONCE to the LAST captured market price
    (pairs[-1].market_prob) and that final close tick is EXCLUDED from the scored states
    (you cannot beat the close AT the close, and the held-out yardstick must never grade
    itself). Each scored state t in pairs[:-1] contributes d_t = loss_close - loss_model
    where loss_close uses that single held-out close; positive mean => model beats THE
    CLOSE on the OUTCOME. Returns (d_list, cluster_ids) with cluster_id = the game_id so
    the pooled DM clusters by game. A pure market-copy pool still yields d == 0 on every
    scored state (model == close-aligned per state) -> the shrink-trap stays closed.
    """
    pairs = lg._load_pairs(path)  # validity-guarded; rows have model_prob + market_prob
    d: List[float] = []
    cluster: List[Any] = []
    gid = path.stem
    if len(pairs) < 2:
        return d, cluster  # need >=1 scored state PLUS the held-out close tick
    close = _clip01(pairs[-1]["market_prob"])  # THE close: fixed once, held out
    loss_close = (close - outcome) ** 2
    for r in pairs[:-1]:                        # exclude the final close tick from scoring
        mp = _clip01(r["model_prob"])
        loss_model = (mp - outcome) ** 2
        d.append(loss_close - loss_model)
        cluster.append(gid)
    return d, cluster


# --------------------------------------------------------------------------------------- #
# per-game grade                                                                          #
# --------------------------------------------------------------------------------------- #
def grade_one(path: Path, *, eps: float = EPS_DEFAULT,
              min_ticks: int = ic.MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Grade ONE settled game via the EXISTING leak-free live_grade.grade_game + read outcome.

    Returns {game_id, mean_clv, n_ticks, verdict, outcome, settle_ts, d, cluster} where d /
    cluster are the per-state OUTCOME-Brier loss diffs (empty when no settled outcome). Never
    raises (a bad file -> n_ticks 0, INSUFFICIENT_DATA).
    """
    g = lg.grade_game(str(path), eps=eps, min_ticks=min_ticks)
    outcome = _settled_outcome(path)
    d: List[float] = []
    cluster: List[Any] = []
    if outcome is not None:
        d, cluster = _outcome_losses(path, outcome)
    return {
        "game_id": g.get("game_id", path.stem),
        "mean_clv": float(g.get("mean_clv", 0.0)),
        "n_ticks": int(g.get("n_ticks_scored", 0)),
        "verdict": g.get("verdict", "INSUFFICIENT_DATA"),
        "outcome": outcome,
        "settle_ts": _settle_ts(path),
        "d": d,
        "cluster": cluster,
    }


# --------------------------------------------------------------------------------------- #
# clustered bootstrap CI on per-game mean CLV                                             #
# --------------------------------------------------------------------------------------- #
def _cluster_bootstrap_ci(per_game_clv: Sequence[float], *,
                          iters: int = _BOOTSTRAP_ITERS,
                          seed: int = 12345) -> Tuple[float, float]:
    """95% CI for the pooled mean CLV by resampling GAMES (the cluster) with replacement.

    Game-clustered: each draw resamples whole games, so correlated within-game ticks do not
    inflate the apparent precision. Returns (lo, hi); a single game -> (mean, mean) (no spread,
    forcing the caller to INSUFFICIENT_DATA rather than a fake CI).
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
# the pool                                                                                #
# --------------------------------------------------------------------------------------- #
def aggregate_grade(grade_dir: Optional[Path] = None, *,
                    sport: Optional[str] = None,
                    paths: Optional[Sequence[Path]] = None,
                    eps: float = EPS_DEFAULT,
                    alpha: float = ALPHA_DEFAULT,
                    min_games: int = MIN_GAMES,
                    min_total_ticks: int = MIN_TOTAL_TICKS,
                    min_ticks: int = ic.MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Pool MANY settled games into ONE honest CLV/calibration verdict. NEVER raises.

    Discovers (or takes injected) per-game grade files, grades each via the leak-free
    live_grade.grade_game, then pools: a game-clustered bootstrap CI on per-game mean CLV
    (arm A) AND a game-clustered DM on per-state OUTCOME-Brier (arm B). Returns a dict with
    pool_verdict in {BEAT, MATCH, BEHIND, INSUFFICIENT_DATA}, units='probability',
    edge_claimed=False, and NO $ field. See module docstring for the exact verdict logic.
    """
    files = list(paths) if paths is not None else discover_grade_files(grade_dir, sport)
    games = [grade_one(Path(p), eps=eps, min_ticks=min_ticks) for p in files]

    # Pool only games with at least one scored tick (a 0-tick game is not evidence).
    scored = [g for g in games if g["n_ticks"] > 0]
    n_games = len(scored)
    total_ticks = sum(g["n_ticks"] for g in scored)
    per_game_clv = [g["mean_clv"] for g in scored]
    pooled_mean_clv = sum(per_game_clv) / n_games if n_games else 0.0

    # CLV-over-time series (per-game CLV ordered by settle time) -- numbers only, for the UI.
    ordered = sorted(scored, key=lambda g: (str(g["settle_ts"]), str(g["game_id"])))
    clv_over_time = [{"game_id": g["game_id"], "settle_ts": g["settle_ts"],
                      "mean_clv": round(g["mean_clv"], 6), "n_ticks": g["n_ticks"]}
                     for g in ordered]

    clv_lo, clv_hi = _cluster_bootstrap_ci(per_game_clv)

    # OUTCOME arm: pool per-state OUTCOME-Brier loss diffs across games WITH a settled outcome.
    d_all: List[float] = []
    cl_all: List[Any] = []
    n_settled_games = 0
    for g in scored:
        if g["outcome"] is not None and g["d"]:
            d_all.extend(g["d"])
            cl_all.extend(g["cluster"])
            n_settled_games += 1
    has_outcome = n_settled_games >= 2 and len(set(cl_all)) >= 2
    if has_outcome:
        dm = diebold_mariano(d_all, cl_all)
        dm_mean_diff = dm.mean_diff
        dm_p = dm.p_value
        dm_clusters = dm.n_clusters
        outcome_beat = (dm_mean_diff > 0.0) and (dm_p < float(alpha))
    else:
        dm_mean_diff = 0.0
        dm_p = 1.0
        dm_clusters = len(set(cl_all))
        outcome_beat = False

    # --- verdict (honest, two-arm) ---
    enough = (n_games >= int(min_games)) and (total_ticks >= int(min_total_ticks))
    if not enough or not has_outcome:
        verdict = "INSUFFICIENT_DATA"
    elif pooled_mean_clv < -eps:
        verdict = "BEHIND"
    else:
        clv_beat = (pooled_mean_clv > eps) and (clv_lo > 0.0)
        verdict = "BEAT" if (clv_beat and outcome_beat) else "MATCH"

    return {
        "pool_verdict": verdict,
        "n_games": int(n_games),
        "n_settled_games": int(n_settled_games),
        "total_ticks_scored": int(total_ticks),
        "pooled_mean_clv": float(pooled_mean_clv),
        "clv_ci95": [float(clv_lo), float(clv_hi)],
        "outcome_dm_mean_diff": float(dm_mean_diff),
        "outcome_dm_p": float(dm_p),
        "outcome_dm_n_clusters": int(dm_clusters),
        "outcome_arm_available": bool(has_outcome),
        "clv_over_time": clv_over_time,
        "per_game": [{"game_id": g["game_id"], "mean_clv": round(g["mean_clv"], 6),
                      "n_ticks": g["n_ticks"], "outcome": g["outcome"],
                      "verdict": g["verdict"]} for g in scored],
        "min_games": int(min_games),
        "min_total_ticks": int(min_total_ticks),
        # vs_close is the REPLICATED-PROVEN yardstick. A single pooled window is NOT a
        # vs_close proof (no >=2-corpus cross-replication, no clustered-DM p<0.05). It
        # therefore STAYS UNPROVEN here regardless of pool_verdict; the ONLY path to a
        # real upgrade is improve.clv_corpus_inject.maybe_vs_close_upgrade (gate_ship AND
        # n_rep>=2 AND close-corpus clustered DM p<0.05). pool_verdict is reported below as
        # a SEPARATE single-window MEASUREMENT, never a vs_close claim.
        "vs_close": "UNPROVEN",
        "pool_verdict_label": ("POOL_BEAT_SINGLE_WINDOW" if verdict == "BEAT"
                               else verdict),
        "label": "measurement only -- CLV/calibration in probability space, no currency",
        "units": "probability",
        "edge_claimed": False,
    }


def format_report(pool: Dict[str, Any]) -> str:
    """ASCII summary of the pooled verdict. No $ figure -- CLV is probability space."""
    lo, hi = pool.get("clv_ci95", [0.0, 0.0])
    lines = [
        "=== Multi-game aggregate CLV/calibration grade (offline, honest) ===",
        "pool_verdict   : %s" % pool.get("pool_verdict"),
        "n_games        : %d  (settled w/ outcome: %d)" % (
            pool.get("n_games", 0), pool.get("n_settled_games", 0)),
        "total_ticks    : %d" % pool.get("total_ticks_scored", 0),
        "pooled_mean_clv: %+.5f  (probability space; + = beat the close)" % (
            pool.get("pooled_mean_clv", 0.0)),
        "clv_ci95       : [%+.5f, %+.5f]  (game-clustered bootstrap)" % (lo, hi),
        "outcome_dm     : mean_diff=%+.5f p=%.4f clusters=%d  (+ = model beats close)" % (
            pool.get("outcome_dm_mean_diff", 0.0), pool.get("outcome_dm_p", 1.0),
            pool.get("outcome_dm_n_clusters", 0)),
        "units          : probability (CLV / calibration only -- never dollars)",
        "edge_claimed   : False",
    ]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_GRADE_DIR", "MIN_GAMES", "MIN_TOTAL_TICKS",
    "discover_grade_files", "grade_one", "aggregate_grade", "format_report",
]
