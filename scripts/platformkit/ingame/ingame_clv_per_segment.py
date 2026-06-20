"""scripts.platformkit.ingame.ingame_clv_per_segment -- per-segment in-game CLV aggregator.

Extends ingame_clv_aggregate by splitting the CLV readout across period/inning/half buckets
so we measure WHERE in the game live re-pricing beats the close vs INSUFFICIENT_DATA.

Segment labels: Q1..Q4/QOT (NBA period), I1..I9 (MLB inning), H1/H2 (soccer minute/half),
S1..S5 (tennis set). Rows with unresolvable state -> UNK bucket.

Per-segment verdict (CLV arm, honest -- mirrors ingame_clv_aggregate):
  >= min_games AND >= min_ticks_per_seg:
    BEAT  : pooled_mean > +eps AND game-clustered bootstrap CI lower > 0.
    BEHIND: pooled_mean < -eps.
    MATCH : within noise.
  Below either threshold OR empty -> INSUFFICIENT_DATA (never fabricated).

HONESTY: UNITS/PROBABILITY only. No $ / roi / pnl. edge_claimed always False.
INVARIANTS: <=300 LOC; ASCII only; no network at import; no data-registry write.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_clv_per_segment.py -q
"""
from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame import live_grade as lg
from scripts.platformkit.forward_capture import inplay_clv_replay as ic

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"

MIN_GAMES_PER_SEG: int = 3
MIN_TICKS_PER_SEG: int = 10
EPS_DEFAULT: float = ic.EPS_DEFAULT
_BOOTSTRAP_ITERS: int = 2_000
_SEGMENT_ORDER = [
    "Q1", "Q2", "Q3", "Q4", "QOT",
    "H1", "H2",
    "I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9",
    "S1", "S2", "S3", "S4", "S5",
    "UNK",
]

_KV_RE = re.compile(r"(\w+)=(\S+)")


def _parse_kv(s: str) -> Dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _KV_RE.finditer(s)}


def _infer_segment(sport: str, state_summary: str) -> str:
    """Map state_summary string -> segment bucket label. Never raises; unknown -> UNK."""
    if not state_summary:
        return "UNK"
    kv = _parse_kv(state_summary)

    # Basketball: period 1-4, 5+ -> overtime.
    if "period" in kv:
        try:
            p = int(kv["period"])
        except ValueError:
            return "UNK"
        if p <= 0:
            return "UNK"
        return "Q%d" % p if p <= 4 else "QOT"

    # Baseball: inning 1-9 (>=9 clamped to I9).
    if "inning" in kv:
        try:
            inn = min(max(int(kv["inning"]), 1), 9)
        except ValueError:
            return "UNK"
        return "I%d" % inn

    # Soccer via minute (<=45 = H1, >45 = H2).
    if "minute" in kv:
        try:
            m = float(kv["minute"])
        except ValueError:
            return "UNK"
        return "H1" if m <= 45 else "H2"

    # Soccer via explicit half field.
    if "half" in kv:
        h = kv["half"].strip().lower()
        if h in ("1", "top", "first"):
            return "H1"
        if h in ("2", "bottom", "second"):
            return "H2"
        return "UNK"

    # Tennis set.
    if "set" in kv:
        try:
            s = int(kv["set"])
        except ValueError:
            return "UNK"
        return "S%d" % s if 1 <= s <= 5 else "UNK"

    return "UNK"


