# Pod Batch 2026-09-04 Pass 2

Verdict: **PARTIAL COMPLETE.** The deploy completed with `tar_rc=0` and
all 12 required files matched non-empty HEAD blobs. The functional bootstrap
result was 6/7. No foundry process satisfied the only permitted `/proc` match,
so no process was signaled and no guessed relaunch was attempted. S217 was
skipped because its memo contains no launch or dry-run command. Calibration
language only; no flag was changed.

## Scope and code identity

- Main-repo HEAD deployed: `f1bfb3d2a8e633bb750486ef68c574274f4b9305`.
- Pod: `root@213.192.2.123:40034`, repo `/workspace/nba-ai-system`.
- The archive pathset was `scripts/platformkit`, `domains`, `kernel`, `api`,
  `src`, `tests`, and
  `docs/evidence/harness/S217_mlb_depth_capture_pod_2026-09-04.md`.
- No `data/`, `vault/`, `.planning/`, or `.claude/` path was in the archive.
- No FWER file was transferred to the pod. No registry path was written.
- The only local file written by this lane is this memo.

## Step 0 - capacity gate

Command, with `du -sh /workspace` first:

```bash
ssh -F ~/.ssh/config.pod pod 'du -sh /workspace; df -h /workspace; du -sh /workspace/nba-ai-system/data 2>/dev/null; ls /workspace/*.log | head'
```

Exit code: 0. `/workspace` was 38G, below the 45G stop threshold. The mounted
filesystem reported 929T total, 593T used, 337T available, and 64 percent use,
below the greater-than-90-percent stop threshold. The repo data tree was 35G.
The first listed logs were `bootstrap.log`, `bootstrap2.log`,
`foundry_runner_s154.log`, `g172_cv2_environment_gap_20260903_a5.log`,
`keep_track_daemon.log`, `keepalive.log`, `mlb_book_capture.log`, `paper.log`,
and `track_daemon.log`. Deployment was allowed to proceed.

## Step 1 - deploy and parity

Deploy command:

```bash
set -o pipefail
git -c core.autocrlf=false archive HEAD -- scripts/platformkit domains kernel api src tests docs/evidence/harness/S217_mlb_depth_capture_pod_2026-09-04.md | ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && tar -x --no-same-owner'
```

Result: `tar_rc=0`. No stderr was suppressed. Local hashes were computed from
`git show HEAD:<file> | md5sum`; pod hashes came from `md5sum <file>`. The S217
capture module is `mlb_book_capture.py`, named in the S217 memo. The three
additional in-game files were `aci_online.py`, `arm_registry.py`, and
`blend_apply.py`.

| File | HEAD md5 | Pod md5 | Pod bytes | Result |
|---|---|---|---:|---|
| `scripts/platformkit/foundry_runner.py` | `18dcb3e7fddc067bdfb5ec1f748787c8` | `18dcb3e7fddc067bdfb5ec1f748787c8` | 16500 | MATCH |
| `scripts/platformkit/signal_foundry.py` | `ac8161e3b65078afaca035ddac401b77` | `ac8161e3b65078afaca035ddac401b77` | 13281 | MATCH |
| `scripts/platformkit/ops/pod_bootstrap_check.py` | `22b694d9f00666b3d3e3df576253c4e5` | `22b694d9f00666b3d3e3df576253c4e5` | 12935 | MATCH |
| `scripts/platformkit/ingame/inplay_capture_loop.py` | `b5d9ddbe316adeed3c534e31d9ee3053` | `b5d9ddbe316adeed3c534e31d9ee3053` | 71567 | MATCH |
| `scripts/platformkit/ingame/cycle_history.py` | `12df710614f9636e20fc40acc9b78be6` | `12df710614f9636e20fc40acc9b78be6` | 2636 | MATCH |
| `scripts/platformkit/eval_gate/calibration_report.py` | `a1febfdc52e2206c5f3b277e4f390c47` | `a1febfdc52e2206c5f3b277e4f390c47` | 13638 | MATCH |
| `scripts/platformkit/tracking_harness.py` | `856db0b3c0da4e89ba2418467d30bb6e` | `856db0b3c0da4e89ba2418467d30bb6e` | 21426 | MATCH |
| `scripts/platformkit/track_daemon.py` | `6e884d8c16194c3e7809df97fe5274e2` | `6e884d8c16194c3e7809df97fe5274e2` | 21118 | MATCH |
| `scripts/platformkit/ingame/mlb_book_capture.py` | `b5be8ee4996f0c1f9df77ad8b08d0c47` | `b5be8ee4996f0c1f9df77ad8b08d0c47` | 14605 | MATCH |
| `scripts/platformkit/ingame/aci_online.py` | `e2207e37a5cb70a02456949e61e55291` | `e2207e37a5cb70a02456949e61e55291` | 9304 | MATCH |
| `scripts/platformkit/ingame/arm_registry.py` | `18919637df026e26d17dfe0b6967a182` | `18919637df026e26d17dfe0b6967a182` | 3005 | MATCH |
| `scripts/platformkit/ingame/blend_apply.py` | `34269b8926171a7003f5771a553609c8` | `34269b8926171a7003f5771a553609c8` | 7481 | MATCH |

