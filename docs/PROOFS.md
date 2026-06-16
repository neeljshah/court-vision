# PROOFS -- the provability index

> Every prediction claim in this project is backed by a runnable, leak-free / OOS proof
> module. This is the index: each proof maps to the claim it backs, HOW it stays leak-free,
> a runtime class, and the exact command to reproduce it. The honesty truth-source for the
> numbers is `docs/JOB_EVIDENCE_PACKET.md` -- cite that; this file points at the code that
> generates them.
>
> ALL numbers below are CALIBRATION / SHARPNESS (Brier, RMSE, ECE). There is NO $ edge, no
> ROI, no "beat the close" claim. "MATCH the devigged close within noise" and "honest nulls
> are successes" are the framings we stand behind. Markets are efficient; the measured,
> calibrated, delivered advantage is IN-GAME conditioning on the realized state.

---

## How to reproduce in under 60s (fresh clone)

The whole scoreboard reproduces on committed fixtures -- no private corpus needed:

```
# slim install
pip install -r requirements-predictor.txt        # or: pip install -e .  -> cv-matchup/cv-predict/cv-live

# pregame quality vs the market close (fixture path, prints the scoreboard table)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof

# in-game quality, conditional vs static (fixture path)
python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof

# one matchup, pregame + in-game, via the unified CLI
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0
```

The `--corpus tests/fixtures/proof` path runs every harness on a small committed synthetic
slice (PRINT-ONLY; it never overwrites the canonical `vault/_Edge_Maps` reports). It proves
the harnesses run end-to-end in a fresh clone. The CANONICAL NUMBERS below are produced by the
SAME modules run on the full private corpora (`data/domains/<sport>`), recorded in
`vault/_Edge_Maps/_Beat_The_Close.md` and `vault/_Edge_Maps/_Ingame_Scoreboard.md`.

Runtime classes: **fast** = seconds on the committed fixture (`--corpus tests/fixtures/proof`).
**heavy** = the full-corpus run (`data/domains/<sport>`, minutes; private data, the canonical
numbers source).

---

## Headline results (CANONICAL NUMBERS; calibration/sharpness, never a $ edge)

### Beat-the-close (PREGAME, leak-free OOS held-out 2nd half; lower = sharper)
Source: `vault/_Edge_Maps/_Beat_The_Close.md`. Lower Brier/RMSE wins.

| Sport / market | Metric | Our model | Close | Verdict | Why |
|---|---|---|---|---|---|
| NBA moneyline | Brier | 0.1735 | 0.1672 | MATCH (within noise) | MOV-aware Elo matches the devigged close |
| NBA total O/U | RMSE | 19.17 | 18.11 | BEHIND | injury/lineup freshness a box model cannot see |
| MLB moneyline | Brier | 0.2429 | 0.2390 | MATCH | tiny deficit = pitcher-blindness (close prices the SP) |
| MLB total O/U | RMSE | 4.72 | 4.44 | BEHIND | park / weather / SP freshness |
| Soccer O/U-2.5 | Brier | 0.2465 | 0.2390 | MATCH | pooled Platt recalibration |
| Tennis ATP ml | Brier | 0.2177 | 0.2028 | BEHIND | ATP closes are very efficient |

Thesis: pregame MATCHES the devigged close on team-strength markets and is BEHIND on
totals / ATP ONLY by freshness data the market sees and we cannot. That gap is data-bound,
not a model defect.

### In-game (CONDITIONAL on realized state beats the static pregame line; all 4 WIN)
Source: `vault/_Edge_Maps/_Ingame_Scoreboard.md`. Lower Brier = sharper.

| Sport | Checkpoint | Static (pregame) -> Conditional | Verdict |
|---|---|---|---|
| NBA | end Q1/Q2/Q3 | 0.209 -> 0.159 Brier | WIN |
| MLB | after inning 3/5/7 | 0.241 -> 0.126 Brier | WIN |
| Soccer 1X2 | half-time | 0.626 -> 0.502 Brier | WIN |
| Soccer O/U-2.5 | half-time | 0.264 -> 0.176 Brier | WIN |
| Tennis | after set 1 | 0.219 -> 0.151 Brier | WIN |

