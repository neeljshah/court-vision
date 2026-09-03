# G145 NOT VERIFIED debt sweep

**Verdict: ACCEPT -- inventory and read-only debt sweep complete.** This memo
executes `specs/G145_spec.md` and follows `VERIFIER_CONTRACT.md`, including A7
and the section-B self-check below. It changes no threshold, verdict,
coordinate contract, published measurement, pod file, or pod process.

## Scope and method

The source manifest in [`g145_sweep/README.md`](g145_sweep/README.md) lists
every memo read: **56** G80-G143 files in the 2026-09-02 cohort. Fifty-five
contain an explicit `NOT VERIFIED` heading. G85 is the exception: it has no
such heading and therefore contributes zero inferred items. Extracting each
top-level heading through the next heading produced **214 bullet-level items**.

`C` means CHEAP: a minutes-scale, read-only check was available and is recorded
below. `E` means EXPENSIVE: a real measurement, label pass, acquisition, code
path, or its own lane is required. `P` means PERMANENT: the named historic
source, provenance, telemetry, or bounded retrieval path is absent, so the
specific claim cannot be verified from retained evidence. Classes are in source
bullet order; the short phrases preserve the item identity without rewriting
the source memo.

| Memo | Items in source-bullet order | Class |
|---|---|---|
| G80 | historic snapshot; pod landing; full test/reader | P,E,E |
| G81 | pod/reader run; full test; replay necessity | E,E,P |
| G82 | old tennis rows; absent broadcast eye check; sampling metadata | P,P,P |
| G84 | replacement detector; four-line sufficiency; generalization; pixel provenance | E,E,E,E |
| G85 | no explicit NOT VERIFIED section | -- |
| G87 | population rate; role detector; final solve/downstream behavior | E,E,E |
| G88 | persisted sidecars; pod landing; ft/s gate | E,E,E |
| G90 | pod/reader run; absent live ledger; full test | E,P,E |
| G91 | role detector; five-landmark rate; solve/validation; court_feet prohibition | E,E,E,E |
| G92 | ball metrics; physical ground truth; other visual contexts | E,E,E |
| G94 | supervisor restart; pod inspection; abandoned part reaping; master landing | E,E,E,C |
| G95 | geometry; solver score; OCR ability; corpus metadata cause; field-level inference | E,E,E,E,E |
| G96 | tennis_10 eye check; nyYk pixel mark; G89 raw table; test status | P,P,P,E |
| G97 | sample membership; clean-checkout sheets; replacement route | E,P,E |
| G98 | recall/precision; tolerance/interval; tracker-vs-label fault; y-gate discrepancy; production impact | E,E,E,E,E |
| G99 | historic rows/titles; later arrivals; ledger audit; remediation | P,E,E,E |
| G100 | kill frame; thin root causes; mutable outputs; GPU telemetry | P,E,P,P |
| G101 | solve; court_feet; held-out accuracy; detector recovery | E,E,E,E |
| G102 | observed movement significance; absent tennis_10 source; production impact | E,P,E |
| G103 | mismatch root cause; durable recipe; G93 recall/marks | E,E,C |
| G104 | solve; detector recovery; court_feet accuracy; six-clip generalization; G99 audit | E,E,E,E,C |
| G105 | kill/FPS telemetry; historic-rate extrapolation; cap sufficiency; mutable cause; GPU telemetry; proposed diff | P,E,E,P,P,E |
| G106 | geometry; field identity/scale; validation; visible-point detector claim; operational change | E,E,E,E,E |
| G107 | >=10 eligibility snapshot; absent p99.9; policy; tennis_10 eye check; tests | C,P,E,P,E |
| G108 | historic collision proof; future enforcement; re-track result; backdated snapshot | P,E,E,P |
| G109 | counterfactual quality; soccer repair; tennis future stride; later pod count; tests | E,E,E,E,P |
| G110 | historic WFl provenance; pixel-exact reconstruction; G93 measurement | P,E,E |
| G111 | geometry; detector role/localization; court_feet/validation; broadcast generalization; independent labelling | E,E,E,E,E |
| G112 | valid decision set; alternative footage impossibility; operational change | E,E,E |
| G113 | duration share; second observer; inventory cause; live-only recompute; content-gate run | E,E,E,E,E |
| G114 | target-frame solve; external archive; update mechanism; re-track; tests | P,P,P,E,P |
| G115 | generalization; second reviewer; replacement method; historic WFl provenance | E,E,E,P |
| G116 | historical identity; external archive; deletion event; storage capacity; later state; tests | P,P,P,E,E,P |
| G117 | duration share; second observer; prospective classifier; downstream recompute | E,E,E,E |
| G118 | temporal recovery benefit; absent tennis_10 source; production impact; generalization | E,P,E,E |
| G119 | recall/comparison; precision/robustness; integration; generalization | E,E,E,E |
| G120 | generalization; divergent original tiles; new audit; solve/deployment | E,P,E,E |
| G121 | coordinates/metrics; integration; source-versus-label cause | E,E,C |
| G122 | historic recovery; witness tracking quality | P,E |
| G123 | post-CLAHE audit; generalization; alternatives; court solve | E,E,E,E |
| G124 | historic bytes; causal association; selected-case attribution; guard | P,E,E,E |
| G125 | game-only rate; new sample/solver; metrics; other-sport live share | E,E,E,E |
| G126 | replacement census; system change; inter-rater/generalization | E,E,E |
| G127 | historic counts; historic source identity; quality; eligible denominator | P,P,E,E |
| G129 | G68 byte identity; generalization; alternative detector; solve/deployment | P,E,E,E |
| G131 | policy result; future >=10; future quality; tennis retrieval; tests | E,E,E,P,P |
| G132 | generalization; independent labels; alternatives/solve | E,E,E |
| G133 | acquisition timestamps; forecast; tennis_08 completion; queue experiment; policy/deployment | P,E,E,E,E |
| G134 | generalization; human labels; detector/integration | E,E,E |
| G135 | four-line solve; distance error; reprojection; court_feet; generalization | E,E,E,E,E |
| G136 | 46.2% precision; adjudication; independent corpus/pipeline | C,E,E |
| G137 | physical four-line frame; co-occurrence distribution; solve/validation | E,E,E |
| G138 | outside-subset correctness; partial assigner comparison; solve/validation | E,E,E |
| G139 | other ffprobe failures; multi-stream policy; tennis_08 cause; live pod behavior | E,E,E,E |
| G140 | corner detector metrics; integration; precise reachability rate | E,E,E |
| G141 | learned/alternative detector; integration; generalization/rate; distance validation | E,E,E,E |

