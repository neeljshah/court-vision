# `kernel/` — module reference

Exhaustive, file-by-file reference for every module under `kernel/` (34 `.py` files, excluding
`__pycache__`, all read in full). See [README.md](README.md) first for the high-level summary
and the implementation-status table — this page is the detail behind that table.

---

## `kernel/paths.py` — repo-root resolution

- `repo_root() -> Path` — resolution order: `COURTVISION_ROOT` env var first, then walks
  `Path(__file__).resolve().parents` looking for any of `("CLAUDE.md", ".git", "pyproject.toml")`.
  Raises `RuntimeError` if no marker is found anywhere up the tree — fail-closed rather than
  silently returning a wrong root.

---

## `kernel/config/` — the `SportContext` seam (fully implemented)

### `context.py` — `SportContext`

A frozen dataclass a domain adapter constructs once at process start and threads explicitly
through every kernel call (constructor injection, no global mutable singleton, no import-time
side effects).

- **Mandatory fields:** `stats: SportStatRegistry`, `clock: GameClockConfig`,
  `roster: RosterConfig`, `game_state: GameStateConfig`, `pbp_mapper: PBPEventMapper`,
  `league_client: LeagueClient`, `entities: EntityRegistry`, `source_tiers: Mapping[str, int]`,
  `atlas_schema: AtlasSchema`.
- **Optional fields:** `court: Optional[CourtConfig] = None`, `speed: Optional[SpeedConfig] = None`,
  `dataset_builder: Optional[Any] = None`, `trainer_hook: Optional[Any] = None`,
  `artifact_root: Path = Path("data")`.
- Derived helpers: `sport_id` (delegates to `stats.sport_id`), `artifact_dir` (=
  `artifact_root / sport_id`), `has_court()`, `has_speed()`, `has_dataset_builder()`,
  `has_trainer_hook()`.
- **Dependency-rule invariant:** this module imports only `kernel.config.*` — never a literal
  `import domains` / `from domains`. Domain discovery is delegated to
  `kernel/config/registry.py::load_sport`, which uses `importlib.import_module` on a string.
- **Resolved:** the NBA domain package lives at `domains/basketball_nba/`, matching what
  `load_sport("basketball_nba")` expects (`domains/basketball_nba/config.py` sets
  `sport_id="basketball_nba"`). The package was renamed from `domains/nba/` in commit `b9c97a55`
  (2026-06-12); no naming mismatch remains.

### `stats.py` — `StatSpec` + `SportStatRegistry`

Replaces a hardcoded stat tuple that used to be duplicated across 30+ modules.

- `StatSpec` (frozen dataclass): `name, kind (count|continuous|binary|interval), display,
  sigma_default, priced=True, higher_is_better=True, settle, correlated_with,
  calibration_fallback_slope`. `__post_init__` raises `ValueError` on an invalid `kind`.
- `SportStatRegistry` (frozen dataclass): `sport_id, stats: Dict[str, StatSpec],
  box_score_mapping, score_stat, minutes_equiv="minutes"`. Methods: `target_names()`,
  `priced_order()`, `spec(name)` (raises `KeyError`), and the `loop_targets` property =
  `target_names() + ("minutes","total","winprob","usage","sigma")`.
- **Invariant:** insertion order of the `stats` dict is load-bearing — array-positional code
  (model pickle feature order, correlation matrices) depends on it.

### `clock.py` — `GameClockConfig`

Replaces hardcoded clock literals (`REG_GAME_LEN_SEC=2880`, `OT_PERIOD_LEN=300`, etc).

- Fields: `n_periods, period_len_sec, ot_len_sec, untimed=False, play_clock_sec=24,
  penalty_threshold=5, max_ot_periods=None`.
- Methods: `regulation_sec()`, `remaining_frac(period, period_clock_sec)` (ZeroDivision-safe,
  unit-index fallback when `untimed=True`, e.g. tennis), `snapshot_grid()` (e.g.
  `("endP1","endP2","endP3")` for NBA), `bucket_breakpoints()` (cut points for time-remaining
  bucketing; consumed by the not-yet-built `kernel/model_ops/ingame_sigma.py`).

