# Paper desk silent-failure audit

The live state shows two skipped nights that aged out of the desk's scan, two partial nights that later ticks do not retry, and a September 30 receipt that is accepted despite a zero-byte qualification artifact. The task log reports `EXIT:0` for a tick whose status says `refused`. Findings are ranked by severity, then likelihood. "Reachable only" means the code path is established, but I did not find it in the inspected live state.

## P0 - loses or corrupts a night

1. **A partial night becomes terminal.** `scripts/platformkit/ops/paper_desk_actions.py:159-163`; `scripts/platformkit/execution/paper_night.py:240-247`  
   Trigger: A night writes a `PARTIAL` canonical receipt. September 29 and 30 both did; September 29 lacks its scoreboard artifact.  
   Wrong outcome: Later ticks accept the existing receipt and skip the night; the desk never invokes the runner's revision path. Fix: Keep partial nights in a durable retry queue and run a bounded, explicit revision when their failed inputs recover.

2. **Unresolved nights age out after three days.** `scripts/platformkit/ops/paper_desk_tick.py:217-224`; `scripts/platformkit/ops/paper_desk_attention.py:188-195,241-249`  
   Trigger: A served schedule is absent until its night falls outside `backfill_days=3`. Live `status.json` lists September 27 and 28 as expired `night_skipped_no_schedule` attention.  
   Wrong outcome: No later tick scans either night, even if its schedule appears; expired attention is eventually dropped. Fix: Scan a durable queue of unresolved dates and clear each entry only after a valid receipt or explicit resolution.

3. **A killed qualification leaves an empty canonical artifact.** `scripts/platformkit/ops/forward_qualification_daily.py:58-70,197`  
   Trigger: The producer reserves the final output name before working, then is killed. The September 30 receipt records a 900.297-second deadline kill and a present, zero-byte qualification file.  
   Wrong outcome: The canonical file is unreadable; a later qualification run would choose `.r1` while the empty canonical path remains. Fix: Reserve a separate claim file and publish the final name only after the artifact is complete.

4. **Sleep can permanently miss a D1 schedule.** `scripts/platformkit/ops/paper_desk_actions.py:92-106`; `docs/operations/install_paper_desk_task.ps1:87-93`  
   Trigger: The laptop resumes after local and UTC dates diverge, about 19:00 Chicago time during daylight saving time. The installed task definition has `WakeToRun=false`. Reachable only for this specific window.  
   Wrong outcome: The tick records `schedule_missed_window`; the next day it targets a different D1, so the missed schedule has no automatic backfill. Fix: Persist missing target dates and support a dated schedule recovery run.

5. **One sport's fetch failure can be sealed into a complete schedule.** `scripts/platformkit/execution/forward_schedule_sources.py:141-157`; `scripts/platformkit/execution/schedule_d1.py:204-208,216-264`  
   Trigger: One configured sport's schedule fetch fails while the other produces rows. Reachable only.  
   Wrong outcome: The writer publishes the artifacts and pointer without the failed sport; subsequent ticks see a complete schedule and do not retry it. Fix: Refuse publication if any requested sport has a network or payload failure.

6. **Missing next-day capture can shrink scored outcomes without failing the night.** `scripts/platformkit/execution/paper_night_inputs.py:114-124`; `scripts/platformkit/execution/ingame_scoreboard.py:179-185,196-242`; `scripts/platformkit/execution/registry_scorer_e_night.py:70-93,143-145`  
   Trigger: A served game crosses UTC midnight and its D+1 book or state shard is absent. Reachable only; the inspected September 29-30 receipts did not show this absence.  
   Wrong outcome: Fill inputs omit the shard, scoreboard losses exclude unsettled outcomes, and Registry E can publish `complete=true` for surviving rows. Fix: Require expected D and D+1 shards before scoring and mark each affected artifact incomplete when coverage is missing.

