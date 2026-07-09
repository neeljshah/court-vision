"""scripts.platformkit.ingame.state_bucket_benchmark -- MLB per-state-bucket
MODEL-vs-MARKET calibration benchmark (goal 1b/1c). Is our in-game model better OR
worse calibrated than the LIVE Kalshi market price, by game state (margin x phase)?

DATA REALITY (read before editing): data/cache/ingame_grade/mlb/*.jsonl has TWO
DISJOINT id schemes -- ~185 files keyed by KALSHI TICKER (KXMLBGAME-...) carry real
(model_prob, market_prob) ticks but no settle_stamp label (settle_stamp keys by ESPN
numeric id, a different space); ~82 files keyed by ESPN numeric id carry only a settle
stub (state_summary='FINAL') and zero ticks. They never join on game_id, so the
"settled label on the grade file" premise does not hold. Fix (reuse, proven in
ingame_outcome_verdict_2026_07_01): MlbOutcomeResolver parses the Kalshi ticker (date +
away/home abbrs) and joins data/domains/mlb/espn_boxscores.parquet for home_win.
Unresolvable/unparseable games are DROPPED, never a fabricated label.

BUCKETING (adaptation): rows carry inning/half/score, not frac_elapsed (absent in this
schema) -- phase is an INNING-GROUP, not a time tercile:
  phase  : early (inning 1-3) | mid (4-6) | late (7+) | unknown (no inning)
  margin : trailing_big (home-away<=-3) | trailing (-2..-1) | tied (0)
          | leading (+1..+2) | leading_big (>=+3)   [home perspective; PAIR_SIDE='home']
A tick without a parseable home_score/away_score is dropped, never guessed.

METRICS per bucket AND pooled, MODEL vs MARKET separately against the resolved
home_win label: n_ticks, n_games, Brier/log-loss/ECE(10-bin) (eval_gate.scoring,
kernel-backed). Plus mean |model-market| and a GAME-CLUSTERED bootstrap verdict on the
paired per-tick Brier diff (market_brier - model_brier; positive = model better).
Buckets with < MIN_GAMES games -> INSUFFICIENT_DATA, never FAILED.

HONESTY (binding): calibration measurement only, no $/ROI/edge field. edge_claimed is
always False. A market-copy model scores delta==0 everywhere (correctness anchor).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no network at
import; never writes data/registry/; never flips a flag; never edits live_grade.py /
ingame_outcome_label.py / eval_gate/scoring.py; data/cache/ingame_grade is READ-ONLY here.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_state_bucket_benchmark.py -q
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.eval_gate.scoring import brier, ece, log_loss
from scripts.platformkit.ingame import live_grade as lg
from scripts.platformkit.ingame.ingame_clv_aggregate import discover_grade_files
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_state_bucket_benchmark.json"

MIN_GAMES = 8            # honest floor: fewer games = INSUFFICIENT_DATA, never a verdict
EPS_BRIER = 0.001         # deadband on the pooled-per-game Brier-diff CI
_BOOTSTRAP_ITERS = 2000

_MARGIN_BUCKETS: Tuple[Tuple[str, float, float], ...] = (
    ("trailing_big", -999.0, -3.0),
    ("trailing", -2.0, -1.0),
    ("tied", 0.0, 0.0),
    ("leading", 1.0, 2.0),
    ("leading_big", 3.0, 999.0),
)
_PHASE_BUCKETS: Tuple[Tuple[str, int, int], ...] = (
    ("early", 1, 3),
    ("mid", 4, 6),
    ("late", 7, 99),
)

# -- state_summary parsing + bucketing --
def _parse_state_summary(s: str) -> Dict[str, float]:
    """'home_score=7 away_score=1 inning=5 half=bottom ...' -> {k: float}. Never raises."""
    out: Dict[str, float] = {}
    for tok in str(s or "").split():
        if "=" not in tok:
            continue
        k, _, v = tok.partition("=")
        try:
            out[k] = float(v)
        except ValueError:
            continue
    return out

def margin_bucket(home_score: float, away_score: float) -> str:
    margin = home_score - away_score
    for name, lo, hi in _MARGIN_BUCKETS:
        if lo <= margin <= hi:
            return name
    return "leading_big" if margin > 0 else "trailing_big"

def phase_bucket(inning: Optional[float]) -> str:
    if inning is None:
        return "unknown"
    for name, lo, hi in _PHASE_BUCKETS:
        if lo <= inning <= hi:
            return name
    return "unknown"

# -- loading --
def load_bucketed_ticks(grade_dir: Optional[Path] = None,
                        resolver: Optional[MlbOutcomeResolver] = None
                        ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Read every mlb grade file, keep resolvable+bucketable ticks. Never raises.

    Returns (ticks, counts) where each tick carries {game_id, bucket, model_prob,
    market_prob, outcome}. counts = {n_files, n_games_with_pairs, n_resolved, n_unresolved}.
    """
    res = resolver if resolver is not None else MlbOutcomeResolver()
    files = discover_grade_files(grade_dir, sport="mlb")
    ticks: List[Dict[str, Any]] = []
    counts = {"n_files": len(files), "n_games_with_pairs": 0, "n_resolved": 0,
             "n_unresolved": 0, "n_resolved_but_unbucketable": 0}
    for path in files:
        try:
            pairs = lg._load_pairs(path)
        except Exception as exc:  # noqa: BLE001 -- one bad file is not a crash
            logger.debug("load_bucketed_ticks: %s failed: %s", path, exc)
            continue
        if not pairs:
            continue
        counts["n_games_with_pairs"] += 1
        gid = str(pairs[0].get("game_id", path.stem))
        home_win = res.home_win(gid)
        if home_win is None:
            counts["n_unresolved"] += 1
            continue
        counts["n_resolved"] += 1
        n_before = len(ticks)
        for r in pairs:
            fields = _parse_state_summary(r.get("state_summary"))
            if "home_score" not in fields or "away_score" not in fields:
                continue
            mb = margin_bucket(fields["home_score"], fields["away_score"])
            pb = phase_bucket(fields.get("inning"))
            ticks.append({
                "game_id": gid, "bucket": "%s|%s" % (pb, mb),
                "model_prob": float(r["model_prob"]), "market_prob": float(r["market_prob"]),
                "outcome": float(home_win),
            })
        if len(ticks) == n_before:
            # Older captures wrote state_summary='live' (no score/inning fields yet);
            # a resolved game with zero parseable state is dropped, never guessed.
            counts["n_resolved_but_unbucketable"] += 1
    return ticks, counts

