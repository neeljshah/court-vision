"""scripts.platformkit.ingame.prospective_scoreboard -- FORWARD-ONLY checkpoint grader.

WHY
---
Every "beats the market" read so far came from HISTORICAL capture corpora, where
two artifacts bind: the actual-played proxy (newsprior) and the state-lag skew
(market ticks median ~20-26s fresher than the graded state). The durable claim
can only come from rows captured FORWARD by the live paper chain, where model
and market are read in the same tick. This module grades exactly that: per
(sport, checkpoint), the paired Brier delta of the FROZEN live-served model
number (grade rows' model_prob, computed as-of the tick, never refit here)
against the devigged market prob captured in the same row -- on games whose
capture began AFTER this module's own pre-registration stamp. It NEVER grades a
game captured before its own code existed.

PREREGISTRATION (binding): PREREGISTERED_AT below is this module's birth stamp.
A game whose FIRST captured tick predates it is excluded -- no retroactive
cherry-picking, ever. The stamp is a constant, not an argument.

VERDICT DISCIPLINE (binding): per (sport, checkpoint) the verdict is
  PENDING                    -- n < MIN_GAMES, or the 95% CI includes 0
  BEATS_MARKET_PROVISIONAL   -- CI lower bound > 0 (model Brier strictly lower),
                                still PROVISIONAL until an independent later
                                window replicates it
  BEHIND_MARKET              -- CI upper bound < 0
"provisionally beats" converts to "beats" ONLY when the CI earns it -- the
artifact says PENDING until then. edge_claimed is always False; UNITS /
probability only; no $ / ROI field anywhere.

SOURCES (read-only): data/cache/ingame_grade/<sport>/<game_id>.jsonl -- tick
rows {ts, model_prob, market_prob (home side), state_summary "k=v ..."} plus a
settle row {settled: true, home_win}. state_summary carries period/clock
(basketball) or inning/half (mlb); rows missing the keys a checkpoint needs are
skipped honestly.

ARTIFACTS: data/cache/benchmarks/prospective_scoreboard.json (current state,
overwritten) + one line per run appended to prospective_scoreboard_history.jsonl
(the daily accrual trail the pod cycle builds).

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network; no
data/registry writes; no flag flips; reuses run_mlb._bootstrap_ci (b=3000,
seed=0) -- same CI convention as every other benchmark in crps_market/.

CLI:  python -m scripts.platformkit.ingame.prospective_scoreboard
Test: python -m pytest tests/platformkit/ingame/test_prospective_scoreboard.py -q
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.benchmarks.crps_market.run_mlb import _bootstrap_ci

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_OUT = _REPO_ROOT / "data" / "cache" / "benchmarks" / "prospective_scoreboard.json"
DEFAULT_HISTORY = DEFAULT_OUT.with_name("prospective_scoreboard_history.jsonl")

# Birth stamp of this module -- games first captured before this are NEVER graded.
PREREGISTERED_AT = "2026-07-19T04:30:00Z"

MIN_GAMES = 30  # below this a checkpoint stays PENDING regardless of the point estimate

# Checkpoint predicates read the parsed state_summary dict. First tick row
# satisfying the predicate anchors the checkpoint: state AT-or-just-AFTER the
# boundary (Q2 open). NOTE this is the OPPOSITE side of the boundary from
# ingame_nba_winprob.checkpoint_row's last-before-anchor convention -- fine
# here (model+market read in the same tick, self-consistent), but do not
# compare deltas across the two corpora without accounting for it.
# clock counts DOWN within a period (seconds remaining).
_BASKETBALL = [
    ("end_q1", lambda s: s.get("period", 0) >= 2),
    ("halftime", lambda s: s.get("period", 0) >= 3),
    ("end_q3", lambda s: s.get("period", 0) >= 4),
    ("q4_under5", lambda s: s.get("period", 0) >= 4 and s.get("clock", 1e9) <= 300),
]
CHECKPOINTS: Dict[str, List[Tuple[str, Any]]] = {
    "nba": _BASKETBALL,
    "wnba": _BASKETBALL,
    "mlb": [
        ("end_inn3", lambda s: s.get("inning", 0) >= 4),
        ("end_inn6", lambda s: s.get("inning", 0) >= 7),
        ("end_inn8", lambda s: s.get("inning", 0) >= 9),
    ],
    # soccer_intl state_summary carries minute (grade rows from the capture
    # chain); model is the validated live predictor. Added 2026-07-19 for
    # evidence throughput -- same PENDING-until-CI discipline as every sport.
    "soccer_intl": [
        ("min30", lambda s: s.get("minute", 0) >= 30),
        ("halftime", lambda s: s.get("minute", 0) >= 46),
        ("min75", lambda s: s.get("minute", 0) >= 75),
    ],
}


def parse_state_summary(text: Any) -> Dict[str, float]:
    """"home_score=4.0 clock=432.0 period=1" -> {"home_score": 4.0, ...}.
    Non-numeric values (half=bottom, count=2-2) are skipped -- checkpoints
    only need numeric period/clock/inning. Never raises."""
    out: Dict[str, float] = {}
    if not isinstance(text, str):
        return out
    for tok in text.split():
        if "=" not in tok:
            continue
        k, _, v = tok.partition("=")
        try:
            out[k] = float(v)
        except ValueError:
            continue
    return out


def _norm_ts(ts: str) -> str:
    """Normalize an ISO timestamp for safe lexicographic compare/sort: strip a
    Z/offset suffix and any fractional seconds -> 'YYYY-MM-DDTHH:MM:SS'."""
    t = ts.replace("Z", "").split("+")[0]
    return t.split(".")[0]


def _prob01(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if 0.0 <= f <= 1.0 else None


def load_game(path: Path) -> Optional[Dict[str, Any]]:
    """One grade file -> {first_ts, y, ticks:[(ts, state, model_p, market_p)]}.
    None when the file has no settled outcome or no valid tick. Never raises."""
    ticks: List[Tuple[str, Dict[str, float], float, float]] = []
    y: Optional[int] = None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("settled"):
                    hw = row.get("home_win")
                    if hw in (0, 1, 0.0, 1.0):
                        y = int(hw)
                    continue
                mp, kp = _prob01(row.get("model_prob")), _prob01(row.get("market_prob"))
                ts = str(row.get("ts") or "")
                if mp is None or kp is None or not ts:
                    continue
                ticks.append((_norm_ts(ts), parse_state_summary(row.get("state_summary")), mp, kp))
    except OSError:
        return None
    if y is None or not ticks:
        return None
    ticks.sort(key=lambda t: t[0])
    return {"first_ts": ticks[0][0], "y": y, "ticks": ticks}


def checkpoint_pairs(game: Dict[str, Any], sport: str) -> Dict[str, Tuple[float, float]]:
    """{checkpoint: (model_p, market_p)} -- the FIRST tick satisfying each
    predicate. A checkpoint no tick reaches is simply absent (honest gap)."""
    out: Dict[str, Tuple[float, float]] = {}
    for label, pred in CHECKPOINTS.get(sport, []):
        for _ts, state, mp, kp in game["ticks"]:
            if pred(state):
                out[label] = (mp, kp)
                break
    return out


def _verdict(deltas: List[float]) -> Tuple[str, List[float]]:
    ci = _bootstrap_ci(deltas) if deltas else [0.0, 0.0]
    if len(deltas) < MIN_GAMES:
        return "PENDING", ci
    if ci[0] > 0:
        return "BEATS_MARKET_PROVISIONAL", ci
    if ci[1] < 0:
        return "BEHIND_MARKET", ci
    return "PENDING", ci


def run(grade_dir: Optional[Path] = None, *, preregistered_at: str = PREREGISTERED_AT,
        now: Optional[datetime] = None) -> Dict[str, Any]:
    """Grade every eligible settled game forward of *preregistered_at*."""
    base = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    nowdt = now or datetime.now(timezone.utc)
    sports: Dict[str, Any] = {}
    n_excluded_pre_prereg = 0
    for sport in sorted(CHECKPOINTS):
        sdir = base / sport
        per_cp: Dict[str, List[float]] = {c[0]: [] for c in CHECKPOINTS[sport]}
        n_games = 0
        for f in sorted(sdir.glob("*.jsonl")) if sdir.is_dir() else []:
            if f.name.startswith("_"):
                continue
            game = load_game(f)
            if game is None:
                continue
            if game["first_ts"] < _norm_ts(preregistered_at):
                n_excluded_pre_prereg += 1
                continue
            pairs = checkpoint_pairs(game, sport)
            if not pairs:
                continue
            n_games += 1
            y = game["y"]
            for label, (mp, kp) in pairs.items():
                # paired Brier delta, positive = model beat the market at this checkpoint
                per_cp[label].append((kp - y) ** 2 - (mp - y) ** 2)
        cps: Dict[str, Any] = {}
        for label, deltas in per_cp.items():
            verdict, ci = _verdict(deltas)
            cps[label] = {
                "n": len(deltas),
                "delta_brier_mean": round(sum(deltas) / len(deltas), 4) if deltas else None,
                "delta_95ci": ci if deltas else None,
                "verdict": verdict,
            }
        sports[sport] = {"n_settled_games_graded": n_games, "checkpoints": cps}
    return {
        "as_of": nowdt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preregistered_at": preregistered_at,
        "n_excluded_pre_prereg": n_excluded_pre_prereg,
        "min_games": MIN_GAMES,
        "sports": sports,
        "edge_claimed": False,
        "honest_note": (
            "FORWARD-ONLY prospective grading: only games whose first captured tick "
            "postdates this module's preregistration stamp are ever graded. Frozen "
            "live-served model_prob vs same-tick devigged market prob; paired Brier "
            "delta per checkpoint, bootstrap CI (b=3000, seed=0). Verdicts stay "
            "PENDING until n>=%d AND the CI excludes 0; BEATS_MARKET_PROVISIONAL "
            "remains provisional until replicated on an independent later window. "
            "UNITS/probability only -- no $ / ROI anywhere." % MIN_GAMES
        ),
    }


def write_artifacts(doc: Dict[str, Any], out: Optional[Path] = None,
                    history: Optional[Path] = None) -> Path:
    out_path = Path(out) if out is not None else DEFAULT_OUT
    hist_path = Path(history) if history is not None else (
        out_path.with_name(out_path.stem + "_history.jsonl"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    summary = {"as_of": doc["as_of"],
               "sports": {s: {c: {"n": v["n"], "verdict": v["verdict"],
                                  "delta": v["delta_brier_mean"]}
                              for c, v in body["checkpoints"].items()}
                          for s, body in doc["sports"].items()}}
    with hist_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=True) + "\n")
    return out_path


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grade-dir", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    doc = run(Path(a.grade_dir) if a.grade_dir else None)
    path = write_artifacts(doc, Path(a.out) if a.out else None)
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    print("wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["PREREGISTERED_AT", "MIN_GAMES", "CHECKPOINTS", "parse_state_summary",
           "load_game", "checkpoint_pairs", "run", "write_artifacts"]
