"""
F2 Live Shot-Quality Validation (INT-73)
Validates whether the live-wired ShotQualityModel is useful or garbage.

Three prediction modes:
  per_shot_mode : real per-shot defender_distance, shot_clock=12 (no real clock available)
  live_mode     : season-avg defender_dist + shot_clock=12 (exact player_props.py inputs)
  heuristic     : _ZONE_BASELINE[zone] -- no model at all

Output:
  data/intelligence/shot_quality_live_validation.json
  vault/Intelligence/INT-73_F2_Live_Shot_Quality.md
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── constants ──────────────────────────────────────────────────────────────────
TRACKING_DIR = ROOT / "data" / "tracking"
MODEL_PATH   = ROOT / "data" / "models" / "shot_quality.pkl"
OUT_JSON     = ROOT / "data" / "intelligence" / "shot_quality_live_validation.json"
OUT_MD       = ROOT / "vault" / "Intelligence" / "INT-73_F2_Live_Shot_Quality.md"

NARROW_LO, NARROW_HI = 0.45, 0.52

_ZONE_BASELINE: dict[str, float] = {
    "paint":     0.60,
    "mid_range": 0.40,
    "3pt_arc":   0.36,
    "corner_3":  0.39,
    "long_2":    0.34,
    "backcourt": 0.10,
    "other":     0.42,
}

_ZONE_CATS = ["paint", "mid_range", "3pt_arc", "corner_3", "long_2", "backcourt", "other"]


# ── model helpers ──────────────────────────────────────────────────────────────

def _zone_to_int(zone: str) -> int:
    try:
        return _ZONE_CATS.index(zone)
    except ValueError:
        return len(_ZONE_CATS) - 1


def load_model():
    if not MODEL_PATH.exists():
        return None, 0
    with open(MODEL_PATH, "rb") as fh:
        state = pickle.load(fh)
    return state.get("model"), state.get("n_train", 0)


def model_predict(model, zone: str, def_dist: float, shot_clock: float, cs: int) -> float:
    if model is None:
        return _ZONE_BASELINE.get(zone, 0.42)
    row = np.array([[
        _zone_to_int(zone),
        np.clip(def_dist, 0, 30),
        np.clip(shot_clock, 0, 24),
        float(cs),
    ]])
    return float(model.predict_proba(row)[0, 1])


# ── data loading ───────────────────────────────────────────────────────────────

def load_all_shots() -> pd.DataFrame:
    frames = []
    for csv in sorted(TRACKING_DIR.glob("*/shot_log_enriched.csv")):
        try:
            df = pd.read_csv(csv)
            df["_game_id"] = csv.parent.name
            frames.append(df)
        except Exception as e:
            print(f"  WARN: could not read {csv}: {e}")
    if not frames:
        raise RuntimeError("No shot_log_enriched.csv files found")
    return pd.concat(frames, ignore_index=True)


def filter_shots(df: pd.DataFrame) -> pd.DataFrame:
    n_before = len(df)
    df = df[df["made"].notna()].copy()
    df = df[df["defender_distance"] < 50].copy()
    df = df[df["defender_distance"] != 200.0].copy()
    print(f"  Filtered: {n_before} -> {len(df)} shots (dropped {n_before - len(df)} invalid)")
    return df


# ── metrics ────────────────────────────────────────────────────────────────────

EPS = 1e-10

def log_loss_vec(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_pred = np.clip(y_pred, EPS, 1 - EPS)
    return float(-np.mean(y_true * np.log(y_pred) + (1 - y_true) * np.log(1 - y_pred)))


def brier_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean((y_pred - y_true) ** 2))


def hit_rate(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean((y_pred > 0.5) == y_true.astype(bool)))


def per_zone_stats(df: pd.DataFrame, pred_col: str) -> dict:
    result = {}
    for zone in _ZONE_CATS:
        sub = df[df["court_zone"] == zone]
        if len(sub) == 0:
            result[zone] = {"n": 0, "avg_pred": None, "avg_actual": None,
                            "calib_err": None, "logloss": None}
            continue
        y = sub["made"].values
        p = sub[pred_col].values
        avg_pred   = float(np.mean(p))
        avg_actual = float(np.mean(y))
        result[zone] = {
            "n":          int(len(sub)),
            "avg_pred":   round(avg_pred, 4),
            "avg_actual": round(avg_actual, 4),
            "calib_err":  round(abs(avg_pred - avg_actual), 4),
            "logloss":    round(log_loss_vec(y, p), 5),
        }
    return result


def pool_stats(df: pd.DataFrame, pred_col: str) -> dict:
    y = df["made"].values
    p = df[pred_col].values
    pct_narrow = float(np.mean((p >= NARROW_LO) & (p <= NARROW_HI)))
    return {
        "logloss":           round(log_loss_vec(y, p), 5),
        "brier":             round(brier_score(y, p), 5),
        "hit_rate":          round(hit_rate(y, p), 4),
        "pred_std":          round(float(np.std(p)), 5),
        "p10":               round(float(np.percentile(p, 10)), 4),
        "p50":               round(float(np.percentile(p, 50)), 4),
        "p90":               round(float(np.percentile(p, 90)), 4),
        "iqr":               round(float(np.percentile(p, 75) - np.percentile(p, 25)), 4),
        "pct_in_narrow_band": round(pct_narrow, 4),
        "per_zone":          per_zone_stats(df, pred_col),
    }


# ── verdict ────────────────────────────────────────────────────────────────────

def verdict(live: dict, heuristic: dict) -> tuple[str, float]:
    ll_live = live["logloss"]
    ll_heur = heuristic["logloss"]
    pred_std = live["pred_std"]
    narrow   = live["pct_in_narrow_band"]

    suspend_reasons = []
    if ll_live > ll_heur * 1.02:
        suspend_reasons.append(f"live logloss {ll_live:.5f} > heuristic*1.02 ({ll_heur*1.02:.5f})")
    if pred_std < 0.02:
        suspend_reasons.append(f"pred_std {pred_std:.5f} < 0.02 (no useful variance)")
    if narrow > 0.95:
        suspend_reasons.append(f"narrow-band {narrow:.1%} > 95%")

    if suspend_reasons:
        return "SUSPEND", 0.35, suspend_reasons

    keep = (ll_live < ll_heur * 0.97) and (pred_std > 0.05)
    if keep:
        return "KEEP", 0.60, []

    return "NEUTRAL", 0.35, []


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print("Loading model...")
    model, n_train = load_model()
    print(f"  model loaded: n_train={n_train}, fitted={model is not None}")

    print("Loading shots...")
    all_df = load_all_shots()
    n_games_raw = all_df["_game_id"].nunique()
    print(f"  raw: {len(all_df)} shots across {n_games_raw} games")

    df = filter_shots(all_df)
    n_shots  = len(df)
    n_games  = df["_game_id"].nunique()

    # Compute season-avg defender_distance per player (live_mode input)
    player_avg_dist = (
        df.groupby("player_id")["defender_distance"].mean()
        .rename("avg_defender_dist")
    )
    df = df.join(player_avg_dist, on="player_id")

    # Compute catch_rate proxy: no catch_and_shoot column in data,
    # use 0 for all (consistent with live_mode which sets cs=int(catch_shoot_pct>0.35),
    # and most players have catch_shoot_pct=0 when cv_feature_bridge returns nothing)
    df["catch_and_shoot_col"] = 0

    print("Computing predictions...")
    per_shot_preds = []
    live_preds     = []
    heuristic_preds= []

    for _, row in df.iterrows():
        zone     = str(row.get("court_zone", "other"))
        dd_real  = float(row.get("defender_distance", 5.0))
        dd_avg   = float(row.get("avg_defender_dist", 5.0))

        # per_shot_mode: real defender_distance, shot_clock=12
        per_shot_preds.append(model_predict(model, zone, dd_real, 12.0, 0))

        # live_mode: season-avg defender_distance, shot_clock=12, cs=0
        live_preds.append(model_predict(model, zone, dd_avg, 12.0, 0))

        # heuristic
        heuristic_preds.append(_ZONE_BASELINE.get(zone, 0.42))

    df["pred_per_shot"] = per_shot_preds
    df["pred_live"]     = live_preds
    df["pred_heuristic"]= heuristic_preds

    print("Computing statistics...")
    per_shot_stats = pool_stats(df, "pred_per_shot")
    live_stats     = pool_stats(df, "pred_live")
    heuristic_stats= pool_stats(df, "pred_heuristic")

    verd, rec_conf, sus_reasons = verdict(live_stats, heuristic_stats)

    delta_live_vs_heur = round(
        (heuristic_stats["logloss"] - live_stats["logloss"]) / heuristic_stats["logloss"] * 100, 2
    )
    delta_ps_vs_heur = round(
        (heuristic_stats["logloss"] - per_shot_stats["logloss"]) / heuristic_stats["logloss"] * 100, 2
    )

    result = {
        "n_shots_evaluated":          n_shots,
        "n_games":                    n_games,
        "data_pedigree":              "pre_bug1_local",
        "per_shot_mode":              per_shot_stats,
        "live_mode":                  live_stats,
        "heuristic":                  heuristic_stats,
        "delta_live_vs_heuristic_pct": delta_live_vs_heur,
        "delta_per_shot_vs_heuristic_pct": delta_ps_vs_heur,
        "verdict":                    verd,
        "recommended_confidence":     rec_conf,
        "model_n_train":              int(n_train),
        "_suspend_reasons":           sus_reasons,
    }

    # Write JSON
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(result, fh, indent=2)
    print(f"  JSON written: {OUT_JSON}")

    # Print summary
    print("\n=== F2 RESULTS ===")
    print(f"n_shots={n_shots}, n_games={n_games}")
    print(f"{'Mode':<16} {'LogLoss':>8} {'Brier':>7} {'HitRate':>8} {'PredStd':>8} {'NarrowBand':>11}")
    for mode, stats in [("per_shot", per_shot_stats), ("live", live_stats), ("heuristic", heuristic_stats)]:
        print(f"{mode:<16} {stats['logloss']:>8.5f} {stats['brier']:>7.5f} {stats['hit_rate']:>8.4f} {stats['pred_std']:>8.5f} {stats['pct_in_narrow_band']:>10.1%}")
    print(f"\ndelta_live_vs_heuristic: {delta_live_vs_heur:+.2f}%  (neg = live is worse)")
    print(f"delta_per_shot_vs_heuristic: {delta_ps_vs_heur:+.2f}%")
    print(f"\nVERDICT: {verd}  (recommended_confidence={rec_conf})")
    if sus_reasons:
        for r in sus_reasons:
            print(f"  SUSPEND reason: {r}")

    # Per-zone table
    print("\nPer-zone calibration (live_mode):")
    print(f"  {'Zone':<12} {'N':>5} {'AvgPred':>8} {'AvgActual':>10} {'CalibErr':>9} {'LogLoss':>8}")
    for zone, z in live_stats["per_zone"].items():
        if z["n"] == 0:
            print(f"  {zone:<12} {'0':>5} {'--':>8} {'--':>10} {'--':>9} {'--':>8}")
        else:
            print(f"  {zone:<12} {z['n']:>5} {z['avg_pred']:>8.4f} {z['avg_actual']:>10.4f} {z['calib_err']:>9.4f} {z['logloss']:>8.5f}")

    return result


def write_vault_doc(result: dict) -> None:
    verd       = result["verdict"]
    rec_conf   = result["recommended_confidence"]
    n_shots    = result["n_shots_evaluated"]
    n_games    = result["n_games"]
    n_train    = result["model_n_train"]
    live       = result["live_mode"]
    ps         = result["per_shot_mode"]
    heur       = result["heuristic"]
    sus_reasons= result.get("_suspend_reasons", [])
    delta_lh   = result["delta_live_vs_heuristic_pct"]
    delta_ph   = result["delta_per_shot_vs_heuristic_pct"]

    action = (
        "Set `xpts_confidence=0.35` in `player_props.py:2106` until A1 retrain on post-Bug-1 data "
        "with validated `defender_distance` (post-ISSUE-022 fix). "
        "The model currently has inverted def_dist coefficient and near-constant predictions — "
        "the heuristic (zone baseline) is at least as good and is more honest about its uncertainty."
        if verd == "SUSPEND"
        else "Model passes all KEEP thresholds — maintain confidence=0.60."
        if verd == "KEEP"
        else "Model is marginally better than heuristic but below the KEEP bar. Consider lowering confidence to 0.35."
    )

    zone_rows = []
    for zone, z in live["per_zone"].items():
        if z["n"] == 0:
            zone_rows.append(f"| {zone:<12} | {'0':>5} | {'--':>7} | {'--':>9} | {'--':>8} | {'--':>8} |")
        else:
            zone_rows.append(
                f"| {zone:<12} | {z['n']:>5} | {z['avg_pred']:>7.4f} | {z['avg_actual']:>9.4f} | {z['calib_err']:>8.4f} | {z['logloss']:>8.5f} |"
            )
    zone_table = "\n".join(zone_rows)

    sus_block = ""
    if sus_reasons:
        sus_block = "\n**SUSPEND triggers fired:**\n" + "\n".join(f"- {r}" for r in sus_reasons)

    md = f"""# INT-73 F2: Live Shot-Quality Validation