# -- metrics + cluster-bootstrap verdict --
def _cluster_bootstrap_ci(per_game_delta: Sequence[float], *,
                          iters: int = _BOOTSTRAP_ITERS, seed: int = 42) -> Tuple[float, float]:
    """95% CI for the pooled mean Brier-diff by resampling GAMES with replacement."""
    vals = [float(v) for v in per_game_delta]
    g = len(vals)
    if g == 0:
        return (0.0, 0.0)
    if g == 1:
        return (vals[0], vals[0])
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample = [vals[rng.randrange(g)] for _ in range(g)]
        means.append(sum(sample) / g)
    means.sort()
    return (means[int(0.025 * (iters - 1))], means[int(0.975 * (iters - 1))])

def _score_bucket(ticks: List[Dict[str, Any]], *,
                  min_games: int = MIN_GAMES, eps: float = EPS_BRIER) -> Dict[str, Any]:
    """Model vs market metrics + game-clustered paired-Brier verdict for one tick group."""
    game_ids = sorted(set(t["game_id"] for t in ticks))
    n_games = len(game_ids)
    model_p = [t["model_prob"] for t in ticks]
    market_p = [t["market_prob"] for t in ticks]
    y = [t["outcome"] for t in ticks]
    gap = sum(abs(m - k) for m, k in zip(model_p, market_p)) / len(ticks) if ticks else 0.0

    per_game_delta: List[float] = []
    for gid in game_ids:
        gt = [t for t in ticks if t["game_id"] == gid]
        d = [(k - p) ** 2 - (m - p) ** 2 for m, k, p in
             zip((t["model_prob"] for t in gt), (t["market_prob"] for t in gt),
                 (t["outcome"] for t in gt))]
        per_game_delta.append(sum(d) / len(d))

    ci_lo, ci_hi = _cluster_bootstrap_ci(per_game_delta)
    if n_games < min_games:
        verdict = "INSUFFICIENT_DATA"
    elif ci_lo > eps:
        verdict = "MODEL_AHEAD"
    elif ci_hi < -eps:
        verdict = "MODEL_BEHIND"
    else:
        verdict = "MATCH"

    return {
        "n_ticks": len(ticks), "n_games": n_games,
        "model": {"brier": brier(model_p, y), "log_loss": log_loss(model_p, y),
                 "ece": ece(model_p, y)} if ticks else None,
        "market": {"brier": brier(market_p, y), "log_loss": log_loss(market_p, y),
                  "ece": ece(market_p, y)} if ticks else None,
        "mean_abs_gap": gap,
        "brier_delta_market_minus_model": (sum(per_game_delta) / n_games) if n_games else 0.0,
        "brier_delta_ci95": [ci_lo, ci_hi],
        "verdict": verdict,
    }

