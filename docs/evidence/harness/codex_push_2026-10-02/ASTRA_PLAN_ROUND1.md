## 1. VERDICT

1. **The immediate completion blocker is qualification runtime.** On 09-30 it hit the 900-second deadline with 4,025,282,560 bytes free at launch; the slow phase remains UNKNOWN. Adding RAM alone does not resolve this receipt. `docs/evidence/forward/nights/2026-09-30.json:steps[name=qualification]`
2. **Second is capture quality and continuity.** All six served games with valid qualification receipts failed; the latest issue report records three 14.9-hour capture outages. `docs/evidence/forward/qualification/{2026-09-22,2026-09-29}.json:games`; `docs/evidence/forward/issues/2026-10-02.md:34-36`
3. Zero COMPLETE fitted nights are evidenced, but a FITTED scoreboard exists. All five night records are PARTIAL. `docs/evidence/forward/nights/{2026-09-24,2026-09-25,2026-09-26,2026-09-29,2026-09-30}.json:status`; `2026-09-30.json:steps[name=scoreboard].training_label`
4. "Every served game since 09-22 failed" is overstated: six failures are observed; the remaining 23 served entries lack valid qualification evidence, including dates not yet due. Their qualification is UNKNOWN. `docs/evidence/forward/schedules/*_maker_forward.json`; `docs/evidence/forward/qualification/*.json`
5. Keep the model as the measured staleness backstop and prioritize execution-quality and calibration receipts. `docs/evidence/harness/INGAME_MODEL_2_PLAN_2026-09-29.md:255-270`; `docs/JOB_EVIDENCE_PACKET.md:96`
6. The branch queue is not a queue of uniformly ready landings: S691 has an uncommitted blocking correction. `private/cloud/verify-S691-2026-10-01:docs/evidence/harness/S691_cloud_verify_2026-10-01.md:38-76`
7. Current processes, hardware adoption, remote-ref freshness and the next feasible seven-night calendar are UNKNOWN. This review used local reads only; no files changed, tests ran or network calls occurred.

## 2. CRITICAL PATH

Proposed success contract: count a night only when its prospectively declared, nonempty served cohort passes the unchanged qualification rules; required producers complete; scored receipts and paired losses exist; and input availability and actual execution time are evidenced. Retain the full selection, unserved entries and exclusions. Seven means seven consecutive UTC dates: empty schedules, missing receipts and retrospective reconstructions do not count. This operational target does not satisfy a statistical sample floor.

The existing qualification rules are coverage >=90%, >=480 decisions, book gaps median <=45 s/p95 <=90 s/max <=120 s, state gap <=30 s, and complete tape coverage without fatal gaps. `scripts/platformkit/execution/forward_replay_qualification.py:15-25,64-90`

