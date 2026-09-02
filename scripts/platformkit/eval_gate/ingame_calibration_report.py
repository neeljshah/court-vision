"""scripts.platformkit.eval_gate.ingame_calibration_report -- S43, evidence only.

S43: `max_loser_wp` is DEGENERATE on the pregame gate corpora (one row per
event_id, so every "game path" is a single tick and the peak is just that tick's
probability).  It needs the per-tick in-game stream.  This module composes the
SAME existing pieces S05 composes -- `wp_diagnostics.max_loser_wp` and
`wp_diagnostics.reliability` (bound to `calib_decomp.bin_edges`, the ONE S42 bin
rule), `eval_gate.scoring.ece` / `.sharpness`, `calib_decomp.decompose` (three
Murphy terms) and `ingame.gap_effective_n.effective_sample_size` -- over that
per-tick stream, where a game path is many ticks and max-loser-WP is a real
distribution across games.

DESCRIPTIVE ONLY.  No bar, no threshold and no gate is armed here: max-loser-WP
is REPORTED.  Before it could gate anything it would need its own prereg-sealed
bar, fixed before the first metric (Q3).  Nothing is charged, promoted or
served.  Calibration, not edge.  ASCII.

Per-file test:
  python -m pytest scripts/platformkit/eval_gate/test_ingame_calibration_report.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.calib_decomp import bin_edges, decompose
from scripts.platformkit.eval_gate.calibration_report import _from_bins
from scripts.platformkit.eval_gate.scoring import ece, sharpness
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.wp_diagnostics import max_loser_wp, reliability

REPO = Path(__file__).resolve().parents[3]
SERIES_CSV = REPO / "data" / "cache" / "eval_gate" / "s06_stacker_series_2026-09-03.csv"
OUTPUT = REPO / "docs" / "evidence" / "calibration" / "mlb_ingame_reliability_2026-09-03.json"
BIN_EDGE_RULE = (
    "calib_decomp.bin_edges(bins) -- np.linspace(0, 1, bins + 1) equal-width edges, "
    "bin k = [lo, hi) except the last = [lo, hi]; the SAME rule eval_gate.scoring.ece "
    "and calib_decomp.decompose bin by (gap S42)"
)
DESCRIPTIVE_NOTE = (
    "DESCRIPTIVE. max-loser-WP is REPORTED here, not gated: no bar, no threshold and "
    "no promotion is armed by this artifact. Gating on it would require its own "
    "prereg-sealed bar fixed before the first metric (Q3). Calibration, not edge."
)
ESS_NOTE = ("effective_sample_size over each series' OWN per-tick residual loss "
            "(model_prob - outcome) ** 2, clustered by game; the column is named "
            "loss_differential by that function's signature, it is a level not a paired "
            "difference")


def _loser_block(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-game max-loser-WP distribution: p50 / p90 / max and the >0.8, >0.9 shares."""
    result = max_loser_wp(ticks)
    peaks = [float(row["max_loser_wp"]) for row in result["per_game"]]
    n = len(peaks)
    return {
        "n_loser_games": n,
        "p50": result["quantiles"]["50"],
        "p90": result["quantiles"]["90"],
        "max": max(peaks) if peaks else None,
        "above_0_8": result["above_0_8"],
        "above_0_9": result["above_0_9"],
        "share_above_0_8": (result["above_0_8"] / n) if n else None,
        "share_above_0_9": (result["above_0_9"] / n) if n else None,
        "quantiles": result["quantiles"],
        "per_game": result["per_game"],
    }


def _series_block(probs: Sequence[float], outcomes: Sequence[float],
                  game_ids: Sequence[str], bins: int) -> dict[str, Any]:
    """One series: reliability bins, ECE, three Murphy terms, sharpness, loser peaks, ESS."""
    p = [float(value) for value in probs]
    y = [float(value) for value in outcomes]
    games = [str(value) for value in game_ids]
    ticks = [{"model_prob": prob, "outcome": outcome, "game": game}
             for prob, outcome, game in zip(p, y, games)]
    table = reliability(ticks, edges=bin_edges(bins))
    murphy = decompose(p, y, bins=bins)
    summary_ece = ece(p, y, bins=bins)
    base_rate = float(np.mean(y))
    redone = _from_bins(table, base_rate, len(p))
    losses = [(prob - outcome) ** 2 for prob, outcome in zip(p, y)]
    ess = effective_sample_size(pd.DataFrame({"game": games, "loss_differential": losses}))
    return {
        "n_ticks": len(p),
        "n_games": len(set(games)),
        "base_rate": base_rate,
        "brier": float(np.mean(losses)),
        "ece": float(summary_ece),
        "murphy": {key: murphy[key] for key in ("reliability", "resolution", "uncertainty")},
        "sharpness": sharpness(p),
        "reliability_bins": table,
        "max_loser_wp": _loser_block(ticks),
        "ess": {key: float(value) for key, value in ess.items()},
        "reproduced_from_bins": redone,
        "reproduction_max_abs_diff": max(
            abs(redone["ece"] - float(summary_ece)),
            abs(redone["reliability"] - murphy["reliability"]),
            abs(redone["resolution"] - murphy["resolution"]),
        ),
    }


