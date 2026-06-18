# Headless claude -p Recipe and Nightly Cron Plan

## Corrected headless recipe

### Flags that DO exist
```
claude -p "prompt text"
       --output-format json       # structured JSON output (includes cost)
       --output-format stream-json # streaming JSON events
       --allowedTools "Bash,Read,Glob"   # comma-separated tool allowlist
       --permission-mode acceptEdits     # or default / bypassPermissions
       --json-schema path/to/schema.json # constrain output to JSON schema
```

### Flags that do NOT exist (common mistakes)
```
--max-turns      # DOES NOT EXIST -- cap turns via subagent maxTurns frontmatter
--max-budget-usd # DOES NOT EXIST -- read cost post-hoc from JSON output
```

### Correct cost-extraction pattern
```bash
# Run headless, capture full JSON, extract cost with jq:
claude -p "your prompt" --output-format json > /tmp/run.json
jq '.total_cost_usd' /tmp/run.json

# Or pipe to cost ledger in one shot:
claude -p "your prompt" --output-format json \
  | python scripts/platformkit/cost_ledger.py --tag nightly_eval
```

### Cap turns correctly (via subagent frontmatter)
If you want to cap turns for a spawned subagent, add to its .claude/agents/<name>.md:
```yaml
---
name: eval-worker
maxTurns: 10
model: claude-haiku-4-5
---
```
There is no CLI flag for this.

### Full headless pattern for nightly jobs
```bash
#!/usr/bin/env bash
# Example: nightly eval gate run
set -euo pipefail

REPO=/c/Users/neelj/nba-ai-system
PROMPT="Run the eval gate on today's predictions. Output JSON with keys:
  sport, date, n_games, brier, mae_pts, mae_reb, mae_ast, drift_flag."

cd "$REPO"
claude -p "$PROMPT" \
  --output-format json \
  --allowedTools "Bash,Read,Glob,Grep" \
  --permission-mode acceptEdits \
  > /tmp/eval_gate_run.json

# Log cost
python scripts/platformkit/cost_ledger.py \
  --input /tmp/eval_gate_run.json \
  --tag eval_gate

# Extract result
jq '.result' /tmp/eval_gate_run.json
```

---

## Nightly Cron Plan

Three nightly jobs. Each is a headless claude -p call piped through cost_ledger.py.
All times in UTC. Repo cwd: /c/Users/neelj/nba-ai-system.

### Job 1: Eval Gate (02:00 UTC)

**Purpose:** score yesterday's predictions against actuals; flag calibration drift.

**Trigger:** 02:00 UTC daily (after box scores land ~01:30 UTC)

**Cron line (Windows Task Scheduler or WSL cron):**
```
0 2 * * * cd /c/Users/neelj/nba-ai-system && bash scripts/cron/nightly_eval_gate.sh >> data/ops/cron_eval_gate.log 2>&1
```

**Script skeleton (scripts/cron/nightly_eval_gate.sh):**
```bash
#!/usr/bin/env bash
set -euo pipefail
PROMPT="Run scripts/platformkit/eval_gate/run_all.py for yesterday's games.
Output JSON: {sport, date, n_games, brier, cal_error, drift_flag, next_action}."
claude -p "$PROMPT" --output-format json \
  | tee /tmp/eval_run.json \
  | python scripts/platformkit/cost_ledger.py --tag eval_gate
python scripts/platformkit/obs/alert_on_drift.py --input /tmp/eval_run.json
```

**Output:** appends to data/ops/cost_ledger.parquet; alert if drift_flag=true.

---

### Job 2: Benchmark (03:00 UTC)

**Purpose:** run 300-frame CV tracking benchmark, compare to previous run, log to vault.

**Trigger:** 03:00 UTC daily (after eval gate completes)

**Cron line:**
```
0 3 * * * cd /c/Users/neelj/nba-ai-system && bash scripts/cron/nightly_benchmark.sh >> data/ops/cron_benchmark.log 2>&1
```

**Script skeleton (scripts/cron/nightly_benchmark.sh):**
```bash
#!/usr/bin/env bash
set -euo pipefail
PROMPT="Run the benchmark skill: download a fresh NBA clip, run tracking pipeline
on 300 frames, evaluate quality metrics, cross-validate NBA Stats API,
compare to previous run, log to vault. Output JSON summary."
claude -p "$PROMPT" --output-format json \
  | tee /tmp/benchmark_run.json \
  | python scripts/platformkit/cost_ledger.py --tag benchmark
```

**Note:** benchmark downloads a clip -- ensure network + disk are available at 03:00 UTC.
Clip download + 300-frame pipeline estimated ~8-12 min on RTX 4060.

---

### Job 3: Calibration Drift Check (04:00 UTC)

**Purpose:** check whether model calibration has drifted vs prior 7-day rolling window;
emit a report to vault and flag if ECE > 0.05.

**Trigger:** 04:00 UTC daily

**Cron line:**
```
0 4 * * * cd /c/Users/neelj/nba-ai-system && bash scripts/cron/nightly_cal_drift.sh >> data/ops/cron_cal_drift.log 2>&1
```

**Script skeleton (scripts/cron/nightly_cal_drift.sh):**
```bash
#!/usr/bin/env bash
set -euo pipefail
PROMPT="Run scripts/platformkit/obs/drift_report.py for all active sports.
Compute ECE, reliability diagram data, and compare to 7-day baseline.
Output JSON: {sport, date, ece, reliability_bins, drift_flag, recommended_action}."
claude -p "$PROMPT" --output-format json \
  | tee /tmp/cal_drift_run.json \
  | python scripts/platformkit/cost_ledger.py --tag cal_drift
```

**Drift flag definition:** ECE > 0.05 OR abs(bias) > 0.02 on any market tier.

---

## Windows Task Scheduler setup (WSL path)

If running on Windows 11 Home with WSL2:

1. Open Task Scheduler -> Create Basic Task
2. Trigger: Daily, specific time (UTC offset from local)
3. Action: Start a program
   - Program: C:\Windows\System32\wsl.exe
   - Arguments: -e bash /c/Users/neelj/nba-ai-system/scripts/cron/nightly_eval_gate.sh
4. Run whether user is logged on or not
5. Conditions: uncheck "Start only if AC power"

Alternatively, use WSL2 cron directly:
```bash
# In WSL2:
crontab -e
# Add lines from above
```

---

## Cost estimation (per nightly run)

| Job            | Model        | Est tokens (in+out) | Est cost/run |
|----------------|-------------|---------------------|--------------|
| eval_gate      | Haiku 4-5   | ~8K / ~2K           | ~$0.003      |
| benchmark      | Sonnet 4-5  | ~15K / ~3K          | ~$0.045      |
| cal_drift      | Haiku 4-5   | ~6K / ~1K           | ~$0.002      |
| Monthly total  |             |                     | ~$1.50/mo    |

All costs tracked in data/ops/cost_ledger.parquet via cost_ledger.py.