The sharpest forecaster FUSES the pregame intelligence (ratings) AS THE PRIOR with the
realized state -- not either alone. This is the decisive measured + calibrated + delivered
edge, 4/4 sports. A live book also sees the state, so this is forecaster QUALITY, not a $ edge.

---

## The proof modules

Leak-guard column shows HOW each stays honest. All modules: never edit `src/` or `kernel/`;
`<= 300 LOC`; calibration/accuracy only, no $ edge claimed.

### Consolidated scoreboards (run these first)

| Module | Claim it backs | Leak guard | Runtime | Reproduce |
|---|---|---|---|---|
| `scripts/platformkit/beat_the_close_scoreboard.py` | All 6 pregame rows: our model vs devigged close | Delegates to the per-market harnesses below (each leak-free) | fast (fixture) / heavy (real) | `python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof` |
| `scripts/platformkit/ingame_scoreboard.py` | All in-game rows: conditional vs static | Delegates to the per-sport in-game harnesses (each leak-free) | fast (fixture) / heavy (real) | `python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof` |

### NBA

| Module | Claim it backs | Leak guard | Runtime | Reproduce |
|---|---|---|---|---|
| `proof_nba/ml_accuracy.py` | NBA moneyline MATCH (Brier 0.1735 vs 0.1672) | MOV Elo updated AFTER each game snapshot; close is comparison forecaster only, never a model input | heavy | `python -m scripts.platformkit.proof_nba.ml_accuracy` |
| `proof_nba/asof_box_accuracy.py` | NBA totals RMSE-vs-close (the BEHIND-by-freshness row) | EW points-for/against snapshot-before-update; close used only as comparison | heavy | `python -m scripts.platformkit.proof_nba.asof_box_accuracy` |
| `proof_nba/totals_calibration.py` | NBA O/U totals calibration (ECE/Brier + Gaussian sigma) | Walk-forward EW model, snapshot-before-update; sigma fit on 1st half, applied to 2nd | heavy | `python -m scripts.platformkit.proof_nba.totals_calibration` |
| `proof_nba/totals_with_availability.py` | Tests whether AVAILABILITY closes the totals gap (freshness attribution) | Uses only WHO is a pre-game-known 0-min scratch + their PRIOR ppg; strict 0-min filter excludes in-game injuries | heavy | `python -m scripts.platformkit.proof_nba.totals_with_availability` |
| `proof_nba/ingame_accuracy.py` | NBA in-game WIN (0.209 -> 0.159 Brier) + ECE recal | Mid-game state at end Q1/Q2/Q3 reconstructed leak-free (later quarters never seen); recalibrator fit on TRAIN games only | heavy | `python -m scripts.platformkit.proof_nba.ingame_accuracy` |
| `proof_basketball_nba/run_proof.py` | NBA adapter calibration + structure (V1 report) | Walk-forward; F5 import-isolation (zero other-sport / src.data) | heavy | `python -m scripts.platformkit.proof_basketball_nba.run_proof --corpus data/domains/basketball_nba` |

Supporting NBA totals studies (calibration / ablation, all leak-free walk-forward):
`proof_nba/totals_ensemble.py`, `proof_nba/totals_pace_efficiency.py`,
`proof_nba/totals_with_rest.py`, `proof_nba/totals_with_availability.py`,
`proof_nba/fusion_nba.py`.

### MLB

| Module | Claim it backs | Leak guard | Runtime | Reproduce |
|---|---|---|---|---|
| `proof_mlb/beat_the_close_ml.py` | MLB moneyline MATCH (Brier 0.2429 vs 0.2390) | Walk-forward MOV-Elo updates AFTER snapshot; held-out 2nd half; close is comparison only | heavy | `python -m scripts.platformkit.proof_mlb.beat_the_close_ml` |
| `proof_mlb/beat_the_close_total.py` | MLB totals RMSE-vs-close (BEHIND-by-freshness) | Run-rate lambdas snapshot BEFORE result folded in; RMSE on held-out 2nd half | heavy | `python -m scripts.platformkit.proof_mlb.beat_the_close_total` |
| `proof_mlb/ingame_accuracy.py` | MLB in-game WIN (0.241 -> 0.126 Brier) | Pregame = walk-forward Elo before update; mid-game = cumulative runs through inning k (innings>k never seen); recal fit on TRAIN only | heavy | `python -m scripts.platformkit.proof_mlb.ingame_accuracy` |
| `proof_mlb/curve_oos.py` | OOS-validates the per-inning run curve (TRAIN 2010-16, VAL 2017-21) | Era-split: curve fit on TRAIN era only; VAL era never touches the fit; RMSE+bias never MAE | heavy | `python -m scripts.platformkit.proof_mlb.curve_oos` |
| `proof_mlb/ingame_tto.py` | Tests times-through-order / bullpen lambda decay (in-game sharpening) | Era-split OOS (fit 2010-16, validate 2017-21); innings>checkpoint never seen; RMSE+bias | heavy | `python -m scripts.platformkit.proof_mlb.ingame_tto` |
| `proof_mlb/run_proof.py` | MLB gate honesty (>=2 corpora NL+AL; rest/streak/h2h all REJECT) | F5 import-isolation; REJECT is the success criterion | heavy | `python -m scripts.platformkit.proof_mlb.run_proof --corpus data/domains/mlb` |

