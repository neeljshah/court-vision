# S132 + S133 -- the NBA "close" stops being a post-tip in-play quote, and the MLB pick'em quotes come back (2026-09-03)

Rows: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S132 (the NBA in-play close) and S133 (the
placeholder / ambiguity attach), both filed from `docs/evidence/harness/REDTEAM_ROUND2_2026-09-03.md`
sections F1, F12 and F16. Named by the register id of the NBA-close row (S132); the red-team memo's
own draft ids were S139/S140.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked in section 6).
Calibration language only. **NOT VERIFIED** -- this is the lane's own report; no independent
verifier has re-run it.

---

## VERDICT

**Both premises HELD and both are FIXED. The NBA close corpus survives at 563 of 1,814 events
(was 952), well above the 300 bar, so it is NOT closed at limit -- but 389 of the old 952 were
contaminated in-play ticks and every NBA number in S112/S113 was measured against a reference that
partly contained the answer.** On the clean reference the NBA close still beats Elo, by
**+0.021819** instead of the published **+0.025606** (declared-cluster CI `[+0.010468, +0.033170]`,
p = 4.82e-04, 30 clusters, n 351 -> 171): the sign and the verdict hold, the headline number does
not. On MLB the fix runs the other way -- 16 genuine pick'em closes return (894 -> 910) -- and the
close-vs-Elo interval **crosses zero for the first time**: +0.007269 CI `[+0.000066, +0.014473]`
p = 0.0481 becomes +0.006709 CI `[-0.000198, +0.013617]` p = 0.0564. That is an honest NULL where
S112 read a marginal positive, and it is the one verdict-shaped change in this lane.

Every model arm is still a NULL against the close, before and after, on both sports. No arm clears
`+0.004` with a CI excluding zero. Uncharged: `_charge_ledger` never called,
`data/cache/eval_gate/backtest_fwer.jsonl` never opened (18 rows, unchanged), `data/registry/`
untouched, no flag flipped ON, nothing read or written under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/`, no pod contact, no push.

---

## 1. STEP 0 -- PREMISE (Q8): BOTH HELD, reproduced from disk before any edit

Probe: session scratchpad `step0.py`, reading `data/cache/inplay_odds/nba_checkpoints_full.parquet`
and the live MLB price series through the module's own functions.

### S132 -- the NBA first-in-play tick

```
n first traded period-1 ticks      1591
close_sec_after_tip median 21.0 mean 23.0 p90 46.0 p99 60.1 max 408.0
share <= 30 s                      0.6738  (outside 0.3262)
share with any points on board     0.4349
share with margin != 0             0.3953
|margin| mean 0.908 max 6 ; points mean 1.29 p90 4 max 37
among <= 30 s ticks, share with points on board  0.2836
GENUINELY PRE-SCORING (margin==0 & pts==0 & sec<=30)  768 of 1591 = 0.4827
```

The red-team numbers reproduce: **43.49 pct** carry points (memo 43.5), **32.62 pct** sit outside
the 30 s window (memo 32.3 -- the store has grown by a handful of ticks since; max seconds-after-tip
is now 408, not 391), and **28.36 pct** of the inside-30-s subset already carry a score (memo 28.4).
Fewer than half of the ticks (48.27 pct) are genuinely pre-scoring.

### S133 -- the placeholder rule and the ambiguity fall-through

```
mlb_close kept 894 ; drops {placeholder_half: 19, ambiguous_event_id: 0, no_spine_match: 22, ...}
  prob_home 0.52 prob_away 0.52 -> p_close 0.500000  DROPPED
  prob_home 0.55 prob_away 0.48 -> p_close 0.533981  kept
  prob_home 0.50 prob_away 0.50 -> p_close 0.500000  DROPPED