| Order | Row; owner; platform | Smallest necessary action | Evidence of need | Artifact proving completion |
|---|---|---|---|---|
| 1 | NEW qualification completion; **codex-build; PORTABLE** | Profile the existing path, repair the measured slow phase and eliminate empty canonical output after interruption. | `docs/evidence/forward/nights/2026-09-30.json:steps[name=qualification]`; `scripts/platformkit/ops/forward_qualification_daily.py:58-70,197,275-279` | A reviewed candidate preserving qualification results, followed by a WINDOWS replay of identical input prefixes finishing below 900 s within the existing memory ceiling. |
| 2 | S673; **owner-manual; WINDOWS** | Keep the recorder powered and logged on; establish the 05:45Z power/RAM preflight. | `docs/evidence/HARNESS_GAPS_2026-09-03.md:783`; `docs/evidence/forward/issues/2026-10-02.md:34-36` | Dated preflight plus uninterrupted heartbeat/actual-start evidence through the night. |
| 3 | S561, then S598/S597 part 1; **claude-land; WINDOWS** | Land and adopt existing capture candidates in a permitted between-game window. Do not dispatch replacements. | `docs/operations/DESK_STATE.md:73-78,95`; `docs/evidence/tracking/specs/S598_spec.md:6-10` | Adoption receipt with code identity and child start time; depth persists beyond the first hour through the declared terminal boundary. |
| 4 | S597 part 2; **codex-build; PORTABLE** | Produce the served-ticker tape-latency census; apply no transport change before its gate. | `docs/evidence/tracking/specs/S597_spec.md:8-14` | `docs/evidence/forward/latency/<first>_<last>_trade_tape_latency.json`; >=200 observations and p50 <30 s, or the prescribed next lever. |
| 5 | S597 levers / conditional S660-S661; **owner-manual; WINDOWS** | Adopt one measured lever at a time. Use the socket only if needed after the REST changes. | `docs/evidence/tracking/specs/S597_spec.md:12-14`; `docs/evidence/HARNESS_GAPS_2026-09-03.md:770-771` | One nonempty served cohort passes qualification; socket route additionally has its paired REST comparison and reconnect receipt. |
| 6 | S659, S690, S676, S678; **claude-land; WINDOWS** | Finish adoption/publication corrections, publish health independently of adoption success, and establish pre-read manifests. | S659 branch memo `:89-99`; S690 branch memo `:107-110`; `docs/evidence/HARNESS_GAPS_2026-09-03.md:786,788,802` | Allowlisted publication receipts, manifest citation, off-box missing-heartbeat alert and actual-start audit. Branch memo paths are expanded in section 4. |
| 7 | S659/S680; **owner-manual; WINDOWS** | Execute the spare-laptop runbook and enforce one publishing recorder. Respect receipt and seal conditions before cutover. | `docs/operations/RECORDER_LAPTOP_RUNBOOK.md:1-6,131-141`; `docs/evidence/HARNESS_GAPS_2026-09-03.md:790,801` | Hardware adoption receipt, second-writer refusal, paired-host comparison and one authoritative recorder identity. |
| 8 | S558; **claude-land; WINDOWS** | Add the minimal unattended S551 receipt hook after qualification works; preserve mixed-sport refusal and the existing seal. | `docs/evidence/harness/PROPOSED_S558_exec_receipts_unattended_2026-09-30.md:9-17,46-67` | Night record lists the execution receipt and its explicit eligibility/refusal status; no silent omitted cohort. |
| 9 | S676/S680; **owner-manual; WINDOWS** | Hold the cohort-selection rule and model identity steady while accruing seven qualifying, complete, scored nights. | `docs/evidence/HARNESS_GAPS_2026-09-03.md:786,790`; `docs/operations/DESK_STATE.md:49-71` | Seven dated night bundles with qualification, scoreboard, execution receipt, paired losses, manifests and health evidence; independent recount equals 7. |

Do not place the S691-S710 event-core program on this shortest path. Its target is broader than the existing nightly replay, which already produced a fitted scoreboard. `docs/evidence/harness/AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md:101-118`; `docs/evidence/forward/nights/2026-09-30.json:steps`

## 3. RANKED ROWS

These are completion scopes for existing rows, except the two explicitly NEW proposals. Acceptance checks below are future work, not tests performed in this review. TODAY means an independent builder in a separate worktree; the lander alone updates shared register/handoff files.

**Protected set P, binding on every row:** all files listed in `docs/operations/DESK_STATE.md:64-71`: the scoreboard/walkforward identities; `baseline_four_arm*`; cross-venue and game-market links; soccer aliases/crosswalk; every `docs/evidence/forward/model2/PREREG_M2.json:pins` entry; and the nine S515 files listed in `docs/evidence/harness/S515_live_shadow_quoter_2026-09-29.md:11-19`. Also preserve every PREREG and sealed S551 implementation. A separate chain step is required for any identity change.

1. **NEW - Qualification runtime and publication; M; TODAY: YES.**
   - Goal: complete the existing qualification without changing its answer.
   - Own N: `scripts/platformkit/ops/qualification_runtime_probe.py`, `tests/platformkit/ops/test_qualification_runtime_publication.py`; M: `scripts/platformkit/ops/forward_qualification_daily.py`. Add a measured slow-seam amendment before modifying another module.
   - Accept: identical frozen input prefixes finish <900 s and <=1,572,864,000 bytes; every game/count/reason matches the reference; interruption leaves valid refusal or no canonical JSON, never an empty one.
   - Control: forced termination, duplicate launch, future-row truncation and interrupted retry preserve prior receipts. Do not raise the deadline to manufacture completion.
   - Evidence: `docs/evidence/forward/nights/2026-09-30.json:steps[0]`; publication reservation at `forward_qualification_daily.py:58-70`. Protect P, capture processes and shared position ledger.

