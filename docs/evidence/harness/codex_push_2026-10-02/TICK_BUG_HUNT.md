Both defects are confirmed. A has two cause-blind backoff gates; B parses an empty qualification artifact left by a killed producer. B's attention is stale but does already expire.

I read `status.json`, the last 400 lines of `task.log`, the relevant receipts, and the code. No files were changed, no tests ran, and no network was used.

**A: capture retry**

The journal confirms all three `13:25:35Z` capture attempts recorded `ongoing_low_ram`. The `13:34:01Z` status records backoff despite approximately 6 GB available. The three heartbeat files have modification times at `13:29:47Z`; a local process snapshot found no capture supervisors.

The exact path is:

- `scripts/platformkit/ops/paper_desk_tick.py:211-212` dispatches captures without `memory=True`, bypassing the admission check at `:68-70`.
- `paper_desk_tick.py:145-159` inspects ownership, reads the request and matching launcher receipt, and reconciles pending ownership.
- `scripts/platformkit/ops/paper_desk_start.py:90-126` refuses STOP, inaccessible identities, pending launchers, or orphan writers; only a complete absent inventory permits launch.
- `scripts/platformkit/ops/paper_desk_reconcile.py:17-42` confirms present supervisors, preserves live launcher ownership, marks proven absence `launch_failed_reconciled`, or escalates unresolved ownership after three observations.
- `paper_desk_tick.py:169-175` blocks pending/future requests, then applies the 60-minute delay without examining cause.
- `paper_desk_tick.py:177-184` reserves the request and invokes `paper_desk_start`.
- `paper_desk_start.py:153-173` repeats ownership reconciliation and independently applies another cause-blind 60-minute delay.
- `paper_desk_start.py:175-183` reserves launch ownership before WMI creation.
- `paper_desk_tick.py:128-131` invokes `run_producer(..., detached=True)`.
- `scripts/platformkit/ops/paper_desk_process.py:197-213` counts `ongoing_low_ram`, sets `producer_stopped`, then replaces its reason with `detached_launch_pending_reconciliation`. It does **not** terminate the detached launcher.
- `paper_desk_tick.py:185-199` persists launcher results only after exit zero; this attempt's low-RAM cause remains in the journal, absent from its request marker.
- `scripts/platformkit/ops/capture_supervisor.py:197-222` separately backs off child exits/start failures. Its `--min-free-mb` gate checks **disk space**, not RAM (`:205-213`).

The low-RAM observation does not establish why the supervisors later disappeared: their heartbeat payloads show children actually started around `13:27:41Z`.

Root cause, in two sentences: The tick loses the attempt's refusal cause from its durable request state, then both the tick and launcher impose a time-only 60-minute backoff. Capture also lacks a pre-launch RAM gate, so transient resume pressure can create this state again tonight.

The smallest proposal below preserves cause, adds admission before a new attempt, and passes a timestamp-bound retry exception through the second gate. Unknown failures and crash attempts retain 60 minutes; observing a live supervisor clears the transient exception.

