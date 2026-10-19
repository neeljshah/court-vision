# S705 tick hook -- PROPOSED diff (NOT APPLIED; WINDOWS; tick owner applies)

PAPER ONLY. Status: PROPOSED. Nothing in this file has been applied to the tick, the config or
the launcher. The cloud run that built `scripts/platformkit/ops/disk_guard.py` could not test
any of this on the recorder box. Spec: `docs/evidence/harness/S705_spec_2026-09-30.md`
(AMENDMENT 1 items 5, 7, 9, 13, 18).

## Part 1 -- gate the `nights` step on the guard (paper_desk_tick.py)

The guard gates ONLY the nights step. It never gates `capture:*` or `heartbeat:*`: the capture
supervisor keeps its own 2000 MiB floor (capture_supervisor.py:204-212). `defer_night` is True
only on `disk_refuse` (free < 5 GB). A guard exception is journalled as a refusal on its own
step and never blocks the night (contract B3: a missing reading is not a bad reading).

```diff
--- a/scripts/platformkit/ops/paper_desk_tick.py
+++ b/scripts/platformkit/ops/paper_desk_tick.py
@@ imports
+from scripts.platformkit.ops import disk_guard
@@ def work(self) -> None:
         for key in ("books_root", "state_root"):
             self.step("heartbeat:" + key, lambda r, k=key: self.watchdog(k, r))
+        guard: dict = {}
+        def disk(row: dict) -> None:
+            receipt = self.root / disk_guard.DEFAULT_RECEIPT
+            try:
+                prior = json.loads(receipt.read_text(encoding="ascii"))
+            except (OSError, ValueError):
+                prior = None
+            logs = [str(self.root / "logs/desk" / (n + ".launch.log")) for n in self.config["captures"]]
+            roots = [str(local(self.root, self.config[k])) for k in ("books_root", "state_root")]
+            guard.update(disk_guard.run(str(self.root), int(self.epoch), logs, roots, prior=prior))
+            row.update(decision="disk_" + guard["decision"], reason=",".join(guard["reasons"]),
+                       rotation_proposals=len(guard["rotation_proposals"]))
+        self.step("disk_guard", disk)
         self.step("schedule", self.schedule, memory=True)
         def nights(row: dict) -> None:
+            if guard.get("defer_night") is True:
+                row.update(decision="deferred_low_disk", reason="disk_refuse")
+                return
             days = count(self.config["backfill_days"], 31, 1)
```

Open question for the tick owner: `self.step` counts any non-empty `refusals` as a tick refusal.
The disk step records none on `warn`, so a warn keeps `tick_ok`. Whether `deferred_low_disk`
should count as a refusal is the owner's call. The diff above does not count it.

## Part 2 -- relocate the hidden-launch logs (paper_desk_config.json)

All three `--log` values today sit under `data\cache\capture_supervisor\`. The S705 run
override says the rotator never selects a path under `data/` or `docs/evidence/`. So the guard
lists these three logs in `skipped[]` as `protected_path_skipped`: it still reads their sizes
for the growth rate, but it NEVER proposes rotating them. Until this relocation lands, the
rotator is INERT in production. The target `logs\desk\` is gitignored (`.gitignore:180 logs/`),
so a relocated log cannot be staged by an explicit-path `git add` by accident.

```diff
-        "C:\\Users\\neelj\\nba-ai-system\\data\\cache\\capture_supervisor\\books.launch.log",
+        "C:\\Users\\neelj\\nba-ai-system\\logs\\desk\\books.launch.log",
-        "C:\\Users\\neelj\\nba-ai-system\\data\\cache\\capture_supervisor\\state2.launch.log",
+        "C:\\Users\\neelj\\nba-ai-system\\logs\\desk\\state2.launch.log",
-        "C:\\Users\\neelj\\nba-ai-system\\data\\cache\\capture_supervisor\\polymarket.launch.log",
+        "C:\\Users\\neelj\\nba-ai-system\\logs\\desk\\polymarket.launch.log",
```

`mkdir logs\desk` first. The change takes effect only at the next capture relaunch, so it rides
a normal adoption window (06:00Z-16:00Z, no live game; DESK_STATE section 3). Nothing else moves.

## Part 3 -- executing a rotation proposal (owner / tick owner; NOT automated)

`hidden_launch.py:23` holds the log open in `"ab"` mode for the child's whole life. On Windows
a rename of the open file fails; on POSIX the child keeps writing into the renamed `.1`. Every
proposal therefore carries `precondition: writer_stopped`. Apply a proposal only between
launches of that capture, in its own adoption window:

1. Stop the capture through its supervisor stop file (never kill an unidentified process).
2. Apply the proposal's `renames` in the listed order (highest generation first). The
   `would_drop` entry is the oldest generation; removing it is an owner decision.
3. Relaunch the capture; the launcher recreates the live log.

The guard itself never deletes, renames or truncates anything. Changing that needs a new row.

## NOT VERIFIED

- The recorder disk (real free bytes, real log sizes, real archive growth).
- This hook on the Windows tick, including "disk_refuse within one tick" end to end. The cloud
  run shows it for one `evaluate`/`run` call only.
- The relocation, and any proposal execution.