2. **S673 - Recorder preflight; S; TODAY: YES, code/runbook only.**
   - Own proposed N: `scripts/platformkit/ops/recorder_preflight.py`, `tests/platformkit/ops/test_recorder_preflight.py`, `docs/operations/PAPER_DESK_PREFLIGHT.md`; M: none.
   - Accept: one 05:45Z receipt names AC standby, available RAM and process pressure; every missed night has a reason. Missing measurements remain UNKNOWN.
   - Control: sleeping-host and low-RAM cases cannot produce READY; the tool changes no power setting and kills nothing.
   - Evidence: `docs/evidence/HARNESS_GAPS_2026-09-03.md:783`. Protect P and running captures; owner applies settings.

3. **S561 - Correct live-window classification; S; TODAY: LAND EXISTING, not a new build.**
   - Own M: `scripts/platformkit/ingame/kalshi_series_scope.py`, `tests/platformkit/test_kalshi_book_capture.py`; existing candidate additions: `tests/platformkit/ingame/test_s561_live_window.py`, fixture `s561_market_rows.json`, `docs/operations/relaunch_books_s561_2026-09-30.ps1`.
   - Accept: measured expiration/start fixtures reproduce the declared live classifications; adoption records the landed SHA and a new books child.
   - Control: boundary and process-selection cases; no unrelated process stopped.
   - Evidence: `docs/evidence/HARNESS_GAPS_2026-09-03.md:706`; `private/parked/S561-h232` changed-path inventory. Protect P; WINDOWS landing/adoption only.

4. **S598/S597 part 1 - Whole-game focus; M; TODAY: FINISH/LAND EXISTING.**
   - Own N: `scripts/platformkit/ingame/capture_served_window.py`, `local_capture_discovery.py`; M: `capture_scheduler.py`, `local_capture_runner.py`; corresponding candidate tests and dated relaunch script.
   - Accept: every specified boundary case passes; served depth continues beyond +3600 s to the declared terminal/cap boundary; request budget unchanged; adoption RSS increase <=150 MB.
   - Control: restart at +7200 s, terminal market still draining, capacity contention, absent terminal evidence.
   - Evidence: `docs/evidence/tracking/specs/S598_spec.md:6-17,100-105`. Protect P and S561-owned file; no parallel scheduler edits or running-capture changes.

5. **S597 part 2 - Measure tape before another transport; S; TODAY: YES, census only.**
   - Own N: `scripts/platformkit/ingame/trade_tape_latency.py`, `tests/platformkit/ingame/test_trade_tape_latency.py`; M: none in this first dispatch.
   - Accept: >=200 served observations; p50 <30 s yields `none_needed`; >=30 s selects the next prescribed lever; streaming RSS <=400,000,000 bytes.
   - Control: 199 observations is insufficient; exactly 30 s triggers; missing and negative timestamps are counted; backfill and live rows remain separate.
   - Evidence: `docs/evidence/tracking/specs/S597_spec.md:10-18`. Protect P and all capture modules until a separately adopted lever.

6. **S659 - Make recorder adoption actually repeatable; M; TODAY: CORRECT EXISTING BRANCH.**
   - Own candidate `scripts/platformkit/ops/recorder_adopt.py`, `recorder_adopt_git.py`, `recorder_adopt_rules.py`, `recorder_adopt_closures.json`, `docs/operations/recorder_adopt.ps1`; proposed N: recorder-specific rerunnable relaunch scripts and one regression test.
   - Accept: two consecutive fixture adoptions succeed; capture-closure changes either restart exactly the affected capture with heartbeat proof or refuse before pulling.
   - Control: fixed-name stale-lock collision, missing launcher, dirty tree, active game and failed heartbeat.
   - Evidence: `private/cloud/S659-2026-09-30:docs/evidence/harness/S659_cloud_result_2026-09-30.md:89-99`. Protect P; no concurrent S690 edits; hardware adoption WINDOWS.

