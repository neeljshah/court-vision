# Improve Loop — Continuous Prediction Improvement Bot

Specialized variant of the workday loop, scoped to **NBA prediction model
improvement** (the cycle 110/111/112-style work). Runs rounds back-to-back:
each round runs N probes in parallel, ships winners, updates memory, and
plans the next round off the new baseline.

**Model routing — same rule as workday-loop:** Opus orchestrates + plans +
reviews + decides; Sonnet writes the probe code and the live_engine wiring.
Coding never happens in the Opus session — always delegate to Sonnet
subagents. `Explore` does broad searches when needed.

## State

- `scripts/improve_loop/state.json` — rounds completed, ships, rejects,
  saturated angles, current baseline MAE, open frontier candidates
- `scripts/improve_loop/scaffold.py` — `run_endq3_probe(name, treatment_fn)`
  and `run_point_probe(point, name, treatment_fn)` — produce
  `scripts/_results/improve_<name>.md` + `.json` with single-split + WF
  4-fold against the live_engine baseline
- `scripts/_results/improve_*.md` — per-probe results

## EACH WAKE — run a round, then loop

A round = plan N probes → build N probes → run N probes → ship winners.
Default N=4 (room for 6-8 if disjoint).

### 1 — Read state (single Bash, stays in Opus)

```bash
python scripts/improve_loop/state.py
```

Stop the loop only if:
- `open_frontier` is empty AND last 2 rounds shipped nothing → exit
  reason="frontier_exhausted"
- explicit user stop

### 2 — PLAN (Opus, parallel) — propose N probe specs

In **ONE message**, spawn N parallel Opus subagents (`subagent_type=
"general-purpose"`, `model="opus"`). Each gets:
- the saturated-angles list (do not re-attempt)
- the open frontier list (preferred starting set, can deviate)
- the current baseline MAE
- a directive to design a SINGLE concrete probe with: rationale,
  treatment function pseudocode, ship gate, probe filename
  `scripts/probe_R<round>_<slot>_<name>.py`

Spawn diverse probes — different mechanisms, different stats, different
periods (endQ1/Q2/Q3). Variance is the point: 1 of 4 ships is a win.

### 3 — BUILD (Sonnet, parallel) — write N probe scripts

In **ONE message**, spawn N parallel Sonnet subagents
(`subagent_type="general-purpose"`, `model="sonnet"`). Each gets one
probe spec from step 2 plus:
- the scaffold contract: import `from scripts.improve_loop.scaffold
  import run_endq3_probe, BASELINE` (or `run_point_probe`)
- write a 30-50 LOC file: `scripts/probe_R<round>_<slot>_<name>.py`
- the file's `__main__` calls `run_endq3_probe(name, treatment_fn)`
- include `--max-games` arg for fast iteration

### 4 — RUN — execute N probes in parallel via background bash

Spawn N `Bash(run_in_background=True)` calls in ONE message, each:
`conda run -n basketball_ai python scripts/probe_R<round>_<slot>_*.py`.
Wait for notifications. Each probe writes its own
`scripts/_results/improve_*.md` and `.json`.

### 5 — ADJUDICATE (Opus, inline) — read results, decide

For each result: read the `.json`, check `ship` field. For each SHIP:
- if it touches `src/prediction/live_engine.py` — spawn a Sonnet wiring
  agent in step 6
- if it's a recalibration / artifact refresh — just commit the artifact

For each REJECT: extract the saturated angle phrase, call
`scripts/improve_loop/state.py` helpers to record.

If two SHIPS conflict (e.g. both override the same row at the same
period+stat), keep the larger PTS delta; demote the other to "deferred
- composes with X".

### 6 — SHIP (Sonnet, parallel) — wire each winner

In **ONE message**, spawn one Sonnet per ship-eligible winner. Each gets:
- the probe path + result file
- the target file (usually `src/prediction/live_engine.py`)
- a directive: add a `_USE_<flag>=True`, add a helper, gate the change
  on snapshot period, never break existing flags. Run
  `python -m pytest tests/test_live_engine*.py -q` before reporting.
- commit message template: `cycle R<round>_<slot> (improve_loop): <name>`

After all wiring Sonnets return, Opus reviews diffs, commits, pushes
`master` and `bot/live`.

### 7 — MEMORY (Opus, inline) — update vault + state

After commits:
```python
# scripts/improve_loop/state.py
record_ship(name, delta_pts, stats_won, commit, summary)
record_reject(name, reason, saturated_angle)
bump_round()
update_baseline({...new MAEs from the largest shipped probe...})
```

Append one block to `vault/Improvements/Tracker Improvements Log.md`
summarizing the round (ships, rejects, baseline shift).

Append one line per ship to `vault/Sessions/Decision Log.md`:
`| <date> | improve_loop R<round>: <name> | <delta> PTS / <wins>/7 |`

If a learning is durable and non-obvious, sharpen the existing entry in
`vault/Improvements/Engineering Knowledge.md`. Dedup, don't append.

### 8 — LOOP

Re-probe state (step 1). If frontier still has candidates and recent
rounds are productive, continue in-turn. Otherwise schedule wake or exit.

## Why this beats sequential cycles

| Sequential (cycles 110-112) | Parallel (improve_loop) |
|----------------------------|-------------------------|
| 1 probe at a time | 4-8 probes per round |
| 1 plan → 1 build → 1 run | N plans in parallel, N builds in parallel, N runs in parallel |
| ~200 LOC per probe (no scaffold) | ~30-50 LOC per probe (uses scaffold) |
| Manual state tracking | Compounding state.json — planning agents read saturated angles |
| Memory updated ad-hoc | Memory updated every round, machine-readable |

The expected hit rate is low (1 in 4 ships) — that's the point. The bot
runs broad and cheap searches, ships the wins, learns from the losses.

## Hard constraints

- Never edit `src/prediction/betting_portfolio.py`, `database/schema.sql`,
  `CLAUDE.md` — those go to `for-review.md`
- Walk-forward 4/4 + single-split strictly down + >=4/7 wins is the ship
  gate. No exceptions.
- Probes must use `from scripts.improve_loop.scaffold import ...` so all
  results are uniform.
- Saturated angles in state.json are sacred — never re-attempt without
  a fundamentally new mechanism (e.g. different feature set, different
  baseline).
- conda env: `basketball_ai`. Use `Write` for multiline Python — never
  `conda run -n basketball_ai python -c "..."` with newlines.