### `roster.py` — `PositionSchema` + `RosterConfig`

- `PositionSchema`: `positions: Tuple[str,...]`, `archetypes: Dict`; `__contains__`, `index()`.
- `RosterConfig`: `on_field_count, roster_size, season_length_games, positions: PositionSchema,
  substitution_model="free" (free|platoon|limited|none), foul_out_limit=6, reach_ft=6.0`.
  `__post_init__` validates `substitution_model` membership, `on_field_count >= 1`,
  `roster_size >= on_field_count`, `season_length_games >= 1`, `reach_ft > 0` — all raise
  `ValueError`.

### `game_state.py` — `GameStateConfig`

- Fields: `blowout_margin, clutch_margin, clutch_remaining_sec, garbage_margin,
  competitive_margin, final_margin_sigma, winprob_promotion_period`, plus
  `legacy_overrides: Mapping[str,float]`. The `legacy_overrides` map is a deliberate honesty
  mechanism: where two legacy NBA modules historically disagreed on a threshold (e.g.
  blowout=15.0 in one module vs 18.0 in another), **both values are preserved verbatim**, keyed
  `"<module>.<name>"`, rather than silently unified into one "correct" number.
  `__post_init__` raises `ValueError` on any non-positive threshold.
- Methods: `is_blowout(margin)`, `is_clutch(margin, remaining_sec, period)`,
  `is_competitive(margin)`.

### `court.py` — `CourtConfig` (optional field)

- Fields: `surface_w, surface_h, unit (ft|yd|m), goal_x_left, goal_x_right, goal_y, key_zones: Dict,
  rectified_px=(940,500), fps_native=30.0, speed_tiers: Dict, three_pt_dist=0.0`.
- Methods: `area()`, `control_grid(cells_per_unit=0.5)`, `normalize_speed(px_per_frame, fps,
  px_per_unit) -> float` (fixes a historical bug where fps was hardcoded to 30 in two legacy `src/`
  spatial modules).

### `speed.py` — `SpeedConfig` (optional field)

- Fields: `video_fps, thresholds_ft_s: Dict, screen_dist_ft=0.0`.
- Methods: `per_frame(threshold_ft_s)` (raises `ZeroDivisionError` if `video_fps==0`),
  `per_frame_named(name)` (raises `KeyError` on an unknown name).

### `entities.py` — `EntityRegistry` (Protocol)

`@runtime_checkable`. Attribute `sport_id: str`; methods `resolve_team(token) -> str`,
`resolve_player(token) -> str`, `parse_game_id(game_id) -> dict` (must contain exactly
`"season"/"kind"/"seq"` keys), `season_of(d) -> str`, `entity_key(kind, ident) -> str`,
`book_aliases() -> Mapping[str,str]`.

- **Binding invariant, stated repeatedly in the docstring:** `resolve_team`, `resolve_player`,
  and `parse_game_id` **must raise** (`KeyError`/`ValueError`) on an unrecognized token — never
  guess or silently return a wrong id. Rationale: a silently-wrong id would corrupt signal
  attribution, walk-forward folds, and CLV records without any visible failure.

### `pbp.py` — `CanonicalEvent`, `CanonicalEventKind`, `PBPEventMapper`, `LeagueClient`

- `CanonicalEventKind` (enum): `SCORE, MISS, TURNOVER, PENALTY, SUBSTITUTION, PERIOD_START,
  PERIOD_END, STOPPAGE, POSSESSION_CHANGE, OTHER`.
- `CanonicalEvent` (frozen dataclass): `kind, ts_game_sec, period, side=None, points=0,
  actor_id=None, detail: Dict[str,Any] = {}`. **Invariant:** `detail` is an opaque payload —
  kernel code must never read or branch on it; only adapters/adapter-level tests may inspect it.
- `PBPEventMapper` (Protocol, runtime-checkable): `to_canonical(raw_event)`, `iter_game(game_id)`,
  `possession_side(event)`.
- `LeagueClient` (Protocol, runtime-checkable): `get_schedule`, `get_box_score`, `get_pbp`,
  `get_roster`, `get_player_gamelog`, `get_availability`.

