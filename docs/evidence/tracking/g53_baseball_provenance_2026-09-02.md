# G53: baseball validated-scale provenance repair and restatement

Date: 2026-09-02. Worktree: `a7`. Log: `cx_g53_baseball_provenance`.

Verdict: **ACCEPT WITH CORRECTIONS (restatement only).**

**G33 gate: MAY NOW PROCEED.** Its premise is reproducible when each source
population is named and kept separate. This memo does not authorize binning
night segments as day segments, reopen G11, or change G33's existing binning
rules.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, section B.

## Scope

This is a provenance repair. No tracking was rerun, no footage was acquired,
no render was made, and no validation definition was changed. A segment remains
validated exactly when the 2026-09-01 run marked it validated.

## Reproduction from complete source populations

All rows in each named JSON file were summed; no segment was sampled or
excluded. Wilson intervals below use the two-sided 95 percent Wilson score
interval with z = 1.959963984540054.

| Population | Artifact read | Complete row arithmetic | Restated segment result |
|---|---|---|---|
| DAY, Window A | `docs/evidence/tracking/baseball_scale_validation_2026-09-01/summary.json` | validated: 7 + 2 = 9; segments: 19 + 11 = 30; pitch-view frames: 255 + 67 = 322 | **9/30 = 0.300; Wilson 95 percent interval [0.167, 0.479].** |
| NIGHT, stride 20 | `docs/evidence/tracking/baseball_scale_validation_2026-09-01/night_stride20/summary.json` | validated: 0 + 0 = 0; segments: 1 + 5 = 6; pitch-view frames: 1 + 9 = 10 | **0/6 = 0.000; Wilson 95 percent interval [0.000, 0.390]. CLOSED AT LIMIT: G11, with the three rejected designs recorded in `docs/evidence/tracking/RESULTS_LEDGER.md` and the G11 register row in `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.** |

Each restated number names every artifact it reads beside the result. The DAY
and NIGHT rows answer separate questions and must remain separate in future
headlines.

## One reconciliation of the superseded aggregate

The former combined headline was `9/36` validated segments and `73/332`
pitch-view frames. It is arithmetically reproduced only by adding the DAY
artifact (9 validated of 30 segments, 322 pitch-view frames) and the separate,
previously unnamed NIGHT artifact (0 validated of 6 segments, 10 pitch-view
frames). It is superseded because it was not reproducible from the named
artifact alone and because it mixed a DAY measurement with G11's closed NIGHT
lane.

## Other documents that quote the former aggregate or its 332-frame count

These are an inventory for the orchestrator. This lane does not edit other
lanes' memos, plans, or specifications.

| Kind | Location | Occurrence(s) | Required disposition |
|---|---|---|---|
| Original memo | `docs/evidence/tracking/baseball_scale_validation_2026-09-01.md` | lines 7, 85 | Replace the aggregate headline and totals with the separated DAY and NIGHT restatement. |
| G33 stop memo | `docs/evidence/tracking/baseball_scale_failure_bins_2026-09-04.md` | lines 7, 8, 20 | Retain only as the historical premise-falsification record; link this restatement when readers need the current numbers. |
| Research memo | `docs/evidence/tracking/G09_calibration_licence_research_2026-09-02.md` | line 136 | Correct the stale scale-validation reference. |
| Results ledger | `docs/evidence/tracking/RESULTS_LEDGER.md` | G10 line 9; G33 line 65 | Correct the G10 metric reference; retain G33 as historical diagnosis with a link to this memo. |
| Execution plan | `docs/evidence/tracking/TRACKING_DAY1_EXECUTION_PLAN_2026-09-04.md` | line 300 | Correct the stale aggregate reference. |
| Gap register | `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` | G10 line 59; G33 line 84; G36 line 87 | Correct each downstream scale claim before it is used as a premise. |
| Program state | `docs/evidence/tracking/TRACKING_PROGRAM_STATE_2026-09-02.md` | line 18 | Correct the stale state summary. |
| G33 specification | `docs/evidence/tracking/specs/G33_spec.md` | lines 6, 8, 21 | Orchestrator must issue a corrected premise before its measurement is resumed. |
| G36 specification | `docs/evidence/tracking/specs/G36_spec.md` | lines 8, 23 | Correct the DAY denominator and fraction before dispatch. |

## NOT VERIFIED

- No segment was re-tracked, rendered, inspected, reclassified, or binned.
- No claim is made about what any segment shows.
- The G33 five-bin failure attribution, control bins, and its required renders
  remain unverified; they are future G33 work.
- No new footage, harness run, pod action, deployment, daemon action, or
  feature-flag change occurred.
- No downstream memo, plan, or specification in the inventory above was edited
  by this lane.
- No code was added, so no per-file test was applicable.

## Verifier contract B self-check

| Condition | Self-check |
|---|---|
| B1 circular metric | Clear. Each fraction sums every segment row in its named JSON artifact; no failing row is excluded. |
| B2 non-additive schema | Clear. No field, status value, reader, or schema changed. |
| B3 fall-through loss | Clear. No gate or quarantine behavior changed. |
| B4 re-claim loop | Clear. No failure or claim handling changed. |
| B5 pre-verification deploy | Clear. No pod file was copied and no deployment occurred. |
| B6 orphans | Clear. No module, import, test, or command reference moved. |
| B7 head-slice evidence | Clear. No render or sampled visual evidence is used. |
| B8 self-fit as independent | Clear. No fitted model or residual is reported. |
| B9 degenerate denominator | Clear. Denominators are explicit complete JSON segment totals: DAY 30 and NIGHT 6. |
| B10 moved bar | Clear. The same-row rule, rubber constant, tolerance, G11 verdict, and every harness threshold are unchanged. |
