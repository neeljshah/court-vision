"""scripts.platformkit.benchmarks.crps_market.ingame_soccer -- IN-GAME accuracy
benchmark for soccer_intl (WC2026), the crps_market track's second sport.

PREMISE CHECK (2026-07-10): ingame_mlb.py's own other_sports_joinable note
already flags soccer_intl "NOT_TESTABLE" for a CRPS comparison -- no
conditional-distribution soccer scoring engine (no game_sim analogue) exists
to produce a model ensemble. A fresh read of data/cache/ingame_grade_joined/
soccer_intl/*.jsonl (48 files / 8,700 rows) confirms why: every row already
carries a single scalar P(home win) pair -- model_prob, market_prob -- plus a
3-way settled outcome (1.0 home win / 0.5 draw / 0.0 away win), never a
distribution. CRPS needs a distributional target; this data supports PAIRED
BRIER instead, so that is what this module scores. (A separate, unrelated
benchmark -- scripts/platformkit/ingame/soccer_wc_checkpoint_benchmark.py --
already runs a fuller Brier/ECE scoreboard off a DIFFERENT corpus + model
repricer chain; this module stays inside the crps_market track and scores the
ingame_grade_joined corpus's own embedded pair, mirroring ingame_mlb.py's
checkpoint + bootstrap-CI + ledger conventions exactly.)

CHECKPOINTS: match minute 60 and 75 (first row at-or-past that minute). Some
captured files use an older "live"-only state_summary with no minute field --
those games are excluded (n_no_minute_timeline), never guessed at.

n is thin (<=48 source games, fewer survive the minute floor): UNDERPOWERED
is the expected honest verdict here -- this ships the harness + baseline that
accrues forward, same as ingame_mlb.py's MLB n=55 path started.

CLI: python -m scripts.platformkit.benchmarks.crps_market.ingame_soccer
Tests: python -m pytest tests/platformkit/test_ingame_brier_soccer.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.benchmarks.crps_market.ingame_mlb import _verdict

_REPO = Path(__file__).resolve().parents[4]
_GAME_DIR = _REPO / "data" / "cache" / "ingame_grade_joined" / "soccer_intl"
_LEDGER = _REPO / "data" / "cache" / "intel_claims" / "ingame_distributional_crps_ledger.jsonl"
_OUT = Path(__file__).resolve().parent / "last_run_ingame_soccer.json"

CHECKPOINTS = (60, 75)   # match minute
_MINUTE_RE = re.compile(r"minute=(\d+)")


def load_game_rows(path: Path) -> List[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def has_minute_timeline(rows: List[dict]) -> bool:
    return any(_MINUTE_RE.search(r.get("state_summary", "")) for r in rows)


def checkpoint_row(rows: List[dict], minute_cp: int) -> Optional[dict]:
    """First row whose parsed match minute is >= minute_cp (rows are already
    ts-ordered in the source file); None if that minute is never reached."""
    for r in rows:
        m = _MINUTE_RE.search(r.get("state_summary", ""))
        if m and int(m.group(1)) >= minute_cp:
            return r
    return None


def _ledger_append(rows: List[dict]) -> None:
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(_LEDGER, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def run(max_games: int = 300) -> dict:
    files = sorted(glob.glob(str(_GAME_DIR / "*.jsonl")))[:max_games]
    buckets: Dict[int, List[dict]] = {cp: [] for cp in CHECKPOINTS}
    n_no_minute = 0

    for fp in files:
        rows = load_game_rows(Path(fp))
        if not rows:
            continue
        if not has_minute_timeline(rows):
            n_no_minute += 1
            continue
        for cp in CHECKPOINTS:
            r = checkpoint_row(rows, cp)
            if r is None:
                continue
            outcome = float(r["outcome"])
            buckets[cp].append({
                "model_brier": (float(r["model_prob"]) - outcome) ** 2,
                "market_brier": (float(r["market_prob"]) - outcome) ** 2,
            })

    checkpoints_out: Dict[str, dict] = {}
    ledger_rows: List[dict] = []
    now = pd.Timestamp.utcnow().isoformat()
    for cp, rows in buckets.items():
        if not rows:
            continue
        mb = np.array([r["model_brier"] for r in rows])
        kb = np.array([r["market_brier"] for r in rows])
        delta = kb - mb  # positive => market brier higher => model sharper
        verdict, ci = _verdict(delta)
        key = "home_win_prob|minute_%d" % cp
        provisional = verdict != "UNDERPOWERED"
        verdict_token = verdict + "_PROVISIONAL" if provisional else verdict
        doc = {
            "n": len(rows), "model_brier_mean": round(float(mb.mean()), 4),
            "market_brier_mean": round(float(kb.mean()), 4),
            "paired_delta_mean": round(float(delta.mean()), 4),
            "paired_delta_95ci": ci, "verdict": verdict_token, "provisional": provisional,
        }
        checkpoints_out[key] = doc
        note = ("paired Brier delta (market_brier - model_brier) on the corpus's own "
                "embedded home-win model_prob/market_prob/outcome at the first row "
                "reaching minute_%d; 1 row/game/checkpoint (game-clustered)." % cp)
        note += (" PROVISIONAL -- single capture-window corpus (WC2026), needs "
                 "independent-corpus replication.") if provisional else ""
        ledger_rows.append({
            "sport": "soccer_intl", "market": "home_win_prob", "bucket": "minute_%d" % cp,
            "edge_claimed": False, "template_id": "ingame_paired_brier_soccer",
            "candidate_id": "soccer_ingame_brier::home_win_prob::minute_%d" % cp,
            "n": doc["n"], "effect": doc["paired_delta_mean"], "p": None,
            "alpha_fwer": None, "verdict": verdict_token, "provisional": provisional,
            "computed_at": now, "note": note,
        })

    result = {
        "sport": "soccer_intl", "edge_claimed": False, "metric": "brier",
        "metric_rationale": (
            "CRPS not constructible: each row carries a single scalar P(home win) "
            "pair (model_prob/market_prob) plus a 3-way settled outcome "
            "(1.0/0.5/0.0), never a distribution/ensemble -- no soccer conditional-"
            "distribution scoring engine exists (matches ingame_mlb.py's own "
            "other_sports_joinable note for soccer_intl). Paired Brier at fixed "
            "match-minute checkpoints is the metric this data supports."),
        "n_game_files": len(files), "n_no_minute_timeline": n_no_minute,
        "checkpoints": checkpoints_out,
        "honest_note": (
            "Calibration sharpness only, never a $/ROI claim. Checkpoints are "
            "match minute 60/75 (first row at-or-past that minute); games whose "
            "capture used the older minute-less state_summary format are "
            "excluded, not guessed. n is thin by construction (<=48 source "
            "games) -- UNDERPOWERED is the expected honest verdict here; this "
            "ships the harness + baseline for forward accrual."),
    }
    _OUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    if ledger_rows:
        _ledger_append(ledger_rows)
    return result


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=300)
    a = ap.parse_args(argv)
    doc = run(a.max_games)
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