Parity command exit code: 0. Final parity: **12/12**. No digest was
`d41d8cd98f00b204e9800998ecf8427e`; no repair deploy was needed.

## Step 2 - bootstrap check

The first command was the requested bare invocation:

```bash
cd /workspace/nba-ai-system && python scripts/platformkit/ops/pod_bootstrap_check.py
```

Exit code: 0. It reported 14/14 imports clean, but did not run the seven
functional probes. The memo-backed command was then run:

```bash
cd /workspace/nba-ai-system && python scripts/platformkit/ops/pod_bootstrap_check.py --profile paper --functional --python /usr/local/bin/python
```

Exit code: 1. Functional result: **6/7**.

| Probe | Result | Evidence |
|---|---|---|
| `parquet_mlb_games` | OK | 27,983 rows, 10 columns |
| `mlb_predictor_init` | OK | 27,983 games, 34 teams |
| `produce_mlb_dry` | OK | status OK, 38 predictions, 112 markets |
| `espn_live_state_mlb` | OK | 4 live games |
| `factory_sources` | OK | 61/61 sources present |
| `boot_packages` | OK | all five named packages imported |
| `supervisor_lock_env` | FAIL | no `-m supervisor` pid in `/proc` |

The import-only command also reported the five required environment names as
missing from its shell. No environment value or process was changed.

## Step 3 - foundry runner

The required scan iterated `/proc/[0-9]*`, skipped the scanning shell's pid,
decoded each NUL-delimited argv, required argv0 exactly `/usr/local/bin/python`, and required
an exact `foundry_runner`, `scripts.platformkit.foundry_runner`, or
`*/foundry_runner.py` argument. Result: `foundry_matches=0`, scan exit code 1.
A second read-only scan allowed any Python argv0 with an exact foundry module or
script argument; result: 0. A final read-only Python-process substring census
also returned 0.

- pid before: `none`.
- exact argv before: unavailable because no permitted process existed.
- current log: `/workspace/foundry_runner_s154.log`, 6,835,769 bytes.
- measured log mtime: `2026-09-04 00:51:15 +0000`.
- signal sent: none.
- pid after: `none`.
- relaunch: skipped; same-argument evidence was unavailable.
- `/workspace/foundry_runner_s233.log`: not created by this lane.

Last three lines of the current log:

```text
screen_failed tier=T0 family=nba:asof_team_adv feature=home_ast_pct_asof reason=ScreenRefused: unavailable: home_ast_pct_asof not found one-row-per-event in no frozen family source
screen_failed tier=T0 family=nba:asof_team_adv feature=away_pace_asof reason=ScreenRefused: unavailable: away_pace_asof not found one-row-per-event in no frozen family source
promotions_held family=nba:boxdetail_asof count=1 reason=allow_charge_off
```

Read-only SQLite URI query of
`data/cache/eval_gate/hypotheses.sqlite` (23,883,776 bytes):

- queued = 43,536 rows (`queue.claimed_at IS NULL`).
- claimed = 2,184 rows (`queue.claimed_at IS NOT NULL`).
- done = 1,387 `result` rows and 1,387 distinct hash/tier pairs.
- done by tier = T0 758 and T1 629.
- excluding same-tier completed rows: queued-open 43,286 and claimed-open 1,676.
- queue rows with a same-tier result = 758.
- claimed owners were `5a20910184ad:55054` with 1,068 rows and
  `5a20910184ad:55269` with 1,116 rows; neither pid existed.

