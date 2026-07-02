"""domains.mlb.sp_adjust_current -- current-era (2026+) SP form adjustment, gated OFF.

Mirrors validated domains/mlb/sp_elo_offset.py (p = sigmoid(elo_logit + w*z_sp)) for
the CURRENT MLB season, where the historical pitchers.parquet corpus (2010-2021) has
no coverage. Joins two current-era sources honestly: player_gamelogs.parquet (every
pitcher who appeared, keyed by game_pk, NOT just starters) and probables.parquet
(probable-starter home_sp_id/away_sp_id, keyed by game_pk). A gamelog row counts as
a START only when its player_id matches the probables row's SP id for that SAME
game_pk (_identify_starts) -- nothing is guessed.

FEATURE (current-era PROXY, NOT the historical first-6-innings feature):
per_start_ra_rate = 6.0 * earnedRuns / inningsPitched -- a full-outing earned-run RATE
projected to a 6-inning workload; a proxy for sp_first6_diff_ew, not the same quantity
(no per-inning line score here). inningsPitched in player_gamelogs.parquet is ALREADY
true decimal thirds (5.667, verified live); innings_to_float() still converts "X.1"/"X.2".

LEAK CONTRACT: snapshot-before-update, identical discipline to asof_sp_form.py. A
pitcher's trailing EW form as of game G uses only starts strictly before G's date;
his own start folds into history only AFTER that game's snapshot is recorded.

NOT wired into any live predictor. maybe_adjust() is a no-op unless CV_MLB_SP_ADJUST=1
-- nothing in this repo sets it. Intended (future, human-gated) wiring point:
predict_service's MLB slate producer. PURE pandas/numpy/scipy; no src.*/kernel.* imports;
ASCII only. Accuracy/calibration only -- no betting edge claimed (no-edge-claims rule).
"""
from __future__ import annotations

import json, os, re  # noqa: E401
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.special import expit, logit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EPS: float = 1e-7
EW_ALPHA: float = 0.35        # matches asof_sp_form.py EW_ALPHA
MIN_PRIOR_STARTS: int = 3     # matches asof_sp_form.py MIN_PRIOR_STARTS
PROXY_INNINGS_TARGET: float = 6.0
_INNINGS_FRAC = re.compile(r"^(-?\d+)\.([12])$")

def innings_to_float(value: object) -> Optional[float]:
    """MLB innings notation -> true decimal innings. "5.1"/"5.2" (box-score outs
    notation, X.1=+1/3, X.2=+2/3) -> 5.333/5.667. Already-decimal floats (as stored
    in player_gamelogs.parquet) pass through. None for missing/non-numeric input."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    m = _INNINGS_FRAC.match(s)
    if m:
        whole, outs = int(m.group(1)), int(m.group(2))
        sign = -1.0 if whole < 0 else 1.0
        return whole + sign * (outs / 3.0)
    try:
        return float(s)
    except ValueError:
        return None

_START_COLS = ["game_pk", "date", "side", "player_id", "earned_runs", "innings_pitched"]

def _identify_starts(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_pk, side) START, side in {'home','away'}. A gamelog row is
    a START iff player_id == probables' home_sp_id/away_sp_id for the SAME game_pk.
    Missing probable SP id -> no start row for that side. Columns: _START_COLS."""
    need_gl = {"game_pk", "date", "player_id", "is_pitcher", "earnedRuns", "inningsPitched"}
    if need_gl - set(gamelogs_df.columns):
        raise KeyError(f"gamelogs_df missing columns: {sorted(need_gl - set(gamelogs_df.columns))}")
    need_pr = {"game_pk", "home_sp_id", "away_sp_id"}
    if need_pr - set(probables_df.columns):
        raise KeyError(f"probables_df missing columns: {sorted(need_pr - set(probables_df.columns))}")
    pit = gamelogs_df.loc[
        gamelogs_df["is_pitcher"] == True,  # noqa: E712
        ["game_pk", "date", "player_id", "earnedRuns", "inningsPitched"],
    ].copy()
    prob = probables_df[["game_pk", "home_sp_id", "away_sp_id"]].drop_duplicates("game_pk")
    rows = []
    for side, id_col in (("home", "home_sp_id"), ("away", "away_sp_id")):
        merged = pit.merge(prob[["game_pk", id_col]], on="game_pk", how="inner")
        is_start = merged[id_col].notna() & (merged["player_id"].astype("Int64") == merged[id_col].astype("Int64"))
        m = merged[is_start].copy()
        if len(m) == 0:
            continue
        m["side"] = side
        m["innings_pitched"] = m["inningsPitched"].apply(innings_to_float)
        rows.append(m.rename(columns={"earnedRuns": "earned_runs"})[_START_COLS])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=_START_COLS)

