GAP S712 (narrowed 2026-10-08) | night (sealed-artifact read on the post-run receipt) | worktree: dispatcher's choice | S712 re-spec lead 2026-10-08
# A night receipt read never raises on an oversize or unreadable sealed artifact, and a RAN step's artifact refusal puts the night row into attention
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md A, B, Q (S-row). PAPER ONLY; no accuracy or market claim.
WHERE: every test is a construct under tmp_path. No committed night, scoreboard or desk audit is opened for write.

PREMISE (memo docs/evidence/harness/S712_RESPEC_2026-10-08.md section 0):
- Night 10-06's post-run tick decision = refused ValueError:evidence_too_large, step_exception.
- Cause: scoreboard/2026-10-06.json is 9,740,112 B and paper_desk_evidence.document() refuses
  anything above 8 MiB (paper_desk_evidence.py:16-17).
- The S711 catch (:112) takes only JSONDecodeError and UnicodeDecodeError.
- accepted_receipt re-raises (paper_desk_actions.py:139-140), so the desk audit write (:231-244) never runs.
- Separately, a RAN step's counted artifact_empty / artifact_unreadable stays on the outcome while the
  row reads night_partial / night_complete with refusals {}, which classifies as success.

CONTRACTS READ:
- S602: legacy nights are listed, never re-run.
  tests/platformkit/ops/test_paper_desk_legacy_nights.py:34-36 pins refusals == {"night_noncanonical_as_of": 1}.
- S586: <D>.rN.json is a permanent refusal (OPEN).
- S711 fix (a): KILLED-step reasons step_killed / artifact_empty.
- S778: terminal nights close by acknowledgement.
- The 2026-10-03 revert of 6e8686491: no empty-steps refusal, no new legacy refusal, no revision queue.

DESIGN (two files, no new module, no queue, no change to any tick decision for a night without an
artifact read refusal):
(1) scripts/platformkit/ops/paper_desk_evidence.py (291 LOC; stay at or below 300):
  - document(path, cap=8 * 1024**2): the default is unchanged for every existing caller
    (schedules, census, schedule_recovery).
  - receipt() passes cap = 32 MiB for artifact paths under docs/evidence/forward/scoreboard/ and
    8 MiB otherwise. Ceiling: 32 MiB = 3.2x the largest observed scoreboard (9,942,028 B, 09-30).
    Upgrade path: a measured per-prefix table like paper_desk_issue_common.READ_CAPS.
  - The read-loop except at :112 also takes ValueError (evidence_too_large, nonfinite_json:*). It appends
    artifact_too_large when str(exc) == "evidence_too_large", else artifact_unreadable, using the S711
    counting lines unchanged.
  - The digest mismatch (:109) still raises. invalid_night_record, duplicate_night_step and
    night_noncanonical_as_of are unchanged. No new key in the receipt() return dict.
