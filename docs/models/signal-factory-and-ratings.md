# Signal Factory, Signal Registry, and Role-Aware Ratings

This page covers the two layers that sit underneath every per-sport model: the **signal
registry** (the catalog of every named signal the system can compute, one row per
*definition*, not per entity) and the **role-aware rating builders** (the "2K-style"
player/team overalls that several sim engines and predictors consume as inputs).

Everything here is calibration/scouting infrastructure. Nothing on this page claims a
betting edge; see [`../PLATFORM.md`](../PLATFORM.md) and
[`calibration-and-validation.md`](calibration-and-validation.md) for the honesty framing
that governs every number produced downstream of these builders.

---

## The signal registry — spine of the signal layer

**Builder:** [`scripts/signals/build_signal_registry.py`](../../scripts/signals/build_signal_registry.py)
**Outputs:**
- `data/registry/signal_registry.parquet` — machine-readable catalog (gitignored; not committed)
- `data/registry/SIGNAL_REGISTRY.md` — human-readable index, regenerated from the parquet

Run with `python scripts/signals/build_signal_registry.py`. It is idempotent — re-running
regenerates both outputs from the `DEFS` dict hardcoded in the builder.

### Schema (one row per signal *definition*)

| Column | Type | Meaning |
|---|---|---|
| `signal_id` | str | `"{entity}.{domain}.{suffix}"`, e.g. `player.scoring.ppp_by_zone` |
| `entity` | str | One of `player`, `team`, `lineup` |
| `domain` | str | Sub-category within the entity, e.g. `scoring`, `defense`, `correlation` |
| `granularity` | str | Pipe-joined axis codes the signal expands across (see below) |
| `source` | str | Provenance note (currently `"see formula"` — the formula column documents derivation) |
| `formula` | str | Human-readable definition of the computation |
| `leak_rule` | str | How the signal must be windowed to stay leak-free: `shift1` (lag one game), `season-agg` (season-to-date aggregate), `as-of-date` (point-in-time snapshot) |
| `consumer` | str | Who reads this signal: `scouting` (display-only, vault notes), `ingame` (live conditioning), `corr-model` (correlation/joint-distribution input), `point-model-candidate` (a walk-forward-gated feature candidate for a point/possession model) |
| `ev_tier` | str | `A` = expected to move its consumer, `B` = plausible, `C` = scouting-only (no overfit risk — display only, never fed to a model) |
| `coverage_pct` | float\|null | Data-coverage fraction once measured (null until backfilled) |
| `status` | str | `proposed` / `folded` (builder + fold live) / `deferred` (explicitly skipped, e.g. thin CV data) |

**Granularity axes** (a signal's `gran` column lists which axes it expands across when
materialized per-entity): `s`=season, `l5`/`l10`/`l20`=rolling windows, `opp`=per-opponent,
`sch`=per-scheme, `q`=per-quarter, `sc`=per-shot-clock, `scr`=per-game-script,
`loc`=per-court-zone. A single registry row expands into many concrete columns once
materialized across these axes and across every player/team/lineup — this is how "86
definitions" becomes "hundreds of columns per entity" in practice.

### What's in the registry today (NBA)

The current `DEFS` table (as of the builder script) enumerates **86 signal definitions**
across 3 entities x ~15 domains:

- **Player (59 defs):** scoring, playmaking, rebounding, defense, movement (CV-derived —
  currently `deferred`, thin CV coverage), usage, situational, durability, form,
  correlation.
- **Team (19 defs):** offense, defense, lineup_eco, context (`context` is `deferred`).
- **Lineup (8 defs):** fivemix (5-man units), pair (2-man synergy).

The EV-tier discipline is explicit in the header comment: *"EV tiers are HONEST
expectations, not promises."* A `C` (scouting-only) signal never enters a model; it exists
purely to populate vault player/team notes for human/agent scouting context. Only `A`/`B`
tier, `point-model-candidate` or `corr-model` consumer signals are eligible to be proposed
as walk-forward feature candidates.

### The signal factory — turning registry entries into candidate proposals

**File:** [`scripts/platformkit/signals/signal_factory.py`](../../scripts/platformkit/signals/signal_factory.py)

The signal factory is a *proposal generator*, not a model trainer. It reads two inputs —
the vault's person-free taxonomy (named archetypes / defensive schemes, via
`scripts.platformkit.signals.vault_taxonomy.load_taxonomy`) and a payload-probe of the
`signal_registry.parquet` stat vocabulary — and emits `CandidateSpec` objects for three
families:

