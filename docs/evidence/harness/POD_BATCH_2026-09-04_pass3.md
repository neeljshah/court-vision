# Pod Batch 2026-09-04 Pass 3

Verdict: **COMPLETE WITH NOT VERIFIED ITEMS.** Pass-2 parity was confirmed at
12/12 before launch. The required `/proc` scan found no foundry runner, so the
specified module invocation was launched once. After 213 seconds it was the
sole exact match at PID 1999712 and was actively consuming CPU. Its redirected
log was still empty. S217 was skipped because its closure memo names no command
and constructed no resumable helper. No protected process was signaled or
restarted. No feature flag was changed. Calibration language only.

## Scope

- Main repo: `C:/Users/neelj/nba-ai-system`, branch `master`.
- Pod: `root@213.192.2.123:40034`, repo `/workspace/nba-ai-system`.
- Local writes by this lane: only this memo.
- Pod launches by this lane: one foundry runner; no S217 process.
- No write was made to `data/cache/eval_gate/backtest_fwer.jsonl` or
  `data/registry`.
- No supervisor, in-play capture, MLB book capture, tracking daemon, or adapter
  process was killed, signaled, or restarted.
- All local shell commands were run with Bash; PowerShell was not launched.

## Step 0 - storage gate

Command:

```bash
ssh -F ~/.ssh/config.pod pod 'du -sh /workspace; df -h /workspace; dd if=/dev/zero of=/workspace/.quota_probe bs=1M count=8 && rm -f /workspace/.quota_probe'
```

Exit code: 0.

```text
32G /workspace
Filesystem size 929T, used 593T, available 336T, use 64 percent
8+0 records in
8+0 records out
8388608 bytes copied
```

The required 8 MiB write probe passed, and the probe file was removed by the
same command.

## Step 1 - pass-2 parity gate

Local reads:

```bash
sed -n '1,260p' docs/evidence/harness/POD_BATCH_2026-09-04_pass2.md
sed -n '1,300p' docs/evidence/harness/S217_mlb_depth_capture_pod_2026-09-04.md
git status --short --branch
```

Each exited 0. The pass-2 memo records non-empty local HEAD and pod MD5 values
for all 12 required files, with every pair equal. Final parity: **12/12**.
Because the required denominator was already 12/12, no rehash and no repair
deploy were performed in pass 3.

The 12 confirmed files were:

1. `scripts/platformkit/foundry_runner.py`
2. `scripts/platformkit/signal_foundry.py`
3. `scripts/platformkit/ops/pod_bootstrap_check.py`
4. `scripts/platformkit/ingame/inplay_capture_loop.py`
5. `scripts/platformkit/ingame/cycle_history.py`
6. `scripts/platformkit/eval_gate/calibration_report.py`
7. `scripts/platformkit/tracking_harness.py`
8. `scripts/platformkit/track_daemon.py`
9. `scripts/platformkit/ingame/mlb_book_capture.py`
10. `scripts/platformkit/ingame/aci_online.py`
11. `scripts/platformkit/ingame/arm_registry.py`
12. `scripts/platformkit/ingame/blend_apply.py`

## Step 2 - foundry runner relaunch

The pre-launch scan iterated `/proc/[0-9]*`, skipped its own shell PID, decoded
NUL-delimited argv, required argv0 `/usr/local/bin/python`, and required a later
argument containing `foundry_runner`. Command shape:

```bash
ssh -F ~/.ssh/config.pod pod 'self=$$; count=0; for d in /proc/[0-9]*; do pid=${d#/proc/}; [ "$pid" = "$self" ] && continue; [ -r "$d/cmdline" ] || continue; mapfile -d "" -t av < "$d/cmdline" || continue; [ "${#av[@]}" -gt 0 ] || continue; [ "${av[0]}" = "/usr/local/bin/python" ] || continue; hit=0; for a in "${av[@]:1}"; do case "$a" in *foundry_runner*) hit=1;; esac; done; [ "$hit" -eq 1 ] || continue; count=$((count+1)); printf "FOUNDRY_PID=%s ARGV=" "$pid"; printf "%q " "${av[@]}"; printf "\n"; done; printf "FOUNDRY_MATCHES=%s\n" "$count"'
```

Exit code: 0. Result: `FOUNDRY_MATCHES=0`.

Launch command:

```bash
ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && { FOUNDRY_PORTABLE_CORPUS=1 FOUNDRY_CLOSE_INCUMBENT=1 nohup /usr/local/bin/python -m scripts.platformkit.foundry_runner --db data/cache/eval_gate/hypotheses.sqlite --sport mlb,nba,soccer,tennis --predictor real --batch 50 --screen-rows 800 --poll-seconds 30 > /workspace/foundry_runner_s233.log 2>&1 & runner_pid=$!; printf "FOUNDRY_LAUNCHED_PID=%s\n" "$runner_pid"; }'
```

Exit code: 0. Shell-returned PID: `1999712`. The requested module entry point
was used exactly; no alternate invocation or help-derived command was needed.

Post-launch snapshot at `2026-09-04T01:36:40Z`, 213 seconds after the process
and log start time of `2026-09-04T01:33:07Z`:

```text
FOUNDRY_PID=1999712
ARGV=/usr/local/bin/python -m scripts.platformkit.foundry_runner --db data/cache/eval_gate/hypotheses.sqlite --sport mlb,nba,soccer,tennis --predictor real --batch 50 --screen-rows 800 --poll-seconds 30
FOUNDRY_MATCHES=1
process state=Rl, elapsed=268 s, CPU=20.6 percent
stdout target=/workspace/foundry_runner_s233.log
new log bytes=0
new log mtime=2026-09-04 01:33:07Z
first 10 log lines=(none; file empty)
traceback lines=(none; file empty)
screen_failed log lines=0
```