def _per_start_ra_rate(earned_runs: object, innings_pitched: Optional[float]) -> Optional[float]:
    """6.0 * earnedRuns / inningsPitched. Guards inningsPitched <= 0 -> None."""
    if (innings_pitched is None or innings_pitched <= 0 or earned_runs is None
            or (isinstance(earned_runs, float) and np.isnan(earned_runs))):
        return None
    return PROXY_INNINGS_TARGET * float(earned_runs) / float(innings_pitched)

class _EWState:
    """Exponential-weighted trailing per-start RA-rate tracker (mirrors
    asof_sp_form._EWState's online update rule)."""
    __slots__ = ("_ew", "_n")

    def __init__(self) -> None:
        self._ew: Optional[float] = None
        self._n: int = 0

    def snapshot(self) -> Tuple[float, int]:
        if self._n < MIN_PRIOR_STARTS or self._ew is None:
            return float("nan"), self._n
        return self._ew, self._n

    def update(self, ra_rate: float) -> None:
        self._ew = ra_rate if self._ew is None else (1.0 - EW_ALPHA) * self._ew + EW_ALPHA * ra_rate
        self._n += 1

def _ew_snapshot(row: pd.DataFrame, states: Dict[int, _EWState]) -> Tuple[float, int]:
    if len(row) == 0:
        return float("nan"), 0
    return states.setdefault(int(row["player_id"].iloc[0]), _EWState()).snapshot()

def _ew_update(row: pd.DataFrame, states: Dict[int, _EWState]) -> None:
    if len(row) == 0:
        return
    ra = row["ra_rate"].iloc[0]
    if ra is not None and not (isinstance(ra, float) and np.isnan(ra)):
        states[int(row["player_id"].iloc[0])].update(float(ra))

_SP_FORM_COLS = [
    "game_pk", "home_sp_form_ew", "away_sp_form_ew", "sp_diff_ew",
    "home_sp_starts_prior", "away_sp_starts_prior",
]
def build_current_sp_form(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame) -> pd.DataFrame:
    """Leak-free EW current-era SP form, one row per game_pk (columns: see
    _SP_FORM_COLS). Walk-forward over identified starts in (date, game_pk) order:
    snapshot each side's pre-game EW state, THEN fold that start's ra_rate into the
    pitcher's running history (snapshot-before-update). sp_diff_ew = away_sp_form_ew
    - home_sp_form_ew (positive -> home SP historically allowed runs at a LOWER
    rate = home edge; same sign convention as sp_elo_offset's sp_first6_diff_ew).
    NaN when either side has < MIN_PRIOR_STARTS prior starts."""
    starts = _identify_starts(gamelogs_df, probables_df)
    if len(starts) == 0:
        return pd.DataFrame(columns=_SP_FORM_COLS)
    starts = starts.copy()
    starts["ra_rate"] = [
        _per_start_ra_rate(er, ip) for er, ip in zip(starts["earned_runs"], starts["innings_pitched"])
    ]
    starts["_d"] = pd.to_datetime(starts["date"])
    starts = (starts.sort_values(["_d", "game_pk", "side"], kind="mergesort")
              .drop(columns="_d").reset_index(drop=True))
    states: Dict[int, _EWState] = {}
    result_rows = []
    for game_pk, grp in starts.groupby("game_pk", sort=False):
        home_row, away_row = grp[grp["side"] == "home"], grp[grp["side"] == "away"]
        h_ew, h_n = _ew_snapshot(home_row, states)
        a_ew, a_n = _ew_snapshot(away_row, states)
        result_rows.append({
            "game_pk": int(game_pk), "home_sp_form_ew": h_ew, "away_sp_form_ew": a_ew,
            "home_sp_starts_prior": h_n, "away_sp_starts_prior": a_n,
        })
        _ew_update(home_row, states)
        _ew_update(away_row, states)
    out = pd.DataFrame(result_rows)
    h_ew_arr = out["home_sp_form_ew"].values.astype(float)
    a_ew_arr = out["away_sp_form_ew"].values.astype(float)
    out["sp_diff_ew"] = np.where(np.isnan(h_ew_arr) | np.isnan(a_ew_arr), np.nan, a_ew_arr - h_ew_arr)
    return out[_SP_FORM_COLS]