7. **S690 - Publish evidence despite adoption refusal; M; TODAY: AFTER S659.**
   - Own candidate `scripts/platformkit/ops/evidence_allowlist.py`, `evidence_allowlist_push.py`, `recorder_adopt_evidence.py`; M: S659 integration files; corresponding evidence-push tests.
   - Accept: issue, schedule, night, health and adoption artifacts publish through the allowlist even when a code adoption is refused; no unrelated path is staged.
   - Control: staged outsider, STOP/lock, conflict and refused adoption; never silently discard local evidence.
   - Evidence: `docs/evidence/HARNESS_GAPS_2026-09-03.md:802`; S690 branch memo `:107-110`. Protect P; serialize with S659.

8. **S676 - Count usable nights honestly; S; TODAY: YES, existing-branch corrections.**
   - Own candidate `scripts/platformkit/ops/{slo_status,desk_health,deadman_check}.py`, `docs/operations/SLOS.md`, `tests/platformkit/ops/test_slo_status_s676.py`.
   - Accept: 14-day recount matches source receipts; qualifying, complete, scored and on-time counts remain distinct; missing night/heartbeat alerts fire.
   - Control: canonical `as_of` paired with late `started_utc` is not on-time; one 86,400-second tick cannot conceal the day's outage.
   - Evidence: S676 branch memo `:27-38`; `docs/evidence/forward/nights/2026-09-30.json:as_of,steps[0].started_utc`. Protect P; tick hook stays with the lander.

9. **S678 - Input availability manifests; S; TODAY: REVERIFY EXISTING CANDIDATE.**
   - Own candidate `scripts/platformkit/eval_gate/{corpus_manifest,corpus_manifest_git}.py`, `tests/platformkit/eval_gate/test_corpus_manifest.py`; M outside candidate: none.
   - Accept: manifests for three prospective days precede their scored reads; all full-file hashes reproduce; each night cites its manifest.
   - Control: same-size middle-byte mutation, substituted citation and manifest committed after scoring refuse equivalence.
   - Evidence: `docs/evidence/HARNESS_GAPS_2026-09-03.md:788`; S678 branch memo `:19-24`. Protect P; historical availability cannot be reconstructed by a new manifest.

10. **S680 - One recorder authority and seven-night proof; L; TODAY: YES, pure components only.**
    - Own proposed N: `scripts/platformkit/ops/recorder_lease.py`, `recorder_pair_census.py`, `tests/platformkit/ops/test_recorder_lease.py`; M to publication hook only in a later serialized integration.
    - Accept: second desk ID cannot publish; seven consecutive qualifying scored nights belong to one lease holder; paired-host coverage, tape lag, focus gaps and clock offsets are reported.
    - Control: simultaneous writers, expired lease and missing peer observations; none becomes silent PASS.
    - Evidence: `docs/evidence/HARNESS_GAPS_2026-09-03.md:790,801`. Protect P; use the spare-laptop direction, not the stale VM wording.

11. **S664/S695 - Clock measurement and refusal; S; TODAY: LAND EXISTING IN ORDER.**
    - Own candidate `scripts/platformkit/ops/clock_offset.py`, `clock_guard.py`, `clock_guard_cli.py`, `clock_guard_config.json` and their tests; tick integration remains PROPOSED.
    - Accept: missing offset is `OFFSET_UNMEASURED`; injected +45 s refuses within one tick; declared bounds and observed maximum appear in the receipt.
    - Control: unreachable source never becomes zero offset; clearing the skew clears the corresponding refusal.
    - Evidence: `docs/evidence/harness/AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md:136`; register S664 at `docs/evidence/HARNESS_GAPS_2026-09-03.md:774`. Protect P; actual journal collection WINDOWS.

