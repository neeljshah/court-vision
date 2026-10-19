## 5. S688

**NOT READY: correct the two prose locations and run the explicitly omitted Windows tests.** Report-only code can then land while the real paired-output acceptance item stays open. [O/integ_windows_tests.md; O/px_r5_review.md:3; lane `/root/s679_s688`]

### Identity

```text
candidate: private/cloud/S688-2026-09-30
tip:       f8333af75043a7c061ee552a097e64362bae9ddf
base:      89218a7311107f620e70fbb47dacd34610e28486

master..candidate, oldest first:
7c9155224 S688 BUILT: game-level paired statistic and reliability decomposition
ee272cb3a S688 spec: premise-share wording correction
f8333af75 S688 VERIFIED ACCEPT WITH CORRECTIONS: memo + mutation assertions
```

Five new files, **821 insertions**; reverse path-limited master diff empty. [Lane `/root/s679_s688`; C688 commit objects]

```text
docs/evidence/harness/S688_cloud_result_2026-09-30.md
docs/evidence/harness/S688_spec_2026-09-30.md
scripts/platformkit/eval_gate/paired_tests.py
scripts/platformkit/eval_gate/reliability_corp.py
scripts/platformkit/eval_gate/test_paired_tests.py
```

### Verdict history and remaining issues

Pre-build REVISE was folded. Contract and adversarial tiers returned ACCEPT WITH CORRECTIONS. The memo explicitly says:

> "The corrections below were applied without re-verification."

The added mutation assertions and missing memo exist; builder results report eleven passes. Latest static review is **LAND**, but also states:

> "The comparison against existing Model 2.0 probe outputs remains unverified"

The Windows report states that zero S688 tests ran because the file is outside its `tests/` filter. [C688:docs/evidence/harness/S688_cloud_result_2026-09-30.md; C688:scripts/platformkit/eval_gate/test_paired_tests.py; O/px_r5_review.md:3; O/integ_windows_tests.md]

Before landing:

1. Replace the prohibited description at result-memo line 21 with `boundary probes`.
2. Replace the prohibited disclaimer at spec line 37 with calibration-only wording.
3. Run the three exact files in section 6 on Windows, then obtain review of the corrected tip.

No statistic, seed, simulation band, threshold or width requirement changes. [C688 memo/spec; scripts/platformkit/tracking/contract_preflight.py:69; O/px_w8.md:40]

The real Model 2.0 comparison is **not fixed or supplied by the tip**. Its later command is:

```powershell
python -m scripts.platformkit.eval_gate.paired_tests --csv <archived-game-losses.csv>
```

The actual input path is UNKNOWN. Required columns are `game_id,loss_ref,loss_cand`; retain `report_only=true`, the estimand, game count, `compare.sign_agree`, `compare.width_gap_pct` and the discrepancy flag. Reliability output remains descriptive. [C688:scripts/platformkit/eval_gate/paired_tests.py; C688 result memo:126; O/px_x5.md]

### Operational disposition

No existing caller changes, no tick/capture effect, no restart and no new night receipt field. After its hold clears, replay the three commits and reviewed prose correction through the common procedure. Rollback is the actual landing commit; relaunch nothing. Full empirical acceptance remains open after tooling landing. [C688 diff; O/px_r5_review.md:3]

## Related dossier excerpts (verbatim)

# D1 landing dossier

**Two candidates are ready for landing checks, two need small preflight corrections, and S688 remains on hold.** S688 was not tested on Windows: the integration filter collected zero tests for it. [O/integ_windows_tests.md; lane outputs `/root/s594`, `/root/s631_s666`, `/root/s679_s688`]

These are **future lander commands**, not actions performed by this read-only lane. Execute rows serially in this order: **S666, S679, corrected S631, corrected S594, then S688 after its hold clears**. Capture activation is a separate owner/session handoff. [O/px_r1_review.md:103; O/px_r2_review.md:34; O/px_w7.md:60; docs/operations/DESK_STATE.md:73]

**S688** - historical cloud counts 11, 8 and 1; Windows outcomes UNKNOWN:

```text
scripts/platformkit/eval_gate/test_paired_tests.py
scripts/platformkit/eval_gate/test_walkforward.py
tests/platformkit/test_loc_rail_scope.py
```

| S688 | Only after hold clears: `LANDED <sha>; ACCEPT WITH CORRECTIONS; report-only tooling; exact Windows/main <results>; real Model 2.0 comparison OPEN.` | Quant-grade: `S688 tooling LANDED <sha>; real comparison OPEN; no tick/capture adoption.` |

| S688 | `private/cloud/S688-2026-09-30` | r5 LAND | NOT READY | None | 5 | Prose cleanup and omitted Windows tests; real comparison stays open |

- S631 real OOF execution; S666 real mappings/marks/replay; S679 producer enforcement; and S688 real paired-output comparison remain open. [Each candidate result memo's NOT VERIFIED section]
