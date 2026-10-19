# S709 PROPOSED diffs: adopting DESK_ROOT in existing modules (NOT APPLIED)

PAPER ONLY. These diffs are offered, not made. The S709 cloud branch edits none of these files: the tick
modules, the start launcher, the fault matrix, the task installer and docs/operations/paper_desk_config.json
are byte-identical to trunk. A laptop session applies them (or not) after the S709 branch lands, and runs
the Windows tick contract run afterwards. Resolver: scripts/platformkit/ops/desk_root.py (S709).

With DESK_ROOT unset every diff below is a no-op: resolve_config returns a deep copy that serialises to the
same bytes as the committed config (test_default_modes_byte_identical), and roots_agree returns True.

## P1. scripts/platformkit/ops/paper_desk_tick.py main (in-process consumer, tick.py:144 via :260)

```diff
+from scripts.platformkit.ops.desk_root import resolve_config, roots_agree
@@ def main(argv: list[str] | None = None) -> int:
     root = args.root.resolve()
     desk = Desk(root, {}, utc_now(), dry_run=args.dry_run)
     try:
+        if not roots_agree(root):
+            raise ValueError("desk_root_disagrees_with_root")
         desk.config_path = local(root, str(args.config))
-        desk.config = read(desk.config_path)
+        desk.config = resolve_config(read(desk.config_path))
         return desk.tick()
```

The disagreement is journalled as the existing `tick_exception` refusal (fail closed).

## P2. scripts/platformkit/ops/paper_desk_start.py main (subprocess consumer, --config)

```diff
+from scripts.platformkit.ops.desk_root import resolve_config
@@ def main(argv: list[str] | None = None) -> int:
-    result = start_capture(args.name, read(args.config), args.state, args.now)
+    result = start_capture(args.name, resolve_config(read(args.config)), args.state, args.now)
```

P1 and P2 must land together. With P1 alone, the tick's STOP and ownership checks would use rebased paths
while the launcher still used the committed paths, so the two could disagree about a STOP file.

## P3. scripts/platformkit/ops/system_fault_matrix.py LIVE_ROOT (protection guard)

```diff
+from scripts.platformkit.ops.desk_root import desk_root
-LIVE_ROOT = Path(os.environ.get("FAULT_MATRIX_LIVE_ROOT", r"C:\Users\neelj\nba-ai-system"))
+LIVE_ROOT = Path(os.environ.get("FAULT_MATRIX_LIVE_ROOT") or desk_root())
```

Precedence: FAULT_MATRIX_LIVE_ROOT, then DESK_ROOT, then the default. WARNING: LIVE_ROOT decides which
live directories the fault guard protects. A wrong DESK_ROOT would move that protection off the real live
data directories. Two more behaviour changes (CONTRACT tier correction): an EMPTY FAULT_MATRIX_LIVE_ROOT now falls through to
DESK_ROOT (today it yields Path("")), and an invalid DESK_ROOT now raises ValueError at module import.
Apply P3 only on a box where DESK_ROOT is set by the task installer (P4), never ad hoc.

## P4. docs/operations/install_paper_desk_task.ps1 (puts DESK_ROOT into the scheduled task)

```diff
-$arguments = @($HiddenLaunch, '--log', $log, '--cwd', $Root, '--tag', 'S500',
+$arguments = @($HiddenLaunch, '--log', $log, '--cwd', $Root, '--env', "DESK_ROOT=$Root", '--tag', 'S500',
     '--', $PythonPath, '-m', 'scripts.platformkit.ops.paper_desk_tick',
```

hidden_launch.py already takes `--env K=V` (tools/desk_bin/hidden_launch.py:13). With P4, DESK_ROOT and
`--root` both come from `$Root`, so P1's agreement check holds by construction. On today's laptop the
value equals the default, so the resolved config is unchanged.

## Not proposed here (NEW GAP candidates, for the register owner to allocate)

- The 15 profile strings outside the repo root (python.exe x6, pythonw.exe x3, bin\hidden_launch.py x3,
  REQUESTS_CA_BUNDLE=...\bin\winroots.pem x3) are machine layout, not repo root. DESK_ROOT does not touch
  them. A recorder VM with another user name or Python location needs its own variable, or a per-box
  config.
- scripts/platformkit/ops/probes/s421_probe*.py hard-code `Path("C:/Users/neelj/nba-ai-system")`. They are
  one-off probes and are left as they are.
