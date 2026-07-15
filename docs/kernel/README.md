# `kernel/` — the sport-blind machinery

`kernel/` is where the platform's sport-agnostic contract lives: the typed configuration every
domain adapter must supply (`SportContext`), the mechanical conformance checks that validate it,
and the pure statistical primitives (Brier, ECE, isotonic calibration, Shin devig) used across
sports. The idea, laid out in full in **[../PLATFORM.md](../PLATFORM.md)**, is that this
directory holds the "hard, compounding" work once, and every sport (`domains/<sport>/`) reuses
it instead of re-deriving it.

This page is the honest, code-verified reference: what's actually implemented here today, file
by file, versus what's a reserved namespace waiting to be filled. For the full new-sport
contract narrative (the three seams, the parity matrix, the 9-step playbook) read
[../PLATFORM.md](../PLATFORM.md) first — this page assumes that context and goes module by
module. For the finer-grained per-file reference, see
[module-reference.md](module-reference.md).

---

## Implementation status

Reading all 34 `.py` files under `kernel/` (excluding `__pycache__`) shows a clean split: two
subtrees are fully implemented, and the rest are one-line docstring stubs reserving a namespace
for machinery that currently still lives elsewhere in the repo.

| Subtree | Status | What's actually there |
|---|---|---|
| `kernel/config/` | **Implemented** | The full `SportContext` seam — 12 files, 14 typed sub-configs (9 mandatory + 5 optional) |
| `kernel/testing/` | **Implemented** | Conformance checker, conformance kit, fixtures, golden-file comparator, sport-blind invariant checkers |
| `kernel/validation/proof_metrics.py` | **Implemented** | Brier, ECE, reliability slope, isotonic calibration, two-sided devig, CLV sign-invariant checks |
| `kernel/paths.py` | **Implemented** | Repo-root resolution (marker-file walk, fail-closed) |
| `kernel/loop/` | **Stub** (docstring only) | Discovery loop actually runs today from `src/loop/` (legacy, NBA-only, human-gated) + `scripts/platformkit/autoloop/` (cross-sport scheduler) |
| `kernel/sim_framework/` (+ `joint/`) | **Stub** (docstring only) | Monte-Carlo / `JointDistribution` logic actually runs today per-adapter, e.g. `domains/tennis/predictor.py::to_jd()` |
| `kernel/decision/` (+ `exchange/`, `venues/`) | **Stub** (docstring only) | Devig / sizing / venue logic runs today from `scripts/platformkit/` (`econ/`, `paper/`, `execution/`) |
| `kernel/brain/` | **Stub** (docstring only) | Agent-orchestration concern; not yet extracted from `src/` |
| `kernel/calibration/` | **Stub** (docstring only) | Calibration math currently lives in `kernel/validation/proof_metrics.py` instead |
| `kernel/fusion/` | **Stub** (docstring only) | Signal/stat fusion concern; not yet built anywhere |
| `kernel/spatial/` | **Stub** (docstring only) | Referenced by `kernel/config/court.py` and `speed.py` docstrings as a future consumer; not yet built |
| `kernel/data_infra/` | **Stub** (docstring only) | Ingestion/caching/registry concern; lives per-adapter (`domains/<sport>/ingest_*.py`) today |
| `kernel/model_ops/` | **Stub** (docstring only) | Model lifecycle concern; referenced by `kernel/config/clock.py` as a future consumer, not yet built |

This is consistent with — and gives concrete file-level evidence for — the status line
[../PLATFORM.md](../PLATFORM.md) reports from its own build harness. `kernel/config` and
`kernel/testing` are the tasks that landed; the rest of the namespace is reserved for tasks still
`todo`/`in_progress`. If you're reading `kernel/`'s directory listing or `../PLATFORM.md`'s
architecture diagram and assuming `kernel/loop/` or `kernel/sim_framework/` contain working code,
they do not yet — check this table first.

---

## What's real: the `SportContext` seam (`kernel/config/`)

Every domain adapter constructs one `SportContext` (`kernel/config/context.py`, a frozen
dataclass) at process start and threads it explicitly through the rest of the pipeline — no
global mutable singleton, no import-time side effects. It aggregates 14 typed sub-configs: 9
mandatory and 5 optional.

