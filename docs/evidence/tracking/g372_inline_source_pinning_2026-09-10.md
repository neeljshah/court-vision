VERDICT: PARTIAL (adjudicated) -- phase A ACCEPT; phase B measured then REVERTED (coverage 43/81 by construction; repeat-row wave after the restart, unattributed)
# G372 inline source pinning -- phase B (authorized deploy-only overlay + live measurement)
Spec `docs/evidence/tracking/specs/G372_spec.md`; contract `docs/evidence/tracking/VERIFIER_CONTRACT.md` A/B plus Q1/Q6, self-checked. Phase A (code + attribution + scratch controls) was verified ACCEPT by codex-sol at `c25ee30aa`; its full memo is preserved byte-for-byte beside this one as `g372_inline_source_pinning_2026-09-10_phase_a.md` and its verdict line is superseded by line 1 above.
B5: Deployed to /workspace/deploy/nba-ai-system under the 2026-09-08 user authorization after phase-A ACCEPT; the landing repo's scripts/ is unchanged (PROPOSED diff only); landing ADJUDICATED.
Machine (S1): pod `d69708b8b854` at 213.192.2.120:40117, CPU only, 27 cores, daemon `--workers 8`, thread caps 1, poll `--interval` 20 s. `/workspace/nba-ai-system` (MAIN), the feeder and the quota guard were never touched; every lane write went to `/workspace/wt/a9` except the deployed daemon's own writes and the one disclosed pollution below.
Q1 SEAL ORDER. `g372_prereg_amendment_A3_2026-09-10.md`, SEAL `3ed7470864af67da4dd089bab017f5625be7b86462f22b24d5d8207620dc3cd6`, commit `b0b6b960`, was sealed ALONE and predates every number below. It fixes the restart, both windows, the coverage and pin denominators, the paired-replay construction, the 100-minute replay budget and the revert rule. The prereg, A1 and A2 are byte-unchanged.
## Deploy (full stdout in `deploy_log.txt`)
CODE IDENTITY before the overlay: deployed `track_daemon.py` = `9747d9a085405c492f04c4e3b162ed8b1d897309da6f0f9c014cb7092056f5ac`, byte-identical to the spec's cited hash. NO DRIFT.
Backup `scripts/platformkit/track_daemon.py.bak_g372_2026-09-10` written first (same digest). `patch -p1 --dry-run` rc 0, then `patch -p1` rc 0, 7 hunks. Patched file `e05ea5b6a3618c67144c04208838497d777838570051bfcf3135c086591c7611`. `python3 -m py_compile` rc 0. The sidecar module the hook imports was copied INTO the deploy tree at `scripts/platformkit/tracking/g372_source_sidecar.py` (`9c59f8b2f287eea617a82abab66f5c992506660f5d79cef62bbba8db2ab0412d`); a grep confirms the deploy tree imports nothing from `/workspace/wt`. Import check printed `PID_FILE /workspace/track_daemon.pid`, `IDENTITY data/tracking/source_identity`, deploy manifest `2bbd585a6450514d7c8b3e69a695df4e2e2d583589ee5c1d45e855da2582b33f`.
SMOKE GATE (A3.2) PASSED before any restart: the patched claim path was exercised out of process on one scratch copy of a staged source, writing only under `/workspace/wt/a9/scratch_g372/`. Bind 1.090 s; sidecar committed with all 11 `SIDE_FIELDS`; `start_time_kind DECODED_PTS`; `source_bytes` equal to the file size; one RESERVED journal row. The follow-on `run_clip` schema confirmation on that same source did NOT run: its preflight rejected the clip (median person count 0), a property of the picked source, not of the overlay, which touches no line of `run_clip.py`. The producer-schema evidence below is the LIVE before/after comparison, which is stronger.
## Restart (exactly once)
`T_RESTART` 2026-09-10T19:33:10Z: SIGTERM to pid 475000. Eight in-flight `run_clip` children were running (`fiba-Y1cgaIWW8gk_s5543`, `RIrGQJ_jsGQ_s1475`, `RIrGQJ_jsGQ_s155`, `RIrGQJ_jsGQ_s2795`, `RIrGQJ_jsGQ_s4115`, `RIrGQJ_jsGQ_s5435`, `0KIBu1jQBL8_s5730`, `1E5Rw89keTg_s599`); the new daemon logged `reaped 8 orphaned tracking jobs from a previous daemon` and re-claimed their sections.
Relaunched by `bash /workspace/start_daemon.sh 8` at 19:34:11Z. NEW PID 127417. Log `/workspace/track_daemon_2026-09-101934.log`. FIRST CLAIM 19:34:13Z. WATCHDOG CLEARED at 19:41:36Z (7.4 min, bar 20 min): `WeheQidCPXI_s1454 tracked seconds 408` with `source_identity_path data/tracking/source_identity/WeheQidCPXI_s1454.source_identity.json`. Zero tracebacks in the log across the whole 61-minute window.
## Windows (`before_window.csv`, `after_window.csv`, `throughput_phaseb.csv`; snapshots `ledger_snapshot_before.jsonl` `43e949405d5c892dc45d8edb1600362497fa135300aafd7cee1039de154fb9ae` and `ledger_snapshot_after.jsonl` `c494d1e2be79b7b1627e5e49f2979c5c813a6fb3d585e3b259bf9292fb9d0b3e`)
| window | span | rows | unique | median s/clip | clips/h | arrivals | mean active load | tracked / thin | tracked median s | repeat rows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BEFORE | 18:33:10Z-19:33:10Z | 78 | 75 | 406.0 | 78.0 | 73 | 7.617 | 68 / 10 | 426.0 | 3 |
| AFTER | 19:34:13Z-20:34:13Z | 78 | 43 | 40.0 | 78.0 | 43 | 4.639 | 36 / 42 | 426.5 | 35 |
Straddle rows 0 (every AFTER row was claimed after `T_RESTART`), censored rows 0, decoded-frames median 3901.0 in BOTH windows. The all-rows median ratio 0.0985 is NOT a throughput result: the workload composition changed (thin rows 10 -> 42, repeat rows 3 -> 35), so the two medians describe different mixes. The tracked-only figures 426.0 -> 426.5 condition on outcome and are DESCRIPTIVE only. Per the spec, unchanged clips per hour is never a pass on its own; the scored clause is the paired replay.
## Coverage (`sidecars_live.csv`, `claim_journal_live.csv`, `summary_phaseb.json`)
Claim journal in-window: 81 RESERVED attempts over 43 unique `game_id` and 13 distinct videos; 38 TERMINAL_ERROR rows, every one `FileExistsError`.
COVERAGE PER CLAIM ATTEMPT = 43 valid immutable sidecars / 81 attempts = 0.530864. This FAILS the 1.000 bar and is the binding number, matching the spec's own denominator ("all unique claim attempts"). Coverage per unique `game_id`, the A3.6 denominator, is 43/43 = 1.000000 over 13 distinct videos; it is printed beside the failing number, never instead of it.
CAUSE, measured: `write_sidecar` opens with mode `xb`, so a RE-CLAIM of a `game_id` already bound cannot commit a second sidecar. Seven sections were re-claimed 38 times between them and every one of those attempts recorded `FileExistsError` and left `source_identity_path` null. Tracking was never gated, quarantined or retried on it (B3/B4 respected): all 81 completions carry the key and the failing 38 pass straight through.
## Independent agreement (`pins_live.csv`, `join_live.csv`)
The watcher polled the DEPLOYED claim journal and, for every new reservation, copied the staged source to scratch and read it with the G369 helpers only (`_file_record`, `_probe`, `_manifest`); `cmd_pin` and `cmd_exact_align` were never called. Join key `game_id` plus source SHA-256.
AGREEMENT = 43 AGREE / 43 attempted pins = 1.000000, 0 DISAGREE, 0 rows omitted, 13 distinct videos, maximum pin lag 2.0 s against the 60 s rule. Both bars (>= 30 pins, >= 10 videos) are MET. Carried caveat: both sides stream SHA-256, so this proves the two code paths bind the same bytes, not that the digest is correct against a third implementation.
## Controls (`controls_live.csv`; CONSTRUCT, enumerated separately, never counted toward n)
identical_read PASS on live sidecar `0KIBu1jQBL8_s5730.source_identity.json`; deterministic_write PASS (two writes of that fixed payload reproduce its exact digest); immutable_no_rewrite PASS (`FileExistsError`).
## Schema (`schema_diff_phaseb.txt`)
PRODUCER TABLE `tracking_data.csv`: before `0KIBu1jQBL8_s155` 73 columns, after `G8bPOW37Sp0_s615` 73 columns, only_before [], only_after [], order identical -- DIFF EMPTY.
COMPLETION LEDGER key set: removed_or_renamed [], added ["source_identity_path"] -- ADDITIVE ONLY. All 81 AFTER rows carry the key; 43 carry a non-null value.
## Paired throughput replay (`replay_pairs.csv`, `replay_pairs_run1_sources_pruned.csv`)
RUN 1 (20:37:32Z-21:00Z) was DISCARDED as a broken procedure, not for its result: it read each source in place from `footage_corpus`, and the pod quota guard -- retuned at 19:53:34Z by another session to high 35000 / min_age 90 and not ours to touch -- deleted the source between the control and the treatment arm. 17 pairs completed, only 3 with both arms rc 0; four failing sources were checked and all four carry a guard DEL line and are gone. Both files are archived.
RUN 2 ran inside the SAME sealed 100-minute budget (it drained its queue at 21:54:41Z, before the 22:17:32Z deadline) with one correction: each source is copied to scratch at pair start and BOTH arms read that one pinned copy. Sealed listing at replay start: 39 eligible, `119c67c6538d7c4c70e7c3af968083361311e9e4918431d1aa2ac24f7770156e`, k = 1, so all 39 were sampled -- no head slice.
RESULT, below bar: 27 completed pairs (all with both arms rc 0), 12 SOURCE_GONE (the guard pruned them before their pair started; retained in the file, never dropped). Control median 368.64 s, treatment median 375.79 s, RATIO 1.0194, median bind 1.52 s plus the 20 s worst-case tick deferral. THROUGHPUT CLAUSE = NOT VALIDATED at n = 27 against the sealed >= 30 bar. The 1.0194 figure is printed as a below-bar measurement and is NOT a pass; the bar was not lowered.
## Named failing or NOT VALIDATED clauses
1. Coverage per claim attempt 0.530864 (bar 1.000) -- the `xb` sidecar cannot bind a re-claim.
2. Paired throughput NOT VALIDATED at n = 27 (bar >= 30) -- 12 of 39 sealed inputs pruned mid-run by a quota guard the lane may not touch.
3. `_WEIGHT_DIGEST` is EMPTY `{}` on this deploy: it globs `data/models/*.pt`, which holds only `osnet_x0_25_imagenet.pth`, while the detector weights actually live at `models/weights/yolov8n_ball.pt`, `yolov8n.pt`, `resources/yolov8n.pt` and `yolov8n-pose.pt`. Every live sidecar therefore pins routes but NO weights.
4. The deploy tree's own per-file daemon test regressed: `tests/platformkit/test_g328_daemon_worker_accounting.py` is 2 passed on the restored backup and 1 failed / 1 passed patched. Two causes: the test's `FakeProc` double replaces `subprocess.Popen` while `bounded_ffprobe` calls `subprocess.run`, and the hook's one-tick claim deferral changes the within-tick active count from 2 to 1. Master is unaffected -- the landing repo's `scripts/` is untouched.
5. The identity thread catches only `(OSError, ValueError)`. The pytest double raised `TypeError`, so two reservations were left with NO sidecar AND NO terminal row -- a silent hole in an append-only journal that is supposed to cover every reservation.
6. `_PENDING` is popped only on dispatch, so a reserved video that stops being claimable leaves a stale entry for the life of the process.
## Disclosures
Running the deploy tree's daemon test at 19:28:50Z and 19:29:16Z wrote two `RESERVED` rows with `game_id "queued"` into the LIVE `data/tracking/source_identity/claim_journal.jsonl` -- a write under `/workspace/data` by this lane. Both predate `T_RESTART`, are excluded from every window by their `claim_utc`, and are visible in `claim_journal_live.csv` with `in_window 0`. No sidecar was created for them.
The re-claim wave itself is MEASURED but NOT ATTRIBUTED: repeat rows rose 3/78 -> 35/78 across the restart. One candidate cause was tested and FALSIFIED -- none of the 7 re-claimed `game_id` has a quota-guard DEL line and all 7 are still in the corpus. A single window cannot exonerate the overlay; this is filed as a new gap.
Wall time: A3 seal 14 min; deploy, baseline test and smoke 9 min; restart 2 min; AFTER window 61 min; replay run 1 23 min plus run 2 53 min; analysis, memo and landing 25 min; about 3 h 07 min.
SHA-256: A3 seal `3ed74708`; PROPOSED diff `e0d8e924`; backup `9747d9a0`; patched daemon `e05ea5b6`; sidecar module `9c59f8b2`; deploy manifest `2bbd585a`; BEFORE snapshot `43e94940`; AFTER snapshot `c494d1e2`. `/workspace/POD_STATE_2026-09-10.md` carries the overlay, the backup path, the restart time, the new pid and the revert recipe.
Q6 automated scan over this memo, amendment A3 and every new phase-B artifact:
```
vocabulary (roi|profit|bankroll|pnl|edge|dollar sign): 0 prose hits; the 2 raw hits are shell variables inside one verbatim ps command line captured in deploy_log.txt -- opaque quoted text, exempt per the Q6 NOTE
retracted figures (18.38|0.119|54.57|8.94|78.11): 0 hits, grep rc 1
```
## NOT VERIFIED
- Whether the overlay caused the re-claim wave. The rate rose across the restart, the one tested cause was falsified, and no controlled comparison was run. NOT ATTRIBUTED in either direction.
- The throughput clause. 27 pairs is below the sealed 30; the 1.0194 ratio is a below-bar measurement, not a verdict, and the window comparison is confounded by the composition change.
- That coverage would reach 1.000 per claim attempt under any workload. It was measured at 0.530864 on this one, and the `xb` re-claim defect is structural, not a sampling artifact.
- The correctness of the SHA-256 binding against a third independent implementation; both sides stream SHA-256.
- That the deployed overlay is safe over a longer horizon than this 61-minute window, or under a daemon restart with a non-empty `_PENDING`.
- The `run_clip` output schema was compared LIVE before versus after and is identical; it was NOT re-confirmed through the smoke path, whose source failed preflight.

