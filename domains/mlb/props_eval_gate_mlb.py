"""LANE 3 -- leak-free per-opportunity props eval for SP strikeouts/hits/walks
(WAKE-31, queue item 3): the REAL eval on the 5-season gamelogs+probables corpus.

THE QUESTION (calibration, NOT a $-edge): for a starting pitcher's next start, does
a walk-forward EW-mean rate x expected-BF projection -> Poisson/NB distribution
score better than two honest baselines (season-to-date mean, league-average rate)
on CRPS (point-forecast sharpness) and pinball loss / coverage at synthetic lines
(median, median+/-1)? Scored per PROP (strikeouts, hits allowed, walks allowed)
across >=2 INDEPENDENT held-out season corpora. An honest MATCHES/WORSE verdict is
a success, not a failure (no-edge-claims rule).

MARKET LINES: searched data/domains/mlb (odds.parquet = game-level ML/OU only, no
player props) and data/frontend/prop_history_corpus_mlb.jsonl (3000 rows, but
market_prob is null in every row sampled -- no real historical prop LINE with a
close timestamp exists on disk for this corpus). This eval is therefore
CALIBRATION-VS-OUTCOME ONLY; no line-beat / MODEL_VIEW claim is made anywhere in
this module. If real prop lines with timestamps ever land on disk, a market
comparison could be added as a clearly-labelled MODEL_VIEW (not a close-beat).

STARTER IDENTITY: mirrors domains/mlb/sp_adjust_current.py's discipline exactly --
a player_gamelogs pitcher row counts as a START only when player_id matches
probables' home_sp_id/away_sp_id for the SAME game_pk (_identify_starts, reused via
props_eval_gate_mlb_dist.py).

LEAK CONTRACT: walk-forward, snapshot-before-update. For start N of a pitcher, the
EW rate + expected-BF projection uses ONLY that pitcher's starts strictly BEFORE
start N's date; start N's own realized line folds into history only AFTER its
snapshot is taken and scored (same discipline as sp_adjust_current._EWState). See
props_eval_gate_mlb_dist.py::build_opportunities for the implementation.

CORPORA (independent, by season -- via the identified start's own game date):
  FIT        : 2022-2023 (rate/EW hyperparameters are fixed constants, not tuned
               per-corpus; "fit" here means the corpus the EW walk-forward warms up
               on, not a tuned free parameter search).
  HOLDOUT_A  : 2024
  HOLDOUT_B  : 2025-2026
Each corpus is scored independently; a SHIP-class verdict requires BOTH holdouts to
beat or match both baselines (no cherry-picking one favorable holdout).

BASELINES (the honest bar):
  season_mean : pitcher's own EW-mean rate computed identically (same walk-forward,
                same leak guard) but with EW_ALPHA=0 (i.e. cumulative mean, no
                exponential recency weight) -- "season-to-date mean".
  league_avg  : the pooled league per-BF rate (same leak guard) with NO player-
                specific history at all.
Both baselines use the SAME expected-BF exposure projection as the model (so only
the RATE projection is being compared, not exposure).

PURE pandas/numpy/stdlib; no src/kernel/api imports. ASCII only.
Public functions NEVER raise -> {"status": "error"/"empty", ...} degraded payload.
Per-file test only (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_props_eval_gate_mlb.py -q
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
    OpportunityRecord,
    build_opportunities,
    crps_discrete,
    median_and_pm1,
    pinball_at_quantile,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Scoring: CRPS + pinball(median, median-1, median+1) per variant, per corpus.
# ---------------------------------------------------------------------------


def _score_variant(records: List[OpportunityRecord], lam_attr: str, stat_key: str
                   ) -> Dict[str, object]:
    disp = dispersion_for(stat_key)
    rows = [r for r in records if not math.isnan(getattr(r, lam_attr))
            and r.n_prior_starts >= MIN_PRIOR_STARTS]
    n = len(rows)
    if n == 0:
        return {"n": 0, "crps": None, "pinball_median": None,
                "pinball_lo": None, "pinball_hi": None,
                "coverage_median": None, "coverage_lo": None, "coverage_hi": None}
    crps_vals, pin_med, pin_lo, pin_hi = [], [], [], []
    cov_med = cov_lo = cov_hi = 0
    for r in rows:
        lam = max(getattr(r, lam_attr), 0.0)
        lo_line, med_line, hi_line = median_and_pm1(lam, disp)
        crps_vals.append(crps_discrete(lam, disp, r.y))
        pin_med.append(pinball_at_quantile(r.y, med_line, 0.5))
        pin_lo.append(pinball_at_quantile(r.y, lo_line, 0.5))
        pin_hi.append(pinball_at_quantile(r.y, hi_line, 0.5))
        cov_med += 1 if r.y <= med_line else 0
        cov_lo += 1 if r.y <= lo_line else 0
        cov_hi += 1 if r.y <= hi_line else 0
    return {
        "n": n,
        "crps": round(float(np.mean(crps_vals)), 5),
        "pinball_median": round(float(np.mean(pin_med)), 5),
        "pinball_lo": round(float(np.mean(pin_lo)), 5),
        "pinball_hi": round(float(np.mean(pin_hi)), 5),
        "coverage_median": round(cov_med / n, 4),
        "coverage_lo": round(cov_lo / n, 4),
        "coverage_hi": round(cov_hi / n, 4),
    }


def score_prop(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame,
              stat_key: str) -> Dict[str, object]:
    """Full per-corpus scoreboard for one prop: model vs season_mean vs
    league_avg, each corpus scored independently. Never raises."""
    try:
        records = build_opportunities(gamelogs_df, probables_df, stat_key)
    except Exception as exc:  # noqa: BLE001
        return {"stat": stat_key, "status": "error", "error": str(exc)}
    if not records:
        return {"stat": stat_key, "status": "empty", "corpora": {}}
    by_corpus: Dict[str, List[OpportunityRecord]] = {}
    for r in records:
        by_corpus.setdefault(r.corpus, []).append(r)
    out: Dict[str, object] = {"stat": stat_key, "status": "ok", "corpora": {}}
    for corpus_label in CORPORA:
        rows = by_corpus.get(corpus_label, [])
        out["corpora"][corpus_label] = {
            "model": _score_variant(rows, "lam_model", stat_key),
            "season_mean": _score_variant(rows, "lam_season_mean", stat_key),
            "league_avg": _score_variant(rows, "lam_league_avg", stat_key),
        }
    return out


# ---------------------------------------------------------------------------
# Verdict: BEATS_BASELINE / MATCHES / WORSE per prop, requiring BOTH holdouts
# to agree (no cherry-picking a single favorable corpus).
# ---------------------------------------------------------------------------

_MATCH_TOL = 0.02  # relative CRPS tolerance treated as "no material difference"
_RANK = {"WORSE": 0, "MATCHES": 1, "BEATS": 2, None: -1}


def _compare_crps(model_crps: Optional[float], base_crps: Optional[float]) -> Optional[str]:
    if model_crps is None or base_crps is None or base_crps <= 0:
        return None
    rel = (model_crps - base_crps) / base_crps
    if rel < -_MATCH_TOL:
        return "BEATS"
    if rel > _MATCH_TOL:
        return "WORSE"
    return "MATCHES"


def _worst_of(labels: List[Optional[str]]) -> str:
    """Conservative combine across baselines/holdouts: the WORST outcome wins
    (a prop only earns BEATS_BASELINE if it beats/matches on every axis)."""
    valid = [l for l in labels if l is not None]
    if not valid:
        return "INSUFFICIENT"
    worst = min(valid, key=lambda l: _RANK[l])
    return {"WORSE": "WORSE", "MATCHES": "MATCHES", "BEATS": "BEATS"}[worst]


def verdict_for_prop(scoreboard: Dict[str, object]) -> Dict[str, object]:
    """BEATS_BASELINE / MATCHES / WORSE / INSUFFICIENT for one prop's scoreboard.
    Requires >=30 scored opportunities in EACH holdout corpus to trust a verdict
    (mirrors sp_adjust_current's n>=30 floor). BEATS_BASELINE requires the model
    to beat-or-match BOTH baselines in BOTH holdout corpora (holdout_2024,
    holdout_2025_2026) -- fit_2022_2023 is reported but does not gate the verdict
    (it is the warm-up corpus, not an independent holdout)."""
    if scoreboard.get("status") != "ok":
        return {"verdict": "INSUFFICIENT", "reason": scoreboard.get("status", "no data")}
    corpora = scoreboard.get("corpora", {})
    holdouts = ["holdout_2024", "holdout_2025_2026"]
    per_holdout_labels: Dict[str, str] = {}
    n_by_holdout: Dict[str, int] = {}
    for h in holdouts:
        c = corpora.get(h, {})
        model = c.get("model", {})
        n = model.get("n", 0) or 0
        n_by_holdout[h] = n
        if n < 30:
            per_holdout_labels[h] = "INSUFFICIENT"
            continue
        vs_season = _compare_crps(model.get("crps"), c.get("season_mean", {}).get("crps"))
        vs_league = _compare_crps(model.get("crps"), c.get("league_avg", {}).get("crps"))
        per_holdout_labels[h] = _worst_of([vs_season, vs_league])
    if any(v == "INSUFFICIENT" for v in per_holdout_labels.values()):
        return {
            "verdict": "INSUFFICIENT",
            "reason": f"n<30 scored opportunities in a holdout corpus: {n_by_holdout}",
            "per_holdout": per_holdout_labels, "n_by_holdout": n_by_holdout,
        }
    final = _worst_of(list(per_holdout_labels.values()))
    verdict = {"BEATS": "BEATS_BASELINE", "MATCHES": "MATCHES",
               "WORSE": "WORSE"}[final]
    return {
        "verdict": verdict, "per_holdout": per_holdout_labels,
        "n_by_holdout": n_by_holdout,
        "reason": f"conservative worst-of across both baselines x both holdouts: {per_holdout_labels}",
    }


# ---------------------------------------------------------------------------
# CLI: full 3-prop eval, writes verdict JSON + reject-ledger rows.
# ---------------------------------------------------------------------------


def run_full_eval() -> Dict[str, object]:
    """Run all 3 props' scoreboards + verdicts. Never raises (degrades per-prop)."""
    gamelogs_df = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/player_gamelogs.parquet")
    probables_df = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/probables.parquet")
    props_out: Dict[str, object] = {}
    for stat_key in PROPS:
        scoreboard = score_prop(gamelogs_df, probables_df, stat_key)
        verdict = verdict_for_prop(scoreboard)
        props_out[stat_key] = {"scoreboard": scoreboard, "verdict": verdict}
    return {
        "props": props_out,
        "market_lines_available": False,
        "market_lines_note": (
            "No historical MLB player-prop LINE with a close timestamp exists on "
            "disk (odds.parquet is game-level ML/OU only; "
            "prop_history_corpus_mlb.jsonl carries market_prob=null throughout). "
            "This eval is CALIBRATION-VS-OUTCOME ONLY -- no market-beat claim."
        ),
        "corpora_definition": CORPORA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_verdict_json(result: Dict[str, object], out_path: Optional[Path] = None) -> Path:
    path = out_path or (_REPO_ROOT / "data/domains/mlb/props_eval_verdict.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    return path


def _write_ledger_rows(result: Dict[str, object]) -> List[Dict[str, object]]:
    from scripts.platformkit.reject_ledger import record
    rows = []
    for stat_key, payload in result.get("props", {}).items():
        v = payload.get("verdict", {})
        metrics = {
            "n_by_holdout": v.get("n_by_holdout"),
            "per_holdout": v.get("per_holdout"),
        }
        rows.append(record(
            "mlb", f"props_eval_{stat_key}", v.get("verdict", "INSUFFICIENT"),
            v.get("reason", ""), corpus="2022-2026_walkforward",
            metrics=metrics, source="manual",
        ))
    return rows


def main() -> None:
    result = run_full_eval()
    out_path = _write_verdict_json(result)
    _write_ledger_rows(result)
    print(f"Wrote verdict to {out_path}")
    for stat_key, payload in result["props"].items():
        v = payload["verdict"]
        print(f"  {stat_key}: {v.get('verdict')} -- {v.get('reason', '')}")


if __name__ == "__main__":
    main()
