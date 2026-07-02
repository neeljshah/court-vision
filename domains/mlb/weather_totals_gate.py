"""domains.mlb.weather_totals_gate -- leak-free weather-vs-totals re-gating daemon core.

Honest question this answers: does pregame weather (temperature + wind out/in)
add leak-free predictive power for the REALIZED total runs of a game, beyond a
leak-free NO-WEATHER baseline (the expanding chronological mean of total runs)?

Scope is deliberately narrow: this is SHARPNESS vs OUR OWN BASELINE only, NOT
a comparison to the market total close. oddsapi captures do carry MLB totals
closes; comparing weather-adjusted totals to the market close is DEFERRED to a
later gate -- doing that here would silently smuggle in a market-beat claim
this module never earns. See .claude/rules/no-edge-claims.md.

Data:
  data/domains/mlb/probables.parquet  -- one row per game_pk (already latest
      snapshot; verified no duplicate game_pk rows live). weather_condition,
      temp_f (float, ~2%% missing), wind (raw string, ~2%% missing).
  data/domains/mlb/games_current.parquet -- event_id-keyed outcomes: home_runs,
      away_runs, date. total_runs = home_runs + away_runs.
  domains.mlb.game_pk_bridge.build_game_pk_bridge -- the only provable
      game_pk <-> event_id map (ambiguous doubleheaders are left unmapped,
      never guessed).

WIND VOCABULARY (verified against the live parquet, 1327 rows, 2026-07-02):
  "<N> mph, Out To {CF,LF,RF}"  -> out
  "<N> mph, In From {CF,LF,RF}" -> in
  "<N> mph, L To R" / "R To L"  -> cross
  "<N> mph, Calm"               -> calm
  "0 mph, None"                 -> calm (the dome/no-wind-reported encoding)
  "<N> mph, Varies"             -> unknown (direction genuinely unstated)
  anything else / NaN           -> unknown

METHOD (run_gate): walk-forward, expanding window, strictly chronological by
date. After a 100-game burn-in, for game i: baseline_i = mean(total_runs of
games < i). candidate_i = baseline_i + OLS(temp_f centered on TRAIN mean,
wind_out, wind_in) fitted ONLY on games < i (refit every 25 games for speed;
between refits the last-fitted coefficients are reused). A game with missing
weather falls back to candidate_i = baseline_i (no leak, no guess). Scored on
RMSE + MAE over all scorable games in the burned-in region.

REPLICATION: the scored region is split into two disjoint DATE halves
(chronological midpoint); candidate must beat baseline RMSE in BOTH halves,
or the lift does not replicate and is REJECTed -- a single-fold lift is an
artifact, not a proof (repo-wide discipline; see no-edge-claims.md).

Verdict: SHIP_REVIEW (replicates in both halves) / REJECT (fails either half,
or candidate does not beat baseline) / INCONCLUSIVE (< 200 scorable rows).
SHIP_REVIEW surfaces the candidate for a HUMAN to decide whether to wire it;
this module never wires or ships anything itself.

PURE pandas/numpy; no src/kernel/api imports. ASCII only. <=300 LOC.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROBABLES = _REPO_ROOT / "data" / "domains" / "mlb" / "probables.parquet"
_GAMES_CURRENT = _REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet"
_OUT_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "weather_totals_verdict.json"

BURN_IN: int = 100
REFIT_EVERY: int = 25
MIN_SCORABLE: int = 200

_OUT_DIRS = {"cf": "out", "lf": "out", "rf": "out"}
_IN_DIRS = {"cf": "in", "lf": "in", "rf": "in"}


def parse_wind(raw: object) -> Tuple[Optional[float], str]:
    """Parse a raw wind string like "8 mph, Out To RF" -> (speed_mph, dir_class).

    dir_class in {"out","in","cross","calm","unknown"}. Missing/unparseable
    input -> (None, "unknown"). Verified vocabulary (see module docstring):
    Out To {CF,LF,RF} -> out; In From {CF,LF,RF} -> in; L To R / R To L ->
    cross; Calm or "0 mph, None" -> calm; Varies -> unknown.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None, "unknown"
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None, "unknown"
    parts = s.split(",", 1)
    speed: Optional[float] = None
    try:
        speed_str = parts[0].strip().lower().replace("mph", "").strip()
        speed = float(speed_str)
    except (ValueError, IndexError):
        speed = None
    tail = parts[1].strip() if len(parts) == 2 else ""
    tail_low = tail.lower()
    if tail_low.startswith("out to"):
        return speed, "out"
    if tail_low.startswith("in from"):
        return speed, "in"
    if tail_low in ("l to r", "r to l"):
        return speed, "cross"
    if tail_low == "calm" or tail_low == "none":
        return speed, "calm"
    if tail_low == "varies":
        return speed, "unknown"
    return speed, "unknown"