7. **A Windows replace failure can strand a schedule halfway through publication.** `scripts/platformkit/execution/schedule_d1.py:252-265`; `scripts/platformkit/ops/paper_desk_evidence.py:31-57`; `scripts/platformkit/ops/paper_desk_actions.py:97-102`  
   Trigger: A transient `os.replace` permission failure occurs after one or more staged files have been published, as can happen under a Windows file lock. Reachable only; no such live failure was established.  
   Wrong outcome: There is no rollback; later ticks classify the mixed artifact set as incomplete or invalid and require intervention. Fix: Retry transient replace failures within a bound, roll back a failed publication, and permit recovery of an incomplete set.

## P1 - hides a failure

8. **An unreadable night artifact is later called accepted.** `scripts/platformkit/ops/paper_desk_evidence.py:99-105`; `scripts/platformkit/ops/paper_desk_actions.py:129-134,159-163`  
   Trigger: September 30's sealed qualification artifact is zero bytes. Full validation raised `JSONDecodeError`, recorded in live `night_attention`. A later tick used `artifacts=False`.  
   Wrong outcome: Live status then says `receipt_accepted=true` and `night_skipped` without validating that artifact. Fix: Validate sealed artifacts on every existing-receipt decision; retain an explicit unresolved state and revision path for invalid evidence.

9. **Registry E returns success for a refusal.** `scripts/platformkit/execution/registry_scorer_e_night.py:248-251`; `scripts/platformkit/execution/paper_night.py:255`  
   Trigger: The caller policy is not yet effective. September 29's E artifact says `REFUSED/config_not_effective`, but the child exited 0 and the night recorded the step as `RAN`.  
   Wrong outcome: E contributes no rows yet can satisfy the night's complete predicate if other steps pass. Fix: Return a refusal exit code and check E artifact status in the parent.

10. **Incomplete training history returns success.** `scripts/platformkit/execution/scoreboard_history.py:112-115,150-176`; `scripts/platformkit/execution/paper_night.py:255`  
    Trigger: A prior schedule or shard is missing. The September 30 receipt records history `complete:false`, `incomplete:2`, exit 0, and no reason.  
    Wrong outcome: The runner can count incomplete history as a successful step. Fix: Return nonzero for `result.complete=false` and validate that field before marking the step successful.

11. **An incomplete week can satisfy the night complete predicate.** `scripts/platformkit/execution/paper_night.py:162-167,255`  
    Trigger: The week reporter exits 3 with a fresh `INCOMPLETE` artifact, as recorded in the September 30 receipt.  
    Wrong outcome: The runner leaves the step reason empty, so this step does not prevent `COMPLETE`. Fix: Give the step a `week_incomplete` reason or make the complete predicate check `week_status`.

12. **Task Scheduler sees success when the tick refuses work.** `scripts/platformkit/ops/paper_desk_tick.py:234-242`  
    Trigger: Any step refusal without a journal write failure. Live status has an October 2 tick marked `refused/step_refusals`; the corresponding task-log period reports `EXIT:0`.  
    Wrong outcome: Task Scheduler and exit-code monitoring cannot distinguish that failure from a clean tick. Fix: Return nonzero for step refusals while leaving future scheduled ticks enabled.

## P2 - hygiene

13. **Low disk has no retry spacing.** `scripts/platformkit/ops/capture_supervisor.py:204-230`  
    Trigger: Free disk falls below the configured 2,000 MB floor. Reachable only.  
    Wrong outcome: The supervisor records and flushes another refusal about every five seconds on the disk that is already low. Fix: Advance `next_start` on disk refusal with capped backoff and rate-limit repeated journal entries.

## Top 5 to fix today

1. Retry or explicitly resolve partial nights; validate the September 30 empty artifact.
2. Keep unresolved nights eligible beyond the three-day scan.
3. Recover D1 schedules missed while the laptop sleeps.
4. Refuse a schedule when either configured sport's fetch fails.
5. Fail scoring when required D+1 capture is missing.

## Not verified

No tests, network calls, or file changes were made. I inspected the installer definition, not the effective Task Scheduler registration. I did not establish a numeric improvement in any metric from missing capture, a live Windows replace failure, or a production RAM-cap overrun. `evidence_push.py` had no caller in the traced nightly tick path.