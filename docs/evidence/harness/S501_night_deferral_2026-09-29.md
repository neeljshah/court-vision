# S501 paper-night deferral, FIX r4

Verdict: ACCEPT candidate after FIX r4. This is paper only and all evidence is construct-only under temporary roots.

## Before measurement and scope

The measured 2026-09-26 record is `docs/evidence/forward/nights/2026-09-26.json`: qualification, fill_realism, week, scoreboard, and history were REFUSED for `free_ram_below_floor`; e RAN with exit 0. The existing terminal record was therefore present before this change. C2 is code-derived from the pinned base terminal writer; C1 is the measured-record replay. The landed step order is in `paper_night.py` lines 76-109.

## Construct cases

| Case | Scenario | Exit | Files under nights / night_deferrals | Pass |
| --- | --- | ---: | --- | --- |
| C1 | Measured five-family refusal, e admitted | 4 | absent / base receipt | yes |
| C2 | All six rows RAM-refused | 4 | absent / base receipt | yes |
| C3 | One family admission, later RAM refusals | 3 | base record / absent | yes |
| C4 | Nonzero e or non-RAM refusal | 3 | base record / absent | yes |
| C5 | Deferred then admitted retry | 0, then 3 | base record / prior receipt retained | yes |
| C6 | Terminal base, plain retry and explicit r1 | 3, then 4 | base and no r1 / r1 receipt | yes |
| C7 | Fifty-five deferred attempts | 4 | absent / one bounded receipt | yes |
| C8a | Allowed family skip plus RAM refusals | 4 | absent / base receipt | yes |
| C8b | All skipped with no RAM refusal | 3 | base record / absent | yes |
| C9 | Declared seal manifest (7 identity files, keys and values), disjoint from S501's owned paths; fixed-base byte check only under S501_LANDING_CHECK=1 | n/a | none / none | yes |
| C10 | Census has no terminal record | n/a | absent / base receipt ignored | yes |
| C11 | Under- and over-deferral mutations | see below | construct only | yes |
| C12 | Real post-effective E runs, then admitted retry reports `already_present` | 4, then 0 | base record / receipt retained | yes |
| C13 | Repeated deferred r1 | 4, 4 | no r1 record / r1 receipt count 2 | yes |
| C14 | Admitted r1 after deferral | 0 | r1 record / r1 receipt retained | yes |
| C15 | Explicit r1 without a base record | 4 | no r1 record / r1 receipt | yes |
| C16 | Planned three-family RAM-refused night | 4 | absent / base receipt | yes |
| C17 | Planned single-family RAM-refused night | 4 | absent / base receipt | yes |
| C18 | Unknown row beside RAM refusals | 3 | base record / absent | yes |

The C16-C18 test also confirms a duplicate family name is terminal. A skipped family row with `input_root_absent` is terminal; only `archive_absent` and `not_landed` are retryable skips. Corrupt prior receipts return `deferral_receipt_corrupt`; failed replace and temporary-write operations return `deferral_write_failed`. Both return 2, retain prior bytes, leave no night record, and leave no temporary residue.

## C11 mutation evidence

Under-deferral (`paper_night.defer_reason = lambda _: None`) fails named C1, C2, and C7 checks in `test_d1b_spec_mutants_fail_factored_named_cases_then_pass`; the unpatched C7 path runs 55 receipt attempts.

Always-defer (`paper_night.defer_reason = lambda _: "free_ram_below_floor"`) fails named C3, C4, C8b, and C12 checks in that same factored test. Restoring the implementation gives 11 passed in `test_paper_night_deferral_r2.py`.

## Must-not-move seal

Pinned base: `d7963c17323d3e76c010a088f27690d9258fcc26`. The hashes below are SHA-256 of LF-normalized pinned bytes.

| Path | Bytes | SHA-256 | Result |
| --- | ---: | --- | --- |
| paper_night_budget.json | 1971 | 8f83eda9e1666b50fd252e2c28c7b6570ded8e2cd455f6bba6681d45ccd1a998 | unchanged |
| nights/2026-09-26.json | 10920 | ab9d880e2135859111c26b817a2251ab376adb327070d874d49ec01937df2ade | unchanged |
| scoreboard/PREREG_2026-09-24.json | 5046 | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | unchanged |
| scoreboard/PREREG_E_2026-09-25.json | 1423 | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 | unchanged |