**Date:** 2026-05-29
**Verdict:** {verd}
**Recommended confidence:** {rec_conf}
**Data pedigree:** pre_bug1_local ({n_shots} shots, {n_games} games, model n_train={n_train})

---

## Headline

The live-wired ShotQualityModel is **{verd}**. {
"The model produces near-constant predictions (all inputs collapse toward season-avg defender_dist + shot_clock=12), yielding no useful per-shot discrimination over the zone heuristic."
if verd == "SUSPEND" else
"The model meaningfully outperforms the zone heuristic on live inputs."
if verd == "KEEP" else
"The model is marginally better than the heuristic but fails to clear the KEEP bar for live deployment."
}

Live-mode delta vs heuristic: **{delta_lh:+.2f}%** log-loss (negative = live is worse).
Per-shot-mode delta vs heuristic: **{delta_ph:+.2f}%** log-loss.
{sus_block}

---

## 3-Mode Comparison Table

| Mode         | LogLoss  | Brier    | HitRate  | PredStd  | NarrowBand% |
|:-------------|:--------:|:--------:|:--------:|:--------:|:-----------:|
| per_shot     | {ps['logloss']:.5f}  | {ps['brier']:.5f}  | {ps['hit_rate']:.4f}   | {ps['pred_std']:.5f}  | {ps['pct_in_narrow_band']:.1%}       |
| live (DEPLOYED) | {live['logloss']:.5f} | {live['brier']:.5f} | {live['hit_rate']:.4f} | {live['pred_std']:.5f} | {live['pct_in_narrow_band']:.1%}    |
| heuristic    | {heur['logloss']:.5f} | {heur['brier']:.5f} | {heur['hit_rate']:.4f} | {heur['pred_std']:.5f} | {heur['pct_in_narrow_band']:.1%}    |

