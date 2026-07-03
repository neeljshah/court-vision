"""domains.mlb.weather_vs_close_gate -- does weather add anything vs the
market's own TOTALS CLOSE, not just vs our own no-weather baseline?

weather_totals_gate.py already answers "does weather beat OUR baseline" (a
narrower, easier bar). This module answers the decisive question: does a
walk-forward weather correction shave any RMSE off the market's closing total
line itself? The expected, market-efficient result is NO -- books already
price weather into the total. A REJECT here is the likely and valuable
outcome (see .claude/rules/no-edge-claims.md); SHIP_REVIEW would be
extraordinary and should be treated with suspicion pending more data.

Universe: games with ALL of (a) a totals-market CLOSE line (the anchor/
Pinnacle-devigged closing total, via oddsapi_close_corpus.select_closes), (b)
weather (temp_f, wind, via weather_totals_gate.build_weather_corpus, which
already bridges game_pk -> event_id and joins the realized outcome), (c) a
realized total_runs outcome. The totals close corpus only covers 2025+2026
(oddsapi backfill window), so this universe is a strict subset of the wider
weather_totals_gate corpus (2024+).

Three predictors of realized total runs, scored via walk-forward RMSE/MAE:
  1. CLOSE           -- the closing total line itself, unmodified.
  2. CLOSE+WEATHER    -- close + OLS residual correction on (temp_f centered,
     wind_out, wind_in), fit ONLY on games strictly before the scored game
     (expanding window, refit every 25 games, 100-game burn-in). This is the
     ONLY interesting comparison: if weather is already priced into the
     close, the fitted coefficients should be ~0 and RMSE should not improve.
  3. OURS+WEATHER     -- our own no-weather-baseline+weather candidate from
     weather_totals_gate.run_gate, reported only as a gap-to-market readout
     (never compared as if it could beat the market).

REPLICATION: the scored region splits into two disjoint DATE halves (chrono
midpoint); CLOSE+WEATHER must beat CLOSE RMSE in BOTH halves for SHIP_REVIEW,
else REJECT. Fewer than MIN_SCORABLE rows -> INCONCLUSIVE.

PURE pandas/numpy; reuses oddsapi_close_corpus.select_closes/load_closes and
weather_totals_gate.parse_wind/build_weather_corpus rather than re-parsing.
No src/kernel/api imports. ASCII only. <=300 LOC.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.odds_provider.oddsapi_close_corpus import (  # noqa: E402
    _game_dates, load_closes,
)
from scripts.platformkit.odds_provider.team_resolver import canonical  # noqa: E402
from domains.mlb.weather_totals_gate import (  # noqa: E402
    build_weather_corpus, parse_wind,  # noqa: F401  (parse_wind re-exported for callers/tests)
)

_OUT_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "weather_vs_close_verdict.json"

BURN_IN: int = 100
REFIT_EVERY: int = 25
MIN_SCORABLE: int = 200


def _totals_point(close: Dict[str, Any]) -> Optional[float]:
    """The closing total line (points) from an anchor-devigged totals row."""
    outcomes = close.get("anchor_outcomes") or []
    for o in outcomes:
        pt = o.get("point")
        if pt is not None:
            return float(pt)
    return None


def _resolve_close_event_ids(closes: List[Dict[str, Any]],
                              games_current: pd.DataFrame) -> Dict[str, Tuple[str, float]]:
    """date+team-resolve each totals close to its games_current event_id.

    Mirrors oddsapi_close_corpus._mlb_result_fn's join exactly (same
    canonical() + _game_dates() helpers) so this reuses the ONE provable
    odds<->games_current bridge instead of re-deriving a second one.
    Ambiguous keys (>1 event_id for a date+team-pair, e.g. doubleheaders)
    are dropped, never guessed. Returns event_id -> (event_id, close_total).
    """
    gc = games_current.copy()
    gc["d"] = pd.to_datetime(gc["date"], errors="coerce").dt.strftime("%Y%m%d")
    idx: Dict[tuple, List[str]] = {}
    for _, r in gc.iterrows():
        k = (r["d"], canonical("mlb", str(r["home_team"])), canonical("mlb", str(r["away_team"])))
        idx.setdefault(k, []).append(str(r["event_id"]))

    out: Dict[str, Tuple[str, float]] = {}
    for c in closes:
        pt = _totals_point(c)
        if pt is None:
            continue
        home = canonical("mlb", str(c.get("home")))
        away = canonical("mlb", str(c.get("away")))
        for d in _game_dates(c):
            events = idx.get((d, home, away))
            if events and len(events) == 1:
                out[events[0]] = (events[0], pt)
                break
    return out


def build_close_weather_corpus(
    weather_corpus: Optional[pd.DataFrame] = None,
    closes: Optional[List[Dict[str, Any]]] = None,
    games_current: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """The decisive universe: weather corpus rows that ALSO carry a totals close.

    Columns: date, game_pk, event_id, close_total, temp_f, wind_speed,
    wind_out, wind_in, total_runs. Sorted chronologically (date, game_pk).
    """
    wc = weather_corpus if weather_corpus is not None else build_weather_corpus()
    gc = (games_current.copy() if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(str(_REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet")))
    all_closes = closes if closes is not None else load_closes("mlb")
    totals_closes = [c for c in all_closes if c.get("market") == "totals"]
    resolved = _resolve_close_event_ids(totals_closes, gc)

    # weather_totals_gate.build_weather_corpus doesn't expose event_id in its
    # output columns; rebuild the same game_pk -> event_id map it uses so we
    # can attach the close without re-parsing probables/games_current twice.
    from domains.mlb.game_pk_bridge import build_game_pk_bridge
    player_gamelogs_path = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
    player_gamelogs = (pd.read_parquet(str(player_gamelogs_path))
                        if player_gamelogs_path.exists() else pd.DataFrame())
    bridge = build_game_pk_bridge(player_gamelogs=player_gamelogs if len(player_gamelogs) else None,
                                   games_current=gc)

    df = wc.copy()
    df["event_id"] = df["game_pk"].map(bridge.mapping)
    df["close_total"] = df["event_id"].map(lambda e: resolved[e][1] if e in resolved else np.nan)
    df = df[df["close_total"].notna()].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "game_pk"], kind="mergesort").reset_index(drop=True)
    return df


def _fit_ols_resid(train: pd.DataFrame, temp_mean: float) -> Optional[np.ndarray]:
    """OLS: (total_runs - close_total) = a + b*(temp_f-mean) + c*wind_out + d*wind_in."""
    rows = train[train["temp_f"].notna()]
    if len(rows) < 20:
        return None
    x_temp = rows["temp_f"].values.astype(float) - temp_mean
    x_out = rows["wind_out"].values.astype(float)
    x_in = rows["wind_in"].values.astype(float)
    resid = rows["total_runs"].values.astype(float) - rows["close_total"].values.astype(float)
    X = np.column_stack([np.ones(len(rows)), x_temp, x_out, x_in])
    try:
        coefs, *_ = np.linalg.lstsq(X, resid, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return coefs


def _score_half(y_true: np.ndarray, close_pred: np.ndarray, cand_pred: np.ndarray) -> Dict[str, float]:
    close_rmse = float(np.sqrt(np.mean((y_true - close_pred) ** 2)))
    close_mae = float(np.mean(np.abs(y_true - close_pred)))
    cand_rmse = float(np.sqrt(np.mean((y_true - cand_pred) ** 2)))
    cand_mae = float(np.mean(np.abs(y_true - cand_pred)))
    return {
        "n": int(len(y_true)), "close_rmse": close_rmse, "close_mae": close_mae,
        "candidate_rmse": cand_rmse, "candidate_mae": cand_mae,
        "rmse_delta": cand_rmse - close_rmse,  # negative = candidate beats the close
    }


def run_gate(corpus: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Walk-forward CLOSE vs CLOSE+WEATHER gate. See module docstring."""
    df = corpus if corpus is not None else build_close_weather_corpus()
    n_total = len(df)
    if n_total <= BURN_IN:
        return {"n": n_total, "n_scorable": 0, "verdict": "INCONCLUSIVE",
                "honest_note": "fewer rows than burn-in; cannot walk-forward score"}

    total_runs = df["total_runs"].values.astype(float)
    close_total = df["close_total"].values.astype(float)
    close_pred = close_total.copy()
    candidate_pred = np.full(n_total, np.nan)
    coefs: Optional[np.ndarray] = None
    temp_mean = 0.0
    last_final_coefs: Optional[np.ndarray] = None

    for i in range(BURN_IN, n_total):
        if (i - BURN_IN) % REFIT_EVERY == 0 or coefs is None:
            hist = df.iloc[:i]
            hist_temp = hist["temp_f"].dropna()
            temp_mean = float(hist_temp.mean()) if len(hist_temp) else 0.0
            coefs = _fit_ols_resid(hist, temp_mean)
            if coefs is not None:
                last_final_coefs = coefs
        row = df.iloc[i]
        if coefs is None or pd.isna(row["temp_f"]):
            candidate_pred[i] = close_total[i]
        else:
            adj = (coefs[0] + coefs[1] * (float(row["temp_f"]) - temp_mean)
                   + coefs[2] * float(row["wind_out"]) + coefs[3] * float(row["wind_in"]))
            candidate_pred[i] = close_total[i] + adj

    scorable_idx = np.arange(BURN_IN, n_total)
    n_scorable = int(len(scorable_idx))
    if n_scorable < MIN_SCORABLE:
        return {"n": n_total, "n_scorable": n_scorable, "verdict": "INCONCLUSIVE",
                "honest_note": "fewer than %d scorable rows -- too small to trust" % MIN_SCORABLE}

    y_true = total_runs[scorable_idx]
    cpred = close_pred[scorable_idx]
    kpred = candidate_pred[scorable_idx]
    overall = _score_half(y_true, cpred, kpred)

    mid = n_scorable // 2
    half1 = _score_half(y_true[:mid], cpred[:mid], kpred[:mid])
    half2 = _score_half(y_true[mid:], cpred[mid:], kpred[mid:])
    replicated = half1["rmse_delta"] < 0 and half2["rmse_delta"] < 0

    if not replicated:
        verdict, reason = "REJECT", "candidate does not beat the market close RMSE in both date halves"
    elif overall["rmse_delta"] >= 0:
        verdict, reason = "REJECT", "candidate does not beat the market close RMSE overall"
    else:
        verdict, reason = "SHIP_REVIEW", "candidate beats the market close RMSE overall and in both date halves"

    return {
        "n": int(n_total), "n_scorable": n_scorable, "coverage": n_scorable / n_total,
        "overall": overall, "half1": half1, "half2": half2,
        "residual_coefs": (
            {"intercept": float(last_final_coefs[0]), "temp_f_centered": float(last_final_coefs[1]),
             "wind_out": float(last_final_coefs[2]), "wind_in": float(last_final_coefs[3])}
            if last_final_coefs is not None else None),
        "verdict": verdict,
        "verdict_reason": reason,
        "honest_note": ("the close is the benchmark; matching it is expected; beating it would be "
                         "extraordinary and should be treated with suspicion pending more data. "
                         "no $ edge claimed."),
    }