### `atlas_schema.py` — `AtlasSchema`

- Fields: `sport_id, player_sections=(), team_sections=(), entity_frontmatter: Mapping={},
  dim_to_section: Mapping={}`. Methods: `player_section_count` / `team_section_count`,
  `resolve_section(dim_key)`, `all_sections()`. An empty instance (`player_sections=()`,
  `team_sections=()`) is explicitly documented as a valid launch state for a new sport.

### `registry.py` — sport registry + `load_sport`

The only place in `kernel/` that dynamically discovers a domain package, via string-based
`importlib.import_module`, never a literal import.

- `DEFAULT_SPORT_ID = "basketball_nba"`.
- `register_sport(ctx) -> None` (idempotent via `setdefault`).
- `get_sport(sport_id=None) -> SportContext` — resolution order: explicit arg ->
  `COURTVISION_SPORT` env var -> `DEFAULT_SPORT_ID`; raises `KeyError` (listing registered
  sports) if not found.
- `load_sport(sport_id) -> SportContext` — `importlib.import_module(f"domains.{sport_id}.config")`,
  expects module attribute `SPORT_CONTEXT`; raises `ValueError` on import failure or wrong type,
  `KeyError` if the attribute is missing.
- `list_sports()`, `unregister_sport()` (test-only, per docstring).

---

## `kernel/testing/` — conformance + regression tooling (implemented)

### `conformance.py` — `check_sport_context()`

The mechanical gate that enforces the `SportContext` seam.

- `check_sport_context(ctx) -> List[str]` — returns human-readable violation strings; empty list
  means conformant. Checks, in order: (1) `stats` valid with non-empty `target_names()`,
  `loop_targets` tail equal to `("minutes","total","winprob","usage","sigma")`,
  `priced_order() ⊆ target_names()`, non-empty `sport_id`; (2) `clock` valid, `regulation_sec() > 0`
  unless `untimed=True`; (3) `roster` valid, `on_field_count >= 1`,
  `roster_size >= on_field_count`; (4) `game_state` has all 7 required attributes; (5-7)
  `entities` / `pbp_mapper` / `league_client` each structurally satisfy their Protocol; (8)
  `atlas_schema` is a valid instance; (9-10) `court` / `speed` are `None` or the correct type.
- `assert_sport_context_conformant(ctx)` — raises `AssertionError` bullet-listing every
  violation.
- **Invariant:** imports only `kernel.config.*` + stdlib — no `domains` import.

### `domain_conformance_kit.py` — `DomainConformanceKit`

Bundles `check_sport_context` plus five more targeted checks into one runnable scorecard.
Methods each returning a `Result(status, message)`: `check_context()`, `check_protocols()`
(per-protocol granular messages), `check_stat_ordering()`, `check_clock()`, `check_atlas()`, and
`check_gate_wiring()` — which **always returns `SKIP`**, never `PASS`, because it needs a real
dataset builder + golden snapshot to run hermetically; a deliberate honesty mechanism, not an
oversight. `run_all()` -> `Dict[str, Result]`; `summary(results)` -> printable scorecard.
`CheckStatus` enum: `PASS`, `SKIP`, `FAIL`.

### `fixtures.py` — toy `SportContext` factories

`make_toyball_context()` and `make_toyball_untimed_context()` build fully-conformant toy
`SportContext` instances (a timed 2-stat sport and an untimed 9-period variant) so kernel tests
never need real domain code. Backed by minimal but protocol-satisfying toy implementations of
`EntityRegistry`, `PBPEventMapper`, `LeagueClient` (the toy entity registry still raises
`KeyError` on an unknown team/player, honoring the contract).

### `golden.py` — exact-equality golden artifacts

Byte-identical regression comparison. `save_golden` (numpy via `np.save`, else JSON),
`load_golden`, `compare_golden(...) -> (bool, str)` — **exact** equality only (`np.array_equal`,
never `np.allclose`); on mismatch the message includes the first differing index.
`write_manifest` / `verify_manifest` — a SHA-256 manifest over an entire golden directory. The
module docstring states approximate comparisons are *deliberately absent*: this exists to catch
silent numeric drift, not to tolerate it.