Classification total: **6 CHEAP, 165 EXPENSIVE, 43 PERMANENT**.

## Cheap checks completed read-only

| Check | Result | Evidence |
|---|---|---|
| G94 item 4: master landing was pending at author time | **Resolved.** Master contains both the memo and `scripts/platformkit/test_bridge_liveness.py` through `2336247a8743774479a747e9dcda272431e0e241`; the paths exist at `master:<path>`. This reports completion of the author-time verifier action only. | `git -C C:/Users/neelj/nba-ai-system log master -- ...`; `master:docs/evidence/tracking/g94_pipeline_liveness_2026-09-02.md`; `master:scripts/platformkit/test_bridge_liveness.py` |
| G103 item 3: G93 result remained unmeasured | **Confirmed.** The only G93 detection-limit artifact in this worktree is the 1,942-byte protocol; it has no `Result`, `Results`, or `Recall` result heading. This does not substitute a measurement. | [`g93_detection_limit/protocol.md`](g93_detection_limit/protocol.md) |
| G104 item 5: a corpus-wide G99 audit remained required | **Resolved as an outstanding task.** G99 exists, reports 66 clips and four named label mismatches, and retains 66 numbered contact-sheet renders. Its historic-cause caveat remains separate. | [`g99_corpus_sport_audit_2026-09-02.md`](g99_corpus_sport_audit_2026-09-02.md); [`g99_corpus_audit/`](g99_corpus_audit/) |
| G107 item 1: current snapshot had six eligible reports | **Overtaken, not a correction to G107's frozen snapshot.** G131 records that G107 stopped at 6 and the later G109/G131 read had 8 eligible records. The >=10 bar remains unmet. | [`g107_jump_statistic_policy_2026-09-02.md`](g107_jump_statistic_policy_2026-09-02.md); [`g131_jump_statistic_policy_attempt2_2026-09-02.md`](g131_jump_statistic_policy_attempt2_2026-09-02.md) |
| G121 item 3: source-render-label conflict cause | **Overturned on G126's audit sample.** G126's explicit verdict is that G111 labels are wrong; it rules out the source-render association explanation on its reviewed sample. This sweep does not revise any reachability number. | [`g121_corner_pixel_targets_2026-09-02.md`](g121_corner_pixel_targets_2026-09-02.md); [`g126_g111_label_audit_2026-09-02.md`](g126_g111_label_audit_2026-09-02.md) |
| G136 item 1: 46.2% is a precise independent population estimate | **Confirmed caveat.** Recomputing the committed first pass yields 97/210 = 46.2%; joining the committed second pass yields 28/42 = 66.7% agreement. The memo's below-80% reliability qualification holds. | [`g130_recensus/first_pass_source_judgements.csv`](g130_recensus/first_pass_source_judgements.csv); [`g130_recensus/second_pass_source_judgements.csv`](g130_recensus/second_pass_source_judgements.csv); [`g136_recensus_second_pass_2026-09-02.md`](g136_recensus_second_pass_2026-09-02.md) |