```diff
--- a/scripts/platformkit/ops/paper_desk_tick.py
+++ b/scripts/platformkit/ops/paper_desk_tick.py
@@ -16,1 +16,1 @@
-from scripts.platformkit.ops.paper_desk_start import inspect_capture
+from scripts.platformkit.ops.paper_desk_start import inspect_capture, retryable_capture
@@ -154,2 +154,3 @@
                 if launched.get("attempted_at") == old["ts"]:
                     old["launcher_identity"] = launched.get("launcher_identity")
+                    old["retry_cause"] = launched.get("retry_cause", old.get("retry_cause"))
@@ -164,2 +165,3 @@
             if result["decision"] == "present" and request.exists() and not self.dry:
-                atomic(request, dict(old, status="confirmed", identities=result["identities"]))
+                atomic(request, dict(old, status="confirmed", retry_cause=None,
+                                     identities=result["identities"]))
@@ -168,1 +170,6 @@
             return
+        if count(self.ram()) < max(admission_mib(self.config, "capture"),
+                                  reserve_mib(self.config, "capture")) * 1024**2:
+            row.update(decision="deferred_low_ram", reason="available_ram_below_minimum")
+            return
+        retry_at = old.get("ts") if retryable_capture(old) else None
@@ -173,1 +180,1 @@
-            if self.epoch - instant(old["ts"]) < 3600:
+            if not retry_at and self.epoch - instant(old["ts"]) < 3600:
@@ -182,3 +189,11 @@
-        self.execute(row, "scripts.platformkit.ops.paper_desk_start",
-                     ["--config", str(self.config_path), "--name", name,
-                      "--state", str(launch), "--now", self.now], [], "capture")
+        try:
+            self.execute(row, "scripts.platformkit.ops.paper_desk_start",
+                         ["--config", str(self.config_path), "--name", name,
+                          "--state", str(launch), "--now", self.now] +
+                         (["--retry-at", retry_at] if retry_at else []), [], "capture")
+        finally:
+            if not self.dry:
+                cause = ("ongoing_low_ram" if row["refusals"].get("ongoing_low_ram") else
+                         "launch_refused" if row["refusals"].get("spawn_failed_before_create") else None)
+                if cause:
+                    atomic(request, dict(read(request), retry_cause=cause))
--- a/scripts/platformkit/ops/paper_desk_start.py
+++ b/scripts/platformkit/ops/paper_desk_start.py
@@ -52,1 +52,6 @@
+def retryable_capture(state: dict) -> bool:
+    """Retry known admission or creation refusals after ownership reconciliation."""
+    return state.get("retry_cause") in {"ongoing_low_ram", "launch_refused"}
+
+
 def process_snapshot() -> list[dict]:
@@ -145,2 +150,3 @@
 def start_capture(name: str, cfg: dict, state_path: Path, now: str, *,
-                  process_rows: list[dict] | None = None, create=None) -> dict:
+                  process_rows: list[dict] | None = None, create=None,
+                  retry_at: str | None = None) -> dict:
@@ -154,2 +160,3 @@
         atomic(state_path, dict(state, attempted_at=state.get("attempted_at", now),
-                               status="confirmed", identities=result["identities"]))
+                               status="confirmed", retry_cause=None,
+                               identities=result["identities"]))
@@ -172,1 +179,2 @@
-        if epoch - attempted < 3600:
+        if epoch - attempted < 3600 and not (
+                retryable_capture(state) or retry_at == state["attempted_at"]):
@@ -181,1 +189,6 @@
-    identity = (create or wmi_create)(entry["argv"], entry["cwd"])
+    try:
+        identity = (create or wmi_create)(entry["argv"], entry["cwd"])
+    except subprocess.CalledProcessError:
+        marker["retry_cause"] = "launch_refused"
+        atomic(state_path, marker)
+        raise
@@ -195,3 +208,5 @@
+    parser.add_argument("--retry-at")
     args = parser.parse_args(argv)
-    result = start_capture(args.name, read(args.config), args.state, args.now)
+    result = start_capture(args.name, read(args.config), args.state, args.now,
+                           retry_at=args.retry_at)
     print(json.dumps(result, sort_keys=True))
```

Ownership checks still precede the exception. WMI timeouts remain ambiguous and retain conservative handling; only explicit creation failure receives `launch_refused`. Existing cause-free markers retain the old delay rather than guessing their history.

**B: the actual bad JSON file**

The failing file is:

`docs/evidence/forward/qualification/2026-09-30.json`

It is zero bytes, and its SHA256 exactly matches the empty-file seal in the night receipt:

`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

The qualification receipt records:

```text
step_status: KILLED
reason: step_deadline_exceeded
wall_s: 900.297
exit_code: 15
processes_killed: 1
kill_survivors: 0
artifact_resolution: unknown_child_killed
```

Candidate checks:

- All seven present artifacts matched their recorded hashes; qualification alone was empty.
- The other six parsed as JSON.
- All 23 inspected JSON files under `data/cache/paper_desk/` parsed successfully.
- `docs/evidence/forward/night_deferrals/` was absent.
- `RUNNER.lock` is intentionally empty: `scripts/platformkit/execution/paper_night_lock.py:11-16` creates an OS-held lock using `"a+b"`. It is not parsed as JSON.
- Empty `tick.lock` and `journal.lock` are likewise intentional (`paper_desk_steps.py:116-128`).

The exact failure path is:

- `scripts/platformkit/ops/forward_qualification_daily.py:58-66` exclusively creates an empty **final JSON pathname**. `:197` reserves it before computation.
- `scripts/platformkit/execution/paper_night.py:148-150` monitors the child. The deadline path records the kill; publication at `forward_qualification_daily.py:275-279` never completes.
- `forward_qualification_daily.py:40-55` already stages, flushes, fsyncs, and atomically replaces completed JSON. The empty file is therefore an **abandoned reservation**, not proof of a torn JSON write.
- `paper_night.py:172-178` records unknown artifact resolution, then seals the empty file as present.
- `scripts/platformkit/ops/paper_desk_actions.py:217-220` handles exit 3 and reads the night receipt with artifact validation.
- `scripts/platformkit/ops/paper_desk_evidence.py:99-105` verifies the empty artifact's matching digest, then parses it through `document()`.
- `paper_desk_evidence.py:14-20` raises `JSONDecodeError` without attaching the pathname.
- `paper_desk_actions.py:135-137` rethrows it; `paper_desk_tick.py:73-76` records generic `refused` / `step_exception`.
- Later ticks use `artifacts=False` for existing receipts and emit `night_skipped` (`paper_desk_actions.py:159-163`).
- `scripts/platformkit/ops/paper_desk_attention.py:225-229` clears attention only on a newer successful result for that subject. A benign skip cannot clear it.

The "forever" premise needs correction. `paper_desk_attention.py:188-196,232-249` already expires dated attention, and `docs/operations/paper_desk_config.json:9` sets three backfill days: this September 30 night expires on the first journal update at or after **2026-10-04T00:00:00Z**, retaining bounded expiry evidence.

Root cause, in two sentences: Qualification reserves its final JSON filename with an empty file, and a deadline kill leaves that reservation to be sealed and subsequently parsed as evidence. The reader loses the pathname in a generic exception, while later envelope-only checks cannot clear it; another qualification kill before publication can reproduce this tonight.

The smallest fix separates reservation from publication, reuses `atomic_replace.py`, and counts a named JSON refusal. Keep the existing expiry rule; do not clear artifact failures merely because their receipt envelope parses.

```diff
--- a/scripts/platformkit/ops/forward_qualification_daily.py
+++ b/scripts/platformkit/ops/forward_qualification_daily.py
@@ -30,1 +30,2 @@
 from scripts.platformkit.execution.forward_replay_qualification import REASONS, WINDOW_S
+from scripts.platformkit.ops.atomic_replace import replace_with_retry
@@ -51,1 +52,1 @@
-        os.replace(temporary, path)
+        replace_with_retry(temporary, path)
@@ -59,1 +60,1 @@
-    """Claim an unused path exclusively; an existing date artifact is kept."""
+    """Reserve a revision with a permanent sidecar; publish JSON atomically."""
@@ -64,2 +65,2 @@
-            with target.open("x", encoding="ascii"):
-                pass
+            if target.exists(): raise FileExistsError(target)
+            with target.with_name(target.name + ".claim").open("x", encoding="ascii"): pass
@@ -275,5 +276,1 @@
-    try:  # AMENDMENT 3 order: the artifact EXISTS before any snapshot is deleted
-        _atomic(target, payload)
-    except Exception:  # never leave the reserved path as a zero-byte date claim
-        target.unlink(missing_ok=True)
-        raise
+    _atomic(target, payload)  # Publish before deleting any snapshot.
--- a/scripts/platformkit/ops/paper_desk_evidence.py
+++ b/scripts/platformkit/ops/paper_desk_evidence.py
@@ -14,1 +14,5 @@
+class EvidenceJSONError(ValueError):
+    """A named evidence file could not be decoded as JSON."""
+
+
 def document(path: Path) -> object:
@@ -20,1 +24,4 @@
-    return json.loads(path.read_bytes(), object_pairs_hook=_pairs, parse_constant=refuse, parse_float=Decimal)
+    try:
+        return json.loads(path.read_bytes(), object_pairs_hook=_pairs, parse_constant=refuse, parse_float=Decimal)
+    except json.JSONDecodeError as exc:
+        raise EvidenceJSONError("invalid_json:" + path.as_posix() + ":" + str(exc)) from exc
--- a/scripts/platformkit/ops/paper_desk_actions.py
+++ b/scripts/platformkit/ops/paper_desk_actions.py
@@ -12,1 +12,1 @@
-    FORWARD, census_state, day_after, receipt, schedule_paths, schedule_state)
+    FORWARD, EvidenceJSONError, census_state, day_after, receipt, schedule_paths, schedule_state)
@@ -135,1 +135,5 @@
+        except EvidenceJSONError as exc:
+            row.update(decision="refused", reason=str(exc))
+            row["refusals"]["night_evidence_invalid_json"] = 1
+            return None
         except ValueError as exc:
```

Permanent `.claim` files preserve exclusive revision allocation after interruption; they are never evidence JSON. Adoption must avoid overlapping old and updated qualification producers because their reservation protocols differ.

These proposed changes keep every touched file below 300 lines. They do not repair or rewrite the historical sealed artifact. Also, that night's scoreboard is 9,942,028 bytes, exceeding `document()`'s 8 MiB bound; repairing only qualification would expose that separate validation failure.

**Tests to add, not run**

| Test name | Required assertions |
|---|---|
| `test_capture_low_ram_retries_through_both_gates` | Persist low-RAM cause; reconcile all owners absent; recover RAM; eight minutes later both tick and launcher permit exactly one creation. |
| `test_capture_crash_keeps_hour_backoff` | Identical timing and ownership, but crash/unknown cause: zero launches before 60 minutes, eligible at 60 minutes. This catches an inverted retry rule. |
| `test_capture_refusal_retries_after_reconciliation` | Explicit WMI refusal or pre-create spawn failure retries next tick; live/uncertain ownership still prevents creation. |
| `test_capture_low_ram_does_not_reserve_attempt` | Below admission: no launch and no new attempt timestamp. |
| `test_capture_retry_timestamp_cannot_bypass_newer_attempt` | Retry permission for attempt T cannot bypass a newer launch receipt. |
| `test_capture_present_clears_transient_retry_cause` | Observe supervisor present, then absent: prior transient cause no longer bypasses crash backoff. |
| `test_empty_sealed_artifact_names_file` | Empty artifact with matching seal produces one `night_evidence_invalid_json`, its pathname, and no generic `step_exception`. |
| `test_valid_sealed_artifact_is_accepted` | Equivalent valid JSON is accepted without the refusal; catches inverted validation. |
| `test_reservation_does_not_publish_empty_json` | Reservation creates only `.claim`; interrupted work leaves final JSON absent. |
| `test_reservations_preserve_existing_revisions` | Concurrent reservations choose distinct paths; existing JSON stays byte-identical. |
| `test_atomic_publication_uses_shared_retry` | Transient `PermissionError` retries; exhausted/pre-replace failure preserves previous complete bytes or absence. |
| `test_night_attention_expiry_boundary` | September 30 attention survives October 3, expires October 4, and gains expiry evidence; envelope-only `night_skipped` does not clear it early. |

**Windows adoption**

1. Apply the reviewed proposal between ticks, with no qualification producer running. Run the focused tests individually on the recorder.
2. Leave historical receipts, lock files, STOP files, and feature flags intact. Existing cause-free capture markers remain conservative until their hour expires; do not erase ownership records to bypass them.
3. Let the next `CourtVisionPaperDesk` invocation load the code, or trigger the existing task once RAM passes admission.
4. Check the new journal for reconciled capture starts, advancing heartbeats, named evidence refusals, and the dated attention expiry.

Neither patch requires a capture restart or task reinstall. The installed task starts a fresh tick process (`docs/operations/install_paper_desk_task.ps1:60-62`); these changes affect that process and subsequently launched producers. Absent captures need a normal start through the tick.

**Other occurrences**

- **Cause-blind night backoff:** `paper_desk_actions.py:58-78` records missing-receipt failures, including transient producer contention and launch failure; `:39-55` validates but ignores the saved outcome and imposes three hours. Contention originates at `paper_desk_process.py:40-55,153-154`; launch exceptions are recorded at `paper_desk_actions.py:207-209`. Runtime low RAM does not kill nights: `paper_desk_process.py:149,197` explicitly exempts them.
- **Stale missing-schedule delay:** `paper_desk_actions.py:166-180` checks today's skip marker before checking whether the schedule has since arrived, delaying recovery until another UTC date.
- **Stale dated attention:** schedule, census, `nights`, and `census_scan` share success-only clearing. They expire rather than persist forever: night/schedule after the configured three-day window, census after six days.
- **Potentially indefinite attention:** capture, heartbeat, lock, and tick have no expiry (`paper_desk_attention.py:188-190`). Their entries clear on qualifying later success, but can remain indefinitely when subsequent outcomes are only benign/deferred. This is a reachable shared behavior, not evidence that every slot currently suffers it.
- No additional explicit attempt-time backoff was found for schedule, census, or heartbeat.

NOT VERIFIED.