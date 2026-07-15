# Calibration and Validation Methodology

**The product is a calibrated predictor, not a betting-edge system.** Every claim on this
page is about calibration/sharpness (Brier, RMSE, ECE) versus the devigged market close —
never a dollar edge or ROI. Pregame markets are efficient; the honest, defensible result is
"matches the devigged close within noise" on team-strength markets, plus a measured,
calibrated in-game conditioning improvement. See [`../PLATFORM.md`](../PLATFORM.md) and
`docs/JOB_EVIDENCE_PACKET.md` (the single numeric truth source) for the full framing. An
honest REJECT — a signal or model that fails its gate — is recorded as a success, not
hidden.

This page describes the **sport-blind kernel machinery** that every domain adapter inherits;
for the NBA-specific implementation detail (ECE targets per prop, the Shin devig worked
example, per-tier calibration requirements) see [`calibration.md`](calibration.md), the
older NBA-only writeup that predates the kernel extraction.

---

## Why calibration, not edge

An uncalibrated model that says "P(over) = 0.62" is worthless if that 62% bucket actually
hits 52% of the time. Calibration is the prerequisite for treating model output as a real
probability rather than an ordinal ranking — it is necessary infrastructure, not a claim of
predictive advantage. The system's own validation shows pregame markets are largely
efficient: models **match** the devigged close on team-strength markets (moneyline) and run
**behind** on totals/derivative markets specifically because of freshness data (injuries,
lineups, weather, park/pitcher news) a static box-score model cannot see in time. That gap
is honestly attributed to missing freshness, not modeling failure.

---

## Kernel-level proof metrics

**File:** [`kernel/validation/proof_metrics.py`](../../kernel/validation/proof_metrics.py) — pure stdlib + numpy + sklearn, no domain imports.

| Function | What it measures |
|---|---|
| `brier(probs, outcomes)` | Mean squared error between forecast probability and binary outcome. Perfect = 0.0; constant-0.5 baseline = 0.25. |
| `ece(probs, outcomes, bins=10)` | Expected Calibration Error: frequency-weighted average gap between predicted probability and empirical frequency across probability bins. |
| `reliability_slope(probs, outcomes, bins=10)` | OLS slope of the reliability diagram; 1.0 = perfectly calibrated, <1 = overconfident, >1 = underconfident. |
| `isotonic_calibrate(train_p, train_y, eval_p)` | Fits `IsotonicRegression` on a train corpus and transforms a held-out eval corpus — the calibration primitive every sport's recalibrator wraps. |
| `devig2(price_a, price_b)` | Two-sided devig of decimal odds to fair implied probabilities. |
| `clv_sign_invariants(...)` | **Plumbing correctness only** — checks two mechanical CLV-sign invariants (betting the close against itself must yield CLV≡0; two-sided CLV must be anti-symmetric after devig). The module's own docstring is explicit that a passing result "carries zero edge meaning" — it guards a known sign-bug class, nothing more. |

Every sport's calibration and CLV bookkeeping is built on these five sport-blind functions,
so a fix or a new metric here benefits every domain simultaneously.

---

## The three recalibration methods and when each is used

| Method | Functional form | Parameters | Use when |
|---|---|---|---|
| **Platt scaling** | `sigmoid(a*z + b)` | 2 (logistic fit) | Calibration curve is monotone-sigmoid; low data (thin corpora, per-segment fits) |
| **Isotonic regression** | Nonparametric monotone step function | ~n_bins | Non-sigmoid / kinked curve; high data volume |
| **Temperature scaling** | `sigmoid(z / T)`, scalar T | 1 | Only sharpness (not shape) is off — e.g. tennis WTA uses a fixed `T=1.36` (`domains/tennis/predictor_helpers.py`) rather than a full Platt fit |

The trade-off is bias vs. variance: Platt's 2-parameter sigmoid is stable on small samples
but cannot fix a non-sigmoid kink; isotonic fits any monotone shape but needs enough data
per bin or it overfits the calibration set. **Cross-fitting is the honesty discipline that
makes any of these trustworthy**: fitting a calibrator on the same rows you then score
against makes any monotone calibrator look like an improvement (it can memorize empirical
frequencies). The pattern used throughout the codebase is k-fold cross-fit — fit on k-1
folds, predict the held-out fold, only ever score out-of-fold predictions — and a calibrator
is shipped **only if** the cross-fitted Brier beats the uncalibrated baseline. In practice a
well-trained blended model is often already close to calibrated and the extra calibration
layer is not deployed at all; that null result is recorded, not discarded.

---

## Leak-avoidance: the two seams that make it structural, not a promise

Leak safety in this codebase is not a checklist — it is enforced by two frozen data
contracts every domain adapter must implement, both defined once in `scripts/platformkit/`
and reused by every sport.

### 1. The `IngestManifest` — provenance / leak-class contract