### Soccer

| Module | Claim it backs | Leak guard | Runtime | Reproduce |
|---|---|---|---|---|
| `proof_soccer/beat_the_close_ou.py` | Soccer O/U-2.5 MATCH (Brier 0.2465 vs 0.2390) | EW Poisson ratings emit strictly pre-match snapshot; pooled Platt fit on 1st half, applied to 2nd; close is comparison only | heavy | `python -m scripts.platformkit.proof_soccer.beat_the_close_ou` |
| `proof_soccer/beat_the_close_1x2.py` | 1X2 beat-close (honest DATA NULL: corpus is O/U-2.5-only, no 1X2 close to devig) | Walk-forward lambdas/rho strictly pre-match; returns ok=False with the data explanation (a documented null, not a failure) | heavy | `python -m scripts.platformkit.proof_soccer.beat_the_close_1x2` |
| `proof_soccer/ingame_ht_accuracy.py` | Soccer in-game WIN (1X2 0.626 -> 0.502; O/U-2.5 0.264 -> 0.176) | Halftime score = leak-free minute-45 state; full-time result is the future outcome; held-out split | heavy | `python -m scripts.platformkit.proof_soccer.ingame_ht_accuracy` |
| `proof_soccer/division_calibration.py` | Per-division O/U-2.5 recalibration (ECE improvement, not edge) | Walk-forward leak-free engine; per-division recalibrators fit on earlier split, evaluated on held-out later split | heavy | `python -m scripts.platformkit.proof_soccer.division_calibration` |
| `proof_soccer/run_proof.py` | Soccer gate honesty (rest/totals-form/h2h all REJECT) | Walk-forward; REJECT is the success criterion; devigged Pinnacle expected to beat the model | heavy | `python -m scripts.platformkit.proof_soccer.run_proof --corpus data/domains/soccer` |

### Tennis

| Module | Claim it backs | Leak guard | Runtime | Reproduce |
|---|---|---|---|---|
| `proof_tennis/beat_the_close_ml.py` | ATP match-win BEHIND (Brier 0.2177 vs 0.2028) | NEVER uses winner-order; predicts P(p1 wins) on the SYMMETRIC p1_id<p2_id ordering; Elo walk-forward; Platt on strictly-prior rows; close is comparison only | heavy | `python -m scripts.platformkit.proof_tennis.beat_the_close_ml` |
| `proof_tennis/ingame_accuracy.py` | Tennis in-game WIN (0.219 -> 0.151 Brier) | State = within-match ROLE fixed by the SET RESULT (set-1 leader), NOT the match outcome; label = match winner (the future); Elo walk-forward | heavy | `python -m scripts.platformkit.proof_tennis.ingame_accuracy` |
| `proof_tennis/ingame_bo5.py` | Best-of-5 (Grand Slam) in-game coverage extension | Same set-result-role / match-outcome-label pattern; no later-set info enters an earlier checkpoint; Elo walk-forward | heavy | `python -m scripts.platformkit.proof_tennis.ingame_bo5` |
| `proof_tennis/ingame_calib.py` | In-game ECE + leak-free TRAIN/EVAL recalibrator | Held-out preds split chronologically; recalibrator fit on TRAIN half only, applied to EVAL, never refit on eval | heavy | `python -m scripts.platformkit.proof_tennis.ingame_calib` |
| `proof_tennis/wta_recal.py` | WTA-native calibration gate-test (thin-prior hypothesis) | WTA-native walk-forward Elo + walk-forward Platt; min-prior-match filter on eval | heavy | `python -m scripts.platformkit.proof_tennis.wta_recal` |
| `proof_tennis/wta_recal_temp_iso.py` | WTA temperature + isotonic recal (over-confidence fix; honest persistent-FAIL allowed) | Temperature / isotonic fit on strictly-prior rows; ECE reported per eval window | heavy | `python -m scripts.platformkit.proof_tennis.wta_recal_temp_iso` |
| `proof_tennis/wta_temp_live.py` | WTA live temperature recalibrator (T=1.36; holdout ECE 0.045 -> 0.019) | Temperature fit on holdout-respecting split; calibration win, not a market row | heavy | `python -m scripts.platformkit.proof_tennis.wta_temp_live` |
| `proof_tennis/run_proof.py` | Tennis gate honesty (fatigue/surface/h2h all REJECT) | Walk-forward; REJECT is the success criterion; devigged Pinnacle expected to beat the Elo | heavy | `python -m scripts.platformkit.proof_tennis.run_proof --corpus data/domains/tennis` |

