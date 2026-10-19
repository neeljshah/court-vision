## 2. S631

**READY AFTER prose-only vocabulary cleanup, a narrow spec amendment permitting that cleanup, and matching review.** The functional correction is already accepted. [O/px_r1_review.md:55; C631:docs/evidence/harness/S631_spec_2026-09-30.md; lane `/root/s631_s666`]

### Identity

```text
candidate: private/cloud/S631-2026-09-30
tip:       7f189d11697de648c194954731c55e54776d148c
base:      67a0801b85cf36339b929cf5766fad8515ce22e2

master..candidate, oldest first:
d27798d87 S631: stats=[] means no stats; None keeps all; constructs + amended spec
7f189d116 S631: cloud result memo; contract corrections and adversarial acceptance
```

Four files, **154 insertions and two deletions**; reverse path-limited master diff empty. [Lane `/root/s631_s666`; C631 commit objects]

```text
docs/evidence/harness/S631_cloud_result_2026-09-30.md
docs/evidence/harness/S631_spec_2026-09-30.md
scripts/platformkit/improve/prop_line_distance_calib.py
tests/platformkit/improve/test_prop_line_distance_calib_s631.py
```

### Verdict history and remaining issues

Pre-build REVISE was folded; contract ACCEPT WITH CORRECTIONS required the missing memo; adversarial ACCEPT followed. The memo says: "The one correction (A7: this evidence file was missing at d27798d8) is closed by this file." The tip contains that memo and the explicit `None` check. Latest independent verdict is **LAND**; Windows integration collected six tests and passed all six. [C631:docs/evidence/harness/S631_cloud_result_2026-09-30.md; C631:scripts/platformkit/improve/prop_line_distance_calib.py:222; O/px_r1_review.md:55; O/integ_windows_tests.md]

No final-review functional defect remains. Real OOF-data execution and optional broader input/order cases remain unverified. [C631:docs/evidence/harness/S631_cloud_result_2026-09-30.md]

The all-path preflight would reject prose in the following locations. Replace it exactly as follows, preserving module line count:

```text
module line 20:  Readout-only calibration reporting. Never raises.
module line 21:  Dimensionless calibration metrics only.
module line 42:  # Verdict thresholds for calibration.
module line 218:     Never raises. Output contains calibration metrics only.
spec line 34:    CALIBRATION: metrics only (Brier/ECE/BSS); existing output keys unchanged.
memo line 51:    Calibration reporting only.
```

Append a mechanical spec amendment permitting only those comment/docstring/prose substitutions. Its original restriction otherwise permits only the functional/documentation lines already changed. Keep all executable statements, assertions, thresholds and the **374-line existing allowance** unchanged. [C631:docs/evidence/harness/S631_spec_2026-09-30.md:30; scripts/platformkit/tracking/contract_preflight.py:69; tests/platformkit/test_loc_rail_scope.py:57]

### Landing and operational disposition

Use the common procedure: `d27798d87`, `7f189d116`, then reviewed cleanup. Include the exact existing LOC exemption in preflight; do not enlarge it. [C631 spec; tests/platformkit/test_loc_rail_scope.py:57]

No scheduled caller or capture integration was found; the behavior changes when this helper is explicitly invoked. No restart or next-night runtime field is required. Record adoption as `N/A - no scheduled caller`; `tick_ok` would not prove this helper ran. Rollback is the actual S631 landing commit, with no process relaunch. [C631:docs/evidence/harness/S631_cloud_result_2026-09-30.md:18; C631 diff; lane `/root/s631_s666`]

### Other dossier lines naming S631 (verbatim)

These are **future lander commands**, not actions performed by this read-only lane. Execute rows serially in this order: **S666, S679, corrected S631, corrected S594, then S688 after its hold clears**. Capture activation is a separate owner/session handoff. [O/px_r1_review.md:103; O/px_r2_review.md:34; O/px_w7.md:60; docs/operations/DESK_STATE.md:73]

**S631** - historical counts 20, 6 and 1:

```text
tests/platformkit/improve/test_prop_line_distance_calib.py
tests/platformkit/improve/test_prop_line_distance_calib_s631.py
tests/platformkit/test_loc_rail_scope.py
```

Use the frozen pre-landing master SHA and the complete owned text manifest. S679's gzip is validated by its test rather than decoded as prose. S631 alone receives its existing exact-path LOC exemption. [scripts/platformkit/tracking/contract_preflight.py; tests/platformkit/test_loc_rail_scope.py:57; C679 test fixture assertion]

if ($Id -eq "S631") {
    $LocArgs = @("--loc-exempt",
        "scripts/platformkit/improve/prop_line_distance_calib.py")
}

| S631 | `LANDED <sha>; ACCEPT WITH CORRECTIONS; explicit empty stats selects no rows; None retains defaults; reviewed prose cleanup; main <results>; no scheduled caller.` | Pregame: add `S631 LANDED <sha>; no capture adoption.` Preserve S632/S449 obligations. |

| S631 | `private/cloud/S631-2026-09-30` | r1 LAND | READY AFTER prose cleanup and matching review | Explicit helper calls only | 3 | Whole-file vocabulary preflight |

3. **S631:** perform the specified prose-only correction/amendment, obtain matching review, then verify and land.

- S631 real OOF execution; S666 real mappings/marks/replay; S679 producer enforcement; and S688 real paired-output comparison remain open. [Each candidate result memo's NOT VERIFIED section]