12. **S558 - Minimal execution receipt scheduling; M; TODAY: YES, wrapper/proposal only.**
    - Own proposed N: `scripts/platformkit/execution/exec_receipt_step.py`, `tests/platformkit/execution/test_exec_receipt_step.py`; later M: `paper_night.py`, `paper_night_steps.py`, `paper_night_budget.json`.
    - Accept: S551 receipt is explicit; S550 runs Sunday only; S516 runs only with shadow rows; absent optional keys preserve the existing plan; mixed-sport nights retain the documented refusal.
    - Control: directory-versus-file CLI outputs, missing shadow rows and prereg refusal exit 3.
    - Evidence: `docs/evidence/harness/PROPOSED_S558_exec_receipts_unattended_2026-09-30.md:19-67`. Protect P; shared night files are lander-only and serialized with row 1.

13. **S684 - Freshness and selection disclosure; S; TODAY: YES, existing-candidate completion.**
    - Own candidate `scripts/platformkit/evidence/{subset_census,subset_census_bound}.py`, `tests/platformkit/evidence/test_subset_census.py`.
    - Accept: age-bucket counts sum exactly to scored ticks; covered/uncovered counts reconcile to the full selection; unsupported headline interpretation is WITHHELD.
    - Control: stale bulk observations labelled fresh, omitted games and missing age values must change the disclosure.
    - Evidence: `docs/evidence/harness/QUANT_GRADE_BUILD_SLATE_2026-09-30.md:72`; `docs/evidence/forward/scoreboard/2026-09-30.json:ticks[].mid_age_us`. Protect P; write sidecars only.

14. **S660/S661 - Conditional socket route; M; TODAY: SIGNER REVIEW ONLY.**
    - Own existing `scripts/platformkit/ingame/kalshi_ws_signer.py`, its test and candidate setup change; proposed S661 N: `scripts/platformkit/ingame/socket_rest_pair_census.py`, its test and a dated owner launcher.
    - Accept: >=95% reconstructed-book agreement within 1 s; zero unresynced gaps; 100 reconnects without authentication rejection; tape p50 <30 s; added RSS <=150 MB; qualification clears or reports NO.
    - Control: dropped sequence, stale credential timestamp and missing resnapshot.
    - Evidence: `docs/evidence/HARNESS_GAPS_2026-09-03.md:770-771`. Protect P and current capture output; owner supplies read-only credentials and approves the extra process.

15. **NEW - Stop truncating valid registry receipts; S; TODAY: YES.**
    - Own N: `scripts/platformkit/ops/registry_e_health_reader.py`, `tests/platformkit/ops/test_registry_e_health_reader.py`; M: the registry-E read seam in `paper_desk_issue_checks.py`.
    - Accept: the existing 3,174,370-byte receipt is read as valid with zero scored E ticks; malformed large receipts still refuse; memory remains bounded.
    - Control: truncated tail, invalid summary type, oversized unrelated fields and missing file remain distinct states.
    - Evidence: `scripts/platformkit/ops/paper_desk_issue_common.py:90-105`; `docs/evidence/forward/registry_e/2026-09-30.json:summary`; `docs/evidence/forward/issues/2026-10-02.md:13`. Protect P and the receipt itself.

## 4. LANDING ORDER

The local inventory contains 64 cloud refs and 13 parked refs. Fifty cloud refs name S6xx/S7xx rows; 48 have substantive implementation/test/operations differences from master after removing S640/S642. That does **not** establish 48 ready landings. Local master is `b16997464c7ee255b8d70d6391b8df77d6ce7d48`. Ref freshness against the server is UNKNOWN. Sources: `.git/refs/remotes/private/{cloud,parked}/`; `.git/refs/heads/master:1`.

For every inventoried ref, the review used:

```powershell
git log --oneline master..private/<branch> | Select-Object -First 4
git diff --stat master...private/<branch>
```

It additionally compared changed implementation files directly with master to detect extracted landings. Unique ancestry alone is insufficient.

