## 1. S594

**READY AFTER vocabulary-only preflight correction and matching review. Landing keeps both cadence options OFF; operational adoption remains separate.** [C594:docs/evidence/harness/S594_spec_2026-09-30.md; scripts/platformkit/tracking/contract_preflight.py:69; lane `/root/s594`]

### Identity

```text
candidate: private/cloud/S594-2026-09-30
tip:       b02aefd1e84d27326909d5821d736c90c8455009
base:      a60dcb09a3185a20868883d41380e2a563d8b137

master..candidate, oldest first:
3b6442771 S594 candidate: opt-in slow-sport poll lane + due-time wake + tick split
b02aefd1e S594 ACCEPT WITH CORRECTIONS: verifier corrections + result memo
```

The diff contains nine files, **1,047 insertions and 48 deletions**. The reverse, path-limited `candidate...master` diff is empty. [Lane `/root/s594`; C594 commit objects]

```text
docs/evidence/harness/S594_cloud_result_2026-09-30.md
docs/evidence/harness/S594_spec_2026-09-30.md
scripts/platformkit/ingame/local_state_capture.py
scripts/platformkit/ingame/local_state_capture_commit.py
scripts/platformkit/ingame/local_state_capture_lanes.py
scripts/platformkit/ingame/local_state_capture_merge.py
tests/platformkit/ingame/s594_lane_fixture.py
tests/platformkit/ingame/test_state_capture_lanes.py
tests/platformkit/ingame/test_state_capture_lanes_units.py
```

### Verdict history and remaining issues

- Pre-build critic: REVISE; fourteen items folded into AMENDMENT 1.
- Contract and adversarial tiers: ACCEPT WITH CORRECTIONS; corrections committed, followed by builder mutation checks.
- Latest independent review: **LAND**, quoting: "No additional defect found. The constructs check actual cadence, archive rows and retry behavior."
- Windows integration: two files, **25 passed**, no failures, errors or skips. These are historical results, not verification of the future rebased tree. [C594:docs/evidence/harness/S594_cloud_result_2026-09-30.md; O/px_r1_review.md:49; O/integ_windows_tests.md]

The memo preserves these findings; my tip inspection agrees they remain open:

| Quoted finding | Current assessment |
|---|---|
| "There is no heartbeat signal for a hung lane worker" | Not fixed; no worker-age/timeout observable. |
| "The old-blob cases skip in a clone that lacks a60dcb09a" | Not fixed; fixture still permits skipping. The required blob exists locally. |
| "The `_prepare_tick` raise after a harvest loses one poll" | Not fixed; disclosed follow-up. |
| "The production factory has no end-to-end test through `_main`" | Not fixed; factory and CLI are tested separately. |

These are disclosed follow-ups, not surviving rejection findings. [C594:docs/evidence/harness/S594_cloud_result_2026-09-30.md:132; C594:scripts/platformkit/ingame/local_state_capture_lanes.py; C594:tests/platformkit/ingame/s594_lane_fixture.py]

**New mechanical blocker:** whole-file vocabulary scanning covers identifiers and disclaimers. Make only these corrections:

1. Rename the loop variable at `local_state_capture_lanes.py:32-34` to `upper_bound`, including its two uses.
2. Replace result-memo line 113 with `Calibration and execution-quality language only.`

This leaves every cadence value, threshold and behavior unchanged. The expected scanner failure is established statically; preflight was not executed. [C594:scripts/platformkit/ingame/local_state_capture_lanes.py:32; C594:docs/evidence/harness/S594_cloud_result_2026-09-30.md:113; scripts/platformkit/tracking/contract_preflight.py:69]

### Landing, live effect and adoption

Use the common landing procedure below, replaying `3b6442771`, then `b02aefd1e`, then the reviewed vocabulary correction. Its test manifest is in section 6. No `.gitattributes` or shared-metadata conflict is present in the candidate. [C594 diff; lane `/root/s594`]

An already-running child keeps its imported code. A subsequently started state2 child loads the additive `task_split`/`tick_split` diagnostics. The current scheduled launcher supplies neither cadence option; landing alone does not activate them. [C594:scripts/platformkit/ingame/local_state_capture.py; C594:scripts/platformkit/ingame/local_state_capture_commit.py; docs/operations/paper_desk_config.json:65; scripts/platformkit/ops/paper_desk_start.py:65]