C9 (AMENDMENT 6 F1a) has three parts, all cwd-free (root derived from the test file). (i) The manifest walker parses keys and values of every current PREREG_* and BLOCK_CONFIG_E_* seal and asserts a nonempty declared set containing all 7 identity files: 7 are declared, 6 are tracked at base d7963c17323d3e76c010a088f27690d9258fcc26, and baseline_four_arm_features_nfl.py (declared only by PREREG_2026-10-01) lands with S492. (ii) The declared manifest plus the seal files and paper_night_budget.json is disjoint from S501's static owned-path list, and no owned path is under data/registry/. (iii) The fixed-base byte comparison (protected paper_night files, seals, tracked identity files, nights/2026-09-26.json, S500 evidence) runs only when S501_LANDING_CHECK=1, so S492's legitimate identity edits cannot turn it red after landing; it passed at FIX r4 (19 passed with the variable set). The 6 tracked identity files at base, LF-normalised sha256: walkforward.py 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9; ingame_scoreboard.py 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6; ingame_scoreboard_rules.py 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351; baseline_four_arm.py dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2; baseline_four_arm_eligibility.py d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032; baseline_four_arm_features.py 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade. Each construct root asserts that it creates no `data/registry/`. The S485 frozen-source test preserves exact equality for every frozen member other than paper_night.py; it removes the one S501 import and the exact bracketed hook, then tokenizes away comments and blank lines before comparing to the pin. No committed JSON seal or fixture was added, so `.gitattributes` patterns added: none.

## Converted pin locations

| File | Old line | New line | Preserved property |
| --- | ---: | ---: | --- |
| test_paper_night.py | 115 | 115 | RAM floor starts no child; sentinel output is absent |
| test_paper_night_scoreboard_step_1c.py | 19 | 20 | Scoreboard RAM floor starts no child; sentinel output is absent |
| test_s485_baseline_contract.py | 82 | 103 | All frozen source remains pinned except the bracketed S501 import and hook |

Each converted RAM test now asserts exit 4, a valid receipt, its one refused step, no `nights/<D>.json`, and no sentinel child output.

## FIX r0

- B1: bracketed the S501 hook, retained one S501 import, and converted only the paper_night.py S485 member to a tokenize-based pinned comparison.
- B2: changed planned-row eligibility from an exact six-name set to the present family rows plus optional e; unknown and duplicate names remain terminal.
- B3: restricted deferred skipped family rows to `archive_absent` and `not_landed`; added the `input_root_absent` terminal construct.
- B4: converted both one-step RAM pins to valid deferred receipts while retaining the no-child sentinel assertions.
- B5: separated corrupt-receipt `ValueError` from write `OSError`; both replace and temporary-write failure constructs retain the receipt and clean temporary files.
- B6: added this C1-C18 table, mutation evidence, pin table, protected hashes, follow-up contract, adjudication, and all required per-file results.

## S500 follow-up contract (A5, verbatim)

(a) exit 4 + a receipt that validates AND whose `date`, `as_of`, `revision`, `path` and sha256 (from the stdout report) bind to the CURRENT invocation = decision `night_deferred_ram`; (b) that decision CLEARS the tick's child-failure counter for the night (a deferral is not a failure); (c) both audit sidecars (data/cache/paper_desk/night_audits/<D>.json and docs/evidence/forward/desk_audits/<D>.json) are FINALIZED with the deferral decision after the child; (d) the earlier items stay (night stays due, no skip-state write, one night per tick, census never reads night_deferrals/, exit 4 without a valid bound receipt or with a nights/<D>.json present is `night_contract_violation`).

## 2026-09-26 adjudication (A1)

DO NOT run `--rerun` for 2026-09-26. Record the night as lost to the 09-25..28 capture outage plus the RAM refusal; the existing terminal PARTIAL record stays as the only record. A later rerun requires a new row that verifies downstream exclusion of `window_complete: false` receipts in the scoreboard, census, and week-fill consumers and inventories every rerun side effect. The earlier prechecks were not re-run here.

## Per-file results