| Priority | Exact branch or group | Landing decision and dependencies |
|---|---|---|
| 1 | `private/parked/S561-h232` | Land with books adoption; then the local S598 candidate. S598 has no corresponding private cloud/parked ref in this inventory. `docs/operations/DESK_STATE.md:75-78,154-156` |
| 2 | `private/cloud/S653-S656-fix-2026-09-30`; `private/cloud/S659-2026-09-30`; `private/cloud/S690-2026-09-30` | Transfer prerequisites, then corrected S659, then corrected S690. Do not automate adoption until rerunnable relaunch scripts exist. S659 memo `:89-99`; S690 memo `:107-110`. |
| 3 | `private/cloud/S676-2026-09-30`; `private/cloud/S678-2026-09-30` | Finish carried corrections and verify final candidate content before integration. S676 memo `:27-38`; S678 memo `:19-24`. |
| 4 | `private/cloud/S664-2026-09-30`; `private/cloud/S695-2026-09-30` | Clock journal before clock guard; recorder hook needs its own runtime proof. `docs/operations/DESK_STATE.md:23`; architecture `:136`. |
| 5, conditional | `private/cloud/S660-2026-09-30`; `private/cloud/S694-2026-09-30` | Only alongside S661's approved socket probe. The adapter does not itself establish live qualification. Register `:770-771,806`. |
| 6 | `private/cloud/S684-2026-09-30`; `private/cloud/S663-2026-09-30`; `private/cloud/S682-2026-09-30` | Freshness disclosure, latency ledger, then corrected power ledger using actual S676 input. S682 still names open corrections and absent real accrual input. S682 memo `:31-45`; quant slate `:51,70,72`. |
| Seal queue | `private/parked/S492B-h300`; `private/parked/S502-h342`; `private/parked/S625-h322` | Receipt-gated S492 B, then S502 adoption; S625 waits for its own seal/receipt sequence through S469. Do not land inherited branch content wholesale. `docs/operations/DESK_STATE.md:49-58,78` |
| Soccer queue | `private/parked/S531-h260-rebased`; `private/parked/S534-h261-rebased`; `private/parked/S613-h320` | Resolve S598/S531 scheduler overlap first; S534 reseal precedes S613 using the current addendum. Re-evaluate expired calendar windows from receipts. `docs/operations/DESK_STATE.md:59-60,88` |
| Later architecture | S666 before S667/S668/S669; S670 before S698 | Hold off the seven-night path. These dependencies are explicit. `docs/operations/DESK_STATE.md:23` |
| Later core | S691 before S692/S696/S699/S702; S699 before S700; S702 before S707 | S691 first needs F-A1 committed and verified. Its current review says the proposed fix was reverted. `private/cloud/verify-S691-2026-10-01:docs/evidence/harness/S691_cloud_verify_2026-10-01.md:51-76` |
| Later fill semantics | S671 with S693, then reconsider S703 | Reconcile the duplicated venue-rule implementation before integrating both. S693 branch memo `:33-37`; preserve S703's failed-result evidence rather than adopt its arm, S703 memo `:15,79`. |

In the final three rows, branch names have prefix `private/cloud/`; S696/S699/S700/S702/S703/S707 use suffix `-2026-10-01`, the others `-2026-09-30`.

**Drop from the landing queue, retain the evidence:**

- `private/cloud/S504-S641-2026-09-30`, `private/cloud/S642-2026-09-30`, `private/parked/S657-h332`: implementation already extracted. S657's landing is recorded at `docs/evidence/HARNESS_GAPS_2026-09-03.md:768`.
- `private/cloud/S640-2026-09-30`: would remove the Windows correction now present at `tests/governance/test_run_governance.py:258-259`.
- `private/parked/S588-h257-base`: no unique candidate commits.
- Original `private/parked/S531-h260` and `private/parked/S534-h261`: use the rebased candidates named by `docs/operations/DESK_STATE.md:88`.
- `private/parked/S643-h331`: superseded draft. Keep `S643-h331-r2` and `private/cloud/S646-2026-09-30` parked; do not reopen them as routine work. `docs/operations/DESK_STATE.md:23,98`

**Hold outside the critical path:** cloud S530, S594, S631, S637, S641-fix, S658, S672, S674, S675, S677, S679, S683, S685-S689, S697, S701, S705 and S709. Reopen only for a measured dependency: interpreter parity, resource contention, disk shortage or changed recorder root. Their existing scopes are in `docs/evidence/HARNESS_GAPS_2026-09-03.md:S530,S594,S631,S637,S641,S658,S672-S709`; S701's limited sub-bar is disclosed in its `2026-10-01` cloud-result memo `:21,30`.