(2) scripts/platformkit/ops/paper_desk_actions.py (294 LOC; zero net lines). In accepted_receipt, line
    136 becomes a count n over parsed["arm_outcomes"] of artifact_refusal_reasons on outcomes WITHOUT
    an artifact_resolution key (i.e. not KILLED steps):
  - when n > 0: row["refusals"]["night_artifact_refused"] = n;
  - row["receipt_accepted"] = (n == 0).
  "night_artifact_refused" is in neither night success nor benign (paper_desk_attention.py:76), so
  the row classifies as attention. paper_desk_attention.py is NOT edited. The legacy branch
  (:141-153) and the existing-receipt branch (:162-165, artifacts=False) are byte-identical.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = construct cases passing in tests/platformkit/ops/test_s712_artifact_read.py, one file per process.

  before = on master:
    - case (a) raises ValueError("evidence_too_large") out of receipt();
    - case (c) row decision night_partial, refusals {}, classification success.

  bar = 6 of 6 pass. Each of these existing files must be green, one file per process, with no
  assertion edited:
    - tests/platformkit/ops/test_paper_desk_legacy_nights.py
    - test_paper_desk_s520_night2.py
    - test_paper_desk_r3_runtime.py
    - test_paper_desk_r4_runtime.py
    - test_paper_desk_tick.py
    - test_paper_desk_amendment.py
    - test_paper_desk_evidence.py
    - test_paper_desk_r2_evidence.py
    - tests/platformkit/execution/test_s711_empty_claims.py
    - tests/platformkit/execution/test_paper_night_inputs_e2e.py
    - every other tests/platformkit/ops/test_paper_desk*.py file (list each count in the result memo)

  n = 6 (CONSTRUCT):
    (a) RAN scoreboard artifact of 8 MiB + 1 B (valid JSON, digest recorded): receipt() returns; the
        outcome carries its summary; no refusal.
    (b) the same artifact at 32 MiB + 1 B: artifact_refusal_reasons == ["artifact_too_large"]; no raise.
    (c) RAN qualification artifact present, zero bytes, digest recorded, driven through
        Desk.night() with a stub child exiting 3: decision night_partial, refusals
        {"night_artifact_refused": 1}, receipt_accepted False, classification attention, desk audit
        written.
    (d) RAN artifact holding NaN: artifact_unreadable counted; no raise.
    (e) KILLED step with a dropped claim plus clean RAN steps: refusals {} and classification success
        (S711 reasons do not count).
    (f) a canonical night with steps=[] and a non-canonical legacy-listed night: rows byte-equal to
        master's (decision, reason, refusals, receipt_accepted).

  eye check = n/a (S-row). Reproduction = run the test file.

  must not move:
    - document() default cap and its other callers;
    - the S602 legacy branch;
    - the existing-receipt branch;
    - receipt() return keys;
    - every committed night / scoreboard / desk audit;
    - paper_desk_attention.py, paper_night*.py, paper_desk_config.json bytes (S709 CONFIG_SHA pin).

NON-TAUTOLOGY: (c) drives the real Desk.night() post-run branch and the real classification(). Only
the child process is stubbed. Removing either hunk turns (b) or (c) red.

OUT OF SCOPE: a PARTIAL-night revision queue (memo B2: no revision can change a deadline-killed
verdict, S586 refuses rN, S778 is the closure path). Re-observing night 10-06 (its attention closes
through an S778 acknowledgement). The digest-mismatch raise.

NOT VERIFIED: tick RSS for a 32 MiB parse (ESTIMATE <= ~180 MB at the S718 ratio); night 10-07's
scoreboard size.

AMENDMENT 1 (2026-10-09 14:4xZ, post-landing disclosures by the paper-desk-improve run; binding on any follow-up):
- LANDED b33df3001 (candidate e00178360; codex sol contract tier ACCEPT, Opus adversarial tier ACCEPT). Prefix rule as
  built: path.is_relative_to(root / FORWARD / "scoreboard") on the RESOLVED artifact path; Desk resolves root
  (paper_desk_tick.py:34, :281); a direct receipt() call with an unresolved root (a junction) raises in local() before
  any cap, unchanged from master.
- The read-loop except takes every ValueError document() raises: evidence_too_large -> artifact_too_large;
  nonfinite_json:*, duplicate_json_key (paper_desk_steps._pairs), JSONDecodeError, UnicodeDecodeError ->
  artifact_unreadable (artifact_empty when the recorded bytes == 0). duplicate_json_key was not named by the DESIGN;
  it is counted, never valid (the S711 intent). OSError still raises.
- Coverage gap (adversarial mutant M5): no construct covers a non-scoreboard RAN artifact over 8 MiB, so a mutant that
  gives every artifact 32 MiB passes 6 of 6. A follow-up adds case (g): an 8 MiB + 1 B qualification artifact ->
  artifact_refusal_reasons == ["artifact_too_large"].
- receipt_accepted False keeps a prior night_failure_state entry for that day (master deleted it on accept); only
  failed_night_backoff reads it, and night() returns before backoff once a record exists. Cosmetic; not rowed.
- Measured sizes: scoreboard 10-06 9,740,112 B, 10-07 12,446,587 B, 10-08 9,292,275 B; 32 MiB = 2.7x the largest.
- NOT VERIFIED: tick RSS on a 32 MiB parse (ESTIMATE ~285 MB at the 8.9x ratio measured on the 10-07 read); the
  post-run parse runs under no fresh RAM gate (paper_desk_actions.py:225; the S522 light-step gates exclude night).
- New rows from the tiers: S803 (scanner tick_refused keys on decision / reason only), S804 (rolling week artifact
  rewritten by later nights breaks a later artifacts=True read of an older night).
