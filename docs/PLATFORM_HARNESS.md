# The Machine That Builds the Machine

`scripts/platform_harness/` is the autonomous build orchestrator: it turns a
1,500-line task backlog into a running loop that probes state, plans a wave
of parallel-safe work, spawns coding agents, runs gates, and merges -- with
no human required to click "continue." This doc describes the loop, who
decides what, the gate tiers that keep a bad diff from ever landing, and the
program's current honest status (numbers pulled from a live run of
`build_status.py`, not typed by hand).

Source: `scripts/platform_harness/{build_status,backlog,backlog_lint,waves,
gates,harness_state,rollback,stop_window,game_day}.py`,
`.planning/platform/BUILD_BACKLOG.md`, `tests/platform/test_g1_id_aware.py`,
`scripts/platformkit/capture_pytest_baseline.py`. See also
[docs/PLATFORM.md](PLATFORM.md) for the kernel/adapter architecture this
harness builds toward, and [docs/DAEMONS.md](DAEMONS.md) for the always-on
runtime fleet it is separate from (the harness builds code; the daemons run
it).

---

## The loop: probe -> adjudicate -> plan wave -> spec -> spawn -> review -> gate -> merge

**Probe.** `build_status.py` is the cheap, cold-start-safe step 1: it prints
the entire resume picture in <=20 grep-able lines with zero side effects --
program name, phase cursor, task counts by status, the active phase, the
ready set, the in-flight wave, `stop_requested`, and open/answered human
gates. Every wake starts here so a fresh session (or a fresh Claude with no
memory of the last one) knows exactly where the program stands before
touching anything.

**Adjudicate.** Open human-gate items in `.planning/platform/human-gates.md`
are parsed by `human_gate_counts()` (block-scanned on `^## \[` headings,
`STATUS:`/`BLOCKING:` fields extracted per block). A gate marked
`BLOCKING: yes` and still `STATUS: open` halts new work in that lane; per
[CLAUDE.md](../CLAUDE.md)'s autonomous-build directive, these are
Fable-adjudicated rather than left waiting on a human -- the loop never
blocks indefinitely on a question it can answer itself using the same
judgment a human operator would apply.

**Plan wave.** `waves.plan_wave()` takes `backlog.ready_set()` (tasks whose
`depends_on` are satisfied and whose `phase` is eligible -- see below) and
greedily builds the next batch whose `files` lists are **pairwise
disjoint**, so two agents writing to the same file in the same wave is
mechanically impossible, never a merge-time surprise. A handful of
mechanisms shape the batch:

- `HOT_FILES` (e.g. `api/main.py`, `CLAUDE.md`, `database/schema.sql`,
  `requirements.txt`, `src/prediction/betting_portfolio.py`) -- listing any
  of these forces the task **serial** (solo wave, cap 1).
- `is_serial()` also forces solo for `size == "L"`, `owner_model == "opus"`,
  or `change_kind == "ops"`.
- `cap_for()` sizes the rest of the wave: 6 for `change_kind == "move"`, 8
  otherwise.
- `game_day_eligible()` is a conservative filter for landing work on an NBA
  game day: excludes `move`, anything serial, and any file under `src/`,
  `api/`, or containing `loop` in its path -- only doc/test/verify/new-under-
  kernel-or-tests changes are allowed to land while a real slate is live.

**Spec.** Each task is one YAML-fenced block in
`.planning/platform/BUILD_BACKLOG.md`, the *only* file `backlog.py` parses.
A real, low-risk example (`P0-E-001`):

```yaml
id: P0-E-001
title: Register the 10 CV_CFG_* flags, default-OFF, in src/brain/flags.py
phase: 0   epic: P0-E   depends_on: [P0-D-017]   size: S   parallel_group: p0e   owner_model: sonnet   review: opus
change_kind: parameterize
files: [src/brain/flags.py, tests/platform/test_cfg_flags.py]
do: CV_CFG_STATS, CV_CFG_PBP, CV_CFG_COURT, CV_CFG_CLOCK, CV_CFG_LEAGUE_CLIENT, CV_CFG_ROSTER, CV_CFG_SPEED,
    CV_CFG_GAMESTATE, CV_CFG_ENTITIES, CV_CFG_ATLAS -- each default OFF, flag_allowed_on=False until its recorded
    gate verdict; gate text per EXTRACTION sec 2.1.3: "byte-identical fixture slate ON==OFF, pytest green, loop
    dry-run green". Namespace per MASTER_PLAN R9 (no CV_KERNEL_*; CV_DOMAIN_<SPORT> reserved for sport enablement).
done_criteria: tests assert all 10 registered, all OFF, unknown-flag lookup still raises; GATES (the registration
    is a registry-only diff -- blessed non-violating per R9 -- but must still be byte-identical: G2 green).
```