The only item materially overturned by a cheap check is G121 item 3, and the
overturn is scoped to G126's audit sample. G107 is a time-indexed snapshot that
became stale; it is not retroactively rewritten. No number is changed here.

## Expensive work, ordered by consequence if wrong

1. **G136/G111/G126/G137-G141 -- basketball visibility and four-constraint route.** A replacement source-decoded, independently adjudicated reachability census and a learned/template corner evaluation would determine whether the programme's only non-tennis geometry opportunity is materially mischaracterised.
2. **G105/G100/G124/G127/G133 -- timeout/thin-output mechanism.** Per-attempt progress telemetry and a controlled, separately specified measurement are needed before any timeout-cap or acquisition conclusion can be trusted.
3. **G91/G101/G95/G106/G104/G112 -- non-tennis reachability/acquisition.** Additional valid wide-footage decision sets are required before the closed current-camera routes can be generalized or overturned.
4. **G115/G120/G123/G129/G132/G134/G135 -- basketball line-route generalization.** Independent labels and a fresh held-out frame set are needed before candidate-method movements can steer a detector choice.
5. **G92/G98/G102/G118 -- tennis ball-label reliability.** A changed or independently adjudicated criterion and source recovery are prerequisite to any tracker metric.
6. **G113/G117 -- content taxonomy/classifier performance.** Duration-weighted, independently labelled corpus work is required before content-gate quality can be claimed.

## Permanent items that must not consume a duplicate lane

- **Pruned source evidence:** G82 items 1-3; G96 items 1-3 (including the
  expressly unretrievable `tennis_10` eye check); G114 items 1-3; G115 item 4;
  G120 item 2; and G129 item 1.
- **Unrecorded historic provenance or telemetry:** G80 item 1; G90 item 2;
  G99 item 1; G100 items 1, 3-4; G105 items 1, 4-5; G108 items 1 and 4;
  G110 item 1; G116 items 1-3 and 6; G124 item 1; G127 items 1-2; G133 item 1.
- **No retained historic basis for the named value:** G107 items 2 and 4; G109
  item 5; G131 items 4-5; and the remaining `P` entries in the inventory table.

These labels do not say the underlying question is metaphysically impossible;
they say the exact historic claim cannot be verified without inventing evidence
or replacing it with a new, separately scoped measurement.

## A7 evidence-path check

At verification time, all 56 source memo paths in `g145_sweep/README.md`, this
memo, `g145_sweep/README.md`, and every local evidence path linked in the cheap
check table exist. The G94 check additionally confirmed both named paths in
master. No glob, missing render, or absent CSV was silently treated as a pass.

## Verifier-contract self-check (section B)

| Check | Result |
|---|---|
| B1 circular metric | PASS. G136 was recomputed over all 210 committed first-pass rows; no failures were excluded. |
| B2 non-additive schema | PASS. Documentation only; no field, status, or reader changed. |
| B3 fall-through loss | PASS. No gate or quarantine changed. |
| B4 re-claim loop | PASS. No claim state changed. |
| B5 pre-verification deploy | PASS. Pod was read-only; nothing was copied or deployed. |
| B6 orphans | PASS. No modules moved or retired. |
| B7 head-slice evidence | PASS. No new render-derived metric was claimed. |
| B8 self-fit as independent | PASS. No model/residual claim was made. |
| B9 degenerate denominator | PASS. The inventory counts explicit source bullets; the one recomputation states its complete row denominator. |
| B10 moved bar | PASS. No threshold or gate changed. |

## NOT VERIFIED (this memo)

- The cohort is the named G80-G143 2026-09-02 landing set in this worktree; it
  is not a claim about any untracked memo outside that identifier/date scope.
- Cheap checks are documentation/git-history checks except the G136 CSV recount.
  They do not replace the expensive measurements listed above.
- The master-path existence check establishes A7 for the two named G94 paths at
  this read; it does not independently re-run G94's focused test.