### Shared / cross-sport infrastructure

| Module | Role |
|---|---|
| `proof_common/runner.py`, `proof_common/spec.py`, `proof_common/paper.py` | V1/V2/V3/V4 proof scaffold reused by every sport's `run_proof.py` |
| `proof_common/equivalence_check.py` | Byte-identical / equivalence verification |
| `proof_<sport>/gate_test_asof.py` | As-of (leak-free snapshot) gate tests per sport |
| `proof_<sport>/fusion_<sport>.py` | Fusion (pregame prior + realized state) studies per sport |
| `proof_tennis/kernel_manifest.py` | Sport-blind kernel import-isolation manifest |

---

## Leak-free / OOS discipline (the rigor that is the sell)

Every harness obeys the same binding rules, and they are visible in the code, not asserted:

- **Snapshot-before-update / walk-forward.** Ratings (Elo, EW Poisson, run-rate lambdas)
  emit a strictly pre-event snapshot; the result is folded in only AFTER. No feature can see
  its own outcome.
- **The close is a comparison forecaster, never a model input.** The devigged closing line is
  read only to score against; it never enters the model.
- **Held-out OOS evaluation.** Pregame proofs warm up on the first chronological half and
  score the held-out second half. MLB curve / TTO use an era split (fit 2010-16, validate
  2017-21). Recalibrators are fit on a TRAIN split only and applied to held-out -- never
  refit on the eval set.
- **In-game state is reconstructed leak-free.** Later quarters / innings / sets are never read
  at an earlier checkpoint. Tennis avoids winner-ordering by framing the state as a set-result
  ROLE and the label as the (future) match outcome.
- **Point forecasts graded RMSE + signed bias, never MAE** (MAE rewards shrink-to-median
  artifacts).
- **Import-isolation (F5).** Each sport's `run_proof.py` imports zero other-sport domain code
  and zero `src.data` / `src.sim` / `src.tracking` / `src.pipeline`, proving the adapter is
  self-contained.

---

## The honest framing (binding)

- **Honest nulls and MATCH verdicts are successes.** Matching the devigged close within
  sampling noise is the realistic best case for an efficient market -- beating it would imply
  information the close lacks. We claim the MATCH, not an edge.
- **The BEHIND rows are data-bound, not defects.** NBA/MLB totals and ATP match-win trail by
  the freshness data (injuries, lineups, park, weather, starting pitcher) the market sees and
  a public/box model cannot. The `totals_with_availability` proof tests that attribution
  directly.
- **The in-game conditioning edge is the measured, calibrated, delivered advantage, 4/4
  sports.** It is forecaster QUALITY (a live book also sees the state), not a $ edge.
- **No $ edge, no ROI, no "beat the close."** Numbers here are Brier / RMSE / ECE only. The
  single honesty truth-source for figures is `docs/JOB_EVIDENCE_PACKET.md`; retracted /
  inflated numbers are listed there (and in `docs/KNOWN_LIMITATIONS.md`) in explicit
  retraction context and appear nowhere else. The strongest signal in this repo is that the
  instruments above caught and retracted their own over-claims.