def adjust_win_prob(p_elo: float, sp_diff: float, w: float, sp_mean: float, sp_std: float) -> float:
    """sigmoid(logit(p_elo) + w * z_sp). NaN-safe: NaN p_elo/sp_diff -> p_elo unchanged."""
    if p_elo is None or (isinstance(p_elo, float) and np.isnan(p_elo)):
        return p_elo
    if sp_diff is None or (isinstance(sp_diff, float) and np.isnan(sp_diff)):
        return float(p_elo)
    sp_std_safe = max(float(sp_std), _EPS)
    z = (float(sp_diff) - float(sp_mean)) / sp_std_safe
    p_clipped = float(np.clip(p_elo, _EPS, 1.0 - _EPS))
    return float(expit(float(logit(p_clipped)) + float(w) * z))

@dataclass(frozen=True)
class SpAdjustParams:
    """Fitted-elsewhere params for maybe_adjust (historical or 2026-refit); this
    module only applies them, never fits against live data."""
    w: float
    sp_mean: float
    sp_std: float

def maybe_adjust(p_elo: float, sp_diff: float, params: SpAdjustParams) -> float:
    """Return p_elo UNCHANGED unless env CV_MLB_SP_ADJUST == "1". Human-gated
    no-op by default; the flag is never set anywhere in this repo. Intended
    (future) wiring point: predict_service's MLB slate producer, gated behind
    an explicit human decision to flip this flag."""
    if os.environ.get("CV_MLB_SP_ADJUST") != "1":
        return p_elo
    return adjust_win_prob(p_elo, sp_diff, params.w, params.sp_mean, params.sp_std)

# --- Task 3: 2026 forward OOS evaluation + verdict CLI ---

def _load_2026_universe() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """2026 universe: games in BOTH games_current.parquet (outcomes) and
    probables.parquet (SP identity), bridged via game_pk<->event_id. Unmapped/
    ambiguous game_pks are skipped honestly (never guessed)."""
    from domains.mlb.game_pk_bridge import build_game_pk_bridge
    games_current = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/games_current.parquet")
    probables = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/probables.parquet")
    player_gamelogs = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/player_gamelogs.parquet")
    bridge = build_game_pk_bridge(player_gamelogs=player_gamelogs, games_current=games_current)
    prob = probables.copy()
    prob["event_id"] = prob["game_pk"].map(bridge.mapping)
    prob = prob[prob["event_id"].notna()]
    universe = games_current.merge(prob[["game_pk", "event_id"]], on="event_id", how="inner")
    universe = universe[universe["target_home_win"].notna()].reset_index(drop=True)
    return universe, probables, player_gamelogs

def _apply_variant(p_elo, sp_diff, y_true, w, sp_mean, sp_std, evaluate_metrics) -> Dict[str, object]:
    """Apply adjust_win_prob row-wise + score vs y_true (shared by variants a/b)."""
    p_sp = np.array([adjust_win_prob(pe, sd, w, sp_mean, sp_std) for pe, sd in zip(p_elo, sp_diff)])
    return {"w": w, "sp_mean": sp_mean, "sp_std": sp_std, "sp_model": evaluate_metrics(y_true, p_sp)}