## Step 4 - S217 capture

Skipped; pid = `skipped`. The deployed HEAD memo
`docs/evidence/harness/S217_mlb_depth_capture_pod_2026-09-04.md` is a
premise-falsified closure. It names no launch or dry-run command, states that no
capture helper was produced, and states that restart behavior was not
constructed. The functional live-state probe did report four MLB games on
2026-09-04 UTC, but the missing launch command remained decisive. No substitute
command was invented and no capture path was written.

## Step 5 - bounded measurements

### S19/S55 paper stack

The exact `/proc` module scan found no supervisor pid, so its direct child count
was 0. No supervisor action was taken. The last three lines of
`/workspace/paper.log` were:

```text
2026-09-03 14:17:41,298 INFO supervisor.supervisor: supervisor: launched m33_http_wedge_reaper pid=37086
2026-09-03 14:17:42,310 INFO supervisor.supervisor: supervisor: launched m43_settle_sweep pid=37176
2026-09-03 14:17:43,328 INFO supervisor.supervisor: supervisor: launched m44_exec_evidence pid=37268
```

### S32 in-play capture

`/proc` showed pid 36783 with exact argv
`/usr/local/bin/python -u -m scripts.platformkit.ingame.inplay_capture_runner`.
Stdout was `logs/m2_inplay_capture.out`; stderr was
`logs/m2_inplay_capture.err`. Stdout contained one startup line whose restricted
non-calibration token is not copied here. The last three logical stderr lines
were:

```text
kalshi in-play markets failed for kbo/KXKBOSPREAD: HTTP Error 429: Too Many Requests
kalshi in-play markets failed for wnba/KXWNBATOTAL: HTTP Error 429: Too Many Requests
kalshi in-play markets failed for mlb/KXMLBGAME: HTTP Error 429: Too Many Requests
```

The exact UTC-day cycle store named by the deployed code was
`data/cache/ingame_cycle_history/2026-09-04.jsonl`. It was absent, so its stored
tick count was **0**. The current measurement heartbeat was
`data/cache/ingame_grade/_capture_heartbeat.json` (15,350 bytes), with
`as_of=2026-09-04T01:13:35Z`, `n_live=5`, `n_pairs=5`,
`n_requests_total=19`, and `n_429_total=1`. The daemon heartbeat
`data/cache/daemon_heartbeats/m2_inplay_capture.txt` held the same timestamp.

### S33 MLB depth capture

No Python process argv contained `mlb_book_capture` or `run_pod_capture`.
`/workspace/mlb_book_capture.log` was 0 bytes and therefore had no last-three
line payload. No action was taken.

### Utilization

Snapshot at `2026-09-04T01:12:34+00:00`:

```text
GPU utilization: 0 percent; memory used: 1023 MiB
uptime: 147 days 15:26; load average: 15.89, 14.75, 16.42
RAM GiB: total 1007, used 68, free 160, buff/cache 788, available 939
swap GiB: total 0, used 0, free 0
```

Commands were `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv`,
`uptime`, and `free -g`; all completed in the measurement SSH session.

### Partial files

Read-only census command:

```bash
find /workspace/nba-ai-system/data -type f -name '*.part' -print | sort
```

Count: **0**. There were no paths or sizes to list. Nothing was deleted.

## NOT VERIFIED

- The foundry same-argument restart, new pid, and new-log first five lines are
  not verified because no permitted foundry pid existed and no argv could be
  captured before a signal.
- S217 launch, resume behavior, cadence, uniqueness, lost-window, and 429
  measurements are not verified because the memo names no command and records
  a premise-falsified closure.
- The seventh bootstrap probe is not verified; it failed on supervisor absence.
- Supervisor liveness is not verified; only the missing exact cmdline, zero
  direct-child count, heartbeat ages, and paper-log tail were measured.
- The S32 UTC-day cycle file contains no persisted rows; the current heartbeat
  verifies a live cycle at `2026-09-04T01:13:35Z`, not cycle-history durability.
- S33 capture output is not verified because its process was absent and its log
  was empty.