## Fix 1c corrections (2026-09-10, appended; the phase-B text above is preserved as sealed at df95c430d)
## Corrected phase-B join
`join_live.csv` now retains all 81 in-window claim attempts: 43 `AGREE` rows plus 38 `NO_SIDECAR` rows.
Each added row is the matching in-window `pins_live.csv` attempt and records `FileExistsError` in `verdict`.
The first phase-B table omitted those 38 attempts; that omission is corrected here, not hidden.
`summary_phaseb_join.json`: `pins_attempted` 81; `agreement_over_attempts` 0.530864 (43/81); `agreement_over_joined` 1.000000 (43/43).
COVERAGE PER CLAIM ATTEMPT = 43/81 = 0.530864, the named failing clause against the 1.000 bar.
The `xb` sidecar write structurally prevents a second bind for a re-claim, so this is construction, not a sampling claim.

## Replay and controls
The paired replay completed 27/39 pairs. It remains NOT VALIDATED against the sealed >= 30-pair bar; no threshold moved.
Controls PASS: identical_read, deterministic_write, and immutable_no_rewrite. The shared SHA-256 limitation remains disclosed.
The producer table stayed at 73 columns before and after; completion added only `source_identity_path`.

## Post-window revert
At 2026-09-10T22:15Z the deploy `track_daemon.py` was restored to sha256 `9747d9a085405c492f04c4e3b162ed8b1d897309da6f0f9c014cb7092056f5ac`.
The withdrawn overlay sha256 was `e05ea5b6a3618c67144c04208838497d777838570051bfcf3135c086591c7611`; it remains beside the daemon as `track_daemon.py.g372_overlay_reverted_2026-09-10`.
The daemon was restarted after the restore; the re-claim wave is NOT ATTRIBUTED, and the memo's quota-guard hypothesis was falsified.

