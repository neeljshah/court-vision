# S676 cloud result (2026-09-30): service levels, desk-health digest, dead-man check

Row S676 (QUANT-GRADE slate section 2; one-off override section 3a). Branch
`cloud/S676-2026-09-30`, based on trunk e1b3bcdc. PAPER ONLY; operational service levels, no
model or market claim. PORTABLE: yes (code and construct tests); the tick hook is WINDOWS and the
targets are OWNER.

Process: cloud desk-improve routine, one-off override. codex is not available in the cloud box, so
every independent role was an independent Opus sub-agent (spawned with the Agent tool, fresh
context, told it did not build the row): the pre-build critic, the CONTRACT tier and the
ADVERSARIAL tier. None of them edited a tracked file.

## Verdicts

| Stage | Who | Commit | Verdict |
|---|---|---|---|
| Pre-build critique | independent Opus sub-agent (astra role) | spec draft | REVISE, 10 items, all folded as AMENDMENT 1 |
| CONTRACT tier, round 0 | independent Opus sub-agent | 7d8935b8 | ACCEPT WITH CORRECTIONS (A7: this memo absent; NEW GAPs: config not named in artifact, hardcoded 06:05, shallow-clone false late, loose _health) |
| ADVERSARIAL tier, round 0 | independent Opus sub-agent | 7d8935b8 | ACCEPT WITH CORRECTIONS (38 mutants, 27 killed, 11 survived; 1e400 duration hid gaps; local-date default day) |
| Fix round 1 | builder | 95da033b | all round-0 corrections folded; 6 tests added (17 total), no acceptance literal changed |
| CONTRACT tier, re-verify | same sub-agent | 95da033b | ACCEPT WITH CORRECTIONS (only open item: this memo; all four NEW GAPs closed) |
| ADVERSARIAL tier, re-verify | same sub-agent | 95da033b | ACCEPT WITH CORRECTIONS (all 11 targeted survivors killed except one agreed equivalent mutant; see carried corrections) |

Final: ACCEPT WITH CORRECTIONS on both tiers. This is the single allowed re-verification; no
further code change was made after it.

Corrections CARRIED to the landing session (verified behaviour by hand probe, but no test literal
fails when the fix is reverted; add these literals before or at landing):
- C1 shallow-clone guard in deadman_check.committed_at (probe: depth-1 and depth-2 clones give
  "unknown", full clone gives the real 06:00 add; conservative per A1.8).