**File:** [`scripts/platformkit/ingest_manifest_core.py`](../../scripts/platformkit/ingest_manifest_core.py)

Every corpus a sport depends on is declared as an `IngestSource(corpus, leak_class,
sla_minutes, description)`. Four `leak_class` values are load-bearing:

- `LEAK_PRE_GAME` — known before tip/first-pitch/kickoff; safe as a pregame feature.
- `LEAK_IN_GAME` — accrues during play; in-game conditioning only, never a pregame feature.
- `LEAK_POST_GAME` — only known after the final whistle; settlement labels and training
  *targets*, never pregame features.
- `LEAK_REFERENCE` — static reference data (parks, surfaces, rosters).

The honesty anchor, confirmed in `domains/tennis/ingest_manifest.py`: the post-game
serve/return box (`match_stats`) is correctly tagged `LEAK_POST_GAME`, but the *as-of*
features derived from it (`asof_features`, `asof_hold`, `asof_return`) are tagged
`LEAK_PRE_GAME` — because the shared `scripts.platformkit.asof_common` walk-forward builder
snapshots a player's trailing stats **before** updating them with the current match's
result. Every "as-of" builder across every domain (`asof_*.py` files under each
`domains/<sport>/`) follows this same snapshot-before-update discipline.

`IngestManifest.validate()` checks structural correctness (no duplicate corpora, valid leak
classes, positive SLAs). `validate_against_inventory(inventory)` cross-checks every declared
source against the live data census — a source that's missing or 0-row on disk is a
manifest error, not a silent gap.

### 2. The `FeatureSpec` — train==inference parity contract

**File:** [`scripts/platformkit/feature_spec_core.py`](../../scripts/platformkit/feature_spec_core.py)

A `FeatureSpec` is the frozen, ordered, versioned column list for one sport's base feature
matrix — a tuple of `FeatureField(name, source, default, cast, source2, op)` entries.
`build_base_matrix(spec, df)` is the **single derivation point**: both training and
inference call the same function, so the column set and column order can never silently
diverge between the two paths. This closes what the module's own docstring calls "the most
expensive bug class in this codebase" — a feature wired at train time that reads a silent
constant (usually 0.0) at inference because the inference path never sets it, uses a
different key, or the pipeline was rebuilt without re-wiring the new column. The model still
imports and runs fine; it just silently bets on a dead feature, which shows up only as a
small, permanent, hard-to-diagnose calibration regression in production.

Two properties enforce this mechanically:
- **Required-source-absence raises**, it never silently zero-fills — a `FeatureField` with
  `default=None` treats a missing source column as a hard error, not a `0.0`.
  `default` is applied *only* when the source column is entirely absent from the frame; a
  present column's `NaN` values pass through untouched (matching the per-row
  `float(row.get(src, default))` convention the adapters used before this seam existed).
- **`catalog_hash()`** produces a stable 16-hex hash over `version + every field's
  name|source|default|cast[+op|source2]`, so any change to the feature contract is
  detectable and versionable.

`assert_matches_catalog(spec, col_names)` is the runtime assertion: if the columns produced
by a real adapter's feature-building code don't byte-match the frozen catalog (same names,
same order), it raises. Tennis's full spec is five fields
(`domains/tennis/feature_spec.py`): two `OP_DIFF` Elo differences (`elo_diff`,
`surface_elo_diff`) plus `best_of`/`rest_days_a`/`rest_days_b` — deliberately minimal, which
is why it's cited in `docs/PLATFORM.md` as the cleanest reference.

### The complementary runtime check: `parity_ok()`

**File:** [`improve/parity_check.py`](../../improve/parity_check.py)

Where `FeatureSpec` prevents the bug structurally (one derivation point), `parity_ok()` is a
runtime **assertion function** that can be called on any pair of `(train_features,
infer_features)` dicts for the same observation. It reports two things separately:
`mismatches` (any diverging key/value) and `zero_reads` (the subset of mismatches where the
inference value is ~0.0 but the train value was not — almost always a wiring bug rather than
a legitimate data difference). Pure function, no I/O, never raises internally (`parity_ok`
catches its own exceptions and returns `ok=False` with a descriptive entry) — designed to be
called cheaply and often, including inside CI, without needing a real feature pipeline
wired up.

---

## The parity-matrix gate — one green/red grid over every sport

**File:** `scripts/platformkit/parity_matrix.py` (referenced from `docs/PLATFORM.md`, which
documents its mechanics in full).

A fail-closed grid over `SPORTS x {census, manifest, feature_spec}`. Each cell is computed
independently and purely offline (no torch, no app boot, runs in seconds):

- **census** — do the sport's declared corpora exist and are they non-empty on disk?
- **manifest** — does `IngestManifest.validate()` pass, and does every declared source
  exist + have rows in the live census?
- **feature_spec** — does the `FeatureSpec` load, have a non-empty catalog, and does
  `build_base_matrix` produce exactly `n_features()` columns with matching names?