### `invariants.py` — sport-blind invariant checkers

Take plain accessor callables (work on dicts, dataclasses, anything). `fold_scores`,
`check_truncation_invariance` (folding the full event log reproduces the declared final score —
the general mechanism behind every sport's "truncation-invariance" leak test),
`check_prefix_running_scores`, `check_registry_order`, `check_frozen` (verifies a dataclass
actually raises `FrozenInstanceError` on mutation), `check_monotonic_nonincreasing`.

---

## `kernel/validation/proof_metrics.py` — sport-blind statistical primitives (implemented)

Pure functions, imports only stdlib + numpy + sklearn (no `src`/`domains`/`scripts`).

- `brier(probs, outcomes) -> float` — mean squared error between forecast and binary outcome.
- `ece(probs, outcomes, bins=10) -> float` — expected calibration error, frequency-weighted.
- `reliability_slope(probs, outcomes, bins=10) -> float` — OLS slope of the reliability diagram
  (~1.0 well-calibrated, <1 overconfident, >1 underconfident; `nan` if <2 populated bins).
- `isotonic_calibrate(train_p, train_y, eval_p) -> np.ndarray` — fits `IsotonicRegression` on
  train, transforms held-out eval. The leak-free calibration mechanism.
- `devig2(price_a, price_b) -> (float, float)` — two-sided decimal-odds devig.
- `clv_sign_invariants(...)` — **explicitly a plumbing/wiring-correctness check, not an edge
  claim** (stated in both module and function docstrings). Checks that betting the close against
  itself yields CLV ≡ 0 and that two-sided CLV is anti-symmetric after devig. Guards a documented
  historical "CLV recorded backwards" bug class.

---

## Reserved-namespace stubs (docstring only, no implementation)

Each is a single-line `__init__.py` naming a future purpose. Listed with what the docstring
claims and where the equivalent logic actually lives today:

| Module | Docstring claim | Where the logic actually lives today |
|---|---|---|
| `kernel/brain/__init__.py` | "signal discovery and hypothesis management" | `src/loop/`, `src/brain/` (legacy, NBA-only) |
| `kernel/calibration/__init__.py` | "probability and output calibration" | `kernel/validation/proof_metrics.py` |
| `kernel/data_infra/__init__.py` | "data ingestion, caching, and registry" | `domains/<sport>/ingest_*.py` (per-adapter) |
| `kernel/decision/__init__.py` | "decision engine and market interface" | `scripts/platformkit/execution/`, `econ/`, `paper/` |
| `kernel/decision/exchange/__init__.py` | "exchange adapters" | `scripts/platformkit/pm_trading/` |
| `kernel/decision/venues/__init__.py` | "venue/book adapters" | `scripts/platformkit/venue_history/` |
| `kernel/fusion/__init__.py` | "signal and model fusion layer" | not yet built anywhere |
| `kernel/loop/__init__.py` | "self-improving loop orchestration" | `src/loop/` + `scripts/platformkit/autoloop/` |
| `kernel/model_ops/__init__.py` | "model training, gating, and lifecycle management" | not yet built (referenced by `kernel/config/clock.py`) |
| `kernel/sim_framework/__init__.py` | "domain-agnostic simulation framework" | per-adapter, e.g. `domains/tennis/predictor.py` |
| `kernel/sim_framework/joint/__init__.py` | "joint simulation and correlation pricing" | per-adapter (same as above) |
| `kernel/spatial/__init__.py` | "spatial and coordinate utilities" | not yet built (referenced by `court.py` / `speed.py`) |

None of these should be imported expecting real functionality today. If you're extending the
platform and need one of these concerns, either extend the adapter directly (as
`domains/tennis/predictor.py` does today) or start the extraction into the kernel namespace —
either way, update this table.

---

## Kernel-purity check (reproducible)

```
grep -rnE '^\s*(import|from)\s+(src|domains|api|scripts)(\.|$| )' kernel/ --include='*.py'
# -> no matches, as of this writing
```

Zero violations found: no file under `kernel/` contains a literal `import`/`from` of `src`,
`domains`, `api`, or `scripts`.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