# -- top-level build --
def build_benchmark(grade_dir: Optional[Path] = None,
                    resolver: Optional[MlbOutcomeResolver] = None) -> Dict[str, Any]:
    """Assemble the full per-bucket + pooled benchmark doc. Never raises."""
    ticks, counts = load_bucketed_ticks(grade_dir, resolver)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for t in ticks:
        buckets.setdefault(t["bucket"], []).append(t)

    bucket_rows = []
    for name in sorted(buckets):
        row = _score_bucket(buckets[name])
        row["bucket"] = name
        bucket_rows.append(row)
    pooled = _score_bucket(ticks)

    doc: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "mlb",
        "benchmark": "live_kalshi_market_price",
        "binning": {
            "phase": "inning-group (early 1-3, mid 4-6, late 7+; no frac_elapsed in this "
                     "schema, adapted from inning)",
            "margin": "home_score-away_score: trailing_big<=-3, trailing -2..-1, tied 0, "
                     "leading +1..+2, leading_big>=+3",
        },
        "n_grade_files_mlb": counts["n_files"],
        "n_games_with_ticks": counts["n_games_with_pairs"],
        "n_games_outcome_resolved": counts["n_resolved"],
        "n_games_outcome_unresolved": counts["n_unresolved"],
        "n_games_resolved_but_unbucketable": counts["n_resolved_but_unbucketable"],
        "min_games_for_verdict": MIN_GAMES,
        "buckets": bucket_rows,
        "pooled": pooled,
        "units": "probability (Brier/log-loss/ECE; no dollars)",
        "edge_claimed": False,
        "honest_note": ("Calibration/benchmark measurement only vs the LIVE market price, "
                        "not a devigged close. Outcomes resolved via Kalshi-ticker to "
                        "ESPN-boxscore join (ingame_outcome_label.MlbOutcomeResolver); "
                        "unresolved games are dropped, never fabricated. No $/ROI/edge claim."),
        "calibration_scoreboard": {"per_sport": [{
            "sport": "mlb", "method": "mlb_state_bucket_pooled",
            "n": pooled["n_ticks"],
            "baseline_brier": pooled["market"]["brier"] if pooled["market"] else None,
            "improved_brier": pooled["model"]["brier"] if pooled["model"] else None,
            "baseline_ece": pooled["market"]["ece"] if pooled["market"] else None,
            "improved_ece": pooled["model"]["ece"] if pooled["model"] else None,
        }]},
    }
    return doc

def write_benchmark(out_path: Optional[Path] = None,
                    grade_dir: Optional[Path] = None,
                    resolver: Optional[MlbOutcomeResolver] = None,
                    history_path: Optional[Path] = None) -> Dict[str, Any]:
    """Build + atomically write the benchmark JSON; then best-effort scoreboard append.

    scoreboard_history.append_rows reads doc['calibration_scoreboard']['per_sport'] from
    a source file -- our own output doc carries that section, so this is a schema-COMPATIBLE
    append (see scripts/platformkit/scoreboard_history.py), not a reshaped one. A failure to
    append is logged and swallowed (never raises, never distorts the history schema).
    history_path defaults to the REAL data/cache/scoreboard_history.jsonl -- tests MUST
    pass a tmp_path override so synthetic rows never land in production history.
    """
    out = out_path or DEFAULT_OUT_PATH
    doc = build_benchmark(grade_dir, resolver)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    try:
        from scripts.platformkit import scoreboard_history as sh
        sh.append_rows(source_path=out, history_path=history_path)
    except Exception as exc:  # noqa: BLE001 -- history append is best-effort
        logger.debug("write_benchmark: scoreboard_history append skipped: %s", exc)
    return doc

if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({"pooled": result["pooled"], "n_buckets": len(result["buckets"]),
                      "honest_note": result["honest_note"]}, indent=2, ensure_ascii=True))

__all__ = [
    "DEFAULT_GRADE_DIR", "DEFAULT_OUT_PATH", "MIN_GAMES", "EPS_BRIER",
    "margin_bucket", "phase_bucket", "load_bucketed_ticks", "build_benchmark",
    "write_benchmark",
]
