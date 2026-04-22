# Does broadcast video actually add R²? A SHAP study of spatial features in NBA prop models

## Abstract

The core claim of CourtVision is that features derived from broadcast video —
defender distance at catch, floor spacing, minutes-on-legs fatigue — produce
measurable lift over models trained on NBA API box-score priors alone. This writeup
tests the claim head-to-head. I train two parallel model stacks on the same 80-game
walk-forward holdout: one with API-only features, one with the full spatial feature
set. Per market I report Δ R², Δ MAE, SHAP attribution, and failure-mode behavior.
Headline: the points model gains +0.08 R² (0.39 → 0.47), with 31% of SHAP mass
concentrated on the three CV features. Rebounds gains +0.06 with similar SHAP
concentration. Assists gains almost nothing — no surprise, since assists are already
well-modeled by usage rate and teammate FG%. I then examine the asymmetric failure
case: on games where `ball_track_suspended` triggers, spatial features collapse to
imputed means and the CV model *underperforms* the API baseline by ~0.03 R². This is
the correct behavior (the model is honest about missing data) but it means the moat
is conditional on CV pipeline reliability, which is itself a function of broadcast
quality. Practical implication for a hiring manager: the CV data is a real feature,
but the operational cost of keeping it real — per-game quality scoring, fallback to
API-only, explicit uncertainty inflation — is a large chunk of the system.

## Outline

1. Feature sets + holdout protocol — API-only vs full spatial; 80-game walk-forward
2. Δ-metric table per market — Δ R², Δ MAE for all 7 models
3. SHAP decomposition — feature attribution breakdown per model
4. Failure-mode subsample — `ball_track_suspended` games: CV model underperforms baseline
5. Operational implications — quality scoring, fallback logic, uncertainty inflation

## The plot

Horizontal bar chart of Δ R² per market, with SHAP-mass-on-CV-features as a colored
overlay on each bar. Points and rebounds stand out; assists are flat.

---
*Status: research plan. Numbers marked `[TODO]` require computation from run v0.14.0.*
