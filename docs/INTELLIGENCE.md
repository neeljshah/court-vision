# CourtVision Intelligence Layer

> **Funnel position:** this is **stage 2 (SIGNALS)** feeding the model stack, and it's also
> where **stage 6 (INTELLIGENCE)** writes back. See the full funnel in [../README.md](../README.md)
> and [../ARCHITECTURE.md](../ARCHITECTURE.md). Cross-links:
> [PUBLIC_EVIDENCE.md](PUBLIC_EVIDENCE.md) · [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

The intelligence layer sits between raw CV tracking and the prediction models. It is **151 artifact
files** (parquet + json) derived from broadcast-video tracking, NBA Stats API, and play-by-play
microstructure — the original 80-artifact core plus later additions (compound-signal hunts, CV
sidecars, daily-picks retros). Every artifact answers a specific question the prediction stack
would otherwise have to guess at: *who is this player right now, what scheme is the opponent
imposing, how does this matchup behave, is the model confident here?*

Artifacts are gitignored (`data/intelligence/`) — regenerable from raw tracking + NBA Stats. This
doc is the public-facing **manifest**: what exists, what's in each file, how it plugs in. The
10-section inventory below documents the original 80-artifact core in full; later additions are
not yet individually catalogued.

> **Local-only research layer — not part of the public clone.** The 151 artifact files live under
> `data/intelligence/` (gitignored) and are **absent from a fresh clone**; they are not rendered by
> the site and cannot be regenerated without the local raw-tracking + NBA-Stats corpus. What ships
> publicly is this manifest (schema + counts) plus the derived **summaries that appear on the
> evidence pages**. Treat every row count and scale figure below as a description of the local
> research corpus, not something the clone can reproduce on its own.

> **Status (2026-07-15):** 151 artifact files populated (80-artifact core + growth). Coverage is uneven — some layers (lineup
> chemistry, similarity index) span thousands of rows; others (officials player-sensitivity,
> absence-effects) are early and small. Per-artifact row counts are listed so maturity of each
> signal is legible at a glance.

> **Scale summary:** 291,625-pair matchup matrix · 690-node knowledge graph (660 player + 30 team)
> · 1,249 per-player dossiers (28 statistical categories, archetype-labeled) · 30 team scheme cards.
> See **[docs/PLAYER_INTELLIGENCE.md](PLAYER_INTELLIGENCE.md)** for the full showcase with real
> dossier examples (Jokić, SGA, Sam Hauser) and honest scope statement.

---

## How it plugs into the prediction stack

```
Broadcast video ──► CV tracking ──► raw frame features
                                          │
NBA Stats API ──► gamelogs + boxscores ───┤
                                          │
PBP microstructure ───────────────────────┤
                                          ▼
                            ┌─────────────────────────┐
                            │   INTELLIGENCE LAYER    │  ← this doc
                            │  (80 derived artifacts) │
                            └─────────────┬───────────┘
                                          │
       ┌──────────────────────────────────┼──────────────────────────────────┐
       ▼                                  ▼                                  ▼
  Prop models                     In-play winprob                    Bet construction
  (PTS/REB/AST/...)              (endQ1/Q2/Q3 LGB)                  (filters + Kelly)
```

Concrete examples of how a prediction call consumes intelligence:

- **Prop model for tonight's LeBron PTS** → loads `current_form_profiles` (trend tag + driver),
  `matchup_deviations` (LeBron-vs-MIN delta), `per_player_confidence` (volatility-adjusted Kelly
  multiplier), `officials_player_sensitivity` (ref tightness sensitivity), `pace_adjusted_cv`
  (pace-normalized baseline).
- **In-play endQ3 winprob** → consumes `ingame_momentum` (H1 → H2 delta vector), `clutch_cv_split`
  (clutch elevators vs. shrinkers), `quarter_profiles` (per-quarter velocity baseline),
  `coaching_adjustments` (whether the trailing team is mid-adjustment).
- **Bet filter / sizing** → reads `cv_quality_per_game` (gate by tracking quality),
  `confidence_curves` (per-EV-decile reliability), `anomaly_log` (suppress bets on players
  currently outside their baseline).
- **Possession simulation** → the player-level Monte Carlo (`src/sim/`) reads
  `data/cache/team_system/{player_rates, team_rates}` plus scheme / clutch / rest context tables
  as per-possession rate multipliers, so an intelligence finding propagates directly into simulated
  game outcomes and same-game-parlay joint pricing.

**The loop closes here.** The self-improving discovery loop (`src/loop/`) doesn't only *consume*
this layer — it *extends* it. ARM A writes new `signals/<name>.py` leaf signals (each gated by
expanding WF + null-shuffle permutation + Benjamini-Hochberg FDR); ARM B writes new `intel/*.py`
atlas sections back into the player profiles. Artifacts are added only after passing the gate, and
most candidates are correctly rejected.

**Honest caveat on betting value:** The intelligence layer's signal currently moves SHAP importance
only through the prop models, where it contributes to accurate prediction. On point features, that
accuracy gain does not translate to a betting edge (market efficient on closing lines). The real
value of this layer is at the joint/in-game/freshness frontier — and as a basketball-understanding
and scouting resource. See [CEILING.md](CEILING.md) for the ceiling analysis.

> **Measured-lift honesty (read this first).** The descriptive/atlas intelligence is a deep
> **scouting + correlation asset**. Its measured **point-accuracy lift on the served model is
> ~0 today** — CV-derived features carry SHAP ~= 0 in production and the full-season walk-forward
> confirms the model is well-calibrated but does **not** beat the close (CLV ~= 0). Every number
> on this page is a **calibration / sharpness / coverage** statistic, **never a dollar edge**. No
> betting edge is claimed anywhere in this layer. The single truth source for what may be claimed
> is [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md); the retracted figures it lists are never
> reprinted as current.

---

## The artifact classes (what each one *is*)

The 80 artifacts cluster into a small number of *classes*, each answering a different question.
This taxonomy is the conceptual map under the 10-section inventory below.

| Artifact class | Question it answers | Representative artifacts | Persistence |
|---|---|---|---|
| **Identity / archetype** | *Who is this player, structurally?* | `player_fingerprints`, `player_archetype_definitions`, `similarity_matrix` | parquet vector + JSON dict |
| **Form / trend** | *Who are they right now (vs. baseline)?* | `current_form_profiles`, `rolling_trends`, `anomaly_log` | half-life-weighted parquet |
| **Matchup / scheme** | *What is the opponent imposing?* | `defensive_schemes`, `matchup_deviations`, `archetype_scheme_interactions` | per-team / per-pair parquet + t-stat JSON |
| **Lineup / chemistry** | *Who else is on the floor?* | `lineup_chemistry`, `pair_chemistry`, `bench_starter_split` | with-vs-without delta parquet |
| **Situational / contextual** | *What state is the game in?* | `clutch_cv_split`, `quarter_profiles`, `ingame_momentum` | per-bucket parquet |
| **Schedule / rest / officials** | *What surrounds the game?* | `rest_cv_impact`, `pace_adjusted_cv`, `officials_cv_impact` | per-condition parquet + ANOVA JSON |
| **Retrieval** | *What game is this most like?* | `game_similarity_index`, `game_neighbors` | k-NN neighbor lists |
| **Quality / calibration** | *How much should we trust this?* | `cv_quality_per_game`, `per_player_confidence`, `confidence_curves` | gate + decile-reliability tables |

Each artifact is one of three persisted shapes: a **vector** (PCA / k-best fingerprints), a
**conditional delta** (behavior under a condition minus the player's own baseline, with a
significance test), or a **reliability curve** (an EV/quality bucket mapped to a realized
outcome — the honesty layer). No artifact stores a raw future value; deltas and curves are
computed against history only.

---

## How an atlas section is built (leak-free)

The 48 deep atlas-section builders live under `intel/` (30 `player_*` + 18 `team_*`), and they all
subclass the single `AtlasSection` contract in `src/loop/atlas.py`. The contract is what makes the
"intelligence is leak-free" claim mechanical rather than aspirational:

```
intel/player_clutch_scoring.py        # one section = one slice of a dossier
    class PlayerClutchScoring(AtlasSection):
        name = "clutch_scoring"; entity = "player"
        build(entity_id, as_of)  ->  AtlasArtifact | None   # leak-safe, as-of-dated
        validate(artifact)       ->  bool                   # face-validity / range check
        cv_fields()              ->  {name: CVSlot}          # reserved null slots for CV branch
```

The leak-free guarantees, all enforced in code:

1. **As-of boundary.** `build(entity_id, as_of)` may only read rows with `game_date <= as_of`.
   In `player_clutch_scoring.py`, for example, the season-context and PBP sources are explicitly
   filtered (`rows[rows["game_date"] <= pd.Timestamp(as_of)]`) before any aggregate is taken.
2. **Sample-size -> confidence ladder.** `confidence_from_n(n)` maps coverage to a stamped level
   (`high` if n>=20, `med` if n>=5, else `low`); CV-derived fields are capped at `med` via
   `conf_cap`. `n` is the count of *real games observed* (e.g. `clutch_gp`), never the row count.
3. **DEFER over invent.** When a source parquet lacks a raw count, the sub-field is set to `None`
   and tagged `DEFER` with the reason and the script that would unblock it — the builder never
   fabricates a value. (Clutch `ft_rate` / `tov_under_pressure` are live DEFER examples.)
4. **Reserved CV slots.** `cv_fields()` returns named slots with `value=None`. The CV branch fills
   them later **without** a profile-factory rebuild; `validate()` *fails* if any CV slot is
   non-null at build time (CV must not leak into the descriptive substrate prematurely).
5. **Provenance stamp.** Every artifact carries `{source, n, confidence, as_of}`. Validation
   happens twice: the section's own cheap `validate()`, then the full leak / coverage / dedup gate
   in `src.loop.intel_validator`. Only artifacts that pass both are persisted (via
   `profile_factory_bridge.register_section` -> one disjoint parquet + one `sec_<name>` function).

This is the ARM-B half of the self-improving loop: ARM-B writes new `intel/*.py` sections back into
the dossiers; ARM-A writes new `signals/<name>.py` leaf signals. Both are gated; **most candidates
are correctly rejected**, which is the honest success criterion (see [signal-inventory.md](signal-inventory.md)).

---

## The archetype & shrinkage-prior mechanism

The identity class is built on an unsupervised **fingerprint -> archetype -> prior** pipeline:

1. **Fingerprint.** Each player's per-game tracking + box features are reduced to a low-dimensional
   vector (`player_fingerprints.parquet`, PCA; `player_fingerprints_kbest.parquet`, a k-best
   variant robust to missing CV games). The vector is the player's structural signature.
2. **Archetype assignment.** Fingerprints are clustered into the 12 labelled archetypes
   (*Playmaking Big*, *3&D Wing*, *Primary Initiator*, ...). Each player gets a label **plus a
   distance-from-centroid**, so "how prototypical" is itself a feature. `archetype_drift.parquet`
   flags players mid-transition between clusters.
3. **Shrinkage prior.** A thin-sample player (few games, or few CV games) is shrunk toward the
   **archetype centroid** rather than toward the league mean — a small-n player inherits the
   behavioral prior of players who play like them. The `confidence_from_n` ladder controls the
   shrinkage weight: `low`-confidence sections lean hardest on the archetype prior; `high`
   (n>=20) sections trust the player's own observed rates.

> **Selector discipline (gotcha).** Downstream consumers must select on **archetype *names* /
> player_id**, never on raw KMeans cluster IDs — cluster IDs are not stable across refits, so a
> filter keyed on a cluster index silently breaks on the next rebuild. The label dictionary
> (`player_archetype_definitions.json`) is the stable contract.

Honest scope: archetype shrinkage measurably improves **calibration on thin-sample players**
(sharper, better-ranked intervals); it has **not** produced a measured point-accuracy edge on the
served model, and produces **no** betting edge versus closing lines.

---

## Layer inventory

### 1. Player identity & archetype — *who is this player*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `player_fingerprints.parquet` | 221 | PCA-reduced player vector + archetype assignment + distance from centroid |
| `player_fingerprints_kbest.parquet` | 230 | K-best feature variant of the fingerprint (more robust to missing features) |
| `player_archetype_definitions.json` | — | Archetype label dictionary (e.g. *Slashing Wing*, *Stretch Big*, *Rim-Runner*) |
| `player_atlas_viz.png` + `player_atlas_feature_list.json` | — | 2D atlas viz of all players + the features that defined each axis |
| `archetype_drift.parquet` + `archetype_drift_signals.json` | 128 | Players currently transitioning archetypes, with consistency scores |
| `similarity_matrix.parquet` | 26,335 | Pairwise Euclidean + cosine distance over all archetype-eligible players |
| `player_development.parquet` | 42 | YoY development tag (breakout, decline, stable) with delta score |
| `trade_profile_shifts.parquet` | 609 | Pre- vs post-trade tracking profile delta per trade event |

### 2. Form & trend — *who is this player right now*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `current_form_profiles.parquet` | 82 | Trend tag + max-z deviation + top driver feature, half-life-weighted |
| `rolling_trends.parquet` + `active_trend_signals.json` | 31 | Recent-vs-prior window comparison with trend direction |
| `form_vs_baseline_deltas.json` | — | Per-player deviation from career baseline, half-life 8 games |
| `breakout_signals.json` | — | Breakout candidates (positive) and decline candidates (negative) |
| `streak_signatures.parquet` + `streak_signatures_summary.json` + `streak_excluded_players.json` | 149 | Per-game streak state vs season average; excluded list = players whose streaks are noise |
| `anomaly_log.parquet` | 812 | Per-game anomalous performances with top-3 features driving the anomaly |

### 3. Matchup & scheme — *what is the opponent imposing*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `defensive_schemes.parquet` + `scheme_indicators.json` | 30 | Per-team dominant scheme tag + sub-scores (drop, paint protection, perimeter denial, pace control, iso force, closeout) |
| `position_scheme_interactions.parquet` + `position_scheme_signals.json` | 315 | Position × opponent-scheme stat deviation with t-stat + p-value |
| `archetype_scheme_interactions.parquet` + `archetype_scheme_advantages.json` | 108 | Archetype × scheme advantages — which archetypes feast vs. each scheme |
| `pos_vs_pos_matchups.parquet` + `pos_vs_pos_signals.json` | 84 | Position-vs-position matchup deviations |
| `matchup_deviations.parquet` | 581 | Per-player vs each opponent team — paint dwell delta, shot zone delta, z-scores |
| `opponent_imposed_profiles.json` | 30 teams | What each opponent does TO the player they face (vs. the player's baseline) |
| `coaching_adjustments.parquet` + `team_adjustment_tendencies.json` | 58 | Per-game H1→H2 adjustment score with top feature shifted (who adjusts at half) |

### 4. Lineup & chemistry — *who's on the floor*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `lineup_chemistry.parquet` + `lineup_signatures.json` | 4,760 + 1,175 lineups | Per-player tracking delta within each 5-man lineup vs. their own baseline |
| `pair_chemistry.parquet` + `pair_signatures.json` | 998 pairs | Per-2-man chemistry (with-vs-without partner) |
| `bench_starter_split.parquet` + `bench_starter_signatures.json` | 81 / 27 | Per-player starter-vs-bench feature delta with significance test |
| `absence_cv_impact.parquet` + `star_absence_effects.json` | 5 | Beneficiary effects when a star is out (early; sparse — see Limitations) |

### 5. Situational & contextual — *what state is the game in*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `clutch_cv_split.parquet` + `clutch_rankings.json` | 188 | Clutch-vs-non-clutch tracking delta — *elevators*, *shrinkers*, *neutrals* |
| `quarter_profiles.parquet` + `quarter_signatures.json` | 528 | Per-player per-quarter baseline velocity/usage |
| `shot_clock_buckets.parquet` + `shot_clock_player_profiles.json` | 8,514 | Per-player behavior by shot-clock bucket (early/mid/late) |
| `possession_type_profiles.parquet` + `possession_type_signatures.json` | 503 | Per-player behavior by possession type (transition, halfcourt, ATO, etc.) |
| `tipoff_predictability.parquet` + `tipoff_predictability_signals.json` | 45 | How much the opening minutes predict the full-game pattern |
| `sequential_patterns.parquet` + `sequential_signatures.json` | 144 | Rhythm/sequence features (vel after make vs. vel after miss, etc.) |
| `ingame_momentum.parquet` | 775 | Per-player H1 → H2 feature delta (momentum carry) |
| `h1_h2_projections.parquet` + `h2_projection_signals.json` | 497 | H2 projection from H1 state with clutch/closer multipliers |
| `compound_candidates.parquet` | 10 | Compound atlas-pair candidates (player + situation combinations with shift signal) |

### 6. Schedule, rest & officials — *what's happening around the game*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `rest_cv_impact.parquet` + `rest_cv_signatures.json` | 30 | Per-player rest-day / B2B impact on tracking features |
| `pace_adjusted_cv.parquet` + `pace_adjusted_rankings.json` | 121 | Pace-normalized per-player ranking |
| `dow_cv_profiles.parquet` + `dow_signals.json` | 25 | Day-of-week effects with ANOVA F + adjusted p |
| `time_of_day_cv.parquet` | 25 | Weekday vs. weekend tracking deltas |
| `officials_cv_impact.parquet` | 10 | League-level tight/mid/loose ref crew impact |
| `officials_player_sensitivity.parquet` | **0** | Per-player ref-sensitivity — placeholder; not yet populated (see Limitations) |
| `officials_signals.json` | — | Aggregated officiating signals + top ref-sensitive players |

### 7. Game similarity & retrieval — *what game is this most like*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `game_similarity_index.parquet` | 1,214 | Per-player-game top-5 neighbors (overall + same-player) for retrieval-augmented projection |
| `game_neighbors.json` | 505 keys | Game-ID → neighbor list lookup |
| `similar_neighbors.json` | — | Inverse index variant |

### 8. Quality, confidence & calibration — *how much should we trust this prediction*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `cv_quality_per_game.parquet` | 3,560 | Per-game CV quality (homography validity, jersey resolution, phantom-slot flag) — used to gate bets |
| `cv_quality_confidence_curves.json` | — | Quality → confidence mapping; quality-adjusted Kelly multiplier |
| `per_player_confidence.parquet` | 112 | Per-player CV volatility + per-stat confidence multipliers |
| `confidence_curves.json` | — | EV decile → realized return curve (the calibration honesty check) |

### 9. AI chat surface — *how the LLM accesses the intelligence*

| Artifact | Rows | What it encodes |
|---|---:|---|
| `ai_chat_facts.json` | — | Pre-extracted facts (player + team) for grounded LLM responses |
| `ai_chat_index.json` | 14 indices | Topic → artifact routing index (player_profile, player_similarity, player_trend, etc.) |

### 10. Versioned validation outputs — *what's the current generation*

| Artifact | What it encodes |
|---|---|
| `v6_simulation_results.json` | V6 simulation run results |
| `v8_clean_subset_results.json` | V8 clean-subset validation |
| `v9_unified_results.json` | V9 unified results (latest generation) |
| `int_v8_results.json` | Intelligence-layer v8 decomposition |
| `c1_clean_backtest_results.json` | C1 clean baseline backtest with pre/post-fix comparison |
| `team_change_log.json` | Mid-season team-change events for trade-shift attribution |

---

## Trait profiles + season claims (2026-07)

A second generation of this layer sits on top of the 80 artifacts above: instead of a fixed
parquet, `scripts/platformkit/intel_query/` answers questions live from **VERIFIED claims** --
each claim independently recomputed and checked by a separate validator before it is allowed to
answer anything. This is the "AI chat surface" (section 9 above) grown into a full query layer.

**Shooter trait VECTORS, never one re-weighted score.** `compose_profile.py` answers "what kind
of shooter is X" (routed automatically by `ask()`, see `ask.py`'s `_try_shooter_profile`) with a
per-axis vector -- volume, efficiency, difficulty, gravity, context -- each axis citing its own
VERIFIED claim, its own rank, and two percentiles (within the claim's full pool, and within the
NBA's own fg3m>=82 3P%-title qualification pool). Axes are **never** combined into a single score;
a declared, un-tuned band table (elite/high/mid/low) turns percentiles into a plain-language
`trait_line`. This is a deliberate design choice, not a missing feature: Luka Doncic is the
canonical case for why -- mediocre fg3_pct but extreme self-created shot difficulty, huge volume,
real gravity, all of which a single blended number would erase. Honest gaps are reported alongside
the built axes rather than papered over: `avg_shot_distance`/`deep3_share` has no 2024-25 per-shot
location parquet on disk, and true on/off `gravity` has no lineup on/off table yet (it cites the
modeled `gravity_score` atlas claim instead, labelled explicitly as a model, not a measurement --
see [DATA_DEPTH.md](DATA_DEPTH.md)'s keystone section for the plan to close that gap).

**The 2025-26 canonical shooter claim is now VERIFIED.** The naive-composite shooter leaderboard
(`nba_canonical_shooter_claims.py`) was season-parameterized and re-run for 2025-26 once
`domains/basketball_nba/ingest_espn_player_box.py` backfilled the season's full-game player box
gap (74 of 1,156 games missing from the `quarter_box` q0 cache) via ESPN. The resulting claim,
`nba_canonical_shooter_leaderboard_full_season_2025_26`, validated VERIFIED against 339 qualifiers
(games>=20, fga>=200) -- the same independent-recompute discipline as every other claim in this
layer, just extended to the current season for the first time.

**Claim stores + independent validator pattern.** Every claim family in this layer follows the
same shape: a producer module in `scripts/platformkit/intel_validation/` writes a `.jsonl` of
claims (ranking rows, formula, source files, caveats), and a separate validator
(`claims_validator.py`) independently recomputes each claim from the cited source parquet and
stamps a verdict -- `VERIFIED`, `MISMATCH`, or `UNVERIFIABLE`. `ask.py`'s
`load_verified_claims()` only ever surfaces claims with a `VERIFIED` verdict; a `MISMATCH` or
`UNVERIFIABLE` claim stays invisible to every downstream composer, never silently used. Composers
load through `pairs_for_claim_stores()` so a bare `load_verified_claims()` never whole-loads the
GB-scale bulk rate stores (`nba_player_box_rate.jsonl` alone is 1.3GB) -- a live MemoryError this
lane already hit and fixed.

**The one-conclusion composer.** `compose_best.py` answers a genuinely different question --
"who is the *best* shooter, all factors weighed, ONE conclusion" -- via a declared, auditable
rule rather than a re-weighted blend: (1) an optional **domain filter** restricts the ranking pool
to a pre-declared external standard (the NBA's own 3P%-title qualification minimum, fg3m>=82 --
never a tuned threshold); (2) the **primary axis** is selected by a pre-registered predictive-
validity gate verdict read live from disk, so if the gate ever flips, the composer follows it,
never a baked-in "naive wins"; (3) **attribution axes** annotate the primary axis's #1 player with
other VERIFIED claims' rank/value for that same player, purely as context, never overriding the
primary axis; (4) **honest disagreement** is surfaced explicitly whenever an attribution axis's
own #1 differs from the primary axis's #1, with the gate citation explaining why the primary axis
still wins. This is the composer pattern this layer standardizes on for any "one answer, not a
ranking" question: an absurd-looking conclusion gets a domain fix (a filter, a different primary
axis), never silent re-weighting until the number looks right.

---

## What's honest about this layer

- **Row counts above are the truth.** Some layers (similarity 26K, shot-clock buckets 8.5K,
  lineup chemistry 4.7K) are mature. Others (absence-effects 5, officials player-sensitivity 0)
  are scaffolded but sparse — the framework exists; the signal isn't fully populated yet.
- **Significance is recorded where applicable** — `t_stat`, `p_value`, `p_value_adj` columns live
  in the parquets. Most signals are corrected; a few sub-100-row tables aren't significant on their
  own and only earn weight when stacked.
- **CV quality gating is real.** `cv_quality_per_game.parquet` (3,560 game-slots) feeds the
  bet-construction filter — a prediction on a game with `homography_valid_rate < 0.6` is
  downweighted regardless of model confidence.
- **The intelligence layer regenerates from raw tracking + NBA Stats.** Nothing here is
  hand-edited. Every signal is reproducible from a fresh `data/` snapshot.
- **SHAP = 0 in production today.** The artifacts are correct and complete; they do not yet produce
  measurable lift in the prop models. This is the current honest state — do not overclaim.

## How (and how little) it plugs into prediction today

A candid accounting of the wiring, end to end, so the gap between *plumbed* and *paying off* is legible:

| Path | Wired? | Measured effect today |
|---|---|---|
| Dossier fields -> prop model features (PTS/REB/AST/FG3M...) | Yes | Competitive leak-free WF accuracy; **point-accuracy lift attributable to the intelligence layer ~= 0** |
| CV behavioral features -> prop models | Yes (imputed for non-CV games) | **SHAP ~= 0** (`cv_lift_report.json: has_cv_data: false`); lift gated on the 80-game retrain |
| Scheme / clutch / rest tables -> possession Monte Carlo rate multipliers | Yes | Structure validated (teammate-rho emerges ~= -0.10); **no SGP / totals dollar edge claimed** |
| `cv_quality_per_game` -> bet-construction gate | Yes | Real: low-homography games are downweighted regardless of model confidence |
| Intelligence features -> vs. devigged closing line | Yes (graded) | **CLV ~= 0** — market efficient; the model matches but does not beat the close |
| In-game / freshness frontier | Partial | The *thesis* (this is where the gap is) — calibration gains only, **not yet a measured vs-close edge** |

The one-line summary: the layer is a **fully-plumbed, leak-free scouting + correlation substrate**.
It demonstrably sharpens *understanding* and gates bets on data quality; it has **not** demonstrated
a predictive edge on the served model, and claims to the contrary are retracted in
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Limitations

1. **Officials player-sensitivity is empty (0 rows).** Per-player ref-tightness deltas aren't
   passing the significance gate yet — needs more games per ref crew.
2. **Absence-effects has 5 rows.** Star-out / beneficiary attribution only fires on very clean
   absence games; most are confounded by simultaneous injuries.
3. **Similarity index covers 1,214 player-games.** Earlier games + non-tracked games have no
   neighbors.
4. **Compound candidates (atlas A × atlas B) are 10 rows.** Combinatorial search is gated to
   high-prior pairs; broadening is queued.
5. **Several layers don't have a public R²/Brier number** because they're not standalone models —
   they're inputs to models. The validation surface is the downstream prop/winprob walk-forward.
6. **CV features SHAP ≈ 0 in production.** The plumbing is complete; the lift is gated on the
   80-game retrain. Current state: credible thesis, zero demonstrated edge.

## Reproducing

Builder modules live under `scripts/platformkit/intel_validation/` (60+ builder/validator modules);
per-layer scripts can be run individually. Required inputs:
`data/tracking/*` (CV tracking), `data/nba/*` (gamelogs),
`data/cache/inplay_pbp_microstructure.parquet` (microstructure).

Regeneration takes ~25 min on the dev box for the full 80-artifact pass. The artifacts are kept
out of git both because they're large and because they encode the proprietary derivation; the
**schema and counts on this page are the public commitment**.

*Manifest last reviewed 2026-07-23. Underlying artifacts were last built 2026-06-02 (all 151 files
carry that mtime) and have not been regenerated since; the schema/counts above describe that local
build. This is a local-only research layer — not shipped in the public clone.*

**Siblings:** [PLAYER_INTELLIGENCE.md](PLAYER_INTELLIGENCE.md) (dossier showcase + scope) ·
[MEMORY_GRAPH.md](MEMORY_GRAPH.md) (person-free knowledge graph) ·
[signal-inventory.md](signal-inventory.md) (feature catalog + SHIP/REJECT verdicts) ·
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) · [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) ·
[full doc map](INDEX.md).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
