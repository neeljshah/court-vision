# signal-loop — Self-Improving NBA Signal + Intelligence Loop

The autonomous, never-stop loop that co-evolves prediction signals (ARM A) and deep
basketball intelligence atlases (ARM B) on the shared point-in-time store. Opus
orchestrates and reviews; Sonnet subagents implement every concrete signal and atlas
section. The loop runs indefinitely, shipping only what survives the honest 5-criterion
gate, and NEVER touches api/, the live server, the tunnel, data/live/, or data/lines/.

---

## Safety contract (read before EVERY iteration — hard stops, no exceptions)

| NEVER DO | Why |
|---|---|
| Edit, restart, or kill anything under `api/` | Live betting page + cloudflared tunnel on :8077 |
| Touch `data/live/` or `data/lines/` | Live stakes; corruption is real-money loss |
| Run `run.py`, `loop_processor.py`, or `uvicorn` | Would clobber live server process |
| Run the full test suite | Other agents mid-build; run only your own new file |
| Write outside your disjoint assignment | `src/loop/`, `signals/`, `intel/`, `scripts/loop/`, `tests/`, `.planning/loop/`, `.claude/commands/` |
| Skip `py_compile` before marking a file done | Syntax errors block the loop on next boot |
| Use CPU-only XGBoost or un-placed PyTorch | RTX 4060 local / RTX 3090 RunPod — GPU is 5-30x faster |
| Call any live API without `NBA_OFFLINE=1` | Breaks air-gap; all reads are from parquets |

---

## Model routing

| Work | Model | How |
|---|---|---|
| Orchestrate, plan, review diffs, judge verdicts, hard debugging | Opus | this session |
| Read ground truth to plan against | Opus | `Read` actual file sections, never a paraphrase |
| Wide sweep: "where is X and what uses it" | Sonnet Explore | `Agent(subagent_type="Explore")` |
| Implement signals, atlas sections, helpers, tests | Sonnet | `Agent(subagent_type="general-purpose", model="sonnet")` |
| Trivial status queries, file-exist checks | inline Bash | single command |

---

## GPU and efficiency requirements

All training must default to CUDA. Use these patterns exactly:

```python
# XGBoost (2.x)
import xgboost as xgb
_device = "cuda" if device in ("auto", "cuda") else "cpu"
params = {"device": _device, ...}  # NOT tree_method="gpu_hist"
try:
    model = xgb.train(params, dtrain)
except xgb.core.XGBoostError:
    params["device"] = "cpu"
    model = xgb.train(params, dtrain)

# PyTorch
import torch
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = MyModel().to(device)
```

CLI default: `--device auto` resolves to `"cuda"` first. Cache the point-in-time
feature matrix (store JSONL + atlas parquets) so iterative re-tests read from disk,
not NBA API. `NBA_OFFLINE=1` is set for every run.

---

## EACH ITERATION — run back-to-back until context is heavy

One iteration = one `run_iteration("both")` call to the orchestrator, which runs
ARM A (signals) and ARM B (intelligence) in sequence over the shared store.

### 1 — Boot check (single Bash call, stays in Opus)

```bash
cd C:\Users\neelj\nba-ai-system && python -c "
import sys, json, os
os.environ['NBA_OFFLINE']='1'
sys.path.insert(0,'.')
from src.loop.store import get_store
from src.loop import ledger
s = get_store()
stats = s.stats()
print('store:', stats)
tested = ledger.load_all() if hasattr(ledger,'load_all') else []
print('ledger entries:', len(tested) if hasattr(tested,'__len__') else '?')
"
```

Exit the loop only if a hard-stop signal is present:
- `data/loop_stop` file exists → reason="user_stop_file"
- `.bot_state/live_status.json` has `stop_requested: true` → reason="user_stop_flag"
- 3 consecutive iterations had 5+ errors each → reason="env_broken_needs_human"

There is no spend cap. GPU capacity is the goal; CPU idle is the waste.

### 2 — ARM A: signal hypothesis queue

The orchestrator calls `error_miner.mine(store, top_k=20)` automatically. Before
delegating an implementation task, Opus verifies the signal is not already in the
ledger with a non-DEFER verdict:

```bash
python -c "
import sys, os; os.environ['NBA_OFFLINE']='1'; sys.path.insert(0,'.')
from src.loop import ledger
print(ledger.already_tested('<signal_name>', kind='signal'))
"
```

The hypothesis queue is FDR-aware: only hypotheses with a plausible p-value path
(the signal can compute a per-row feature column) get gated. DEFER is requeued
(not ledgered) up to 3 times (orchestrator checkpoint tracks this).

### 3 — ARM B: atlas section build

For each undiscovered `intel/<entity>_<name>.py`, the orchestrator calls
`section.build(entity_id, as_of)` over every entity returned by `section.entities()`,
validates with `intel_validator.validate`, and persists via `profile_factory_bridge.register_section`.

A section is "discovered" once `intel/<name>.py` exists on disk and the class is
importable. Add new sections by creating the file; the orchestrator picks it up on
the next iteration with no registry edit.