| Field | Type | Module | What it captures |
|---|---|---|---|
| `stats` | `SportStatRegistry` | `kernel/config/stats.py` | Every scoring/prop stat this sport tracks, `target_names()`, `priced_order()`, `loop_targets` |
| `clock` | `GameClockConfig` | `kernel/config/clock.py` | Periods, period length, untimed-sport support (tennis), snapshot grid (e.g. `endP1/endP2/endP3`) |
| `roster` | `RosterConfig` | `kernel/config/roster.py` | On-field count, roster size, substitution model, foul-out limit |
| `game_state` | `GameStateConfig` | `kernel/config/game_state.py` | Blowout/clutch/garbage-time margins, with a `legacy_overrides` map that preserves disagreeing historical NBA threshold values verbatim rather than silently unifying them |
| `pbp_mapper` | `PBPEventMapper` (Protocol) | `kernel/config/pbp.py` | Raw play-by-play -> `CanonicalEvent` (a 10-kind enum: SCORE, MISS, TURNOVER, ...) |
| `league_client` | `LeagueClient` (Protocol) | `kernel/config/pbp.py` | Schedule / box score / PBP / roster / gamelog / availability fetchers |
| `entities` | `EntityRegistry` (Protocol) | `kernel/config/entities.py` | Team/player token resolution — **must raise**, never guess, on an unrecognized token |
| `source_tiers` | `Mapping[str, int]` | `kernel/config/context.py` | Per-source trust ranking used to arbitrate conflicting feeds |
| `atlas_schema` | `AtlasSchema` | `kernel/config/atlas_schema.py` | Player/team intelligence-atlas section names (empty is a valid launch state for a new sport) |
| `court` / `speed` | `CourtConfig` / `SpeedConfig` (optional) | `kernel/config/court.py`, `speed.py` | Surface geometry and speed-normalization, only for sports with spatial tracking |
| `dataset_builder` / `trainer_hook` (optional) | `Any` | `kernel/config/context.py` | Reserved hooks for sport-specific dataset construction and training, unused by any adapter yet |
| `artifact_root` (optional) | `Path` | `kernel/config/context.py` | Root directory for this sport's model/data artifacts, defaults to `data` |

`kernel/config/registry.py` is the process-global `{sport_id: SportContext}` store.
`load_sport(sport_id)` dynamically imports `domains.<sport_id>.config` via `importlib` (a
runtime string, never a literal `import domains...` statement) and reads its `SPORT_CONTEXT`
attribute — this is *why* `kernel/config/context.py` itself can stay import-clean of `domains`
and pass the kernel-purity guard (below). `domains/basketball_nba/config.py` registers
`sport_id="basketball_nba"` and exports `SPORT_CONTEXT`, matching what `load_sport("basketball_nba")`
looks for — no naming mismatch exists in the current tree (stale docstrings in `context.py` and
`registry.py` still describe an older `domains/nba/` skeleton that no longer exists; those
docstrings are a separate, smaller doc-drift item outside this page's scope).

**Mechanical validation, not convention.** `kernel/testing/conformance.py::check_sport_context(ctx)`
returns a list of human-readable violation strings — empty means conformant — checking every one
of the 9 fields. `kernel/testing/domain_conformance_kit.py` wraps this into a runnable
PASS/SKIP/FAIL scorecard with more granular per-check messages; its `check_gate_wiring()`
**always returns SKIP**, on principle — it can't run hermetically (it needs a real dataset +
golden snapshot), so it deliberately never fakes a pass.

## What's real: the testing/validation primitives

- **`kernel/testing/golden.py`** — exact-equality (never approximate) regression comparison for
  catching silent numeric drift across a refactor, plus a SHA-256 manifest over a whole golden
  directory.
- **`kernel/testing/invariants.py`** — sport-blind checkers that take plain accessor callables:
  `check_truncation_invariance` (folding the full event log reproduces the declared final score —
  the machinery behind the "truncation-invariance" leak tests), `check_prefix_running_scores`,
  `check_frozen`, `check_monotonic_nonincreasing`.
- **`kernel/testing/fixtures.py`** — `make_toyball_context()` / `make_toyball_untimed_context()`,
  zero-boilerplate fully-conformant toy `SportContext` instances so kernel tests never touch real
  domain code.
- **`kernel/validation/proof_metrics.py`** — the actual math behind every "leak-free, calibrated"
  claim: `brier()`, `ece()`, `reliability_slope()`, `isotonic_calibrate()` (fit on train,
  transform on held-out eval — the leak-free calibration mechanism), `devig2()`, and
  `clv_sign_invariants()` — explicitly labeled a *plumbing correctness check, not an edge claim*.
- **`kernel/paths.py::repo_root()`** — the single authority for locating the repo root (env var
  first, then a marker-file walk up the tree); raises rather than returning a wrong root.

---

## The kernel-purity invariant — verified

[../PLATFORM.md](../PLATFORM.md) states that `kernel/` never imports `src`, `domains`, `api`, or
`scripts`, enforced by an AST-only guard (`scripts/platformkit/check_import_contract.py`). A
direct regex sweep of every file under `kernel/` for
`^\s*(import|from)\s+(src|domains|api|scripts)(\.|$| )` found **zero matches** — the invariant
holds today. The only cross-boundary discovery mechanism is
`kernel/config/registry.py::load_sport`, which resolves a domain package through
`importlib.import_module(f"domains.{sport_id}.config")` using a runtime string.

---

*See [module-reference.md](module-reference.md) for the exhaustive per-file reference. See
[../architecture/system-overview.md](../architecture/system-overview.md) for how the kernel fits
into the whole funnel, and [../PLATFORM.md](../PLATFORM.md) for the full adapter contract.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
