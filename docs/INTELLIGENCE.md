# CourtVision Intelligence Layer

The intelligence layer sits between raw CV tracking and the prediction models. It is **80 artifacts (~10 MB of parquet + json)** derived from broadcast-video tracking, NBA Stats API, and play-by-play microstructure. Every artifact answers a specific question the prediction stack would otherwise have to guess at: *who is this player right now, what scheme is the opponent imposing, how does this matchup behave, is the model confident here?*

Artifacts themselves are gitignored (`data/intelligence/`) — they're regenerable from raw tracking + NBA Stats and they encode the moat. This doc is the public-facing **manifest**: what exists, what's in each file, how it plugs in.

> **Status (2026-05-28):** 80 artifacts populated. Coverage is uneven — some layers (lineup chemistry, similarity index) span thousands of rows; others (officials player-sensitivity, absence-effects) are early and small. Per-artifact row counts are listed below so the maturity of each signal is legible at a glance.

> **Player & team dossiers:** The intelligence layer also synthesizes **1,249 per-player dossiers** (up to 28 statistical categories each, archetype-labeled, scheme-tagged) and **30 per-team scheme cards**. See **[docs/PLAYER_INTELLIGENCE.md](PLAYER_INTELLIGENCE.md)** for the full showcase with real dossier examples (Jokić, SGA, Sam Hauser) and honest scope statement.

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

- **Prop model for tonight's LeBron PTS** → loads `current_form_profiles` (trend tag + driver), `matchup_deviations` (LeBron-vs-MIN delta), `per_player_confidence` (volatility-adjusted Kelly multiplier), `officials_player_sensitivity` (ref tightness sensitivity), `pace_adjusted_cv` (pace-normalized baseline).
- **In-play endQ3 winprob** → consumes `ingame_momentum` (H1 → H2 delta vector), `clutch_cv_split` (clutch elevators vs. shrinkers), `quarter_profiles` (per-quarter velocity baseline), `coaching_adjustments` (whether the trailing team is mid-adjustment).
- **Bet filter / sizing** → reads `cv_quality_per_game` (gate by tracking quality), `confidence_curves` (per-EV-decile reliability), `anomaly_log` (suppress bets on players currently outside their baseline).
- **Possession simulation** → the player-level Monte Carlo (`src/sim/`) reads `data/cache/team_system/{player_rates, team_rates}` plus the scheme / clutch / rest context tables as per-possession rate multipliers, so an intelligence finding (a clutch-usage elevator, a scheme tilt) propagates directly into simulated game outcomes and same-game-parlay joint pricing.

**The loop closes here.** The self-improving discovery loop (`src/loop/`) doesn't only *consume* this layer — it *extends* it. ARM A writes new `signals/<name>.py` leaf signals (each gated by expanding walk-forward + null-shuffle permutation + Benjamini-Hochberg FDR); ARM B writes new `intel/*.py` atlas sections back into the player profiles, with REAL-vs-unknown fields explicitly marked. Artifacts are added only after passing the gate, and most candidates are correctly rejected. The sim's structure is validated but **no betting edge is claimed** — see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md#possession-sim--structure-validated-betting-edge-not-claimed).

---

## Layer inventory

### 1. Player identity & archetype — *who is this player*
| Artifact | Rows | What it encodes |
|---|---:|---|
| `player_fingerprints.parquet` | 214 | PCA-reduced player vector + archetype assignment + distance from centroid |
| `player_fingerprints_kbest.parquet` | 230 | K-best feature variant of the fingerprint (more robust to missing features) |
| `player_archetype_definitions.json` | — | Archetype label dictionary (e.g. *Slashing Wing*, *Stretch Big*, *Rim-Runner*) |
| `player_atlas_viz.png` + `player_atlas_feature_list.json` | — | 2D atlas viz of all players + the features that defined each axis |
| `archetype_drift.parquet` + `archetype_drift_signals.json` | 128 | Players currently transitioning archetypes (e.g. wing → primary handler), with consistency scores |
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
| `streak_signatures.parquet` + `streak_signatures_summary.json` + `streak_excluded_players.json` | 149 | Per-game streak state vs season average; excluded list = players whose streaks are noise, not signal |
| `anomaly_log.parquet` | 812 | Per-game anomalous performances with top-3 features driving the anomaly |

### 3. Matchup & scheme — *what is the opponent imposing*
| Artifact | Rows | What it encodes |
|---|---:|---|
| `defensive_schemes.parquet` + `scheme_indicators.json` | 30 | Per-team dominant scheme tag + sub-scores (drop, paint protection, perimeter denial, pace control, iso force, closeout) |
| `position_scheme_interactions.parquet` + `position_scheme_signals.json` | 315 | Position × opponent-scheme stat deviation with t-stat + p-value |
| `archetype_scheme_interactions.parquet` + `archetype_scheme_advantages.json` | 108 | Same as above but at archetype level — which archetypes feast vs. each scheme |
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
| `absence_cv_impact.parquet` + `star_absence_effects.json` | 5 | Beneficiary effects when a star is out (early; sparse) |

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
| `officials_player_sensitivity.parquet` | 0 | Per-player ref-sensitivity (placeholder; signal not yet populated — see *Limitations*) |
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

## What's honest about this layer

- **Row counts above are the truth.** Some layers (similarity 26K, shot-clock buckets 8.5K, lineup chemistry 4.7K) are mature. Others (absence-effects 5, officials player-sensitivity 0) are scaffolded but sparse — the framework exists; the signal isn't fully populated yet.
- **Significance is recorded where applicable** — `t_stat`, `p_value`, `p_value_adj` columns live in the parquets. Most signals are corrected; a few sub-100-row tables aren't significant on their own and only earn weight when stacked.
- **CV quality gating is real.** `cv_quality_per_game.parquet` (3,560 game-slots) feeds the bet-construction filter — a prediction on a game with `homography_valid_rate < 0.6` is downweighted regardless of model confidence.
- **The intelligence layer regenerates from raw tracking + NBA Stats.** Nothing here is hand-edited. Every signal is reproducible from a fresh `data/` snapshot.

## Limitations

1. **Officials player-sensitivity is empty (0 rows).** The aggregation pipeline runs but per-player ref-tightness deltas aren't passing the significance gate yet — needs more games per ref crew.
2. **Absence-effects has 5 rows.** Star-out / beneficiary attribution only fires on very clean absence games; most are confounded by simultaneous injuries.
3. **Similarity index covers 1,214 player-games.** Earlier games + non-tracked games have no neighbors.
4. **Compound candidates (atlas A × atlas B) are 10 rows.** Combinatorial search is gated to high-prior pairs; broadening is queued.
5. **Several layers don't have a public R² / Brier number** because they're not standalone models — they're inputs to models. The validation surface is the downstream prop / winprob walk-forward, not the intelligence artifact itself.

## Reproducing

Builders live under `scripts/intelligence/` (and a few in `src/intelligence/`). Top-level driver is `scripts/intelligence/build_all.py`; per-layer scripts can be run individually. Required inputs: `data/tracking/*` (CV tracking), `data/nba/*` (gamelogs), `data/cache/inplay_pbp_microstructure.parquet` (microstructure).

Regeneration takes ~25 min on the dev box for the full 80-artifact pass. The artifacts are kept out of git both because they're large and because they encode the proprietary derivation; the **schema and counts on this page are the public commitment**.
