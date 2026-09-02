# S24 -- artifact refresh has no scheduler (`fleet_on` false)

Verdict: **ACCEPT** -- 3/3 consecutive `--once` passes, monotone stamp on every
producer-backed target, measured on the REAL artifacts on this box (not only the
stubbed test). Calibration language only; no dollar, ROI, profit or edge figure
appears here.

Lane J, main repo, 2026-09-03. Spec: `docs/evidence/tracking/specs/S24_spec.md`
(including its UPDATE line: `harness_health` now HAS a producer).
Memo filename follows the spec's EVIDENCE line; the orchestrator prompt named the
same memo as `S24_artifact_refresh_2026-09-03.md` -- one file, this one.

## Step 0 -- premise (HOLDS)

* `grep -rniE "schtasks|crontab|\bcron\b" scripts/platformkit/**.py` -> the only
  hits are `brain_rebuild_runner.py` (docstring), `eval_gate/ledger_backup.py`
  (S29's memo-carries-the-schtasks-line note), `forward_capture/run_capture.py`,
  `ledger/drift_check.py`, `pod_ops_watch.py` (pod liveness),
  `progress/ci_schedule.py` / `ci_cadence_runner.py` (a DIFFERENT subsystem's
  external cadence), `tip_capture/*` (`--once` flags). **No entry refreshes any
  MCP front-door artifact.**
* `scripts/platformkit/mcp_server/` contained no `artifact_refresh*` before this
  landing.
* `fleet_on` as tools.py:104 computes it today: `.bot_state/live_status.json`
  `stop_requested=true` -> **`fleet_on = false`** (the by-design resident-server
  default).
* Heartbeat file `data/cache/mcp_server/artifact_refresh_heartbeat.jsonl`:
  **MISSING** before this landing.

=> before = 0 scheduled runs, 0 heartbeat lines.

Artifact ages at step 0 (hours before the first pass):

| artifact | age_h | bytes |
|---|---:|---:|
| `scripts/platformkit/analytics_showcase/out/market_strength_atlas.json` | 16.5 | 16,944 |
| `scripts/platformkit/analytics_showcase/out/mechanism_exposure.json` | 14.4 | 1,746,047 |
| `data/frontend/analytics/mechanism_exposure.json` | MISSING | - |
| `data/frontend/analytics/harness_health.json` | 9.3 | 3,301 |
| `data/cache/analytics_verify/harness_health.json` | MISSING | - |
| `scripts/platformkit/analytics_showcase/out/harness_health.json` | MISSING | - |
| `data/frontend/analytics/execution_status.json` | 9.0 | 896 |
| `scripts/platformkit/analytics_showcase/out/execution_status.json` | MISSING | - |
| `scripts/platformkit/analytics_showcase/out/paper_execution_audit.json` | 14.5 | 3,665 |

## Producer map (every MCP tool, producer or not)

| MCP tool | artifact paths (IMPORTED from artifact_tools) | producer callable |
|---|---|---|
| `strength_atlas` | `_ATLAS` | `analytics_showcase/market_strength_atlas.build` |
| `mechanism_exposure` | `_MECHANISM` | `analytics_showcase/mechanism_exposure.build` |
| `harness_health` | `_HEALTH` | `eval_gate/harness_health_report.build` (landed bbf49a597) |
| `execution_status` | `_EXECUTION` | `pm_trading/clv_daily_readout.write_readout` |
| `tracking_program_status` | (glob) | **NO_PRODUCER** |

`tracking_program_status` derives itself from a glob over
`docs/evidence/tracking/*.json|*.md` and `data/tracking_reports/**/*.json`. There
is no single artifact and no writer to call, so the refresher records it
`NO_PRODUCER` and never invents one; it is counted and named in every pass, never
dropped from the denominator.

## The three real passes (this box, root = repo)

Stamp = the artifact's own `generated_at` when it declares one. Two artifacts
declare an `as_of` that is NOT a freshness stamp (`market_strength_atlas`:
"latest accepted game date per sport"; `mechanism_exposure`: `2026-05-24`, a data
date), so `generated_at` is the freshness field and `as_of` is carried alongside
verbatim as the MCP tool reports it.

| target | pass 1 stamp_after | pass 2 stamp_after | pass 3 stamp_after | monotone |
|---|---|---|---|---|
| `strength_atlas` | 14:09:47.590051 | 14:10:06.477680 | 14:10:12.755401 | yes |
| `mechanism_exposure` | 14:09:49.571745 | 14:10:08.808381 | 14:10:15.094388 | yes |
| `harness_health` | 14:09:50.571508 | 14:10:09.838802 | 14:10:16.397705 | yes |
| `execution_status` | 14:09:50.633445 | 14:10:09.887559 | 14:10:16.438907 | yes |
| `tracking_program_status` | NO_PRODUCER | NO_PRODUCER | NO_PRODUCER | n/a |

(All 2026-09-02 UTC; the box clock reads 2026-09-02 while the register day is
2026-09-03 -- the stamps are the machine's, not the register's.)

Pass counters, all three passes identical: `n_targets=5, n_advanced=4, n_failed=0,
n_no_producer=1, n_stale=0`. Heartbeat
`data/cache/mcp_server/artifact_refresh_heartbeat.jsonl` = exactly 3 lines,
started_at `14:09:45.396621`, `14:10:02.828078`, `14:10:10.248174`.

Pass 1 `stamp_before` for `execution_status` was `2026-09-03T00:00:00+00:00` --
the previous writer (`clv_daily_readout.main`) hardcodes that `now_iso`, so the
first real pass moved the stamp BACKWARDS to the true wall clock. `advanced` is
therefore defined as "the stamp changed", and monotonicity is asserted across the
three passes AFTER the refresher owns the stamp (it holds, above).

## MCP handlers after the refresh

`tools.handler_for(name)({})` for all five tools:

| tool | status | as_of reported | source_artifact |
|---|---|---|---|
| `strength_atlas` | ok | `latest accepted game date per sport` | `.../out/market_strength_atlas.json` |
| `mechanism_exposure` | ok | `2026-05-24` | `.../out/mechanism_exposure.json` |
| `harness_health` | ok | `2026-09-02T05:42:37.630316+00:00` | `data/frontend/analytics/harness_health.json` |
| `execution_status` | ok | `2026-09-02T14:10:16.438907+00:00` | `data/frontend/analytics/execution_status.json` |
| `tracking_program_status` | ok | `2026-09-02T14:09:25.952065+00:00` | glob list |

None raised; none returned `no_data`.

## Tests

* `python -m pytest tests/platformkit/mcp_server/test_artifact_refresh.py -q` ->
  **7 passed** (0.75s): one-pass advance + single heartbeat line; three passes ->
  exactly 3 lines with strictly increasing stamps and the SAME four target names
  each pass; a raising producer -> `FAILED` with `rc=1` and its message, the other
  rows still advance, still exactly one heartbeat line; a producer-less target ->
  `NO_PRODUCER`, never advanced, and the four counters sum to `n_targets`; nothing
  written outside `tmp_path`; the TARGETS table covers every `tool_specs()` name;
  the module contains no `subprocess` / `Popen` / `os.system` / `ProcSpec(`.
* `python -m pytest tests/platformkit/mcp_server/test_artifact_tools.py -q` ->
  **5 passed** (0.45s), unchanged.

## The cadence line -- NOT armed by this lane

The orchestrator arms this; the module never creates a task (it is the `SCHTASKS`
constant, a string, and the test asserts the module executes nothing):

```
schtasks /Create /SC HOURLY /TN CourtVision-ArtifactRefresh /TR "<python> -m scripts.platformkit.mcp_server.artifact_refresh --once"
```

Equivalent supervisor ProcSpec, if the orchestrator prefers the fleet over the OS
scheduler (also NOT armed here):

```
ProcSpec(name="artifact_refresh",
         argv=[sys.executable, "-m", "scripts.platformkit.mcp_server.artifact_refresh",
               "--loop", "--interval", "3600"],
         cwd=REPO_ROOT, restart=True)
```

`--loop` exists only for that ProcSpec and was never run in this lane. The spec
text said "no loop mode"; the orchestrator prompt asked for `--loop --interval N`
as the cadence mode -- it is present, four lines, unexercised, and starts nothing
on import.

## must-not-move (verified unchanged)

`scripts/platformkit/mcp_server/artifact_tools.py` is untouched -- its `_ROOT`,
`_ATLAS`, `_MECHANISM`, `_HEALTH`, `_EXECUTION`, `_load` and `_as_of` are
IMPORTED, never copied. `STALENESS_HOURS = 48.0` in `analytics_verify/answers.py`
and every other staleness bound untouched. `.bot_state/live_status.json` read
only in step 0, never written. No ProcSpec, no supervisor, no threshold under
`scripts/platformkit/eval_gate/` edited. `data/registry/**` never written.
`data/cache/eval_gate/backtest_fwer.jsonl` not written by this lane (the
harness_health producer reads it read-only); no `_charge_ledger` call anywhere in
the diff.

## NOT VERIFIED

* **No OS task was created** and no supervisor ProcSpec was armed. Nothing runs on
  a cadence as a result of this landing -- the refresher only exists and works.
* **No daemon was started.** `--loop` was never executed.
* The three real passes ran back-to-back by hand inside ~30 seconds; an HOURLY
  cadence (the schtasks line) has never been exercised.
* A hanging producer would hang the pass: the adapters are in-process callables,
  so there is no per-producer timeout (the spec's subprocess timeout does not
  apply). `ponytail:` upgrade path -- move an adapter to `subprocess` only if one
  actually hangs.
* `tracking_program_status` freshness is still unmanaged; `NO_PRODUCER` is a
  recorded fact, not a fix.
* The refreshed artifacts' CONTENTS were not re-audited -- this lane measures the
  freshness stamp advancing, nothing about whether any number in them is right.
* `--out-dir` was left at its default for the real passes, so the heartbeat lives
  in gitignored `data/cache/mcp_server/` and is not committed.

NEW GAP: two MCP tools report an `as_of` that is not a timestamp
(`strength_atlas` = "latest accepted game date per sport", `mechanism_exposure` =
a data date), so a consumer cannot judge those two artifacts' freshness from the
envelope at all.
