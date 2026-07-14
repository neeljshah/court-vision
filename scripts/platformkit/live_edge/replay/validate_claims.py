"""scripts.platformkit.live_edge.replay.validate_claims -- B4 claim validator.

For each B1 situational-claim family (41 BH survivors, lifecycle="proposed",
topic~situation, in data/omni/claims/claims.parquet), scores the conditioned
prediction (discovery baseline + claim's discovered delta) against the
state-only baseline (discovery baseline alone) on the OOS reserve slice
(2025-26), RESTRICTED to ticks where the claim's situation cell is ACTIVE.
Score = squared error (a CRPS-proxy for a scalar continuous outcome --
points-per-possession has no natural distributional forecast to CRPS
against here, so squared error is the proper-scoring-rule stand-in; see
program item B4 which asks for "CRPS/log-loss").

Winner = bootstrap CI of (baseline_err - conditioned_err) excludes 0 on the
positive side (conditioned strictly reduces error).
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.replay.tick_replay import (
    active_mask_for_cell,
    discovery_baseline_ppp,
    load_reserve_tagged,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CLAIMS_PATH = REPO_ROOT / "data" / "omni" / "claims" / "claims.parquet"

N_BOOT = 2000
MIN_ACTIVE = 30  # below this, bootstrap CI is not meaningful -> INSUFFICIENT_DATA
SEED = 0


def load_b1_survivors(claims_path=None) -> pd.DataFrame:
    """The 41 B1 BH-surviving situational claims: lifecycle="proposed"
    (not yet escalated/accepted), topic contains "situation"."""
    df = pd.read_parquet(claims_path or CLAIMS_PATH)
    return df[
        df["topic"].astype(str).str.contains("situation", case=False, na=False)
        & (df["lifecycle"] == "proposed")
    ].copy()


def parse_claim(row: pd.Series):
    """Returns None for the 2 structural/meta claims in the 41 (DATA-ABSENT
    notices, no cell+delta to test) -- everything else is a testable
    cell-conditioned points_per_possession delta, scoped by entity_type
    (league-wide / team / lineup, matching grid_sweep.py's 5 mining passes)."""
    scope = json.loads(row["scope_json"])
    if "context" not in scope:
        return None
    effect = json.loads(row["effect_json"])
    return {
        "cell": scope["context"]["cell"],
        "delta": float(effect["delta"]),
        "stat": effect["stat"],
        "entity_type": scope.get("entity_type", "league"),
        "entity_ids": scope.get("entity_ids", []),
    }


def bootstrap_ci(diffs: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    """Resample-mean bootstrap. Loops per-draw (rather than one (n_boot, n)
    index matrix) so n_active in the hundreds-of-thousands doesn't blow up
    memory -- each draw is still a single vectorized numpy call."""
    rng = np.random.default_rng(seed)
    n = len(diffs)
    boot_means = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        boot_means[i] = diffs[rng.integers(0, n, size=n)].mean()
    return float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))


def validate_one(tagged_df: pd.DataFrame, cell: dict, delta: float, baseline_ppp: float,
                  entity_type: str = "league", entity_ids: list | None = None) -> dict:
    mask = active_mask_for_cell(tagged_df, cell, entity_type=entity_type, entity_ids=entity_ids)
    active = tagged_df.loc[mask]
    n = len(active)
    if n < MIN_ACTIVE:
        return {"n_active": int(n), "delta_score": None, "ci_low": None,
                "ci_high": None, "verdict": "INSUFFICIENT_DATA"}
    actual = active["points"].to_numpy(dtype=float)
    baseline_err = (actual - baseline_ppp) ** 2
    conditioned_err = (actual - (baseline_ppp + delta)) ** 2
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


def run_validation(tagged_df: pd.DataFrame = None, claims_df: pd.DataFrame = None,
                    possessions_source=None) -> pd.DataFrame:
    tagged_df = tagged_df if tagged_df is not None else load_reserve_tagged()
    claims_df = claims_df if claims_df is not None else load_b1_survivors()
    baseline_ppp = discovery_baseline_ppp(possessions_source)
    rows = []
    for _, row in claims_df.iterrows():
        parsed = parse_claim(row)
        if parsed is None:
            rows.append({"claim_id": row["claim_id"], "cell": None, "stat": None,
                         "discovered_delta": None, "n_active": None,
                         "delta_score": None, "ci_low": None, "ci_high": None,
                         "verdict": "NOT_TESTABLE_STRUCTURAL"})
            continue
        result = validate_one(tagged_df, parsed["cell"], parsed["delta"], baseline_ppp,
                               entity_type=parsed["entity_type"], entity_ids=parsed["entity_ids"])
        result.update({"claim_id": row["claim_id"], "cell": parsed["cell"], "stat": parsed["stat"],
                        "discovered_delta": parsed["delta"]})
        rows.append(result)
    return pd.DataFrame(rows)


def write_report(results: pd.DataFrame, out_path: pathlib.Path = None) -> pathlib.Path:
    out_path = out_path or (REPO_ROOT / "data" / "omni" / "live_edge" / "replay" / "VALIDATION_REPORT.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = results["verdict"].value_counts().to_dict()
    lines = [
        "# B4 LIVE REPLAY VALIDATION -- B1 situational claims on OOS reserve (2025-26)\n",
        f"n_families={len(results)} | " + " ".join(f"{k}={v}" for k, v in counts.items()) + "\n",
        "| claim_id | stat | discovered_delta | n_active | delta_score | ci_low | ci_high | verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    def _fmt(v):
        return "" if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, ".5f")

    for _, r in results.iterrows():
        lines.append(
            f"| {r['claim_id']} | {r['stat']} | {_fmt(r['discovered_delta'])} | "
            f"{'' if r['n_active'] is None else r['n_active']} | {_fmt(r['delta_score'])} | "
            f"{_fmt(r['ci_low'])} | {_fmt(r['ci_high'])} | {r['verdict']} |"
        )
    improves = results[results["verdict"] == "IMPROVES"]["claim_id"].tolist()
    lines.append("\n## IMPROVES families (live-pricer candidates)\n")
    lines.append(", ".join(improves) if improves else "(none)")
    lines.append(
        "\n## C1 minutes result -- NOT re-tested here (grain mismatch: per-player-"
        "game observable, not per-possession tick). Already OOS-validated by its "
        "own reserved split in data/omni/live_edge/combine/minutes_combiner_report.json "
        "(COMBINER_BEATS_BASELINE, n_reserve=24954, marginal pinball delta=0.070)."
    )
    out_path.write_text("\n".join(lines), encoding="ascii", errors="replace")
    return out_path


__all__ = [
    "CLAIMS_PATH", "N_BOOT", "MIN_ACTIVE", "load_b1_survivors", "parse_claim",
    "bootstrap_ci", "validate_one", "run_validation", "write_report",
]