def build_ingame_report(ticks: Sequence[Any], series: Mapping[str, Sequence[float]],
                        outcomes: Sequence[float], game_ids: Sequence[str],
                        *, bins: int = 10) -> dict[str, Any]:
    """Descriptive in-game calibration report over one per-tick stream.

    `ticks` is the per-tick record sequence every other argument is aligned to
    (row i of every series, `outcomes` and `game_ids` describes ticks[i]); it is
    used for the denominator and to assert that alignment.
    """
    n = len(ticks)
    if not (len(outcomes) == len(game_ids) == n):
        raise ValueError("outcomes/game_ids must align with ticks (%d)" % n)
    for name, values in series.items():
        if len(values) != n:
            raise ValueError("series %r has %d rows, ticks has %d" % (name, len(values), n))
    blocks = {name: _series_block(values, outcomes, game_ids, bins)
              for name, values in series.items()}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "DESCRIPTIVE",
        "note": DESCRIPTIVE_NOTE,
        "bins": bins,
        "bin_edges": [float(edge) for edge in bin_edges(bins)],
        "bin_edge_rule": BIN_EDGE_RULE,
        "ess_note": ESS_NOTE,
        "n_ticks": n,
        "n_games": len(set(str(value) for value in game_ids)),
        "series": blocks,
        "reproduction_max_abs_diff": max(
            block["reproduction_max_abs_diff"] for block in blocks.values()) if blocks else None,
    }


def _market_by_row(store_ticks: Sequence[Mapping[str, Any]]) -> dict[int, float]:
    return {int(tick["_row_id"]): float(tick["market_prob"]) for tick in store_ticks
            if tick.get("market_prob") is not None}


def main() -> int:
    """MLB window-1 store: raw_model, e4 leak-free (game-first-date) and the market."""
    from scripts.platformkit import hedge_trial_arms as A
    from scripts.platformkit.ingame_replay_scoreboard import discover_store

    frame = pd.read_csv(SERIES_CSV)
    store_ticks, _ = A.load_corpus(discover_store(REPO / "data" / "cache"), "mlb")
    market = _market_by_row(store_ticks)
    frame["market"] = [market[int(index)] for index in frame["tick_index"]]
    report = build_ingame_report(
        list(frame["tick_index"]),
        {"raw_model": list(frame["raw_model"]),
         "e4_blend_leakfree_gd": list(frame["pair_leakfree"]),
         "market": list(frame["market"])},
        list(frame["y"]), list(frame["game"]))
    report["input"] = {
        "per_tick_series": str(SERIES_CSV),
        "store": "data/cache/ingame_grade_joined (mlb, window 1)",
        "raw_model": "tick model_prob",
        "e4_blend_leakfree_gd": ("stacker.e4_gd_series -- the game-first-date leak-free e4 "
                                 "variant scored by S06 (column pair_leakfree)"),
        "market": ("tick market_prob captured per tick by live_grade.capture_pair_once; the "
                   "same series the E4 trial scored"),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=1, sort_keys=True,
                                 default=lambda o: o.item() if hasattr(o, "item") else str(o))
                      + "\n", encoding="ascii")
    print("n_ticks %d | n_games %d | reproduction_max_abs_diff %s"
          % (report["n_ticks"], report["n_games"], report["reproduction_max_abs_diff"]))
    print("SERIES | BRIER | ECE | MURPHY_REL | SHARPNESS | LOSER_P50 | LOSER_P90 | SHARE>0.8")
    for name, block in report["series"].items():
        loser = block["max_loser_wp"]
        print("%s | %.6f | %.6f | %.6f | %.6f | %.4f | %.4f | %.4f"
              % (name, block["brier"], block["ece"], block["murphy"]["reliability"],
                 block["sharpness"], loser["p50"], loser["p90"], loser["share_above_0_8"]))
    print("REPORT: %s" % OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