## Adjudicated status
After the window, repeat-or-duplicate ledger-row share was 1.000 in both the 30-60 and 60-120 minute post-restart windows, versus 0.181 in the hour before; the bridge held only 9 files.
This establishes a repeat-row wave after restart, not its cause. The overlay is withdrawn.
Landing status is PARTIAL (adjudicated): the claim-time identity hook works for unique sections, but no re-deploy is authorized.
The allocated successor must add an idempotent bind, weight-digest fix, full exception scope, `_PENDING` fix, `test_g328` repair, and attribution of the re-claim wave before any re-deploy.

## NOT VERIFIED
Whether the overlay caused the re-claim wave remains NOT ATTRIBUTED; the quota-guard hypothesis was falsified, not a causal attribution.
Coverage at 1.000 per attempt and paired throughput remain unverified; 43/81 and 27 pairs are the controlling results.

## Refreshed digests and Q6
Corrected join sha256: `40793e7317c9d637fbb583781f6da834612421998f49dc46dabc04445ea079f0`; corrected summary sha256: `b09f6eb51e238f07157dbcc0a7a74eccb98994a9e3d1e8e3d67e7aa724b606e4`.
Q6 scan over touched-file content used single-character-class vocabulary and figure patterns plus the currency-character pattern: 0 hits.
No prohibited performance or threshold claim is made; the named coverage failure and replay NOT VALIDATED result remain controlling.
Post-revert measurement (orchestrator, 22:40Z): 26 ledger rows in the 25 min after the revert, repeat-or-duplicate 0 -- the re-claim loop is attributed to the deployed overlay by revert-and-observe (one uncontrolled comparison; no re-deploy).