| Test file | Passed |
| --- | ---: |
| test_paper_night_deferral.py | 10 |
| test_paper_night_deferral_r1.py | 18 (+1 skipped: landing-only byte check; 19 passed with S501_LANDING_CHECK=1) |
| test_paper_night_deferral_r2.py | 13 |
| test_paper_night.py | 39 |
| test_paper_night_steps.py | 56 |
| test_paper_night_steps_1d.py | 25 |
| test_paper_night_steps_1e.py | 8 |
| test_paper_night_deadline.py | 20 |
| test_paper_night_deadline_1b.py | 9 |
| test_paper_night_deadline_1c.py | 3 |
| test_paper_night_inputs.py | 40 |
| test_paper_night_inputs_e2e.py | 11 |
| test_paper_night_e_step_e2e.py | 41 |
| test_paper_night_scoreboard_step.py | 14 |
| test_paper_night_scoreboard_step_1c.py | 4 |
| test_paper_night_scoreboard_step_1d.py | 2 |
| test_paper_night_scoreboard_step_1e.py | 1 |
| test_paper_night_qualification_isolation.py | 2 |
| test_paper_night_scratch.py | 19 |
| test_paper_night_tree_sampler.py | 41 |
| test_scoreboard_history_e2e.py | 13 |
| test_registry_scorer_e_night.py | 33 |
| test_registry_scorer_e_night_1a.py | 13 |
| test_registry_scorer_e_night_1b.py | 15 |
| test_registry_scorer_e_night_capacity.py | 33 |
| test_ingame_scoreboard_night.py | 31 |
| test_s485_baseline_contract.py | 4 |

`python -m scripts.platformkit.execution.paper_night --help` passed. `paper_night_deferral` has no command entry point; receipt validation is exercised by the construct tests.

## FIX r1

- Reproduced before editing: the supplied attack reported `5 failed, 4 passed`; its corrupt receipts escaped as `TypeError` and one yielded `(4, 'free_ram_below_floor')` instead of `(2, 'deferral_receipt_corrupt')`. The verifier's unreadable minimal reproduction reported `OSError denied`; its C11 reproduction found only the missing-deferral lambda; its C12 reproduction used a generic fake E; its C9 reproduction checked two paths; and its memo read found `115/115`, not `115/116`.
- After the r1 changes, the supplied attack is `9 passed`; `test_paper_night_deferral_r1.py` is `18 passed`; the original S501 deferral file is `10 passed`.
- C1a: `validate_receipt` is total over arbitrary JSON, checks exact attempt keys and types, timestamp strings, 64-hex hashes, nonempty samples, date/revision/path binding, exact counters, and rejects a rendered receipt over 65,536 bytes before a temporary file exists. The r1 construct covers every supplied attack shape, a missing attempt field, inconsistent counters, and the 50-attempt oversized case; each preserves prior bytes and writes no night record.
- C1b: unreadable prior receipts now raise `DeferralReceiptUnreadable`; the hook returns exit 2 with `deferral_receipt_unreadable` and reports only the bound path, without `_digest` reading it again. The injected `Path.read_bytes` construct proves no overwrite or night record.
- C1c: r2 patches `paper_night.defer_reason`, the symbol the hook calls. Missing-deferral fails named C1/C2/C7 (C7 executes 55 attempts); always-defer fails named C3/C4/C8b/C12; unpatched factored checks pass.
- C1d: r2 terminal controls for killed, errors, peak-unmeasured, and non-RAM refusal run through `_run`, each beside a RAM refusal, and assert exit 3, a terminal record, and no deferral receipt. The terminal byte-identity check executes the pinned-base writer with the same rows and clock-free input.
- C1e: C9 resolves the repository root from its own file, pins base `d7963c17323d3e76c010a088f27690d9258fcc26`, recursively parses keys and values from every pinned JSON PREREG/BLOCK_CONFIG_E seal for referenced tracked paths, and uses root-relative reads. No new JSON seal or fixture was added; `.gitattributes` patterns added: none.
- C1f: fresh converted-pin locations are `test_paper_night.py:115`, `test_paper_night_scoreboard_step_1c.py:20`, and `test_s485_baseline_contract.py:103`. Inventory: paper_night is the deferral-receipt owner; night_coverage_census, week_fill_accounting, S500 paper_desk_actions, and evidence_pipeline are downstream non-readers of `night_deferrals/`.

The original r0 table remains the C1-C18 construct index. r1 and r2 add receipt, mutation, terminal-control, C12, and cwd regressions. The C12 claim is limited to the construct fixture and its admitted retry.

## FIX r2