def build_weather_corpus(
    probables: Optional[pd.DataFrame] = None,
    games_current: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """probables bridged to games_current outcomes via game_pk_bridge.

    Columns: date, game_pk, temp_f, wind_speed, wind_out, wind_in, total_runs.
    Rows missing the outcome (unmapped/unmatched game_pk) are dropped. Rows
    with missing weather keep NaN in temp_f/wind_speed/wind_out/wind_in (they
    fall back to baseline in run_gate, never dropped or guessed).
    """
    from domains.mlb.game_pk_bridge import build_game_pk_bridge

    prob = (probables.copy() if isinstance(probables, pd.DataFrame)
            else pd.read_parquet(str(_PROBABLES)))
    gc = (games_current.copy() if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(str(_GAMES_CURRENT)))

    player_gamelogs_path = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
    player_gamelogs = (pd.read_parquet(str(player_gamelogs_path))
                        if player_gamelogs_path.exists() else pd.DataFrame())
    bridge = build_game_pk_bridge(player_gamelogs=player_gamelogs if len(player_gamelogs) else None,
                                   games_current=gc)

    prob = prob.copy()
    prob["event_id"] = prob["game_pk"].map(bridge.mapping)
    prob = prob[prob["event_id"].notna()].copy()

    gc2 = gc.copy()
    gc2["total_runs"] = gc2["home_runs"].astype(float) + gc2["away_runs"].astype(float)
    merged = prob.merge(gc2[["event_id", "date", "total_runs"]], on="event_id", how="inner")
    merged = merged[merged["total_runs"].notna()].copy()

    parsed = merged["wind"].apply(parse_wind)
    merged["wind_speed"] = [p[0] for p in parsed]
    dir_class = [p[1] for p in parsed]
    speed_arr = merged["wind_speed"].values.astype(float)
    merged["wind_out"] = [s if d == "out" and not np.isnan(s) else 0.0
                           for s, d in zip(speed_arr, dir_class)]
    merged["wind_in"] = [s if d == "in" and not np.isnan(s) else 0.0
                          for s, d in zip(speed_arr, dir_class)]
    # A row with genuinely no wind string at all keeps wind_speed NaN, but
    # wind_out/wind_in default to 0.0 (contributes nothing, never guessed up).
    out = merged[["date", "game_pk", "temp_f", "wind_speed", "wind_out", "wind_in", "total_runs"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["date", "game_pk"], kind="mergesort").reset_index(drop=True)
    return out


def _fit_ols(train: pd.DataFrame, temp_mean: float) -> Optional[np.ndarray]:
    """OLS residual = a + b*(temp_f - temp_mean) + c*wind_out + d*wind_in.
    Fitted on rows with non-NaN temp_f only. Returns None if too few rows."""
    rows = train[train["temp_f"].notna()]
    if len(rows) < 20:
        return None
    x_temp = (rows["temp_f"].values.astype(float) - temp_mean)
    x_out = rows["wind_out"].values.astype(float)
    x_in = rows["wind_in"].values.astype(float)
    resid = rows["total_runs"].values.astype(float) - rows["_baseline"].values.astype(float)
    X = np.column_stack([np.ones(len(rows)), x_temp, x_out, x_in])
    try:
        coefs, *_ = np.linalg.lstsq(X, resid, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return coefs


def _score_half(y_true: np.ndarray, base_pred: np.ndarray, cand_pred: np.ndarray) -> Dict[str, float]:
    base_rmse = float(np.sqrt(np.mean((y_true - base_pred) ** 2)))
    base_mae = float(np.mean(np.abs(y_true - base_pred)))
    cand_rmse = float(np.sqrt(np.mean((y_true - cand_pred) ** 2)))
    cand_mae = float(np.mean(np.abs(y_true - cand_pred)))
    return {
        "n": int(len(y_true)), "baseline_rmse": base_rmse, "baseline_mae": base_mae,
        "candidate_rmse": cand_rmse, "candidate_mae": cand_mae,
        "rmse_delta": cand_rmse - base_rmse,  # negative = candidate better
    }


def run_gate(corpus: Optional[pd.DataFrame] = None) -> Dict[str, object]:
    """Walk-forward expanding-window gate. See module docstring for method."""
    df = corpus if corpus is not None else build_weather_corpus()
    n_total = len(df)
    if n_total <= BURN_IN:
        return {"n": n_total, "n_scorable": 0, "verdict": "INCONCLUSIVE",
                "honest_note": "fewer rows than burn-in; cannot walk-forward score"}

    total_runs = df["total_runs"].values.astype(float)
    baseline_pred = np.full(n_total, np.nan)
    candidate_pred = np.full(n_total, np.nan)
    coefs: Optional[np.ndarray] = None
    temp_mean = 0.0
    last_final_coefs: Optional[np.ndarray] = None

    for i in range(BURN_IN, n_total):
        hist = df.iloc[:i].copy()
        base_i = float(np.mean(total_runs[:i]))
        baseline_pred[i] = base_i
        if (i - BURN_IN) % REFIT_EVERY == 0 or coefs is None:
            hist_temp = hist["temp_f"].dropna()
            temp_mean = float(hist_temp.mean()) if len(hist_temp) else 0.0
            hist = hist.copy()
            hist["_baseline"] = np.array([np.mean(total_runs[:j]) for j in range(1, i + 1)])
            coefs = _fit_ols(hist, temp_mean)
            if coefs is not None:
                last_final_coefs = coefs
        row = df.iloc[i]
        if coefs is None or pd.isna(row["temp_f"]):
            candidate_pred[i] = base_i
        else:
            adj = (coefs[0] + coefs[1] * (float(row["temp_f"]) - temp_mean)
                   + coefs[2] * float(row["wind_out"]) + coefs[3] * float(row["wind_in"]))
            candidate_pred[i] = base_i + adj

    scorable_idx = np.arange(BURN_IN, n_total)
    n_scorable = int(len(scorable_idx))
    if n_scorable < MIN_SCORABLE:
        return {"n": n_total, "n_scorable": n_scorable, "verdict": "INCONCLUSIVE",
                "honest_note": "fewer than %d scorable rows -- too small to trust" % MIN_SCORABLE}

    y_true = total_runs[scorable_idx]
    base_pred = baseline_pred[scorable_idx]
    cand_pred = candidate_pred[scorable_idx]
    overall = _score_half(y_true, base_pred, cand_pred)

    mid = n_scorable // 2
    half1 = _score_half(y_true[:mid], base_pred[:mid], cand_pred[:mid])
    half2 = _score_half(y_true[mid:], base_pred[mid:], cand_pred[mid:])
    replicated = half1["rmse_delta"] < 0 and half2["rmse_delta"] < 0

    if not replicated:
        verdict, reason = "REJECT", "candidate does not beat baseline RMSE in both date halves"
    elif overall["rmse_delta"] >= 0:
        verdict, reason = "REJECT", "candidate does not beat baseline RMSE overall"
    else:
        verdict, reason = "SHIP_REVIEW", "candidate beats baseline RMSE overall and in both date halves"

    return {
        "n": int(n_total), "n_scorable": n_scorable, "coverage": n_scorable / n_total,
        "overall": overall, "half1": half1, "half2": half2,
        "final_window_coefs": (
            {"intercept": float(last_final_coefs[0]), "temp_f_centered": float(last_final_coefs[1]),
             "wind_out": float(last_final_coefs[2]), "wind_in": float(last_final_coefs[3])}
            if last_final_coefs is not None else None),
        "verdict": verdict,
        "verdict_reason": reason,
        "honest_note": ("sharpness vs OUR OWN no-weather baseline only; NOT compared to the "
                         "market totals close (deferred); no $ edge claimed"),
    }


def main() -> None:
    result = run_gate()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _OUT_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2, default=str)
    import os
    os.replace(str(tmp), str(_OUT_PATH))
    print(json.dumps(result, indent=2, default=str))
    print("\nWrote verdict to %s" % _OUT_PATH)


if __name__ == "__main__":
    main()