def run_forward_eval() -> Dict[str, object]:
    """Task 3: 2026 forward OOS evaluation (see module docstring for variants
    (a) historical-fit -- headline -- and (b) 2026-half-refit sensitivity)."""
    from domains.mlb.ratings import walk_forward_elo
    from domains.mlb.sp_elo_offset import build_merged_features, evaluate_metrics, fit_sp_offset_weight
    universe, probables, player_gamelogs = _load_2026_universe()
    n = len(universe)
    if n == 0:
        return {"n": 0, "n_with_sp_form": 0, "note": "empty 2026 universe"}
    games_hist = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/games.parquet")
    games_hist["date"] = pd.to_datetime(games_hist["date"])
    games_current_full = pd.read_parquet(_REPO_ROOT / "data/domains/mlb/games_current.parquet")
    full_games = pd.concat([games_hist, games_current_full], ignore_index=True)
    full_games["date"] = pd.to_datetime(full_games["date"])
    elo_df = walk_forward_elo(full_games)[["event_id", "p_home_elo"]]
    sp_form = build_current_sp_form(player_gamelogs, probables)
    uni = universe.merge(elo_df, on="event_id", how="left").merge(sp_form, on="game_pk", how="left")
    uni = uni.sort_values(["date", "game_pk"], kind="mergesort").reset_index(drop=True)
    p_elo = np.clip(uni["p_home_elo"].values.astype(float), _EPS, 1.0 - _EPS)
    y_true = uni["target_home_win"].values.astype(float)
    sp_diff = uni["sp_diff_ew"].values.astype(float)
    n_with_sp_form = int(np.sum(~np.isnan(sp_diff)))
    baseline_metrics = evaluate_metrics(y_true, p_elo)
    # (a) historical (2010-2021) fitted w/sp_mean/sp_std, fully OOS on 2026 -- headline.
    w_hist, mean_hist, std_hist = fit_sp_offset_weight(build_merged_features(games_hist))
    variant_a = _apply_variant(p_elo, sp_diff, y_true, w_hist, mean_hist, std_hist, evaluate_metrics)
    # (b) w refit on first half of the 2026 universe, evaluated on the second half only.
    half = n // 2
    if half >= 10 and (n - half) >= 10:
        train_df = pd.DataFrame({"elo_logit": logit(p_elo[:half]),
                                 "sp_first6_diff_ew": sp_diff[:half], "target_home_win": y_true[:half]})
        w_b, mean_b, std_b = fit_sp_offset_weight(train_df)
        variant_b = _apply_variant(p_elo[half:], sp_diff[half:], y_true[half:], w_b, mean_b, std_b, evaluate_metrics)
        variant_b.update(n_train=int(half), n_test=int(n - half), baseline=evaluate_metrics(y_true[half:], p_elo[half:]))
    else:
        variant_b = {"note": "insufficient rows for stable half-split refit (need >=10/half)"}
    return {
        "n": int(n), "n_with_sp_form": n_with_sp_form, "baseline_full": baseline_metrics,
        "variant_a_historical_fit": variant_a, "variant_b_2026_half_refit": variant_b,
    }

def _verdict(task1_replicated: bool, forward: Dict[str, object]) -> Tuple[str, str]:
    if forward.get("n", 0) == 0:
        return "INCONCLUSIVE", "empty 2026 evaluation universe"
    if not task1_replicated:
        return "REJECT", "historical replication did not hold in both eras"
    n_with_sp = forward.get("n_with_sp_form", 0)
    if n_with_sp < 30:
        return "INCONCLUSIVE", f"only {n_with_sp} rows with non-NaN SP form -- too small to trust"
    sp_brier_a = forward["variant_a_historical_fit"]["sp_model"]["brier"]
    base_brier = forward["baseline_full"]["brier"]
    if sp_brier_a <= base_brier:
        return "SHIP-READY", "flag CV_MLB_SP_ADJUST stays OFF; historical-fit variant does not regress 2026 Brier"
    return "REJECT", "historical-fit variant regresses Brier OOS on 2026"

def main() -> None:
    """CLI: run Task 3 forward eval + write the verdict JSON. Task 1's replication gate
    (2010-2015 AND 2016-2021 each: Brier delta < 0, same-sign w) ran read-only; its boolean
    is recorded here."""
    task1_replicated = True
    forward = run_forward_eval()
    verdict, reason = _verdict(task1_replicated, forward)
    out = {
        "task1_replicated_both_eras": task1_replicated,
        "forward_eval_2026": forward,
        "verdict": verdict,
        "verdict_reason": reason,
        "flag": "CV_MLB_SP_ADJUST",
        "flag_state": "OFF (default; not set anywhere in this repo)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path = _REPO_ROOT / "data/domains/mlb/sp_adjust_verdict.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))
    print(f"\nWrote verdict to {out_path}")

if __name__ == "__main__":
    main()