The shape is deliberately flat and machine-parseable: `id` is
`<TRACK>-<EPIC>-<NNN>`, stable forever, never renumbered; `phase` maps to
the roadmap phase (`0`-`9`, plus `N` for the NBA-completeness track and `M`
for maintenance -- both run continuously rather than phase-gated);
`depends_on` accepts task ids, epic ids (meaning "all of that epic's tasks
done"), or a range like `X-P1-001..016`; `owner_model` picks the coding
agent tier (`sonnet` by default); `review` picks the reviewer (`auto` or
`opus` for anything higher-stakes); `size` feeds `waves.is_serial()`.
`backlog_lint.py` runs three independent passes over every block before any
of this is trusted: schema (required fields present, `depends_on` resolves),
honest-edge (no task `do`/`done_criteria`/`title` claims a betting edge
exists, is proven, or is profitable -- the same discipline as
[the no-edge-claims rule](../.claude/rules/no-edge-claims.md), enforced at
the planning layer, not just at review time), and file-collision (tasks
sharing a `parallel_group` that also share a file path must serialize, and
lint catches that cheaply before the harness would catch it at wave time).

**Spawn coders.** A wave's tasks are handed to parallel Sonnet coding agents,
one per task, each scoped to exactly the `files` its spec declares.

**Review.** Per-task review runs at the level the spec's `review` field
names -- `auto` for routine changes, an Opus reviewer for anything
higher-stakes (kernel-touching, `size: L`, or explicitly flagged). The
orchestrator itself is Opus-tier: it plans waves, adjudicates human-gate
proxies, and reviews merge-worthiness; Sonnet agents write the code; a
faster Explore/Haiku tier handles the broad searches (finding files, sweeping
for a pattern) that don't need judgment.

**Gate.** Every task/wave/phase runs through `gates.run_tier()` before it can
merge -- the tiers are described in full below.

**Merge.** A passing gate advances `harness_state` (`build_state.json`):
task status flips to `done`, counters bump, the wave closes, and
`build_status.py`'s next probe reflects the new picture. Nothing here pushes
to `origin` -- see Invariants.

---

## Model routing

| Role | Model | Job |
|---|---|---|
| Orchestrator | Opus | Plans waves, reviews merge-worthiness, holds the "would a human approve this" bar |
| Decision-maker | Fable | Adjudicates human-gates / `review:human` / for-review items as a human proxy so the loop never idles on a question it can answer with the same judgment a human operator would apply |
| Coder | Sonnet (2-3x parallel) | Writes the actual diff for one task, scoped to its declared `files` |
| Search | Explore / Haiku | Broad, judgment-free sweeps -- locating files, grepping for a symbol, enumerating a pattern -- kept off the more expensive tiers |

`owner_model` in a task spec can override the coder tier (`opus` also forces
the task serial via `waves.is_serial()`, since a single higher-stakes change
should not share a wave with anything else).

---

## Gate tiers: task / wave / phase

`gates.py`'s cardinal rule, stated in its own docstring: **"absent
script/baseline -> SKIP, never FAIL."** In H0 (bootstrap) almost every gate
legitimately skips because the script it depends on doesn't exist yet -- a
harness that FAILed on a missing prerequisite before it had built that
prerequisite would deadlock itself.

**Task tier.** Runs `PROTECTED_SCAN` first -- a fixed list of files
(`src/prediction/betting_portfolio.py`, `database/schema.sql`, `CLAUDE.md`,
`requirements.txt`, `api/templates/`, `data/registry/`, `.planning/loop/`,
and more) that must route to human review rather than auto-merge. A hit here
is an immediate task-tier FAIL, no further gates run. Otherwise: an
import-contract check if any `kernel/` file is touched, plus a
**blast-radius-scoped** G1 (targeted pytest for the files in scope, via
`select_tests.select()`) bracketed by a hermeticity check.

**Wave tier.** Never runs the full suite -- only the scoped G1 for the
wave's combined file set, `G5` (shim integrity), `G4` (API boot test), and
the import contract, each independently SKIP-safe. If `select_tests`
decides the change is too broad to scope safely, it returns sentinel `"ALL"`
and the gate escalates to "this belongs at phase tier" rather than silently
running an unscoped (and much slower) suite mid-wave.

**Phase tier.** The only tier that runs the **full, id-aware G1** -- this is
the byte-identical migration contract in practice: `g1(baseline_required=True)`
plus `G2` (fixture-slate byte-identical), `G3` (skipped in H0, loop-adjacent
only), `G4`, `G5`.

### The id-aware G1 gate (P0-H-005)

G1 used to compare only pass/fail **counts** against a frozen baseline -- a
brittle contract: a single new failure could be masked by an unrelated new
pass elsewhere, and a flaky pre-existing failure had no way to be excluded
from a fresh regression. `capture_pytest_baseline.py` fixed this by parsing
junit-xml into **per-test node ids** (`classname::name`) rather than
aggregate counts, and freezing a baseline of `failed_ids` / `error_ids` as
JSON rather than a `k=v` count file. `gates.g1()` now compares the *set* of
failing/error ids from the current run against that frozen set: any id
**not** in the frozen baseline is a genuinely new regression and fails the
gate; ids that were already failing before this change (the "frozen
excluded" count reported in the verdict) don't block a phase that didn't
touch them. A legacy count-format baseline (`_g1_legacy_counts`) is still
honored for backward compatibility, but the id-aware path is what every new
baseline records. Re-baselining is an explicit phase-boundary action, never
automatic -- `test_g1_id_aware.py` proves the comparison logic entirely on
synthetic junit fixtures with `run_pytest` monkeypatched, so the id-aware
gate itself is tested without ever invoking the real 1,500+ file suite.

### Hermeticity (P0-H-004)

Every gate run that invokes pytest snapshots `git status --porcelain` before
and after. Any path added or removed by the run itself (a test writing
outside its own tmp dir, a fixture leaking a file) is a hermeticity FAIL,
reported with the exact offending paths and appended to the ledger --
report-only, never auto-reverted. `HERMETICITY_ALLOWLIST` starts empty on
purpose: a legitimate build artifact should be `.gitignore`d, not
allowlisted around.

---

## Invariants

- **Never pushes to public `origin`.** `scripts/platformkit/check_no_public_push.py`
  is designed to run as a git pre-push hook and block pushes to `origin`
  while any phase is open in `build_state.json`, but it is not yet installed
  as `.git/hooks/pre-push` -- wiring it is a pending backlog item
  (`.planning/platform/build_state.json`). Until installed, the guard is
  enforced by the bot never pushing during open phases; all harness work is
  local commits only.
- **Never flips a flag ON.** Every new capability (`CV_CFG_*`, `CV_DOMAIN_*`)
  registers default-OFF; a task's `done_criteria` explicitly gates the
  ON-path behind its own recorded verdict.
- **Never writes `data/registry/`** except through the explicit,
  dry-run-by-default `stop_window.py` (STOP-window tool, EXECUTION_HARNESS
  sec 6.5) -- everything else treats that directory as read-only, and
  `PROTECTED_SCAN` blocks any task-tier diff that touches it directly.
- **Honest REJECTs are recorded, not hidden.** `backlog_lint.py`'s
  honest-edge pass rejects any task language claiming a proven or existing
  betting edge; the wider platform's REJECT ledger (see
  [docs/PLATFORM_TOOLING.md](PLATFORM_TOOLING.md)) is the same discipline
  applied to signal candidates, not just backlog prose.
- **Rollback is phase-scoped and reversible, never silent.** Every phase
  opens with `git tag platform-phase<N>-pre`. `rollback.py` is dry-run by
  default (`--execute` is the explicit opt-in); a real rollback is
  `git reset --hard platform-phase<N>-pre`, marks the phase and every one of
  its tasks `rolled_back` in `harness_state`, appends a ledger event, and
  adds a `human-gates.md` entry -- `data/registry/` and the vault are never
  touched by a rollback. A rolled-back phase is skipped by the next pick
  until a human (or Fable, per the adjudication rule above) explicitly
  re-opens it.
- **Per-file tests only, everywhere except the phase-tier G1.** The same
  house rule that governs manual work in this repo
  (`.claude/rules/bash-cwd-prefix.md`) is load-bearing here too: task- and
  wave-tier gates always scope pytest to the blast radius; only the
  phase-tier gate is allowed to run the full suite, and it budgets up to 8
  hours (`CV_G1_TIMEOUT_S`, default 28800s) for that.

---

## Current program status

Live output of `python scripts/platform_harness/build_status.py`:

```
program=platform_v1  phase_cursor=0
tasks  total=83  done=53  in_progress=0  review=0  blocked=0  rejected=0  todo/ready=30
percent_done=63.9%
active_phase=0
ready=3   (next3: P0-A-002, P0-H-005, N-HYG-002)
blocked=0
human_gates  open_blocking=0  open_total=3   answered=7
in_flight_wave=none
stop_requested=False
```

83 backlog tasks total, 53 done (63.9%), zero blocked and zero rejected at
task granularity, 3 ready to pick up next, no wave currently in flight, and
no blocking human gate open -- the loop is idle-but-ready, not stuck. `N-`
and `M-` prefixed tasks (the NBA-completeness and maintenance tracks) run
continuously alongside whatever phase is active; everything else is gated to
`active_phase` (`0` right now) until that phase's tasks are done.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