- `playstyle_corr` — archetype-conditioned stat-pair correlation ("does conditioning a
  stat-pair correlation on an Archetype NAME improve calibration of the joint?")
- `scheme_prior` — defensive-scheme -> shot-quality prior
- `archetype_matchup` — archetype-vs-archetype interaction term

Every emitted spec carries `note="calibration, not edge"` and `vs_close="UNPROVEN"`
(`_spec()`, line ~129) and is passed through
`scripts.platformkit.improve.candidate_families.validate_spec` — the same choke point that
rejects any spec containing a dollar/ROI field or a retracted number.

**Name-stability is load-bearing.** Candidate IDs are hashed from vault *names* (e.g.
`"playstyle_corr=arch:stretch_five|pair:pts_reb"`), never from a KMeans cluster-id or a
person identifier — `_slug()` (line 72) normalizes names to a stable ASCII token so the same
idea hashes to the same `candidate_id` even after the underlying archetype taxonomy is
re-clustered. `gen_archetype_matchup` additionally sorts the pair by slug (line 195-207) so
`(A, B)` and `(B, A)` collapse to one canonical id.

**Cold start is a tested invariant, not an edge case.** If the vault taxonomy has zero
archetypes/schemes, or the registry probe (`_probe_stat_pairs`, line 82) yields no valid
stat-pair target and the small hardcoded fallback (`pts`/`reb`/`ast` pairs) also can't be
used, every generator function returns `[]`. The factory never fabricates a target.

The factory **never fits anything** — it stops at `CandidateSpec` generation. Turning a spec
into a gate-consumable candidate (fitting, walk-forward scoring, ship/reject) is a separate
step (`recalibrator.build_candidate`, referred to in the factory's docstring as "the MF4
choke") that this file does not perform. This two-stage split (propose, then separately
gate) is what keeps the discovery loop's proposal surface auditable — a bad idea can be
generated and inspected without ever touching a trained artifact.

---

## Role-aware ratings — the "2K-style" player overall

**Builder:** [`scripts/team_system/build_player_ratings.py`](../../scripts/team_system/build_player_ratings.py)
**Input:** `data/cache/team_system/attribute_vault.parquet` (87 context-adjusted attributes
per player) + `data/cache/team_system/player_roles.parquet` (per-player archetype label)
**Output:** `data/cache/team_system/player_ratings.parquet`

This is the human-facing rating layer (feeds vault player cards and several sim engines'
matchup context), not itself a walk-forward-gated predictive model. The pipeline:

1. **87 attributes -> 13 category ratings.** The `CAT` dict maps each of 13 categories
   (`SCORING`, `SHOOTING`, `PLAYMAKING`, `CREATION`, `FINISHING`, `REBOUNDING`,
   `INTERIOR_D`, `PERIMETER_D`, `CLUTCH`, `IQ`, `SIZE`, `ATHLETICISM`, `DURABILITY`) to a
   weighted list of underlying vault attributes, aggregated by `_cat()` (a weighted mean
   over whatever attributes are present, defaulting to 50.0 if none are).
2. **Attribute interactions.** Category scores are then modulated by explicit multiplicative
   interaction terms — e.g. `INTERIOR_D` scales with player height (a small shot-blocker is
   capped, a 7'5" anchor isn't); `SCORING` scales with the product of efficiency and volume
   (empty high-volume scoring is dinged); `FINISHING`/`CREATION` get a "gravity" bonus from
   elite `SHOOTING` (spacing pulls defenders, opening driving lanes).
3. **Role-weighted aggregation.** `ROLE_W` maps each of 15 archetypes (`LEAD_GUARD`,
   `STRETCH_BIG`, `ANCHOR_BIG`, etc.) to a 10-category weight vector defining which skills
   matter for that role's overall. A uniform floor (`0.78 * role_weights + 0.22 * uniform`)
   prevents a one-dimensional specialist from grading like a well-rounded star purely
   because his one skill is role-weighted heavily.
4. **Impact and trust adjustments.** The raw score is further scaled by offensive load
   (`crea_usage`/`score_volume` average — heavier offensive responsibility separates stars
   from equally-skilled role players) and by a minutes-trust factor (an efficient 19-mpg
   bench player is not rated as a 94-overall star; trust uses the *current-season* role so a
   rookie in a big current role isn't unfairly dampened by a thin prior-season sample).
5. **Fixed anchored curve.** The final `raw` score is mapped to a 1-99 `OVERALL` via a fixed
   piecewise-linear curve (`CURVE_X`/`CURVE_Y`), calibrated to real anchor points (e.g. the
   current #1 overall, a named top tier, a named gap between two specific players) rather
   than re-normalized against whatever corpus happens to be loaded — so ratings are stable
   run-to-run and don't drift as the player pool changes.

The builder also writes a "deep card" markdown block into per-player vault notes
(`_fold()`) showing the underlying attribute breakdown grouped by category, and prints a
league top-20 + roster-specific sanity report (`_report()`).

**What this is not:** a walk-forward-validated predictive model. It is a hand-tuned scoring
function (interaction terms, role weights, and the anchor curve are all manually set,
documented inline as calibrated against specific named-player sanity checks) that produces
a *descriptive* skill rating consumed by scouting surfaces and, where wired, by sim engines
as a matchup-context input (see [`possession-simulators.md`](possession-simulators.md) for
how `INTERIOR_D`/`PERIMETER_D` feed the NBA possession sim's defender-suppression term).
Analogous team-level builders exist alongside it in `scripts/team_system/`
(`build_team_defense.py`, `build_player_roles.py`, `build_player_attributes.py`,
`build_recency_rates.py`, and others) forming the same attribute-vault -> rating pipeline
for team defense and player archetype assignment.

---

## Related

- [`possession-simulators.md`](possession-simulators.md) — how ratings/signals feed the Monte Carlo engines
- [`calibration-and-validation.md`](calibration-and-validation.md) — the honesty discipline every downstream number inherits
- [`pregame-props.md`](pregame-props.md) — the NBA prop-pricing chain that consumes signals
- [`MODEL_UNIVERSE.md`](MODEL_UNIVERSE.md) — the NBA-specific 350-model planning catalog (legacy, pre-kernel-extraction)
- [`../../data/registry/SIGNAL_REGISTRY.md`](../../data/registry/SIGNAL_REGISTRY.md) — the generated human-readable signal index