The `/proc` recheck and combined timestamp/log/SQLite snapshot exited 0. A
separate read-only process-status and schema batch exited 1 because its first
SQLite schema query had shell-quoting damage. It printed process and log facts
before the query failed. The corrected schema-only command was:

```bash
ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && /usr/local/bin/python -c '"'"'import sqlite3; db=sqlite3.connect("file:data/cache/eval_gate/hypotheses.sqlite?mode=ro", uri=True); print("DB_TABLES=" + ",".join(r[1] for r in db.execute("PRAGMA table_list") if r[1] not in ("sqlite_schema","sqlite_temp_schema"))); print("QUEUE_COLUMNS=" + ",".join(r[1] for r in db.execute("PRAGMA table_info(queue)"))); print("RESULT_COLUMNS=" + ",".join(r[1] for r in db.execute("PRAGMA table_info(result)"))); db.close()'"'"''
```

Corrected query exit code: 0. The database has only `hypothesis`, `queue`, and
`result` tables. `queue` has `hash,tier,enqueued_at,claimed_at,lease_until,claimer`;
`result` has no failure-status column. The read-only count snapshot was:

| Count | Definition | Value |
|---|---|---:|
| queued | `queue.claimed_at IS NULL` | 45,588 |
| claimed | `queue.claimed_at IS NOT NULL` | 132 |
| done | rows in `result` | 1,387 |
| done distinct | distinct `(hash,tier)` in `result` | 1,387 |
| screen_failed | lines in the new runner log | 0 |

`screen_failed` is not representable as a SQLite count in this schema: failed
screens are printed by the runner but are not stored in a database status
field. The reported zero is therefore a log count since relaunch, not a
database count.

A final read-only check at `2026-09-04T01:39:56Z` re-read
`/proc/1999712/cmdline`, the new log, and the runner heartbeat in one SSH call;
exit code 0. PID 1999712 still had the exact argv above. The log remained empty,
but `data/ab_reports/foundry_runner.heartbeat.json` had advanced to
`2026-09-04T01:37:32Z`: pass 2 completed 48 screens in 134.693 seconds,
`idle=false`, 12 promotions held, and zero charged evaluations. This runtime
row verifies that the relaunched process completed work despite buffered
stdout.

## Step 3 - previous-runner outage window

Command:

```bash
ssh -F ~/.ssh/config.pod pod 'tail -n 200 /workspace/foundry_runner_s154.log'
```

Exit code: 0. A second batched command ran `stat` and searched the whole log for
`Traceback`, quota, filesystem-full, `OSError`, `OperationalError`, exception,
kill, and fatal markers; exit code 0 and no matching line. The log content has
no timestamps. Filesystem evidence gives:

- old log bytes: 6,835,769.
- old log last-write time: `2026-09-04T00:51:15Z`.
- new runner start time: `2026-09-04T01:33:07Z`.
- observable outage window: **2026-09-04T00:51:15Z to 2026-09-04T01:33:07Z**
  (41 minutes 52 seconds).

Final three old-log lines:

```text
screen_failed tier=T0 family=nba:asof_team_adv feature=home_ast_pct_asof reason=ScreenRefused: unavailable: home_ast_pct_asof not found one-row-per-event in no frozen family source
screen_failed tier=T0 family=nba:asof_team_adv feature=away_pace_asof reason=ScreenRefused: unavailable: away_pace_asof not found one-row-per-event in no frozen family source
promotions_held family=nba:boxdetail_asof count=1 reason=allow_charge_off
```

The last recorded screening error is the `away_pace_asof` `ScreenRefused`
line. It is caught by the runner as a non-fatal per-hypothesis failure, and a
normal `promotions_held` line follows it. There is no terminal error or
traceback in the last 200 lines or in the whole-log marker search. Therefore the
reason the prior process exited is **not verified**; the screening error must
not be treated as its cause.

## Step 4 - S217 capture

Memo read command:

```bash
sed -n '1,300p' docs/evidence/harness/S217_mlb_depth_capture_pod_2026-09-04.md
```

Exit code: 0. The memo is a Q8 premise-falsified closure. It names no launch or
dry-run command, says no capture helper was produced, and says resumability was
not constructed. Per the pass-3 instruction, no substitute command was
invented. S217 result: `skipped`; PID: `skipped`.

## Additional command record

- `tail -n 200 /workspace/foundry_runner_s154.log`: exit 0.
- Old-log `stat` plus whole-log fatal-marker search: exit 0, zero matches.
- `grep` fallback over the pass-1 memo after local `rg` was unavailable: exit 0.
- Local `rg` attempt: exit 127 (`rg` unavailable); no state changed.
- Read-only process/log/schema batch: exit 1 at malformed schema SQL; no state
  changed. Corrected read-only schema command: exit 0.
- Final PID/log/heartbeat read-only batch: exit 0.
- Observation waits were local and made no pod call. The pod timestamps prove
  213 seconds between launch and the required snapshot.

## NOT VERIFIED

- The old runner's exit cause is not verified: no terminal error, traceback,
  or kill record was found. Only the last-write time and final screening lines
  are available.
- The new runner's first 10 lines are not verified because its redirected log
  remained 0 bytes. A completed-pass heartbeat is verified separately.
- A durable `screen_failed` database count is not verified because the SQLite
  schema has no failure-status field; zero is only the new-log count.
- S217 launch, PID, resumability, cadence, uniqueness, lost-window count, and
  request-failure tally are not verified because its memo names no command and
  records that no helper was constructed.
- No claim is made about the health of protected services; they were outside
  the mutation scope and were not signaled or restarted.