The grid uses a tri-state, not a binary: a dimension a sport hasn't built yet is `n/a`
(gray) and does not fail the gate; a dimension that is present but broken is `red` and does.
As of the current build, every sport including `soccer_intl` has a working
`ingest_manifest.py` and `feature_spec.py`, so the grid is all-green across
census/manifest/feature_spec for every declared sport (`python -m
scripts.platformkit.parity_matrix`).

Two AST-only import guards run alongside the parity matrix
(`scripts/platformkit/check_import_contract.py`): **kernel purity** (nothing under `kernel/`
may import `src.*`/`domains.*`/`api.*`/`scripts.*`) and the **cross-adapter ban**
(`domains/<a>/` may never import `domains/<b>/`). Both are static AST checks — they never
execute the inspected files — so a violation is caught without running any model code.

---

## Walk-forward validation and truncation invariance

**File:** [`kernel/testing/invariants.py`](../../kernel/testing/invariants.py) — reusable,
sport-blind invariant checkers used by every domain's conformance tests.

- **`check_truncation_invariance(events, get_points, get_side, expected_totals)`** — folds
  a complete event log (e.g. every scoring play in a game) and asserts the fold reproduces
  the declared final score exactly. This generalizes the invariant that any event-level
  simulator must satisfy: replaying the full event stream cannot silently drop or double
  count scoring.
- **`check_prefix_running_scores(events, ..., cuts)`** — at each specified cut index,
  asserts that folding only the *prefix* of events up to that cut equals the running score
  recorded on the event itself at that point — this is what "as-of" correctness looks like
  at the event-log level: a truncated replay must agree with what was actually known at
  that point in time.
- **`check_registry_order`**, **`check_frozen`**, **`check_monotonic_nonincreasing`** —
  smaller structural guards (stat-name registry order hasn't silently shifted; a frozen
  dataclass is actually immutable; a time-remaining fraction never increases).

`kernel/testing/conformance.py::check_sport_context(ctx)` is the top-level adapter gate: it
validates a domain's full `SportContext` (stats registry, clock config, roster config, game
state config, entities/pbp_mapper/league_client protocols, atlas schema) and returns a list
of human-readable violation strings — empty means fully conformant. This is what the 9-step
new-sport playbook in `docs/PLATFORM.md` runs before a domain is considered wired into the
kernel at all.

---

## Backtest / scoreboard methodology

The headline "are we beating the market?" question is answered by committed, reproducible
scoreboard scripts rather than a single hand-run notebook:

- **`scripts/platformkit/beat_the_close_scoreboard.py`** — one row per (sport, market)
  comparing the model to the devigged market close on the *same* real held-out outcomes.
  RMSE for totals, Brier for win-probability markets. Verdict labels are explicit: `MATCH`
  = within sampling noise of the close, `BEHIND` = the market's freshness advantage. The
  script hard-fails closed (`_all_non_ok`) rather than silently printing a partial or stale
  result when no corpus resolves.
- **`scripts/platformkit/ingame_scoreboard.py`** — the equivalent comparison for the
  in-game conditioning layer: static pregame Brier vs. conditional-on-realized-state Brier.

Both scripts are runnable against committed fixture corpora
(`tests/fixtures/proof`) so the headline numbers reproduce from a fresh clone in under 60
seconds without needing any private data — this is the mechanism behind the "reproduces on
committed fixture" / "VALIDATION_PENDING" distinction used throughout `docs/PLATFORM.md`'s
results table.

**The discipline that backs every number claimed anywhere in this system:**
1. Leak-free (enforced by the `IngestManifest`/`FeatureSpec` seams above).
2. Walk-forward, never a random train/test split — every eval reconstructs "what was known
   as of this point in time."
3. At least two independent corpora must agree before a lift is trusted — a single-fold
   or single-split win is treated as a selection artifact until every walk-forward fold
   agrees.
4. Honest rejects are recorded, not silently dropped — a candidate signal or feature block
   that fails its gate stays in the codebase as infrastructure with a documented REJECT
   verdict and the evidence that produced it (see, e.g., the rejected-block table in
   [`feature-inventory.md`](feature-inventory.md)).
5. Never a fabricated dollar ROI. The only numbers this system reports are calibration
   (Brier/RMSE/ECE) relative to the devigged close.

---

## Related

- [`../PLATFORM.md`](../PLATFORM.md) — the kernel/adapter architecture these seams belong to, and the current per-sport results table
- [`calibration.md`](calibration.md) — NBA-specific calibration detail (Shin devig worked example, per-tier ECE targets) predating the kernel extraction
- [`feature-inventory.md`](feature-inventory.md) — the NBA feature stack and its recorded walk-forward REJECT verdicts
- [`signal-factory-and-ratings.md`](signal-factory-and-ratings.md) — the signal layer these gates screen
- `docs/JOB_EVIDENCE_PACKET.md` — the single source of truth for any current numeric claim