For an owner/session-authorized restart, the existing guarded command can load the landed code **with both options still OFF**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File docs/operations/relaunch_state2_s502_2026-10-01.ps1 -S502Sha 69222512dcda51fd65edf0df8ba40c5f0b8fa47c
```

Preconditions: 06:00Z-16:00Z, between games, no served game within sixty minutes, at least 2,000 MB free RAM, both landed SHAs present in HEAD ancestry, and known state2 ownership. The script supplies its documented STOP-driven shutdown; current eligibility is UNKNOWN. [C594:docs/evidence/harness/S594_cloud_result_2026-09-30.md, ADOPTION; docs/operations/relaunch_state2_s502_2026-10-01.ps1; docs/operations/DESK_STATE.md:73]

**Cadence activation has an additional unresolved handoff:** the candidate contains no S594 relaunch script. Durable activation needs a reviewed owner decision and matching additions to both the relaunch argv and `captures.state2.argv`:

```text
--slow-lane-sports tennis --wake-on-due
```

A one-off launcher change alone is insufficient because tick recreation uses the persistent config. This dossier does not authorize either flag change. [C594:docs/evidence/harness/S594_cloud_result_2026-09-30.md, ADOPTION; docs/operations/paper_desk_config.json:65; C594:docs/evidence/harness/S594_spec_2026-09-30.md:C4]

After activation, require a new child identity and exact argv, progressing source rows, increasing tennis `task_split.lane.n`, advancing main/tick splits, and explained error/drop counters. For the first complete post-adoption UTC day, run:

```powershell
python -m scripts.platformkit.ingame.state_source_latency_cli --root data/cache/ingame_state_local_v2 --first <YYYY-MM-DD> --last <YYYY-MM-DD> --out-dir docs/evidence/forward/latency
```

Inspect per-sport poll gaps, request duration, timestamp coverage and exclusions. Receipt-time qualification does not establish provider-event freshness. [C594:local state capture modules; scripts/platformkit/ingame/state_source_latency_cli.py; O/px_x6.md:74]

Rollback: revert the actual S594 landing commit using the common procedure, then relaunch state2 with the S502 command above. If cadence activation later occurred, also revert its separately recorded config/launcher commit before relaunch. Preserve S502 and all existing receipts. Future landing/activation SHAs are UNKNOWN. [C594 option defaults; docs/operations/relaunch_state2_s502_2026-10-01.ps1]

## S594 common test manifest (verbatim)

**S594** - candidate regressions and inspected direct-reader coverage, including the newly landed schedule caller:

```text
tests/platformkit/ingame/test_state_capture_lanes.py
tests/platformkit/ingame/test_state_capture_lanes_units.py
tests/platformkit/ingame/test_local_state_capture.py
tests/platformkit/ingame/test_local_state_capture_differential.py
tests/platformkit/ingame/test_local_state_capture_schedule.py
tests/platformkit/ingame/test_state_capture_commit.py
tests/platformkit/ingame/test_state_capture_sources.py
tests/platformkit/ingame/test_state_route_deadline.py
tests/platformkit/ingame/test_state_route_deadline_real_caller.py
tests/platformkit/ingame/test_state_route_deadline_pacer.py
tests/platformkit/ingame/test_state_rollover_carry.py
tests/platformkit/ingame/test_tennis_start_strip.py
tests/platformkit/ingame/test_state_capture_recovery.py
tests/platformkit/ingame/test_mlb_live_feed_state.py
tests/platformkit/ingame/test_nba_pbp_source.py
tests/platformkit/ingame/test_nba_pbp_source_1c.py
tests/platformkit/ingame/test_state_capture_io.py
tests/platformkit/ingame/test_wnba_registration.py
tests/platformkit/ingame/test_local_state_recovery_growth.py
tests/platformkit/ingame/test_nba_pbp_starters.py
tests/platformkit/ingame/test_nba_pbp_starters_census.py
tests/platformkit/ingame/test_state_capture_fix_1q.py
tests/platformkit/ingame/test_espn_play_clock_realrow.py
tests/platformkit/ingame/test_mlb_lineup_state.py
tests/platformkit/ingame/test_mlb_lineup_state_1d.py
tests/platformkit/ingame/test_mlb_lineup_state_1f.py
tests/platformkit/ingame/test_mlb_lineup_state_1h.py
tests/platformkit/ingame/test_nba_pbp_player_state.py
tests/platformkit/ingame/test_nba_state_enrichment.py
tests/platformkit/ingame/test_nba_state_enrichment_archive.py
tests/platformkit/ingame/test_schedule_instant_e2e.py
tests/platformkit/execution/test_registry_scorer_e_s471.py
tests/platformkit/execution/test_registry_scorer_e_s471_1b.py
tests/platformkit/test_loc_rail_scope.py
```

S594's pinned historical-comparison skip is a STOP, even if pytest exits zero. Record clean-master baselines for any existing failing regression; the old shallow-cloud failures are not proof of a current Windows baseline. [C594:docs/evidence/harness/S594_cloud_result_2026-09-30.md:59; C594:tests/platformkit/ingame/s594_lane_fixture.py; lane `/root/s594`]

## Other S594 dossier lines (verbatim)

These are **future lander commands**, not actions performed by this read-only lane. Execute rows serially in this order: **S666, S679, corrected S631, corrected S594, then S688 after its hold clears**. Capture activation is a separate owner/session handoff. [O/px_r1_review.md:103; O/px_r2_review.md:34; O/px_w7.md:60; docs/operations/DESK_STATE.md:73]
| S594 | `LANDED <sha>; ACCEPT WITH CORRECTIONS; additive diagnostics; main <results>; defaults OFF; ADOPTION PENDING; prospective cadence NOT VERIFIED.` | Section 3: add S594 state2 entry with defaults OFF, owner/config handoff pending and permitted restart window. |
Append a reversal event and update that row's status; do not erase the earlier landing record. S594 additionally requires the state2 relaunch described above. The other four require no relaunch while they remain unwired. Actual future revert SHAs are UNKNOWN. [Candidate caller analyses; docs/evidence/RESULTS_LEDGER_SYSTEM.md; docs/operations/DESK_STATE.md]
S594/S502 operational composition belongs to the capture owner. Future S564/S596/source-provenance work may collide with `local_state_capture.py`; no such conflicting candidate was found in this census. S679's later producer integration belongs to the existing provenance work, not a second linter. [O/px_w1.md:50; O/px_x10.md:107; O/px_w7.md:60; lane `/root/s594`]
| S594 | `private/cloud/S594-2026-09-30` | r1 LAND | READY AFTER vocabulary cleanup and matching review | Diagnostics on next child start; cadence options OFF | 4 | Preflight cleanup; separate durable adoption handoff |
- S594's durable activation, prospective row progression and cadence evidence remain unverified. [C594 result memo; docs/operations/paper_desk_config.json]