Cloud `verify-*`, `rehearse-*`, `review-landings-*`, `gapreview-*`, `smoke-*` and `sweep-*` branches supply review evidence; they are not additional implementations to merge blindly.

Here, each “Sxxx branch memo” means `docs/evidence/harness/Sxxx_cloud_result_<branch-date>.md` read from the named branch.

## 5. STOP/GO

| Component | Decision | Evidence and proposed operating rule |
|---|---|---|
| Fitted arms | **SIMPLIFY** | Freeze the existing comparison and accrue paired supported receipts. A fitted scoreboard already ran; qualification did not complete. `docs/evidence/forward/nights/2026-09-30.json:steps[name=scoreboard],steps[name=qualification]` |
| Arm E | **STOP new modelling** | Every latest E prediction is null with `training_history_absent`; summary games/ticks are zero. Resume modelling only when its training prerequisites exist. `docs/evidence/forward/registry_e/2026-09-30.json:rows[].E,rows[].e_refusal,summary` |
| registry_e | **SIMPLIFY** | Check prerequisites cheaply and preserve an explicit refusal/eligibility receipt. The latest run consumed 395 s without scored E ticks. `docs/evidence/forward/nights/2026-09-30.json:steps[name=e]`; registry receipt `:summary` |
| fill_realism | **SIMPLIFY** | Keep counts and occasional sensitivity diagnostics; stop treating it as daily execution validation. Latest assumptions use zero submit/cancel latency and the run took 489.015 s. `docs/evidence/forward/fill_realism/2026-09-30.json:mode,assumptions`; night receipt `:steps[name=fill_realism]` |
| Maker-forward schedule writer | **GO** | It defines the prospective denominator. Keep full selection, served subset and explicit amendments; do not select successful games retrospectively. `scripts/platformkit/ops/forward_qualification_daily.py:98-121,158-180` |
| Seal-chain cadence | **SIMPLIFY** | Complete correctness-critical changes in receipt order; pause optional identity churn. A missed window shifts the chain and two identity changes must not share a night. `docs/operations/DESK_STATE.md:49-60` |
| Cloud routines | **SIMPLIFY** | Prioritize carried corrections, landing reviews and dead-man checks; pause indiscriminate new-row generation. The handoff assigns branch-only work to cloud and Windows adoption elsewhere. `docs/operations/DESK_STATE.md:17-23,73-80` |

## 6. SUSPICION LIST

| Belief to falsify | Cheapest exact check | Result if false |
|---|---|---|
| More RAM alone will complete the night. | `docs/evidence/forward/nights/2026-09-30.json:steps[name=qualification].{reason,free_ram_at_start_bytes,peak_working_set_bytes,wall_s}` | Deadline kill despite ample starting RAM. Already observed. |
| Every served game has failed qualification. | Join each `docs/evidence/forward/schedules/*_maker_forward.json` entry to `qualification/<date>.json:games`, counting missing and invalid files separately. | Unobserved entries appear rather than FAIL. Already observed; future/not-due dates must stay separate. |
| A canonical `as_of` proves an on-time night. | Compare `nights/2026-09-30.json:as_of` with `steps[0].started_utc`; inspect `desk_audits/2026-09-29.json:on_time_equivalence`. | Late actual execution or `false`, despite canonical cutoff text. Already observed. |
| Produced E means fitted E. | Count nonnull `docs/evidence/forward/registry_e/2026-09-30.json:rows[].E`; inspect `summary.n_games`. | Both are zero. Already observed. |
| The E artifact is corrupt. | Parse that entire JSON, then parse only its first `2*1024*1024+1` characters; compare with `scripts/platformkit/ops/paper_desk_issue_common.py:98`. | Full parse succeeds and truncated parse fails. Already reproduced. |
| Arm A is fresh throughout the scoreboard. | Count `docs/evidence/forward/scoreboard/2026-09-30.json:ticks[].mid_age_us > 15000000`. | A material stale subset: 2,984 of 4,842 ticks. Already observed. |
| Qualification is only an inexpensive counts pass. | Read `scripts/platformkit/execution/forward_replay_policy.py:87-102` and `position_ledger.py:217-220`; inspect the size of `vault/S362/position_events.jsonl`. | Persistent ledger reads/appends and repeated full-history validation exist. Code confirms the mechanism; whether it caused this deadline is UNKNOWN. |
| A verified branch label means ready to land. | `git show private/cloud/verify-S691-2026-10-01:docs/evidence/harness/S691_cloud_verify_2026-10-01.md` | A blocking correction remains uncommitted. Already observed at lines 38 and 51-76. |