### 4 — Build cycle: Opus plans → Sonnet executes

**4a — PLAN (Opus).** Before dispatching, read the relevant source files; never plan
off a Sonnet/Explore paraphrase for code you will review. For each candidate signal
or atlas section:

1. Read `src/loop/signal.py` and `src/loop/atlas.py` for the exact contract.
2. Read `src/loop/DESIGN.md` section 2 for agreed signatures.
3. Read the spec file: `.planning/loop/spec_features.md` (signals) or
   `.planning/loop/spec_intel_memory.md` (atlas sections).
4. Read any referenced parquet's schema via `pd.read_parquet(...).dtypes` (Bash).
5. Write a concrete spec: exact file, class name, `name`/`target`/`scope` attrs,
   `build()` logic sketch, `cv_fields()` reserved names, `feature_names()` output,
   edge cases, and the `py_compile` + unit-test command.

**4b — EXECUTE (Sonnet subagents — default parallel).**

- Each new `signals/<name>.py` or `intel/<entity>_<name>.py` is a disjoint file.
  Batch up to 8 non-overlapping assignments in ONE message.
- Each Sonnet prompt must include the spec plus:
  *"Set `NBA_OFFLINE=1`, `sys.path.insert(0,'.')`, `cd C:\Users\neelj\nba-ai-system`.
  Implement EXACTLY the agreed signature from DESIGN.md. Files <= 300 LOC, type hints,
  docstrings on public API. Run `python -m py_compile <your_file>` before reporting done.
  If the file is self-contained, also run your own unit test only. NEVER run the full
  test suite. NEVER touch api/, data/live/, data/lines/, or any existing file outside
  your assignment."*
- Collision guard for atlas sections with shared source parquets: assign unique
  entity-id ranges (or per-section files) to avoid concurrent write collisions —
  the parquet write is the critical section.

**4c — REVIEW (Opus, cheap).** Check:
- `py_compile` passed (if Sonnet skipped it, run it now)
- No import of `api.*`, no open of `data/live/*` or `data/lines/*`
- Signal's `build()` reads the store with `as_of=ctx.decision_time` (leak-safe)
- Atlas section's `build()` filters parquet rows to `game_date <= as_of`
- `cv_fields()` returns named slots with `value=None` (reserved, not filled)
- `emits` list matches the dict keys returned by `build()` (if dict-valued)
- New atlas section registered in `.planning/loop/atlas_registry.json` via bridge

### 5 — Gate a signal: the 5 honest criteria (ALL must pass to SHIP)

The gate is run by `gate.evaluate(signal, store=store, device=device)`. Review the
`GateResult` before accepting a SHIP verdict:

| Criterion | Must hold |
|---|---|
| Walk-forward (all folds) | `wf_all_improve=True` — EVERY fold's delta_mae < 0 |
| Null-shuffle control | `null_pass=True` — real delta beats shuffled-label distribution |
| Ablation vs FULL model | `ablation_pass=True` — marginal delta when added to the full model, not in isolation |
| Calibration / reliability | `calibration_ok=True` — reliability diagram is not systematically biased |
| CLV vs Pinnacle | `clv_pass=True` — positive closing-line value vs the sharpest line |

FDR guard: `benjamini_hochberg(p_values, q=0.10)` is recomputed across all ledger
entries each iteration. A signal is only wired if `fdr_pass=True` at the time of
shipping. The one-time held-out set is touched EXACTLY ONCE per loop lifetime
(tracked in `.planning/loop/orchestrator_checkpoint.json`).

VARIANCE_ONLY signals (improve interval width / Kelly sizing but not the point
estimate) are wired into the sigma/interval path only via `wiring.wire_variance_signal`.

### 6 — Ship a signal: wire + write-back

On SHIP, `wiring.ship_signal` does three things in order:

1. **Feature-set registration** — adds the signal's `feature_names()` to the model's
   feature list so the next retrain picks it up.
2. **GPU retrain** — calls `train_fn` (or the default prop-model trainer) with
   `device="cuda"` behind a regime gate. If the regime gate rejects (non-stationary
   data drift), log to ledger and abort the wire.
3. **Write-back** — `wiring.write_back_atlas_field(signal, store)` calls
   `store.write_signal_field(entity_type, entity_id, signal.name, as_of, value)`
   for each entity the signal produced a learned value for, so future signals and the
   intel-scanner can read the shipped signal's outputs as atlas sub-fields.

### 7 — Persist an atlas section: bridge + memory + indices

On validation pass, `profile_factory_bridge.register_section(section, artifacts, store)`:

1. Writes `data/cache/atlas_<entity>_<name>.parquet` (accumulate-don't-clobber:
   higher-confidence-OR-newer wins; no clobber of higher-conf existing rows).
2. Emits a `sec_<name>(pid, s) -> (data, prov)` function body and records it in
   `.planning/loop/atlas_registry.json` so `build_persistent_profiles.py` picks it
   up via the registry hook.