- Reproduced verifier failures before this repair: from a non-repository cwd, C1e failed with `fatal: not a git repository` and exit 128; the supplied deep receipt construct reported `RecursionError escaped main`; the supplied errors construct printed `mutant False exit 3 status PARTIAL` and `mutant True exit 4 status DEFERRED`.
- D1a / SOL 1: receipt booleans are identity-checked, attempt revisions bind to the receipt revision, all JSON decode failures map to `deferral_receipt_corrupt`, and corrupt-prior checks preserve bytes with no terminal night record. Receipt append now discards oldest attempts until the encoded file fits 65,536 bytes; the 2,000-character rerun test runs 30 deferred attempts. E artifact hashing is inside the hook and reports `deferral_e_artifact_unreadable` without reading the target again.
- D1b / SOL 2 and 4: r2 adds real `_run` controls beside RAM refusals, pinned-base terminal byte identity, and in-test M1/M2/M3 checks. C7 is the 55-attempt case and C12 is its own retry check.
- D1c / SOL 3: C12 runs the real post-effective registry scorer through paper_night. The admitted retry emits `already_present`; the receipt and full-output pair remain byte-identical.
- D1d / SOL 5 and OPUS 2: all C9 Git calls use `cwd=root`; seal paths are recursively parsed from pinned-base JSON keys and values, reads are root-relative, and construct roots assert no registry directory. The three S501 files pass from `C:/Users/neelj/AppData/Local/Temp` with counts 10, 17, and 12.
- D1e / SOL 6: the converted paper-night pin is 115/115. This memo now identifies paper_night as the receipt owner and its downstream consumers as non-readers. No JSON fixture or seal was added; `.gitattributes` patterns added: none.

## FIX r3

- E1a / SOL 1: before repair, the minimal reproduction printed `seal_paths_found=['docs/evidence/forward/scoreboard/PREREG_2026-09-24.json']`. `_seal_paths` now visits JSON keys and values, requires nonempty implementation paths, asserts all seven known identity files, and compares every derived tracked path with pinned-base LF-normalized bytes; its r1 file passes 17 tests.
- E1b / OPUS 1: before repair, production M1 and M2 runs each reported `11 passed`. `test_d1b_m1_m2_m3_mutants_fail_named_checks` now first proves the M1 planning-errors RAM-refusal and M2 clean-row controls on unpatched production. M1 and M2 each fail that named test when applied to production; M3 remains killed by its named in-test assertion. The errors control uses RAM samples `[0, 0]`, and the non-RAM control has no planning errors. Production-mutant counts: M1 2 failed and 10 passed; M2 1 failed and 11 passed.
- E1c / OPUS 2: before repair, the production `no_prior_bind` run reported `11 passed`. `test_e1c_foreign_date_and_path_receipts_refuse_without_overwrite` parks valid 2026-09-22 base and r1 receipts under 2026-09-20 paths, then proves each is refused without changing receipt bytes or writing a night record. The production `no_prior_bind` mutant now fails this named test with 1 failed and 11 passed.
- E1d / memo: title and verdict identify FIX r3; C9 descriptions now state the exhaustive key-and-value manifest. No JSON seal or fixture was added; `.gitattributes` patterns added: none.

## FIX r4 (orchestrator, AMENDMENT 6)

- F1a: C9 split into the declared-manifest test (7 identity files incl. the NFL file), the disjointness test, and the landing-only fixed-base byte test; memo resolves six versus seven (7 declared, 6 tracked at base).
- F1b: the `.r1` binding case now asserts that `2026-09-20.r1.json` (target_day + suffix + .json) is absent.
- F1c: new `killed_week` control (qualification RAM-refused, week KILLED at a 0.001 s deadline, real `_run`) exits 3 PARTIAL with a record and no deferral file. Opus mutant `killed_ok` (S501_MUT2) fails exactly `test_d1b_real_terminal_controls_beside_ram_refusals[killed_week]` (1 failed, 12 passed); it survived every file before.
- Per-file after FIX r4: deferral 10, r1 18 + 1 skipped, r2 13, test_paper_night 39, scoreboard_step 14, scoreboard_step_1c 4, s485 4, test_registry_scorer_e_night 33; the three S501 files also pass from cwd Temp. Production files unchanged.

## NOT VERIFIED

No live RAM-refused paper night after landing, S500 adoption of exit 4, or a retrospective rerun was exercised.