- C2 slo_status default --end via utc_yesterday (probe: +02:00 offset resolves to the UTC day).
- C3 ticks_seen upper bound (a later-day tick in D's file).
- C4 strict _health (schema, int slots_due) in slo_status; int slots_due in the deadman schema.
- C5 tick_gap slot LIST drawn from `covered` (the alert itself is tested; the list source is not).
- C6 duration cap `>` vs `>=` at exactly 86400 (boundary only).
NEW GAPs (not rejections; for the register via a laptop session):
- NG1 a duration_s of exactly 86400 is still accepted, so one such row hides the rest of the day;
  a tighter cap (timeouts_s.night plus a margin) would close it.
- NG2 slo_status raises (refused by main, exit 2) if night_not_before_utc is ever written "HH:MM:SS";
  today it is "06:05".
- NG3 duplicate ts across two ticks merges them into one tick; the scheduler does not overlap ticks,
  so this is plausible, not verified on a real journal.

## What was built (new files only; `git diff --stat e1b3bcdc` shows no changed existing file)

| File | Lines | Role |
|---|---|---|
| docs/operations/SLOS.md | 49 | three SLIs with named denominators; targets OWNER_TBD; alert path |
| scripts/platformkit/ops/desk_health.py | 168 | report-only writer of docs/evidence/forward/desk_health/<D>.json from the tick journal |
| scripts/platformkit/ops/slo_status.py | 137 | window attainment (28 days default) + night_yield_miss observations (P1, FAIL) |
| scripts/platformkit/ops/deadman_check.py | 140 | morning dead-man: heartbeat_missing / _invalid / _late, tick_gap; exit 1 + issue title/body |
| tests/platformkit/ops/test_slo_status_s676.py | 269 | construct test (17 tests) (fails on trunk: the modules do not exist) |
| docs/evidence/harness/S676_spec_2026-09-30.md | 66 | spec + AMENDMENT 1 (critic REVISE, 10 items folded) |
| docs/evidence/harness/S676_slo_status_clone_2026-09-30.md | 175 | reproduction artifact (JSON stored as .md: .gitignore:588 tracks only *.md here) |

## Acceptance (spec ACCEPTANCE RULE + AMENDMENT 1)

1. SLI1 equals the hand count. Fixture window 2026-09-20..2026-10-03 (14 days), now
   2026-10-04T12:00:00Z: 4/10 canonical; misses 09-24 (legacy-listed), 09-26 (status FAILED), 09-27
   (wrong date field), 09-28 (absent), 09-29 (rerun name only), 10-02 (as_of one second late);
   09-20..09-23 not_due (before DESK_EPOCH). Literals in the test, not recomputed.
2. night_yield_miss: one observation (FAIL, P1) per miss, exactly that set.
3. Dead-man dry run on a synthetic 48-slot journal (a real `--dry-run` tick never journals tick_ok):
   deleting the 10:02 tick alerts `tick_gap` naming slot 10:00; the intact control (including a
   7000 s night tick that suppresses three scheduler starts) does not alert.

Clone reproduction (A1.5): `python3 -m scripts.platformkit.ops.slo_status --end 2026-09-29 --days 14
--now 2026-09-30T12:00:00Z` -> SLI1 = 1/6 (canonical: 2026-09-26 only; 09-24 and 09-25 fail
night_noncanonical_as_of and are legacy-listed S602; 09-27, 09-28, 09-29 have no record in git);
09-16..09-23 not_due; SLI2 = SLI3 = 0/288 because no desk_health record exists yet (all six days
unobserved). `python3 -m scripts.platformkit.ops.deadman_check --now 2026-09-30T12:00:00Z` -> exit 1,
heartbeat_missing for 2026-09-29 (expected until the hook is wired).

## Test commands and counts (one file per process)

| Command | Commit | Result |
|---|---|---|
| `python3 -m pytest tests/platformkit/ops/test_slo_status_s676.py -q` | 7d8935b8 | 11 passed (builder; CONTRACT tier reran: 11 passed) |
| `python3 -m pytest tests/platformkit/ops/test_slo_status_s676.py -q` | 95da033b | 17 passed (builder; both tiers reran: 17 passed; adversarial with `python -B`, caches cleared) |
| `python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q` | 95da033b | 1 passed (A12; no allowlisted file grew) |
| `python3 -m scripts.platformkit.ops.slo_status --end 2026-09-29 --days 14 --now 2026-09-30T12:00:00Z` | 95da033b | SLI1 1/6; JSON equal to the artifact block |
| `python3 -m scripts.platformkit.ops.deadman_check --now 2026-09-30T12:00:00Z` | 7d8935b8 | exit 1, heartbeat_missing 2026-09-29 |

The trunk test fails by construction (ImportError: the three modules do not exist on e1b3bcdc).

## PROPOSED diffs (not applied; tick modules and the parked S657 branch belong to a laptop run)

P1. Tick hook, `scripts/platformkit/ops/paper_desk_tick.py` (WINDOWS; tick owner). Write the digest at
the first tick after 00:00Z on D+1, independent of the night (AMENDMENT 1 A1.7):

```
     def work(self) -> None:
         """Keep capture, scheduling, night and census failures independent."""
         for name in ("books", "state2", "polymarket"):
             self.step("capture:" + name, lambda r, n=name: self.capture(n, r))
         for key in ("books_root", "state_root"):
             self.step("heartbeat:" + key, lambda r, k=key: self.watchdog(k, r))
+        self.step("desk_health", self.desk_health)
         self.step("schedule", self.schedule, memory=True)
+
+    def desk_health(self, row: dict) -> None:
+        """S676: report-only digest of yesterday's journal; written once, never rewritten."""
+        day = (self.clock.date() - timedelta(days=1)).isoformat()
+        path = self.root / "docs/evidence/forward/desk_health" / (day + ".json")
+        if path.exists():
+            row.update(decision="desk_health_exists", reason="exists")
+        elif self.dry:
+            row.update(decision="would_run", reason="due")
+        else:
+            from scripts.platformkit.ops.desk_health import write
+            write(self.root, day, self.now)
+            row.update(decision="desk_health_written", reason="complete", produced_paths=[str(path)])
```
plus, in `paper_desk_attention.py` ATTENTION_TABLE:
`"desk_health": {"success": frozenset({"desk_health_written", "desk_health_exists"}), "benign": _BENIGN},`
(otherwise the new step falls into the "tick" family and reads as attention).

P2. S657 push list, `scripts/platformkit/ops/evidence_push.py` on parked/S657-h332, `push_set`:
include `docs/evidence/forward/desk_health/<D>.json` when present, EVEN when no night record exists,
so a missing night does not also suppress the heartbeat:
```
-    if not records:
-        return [], []
+    health = FORWARD + "desk_health/" + day + ".json"
+    extra = [checked(root, health)] if (root / health).is_file() else []
+    if not records:
+        return extra, []
     paths = [checked(root, FORWARD + "nights/" + name) for _, name in records]
+    paths += extra
```
and the tick calls `evidence_push --date D` right after the desk_health step (in addition to the
post-night call), so the heartbeat reaches trunk well before 07:00Z.

P3. desk-morning routine, `docs/operations/cloud/desk-morning.prompt.txt`, new step before WRITE:
```
DEAD-MAN (S676): run `python3 -m scripts.platformkit.ops.deadman_check` (after 07:00Z). On exit 1,
open ONE GitHub issue with the printed issue.title and issue.body (skip if an open issue with the
same title exists) and list it first under P0/P1 in the daily report. Exit 2 = not due; say so.
Also run `python3 -m scripts.platformkit.ops.slo_status --days 28` and quote the three fractions
with their denominators (targets OWNER_TBD).
```

P4. Issue ledger wiring, `scripts/platformkit/ops/paper_desk_issues.py` scan list: add a
`('night_yield', ...)` check that calls `slo_status.status(root, yesterday, 14, now)` and emits
`night_yield_miss` FAIL (P1) per miss and PASS per canonical due day, so the ledger can close it.

## NOT VERIFIED (needs the laptop / recorder, data/ or live systems)

- The 14-day hand count against the laptop's docs/evidence/forward/nights/ (the clone holds 3 records;
  09-27..09-29 are absent in git, so the clone's 1/6 is a lower view, not the desk's number).
- desk_health on a REAL tick journal (data/cache/paper_desk/journal/ is local-only); the assumption that
  a tick's end = start + sum of top-level duration_s, and slot jitter on the real scheduler.
- The tick hook (P1), the S657 push-list change (P2) and a heartbeat actually reaching trunk by 07:00Z.
- The owner e-mail path: GitHub issue creation from the morning routine and GitHub e-mail delivery.
- heartbeat_late on real commits (the committer date comes from the laptop clock).
- Ledger wiring of night_yield_miss (P4) and its closure behaviour.
- The three targets (OWNER_TBD; DESK_STATE section 6 item 9).

No register or DESK_STATE edit on this branch (override rule). Landing, the register row and the
RESULTS_LEDGER line belong to a laptop session.