def _load_segment_pairs(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Read grade file, bucket valid tick rows by segment label. Never raises."""
    rows = lg._load_pairs(path)
    if not rows:
        return {}
    sport = str(rows[0].get("sport", ""))
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        seg = _infer_segment(sport, str(r.get("state_summary", "")))
        buckets.setdefault(seg, []).append(r)
    return buckets


def _clv_for_rows(rows: List[Dict[str, Any]]) -> Tuple[float, int]:
    """Per-game mean CLV within a segment. Close (last tick) excluded. Returns (mean, n)."""
    if len(rows) < 2:
        return (0.0, 0)
    scored = rows[:-1]
    clvs = [r["model_prob"] - r["market_prob"] for r in scored]
    return (sum(clvs) / len(clvs), len(clvs))


def _ci(per_game_clv: List[float], *, seed: int = 42) -> Tuple[float, float]:
    """Game-clustered bootstrap 95% CI for pooled mean CLV."""
    g = len(per_game_clv)
    if g == 0:
        return (0.0, 0.0)
    if g == 1:
        return (per_game_clv[0], per_game_clv[0])
    rng = random.Random(seed)
    means = sorted(
        sum(per_game_clv[rng.randrange(g)] for _ in range(g)) / g
        for _ in range(_BOOTSTRAP_ITERS)
    )
    lo = means[int(0.025 * (_BOOTSTRAP_ITERS - 1))]
    hi = means[int(0.975 * (_BOOTSTRAP_ITERS - 1))]
    return (lo, hi)


def _verdict_for_seg(
    per_game_clv: List[float], total_ticks: int, n_games: int, *,
    eps: float = EPS_DEFAULT,
    min_games: int = MIN_GAMES_PER_SEG,
    min_ticks: int = MIN_TICKS_PER_SEG,
) -> Tuple[str, float, float, float]:
    """(verdict, pooled_mean, ci_lo, ci_hi) for one segment bucket."""
    if n_games < min_games or total_ticks < min_ticks or not per_game_clv:
        return ("INSUFFICIENT_DATA", 0.0, 0.0, 0.0)
    pooled = sum(per_game_clv) / len(per_game_clv)
    ci_lo, ci_hi = _ci(per_game_clv)
    if pooled < -eps:
        v = "BEHIND"
    elif pooled > eps and ci_lo > 0.0:
        v = "BEAT"
    else:
        v = "MATCH"
    return (v, pooled, ci_lo, ci_hi)


def _discover(grade_dir: Optional[Path], sport: Optional[str]) -> List[Path]:
    base = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    if not base.is_dir():
        return []
    sub_dirs: List[Path] = (
        [base / sport.lower()] if sport else
        [d for d in sorted(base.iterdir()) if d.is_dir()]
    )
    out: List[Path] = []
    for d in sub_dirs:
        if d.is_dir():
            out.extend(f for f in sorted(d.glob("*.jsonl")) if not f.name.startswith("_"))
    return out


def _build_seg_row(verd: str, pooled: float, ci_lo: float, ci_hi: float,
                   n_games: int, total_ticks: int) -> Dict[str, Any]:
    return {
        "verdict": verd,
        "n_games": n_games,
        "total_ticks": total_ticks,
        "pooled_mean_clv": round(float(pooled), 6),
        "clv_ci95": [round(float(ci_lo), 6), round(float(ci_hi), 6)],
        "units": "probability",
        "edge_claimed": False,
    }


def aggregate_by_segment(
    grade_dir: Optional[Path] = None, *,
    sport: Optional[str] = None,
    paths: Optional[Sequence[Path]] = None,
    eps: float = EPS_DEFAULT,
    min_games: int = MIN_GAMES_PER_SEG,
    min_ticks_per_seg: int = MIN_TICKS_PER_SEG,
) -> Dict[str, Any]:
    """Pool settled grade files into per-segment CLV verdicts. NEVER raises.

    Each segment bucket (Q1..Q4, H1/H2, I1..I9, ...) gets its own pooled CLV + verdict.
    Below min_games or min_ticks_per_seg -> INSUFFICIENT_DATA (never fabricated).
    No $ field; edge_claimed always False.
    """
    files = list(paths) if paths is not None else _discover(grade_dir, sport)

    # Accumulate per-game CLV per segment: seg -> {game_id: (mean_clv, n_scored)}.
    seg_games: Dict[str, Dict[str, Tuple[float, int]]] = {}
    for p in files:
        for seg, rows in _load_segment_pairs(Path(p)).items():
            mean_clv, n_scored = _clv_for_rows(rows)
            if n_scored >= 1:
                seg_games.setdefault(seg, {})[Path(p).stem] = (mean_clv, n_scored)

    def _seg_out(seg: str) -> Dict[str, Any]:
        game_map = seg_games.get(seg, {})
        clvs = [v[0] for v in game_map.values()]
        ticks = sum(v[1] for v in game_map.values())
        verd, pooled, ci_lo, ci_hi = _verdict_for_seg(
            clvs, ticks, len(clvs), eps=eps, min_games=min_games, min_ticks=min_ticks_per_seg,
        )
        return _build_seg_row(verd, pooled, ci_lo, ci_hi, len(clvs), ticks)

    segments_out: Dict[str, Any] = {seg: _seg_out(seg) for seg in _SEGMENT_ORDER}
    for seg in sorted(seg_games):
        if seg not in segments_out:
            segments_out[seg] = _seg_out(seg)

    return {
        "segments": segments_out,
        "segment_order": _SEGMENT_ORDER,
        "n_files": len(files),
        "units": "probability",
        "edge_claimed": False,
        "label": "per-segment in-game CLV -- probability space only, no currency",
        "min_games_per_seg": min_games,
        "min_ticks_per_seg": min_ticks_per_seg,
    }


def format_report(result: Dict[str, Any]) -> str:
    """ASCII summary of per-segment verdicts. No $ -- CLV is probability space."""
    segs = result.get("segments", {})
    order = result.get("segment_order", sorted(segs))
    lines = [
        "=== Per-segment in-game CLV (honest) ===",
        "n_files : %d" % result.get("n_files", 0),
        "%-6s  %-18s  %8s  %7s  %s" % ("SEG", "VERDICT", "N_GAMES", "TICKS",
                                        "pooled_mean_clv"),
    ]
    for seg in order:
        if seg not in segs:
            continue
        s = segs[seg]
        lines.append("%-6s  %-18s  %8d  %7d  %+.5f" % (
            seg, s["verdict"], s["n_games"], s["total_ticks"], s["pooled_mean_clv"],
        ))
    lines += ["units        : probability (CLV only -- never dollars)", "edge_claimed : False"]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_GRADE_DIR", "MIN_GAMES_PER_SEG", "MIN_TICKS_PER_SEG", "EPS_DEFAULT",
    "aggregate_by_segment", "format_report",
]