3. Writes to store: `store.write_atlas(entity_type, entity_id, section, as_of, data, prov)`.

Then `memory_writer.write_finding` writes/updates
`~/.claude/projects/C--Users-neelj/memory/project_atlas_<entity>_<name>.md`
(DEDUP by slug: sharpen existing note, never duplicate), appends ONE index line to
`MEMORY.md` under `## Recent feedback` (<=200 chars), and writes
`vault/Intelligence/<Name>_Atlas.md` (no-op if vault/ absent).

Finally, `scripts/loop/build_profile_indices.py` is re-run (idempotent) to
regenerate `PLAYER_INDEX.json` and `TEAM_INDEX.json` deterministically:

```bash
python scripts/loop/build_profile_indices.py
```

### 8 — Monitor drift and ledger

After each shipped signal, the orchestrator re-runs `ledger.apply_fdr()` across all
entries. Any previously-shipped signal whose `fdr_pass` flips to False at the new
BH threshold is flagged in the ledger with a supersession record (the ledger's
`supersedes` field). Wiring does NOT auto-unwire — Opus reviews and flags to
`human-todo.md` if manual intervention is needed.

Ledger path: `.planning/loop/ledger.jsonl` (one JSON object per line, append-only).

### 9 — End-of-turn rule (NEVER just stop)

Every turn that does ANY work MUST end with one of:

| Outcome | When | Required action |
|---|---|---|
| Continue same turn | Context light, queue has work | Loop to Step 1 immediately |
| Schedule next wake | Context heavy (>8 iterations or compaction fired) | `ScheduleWakeup(delaySeconds=120, prompt="/signal-loop", reason="continue — fresh context")` |
| Exit deliberately | Hard stop condition matched (Step 1) | Log reason to `.planning/loop/loop_exit.log`, write `phase="stopped"` to `.bot_state/live_status.json` |

A turn that finishes an iteration and just ends (no wake, no exit log) is a bug.

---

## Run command

```bash
cd C:\Users\neelj\nba-ai-system && \
  set NBA_OFFLINE=1 && \
  C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe \
    scripts/loop/run_loop.py --arm both --forever
```

Additional flags:
- `--arm signals` — ARM A only (signals, no atlas build this run)
- `--arm intel` — ARM B only (atlas sections, no signal gating)
- `--arm both` — default; runs both arms each iteration
- `--max-iters N` — stop after N iterations (smoke test: `--max-iters 1`)
- `--dry-run` — build + gate + validate but do NOT persist/wire (safe smoke mode)
- `--device cuda|cpu|auto` — GPU device selection (default: auto → cuda)

One-shot smoke test (dry-run, one iteration, validates imports and store):

```bash
cd C:\Users\neelj\nba-ai-system && NBA_OFFLINE=1 \
  C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe \
    scripts/loop/run_loop.py --max-iters 1 --dry-run
```

---

## Files this loop owns (disjoint write zones)

| Zone | What lives here |
|---|---|
| `src/loop/` | Contracts (DONE) + skeleton implementations (BUILD agents fill) |
| `signals/<name>.py` | Concrete `Signal` subclasses (20 planned) |
| `intel/<entity>_<name>.py` | Concrete `AtlasSection` subclasses (28 planned) |
| `scripts/loop/run_loop.py` | CLI entry → `Orchestrator.run` |
| `scripts/loop/build_profile_indices.py` | Regenerate PLAYER_INDEX / TEAM_INDEX |
| `tests/test_loop_*.py` | Per-module unit tests (run only your own) |
| `.planning/loop/` | DESIGN.md, spec_*.md, ledger.jsonl, atlas_registry.json, orchestrator_checkpoint.json, reports/ |
| `.claude/commands/signal-loop.md` | This file |

**Never write outside these zones.** In particular, never edit `api/`, `data/live/`,
`data/lines/`, `scripts/build_persistent_profiles.py` (extend via bridge, not directly),
`vault/` (memory_writer handles vault updates), or any existing `.bot_state/` file
(use `_state` helpers from `scripts/bot_guards/_state.py` for live_status.json).

---

## Reinforcement invariants (verify each iteration)

Before an iteration is considered complete, confirm all three reinforcement links are live:

1. **Signals read atlases.** Every new `Signal.build()` calls `self.read_atlas(entity, section, ctx.decision_time)` for at least one atlas section it declares in `reads_atlas`. An interaction feature (shot_profile.rim_freq x defensive_scheme.drop_rate) counts as two reads.

2. **Shipped signals write back.** Every SHIP verdict triggers `wiring.write_back_atlas_field`, which calls `store.write_signal_field` for each entity with a learned value. Verify the store stats show KIND_SIGNAL count increasing.

3. **Intel-scanner emits hypotheses.** `error_miner.intel_scan(buckets, store)` joins residual buckets x atlas sections. If a new atlas section was built this iteration, the next `mine()` call should surface at least one atlas-derived hypothesis.

If any of these links is broken, flag to `human-todo.md` as a reinforcement regression.
