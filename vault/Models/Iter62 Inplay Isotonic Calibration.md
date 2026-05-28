# Iter 62 — Inplay Isotonic Calibration Overlay

**Run:** 2026-05-27 (post Iter 61 sim reconciliation)
**Type:** Calibration overlay (zero retraining of production `.lgb` models)
**Code:** `scripts/iter62_inplay_isotonic_calibration.py`
**Results:** `data/cache/iter62_inplay_isotonic_results.json`
**Overlays:** `data/models/inplay_isotonic_endq{1,2,3}.joblib`

## Hypothesis

The OOS validation (`data/cache/inplay_oos_validation_2026_05_27.json`) flagged `CALIBRATION_DRIFT_GT_5PCT` on all three snapshots. The bin-9 (0.9-1.0) gap reached -0.24 on endQ1 fold-3 — model says 95%, actual 70%. A per-snapshot isotonic regression fit on accumulated OOS predictions should pull confident predictions back toward reality and cut Brier.

## Method

1. Replicate `probe_R10_M5_inplay_winprob.walk_forward_cv` exactly (4-fold expanding, 60% min-train, seed=42).
2. For each fold k>=1: fit `IsotonicRegression(out_of_bounds='clip')` on all OOS predictions from folds 0..k-1; transform fold-k raw probabilities; compare Brier.
3. Fold 0 cannot be calibrated (no prior OOS data) — neutral.
4. Final overlay = isotonic fit on all four folds' OOS predictions; saved to `data/models/inplay_isotonic_endq{1,2,3}.joblib`.

## pkl Integrity

| snapshot | meta_features | booster_features | match |
|---|---|---|---|
| endQ1 | 8 | 8 | YES |
| endQ2 | 9 | 9 | YES |
| endQ3 | 13 | 13 | YES (probe scaffold is subset; 3 extras: `q1_usg_avg`, `halftime_pace_shift`, `trailing_team_q4_usg_hhi`) |

Production `.lgb` files use CRLF line endings (Windows save artifact) which LightGBM's native parser rejects on `model_file=`. Worked around by loading via `model_str=` after `.replace(b"\r\n", b"\n")`. The on-disk files were NOT touched.

## Results

Per-fold Brier (raw vs isotonic):

| snapshot | fold 0 (no cal) | fold 1 | fold 2 | fold 3 | mean (all) | mean (cal only) |
|---|---|---|---|---|---|---|
| endQ1 raw | 0.2225 | 0.2147 | 0.2258 | 0.2278 | 0.2227 | 0.2227 |
| endQ1 iso | 0.2225 | 0.2146 | 0.2144 | 0.2191 | 0.2177 | **0.2160** |
| endQ1 delta | +0.0000 | -0.0001 | -0.0114 | -0.0087 | -0.0051 | **-0.0067** |
| endQ2 raw | 0.1758 | 0.1817 | 0.1963 | 0.1873 | 0.1853 | 0.1884 |
| endQ2 iso | 0.1758 | 0.1808 | 0.1925 | 0.1870 | 0.1840 | 0.1868 |
| endQ2 delta | +0.0000 | -0.0009 | -0.0038 | -0.0002 | -0.0012 | -0.0016 |
| endQ3 raw | 0.1392 | 0.1484 | 0.1583 | 0.1174 | 0.1408 | 0.1414 |
| endQ3 iso | 0.1392 | 0.1483 | 0.1479 | 0.1247 | 0.1400 | 0.1403 |
| endQ3 delta | +0.0000 | -0.0001 | -0.0104 | **+0.0072** | -0.0008 | -0.0011 |

## Ship Decision

Gate (per snapshot): `>=3/4 folds improve AND mean Brier delta <= -0.003 on at least one snapshot`.

| snapshot | cal folds | improved | mean delta (all) | folds_gate | delta_gate | **decision** |
|---|---|---|---|---|---|---|
| **endQ1** | 3 | **3/3** | **-0.0051** | PASS | PASS | **SHIP** |
| endQ2 | 3 | 3/3 | -0.0012 | PASS | FAIL | REJECT |
| endQ3 | 3 | 2/3 | -0.0008 | FAIL | FAIL | REJECT |

Aggregate mean Brier delta across cal folds: **-0.0032**.

## Why endQ2 / endQ3 don't ship

- **endQ2**: 3/3 folds improve directionally, but magnitudes are small (-0.0009, -0.0038, -0.0002). Mean delta -0.0012 is positive signal but below the -0.003 publishability bar.
- **endQ3**: fold-2 wins big (-0.0104), fold-3 regresses (+0.0072). With score margin and three quarters of history, the raw model is already well-calibrated in the high-confidence bins; isotonic over-corrects on the most-recent fold where overconfidence is mild.

The endQ1 overlay should be wired into the live inplay engine when the engine path is unfrozen.

## Files

- `scripts/iter62_inplay_isotonic_calibration.py` — full WF + isotonic + ship-gate evaluation
- `data/cache/iter62_inplay_isotonic_results.json` — per-fold raw/iso Brier + 10-bin reliability before/after
- `data/models/inplay_isotonic_endq1.joblib` — SHIP — production overlay
- `data/models/inplay_isotonic_endq2.joblib` — saved but DO NOT WIRE (failed gate)
- `data/models/inplay_isotonic_endq3.joblib` — saved but DO NOT WIRE (failed gate)
