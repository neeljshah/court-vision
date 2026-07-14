"""scripts.platformkit.live_edge.player_grid.player_validate -- B4-style OOS
replay validation for player_mine.py's BH survivors, on the 2025-26 reserve.

Thin player-scoped wrapper per program task: reuses
replay.validate_claims.bootstrap_ci (same bootstrap method as B4) and
player_grid.build_player_frame(slice="reserve") for the reserve walk --
never edits replay/*.py (B4's files), never re-touches discovery rows.

Score = squared error of (actual on-floor `scored` value) vs
(discovery baseline_rate) vs (baseline_rate + discovered delta), restricted
to reserve possessions where this exact player is on-floor AND the claim's
situation cell is active -- same proper-scoring-rule stand-in B4 uses.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.replay.validate_claims import bootstrap_ci
from scripts.platformkit.live_edge.player_grid import player_grid as pg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CLAIMS_PATH = REPO_ROOT / "data" / "omni" / "claims" / "claims.parquet"
MIN_ACTIVE = 30


def load_player_survivors(claims_path=None) -> pd.DataFrame:
    df = pd.read_parquet(claims_path or CLAIMS_PATH)
    return df[
        df["topic"].astype(str).str.startswith("player_cell.")
        & (df["lifecycle"] == "proposed")
    ].copy()


def parse_claim(row: pd.Series):
    scope = json.loads(row["scope_json"])
    if "context" not in scope:
        return None
    effect = json.loads(row["effect_json"])
    return {
        "cell": scope["context"]["cell"],
        "delta": float(effect["delta"]),
        "baseline_rate": float(effect["baseline_rate"]),
        "player_id": scope["entity_ids"][0],
    }


def validate_one(reserve_long: pd.DataFrame, player_id: str, cell: dict,
                  delta: float, baseline_rate: float) -> dict:
    mask = reserve_long["player_id"] == player_id
    for k, v in cell.items():
        if k in reserve_long.columns:
            mask &= reserve_long[k] == v
    active = reserve_long.loc[mask]
    n = len(active)
    if n < MIN_ACTIVE:
        return {"n_active": int(n), "delta_score": None, "ci_low": None,
                "ci_high": None, "verdict": "INSUFFICIENT_DATA"}
    actual = active["scored"].to_numpy(dtype=float)
    baseline_err = (actual - baseline_rate) ** 2
    conditioned_err = (actual - (baseline_rate + delta)) ** 2
    diffs = baseline_err - conditioned_err  # positive => conditioned reduces error
    ci_low, ci_high = bootstrap_ci(diffs)
    if ci_low > 0:
        verdict = "IMPROVES"
    elif ci_high < 0:
        verdict = "WORSE"
    else:
        verdict = "NULL"
    return {"n_active": int(n), "delta_score": float(diffs.mean()),
            "ci_low": ci_low, "ci_high": ci_high, "verdict": verdict}


def run_validation(reserve_long: pd.DataFrame = None, claims_df: pd.DataFrame = None,
                    possessions_source=None, box_source=None, scorer_dir=None) -> pd.DataFrame:
    reserve_long = reserve_long if reserve_long is not None else pg.build_player_frame(
        slice="reserve", possessions_source=possessions_source, box_source=box_source,
        scorer_dir=scorer_dir)
    claims_df = claims_df if claims_df is not None else load_player_survivors()
    rows = []
    for _, row in claims_df.iterrows():
        parsed = parse_claim(row)
        if parsed is None:
            rows.append({"claim_id": row["claim_id"], "player_id": None, "cell": None,
                         "discovered_delta": None, "n_active": None, "delta_score": None,
                         "ci_low": None, "ci_high": None, "verdict": "NOT_TESTABLE_STRUCTURAL"})
            continue
        result = validate_one(reserve_long, parsed["player_id"], parsed["cell"],
                               parsed["delta"], parsed["baseline_rate"])
        result.update({"claim_id": row["claim_id"], "player_id": parsed["player_id"],
                        "cell": parsed["cell"], "discovered_delta": parsed["delta"]})
        rows.append(result)
    return pd.DataFrame(rows)


def write_report(results: pd.DataFrame, out_path: pathlib.Path = None) -> pathlib.Path:
    out_path = out_path or (REPO_ROOT / "data" / "omni" / "live_edge" / "player_grid" / "PLAYER_VALIDATION_REPORT.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = results["verdict"].value_counts().to_dict() if len(results) else {}
    lines = [
        "# PLAYER-GRAIN LIVE REPLAY VALIDATION -- player_cell claims on OOS reserve (2025-26)\n",
        f"n_families={len(results)} | " + " ".join(f"{k}={v}" for k, v in counts.items()) + "\n",
        "| claim_id | player_id | discovered_delta | n_active | delta_score | ci_low | ci_high | verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]

    def _fmt(v):
        return "" if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, ".5f")

    for _, r in results.iterrows():
        lines.append(
            f"| {r['claim_id']} | {r['player_id']} | {_fmt(r['discovered_delta'])} | "
            f"{'' if r['n_active'] is None else r['n_active']} | {_fmt(r['delta_score'])} | "
            f"{_fmt(r['ci_low'])} | {_fmt(r['ci_high'])} | {r['verdict']} |"
        )
    improves = results[results["verdict"] == "IMPROVES"]["claim_id"].tolist() if len(results) else []
    lines.append("\n## IMPROVES families (first player-grain live-pricer candidates)\n")
    lines.append(", ".join(improves) if improves else "(none)")
    out_path.write_text("\n".join(lines), encoding="ascii", errors="replace")
    return out_path


def main() -> int:
    results = run_validation()
    path = write_report(results)
    print(results["verdict"].value_counts() if len(results) else "no survivors to validate")
    print(f"[player_validate_v1] wrote {path}")
    return 0


__all__ = [
    "CLAIMS_PATH", "MIN_ACTIVE", "load_player_survivors", "parse_claim",
    "validate_one", "run_validation", "write_report",
]

if __name__ == "__main__":
    import sys
    sys.exit(main())