```

19 live MLB events dropped of 894 kept, and the mechanism reproduces through the real `cjm._devig`:
a symmetric-but-not-placeholder raw quote (0.52/0.52) devigs to exactly 0.500 and was deleted by a
rule written for the untraded 0.500/0.500 listing.

The ambiguity fall-through is real as a MECHANISM but currently unexercised on the pregame side:
`nba_close_corpus.parquet` has **0** duplicated `game_id`s today, while the in-play tick side has
**10** duplicated rows. So no live NBA game is presently downgraded by it -- an honest correction to
the red-team draft row, which showed the effect on a constructed pair. The guard is still needed:
nothing in the old code recorded a downgrade if one occurred.

---

## 2. THE CHANGE (`scripts/platformkit/eval_gate/close_join_nba_mlb.py`, 298 -> 337 lines)

(a) **`nba_first_inplay_tick` now accepts a tick as a close only when it is pre-scoring.**
`score_home`, `score_away` and `margin` are read from the checkpoint store; the frame carries a new
`close_score_on_board` column (added to `CLOSE_COLUMNS`, so `screen_predictor` keeps dropping it
from the feature table -- it can never be screened). A tick that is not
`margin == 0 and close_score_on_board == 0 and close_sec_after_tip <= 30` becomes
`close_source = "inplay_contaminated"` with `p_close = NaN` and is counted in
`drops["inplay_contaminated"]`. `allow_contaminated=True` (threaded through `nba_close` and
`build_close_corpus`, plus a `--allow-contaminated` CLI flag) reproduces the old behaviour byte for
byte, for A2 comparisons only. **Default is the clean rule.**

(b) **The MLB placeholder rule moved BEFORE the devig.** `_drop_placeholder` is now documented and
used as a ONE-SIDED-quote rule only; `mlb_close` drops the raw `prob_home == prob_away == 0.500`
listing instead, so a devigged 0.500 from an asymmetric quote survives.

(c) **`_drop_ambiguous` became `_mark_ambiguous`.** A duplicated `event_id` now yields ONE row with
`close_source = "ambiguous"` and `p_close = NaN` rather than vanishing, and `nba_close` ranks its
two sources through a named `_SOURCE_RANK` (`pregame 3 > ambiguous 2 > first_inplay_tick 1 >
inplay_contaminated 0`) instead of an equality test, so an ambiguous pregame close outranks the
in-play tick and the downgrade cannot happen unrecorded. The same marking applies in `mlb_close`
(0 rows affected today).

`scripts/platformkit/foundry/screen_predictor.py` needed **no edit**: `corpus_states` already
filters `corpus[corpus["p_close"].notna()]`, so the contaminated and ambiguous rows drop out of the
served window automatically, and `CLOSE_COLUMNS` is imported, so the new column is dropped from the
feature table without a change. Its docstring still says "the six close columns"; that prose is now
one short (seven), left alone because this lane owns that file only for the incumbent filter.

`s112_rescore_vs_close.py` needed no edit either: `close_map` already filters `p_close.notna()`.

**Per-file tests:** `python -m pytest tests/platformkit/eval_gate/test_close_join_nba_mlb.py -q`
= **10 passed in 2.05 s** (was 8). Three cover this lane:
`test_nba_tick_with_points_on_the_board_is_not_a_close` (a 2-0 tick and a 2-2 tick inside the 30 s
window are both labelled and priceless, a 0-0 one is kept, `allow_contaminated=True` restores all
three), `test_nba_ambiguous_pregame_close_does_not_downgrade_to_the_tick` (two venue rows for one
game -> `ambiguous`, NaN, the tick never wins), and the extended
`test_mlb_placeholder_half_excluded_and_counted` (a new 0.52/0.52 fixture game devigs to exactly
0.500 and SURVIVES while the raw 0.500/0.500 listing is still dropped and counted).
Regression: `tests/platformkit/foundry/test_screen_predictor.py` = **5 passed**.

The file is 337 lines, over the 300-line rail. Precedent in the same directory:
`calibration_report.py` 358, `family_bars.py` 324, `close_join.py` 315. Stated, not hidden.

---

## 3. THE REBUILT CORPORA

The pre-fix artifacts are kept beside the new ones as
`data/cache/combo/gate_corpus_{nba,mlb}_close_pre_s132.parquet` +
`gate_corpus_{nba,mlb}_close.sources_pre_s132.json`, and the S112 differentials as
`data/cache/eval_gate/s112_rescore_2026-09-03_{nba,mlb}_fullmodel_pre_s132.csv` and
`s112_rescore_2026-09-03_pre_s132.json`. (`data/` is gitignored; these are local artifacts.)

| | nba before (S112) | nba after | mlb before | mlb after |
|---|---|---|---|---|
| rows with a close | **952** | **563** | 894 | **910** |
| coverage of the gate corpus | 52.48 pct | **31.04 pct** | 2.28 pct | 2.32 pct |
| `pregame_last_tick_before_commence` | 220 | **220** | - | - |
| `first_inplay_tick` | 732 | **343** | - | - |
| `inplay_contaminated` (attached, priceless) | - | **389** | - | - |
| `ambiguous` (attached, priceless) | - | 4 | - | 0 |
| `placeholder_half` dropped | 160 (nba, one-sided) | 160 | 19 | **5** |
| within 30 s of tip | 523 | 382 | 0 | 0 |

**563 >= 300, so the NBA close corpus is NOT CLOSED AT LIMIT** -- but 61 pct of its old population
was in-play, and the honest label for every NBA number published in S112 and S113 is **"vs a
partly-contaminated reference"**. The clean corpus is 220 genuinely pregame closes plus 343 ticks
that are 0-0 inside 30 s of tip.

**MLB: 16 of the 19 dropped events return.** The other 3 really were raw 0.500/0.500 listings and
stay dropped; 2 more raw placeholders were also spine-unmatched, which is why `no_spine_match` moves
22 -> 20. So the register's "the 19 MLB rows return" is 16, and the reason for the other 3 is named.

---

## 4. RE-SCORE -- S112 ARM (a), CLEAN CLOSE vs CONTAMINATED CLOSE

`s112_rescore_vs_close.full_model_vs_close` IMPORTED unchanged (no charge, no seal, no ledger).
The `>= 5 outer folds` bar is NOT lowered (Q3): S112 itself raised `k` for mlb (6 -> 7) for exactly
this reason, and the smaller clean NBA window needs the same treatment, so `k` is raised to the
smallest value that meets the unchanged bar -- **nba 6 -> 8**, mlb 7 (unchanged).

| | nba contaminated (S112) | nba clean | mlb contaminated (S112) | mlb clean |
|---|---|---|---|---|
| screen events with a close | 492 | **308** | 442 | **450** |
| rows scored | 351 | **171** | 276 | **281** |
| outer folds `k` | 6 | **8** | 7 | 7 |
| Brier Elo | 0.211728 | 0.213312 | 0.250970 (recomputed) | 0.250970 |
| Brier close | **0.186122** | **0.191493** | 0.243700 | 0.244261 |
| close minus Elo | **+0.025606** | **+0.021819** | **+0.007269** | **+0.006709** |
| declared-cluster CI | [+0.015252, +0.035960] | **[+0.010468, +0.033170]** | [+0.000066, +0.014473] | **[-0.000198, +0.013617]** |
| DM p / clusters | 2.16e-05 / 30 | **4.82e-04 / 30** | 0.0481 / 26 | **0.0564 / 26** |

**A2:** the contaminated column is recomputed by this lane from S112's own archived differential
(`..._pre_s132.csv`) and reproduces the published `+0.025606`, `[+0.015252, +0.035960]`,
`p = 2.16e-05`, 30 clusters to the printed digits, and mlb's `+0.007269` likewise.

**So `+0.025606 vs Elo` DOES change -- to `+0.021819`.** The clean close is measurably less sharp
(Brier 0.186122 -> 0.191493), which is what contamination predicts: part of the old reference's
sharpness was the scoreboard. The sign, the CI-excludes-zero property and the verdict are unchanged
on NBA. On MLB the point estimate barely moves but **the interval now includes zero**: the marginal
"the close beats Elo" reading in S112 (p = 0.0481) is a NULL on the clean attach (p = 0.0564).

Model arms, improvement vs the close (bar `+0.004`, CI must exclude zero):

| sport | arm | contaminated | clean | clears bar? |
|---|---|---|---|---|
| nba | elastic_net | -0.040888 | -0.070107 | no -> no |
| nba | hgb_offset | -0.007784 | -0.008749 | no -> no |
| mlb | elastic_net | -0.022663 | -0.003120 | no -> no |
| mlb | hgb_offset | -0.005575 | -0.004825 | no -> no |

Every arm is BEHIND the close before and after. **No verdict flips.**

---

## 5. RE-SCORE -- S113's LOCAL FACTORY SCREEN ON THE CLEAN CLOSE

Same recipe as S113: `seed_queue --frozen --sport <s>` into a scratch sqlite (nba **1,440** and
mlb **486** enumerated, reproducing S113 exactly), then
`foundry_runner --predictor real --sport <s> --screen-rows 800 --batch 200 --idle-exit` with a
scratch `--db`, `--trials-dir` and `--ledger` and `FOUNDRY_CLOSE_INCUMBENT=1`. `--allow-charge` was
NOT passed: every promotion printed `promotions_held ... reason=allow_charge_off`, `charges=0` on
every pass, and the scratch ledger file was never created. **Only the close arm was re-run** -- the
Elo control never reads the close corpus, so S113's archived
`docs/evidence/harness/S113/promotions_vs_elo_control.md` is still the correct control and is used
unchanged.

**A2 on the baseline:** S113's published `147 of 240 (61.3 pct)` recomputes exactly from its two
archived promotion lists (240 control, 216 close, 147 vanishing) before anything of this lane runs.

### Served window

| sport | S113 (contaminated) | clean |
|---|---|---|
| nba served window | 499 | **313** |
| mlb served window | 452 | **460** |
| nba screen partition sha | `1980f64c6a21fc1e` | `00ce09cab113d25d` |
| mlb screen partition sha | `bee51ac662607eb5` | `5802cb7ab18516c8` |

### Best improvement per family vs the CLEAN close (95 pct CI recomputed from the archived differential alone)

| family | n screens | beat the close | promoted | best improvement | 95 pct CI | n | clusters | screen DM p |
|---|---|---|---|---|---|---|---|---|
| mlb_bullpen_relief_chains | 32 | 0 | 20 | -0.002257 | [-0.005205, +0.000691] | 460 | 29 | 0.1281 |
| mlb_gate | 16 | 0 | 16 | -0.002568 | [-0.005895, +0.000758] | 460 | 29 | 0.1249 |
| nba_boxdetail | 250 | 0 | 20 | -0.000036 | [-0.004083, +0.004012] | 313 | 30 | 0.9857 |
| nba_carryover | 50 | 5 | 20 | +0.000602 | [-0.002935, +0.004140] | 313 | 30 | 0.7303 |
| nba_defender_rollup | 72 | 10 | 20 | +0.000855 | [-0.002586, +0.004296] | 313 | 30 | 0.6153 |
| **nba_gate** | 88 | 12 | 20 | **+0.002302** | **[-0.003129, +0.007733]** | 313 | 30 | 0.3932 |
| nba_opp_allowed | 120 | 8 | 20 | +0.001708 | [-0.002606, +0.006022] | 313 | 30 | 0.4247 |
| nba_player_adv | 48 | 0 | 20 | -0.000233 | [-0.005189, +0.004722] | 313 | 30 | 0.9239 |
| nba_player_value_features | 32 | 0 | 20 | -0.000072 | [-0.004708, +0.004565] | 313 | 30 | 0.9750 |
| nba_quarter_shape | 125 | 4 | 20 | +0.002079 | [-0.001973, +0.006131] | 313 | 30 | 0.3027 |
| nba_team_adv | 112 | 4 | 20 | +0.001620 | [-0.003815, +0.007055] | 313 | 30 | 0.5469 |

Best of all 11 families: **+0.002302** against the unchanged `+0.004` bar, CI including zero,
DM p 0.39. **Still the expected NULL** -- S113's headline best was `+0.000640`; the clean reference
raises it but not past the bar and not to a CI that excludes zero. Screens that beat the incumbent
at all: **43 of 945** on the clean close (S113: 10 of 945; the Elo control: 725 of 977). A less
contaminated close is a slightly easier reference, exactly as the contamination story predicts, and
it is still not beaten.

### Promotions held vs the Elo-relative list

| family | promoted vs Elo (control) | promoted vs clean close | Elo promotions that VANISH |
|---|---|---|---|
| mlb_bullpen_relief_chains | 20 | 20 | 6 |
| mlb_gate | 20 | 16 | 7 |
| mlb_inning | 20 | **0** | 20 |
| nba_boxdetail | 20 | 20 | 15 |
| nba_carryover | 20 | 20 | 11 |
| nba_defender_rollup | 20 | 20 | 12 |
| nba_gate | 20 | 20 | 18 |
| nba_opp_allowed | 20 | 20 | 12 |
| nba_player_adv | 20 | 20 | 11 |
| nba_player_value_features | 20 | 20 | 8 |
| nba_quarter_shape | 20 | 20 | 14 |
| nba_team_adv | 20 | 20 | 20 |
| **TOTAL** | **240** | **216** | **154 (64.2 pct)** |

**So `147 of 240` DOES change -- to `154 of 240` (64.2 pct).** The direction is unchanged and the
conclusion is slightly stronger: on a clean market reference 7 MORE of the 240 Elo-relative
promotions fail to survive. The 216 promoted total is identical (`mlb_inning` still falls entirely
under the unchanged 0.8 coverage floor and `mlb_gate` still fills 16 of 20), so the whole change is
in WHICH hypotheses hold the 216 slots.

---

## 6. CONTRACT SELF-CHECK (sections B and Q)

| rule | status |
|---|---|
| B1 circular metric | No row is excluded to make a metric pass. The excluded set is NAMED and counted (`inplay_contaminated` 389 attached, `ambiguous` 4, `placeholder_half` 160 nba / 5 mlb) and every count is in the rebuilt sidecar report. |
| B2 non-additive schema | `close_score_on_board` is APPENDED to `CLOSE_COLUMNS`; no column renamed or removed. `close_source` gains two values (`inplay_contaminated`, `ambiguous`) -- both only ever on rows whose `p_close` is NaN, and every reader filters `p_close.notna()` first. A5 sweep of every reader of the touched fields: `s112_rescore_vs_close.close_map:66-69`, `foundry/screen_predictor.corpus_states:295-331`, `tests/platformkit/eval_gate/test_close_join_nba_mlb.py`, `tests/platformkit/foundry/test_screen_predictor.py` -- that is the complete set. The other `close_source` hits in the repo (`grade_paper_one`, `prop_settler`, `clv_ledger`, `pm_trading/close_capture`, `shadow_ledger`) belong to the paper-grading ledger schema: a different field, a different producer, untouched. |
| B3 fall-through loss | The opposite of a fall-through: a row that used to vanish (`ambiguous`) or to be silently priced (`inplay_contaminated`) now SURVIVES with a label and no price. Missing is not bad; it is recorded. |
| B4 re-claim loop | None; no queue or claim path is touched. |
| B5 pre-verification deploy | Nothing copied to the pod. No pod contact of any kind. |
| B6 orphans | `_drop_ambiguous` was renamed to `_mark_ambiguous`; it is module-private, absent from `__all__`, and `grep -rn _drop_ambiguous` over the repo returns zero remaining references. |
| B7 head-slice evidence | Q7 applies: every metric here is SCORED over a complete set (all 1,591 first ticks, all 945 screens, all 240 control promotions), not sampled. |
| B8 self-fit as independent | No arm is scored against points used to fit it; `full_model_vs_close` is S108's own walk-forward `_grid_oof`, imported unchanged. |
| B9 degenerate denominator | This lane exists to remove one: the 0.500 placeholder rule now binds the RAW listing, and the in-play "close" that was partly a scoreboard is out of the denominator. |
| B10 moved bar | `IMPROVEMENT_BAR` 0.004, `tiers._COVERAGE_FLOOR` 0.8, `PromotionRule` prereg `b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3` top_n 20 seed 20260903, `s108.OUTER_FOLDS` 6 and the `>= 5 outer folds` minimum are byte-identical to master; `TIP_WINDOW_S` is still 30.0. The only `k` change is the documented raise (nba 6 -> 8) to MEET the unchanged fold minimum, exactly as S112 raised mlb 6 -> 7 for the same reason. |
| Q1 prereg sealed | No scored CLAIM is made -- this lane re-scores existing artifacts and reports the deltas. No prereg written, none needed, none faked. |
| Q2 ledger charged first | Nothing charged. `_charge_ledger` never called; `data/cache/eval_gate/backtest_fwer.jsonl` never opened -- 18 rows, md5 `a4ae7c13995672e478d59770591b83ba`, unchanged. K never read. |
| Q3 no bar lowered | See B10. Where a bar could not be met on the smaller window it was MET by raising `k`, never by lowering the bar. |
| Q4 leak contract | `full_model_vs_close` uses S108's own `folds` / `_grid_oof` (expanding, 2-day gap); the factory screens run through the unchanged `ScreenBinder` + `walk_forward`. |
| Q5 two corpora for an AHEAD | No AHEAD is claimed. Both re-scores are NULL or BEHIND. |
| Q6 calibration language | No dollar / ROI / profit / edge word; none of the retracted figures appears. Every number here is a Brier or a Brier difference. |
| Q7 sampling rail | Metrics are over complete enumerated sets, with n stated on every row. |
| Q8 premise first | Section 1: both premises re-measured from disk BEFORE any edit. Both HELD, with one honest correction (the pregame source currently has 0 ambiguous ids, so the downgrade is a live mechanism with 0 live instances). |
| Q9 archive the differential | `docs/evidence/harness/S132/best_arm_differentials_clean_close.csv` (3,737 rows: `family, hash, event_id, ts, cluster, loss_model, loss_incumbent`) -- every CI in section 5 recomputes from it alone. The S112 arm (a) per-event differentials are in `data/cache/eval_gate/s112_rescore_2026-09-03_{nba,mlb}_fullmodel.csv` (clean) and `..._pre_s132.csv` (contaminated). |

---

## 7. EVIDENCE PATHS

* `scripts/platformkit/eval_gate/close_join_nba_mlb.py` -- the change (337 lines).
* `tests/platformkit/eval_gate/test_close_join_nba_mlb.py` -- 10 passed; `tests/platformkit/foundry/test_screen_predictor.py` -- 5 passed.
* `docs/evidence/harness/S132/promotions_vs_clean_close.md` -- the 216-row clean-close promotion list.
* `docs/evidence/harness/S132/best_arm_differentials_clean_close.csv` -- 3,737 rows (Q9).
* `docs/evidence/harness/S113/promotions_vs_elo_control.md` -- the unchanged 240-row Elo control.
* `data/cache/combo/gate_corpus_{nba,mlb}_close.parquet` + `.sources.json` -- rebuilt (nba 563 of 1,814 covered, mlb 910 of 39,162).
* `data/cache/combo/gate_corpus_{nba,mlb}_close_pre_s132.parquet` + `.sources_pre_s132.json` -- the pre-fix artifacts, kept.
* `data/cache/eval_gate/s112_rescore_2026-09-03_{nba,mlb}_fullmodel.csv` (clean) and `..._pre_s132.csv` / `s112_rescore_2026-09-03_pre_s132.json` (as published by S112).
* Scratch, NOT in the repo: the two sqlite DBs, the trial JSONs and the probe scripts under this session's scratchpad.

`data/` is gitignored, so the parquet and csv artifacts above are LOCAL -- a fresh clone rebuilds
them with `python -m scripts.platformkit.eval_gate.close_join_nba_mlb --sports nba,mlb`.

---

## 8. WHAT IS NOT VERIFIED

* Lane's own report; no independent verifier has re-run any of it.
* The clean NBA close is still 343 of 563 in-play ticks -- 0-0 inside 30 s of tip, but ticks. It is
  a de-facto close, never a pregame price, and `close_kind` still says `VENUE_PROB_ONE_SIDED`.
* The 30 s window is the S112 constant, not a measured optimum. The pre-scoring test
  (`margin 0`, `0 points`) is what removes the contamination; the window is belt-and-braces.
* `close_score_on_board` is 0.0 by CONSTRUCTION for the two pregame sources (before tip / before
  first pitch), not read from a scoreboard feed.
* The ambiguity guard has 0 live instances on the pregame source today; only the in-play side
  exercises it (4 events).
* Only the close arm of the S113 factory was re-run; the Elo control is S113's archived one.
* The pod's live `gate_corpus_{nba,mlb}.parquet` were never rewritten and nothing was shipped.

---

## 9. REGISTER ROW TEXT (for the orchestrator -- HARNESS_GAPS not edited by this lane)

S132: `| S132 | harness | FIXED. Premise HELD and reproduced from disk (43.49 pct of first_inplay_tick closes carry points, 32.62 pct sit 30-408 s after tip, 28.36 pct of the <=30 s subset already carry a score; only 48.27 pct are genuinely pre-scoring). close_join_nba_mlb now accepts an in-play tick ONLY at margin 0, close_score_on_board 0 and close_sec_after_tip <= 30; everything else is close_source=inplay_contaminated with p_close NaN (allow_contaminated=True reproduces the old behaviour for A2). close_score_on_board added to CLOSE_COLUMNS. NBA coverage 952 -> 563 of 1,814 (220 pregame + 343 clean ticks, 389 contaminated) -- above the 300 bar, NOT closed at limit, but every published NBA close number is now labelled "vs a contaminated reference". Re-scored: S112 close-minus-Elo +0.025606 -> +0.021819 (CI [+0.010468,+0.033170], p 4.82e-04, n 351 -> 171, k raised 6 -> 8 to MEET the unchanged >=5-fold bar); S113's 147 of 240 -> 154 of 240 (64.2 pct), best family improvement +0.000640 -> +0.002302 CI [-0.003129,+0.007733] against the unchanged +0.004 bar -- still NULL. Uncharged; 18-row ledger untouched | S112 S113 S118 | FIXED (2026-09-03) |`

S133: `| S133 | harness | FIXED. The MLB placeholder rule now binds the RAW 0.500/0.500 listing instead of the devigged value: 16 of the 19 dropped events return (894 -> 910 closes; the other 3 really were raw 0.500/0.500 listings, and 2 more raw placeholders were also spine-unmatched, so no_spine_match moves 22 -> 20). _drop_ambiguous became _mark_ambiguous: a duplicated event_id now yields ONE row with close_source=ambiguous and p_close NaN, and nba_close ranks its sources through _SOURCE_RANK (pregame 3 > ambiguous 2 > first_inplay_tick 1 > inplay_contaminated 0) so an ambiguous pregame close can no longer fall through to the tick unrecorded. Honest correction to the row: the pregame source has 0 duplicated game_ids today, so the downgrade is a live MECHANISM with 0 live instances; the 4 ambiguous rows all come from the in-play side. MLB by_source moves 894 -> 910; the S112 mlb close-minus-Elo reading DOES change shape -- +0.007269 CI [+0.000066,+0.014473] p 0.0481 becomes +0.006709 CI [-0.000198,+0.013617] p 0.0564, an honest NULL where a marginal positive was read. Every model arm is BEHIND the close before and after on both sports | S112 S118 | FIXED (2026-09-03) |`
