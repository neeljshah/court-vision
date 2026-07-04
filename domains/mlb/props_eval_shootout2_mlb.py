"""LANE 4 -- PROPS BASELINE SHOOTOUT #2 (queue item 4): settle the standing
baseline properly. Wave 5 honestly REJECTED EW-mean projections (WORSE than
season-to-date mean at CRPS for SP strikeouts/hits/walks, both holdouts -- see
data/domains/mlb/props_eval_verdict.json, legacy key "v1" in this run's output).
This module runs ONE more PRE-DECLARED family shootout: adopt nothing, just
record the winner as the bar any future prop model must beat.

FAMILIES (props_eval_shootout2_mlb_families.py; no open-ended search):
  (a) season_mean : cumulative per-BF rate, walk-forward (wave-5 winner).
  (b) league_shrunk: (n*player_rate + k*league_rate)/(n+k), k fit ONCE on
                      fit_2022_2023 via a 1-D grid (fit_shrinkage_k).
  (c) ew_alpha    : EW_ALPHA=0.35 (wave-5 loser, kept as control).
  (d) prev_season : preseason prior = last season's own rate shrunk to league
                     (same k as (b)), then walk-forward updated by season-to-
                     date starts (see _PrevSeasonState below).

Same NB distributional layer + CRPS scoring as LANE 3
(props_eval_gate_mlb_dist.crps_discrete/median_and_pm1/pinball_at_quantile),
same two independent holdouts (holdout_2024; holdout_2025_2026), same >=30
opportunities-per-holdout floor, same corpus definitions (props_eval_gate_mlb_
constants.CORPORA). fit_2022_2023 is reported but does not gate the verdict
(warm-up + k-fit corpus, not an independent holdout) -- identical discipline to
LANE 3's verdict_for_prop.

STANDING BASELINE: the family with the lowest CRPS in BOTH holdouts
independently, per prop. If no single family wins both holdouts, season_mean
(the simplest family) stays the standing baseline by parsimony -- this is
recorded explicitly, never silently defaulted.

MARKET LINES: identical honest note to LANE 3 -- no historical MLB player-prop
LINE with a close timestamp exists on disk, so this is model-vs-outcome
calibration only, never a market claim.

PURE pandas/numpy/stdlib; no src/kernel/api imports. ASCII only.
Public functions never raise -> {"status": "error"/"empty", ...} degraded payload.
Per-file test only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_props_eval_shootout2_mlb.py -q
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from domains.mlb.props_eval_gate_mlb_constants import CORPORA, PROPS, dispersion_for
from domains.mlb.props_eval_gate_mlb_dist import (
    MIN_PRIOR_STARTS,
    crps_discrete,
    median_and_pm1,
    pinball_at_quantile,
)
from domains.mlb.props_eval_shootout2_mlb_families import FAMILIES, fit_shrinkage_k
from domains.mlb.props_eval_shootout2_mlb_opps import build_shootout_opportunities

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEGACY_VERDICT_PATH = _REPO_ROOT / "data/domains/mlb/props_eval_verdict.json"
_OUT_PATH = _REPO_ROOT / "data/domains/mlb/props_eval_verdict.json"

MARKET_LINES_NOTE = (
    "No historical MLB player-prop LINE with a close timestamp exists on disk "
    "(odds.parquet is game-level ML/OU only; prop_history_corpus_mlb.jsonl "
    "carries market_prob=null throughout). This shootout is CALIBRATION-VS-"
    "OUTCOME ONLY -- no market-beat claim, verbatim from LANE 3."
)


def _score_family(rows: List[Dict[str, object]], lam_key: str, disp: float) -> Dict[str, object]:
    scored = [r for r in rows if not math.isnan(r[lam_key]) and r["n_prior_starts"] >= MIN_PRIOR_STARTS]
    n = len(scored)
    if n == 0:
        return {"n": 0, "crps": None, "pinball_median": None,
                "coverage_median": None}
    crps_vals, pin_med = [], []
    cov_med = 0
    for r in scored:
        lam = max(r[lam_key], 0.0)
        _, med_line, _ = median_and_pm1(lam, disp)
        crps_vals.append(crps_discrete(lam, disp, r["y"]))
        pin_med.append(pinball_at_quantile(r["y"], med_line, 0.5))
        cov_med += 1 if r["y"] <= med_line else 0
    return {
        "n": n,
        "crps": round(float(np.mean(crps_vals)), 5),
        "pinball_median": round(float(np.mean(pin_med)), 5),
        "coverage_median": round(cov_med / n, 4),
    }


def score_prop_shootout(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame,
                          stat_key: str) -> Dict[str, object]:
    """Full per-corpus, per-family scoreboard for one prop. Never raises."""
    try:
        k_fit = fit_shrinkage_k(gamelogs_df, probables_df, stat_key)
        rows = build_shootout_opportunities(gamelogs_df, probables_df, stat_key, k_fit["k"])
    except Exception as exc:  # noqa: BLE001
        return {"stat": stat_key, "status": "error", "error": str(exc)}
    if not rows:
        return {"stat": stat_key, "status": "empty", "corpora": {}, "k_fit": {}}
    by_corpus: Dict[str, List[Dict[str, object]]] = {}
    for r in rows:
        by_corpus.setdefault(r["corpus"], []).append(r)
    disp = dispersion_for(stat_key)
    out: Dict[str, object] = {"stat": stat_key, "status": "ok", "k_fit": k_fit, "corpora": {}}
    for corpus_label in CORPORA:
        crows = by_corpus.get(corpus_label, [])
        out["corpora"][corpus_label] = {
            "season_mean": _score_family(crows, "lam_season_mean", disp),
            "league_shrunk": _score_family(crows, "lam_league_shrunk", disp),
            "ew_alpha": _score_family(crows, "lam_ew_alpha", disp),
            "prev_season": _score_family(crows, "lam_prev_season", disp),
        }
    return out


# ---------------------------------------------------------------------------
# Standing baseline verdict: lowest CRPS in BOTH holdouts independently wins;
# else season_mean stays standing by parsimony (recorded explicitly).
# ---------------------------------------------------------------------------

HOLDOUTS = ("holdout_2024", "holdout_2025_2026")
_N_FLOOR = 30


def _holdout_winner(scoreboard: Dict[str, object], holdout: str) -> Optional[str]:
    c = scoreboard.get("corpora", {}).get(holdout, {})
    candidates = {}
    for fam in FAMILIES:
        stats = c.get(fam, {})
        if stats.get("n", 0) >= _N_FLOOR and stats.get("crps") is not None:
            candidates[fam] = stats["crps"]
    if not candidates:
        return None
    return min(candidates, key=lambda f: (candidates[f], FAMILIES.index(f)))


def standing_baseline_for_prop(scoreboard: Dict[str, object]) -> Dict[str, object]:
    """The family lowest-CRPS in BOTH holdouts independently is the standing
    baseline; ties/no-agreement -> season_mean stays standing by parsimony."""
    if scoreboard.get("status") != "ok":
        return {"standing_baseline": "season_mean", "reason": scoreboard.get("status", "no data"),
                "per_holdout_winner": {}}
    winners = {h: _holdout_winner(scoreboard, h) for h in HOLDOUTS}
    valid = [w for w in winners.values() if w is not None]
    if len(valid) == len(HOLDOUTS) and len(set(valid)) == 1:
        return {"standing_baseline": valid[0], "per_holdout_winner": winners,
                "reason": f"{valid[0]} lowest CRPS in both holdouts independently"}
    return {"standing_baseline": "season_mean", "per_holdout_winner": winners,
            "reason": ("no family won both holdouts independently "
                       f"(per-holdout winners: {winners}) -- season_mean (simplest "
                       "family) stays standing baseline by parsimony")}


# ---------------------------------------------------------------------------
# CLI: full 3-prop shootout, writes verdict JSON v2 (preserving v1) + ledger.
# ---------------------------------------------------------------------------


def run_full_shootout() -> Dict[str, object]:
    gamelogs_df = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/player_gamelogs.parquet")
    probables_df = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/probables.parquet")
    props_out: Dict[str, object] = {}
    for stat_key in PROPS:
        scoreboard = score_prop_shootout(gamelogs_df, probables_df, stat_key)
        verdict = standing_baseline_for_prop(scoreboard)
        props_out[stat_key] = {"scoreboard": scoreboard, "standing_baseline": verdict}
    return {
        "shootout": "props_baseline_shootout_2",
        "families": list(FAMILIES),
        "props": props_out,
        "market_lines_available": False,
        "market_lines_note": MARKET_LINES_NOTE,
        "corpora_definition": CORPORA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_legacy_v1() -> Optional[Dict[str, object]]:
    if not _LEGACY_VERDICT_PATH.exists():
        return None
    try:
        with open(_LEGACY_VERDICT_PATH) as f:
            data = json.load(f)
        # only treat as legacy v1 if it's the LANE-3 shape (has 'props' with
        # per-prop 'verdict', not this shootout's 'standing_baseline').
        first_prop = next(iter(data.get("props", {}).values()), {})
        if "verdict" in first_prop:
            return data
    except Exception:  # noqa: BLE001
        return None
    return None


def _write_verdict_json_v2(result: Dict[str, object], out_path: Optional[Path] = None) -> Path:
    path = out_path or _OUT_PATH
    legacy = _load_legacy_v1()
    payload = dict(result)
    payload["schema_version"] = 2
    if legacy is not None:
        payload["legacy_v1_wave5_ew_vs_baselines"] = legacy
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def _write_ledger_rows(result: Dict[str, object]) -> List[Dict[str, object]]:
    from scripts.platformkit.reject_ledger import record
    rows = []
    for stat_key, payload in result.get("props", {}).items():
        sb = payload.get("standing_baseline", {})
        rows.append(record(
            "mlb", f"props_baseline_shootout2_{stat_key}", "STANDING_BASELINE_SET",
            sb.get("reason", ""), corpus="2022-2026_walkforward",
            metrics={"standing_baseline": sb.get("standing_baseline"),
                      "per_holdout_winner": sb.get("per_holdout_winner")},
            source="manual",
        ))
    return rows


def main() -> None:
    result = run_full_shootout()
    out_path = _write_verdict_json_v2(result)
    _write_ledger_rows(result)
    print(f"Wrote verdict v2 to {out_path}")
    for stat_key, payload in result["props"].items():
        sb = payload["standing_baseline"]
        print(f"  {stat_key}: standing_baseline={sb.get('standing_baseline')} -- {sb.get('reason', '')}")


if __name__ == "__main__":
    main()