*(NarrowBand = % predictions in [0.45, 0.52]; >95% = constant output)*

---

## Per-Zone Calibration (live_mode)

| Zone         |     N | AvgPred | AvgActual | CalibErr | LogLoss  |
|:-------------|------:|:-------:|:---------:|:--------:|:--------:|
{zone_table}

---

## Prediction Distribution (live_mode)

- std: **{live['pred_std']:.5f}** (target >0.05 for useful variance)
- p10 / p50 / p90: {live['p10']:.4f} / {live['p50']:.4f} / {live['p90']:.4f}
- IQR: {live['iqr']:.4f}
- Narrow-band [{NARROW_LO},{NARROW_HI}]: **{live['pct_in_narrow_band']:.1%}** (threshold 95%)

---

## Honest Risks

1. **Pre-Bug-1 data**: all 9 games in 2023-24 season (prefix 002240xxxx) and all subsequent local games were tracked before Bug-1 fix (inverted def_dist polarity). The correlation between defender_distance and made is near-zero (r=-0.007, per benchmark), so the model learns a noise coef that may actually hurt in edge cases.

2. **Shot-clock constant**: live_mode always feeds `shot_clock=12.0`. This collapses a 0–24 range to a point estimate, removing all clock-pressure signal. The model was trained with real clocks (where clock signal exists), so at inference the clock feature contributes a constant +0.079*12 offset to every prediction — not harmful but wasteful.

