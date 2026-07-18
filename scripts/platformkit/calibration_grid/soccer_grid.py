"""scripts.platformkit.calibration_grid.soccer_grid -- soccer_intl state-bucket
reliability map (calibration only, never a $/ROI/edge claim).

DATA: data/cache/ingame_grade_joined/soccer_intl/*.jsonl (READ-ONLY). Each row
already carries model_prob, market_prob (both cheap -- no subprocess pricing
needed here, unlike nba_grid/mlb_grid), a 3-way settled outcome (1.0 home win
/ 0.5 draw / 0.0 away win), and a state_summary string. minute=N is present
on most rows (reused regex convention from ingame_soccer.py); score is NOT
reliably present in state_summary -- rows without a parseable score fall into
buckets.soccer_bucket's "score_unknown" band, counted honestly, never guessed.

SCORING RULE (binding, stated in honest_note): outcome is scored AS-IS on
P(home win) with draw counted as 0.5 credit (matches ingame_soccer.py's own
convention) -- this is NOT a 3-way Brier, it is the 2-way home-win calibration
question with a draw given partial credit.

n IS THIN (~26 games carry a minute timeline per the scouted context) --
UNDERPOWERED/insufficient is the expected, honest can_price verdict for most
buckets; this ships the harness + honest exclusion counts for forward accrual.

No model-side subprocess pass exists for this grid: model_prob is already on
every row, so "model" here means the SAME model_prob column the market pass
reads, at zero extra cost -- there is no --model-per-bucket flag.

CLI: python -m scripts.platformkit.calibration_grid.soccer_grid
Tests: python -m pytest scripts/platformkit/calibration_grid/test_soccer_grid.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.calibration_grid.buckets import soccer_bucket
from scripts.platformkit.eval_gate.scoring import brier

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade_joined" / "soccer_intl"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "cache" / "calibration_grid" / "soccer_reliability_map.json"

MIN_GAMES = 30
MAX_MODEL_MARKET_GAP = 0.06

_MINUTE_RE = re.compile(r"minute=(\d+)")
_SCORE_RE = re.compile(r"(?:home_score|score_home)=(\d+).*?(?:away_score|score_away)=(\d+)")


def _parse_minute(state_summary: str) -> Optional[float]:
    m = _MINUTE_RE.search(str(state_summary or ""))
    return float(m.group(1)) if m else None


def _parse_score_diff(state_summary: str) -> Optional[float]:
    m = _SCORE_RE.search(str(state_summary or ""))
    return float(m.group(1)) - float(m.group(2)) if m else None


def _credit(outcome: float) -> float:
    """1.0 home win / 0.5 draw / 0.0 away win -- already the P(home win) target."""
    return float(outcome)


def load_with_counts(data_dir: Optional[Path] = None) -> Any:
    """(rows, counts) -- counts = {n_files, n_rows_no_minute, n_rows_missing_fields}."""
    d = data_dir or DEFAULT_DATA_DIR
    files = sorted(glob.glob(str(Path(d) / "*.jsonl")))
    rows: List[Dict[str, Any]] = []
    n_no_minute = n_missing = 0
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        game_id = Path(fp).stem
        for line in lines:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            minute = _parse_minute(r.get("state_summary"))
            if minute is None:
                n_no_minute += 1
                continue
            if "model_prob" not in r or "market_prob" not in r or "outcome" not in r:
                n_missing += 1
                continue
            score_diff = _parse_score_diff(r.get("state_summary"))
            rows.append({
                "game_id": game_id, "bucket": soccer_bucket(minute, score_diff),
                "model_prob": float(r["model_prob"]), "market_prob": float(r["market_prob"]),
                "outcome": _credit(float(r["outcome"])),
            })
    return rows, {"n_files": len(files), "n_rows_no_minute_timeline": n_no_minute,
                 "n_rows_missing_fields": n_missing}


def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(r["bucket"], []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for bkt, rs in buckets.items():
        y = [r["outcome"] for r in rs]
        mkt = [r["market_prob"] for r in rs]
        mdl = [r["model_prob"] for r in rs]
        n_games = len(set(r["game_id"] for r in rs))
        out[bkt] = {
            "n_ticks": len(rs), "n_games": n_games,
            "outcome_rate": round(sum(y) / len(y), 4),
            "market_mean_prob": round(sum(mkt) / len(mkt), 4),
            "market_brier": round(brier(mkt, y), 4),
            "model_n": len(rs),
            "model_mean_prob": round(sum(mdl) / len(mdl), 4),
            "model_brier": round(brier(mdl, y), 4),
        }
        gap = abs(out[bkt]["model_mean_prob"] - out[bkt]["outcome_rate"])
        if n_games < MIN_GAMES:
            out[bkt]["can_price"] = False
            out[bkt]["reason"] = "insufficient games (n_games=%d < %d)" % (n_games, MIN_GAMES)
        elif gap > MAX_MODEL_MARKET_GAP:
            out[bkt]["can_price"] = False
            out[bkt]["reason"] = ("model miscalibrated vs outcome (|delta|=%.4f > %.2f)"
                                  % (gap, MAX_MODEL_MARKET_GAP))
        else:
            out[bkt]["can_price"] = True
            out[bkt]["reason"] = "ok"
    return out


def build_reliability_map(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    rows, counts = load_with_counts(data_dir)
    buckets = _aggregate(rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sport": "soccer_intl", "edge_claimed": False,
        "n_rows_used": len(rows), "n_games_total": len(set(r["game_id"] for r in rows)),
        **counts,
        "can_price_thresholds": {"min_games": MIN_GAMES, "max_model_market_gap": MAX_MODEL_MARKET_GAP},
        "buckets": buckets,
        "honest_note": (
            "Calibration/reliability measurement only, never a $/ROI/edge claim. "
            "model_prob/market_prob/outcome are read verbatim off each corpus row (no "
            "subprocess pricing pass needed -- unlike nba_grid/mlb_grid). SCORING RULE: "
            "outcome is P(home win) with a draw counted as 0.5 credit (matches "
            "ingame_soccer.py's convention) -- a 2-way calibration question, not a 3-way "
            "Brier. score_diff comes from state_summary when parseable, else the row "
            "falls into the 'score_unknown' band (never guessed). n is THIN by "
            "construction (~26 source games carry a minute timeline) -- most buckets are "
            "expected to land INSUFFICIENT (n_games<%d), which is the honest result, not "
            "a bug. n_rows_no_minute_timeline rows use the older minute-less "
            "state_summary format and are excluded entirely." % MIN_GAMES),
    }


def write_reliability_map(out_path: Optional[Path] = None,
                          data_dir: Optional[Path] = None) -> Dict[str, Any]:
    doc = build_reliability_map(data_dir)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="soccer_intl state-bucket reliability map")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    doc = write_reliability_map(a.out, a.data_dir)
    print(json.dumps({"n_buckets": len(doc["buckets"]), "n_rows_used": doc["n_rows_used"],
                      "honest_note": doc["honest_note"]}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
