# S148 -- every NBA tick headline re-quoted on LIVE ticks only

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S148 (filed by S146).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A, B and Q (self-checked in
section 8). Calibration language only (Q6). **NOT VERIFIED** -- this is the lane's own report;
no independent verifier has re-run it.

---

## VERDICT

**Removing every post-final-buzzer tick halves the corpus and changes NO headline verdict.**
15 headline re-quotes: 15 of 15 reproduce their published CI from their own archive at 1e-9
first, and **0 of 15 change verdict** on live ticks or on live-informative ticks. 10 S102 sweep
hypotheses: 0 change. 27 S86 cells: **2 change**, both OT `rem_le02` cells that were NEGATIVE
only because of dead ticks and are now honest NULLs. **0 AHEAD before, 0 AHEAD after**, and the
+0.004 bar is cleared by nothing on either row set.

Every interval widens roughly as the square root of the halved clustered ESS, and **every
model-vs-line point estimate that was negative gets MORE negative** -- the dead half of the
corpus was where the model looked closest to the line, because there both are near-certain. Two
readings sharpen into honest bad news rather than staying flattering:

* **S86 pooled.** -0.004857 `[-0.007355, -0.002359]` -> **-0.007298 `[-0.012501, -0.002096]`**
  on 110,886 live ticks. The state-priced prior is further behind the in-play line on live ticks
  than the published number showed, and the gap now exceeds 0.004 in the BEHIND direction.
* **S101 P4 grouped coverage at nominal 0.90.** market 0.9800 -> **0.8400**, model 0.9400 ->
  **0.7600**, on 22,553 live P4 ticks of 115,035. The published P4 coverage was carried by the
  80 pct of P4 ticks that are post-buzzer; on live P4 ticks BOTH bands under-cover.

Artifact: `data/cache/eval_gate/s148_live_requote_2026-09-03.json` (local; `data/` is gitignored).
Uncharged: `_charge_ledger` never called, `data/cache/eval_gate/backtest_fwer.jsonl` never opened
(**18 rows**), `data/registry/` untouched, no flag flipped ON, no bar moved, no refit anywhere, no
landed module edited, no pod contact, no push, and nothing read or written under `src/`,
`kernel/`, `api/`, `intel/`, `scripts/team_system/`.

---

## 1. THE LIVE RULE, FROM THE DATA

`data/cache/inplay_odds/nba_checkpoints_full.parquet` carries **13 columns** -- `game_id`,
`game_date`, `ts`, `period`, `game_clock_s`, `score_home`, `score_away`, `margin`, `market_prob`,
`traded`, `market_ticker`, `outcome_home_win`, `venue`. There is **no `final` and no `status`
column**, so the rule cannot read one and is derived from the game state instead:

```
live  <=>  game_clock_s > 0  OR  period < 4
dead  <=>  period >= 4      AND game_clock_s == 0
```

A quarter-end buzzer in P1-P3 is a LIVE tick and is kept (13,660 such ticks exist on the S86
screen CSV); a P4 or OT tick matched to a play state at clock 0 is the post-buzzer price S146
found. A missing clock cannot be confirmed dead and stays live, so the mask never silently
deletes a tick it could not classify.

| corpus | n | dead (excluded) | share | games | games emptied of live ticks |
|---|---|---|---|---|---|
| `s86_nba_every_tick_2026-09-03.csv` (the screen CSV) | 232,951 | **122,065** | 0.5240 | 797 | **0** |
| `nba_checkpoints_full.parquet` (the source corpus) | 465,249 | **244,183** | 0.5248 | 1,593 | 0 |

