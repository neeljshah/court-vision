"""scripts.platformkit.ingame.s90_microstructure_screen -- S90 STEP 0 PREMISE re-measurement.

S90's ask (order-book microstructure as-of features on the scored MLB ticks: depth
imbalance, spread, last-trade direction; next-tick sign accuracy + outcome Brier of e4
vs e4+adjustment) is the SAME L15 gap as S90's sibling row S90b/S100
(scripts.platformkit.eval_gate.s100_microstructure), dispatched earlier the same day and
already CLOSED 2026-09-03 (c8acbd78c) at PREMISE FALSIFIED AT TICK GRAIN: the depth
stores are pre-game snapshots (S105 root-caused why -- ticker selection, not gating or
the poll interval), so only 18 SCREEN-side games ever carry an as-of feature inside the
300 s freshness cap, below the 20-game stop rule S100 set for itself.

STEP 0 here re-measures that premise FRESH (Q8) by calling S100's own loaders (pure
functions, read-only import -- this module never edits s100_microstructure.py) with a
NEW output stem, so the S90 evidence file is independent of S100's. If the SCREEN-side
game count is still below this row's own bar (n >= 30 for a scored/sampled metric), the
result is FALSIFIED / INSUFFICIENT and no arm (next-tick sign accuracy, outcome Brier,
walk-forward logistic adjustment) is fit -- fitting an arm on a premise already known to
fail the sampling rail would be a circular metric (VERIFIER_CONTRACT B1) waiting to
happen, not a screen.

SECOND, INDEPENDENT ask in the S90 row text -- L14 (re-key event_key so one game carries
all its in-play market types) -- is NOT covered by S100 and is answered here as a cheap
side measurement: `rekey_market_overlap` strips the Kalshi series prefix from
`event_key` and counts games carrying >= 2 market types.

A CENSUS / FALSIFIED PREMISE IS A NON-FINDING, not a failure. No prereg seal, no ledger
charge, no K read. Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s90_microstructure_screen.py -q
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from scripts.platformkit.eval_gate import s100_microstructure as S100
from scripts.platformkit.venue_history.game_key import game_key_from_event_key

REPO = Path(__file__).resolve().parents[3]
MLB_PRICES = REPO / "data" / "cache" / "inplay_odds" / "mlb_price_series.parquet"
SOCCER_PRICES = REPO / "data" / "cache" / "inplay_odds" / "soccer_intl_price_series.parquet"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s90_microstructure_2026-09-04"

SCREEN_GAMES_BAR = 30        # this row's own sampling rail (n >= 30 for a scored metric); never moved (Q3)
L14_MLB_TYPES = {"moneyline", "total"}
L14_SOCCER_TYPES = {"moneyline", "spread", "team_total"}


def stop_rule_verdict(n_screen_games: int, bar: int = SCREEN_GAMES_BAR) -> str:
    """Pure STEP 0 decision: below the bar is a valid FALSIFIED/INSUFFICIENT result,
    never a fitted arm.  Kept as its own function so the decision is unit-testable
    without touching any store on disk."""
    if n_screen_games < bar:
        return "PREMISE FALSIFIED / INSUFFICIENT (n_screen_games=%d < bar=%d)" % (n_screen_games, bar)
    return "BUILDABLE (n_screen_games=%d >= bar=%d)" % (n_screen_games, bar)


def rekey_market_overlap(frame: pd.DataFrame, required_types: Iterable[str]) -> Dict[str, Any]:
    """L14: strip the Kalshi series prefix (`KXMLBGAME-...` / `KXMLBTOTAL-...` share one
    game suffix after the first `-`) and count games carrying EVERY type in
    `required_types`.  Pure -- operates on any (event_key, market_type) frame, real or
    synthetic, so it is exercised by a CONSTRUCT test with no store read.
    """
    required = set(required_types)
    suffix = game_key_from_event_key(frame["event_key"])
    types_per_game = frame.assign(_suffix=suffix).groupby("_suffix")["market_type"].apply(set)
    matched = types_per_game[types_per_game.apply(lambda s: required.issubset(s))]
    return {
        "required_types": sorted(required),
        "n_games_total": int(types_per_game.shape[0]),
        "n_games_matched": int(matched.shape[0]),
        "matched_game_suffixes_sample": sorted(matched.index)[:5],
    }


def l14_side_measurement(mlb_path: Path = MLB_PRICES, soccer_path: Path = SOCCER_PRICES) -> Dict[str, Any]:
    """Real-store L14 measurement (uncached; not unit-tested -- `rekey_market_overlap`
    above carries the tested logic)."""
    out: Dict[str, Any] = {}
    for label, path, types in (
        ("mlb_moneyline_total", mlb_path, L14_MLB_TYPES),
        ("soccer_intl_all_three", soccer_path, L14_SOCCER_TYPES),
    ):
        if not path.exists():
            out[label] = {"error": "missing: %s" % path}
            continue
        cols = pd.read_parquet(path, columns=["event_key", "market_type"])
        out[label] = rekey_market_overlap(cols, types)
    return out


def reproduce_s100_premise(stem: str = STEM, out_dir: Path = OUT_DIR) -> Dict[str, Any]:
    """STEP 0: re-run S100's own premise pipeline fresh, under a NEW stem so this row's
    evidence file is independent of S100's.  `S100.run` is a pure read of the depth/trade
    stores and the scored-tick store -- no store, module or S100 artifact is edited."""
    return S100.run(out_dir=out_dir, stem=stem)


def run(out_dir: Path = OUT_DIR, stem: str = STEM) -> Dict[str, Any]:
    premise = reproduce_s100_premise(stem=stem, out_dir=out_dir)
    n_screen = int(premise["max_games_screen_side"])
    l14 = l14_side_measurement()
    summary: Dict[str, Any] = {
        "row": "S90", "duplicate_of": "S100 (scripts.platformkit.eval_gate.s100_microstructure, "
                                       "CLOSED 2026-09-03 c8acbd78c, memo "
                                       "docs/evidence/harness/S100_microstructure_2026-09-03.md)",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "screen_games_bar": SCREEN_GAMES_BAR,
        "n_screen_games_any_feature": n_screen,
        "s100_min_games_to_arm": S100.MIN_GAMES_TO_ARM,
        "verdict": stop_rule_verdict(n_screen, SCREEN_GAMES_BAR),
        "arm_run": False,
        "outcome_brier_computed": False,
        "next_tick_sign_accuracy_computed": bool(n_screen >= 2),  # S100 always computes a descriptive table
        "l14_side_measurement": l14,
        "s100_reproduction_artifact": premise.get("per_tick_series"),
        "s100_reproduction_summary_json": str(Path(out_dir) / (stem + ".json")),
        "not_verified": [
            "no arm was fit (premise below this row's n>=30 sampling rail); no outcome Brier "
            "of e4 vs e4+adjustment was computed",
            "L14 re-key produces overlap counts only; no joint distribution fit or CRPS score "
            "was run (out of this row's bar)",
            "pod-side ingame_books/mlb (S105, mlb_book_capture, median 30 s cadence) is not "
            "joined here -- it is not synced locally and joining it is a separate row",
        ],
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / (stem + "_summary.json")).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="S90: microstructure screen premise re-measurement + L14 side measurement")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--stem", default=STEM)
    args = parser.parse_args(argv)
    summary = run(out_dir=Path(args.out_dir), stem=args.stem)
    print("S90 | %s" % summary["verdict"])
    print("  duplicate_of: %s" % summary["duplicate_of"])
    for label, block in summary["l14_side_measurement"].items():
        if "error" in block:
            print("  L14 %-24s ERROR %s" % (label, block["error"]))
        else:
            print("  L14 %-24s matched %d of %d" % (label, block["n_games_matched"], block["n_games_total"]))
    print("  wrote %s" % (Path(args.out_dir) / (args.stem + "_summary.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