def run_gate_with_context(corpus: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """run_gate() plus an OURS+WEATHER (weather_totals_gate) gap-to-market readout.

    The ours-vs-baseline candidate is never compared as if it could beat the
    market; it is reported purely as "how far is our own model from the close".
    """
    result = run_gate(corpus)
    try:
        from domains.mlb.weather_totals_gate import run_gate as run_ours_gate
        ours = run_ours_gate()
        ours_overall = ours.get("overall") or {}
        result["ours_context"] = {
            "ours_candidate_rmse": ours_overall.get("candidate_rmse"),
            "ours_baseline_rmse": ours_overall.get("baseline_rmse"),
            "ours_verdict": ours.get("verdict"),
            "note": "gap-to-market readout only; OUR baseline+weather is not compared to the close here",
        }
        close_overall = result.get("overall") or {}
        if close_overall.get("close_rmse") is not None and ours_overall.get("candidate_rmse") is not None:
            result["ours_context"]["ours_gap_to_close_rmse"] = (
                float(ours_overall["candidate_rmse"]) - float(close_overall["close_rmse"]))
    except Exception as exc:  # noqa: BLE001
        result["ours_context"] = {"error": str(exc)}
    return result


def main() -> None:
    result = run_gate_with_context()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _OUT_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2, default=str)
    os.replace(str(tmp), str(_OUT_PATH))
    print(json.dumps(result, indent=2, default=str))
    print("\nWrote verdict to %s" % _OUT_PATH)


if __name__ == "__main__":
    main()
