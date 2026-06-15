"""scripts.platformkit.proof_mlb.ingame_tto -- MLB in-game TTO / bullpen lambda decay.

THE QUESTION: domains/mlb/repricer.py today scales the REMAINING-runs lambda by an
EMPIRICAL per-inning run curve (W135, _INNING_SHARES: early innings worth more, 8th/9th
least). But run-scoring is not purely inning-POSITIONAL -- a starting pitcher faces the
order a 3rd time around innings 5-6 (the well-documented times-through-the-order penalty),
then the BULLPEN takes over late. Does conditioning the remaining-runs estimate on the
inning PHASE (early-SP / 3rd-time-through / bullpen) SHARPEN the live final-total forecast
beyond what the per-inning curve already captures?

THE TEST (leak-free, OOS, RMSE + signed BIAS -- never MAE):
  * Reconstruct mid-game states at innings 3 / 5 / 7 from the SAME real per-inning
    linescores scripts/ingame/repricer_calibration.py uses (pitchers.parquet
    home_innings/away_innings; innings > checkpoint are NEVER seen).
  * Predict the final total as  observed_through_N + E[remaining runs | N].
  * FIT E[remaining|N] two ways on a TRAIN era (2010-2016), then VALIDATE OOS (2017-2021):
      (a) PER-INNING CURVE  -- 9 per-inning mean run-rates (the status-quo shape).
      (b) TTO-PHASE         -- 3 phase mean run-rates (early SP innings 1-4 /
                               3rd-time-through innings 5-6 / bullpen innings 7-9),
                               each remaining inning scored at its phase rate.
    Both are fit ONLY on the train era and frozen for the val era (no leak).
  * Compare OOS final-total RMSE + bias of (a) vs (b). Per-checkpoint and pooled.

HONEST: if TTO does NOT beat the per-inning curve OOS, that is a neutral_null SUCCESS --
the per-inning curve already absorbs the times-through-order structure. If it DOES sharpen
and is clean, it could wire into domains/mlb/repricer.py (NOT wired here -- measure first).
A live book also sees the score, so this is forecaster QUALITY, not a $ edge. Markets
efficient; no edge. INVARIANTS: never edit src/ or kernel/; pure numpy/pandas; <=300 LOC.
Run: python -m scripts.platformkit.proof_mlb.ingame_tto
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_PITCHERS = _REPO / "data" / "domains" / "mlb" / "pitchers.parquet"
_TRAIN = (2010, 2016)
_VAL = (2017, 2021)
_CHECKPOINTS = (3, 5, 7)        # innings at which to reconstruct a mid-game state
_N_INN = 9
# TTO phase map for innings 1..9 (1-indexed): early starter / 3rd-time-through / bullpen.
# Early SP = order seen 1st-2nd time (innings 1-4); 3rd-time-through penalty (innings 5-6);
# bullpen takes over (innings 7-9). One label per inning index.
_PHASE_OF_INNING = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2}
_PHASE_NAMES = ("early_SP_1-4", "3rd_time_5-6", "bullpen_7-9")


def _parse_innings(s: Any) -> Optional[List[int]]:
    if not isinstance(s, str):
        return None
    out: List[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok in ("", "x", "X"):
            continue
        try:
            out.append(int(tok))
        except ValueError:
            return None
    return out or None


def _rmse_bias(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    err = pred - truth
    return float(np.sqrt(np.mean(err ** 2))), float(np.mean(err))


def _per_inning_runs(df) -> Tuple[np.ndarray, np.ndarray]:
    """Per-inning run SUMS and COUNTS over both teams' linescores (innings 1..9).

    Counts an inning only when it was actually played (so a not-batted bottom 9th does
    not pull its mean toward 0 spuriously). Returns (sums[9], counts[9])."""
    sums = np.zeros(_N_INN)
    cnt = np.zeros(_N_INN)
    for hi_s, ai_s in zip(df["home_innings"].to_numpy(), df["away_innings"].to_numpy()):
        for s in (_parse_innings(hi_s), _parse_innings(ai_s)):
            if s is None:
                continue
            for i in range(min(_N_INN, len(s))):
                sums[i] += s[i]
                cnt[i] += 1
    return sums, cnt


def _fit_curve(df) -> np.ndarray:
    """(a) PER-INNING CURVE: mean run-rate per inning (one team), innings 1..9 -> rate[9]."""
    sums, cnt = _per_inning_runs(df)
    return sums / np.maximum(cnt, 1.0)


def _fit_phase(df) -> np.ndarray:
    """(b) TTO-PHASE: mean run-rate per PHASE (one team), pooled over the phase's innings.

    Returns a per-inning rate vector[9] where every inning carries its PHASE mean -- so it
    is the per-inning curve COLLAPSED to 3 step levels (early-SP / 3rd-time / bullpen)."""
    sums, cnt = _per_inning_runs(df)
    phase_sum = np.zeros(len(_PHASE_NAMES))
    phase_cnt = np.zeros(len(_PHASE_NAMES))
    for inn in range(1, _N_INN + 1):
        ph = _PHASE_OF_INNING[inn]
        phase_sum[ph] += sums[inn - 1]
        phase_cnt[ph] += cnt[inn - 1]
    phase_rate = phase_sum / np.maximum(phase_cnt, 1.0)
    return np.array([phase_rate[_PHASE_OF_INNING[inn]] for inn in range(1, _N_INN + 1)])


def _remaining_after(rate_per_inning: np.ndarray, n: int) -> float:
    """E[remaining runs, BOTH teams] after inning n given a one-team per-inning rate[9].

    Sum the per-inning rate over innings n+1..9 (0-indexed slice [n:]), doubled for two
    teams. This is the model's estimate of runs still to come from a mid-game state at
    inning n -- the quantity the live total adds to the observed score."""
    return 2.0 * float(rate_per_inning[n:].sum())


def run() -> Dict[str, Any]:
    import pandas as pd  # noqa: PLC0415
    if not _PITCHERS.is_file():
        return {"status": "no_data", "note": f"pitchers.parquet missing at {_PITCHERS}"}
    df = pd.read_parquet(_PITCHERS, columns=["season", "home_innings", "away_innings"])
    train = df[(df["season"] >= _TRAIN[0]) & (df["season"] <= _TRAIN[1])]
    val = df[(df["season"] >= _VAL[0]) & (df["season"] <= _VAL[1])]
    if len(train) < 100 or len(val) < 100:
        return {"status": "no_data", "note": "train/val era too thin"}

    # FIT both remaining-run estimators on TRAIN ONLY (frozen for val -> leak-free OOS).
    curve_rate = _fit_curve(train)            # 9 per-inning rates
    phase_rate = _fit_phase(train)            # 3 phase rates, expanded to 9 inning slots

    # VALIDATE OOS on the val era. Reconstruct mid-game states at the checkpoints; the
    # repricer/forecaster NEVER sees innings beyond the checkpoint.
    rows_curve: Dict[int, List[Tuple[float, float]]] = {ck: [] for ck in _CHECKPOINTS}
    rows_phase: Dict[int, List[Tuple[float, float]]] = {ck: [] for ck in _CHECKPOINTS}
    n_games = 0
    for hi_s, ai_s in zip(val["home_innings"].to_numpy(), val["away_innings"].to_numpy()):
        h, a = _parse_innings(hi_s), _parse_innings(ai_s)
        if h is None or a is None or len(h) < 1 or len(a) < 1:
            continue
        final_total = float(sum(h) + sum(a))
        used = False
        for ck in _CHECKPOINTS:
            if len(h) < ck or len(a) < ck:
                continue
            observed = float(sum(h[:ck]) + sum(a[:ck]))
            pred_curve = observed + _remaining_after(curve_rate, ck)
            pred_phase = observed + _remaining_after(phase_rate, ck)
            rows_curve[ck].append((pred_curve, final_total))
            rows_phase[ck].append((pred_phase, final_total))
            used = True
        if used:
            n_games += 1

    per_ck: Dict[str, Any] = {}
    all_curve: List[Tuple[float, float]] = []
    all_phase: List[Tuple[float, float]] = []
    for ck in _CHECKPOINTS:
        if not rows_curve[ck]:
            continue
        all_curve += rows_curve[ck]
        all_phase += rows_phase[ck]
        pc = np.array(rows_curve[ck])
        pp = np.array(rows_phase[ck])
        rc, bc = _rmse_bias(pc[:, 0], pc[:, 1])
        rp, bp = _rmse_bias(pp[:, 0], pp[:, 1])
        per_ck[f"inning_{ck}"] = {
            "n": int(pc.shape[0]),
            "curve_rmse": round(rc, 4), "curve_bias": round(bc, 4),
            "phase_rmse": round(rp, 4), "phase_bias": round(bp, 4),
            "rmse_gain_phase_minus_curve": round(rp - rc, 4),
            "abs_bias_gain": round(abs(bp) - abs(bc), 4),
        }
    if not all_curve:
        return {"status": "no_data", "note": "no reconstructable val checkpoints"}

    ac, ap = np.array(all_curve), np.array(all_phase)
    rc, bc = _rmse_bias(ac[:, 0], ac[:, 1])
    rp, bp = _rmse_bias(ap[:, 0], ap[:, 1])
    rmse_gain = rp - rc                    # <0 => TTO-phase sharper (lower RMSE) than curve
    bias_gain = abs(bp) - abs(bc)          # <0 => TTO-phase less biased than curve
    phase_sharper = bool(rmse_gain < -1e-4)

    if phase_sharper:
        verdict = (f"TTO-phase SHARPENS the live total OOS: pooled RMSE {rc:.4f} -> {rp:.4f} "
                   f"(gain {rmse_gain:+.4f}); could wire into domains/mlb/repricer.py "
                   f"(NOT wired -- measured first).")
        kind = "sharpens"
    elif abs(rmse_gain) <= 1e-4:
        verdict = (f"NEUTRAL NULL (success): TTO-phase ties the per-inning curve OOS "
                   f"(RMSE {rc:.4f} ~= {rp:.4f}); the curve already absorbs the "
                   f"times-through-order structure. Per-inning curve stays.")
        kind = "neutral_null"
    else:
        verdict = (f"NEUTRAL NULL (success): TTO-phase does NOT beat the per-inning curve OOS "
                   f"(RMSE {rc:.4f} -> {rp:.4f}, WORSE by {rmse_gain:+.4f}); collapsing 9 "
                   f"inning rates to 3 phase steps LOSES sharpness. Per-inning curve stays.")
        kind = "neutral_null"

    return {
        "status": "ok",
        "train_era": f"{_TRAIN[0]}-{_TRAIN[1]}", "val_era": f"{_VAL[0]}-{_VAL[1]}",
        "n_val_games": n_games, "n_checkpoints": int(ac.shape[0]),
        "checkpoints": list(_CHECKPOINTS),
        "phase_rates_per_team_train": {
            _PHASE_NAMES[i]: round(float(v), 4)
            for i, v in enumerate([phase_rate[0], phase_rate[4], phase_rate[6]])},
        "curve_rates_per_team_train": [round(float(x), 4) for x in curve_rate],
        "per_checkpoint": per_ck,
        # ---- the decisive OOS final-total numbers (RMSE + signed bias, never MAE) ----
        "curve_final_total_rmse": round(rc, 4), "curve_final_total_bias": round(bc, 4),
        "phase_final_total_rmse": round(rp, 4), "phase_final_total_bias": round(bp, 4),
        "rmse_gain_phase_minus_curve": round(rmse_gain, 4),
        "abs_bias_gain_phase_minus_curve": round(bias_gain, 4),
        "tto_phase_sharper": phase_sharper, "verdict_kind": kind,
        "verdict": verdict,
        "note": ("Leak-free: both remaining-run estimators fit on TRAIN 2010-2016 ONLY, frozen "
                 "for OOS VAL 2017-2021; innings beyond the checkpoint never seen. Final TOTAL "
                 "graded RMSE + signed bias (MAE deliberately NOT used). A live book also sees "
                 "the score -> forecaster quality, not a $ edge. Markets efficient; no edge."),
    }


def _main() -> int:
    r = run()
    if r.get("status") != "ok":
        print(f"{r.get('status')}: {r.get('note', '')}")
        return 0
    print("=" * 74)
    print("MLB IN-GAME TTO / bullpen lambda decay -- does inning-PHASE conditioning beat the")
    print("per-inning run curve on the live final TOTAL?  (leak-free OOS, RMSE + bias)")
    print("=" * 74)
    print(f"  train {r['train_era']}  ->  val {r['val_era']}  "
          f"(n={r['n_val_games']} val games, {r['n_checkpoints']} checkpoints @ "
          f"innings {r['checkpoints']})")
    print(f"  TRAIN phase rates/team: {r['phase_rates_per_team_train']}")
    for ck in r["checkpoints"]:
        k = f"inning_{ck}"
        if k not in r["per_checkpoint"]:
            continue
        c = r["per_checkpoint"][k]
        print(f"  @inning {ck} (n={c['n']:5d}): curve RMSE {c['curve_rmse']:.4f} "
              f"bias {c['curve_bias']:+.4f}  |  phase RMSE {c['phase_rmse']:.4f} "
              f"bias {c['phase_bias']:+.4f}  (RMSE gain {c['rmse_gain_phase_minus_curve']:+.4f})")
    print("-" * 74)
    print(f"  POOLED  per-inning curve : RMSE {r['curve_final_total_rmse']:.4f}  "
          f"bias {r['curve_final_total_bias']:+.4f}")
    print(f"  POOLED  TTO-phase        : RMSE {r['phase_final_total_rmse']:.4f}  "
          f"bias {r['phase_final_total_bias']:+.4f}")
    print(f"  RMSE gain (phase-curve)  : {r['rmse_gain_phase_minus_curve']:+.4f}   "
          f"|bias| gain : {r['abs_bias_gain_phase_minus_curve']:+.4f}")
    print(f"VERDICT [{r['verdict_kind']}]: {r['verdict']}")
    print(r["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