**Against S146's 235,513.** On the same parquet this rule excludes **244,183**, which is
**8,670 MORE** than S146's 235,513. The two counts are not the same set and neither is
wrong: S146 counted rows that are BOTH matched to the game's last play state AND over the 300 s
staleness rail, while this rule is purely a state rule and also catches post-buzzer ticks whose
matched final play is less than 300 s old. The shares agree to within a fifth of a point
(0.5248 here, 0.5062 for S146's subset), so the premise holds: **about half of every NBA tick
headline's n is post-final-buzzer price.**

The rule is applied ONCE, to the S86 screen CSV, and the resulting `(game_id, ts)` verdict is
joined onto every other NBA archive. All of them are strict subsets of the S86 key set --
**0 rows unmatched** across S94, S96, S97, S98, S103, S114, S115, S116-nba, S101 and the S102
top-10 series -- and `attach_live` raises rather than passing an unmatched row through.

**Live-informative** is the PUBLISHED informative mask -- `tick_informative.flag_ticks` run on
the full series, exactly as each artifact published it -- intersected with live. Held-ness is
never re-derived on a different row set, so the third column is a strict subset of the second.

---

## 2. A2 -- EVERY PUBLISHED HEADLINE REPRODUCED FROM ITS ARCHIVE FIRST

Every quote in this memo goes through the SAME clustered DM + ESS helper the artifacts published
with (`tick_informative._quote` -> `dm_test.diebold_mariano` +
`ingame.gap_effective_n.effective_sample_size`). No second implementation of the statistic exists
in this lane, and every CSV is read through `eval_gate.archive_read.read_series` -- never
`comment="#"` (S143).

| block | comparisons | reproduced | max abs delta | tolerance |
|---|---|---|---|---|
| the 15 headline CIs | 15 | **15** | -- | 1e-9 |
| the 27 S86 period x margin x rem cells | 25 (2 cells publish `dm_ci95: null` on 1 game cluster) | **25** | 4.86e-17 | 1e-9 |
| S101 static grouped coverage, 2 arms x 5 phases | 10 | **10** | 0.0 (exact) | 1e-9 |
| the S102 top-10 sqlite CIs | 10 | **10** | 4.73e-17 | 1e-9 |

**No post-live number below is read for a row whose published number did not reproduce first.**

---

## 3. THE TABLE -- 15 HEADLINES, OLD vs LIVE vs LIVE-INFORMATIVE

Bar +0.004 with a CI excluding zero, unmoved. `improvement` is the mean paired Brier
differential as archived (positive = the candidate arm beats its incumbent). `verdict` is one
deterministic reading applied identically to both row sets: AHEAD (CI above zero AND improvement
>= 0.004), POSITIVE-BELOW-BAR, NEGATIVE (CI below zero), NULL.

| headline | n all -> live -> live-inf | n_eff all -> live -> live-inf | improvement all -> live -> live-inf | CI95 all | CI95 live | CI95 live-informative | verdict all -> live | changed? |
|---|---|---|---|---|---|---|---|---|
| S86 pooled state-priced prior vs the in-play line | 232,951 -> **110,886** -> 92,826 | 3260.07 -> **1542.19** -> 1582.37 | -0.004857 -> **-0.007298** -> -0.007560 | [-0.007355, -0.002359] | **[-0.012501, -0.002096]** | [-0.012869, -0.002251] | NEGATIVE -> NEGATIVE | no |
| S94 phase-conditioned shrinkage, overall | 192,635 -> **93,776** -> 78,105 | 4029.33 -> **1881.98** -> 1984.37 | -0.000243 -> **-0.000814** -> -0.000808 | [-0.000999, +0.000513] | **[-0.002292, +0.000664]** | [-0.002290, +0.000674] | NULL -> NULL | no |
| S94 TARGET cell P1-P2 \| close_le5 \| rem_gt12 | 23,561 -> **23,561** -> 19,776 | 875.59 -> **875.59** -> 890.95 | -0.002807 -> **-0.002807** -> -0.002986 | [-0.006055, +0.000440] | **[-0.006055, +0.000440]** | [-0.006106, +0.000134] | NULL -> NULL | no |
| S96 primary post-event drift arm `thr3_k5` | 39,168 -> **38,113** -> 36,076 | 12191.56 -> **11844.45** -> 11695.29 | -0.000138 -> **-0.000144** -> -0.000152 | [-0.000301, +0.000025] | **[-0.000311, +0.000024]** | [-0.000329, +0.000025] | NULL -> NULL | no |
| S97 two-sensor Kalman posterior | 192,635 -> **93,776** -> 90,080 | 68148.68 -> **33144.87** -> 32997.30 | +0.000003 -> **+0.000006** -> +0.000006 | [-0.000009, +0.000015] | **[-0.000018, +0.000031]** | [-0.000019, +0.000032] | NULL -> NULL | no |
| S98 fitted per-cell sigma arm (`elo_sig`), pooled | 162,171 -> **78,590** -> 66,904 | 2122.30 -> **993.25** -> 1017.08 | -0.002378 -> **-0.004119** -> -0.004102 | [-0.004904, +0.000148] | **[-0.009359, +0.001120]** | [-0.009417, +0.001214] | NULL -> NULL | no |
| S103 sigma grid widened to [3, 60], pooled | 162,171 -> **78,590** -> 66,887 | 2120.08 -> **1022.95** -> 1048.51 | -0.002117 -> **-0.004461** -> -0.004481 | [-0.004670, +0.000436] | **[-0.009712, +0.000790]** | [-0.009811, +0.000849] | NULL -> NULL | no |
| S114 ladder k=1 | 192,635 -> **93,776** -> 78,179 | 1958.85 -> **968.54** -> 986.89 | -0.000537 -> **-0.001102** -> -0.001172 | [-0.001119, +0.000044] | **[-0.002296, +0.000091]** | [-0.002440, +0.000096] | NULL -> NULL | no |
| S114 ladder k=3 | 192,635 -> **93,776** -> 79,075 | 2508.84 -> **1255.21** -> 1354.57 | -0.000252 -> **-0.000520** -> -0.000486 | [-0.000672, +0.000168] | **[-0.001382, +0.000342]** | [-0.001344, +0.000371] | NULL -> NULL | no |
| S114 ladder k=5 (best) | 192,635 -> **93,776** -> 83,356 | 2674.76 -> **1334.63** -> 1422.24 | -0.000243 -> **-0.000501** -> -0.000481 | [-0.000663, +0.000177] | **[-0.001363, +0.000361]** | [-0.001328, +0.000366] | NULL -> NULL | no |
| S114 ladder k=10 | 192,635 -> **93,776** -> 81,598 | 2224.26 -> **1101.59** -> 1132.65 | -0.000406 -> **-0.000839** -> -0.000812 | [-0.000975, +0.000162] | **[-0.002006, +0.000328]** | [-0.001949, +0.000325] | NULL -> NULL | no |
| S115 best non-linear arm (`mlp`) | 192,635 -> **93,776** -> 90,169 | 3239.80 -> **1631.39** -> 1656.30 | -0.000549 -> **-0.001199** -> -0.001194 | [-0.001476, +0.000378] | **[-0.003096, +0.000697]** | [-0.003089, +0.000701] | NULL -> NULL | no |
| S115 arm `hgb` | 192,635 -> **93,776** -> 80,521 | 3077.21 -> **1525.41** -> 1569.75 | -0.001411 -> **-0.002962** -> -0.003059 | [-0.002918, +0.000096] | **[-0.006059, +0.000135]** | [-0.006173, +0.000055] | NULL -> NULL | no |
| S115 arm `hgb_mono` | 192,635 -> **93,776** -> 81,255 | 3025.92 -> **1497.42** -> 1535.76 | -0.001455 -> **-0.003028** -> -0.003076 | [-0.002982, +0.000073] | **[-0.006170, +0.000115]** | [-0.006239, +0.000088] | NULL -> NULL | no |
| S116 pooled residual, NBA side | 192,635 -> **93,776** -> 79,958 | 2370.04 -> **1174.03** -> 1207.48 | -0.000343 -> **-0.000829** -> -0.000807 | [-0.001124, +0.000438] | **[-0.002413, +0.000754]** | [-0.002391, +0.000777] | NULL -> NULL | no |

**Nothing changes verdict, and the non-tautology check is inside the table.** `S94-target` is the
P1-P2 \| close_le5 \| rem_gt12 cell: **23,561 -> 23,561 rows, identical on every statistic**,
because that cell contains no P4 or OT tick at all. The mask is not shrinking everything -- it
removes exactly the rows the rule names. `S96` barely moves (39,168 -> 38,113) because the
post-event drift arm only scores ticks near a market move, few of which are post-buzzer.

Every game survives: `n_games` is unchanged in all 15 rows (797 for S86; 673, 665 and 571
elsewhere), so no cluster is lost and no denominator is recycled.

---

## 4. THE 27 S86 CELLS -- WHERE THE TWO VERDICT CHANGES ARE

21 of 27 cells are entirely live and are identical on both row sets. Only the six `rem_le02`
cells in P4 and OT shrink, and they shrink hard:

| cell | n all -> live | improvement all -> live | CI95 all | CI95 live | n_eff all -> live | verdict all -> live |
|---|---|---|---|---|---|---|
| `OT\|blowout_gt12\|rem_le02` | 134 -> 1 | -- | published `dm_ci95` is null (1 game cluster) | -- | -- | no interval either side |
| `OT\|close_le5\|rem_le02` | 5,667 -> **394** | -0.061524 -> **-0.010074** | [-0.081368, -0.041681] | **[-0.035042, +0.014894]** | 63.11 -> 161.25 | NEGATIVE -> **NULL** |
| `OT\|mid_06_12\|rem_le02` | 1,968 -> **56** | -0.005010 -> **-0.003577** | [-0.007133, -0.002886] | **[-0.017421, +0.010267]** | 69.77 -> 30.95 | NEGATIVE -> **NULL** |
| `P4\|blowout_gt12\|rem_le02` | 49,171 -> **1,393** | +0.000589 -> **+0.000635** | [-0.000247, +0.001424] | **[-0.000333, +0.001603]** | 2448.45 -> 383.56 | NULL -> **NULL** |
| `P4\|close_le5\|rem_le02` | 29,739 -> **2,694** | -0.000047 -> **-0.001951** | [-0.000761, +0.000666] | **[-0.009657, +0.005754]** | 3025.33 -> 1232.26 | NULL -> **NULL** |
| `P4\|mid_06_12\|rem_le02` | 41,423 -> **1,499** | +0.000006 -> **-0.000061** | [-0.000024, +0.000037] | **[-0.000866, +0.000744]** | 433.54 -> 380.91 | NULL -> **NULL** |

**Both changes are NEGATIVE -> NULL, and both are honest corrections.** `OT|close_le5|rem_le02`
published a -0.061524 differential on 5,667 ticks; 5,273 of those are post-buzzer OT prices where
the line sits at 0 or 1 and the model does not, which is the entire source of the apparent
catastrophe. On the 394 live ticks the differential is -0.010074 with an interval that spans
zero. The published cell-level "the model is far behind in the OT endgame" reading is a
post-buzzer artifact.

`OT|blowout_gt12|rem_le02` drops 134 -> 1 tick and has no interval on either side (its published
`dm_ci95` is already `null` -- one game cluster).

---

## 5. S101 -- GROUPED COVERAGE PER PHASE, STATIC ARM AT NOMINAL 0.90

Coverage is S97's grouped measure recomputed by `s101_aci_coverage.grouped_coverage` on the
archived tick file, reproduced exactly (delta 0.0) on all ten published readings before the live
re-score:

| arm at nominal 0.90 | phase | published coverage | reproduced (all rows) | n all -> live | coverage LIVE |
|---|---|---|---|---|---|
| `market\|0.90` | P1 | 0.9362 | 0.9362 | 18,876 -> 18,876 | **0.9362** |
| `market\|0.90` | P2 | 0.9400 | 0.9400 | 29,349 -> 29,349 | **0.9400** |
| `market\|0.90` | P3 | 0.9600 | 0.9600 | 22,259 -> 22,259 | **0.9600** |
| `market\|0.90` | P4 | 0.9800 | 0.9800 | 115,035 -> 22,553 | **0.8400** |
| `market\|0.90` | OT | 0.9412 | 0.9412 | 7,116 -> 739 | **absent -- fewer than 2 groups of 400 live ticks** |
| `model\|0.90` | P1 | 0.9574 | 0.9574 | 18,876 -> 18,876 | **0.9574** |
| `model\|0.90` | P2 | 0.8800 | 0.8800 | 29,349 -> 29,349 | **0.8800** |
| `model\|0.90` | P3 | 0.9400 | 0.9400 | 22,259 -> 22,259 | **0.9400** |
| `model\|0.90` | P4 | 0.9400 | 0.9400 | 115,035 -> 22,553 | **0.7600** |
| `model\|0.90` | OT | 0.6471 | 0.6471 | 7,116 -> 739 | **absent -- fewer than 2 groups of 400 live ticks** |

**P4 is the finding.** 92,482 of 115,035 P4 ticks are post-buzzer. With them the static band
looks over-wide (market 0.98, model 0.94 against a 0.90 nominal); on live P4 ticks alone both
under-cover (0.84 and 0.76). The ONLINE ACI arm still reads 1.0000 everywhere and stays
label-consuming -- a ceiling, never a result -- so it is not re-quoted here. OT cannot be scored
live: 739 live ticks is fewer than the two groups of 400 the measure requires, and the memo says
so rather than quoting a one-group number.

---

## 6. S102 -- THE TOP 10 OF THE 576-HYPOTHESIS SWEEP

Read from the landed `s102_nba_sweep.sqlite` (read-only, `mode=ro`, mtime unchanged) and its
archived `s102_nba_sweep_top10_series.parquet`:

| hypothesis | improvement all -> live -> live-inf | n_eff all -> live | CI95 live | verdict all -> live |
|---|---|---|---|---|
| `margin_over_sqrt_rem\|raw` | +0.000248 -> **+0.000328** -> +0.000281 | 2295 -> **1108** | [-0.001529, +0.002185] | NULL -> NULL |
| `pace_total\|ew20` | +0.000181 -> **+0.000377** -> +0.000380 | 3425 -> **1819** | [-0.000126, +0.000879] | NULL -> NULL |
| `margin_over_sqrt_rem\|raw@p4` | +0.000174 -> **+0.000211** -> +0.000234 | 7512 -> **4645** | [-0.000093, +0.000514] | NULL -> NULL |
| `pace_total\|ew10` | +0.000168 -> **+0.000352** -> +0.000355 | 3753 -> **1987** | [-0.000124, +0.000828] | NULL -> NULL |
| `pace_total\|ew5` | +0.000155 -> **+0.000325** -> +0.000329 | 3986 -> **2104** | [-0.000138, +0.000788] | NULL -> NULL |
| `pace_total\|ew3` | +0.000148 -> **+0.000312** -> +0.000316 | 4067 -> **2144** | [-0.000150, +0.000774] | NULL -> NULL |
| `pace_total\|raw` | +0.000144 -> **+0.000305** -> +0.000288 | 4074 -> **2142** | [-0.000163, +0.000773] | NULL -> NULL |
| `tdm_h600\|dprior` | +0.000139 -> **+0.000285** -> +0.000286 | 26657 -> **13563** | [+0.000110, +0.000460] | POSITIVE-BELOW-BAR -> POSITIVE-BELOW-BAR |
| `margin_over_sqrt_rem\|raw@p3` | +0.000133 -> **+0.000273** -> +0.000295 | 6627 -> **3255** | [-0.000260, +0.000807] | NULL -> NULL |
| `margin\|raw@p3` | +0.000133 -> **+0.000272** -> +0.000271 | 6746 -> **3317** | [-0.000234, +0.000779] | NULL -> NULL |

Every leader's point estimate RISES on live ticks -- the sweep's candidates are all live-state
features, so removing dead ticks removes rows where they carry no information -- and every
interval widens with the halved ESS. **0 of 10 change verdict**, and the one interval that
excludes zero -- `tdm_h600|dprior`, +0.000139 -> +0.000285 `[+0.000110, +0.000460]` -- is still
**14x below the +0.004 bar**, exactly as it was published.

---

## 7. WHAT THIS DOES NOT SAY

* It is **not a refit.** Every probability, every arm and every fold is read as archived; only
  the row set changes. Nothing here re-opens a fitted arm, so no leak contract is re-run.
* It does **not** fix staleness. The S141/S146 300 s rail is a different instrument: a mid-P4
  tick matched to a play state 40 minutes old is LIVE under this rule and stays in. This row
  removes post-buzzer ticks, not stale ones.
* It does **not** rebuild anything. `nba_checkpoints_full.parquet` is untouched and S146's
  REBUILD NOTE still binds.
* Every reading here is **SINGLE-WINDOW**. The S08 two-corpora floor is satisfied by none of
  them, before or after, and 0 are AHEAD either way.

---

## 8. CONTRACT SELF-CHECK (A, B, Q)

| rule | status |
|---|---|
| A2 recompute the headline yourself | Section 2: 15 headline CIs, 25 cell CIs, 10 coverage readings and 10 sqlite CIs recomputed from their own archives BEFORE any live number is read; 60 of 60 reproduce. |
| A3 even sampling | Q7 applies instead: every metric is over a COMPLETE archived set (all 232,951 / 192,635 / 162,171 / 1,926,350 / 770,540 rows), never a slice. |
| A4 count uniqueness | The live key is `(game_id, ts)` and the join is asserted total (0 unmatched; `attach_live` raises otherwise). `n_games` is published beside every n and is unchanged on all 15 rows -- no cluster is recycled or lost. |
| A5 grep every reader of a touched field | This lane adds ONE new module and ONE new test and touches no existing field, so there is nothing to sweep. Its imports are unchanged (`archive_read.read_series`, `tick_informative._quote` / `flag_ticks`, `s101_aci_coverage.grouped_coverage`); their readers were re-run as regression in MASTER: `test_s137_rebaseline.py` **3 passed**, `test_s143_archive_read.py` **3 passed**, `test_s121_requote.py` **4 passed**. |
| A7 every evidence path exists | Section 9; each path was stat'ed at write time. |
| B1 circular metric | The excluded set is NAMED by a rule stated before any metric (section 1), is published per row (`n_excluded_dead`, `share_excluded`), and the unexcluded figure is quoted beside every live one. No row is excluded to make a metric pass -- the exclusion makes 13 of 15 point estimates WORSE. |
| B2 non-additive schema | Nothing renamed or removed; one new module, one new test, one new JSON, one appended inventory block, one appended ledger line. |
| B3 fall-through loss | S101 OT and the two 1-cluster S86 cells are REPORTED as unquotable with the reason, not quietly given a number. |
| B4 re-claim loop | N/A -- a re-quote claims nothing and queues nothing. |
| B5 pre-verification deploy | No pod contact of any kind. |
| B6 orphans | Nothing moved or retired. |
| B7 head-slice evidence | See A3. Every S86 cell, every S101 phase and all 10 S102 hypotheses are enumerated, not sampled. |
| B8 self-fit as independent | No fit anywhere; every number is an archived paired loss re-quoted on a smaller row set. |
| B9 degenerate denominator | The exclusion REDUCES every denominator it touches and `n_eff` is published beside every interval (halved almost everywhere). `n_games` never falls, so no game becomes a recycled unit. |
| B10 moved bar | `BAR` 0.004, byte-identical to master; this module reads it only as a label and applies no gate. The 0.90 nominal and the 400-tick / 50-group coverage resolution are `s101_aci_coverage`'s own constants, imported rather than restated. |
| Q1 prereg sealed | No scored CLAIM is made; this lane re-quotes existing artifacts and reports deltas. No prereg written, none needed, none faked. |
| Q2 ledger charged first | Nothing charged. `_charge_ledger` never called; `backtest_fwer.jsonl` never opened -- **18 rows**. K never read. |
| Q3 no bar lowered | Nothing lowered. One tolerance, 1e-9, for all 60 reproductions. |
| Q4 leak contract | No new fit; the archived predictions came from each row's own purged, embargoed walk-forward, and the row set only shrinks. |
| Q5 two corpora for an AHEAD | No AHEAD exists to satisfy it: **0 before, 0 after**. Every row is SINGLE-WINDOW and is labelled so in section 7. |
| Q6 calibration language | Brier, Brier differences and coverage only. No dollar, ROI, profit or edge word; none of the retracted figures appears. |
| Q7 sampling rail | Every metric is over a complete enumerated archive with n, n_games and n_eff on the row; the 15-headline / 27-cell / 10-hypothesis / 10-coverage sets are `n = 62 (CONSTRUCT)`, exactly the lists the register row names. |
| Q8 premise first | The row's premise -- "235,513 of 465,249 NBA ticks are post-final-buzzer" -- was re-measured before any re-quote, directly on the parquet: **244,183 of 465,249 (0.5248)** under the state rule, of which S146's 235,513 is the also-over-the-rail subset. **NOT FALSIFIED**, and the delta is stated rather than blended (section 1). |
| Q9 archive the differential | Every interval recomputes from an archived per-unit differential named in the artifact, and `s148_live_requote_2026-09-03.json` carries the whole recomputation (`live_rule`, `a2_reproduction`, `a2_summary`, `rows`, `s86_cells`, `s101_grouped_coverage`, `s102_top10`), so any of it can be re-derived from the artifact plus the archives alone. |

**LOC.** `s148_live_requote.py` is **415 lines**, over the 300-line rail; roughly 90 of those
are the archive spec table, which is pure data. Precedent in the same directory:
`s137_rebaseline.py` 379, `calibration_report.py` 358, `close_join_nba_mlb.py` 337. Stated, not
hidden, and not split into a second file for the sake of the count.

---

## 9. EVIDENCE PATHS

* `scripts/platformkit/eval_gate/s148_live_requote.py` -- the live rule, the archive spec table, the three-row-set re-quote, the S86-cell / S101 / S102 blocks, the artifact builder.
* `tests/platformkit/eval_gate/test_s148_live_requote.py` -- **3 passed** (`python -m pytest tests/platformkit/eval_gate/test_s148_live_requote.py -q`): the live mask on a synthetic 3-game frame (regulation, overtime, a P1-P3 buzzer, a missing clock), the verdict reading, and the S86 pooled CI reproduced from its archive to **1e-9** with `n_live + n_excluded_dead == n_all`.
* `data/cache/eval_gate/s148_live_requote_2026-09-03.json` -- the artifact (local; `data/` is gitignored). Rebuild with `python -m scripts.platformkit.eval_gate.s148_live_requote`.
* `docs/evidence/SIGNAL_INVENTORY_2026-09-03.md` -- section 7 appended with the live-only block (existing lines untouched).
* `docs/evidence/RESULTS_LEDGER_SYSTEM.md` -- one appended line.
* Read-only sources: `docs/evidence/harness/S146_checkpoint_corpus_stale_share_2026-09-03.md`, `docs/evidence/harness/S137_rebaseline_2026-09-03.md`, `data/cache/inplay_odds/nba_checkpoints_full.parquet`, and the `data/cache/eval_gate/` archives named in the artifact.

---

## 10. WHAT IS NOT VERIFIED

1. Lane's own report; no independent verifier has re-run any of it.
2. The live rule is a STATE rule read off `period` and `game_clock_s` as the join wrote them. If
   a tick's matched play state is itself wrong, the rule inherits that error; it is not a
   post-buzzer detector built from the price series.
3. `game_clock_s == 0` is an exact float comparison. On this corpus the column is whole seconds
   and every P4/OT zero is a real buzzer state, but a future rebuild writing sub-second clocks
   would need a tolerance.
4. The live/dead split of the OTHER archives is INHERITED from the S86 key join, not re-derived
   from each archive's own state columns (only S86 and S103 carry `period` at all, and only S86
   carries `game_clock_s`). The join is total, but it is a join.
5. `n_eff` here is the shared helper's ICC-based clustered ESS on the SPECIFIC differential being
   quoted; where a memo published an ESS computed on a different arm's loss column the two are
   not the same quantity and neither is wrong (S98's overall 2,129.58 against 2,122.30 here for
   `elo_sig`, carried over from S137).
6. S101's ACI arm is not re-quoted at all -- it reads 1.0000 everywhere and is label-consuming.
7. Every reading is SINGLE-WINDOW; no second corpus, before or after.
