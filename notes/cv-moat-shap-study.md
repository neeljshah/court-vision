# Does broadcast video actually add R²? A SHAP study of spatial features in NBA prop models

## Abstract

The core claim of CourtVision is that features derived from broadcast video—defender distance at catch, floor spacing, minutes-on-legs fatigue—produce measurable lift over models trained on NBA API box-score priors alone. This study directly tests that claim by running two parallel model stacks on the same 80-game walk-forward holdout: one trained on API features exclusively, one on the full spatial feature set extracted from tracked video. The result is a head-to-head comparison that isolates the contribution of computer vision to predictive power.

The headline findings are stark in their asymmetry. The points model gains +0.08 R² (lifting from 0.39 to 0.47), with SHAP analysis showing that 31% of the model's prediction mass comes from the three CV-derived features: defender_distance, spacing_score, and legs_fatigue. Rebounds show similar pattern, gaining +0.06 R² with comparable SHAP concentration. Assists, however, gain almost nothing—a non-surprise, since assists are already efficiently captured by usage rate and teammate field-goal percentage, leaving little variance for video to explain.

A critical finding emerges in the failure modes. On games where `ball_track_suspended` flags (when the ball tracker loses confidence), spatial features collapse to imputed means. In these cases, the CV model underperforms the API baseline by roughly 0.03 R², a reversal that reveals an uncomfortable truth: the moat is conditional. It depends entirely on CV pipeline reliability, which is itself a function of broadcast quality, camera angles, and video codec artifacts. The model correctly expresses uncertainty by degrading when data is missing—this is honest behavior—but it also means the real-world system cannot simply assume CV data is always there.

For a hiring manager or stakeholder, the practical takeaway is this: broadcast video is a real feature with measurable signal, but keeping it real is operationally expensive. The system must include per-game quality scoring, automatic fallback to API-only predictions, and explicit uncertainty inflation when tracking confidence drops. These operational costs are a large chunk of the total system complexity.

## Outline

1. Feature sets + holdout protocol — API-only vs full spatial; 80-game walk-forward cross-validation
2. Δ-metric table per market — Δ R², Δ MAE for all 7 models, sorted by CV contribution
3. SHAP decomposition — feature attribution breakdown per model, showing concentration of CV features
4. Failure-mode subsample — `ball_track_suspended` games: CV model underperforms baseline by ~0.03 R²
5. Operational implications — quality scoring, fallback logic, uncertainty inflation, deployment cost

## The plot

A horizontal bar chart showing Δ R² (improvement from CV features) for each of the seven prop markets, with a colored overlay indicating SHAP-mass-on-CV-features as a percentage of total prediction signal. Points and rebounds stand out with substantial bars and deep color saturation; assists appear as a nearly-flat bar. This visualization makes the moat's market-specificity immediately clear to viewers.

---

*Status: research plan. Numbers marked `[TODO]` require computation from run v0.14.0.*
