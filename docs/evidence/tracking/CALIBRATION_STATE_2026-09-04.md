# Basketball calibration: what tonight's measurements settled

**Date:** 2026-09-04. **Status:** synthesis of landed rows. **No code, threshold,
gate, bar, verdict or register row is changed here.** Every number below is
quoted from a landed ledger row or recomputed by the orchestrator in master; the
provenance is named inline so a reader can check it.

This amends the standing design document
[`CALIBRATION_STRATEGY_2026-09-02.md`](CALIBRATION_STRATEGY_2026-09-02.md),
which remains correct in its geometry survey and its anti-patterns. **What it can
no longer support is its diagnosis of what basketball is missing.**

---

## 1. The one-paragraph state

The fitter and the court model are **not** the problem, the detector's line
geometry is, and **no in-repo option improves that geometry.** Meanwhile a human
census says the footage is far more solvable than our detectors achieve. The
classical in-repo route is exhausted; the remaining paths are a trained model or
labelling, and the viability of labelling turns on a propagation horizon that is
being measured now (G222).

---

## 2. What is settled, with provenance

| Claim | Measurement | Row |
|---|---|---|
| The four-point fitter and the court model introduce **zero** error | exact lines through the labelled corners give **17/17 at 0.000000 px** through the same unchanged `solve_line_pairs` and G205 `score_frame` | G217 |
| All of the oracle's error is **detected line geometry** | selected detected lines miss their labelled corners by **median 10.234792 px, max 59.693249 px** over 68 selections | G217 |
| The error is **scatter, not bias** | every role straddles zero under a fixed sign convention; angle and offset both present, neither dominating (median 6.967785 px offset vs 6.856946 px angle); corner error does not track shallowness (rank assoc. **-0.1225**) | G223 |
| **No deterministic correction exists** | a painted-edge-to-centreline shift would need a stable one-signed residual surviving the 11.39 px label floor; there is none | G223 |
| The tennis **top-hat** evidence transfer makes basketball **worse** | oracle **1/17 at 28.841316 px -> 0/17 at 60.048887 px**; proposals fell 1,928.06 -> 367.53/frame, which does not redeem it | G224 |
| The **semantic quad provider** never fires | **0/17, 0/68, and 17/17 ABSTENTIONS** -- it selects no paint quad at all, despite plentiful contours (1,970 / 1,955 / 817 raw) | G227 |
| Line-segment detectors are exhausted | LSD **0/17** (G205, G210b), M-LSD **0/17** reproduced on the pod (G208, G214) | G205/G208/G210b/G214 |
| The footage is **not** the limit | human census: paint **PAINT_SOLVABLE in 1,029/1,650 = 62.36 pct**, Wilson 95 pct [0.6000, 0.6467], spread through every clip | G68D |
| The construct is **not** stacked against us either | all **68** G140 targets are `status = target`, and **all 17 frames carry all four roles** (orchestrator-verified in master) | G140 |

---

## 3. The correction to the standing strategy document

`CALIBRATION_STRATEGY_2026-09-02.md` section 1.2 states that what basketball
lacks is **role assignment** -- that nothing maps candidate line groups to
baseline / free_throw / lane_low / lane_high, and that the tennis pattern of
"orientation split, then role pinning by termination structure" should be built.

**That work should not be funded on the expectation that it will lift the
result, and here is the argument.**

G210b's `oracle_fit` (`g210b_court_fit_untruncated_search.py:114`) already
performs **perfect role assignment**: for each true paint line it picks, from the
detector's own groups, the one whose line passes closest to the two labelled
corners, and then solves from that group's geometry. **Labels are used only to
CHOOSE; the line geometry is the detector's.**

**So the oracle IS the upper bound on any role-assignment method, and the oracle
scores 1/17 at 28.841316 px.** A termination-structure role assigner, however
elegant, is bounded above by a number that already fails. **Role assignment is
not the missing piece. Line accuracy is.**

Note this also corrects a claim I made earlier and have already retracted in the
ledger: the G214 row concluded that "a better line detector cannot lift the
result much", reasoning from the same oracle. **That inference was backwards.**
The oracle bounds *selection*, not *accuracy*, so a more accurate detector is
exactly the thing that could help -- it is simply that every detector we have
tried is not more accurate.

---

## 4. What is genuinely open

1. **A trained model.** Untried for basketball. Any such row **must cite G31**,
   which closed a trained calibration path AT LIMIT for tennis, and say why
   basketball differs. G214 established the licence and packaging rails that
   blocked zero-shot learned detectors: ELSED needs an OpenCV dev package absent
   from a shared pod image, HAWP pulls LGPL-3.0 `easydict`, and DeepLSD and KpSFR
   have `LICENCE-UNVERIFIED` weights.
2. **Labelling plus propagation.** G196 showed four hand-labelled corners project
   correctly with the three-point arc landing out-of-sample, so a seed works.
   G215 showed chained propagation holds about **50 frames** (10.88 px drift at
   50, 38.47 at 100, 187.77 at 300) and decays from an ordinary camera pan alone.
   **At 50 frames a one-hour 30 fps clip needs roughly 2,000 hand labels, which
   is not viable. G222 is measuring whether direct-to-seed matching removes the
   compounding**; that number decides whether this path is open or closed.
3. **Why the quad provider abstains.** G227 left the rejecting gate explicitly
   NOT VERIFIED. **G229 is measuring it now.** If a single gate is binding with a
   small margin, the "closed at limit" verdict on that candidate should be
   amended; if no candidate is near any gate, the closure is strengthened.

---

## 5. A separate blocker that is not calibration at all

**Basketball has never been scored by the harness once.** G207's census:
`wnba` 0 scored / 2 EXCLUDED, `ncaa_basketball` 0 scored / 1 EXCLUDED, all for
**noncanonical columns** -- while football scored 3, kbo 8, mlb 12, npb 3,
soccer 3 and tennis 3. The legacy table emits `frame, timestamp, player_id,
team, x_position, ...` and declares **no `coordinate_space`, no
`calibration_provenance`, no `projection_status`**, so the harness cannot audit
its frame of reference. **Even a solved homography would not have made those
tables scorable.** G226 built a basketball adapter emitting the canonical schema
with honest `image_px` provenance; G226b then found it **absent from the pod**,
with `POD_GIT_PRESENT=no` and no incremental deploy path. That deployment is
held as a gated decision.

---

## NOT VERIFIED

- Whether a trained basketball calibration model would work; nothing was trained
  or evaluated, and the licence/packaging rails from G214 still apply.
- Whether direct-to-seed propagation extends the horizon (G222, in flight).
- Which gate rejects in the quad provider (G229, in flight).
- Whether the basketball adapter emits a canonical table on real footage; it has
  unit tests only and has never run on a clip.
- Every number here is from a small exhaustive construct of **17 frames** with
  **single-source eye labels** whose p90 repeatability is **11.39 px**. The 12 px
  threshold sits at that floor. These measure these frames, not a rate.
- G68D's 62.36 pct is a **human** solvability judgement on 1,650 sampled tiles
  from 11 clips; it is not a claim that any automatic method could reach it.