## 7. HOW TO GET BETTER

| Improvement | Metric and control | Data already on disk | Minimum sample |
|---|---|---|---|
| **1. Measure conversion from scheduled games to usable receipts.** | Scheduled -> served -> captured -> qualified -> scored counts; coverage, fatal gaps and actual completion time. Retain every failed/unserved denominator. | `docs/evidence/forward/schedules/*_maker_forward.json`; `qualification/{2026-09-22,2026-09-29}.json:games`; `nights/*.json:steps`; `issues/2026-10-02.md:34-36` | Seven consecutive nonempty nights for operational acceptance; >=30 independent games before a sampled calibration conclusion. |
| **2. Separate feed delay, recorder delay and book-observation age.** | Per-game p50/p90/max lag, clock offset and fraction of decisions with fresh state/book. Separate live prints from backfill; missing clocks remain UNKNOWN. | `docs/evidence/forward/exec_quality/2026-09-22_2026-09-26.json`; `qualification/2026-09-29.json:games`; input archive paths in `nights/2026-09-30.json:steps[].argv` | Existing S597 gate: >=200 observations; report distinct games/tickers, not 200 independent games. Statistical cross-game conclusions wait for >=30 games. `docs/evidence/tracking/specs/S597_spec.md:11-17`; verifier contract `:45-48` |
| **3. Evaluate cancellation quality on a common opportunity set.** | Paired +60 s markout, fill share, quote uptime, pending-cancel fills and missing-mark share; retain through-only and displayed-depletion scenarios. Use the sealed latency assumptions and label sensitivity runs separately. | `docs/evidence/forward/exec_policy/PREREG_S551.json:{params,queue_scenarios,primary_horizon_s,stopping_rule}`; `docs/evidence/forward/exec_quality/*.json` | **30 paired games in every nonbaseline cell**, with the existing single-look rule. The current exec_policy directory has no dated scored receipt; accrual is UNKNOWN. `PREREG_S551.json:floor_paired_games,stopping_rule` |
| **4. Make calibration comparisons paired, fresh/stale and terminal-aware.** | Per-game Brier/log-loss differences on identical eligible ticks; preserve archived paired losses. Report model refusals, stale receipt share and terminal-tick exclusions beside every comparison. | `docs/evidence/forward/scoreboard/2026-09-30.json:{ticks,paired_losses,counts}`; `docs/evidence/harness/INGAME_MODEL_2_PLAN_2026-09-29.md:216-229,254-266` | >=30 independent games per declared cell. Keep smaller cells INSUFFICIENT; seek independent-corpus confirmation before a general calibration conclusion. `docs/evidence/tracking/VERIFIER_CONTRACT.md:34-48,64-69` |
| **5. Calibrate the fill model's uncertainty before adding complexity.** | Fill-share sensitivity to order latency, queue assumptions, TTL and horizon censoring; include unknown-queue and unobserved-horizon denominators. Without independent queue/fill labels, report bounds rather than calibrated fill probabilities. | `docs/evidence/forward/fill_realism/2026-09-30.json:{assumptions,quote_life,inputs}`; `docs/evidence/harness/ASTRA_GAP_SWEEP_2026-09-24.md:33-45`; execution architecture `:134` | >=30 tape-complete games per declared comparison for scored summaries. Independent fill labels are an additional requirement; their availability was not checked and is UNKNOWN. |