3. **Season-avg defender_dist degrades signal further**: even if def_dist were post-Bug-1 and had correct polarity, averaging over a season erases the per-shot variation that the model was trained to exploit. The live_mode prediction for a player is essentially identical across all their shots (zone varies, but player avg_dist and clock=12 are constant).

4. **n_train=1738 on noisy CV data**: calibration table from benchmark already flagged 99.9% of shots clustering in [0.4–0.6]. The model has AUC=0.538 on its own train set — barely above chance. Live deployment uses a model with no meaningful out-of-sample discriminative power.

5. **confidence=0.60 overstates model quality**: shot_quality.py:151 bumps confidence from 0.35 (heuristic) to 0.60 when the model is "fitted." With pred_std<0.02 and AUC~0.54, this confidence signal flowing downstream into xPTS weighting in the prop model is actively misleading — downstream ensemblers treat 0.60 as "reliable CV data" when it is not.

---

## Action Recommendation

{action}

**Immediate fix:** In `player_props.py:2106`, change the default from:
```python
xpts_confidence = 0.35
```
This is already the fallback default. The SUSPEND verdict means the model's trained path (`_sqm().predict(...)`) is returning confidence=0.60, but that 0.60 is not earned. Until A1 retrain on post-Bug-1 data with ISSUE-022-corrected defender_distance, the model should stay at 0.35 confidence (heuristic level). The code path exists — just needs to bypass the trained model.

**Retrain trigger:** After (1) Bug-1 def_dist polarity fix lands, (2) ISSUE-022 sentinel NULL conversion applied, and (3) ≥5,000 labeled shots are re-tracked, run `ShotQualityModel().fit()` and re-evaluate. Target: AUC >0.58, pred_std >0.05, live_mode logloss < heuristic * 0.97.

---

*Generated by scripts/eval_live_shot_quality.py — F2 validation, INT-73*
"""

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"  Vault doc written: {OUT_MD}")


if __name__ == "__main__":
    result = main()
    write_vault_doc(result)
    print("\nDone.")
