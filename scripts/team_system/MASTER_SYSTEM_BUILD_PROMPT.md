# MASTER SYSTEM BUILD — the never-stop, every-aspect-of-basketball prediction machine

> Paste this whole file as the first message of a fresh session. It is the standing brief for an
> **autonomous, multi-agent, never-stop build**: turn EVERY measurable aspect of basketball into
> signals → route them into domain models → compose models into simulation engines → fuse engines into
> ONE calibrated prediction → re-price live from the play-by-play in milliseconds → and keep doing this,
> self-calibrating and self-cleaning, forever, until the user says stop. Opus orchestrates; Sonnet builds;
> Haiku does bulk search/extraction/validation. Run python from `C:\Users\neelj\nba-ai-system`; ascii
> prints; GPU (torch/CUDA, RTX 4060) for anything that touches many entities/sims; prefix background Bash
> with `cd /c/Users/neelj/nba-ai-system &&`.

---

## 0. NORTH STAR
Every aspect of basketball imaginable feeds as many models as it can, those models feed as many engines as
they can, the engines run simulations, and the simulations fuse into the single best prediction of what will
happen on the court — pregame and live. The system **never stops iterating**, **auto-calibrates**, **wires
every validated signal automatically**, **carries zero redundancy**, and **runs as fast as the hardware
allows**. The goal is not a model; it is a self-improving machine that rethinks the sport from the floor up.

**THE ONE HARD LAW that makes the ambition real instead of noise:** scale is the enemy of truth unless every
candidate must survive *out-of-sample, cross-season, FDR-controlled* validation before it touches a
prediction. At tens of thousands of candidates, ~N×(false-positive-rate) will "validate" by chance. So the
deliverable of the foundry is the **rejection machinery**, not the proposer. "Most reject" is the product.
Measure progress by **signals that SURVIVE cross-season**, never by signals created. (This is why the
historical *marginal* point prediction is already at its ceiling — see §DISCIPLINE; the wins are in the
JOINT/SHAPE/in-game/freshness layers and in the META layer, not in piling features on the point model.)

---

## 0.1 INVARIANTS — NEVER violate these, no matter what an iteration "discovers" (re-read every wake)
These are HARD GATES, not prose to remember. An unattended multi-day loop erodes discipline first under
"never stop" pressure; convert each law to an enforced check. **NEVER:**
1. ...auto-apply, flip ON, or enable any flag/weight/calibration in a serve/golive/production path. Everything
   the loop produces is a default-OFF, gated, **byte-identical-when-OFF** PROPOSAL. A human flips flags.
2. ...place, stake, size, or recommend a real-money bet, or emit a "bet this" output. Projections only —
   always labeled "projection / paper, NOT a bet, NOT proven forward."
3. ...write to / commit / push any public or recruiter-facing file or git (README, docs/PUBLIC_*, CLAUDE.md,
   the HF demo). Publishing and git are human-only actions. The loop writes ONLY to registries, EDGE_GATE,
   vault/Intelligence, MEMORY.
4. ...calibrate, NB-resample, conformal-shift, or refit anything that moves the **AST marginal/edge** — AST
   stays RAW by name (calibration kills it +7.22%→+1.12%, n=4,210). Any change that moves AST ROI auto-reverts.
5. ...loosen/skip/special-case a gate, lower a threshold, delete a test, or pool playoffs into reg-season to
   force a pass. A gate change is a human-approval item. Goodharting a metric = REJECT.
6. ...re-propose a REJECTED signal **family** (run-wide rejection set is binding — §4A). No re-rolling a
   transform with a different window/threshold until it passes by chance.
7. ...report an edge/ROI number without its CI, n, corpus, and regime; never pool playoffs into a headline;
   always label playoff/Finals context "NO PROVEN EDGE — do not bet the model here."
8. ...let the live (LLM-free) path read a STALE/unvalidated artifact, or fabricate a value when a feed is
   stale/blocked — fall back to last-known-good and log the gap.
9. ...exceed the §6A budget ceilings, grind an EXHAUSTED frontier, start hidden background processes, leave a
   spawned process unreaped, run >1 in-game poller, retry the BLOCKED stats.nba.com, or write a non-BOM/
   non-ASCII PowerShell file (5.1 parse-abort that froze the stack before).
10. ...overwrite a registry/artifact without the staging→validate→atomic-rename→.bak transaction, ship a change
    to a surface with no regression test, or call a change "board-green" without its own new test + the
    byte-identical-OFF assertion.
11. ...treat a SCOUTING/descriptive signal (effect spine, matchup intel, lineup synergy, clutch) as a marginal
    point feature or an edge claim — it is leak-prone; intelligence/JOINT-only until it independently clears
    cross-season.
**ALWAYS:** numbers (CI/n/corpus) every step · cross-season + leak-free before any edge claim · means preserved
on any calibration · provenance-stamp + transactional-write every artifact · record win OR honest-reject · ONE
lever per iteration · read `state.json` from disk on every wake.

---

## 1. LOAD FIRST (read in order, then act — do not re-derive what's measured)
0. **`data/registry/state.json`** (the loop cursor — §7.6) + **`data/registry/iteration_ledger.parquet`**
   (what's already been tried + its verdict — §7.3). If state.json exists you are RESUMING a days-long run:
   read the cursor, honor the phase (§7.0), and never re-try a barred `lever_id`. If it does NOT exist, this is
   the first-ever boot — create the spine (§9.0) before anything else. THIS is how the run survives resets.
1. `MEMORY.md` (the index; note it is bloated + has drift — restructuring it is task §8).
2. `docs/_audits/EDGE_GATE_2026-06-07.md` — the honest map: proven edges, rejects, the iteration logs,
   the ENABLE CAMPAIGN table (8 flags ON, 6 edge-killers OFF with fresh numbers).
3. `vault/Intelligence/_Simulation_Signals.md` — the live signal catalog (§1–§15: rates, roles, attribute
   vault, effect spine, context effects, interactions, defense chain, ft/tov force, dispersion, anchor,
   clock engine, matchup resolver, attribute clash, team clash, **§13d engine ensemble**, deep memory).
4. `data/registry/signal_registry.parquet` (signal_lab) + `data/registry/signal_edge_registry.parquet` —
   the current 21-tested / 5-validated / 16-rejected registry. Two of the 5 "validated" carry manual
   CAVEATs (opp_position_defense_reb = sign-backwards confound DO-NOT-WIRE; oreb_matchup = engine-redundant)
   — reproducing those two auto-rejections is the foundry's TRUST GATE (§3).
5. The spine scripts (read before extending): `scripts/team_system/signal_lab.py` (4 gates — **two leak
   sites to FIX before extending: `:87` `old[old.name!=name]` OVERWRITES the failure record (must become an
   append-only test-event log, §4A); `:71` split-half uses a univariate corr-sign proxy weaker than the OOS
   lift it gates (must become a partial-effect-controlling-for-baseline check, §4G)**),
   `signal_orchestrator.py` (panels + WIRE/CAVEAT patterns + `--status`), `cross_season.py` (GATE-X over
   the 560k legacy corpus + edge_walkforward wrapper), `build_legacy_possessions.py` (548–560k poss,
   2022-23 + 2023-24), `predict_ensemble.py` (the 7-engine fuser, currently EQUAL-WEIGHT — its own docstring
   says no reliability backtest exists yet; §4D refit is BLOCKED until one does, or you'll fit in-sample),
   `engines/__init__.py` (the engine interface contract), `edge_walkforward.py` (cross-season prop bar),
   `calibrate_all_props.py` (the shapeErr scorecard), `update.py` (the refresh pipeline), `learn_ledger.py`.
   Note: `engine_power_ratings.py` uses `df.iterrows()` over 560k rows + `lru_cache` + per-call parquet reads
   — the canonical ANTI-PATTERN (§6.2) not to propagate 10,000×.

## 2. WHAT EXISTS — USE IT, DO NOT REBUILD
- **Engines (7):** `engines/engine_{player_impact,four_factors,power_ratings,team_score,attribute_matchup}.py`
  + `possession_mc` (basketball_sim/fast_sim, anchored marginals, GPU) + `clock_trajectory`
  (game_clock_sim). Fused by `predict_ensemble.py` (auto-discovers `engine_*.py`).
- **Calibration (ON in golive):** CV_COUNT_NB, CV_COUNT_STL, CV_QUARTER_IDENTITY, CV_QUANTILE_CAL,
  CV_ROW_SIGMA, CV_INGAME_SIGMA, CV_ARCHETYPE_CORR, CV_BET_POLICY=reb_ast. Board: `pytest
  tests/test_sim_engine.py -q` (5 must pass).
- **Intelligence:** 87-attr vault (927 players) → folded into 660 notes; matchup resolver, attribute clash,
  team clash; per-entity effect spine (scouting only — faint +0.131, NOT wired to the marginal).
- **Foundry spine:** signal_lab 4 gates (OOS-lift / split-half / orthogonal<0.92 / material), signal_edge
  (ROI/CI vs real odds, ≥2 corpora, playoffs separate), `cross_season.py` GATE-X (poss_dur REPLICATES
  −2.06/−2.01%; after_to does NOT, +0.0% — substrate-limited).
- **Data substrates:** `data/cache/team_system/` (player_rates, recency_rates, attribute_vault,
  player_ratings, league_team_game [30 teams], team_defense_league, legacy_possessions [560k×2 seasons],
  pbp_possessions, secondary_targets, team_game [NYK/SAS q1-q4], assist_network). CDN PBP source =
  cdn.nba.com liveData (stats.nba.com is BLOCKED). The in-game fast harness pattern
  (`_ingame_fast_harness` + cached projection table) scores an adjustment in ~0.1s.

---

## 3. TARGET ARCHITECTURE — the layered machine (build toward this; everything registry-driven, hash-deduped)

```
  DATA SOURCES  (PBP liveData · box · tracking/CV · schedule · injuries · odds open/close)
        │  parsers (Haiku bulk) → as-of, leak-free
        ▼
  SIGNAL LAYER  (tens of thousands)   data/registry/signal_registry.parquet
        │  signal_id = hash(grain+entity+definition)  → DEDUP is structural (re-register = no-op)
        │  each: grain, domain_tag, source, causal_sign, asof_fn, status, gateA_*, gateX_*, judge_*
        ▼  routed by domain_tag (a signal that doesn't fit one model feeds ALL models of its domain)
  MODEL LAYER  (thousands)            data/registry/model_registry.parquet
        │  one model per (DOMAIN × entity-scope): e.g. transition_model[team], rim_finish_model[player],
        │  help_def_model[lineup], fatigue_model[player], clutch_model[team], foul_draw_model[player]...
        │  a model = the VALIDATED signals of its domain → a component prediction (PPP / rate / mult)
        │  model_id = hash(domain+scope+signal_id_set+method);  auto-built, auto-validated, deduped
        ▼  models feed engines (each engine consumes the domain models it needs)
  ENGINE LAYER  (many)                data/registry/engine_registry.parquet
        │  possession_mc · four_factors · power_ratings · team_score · attribute_matchup · clock_trajectory
        │  · + new engines spun from new domain models (transition-engine, matchup-physics-engine, ...)
        │  common predict(home,away,ctx)->{win_prob,margin,total,margin_sd,n_models,n_signals,notes}
        ▼  reliability-weighted fusion (learned cross-season, NOT equal-weight)
  ENSEMBLE  (one)                     predict_ensemble.py + weights from the backtest
        │  fused margin/win-prob + engine-disagreement = model uncertainty + clutch overlay
        ▼  continuous, per-game, board-gated
  CALIBRATION  (online)               data/registry/calibration_registry.parquet
        │  per (prop/engine/context): shapeErr, coverage, reliability; auto-updated each game
        ▼
  SERVE:  pregame slate  ·  IN-GAME FAST PATH (PBP→GPU re-price every possession, <500ms, NO LLM in loop)
```

**No-redundancy mandate — EXACT SPEC (build this, don't paraphrase it):**
- **Content hash:** `signal_id = "sig_"+blake2b(canon,digest_size=12).hexdigest()`, `canon` = JSON dump
  (`sort_keys=True, separators=(",",":")`) of EXACTLY `{grain, entity_scope, domain_tags, source, formula_ast,
  transform_chain, asof_fn_name, causal_sign}`. `formula_ast` is the PARSED+normalized expression (commutative
  operands sorted, whitespace stripped) so `a+b`==`b+a`; float literals quantized to 6 sig-figs. The hash covers
  the DEFINITION, never the data (data freshness = a separate `input_hash`, §6.1). `register(defn)` is pure:
  compute id, if present return it (no-op, no write), else append; registration NEVER computes the value.
- **Registry physical layout (NOT one growing parquet — that is O(N²) at 10k+ rows):** append-only **sharded**
  parquet `data/registry/<name>/part-*.parquet` (one part per batch) + an in-memory `{id:row}` index loaded once.
  Writes = new part via temp-name + `os.replace()` (atomic, same volume); a `compact()` coalesces parts when
  count>64. NEVER read-concat-rewrite the whole registry per row (the current `signal_lab.py` pattern). Schemas:
  `signal_registry{signal_id, grain, entity_scope, domain_tags, source, formula_ast, transform_chain, asof_fn,
  causal_sign:int8, input_hash, honesty_class, bet_wireable:bool, status(proposed|validated|rejected|retired|
  caveat), gateA_rel:f32, gateA_fdr_q:f32, gateX_verdict, judge_sign_ok:bool, judge_engine_ortho:f32, n,
  coverage_pct:f32, created_utc:i64, builder, artifact_path}`; `model_registry{model_id, domain_tag,
  entity_scope, signal_id_set_hash, method, input_hash, oos_score, xseason_verdict, engine_node, status,
  artifact_path, created_utc}`; `engine_registry{engine_id, name, consumes_models[], owns_nodes[],
  reliability_weight, engine_corr, last_backtest_utc}`; `calibration_registry{key, shapeErr, coverage,
  reliability, n, updated_utc}`.
- **Dedup at scale (the O(N²) all-pairs is FORBIDDEN):** `dedup_pass` (1) buckets by `(grain,entity_scope,
  domain_tag)`; (2) within a bucket, SimHash/MinHash over each signal's per-game value vector; (3) confirms exact
  `|corr|>0.97` only on SimHash-collision shortlists → N·bucket-size, not N². Record every merge `retired→dominant`
  (never delete = knowledge). Nothing is computed twice (input-hash cache, §6.1); nothing is stored twice (hash).

**Directory layout (10k entities are DATA ROWS in registries, never 10k files — ~30 modules, not 10k):**
```
scripts/team_system/
  registry/  registry.py(sharded atomic I/O+index) schemas.py ids.py(content-hash)
  cache/     cache.py(CAS) dag.py(topo+stale) provenance.py(input_hash)
  signals/   foundry.py(grammar) gates.py(GATE-A+FDR) judge.py(sign+engine-ortho) asof.py
  models/    domain_model.py  (ONE class parameterized by domain×scope — thousands of ROWS, one module)
  engines/   engine_*.py(contract) base.py(build()+predict()+INPUTS/OUTPUT) dispatch.py
  ensemble/  predict_ensemble.py weights.py(cross-season reliability fit)
  harness/   fast_harness.py(cached-table scorer) smoke.py(board+stale+latency)
  loop/      run_loop.py(checkpoint/resume) watchdog.py gc.py(log+CAS rotation) stop_run.py
```

---

## 4. THE SUBSYSTEMS TO BUILD (each: Sonnet builds the module, Opus reviews, Haiku runs bulk; all gated,
board-green, registry-driven, GPU where it touches many entities)

### 4A. SIGNAL FOUNDRY — auto-propose → 5-stage funnel → only survivors enter models
- **PROPOSE** (`signal_foundry.py`): a **grammar** that enumerates candidate signals from un-mined PBP/CV/box
  columns × transforms (rate, share, as-of rolling, opponent-adjusted, split-by-context, interaction pairs)
  × grains. Each candidate declares: `grain, domain_tag, causal_sign, substrate_tag, asof_fn`. This can emit
  tens of thousands — that is fine ONLY because every one must clear the funnel. Dedup by hash on emit.
- **GATE-A (accuracy) — FDR controlled at the RUN level, not per batch (the single most important piece):**
  signal_lab 4 gates, leak-free, 5-fold group-by-game, PLUS a **running, registry-wide false-discovery budget**
  across ALL batches over the whole multi-day run. Per-batch Benjamini-Hochberg is NOT enough — m independent
  batches over days multiply the family-wise error. Implement **Benjamini-Hochberg-Yekutieli (dependency-robust)
  over the cumulative p-value pool** persisted in the registry, OR **online alpha-investing (LOND)** that spends
  a fixed FDR wealth (α=0.05) across the entire test stream and CANNOT be replenished by running more tests.
  - **Append-only test log:** every candidate ever tested — PASS **and FAIL** — is written immutably
    `{hash, family_key, definition, p, batch_id, asof, verdict}` (fix `signal_lab.py:87` which overwrites it).
  - **Anti-re-roll (the "test until significant" leak — defeats ANY FDR otherwise):** a `family_key =
    hash(grain+entity+transform-family, IGNORING tuning constants)`. Before evaluating, look up by hash AND
    family_key AND a near-dup fingerprint; if it or a |corr|>0.97 sibling was tested, it gets NO fresh
    independent test — prior p carries forward against the same budget. A family may be re-tested ONLY on
    genuinely NEW data it has never seen (a new season/window), using ONLY that data. A REJECTED family is
    permanent (§0.1.6); re-proposing a member is a no-op returning the rejection.
- **GATE-X (cross-season):** `cross_season.py` — possession grain → 560k legacy (both seasons must replicate
  same-sign, split-half stable); pts/ast props → edge_walkforward. **Hard gate where a substrate exists;
  honest `N/A` where it doesn't** (player-game/team-game/lineup have no cross-season substrate yet → flag,
  don't fake). EXTEND the legacy parser to tag `had_oreb` (2nd-chance, 1.337 PPP) + `fastbreak` so the full
  origin/transition family gets a real test instead of the post-TO-only proxy.
- **JUDGE (mechanized CAVEATs — the trust centerpiece):** `sign_sanity` (measured sign vs declared
  causal_sign → auto-reject confounds like opp_position_defense_reb) + `engine_redundancy` (orthogonality of
  the signal vs **the consuming engine's emitted prediction**, not the coarse lab baseline → auto-reject
  double-counts like oreb_matchup). **TRUST GATE: the foundry must reproduce the 2 hand-written CAVEAT
  rejections on the existing registry before it is trusted on new candidates.**
- **WIRE:** survivor → centered-at-neutral artifact (the `shotclock_curve.json` pattern) + default-OFF
  `CV_SIG_<id>` flag + auto board-green A/B → *proposal only; a human/owner flips* (nothing auto-applied).

### 4B. DOMAIN MODEL LAYER — "every transition signal → the transition model" (the user's core insight)
- A `DOMAINS` taxonomy (~70 in 5 families — `data/registry/domain_registry.parquet`, each row:
  `domain, family, scopes[], honesty_class, default_status`). Honesty class is ENFORCED by the router (see end):
  - **A · OFFENSE (create + finish):** transition (split off-TO / off-miss / off-make), halfcourt, early_offense,
    rim_finish, paint_touch, midrange, three_pt_catch, three_pt_pullup, iso, pnr_ballhandler, pnr_screener,
    post_up, off_ball_movement, screen_setting, playmaking, ball_security, shot_selection, spacing_gravity(SCOUT),
    foul_draw, oreb, ft_shooting.
  - **B · DEFENSE (contest + end — each pairs with an offense domain for the matchup clash):** rim_protect,
    paint_defense, perimeter_d, closeout_contest, pnr_coverage, switch_behavior, help_rotation, force_tov, dreb,
    foul_commit, transition_d, shot_quality_allowed.
  - **C · GAME-STATE / IN-GAME (drive the live path, mostly PBP):** possession_origin, shot_clock_state,
    bonus_penalty_state, score_margin_state, clock_period_state (incl. 2-for-1 / end-of-period heaves),
    clutch(SCOUT), momentum_run(NULL-default), timeout_state, dead_ball_set (ATO/SLOB/BLOB), lineup_on_floor,
    foul_trouble, substitution_state.
  - **D · PHYSICAL / SCHEDULE / CONTEXT (modulators):** pace, rest_fatigue, in_game_fatigue, travel(NULL),
    altitude(NULL), schedule_spot(SCOUT), physical_age, injury_load, availability, home_road, referee_crew(SCOUT).
  - **E · IDENTITY / MATCHUP / EMERGENT (compositional):** lineup_synergy(SCOUT), size_matchup, speed_matchup,
    positional_matchup, style_clash, role_usage, scheme_fit, matchup_history(SCOUT,small-n→shrink-to-league),
    defender_assignment(SCOUT; pair-level ρ.10 NOISE, defender-level .63 usable — gate hard).
  - `default_status=NULL` for momentum_run/travel/altitude (the 13-aspect study measured ~0 — they must RE-EARN
    a wire through the foundry, never be assumed).
- For each (domain × scope ∈ {player, team, lineup, matchup}) a `DomainModel` consumes the domain's VALIDATED
  signals → a component prediction with its own confidence (empirical-Bayes shrink). A signal carries a **set**
  of `domain_tags` (e.g. "drive-and-kick rate" → playmaking + paint_touch + three_pt_catch) and routes to EVERY
  model of EVERY domain it touches — many-to-many. Auto-validate (beat the domain's naive baseline OOS + cross-
  season?); fails are recorded-rejected (knowledge), not deleted. `model_registry` keys by hash.
- **THE DOUBLE-COUNTING CONTRACT (the crux of many-to-many → engines — without it the same effect counts N×):**
  1. Domain models predict in **non-overlapping units** — a *multiplier* (rim_finish → make-prob mult), a *rate*
     (force_tov → TOV%), or a *PPP-by-possession-type* (transition → off-TO PPP). An engine composes them by the
     possession identity (`PPP = Σ_type share·PPP_type`; `make = base × Π mult`), NEVER by adding two estimates
     of the same quantity.
  2. The JUDGE's `engine_redundancy` runs at the **engine boundary, leave-one-model-out:** a model is admitted to
     an engine only if its component is orthogonal to that engine's prediction with the model removed (|corr|>0.92
     → redundant FOR THAT ENGINE; may still join a different engine). This generalizes the `oreb_matchup` CAVEAT.
  3. **One canonical owner per (quantity × engine)**, recorded as `engine_node` in `model_registry`; a second
     model touching the same node is rejected OR composed as the residual the owner doesn't explain. `dedup_pass`
     flags violations.
- **Substrate-honest wiring (BINDING):** a signal/model whose grain has no cross-season substrate (player-game
  box, team-game, lineup) is permanently `honesty_class=SCOUTING / bet_wireable=false`: it may inform the
  war-room read + notes + the JOINT/SHAPE distribution, but NEVER an engine path that produces a stake/Kelly/
  published edge. Only `PROVEN-OOS` (cross-season + frozen-season-survived, §8 law 9) is bet-wireable. The
  router blocks SCOUTING domains from any marginal-affecting model until they independently clear GATE-X.
- Engines declare `consumes_models[]` → a validated domain model lifts every engine that consumes it (the
  many-to-many multiplier = the §7.4 "Reach" term).

### 4C. ENGINE LAYER — decorrelated methodologies, each consuming domain models
- Refactor the 7 engines to pull from the domain-model layer (not ad-hoc team aggregates); each declares
  `consumes_models[]` + `owns_nodes[]` so the double-counting contract (§4B) + the ensemble's shared-variance
  down-weighting are queryable. Keep the common `predict()` contract + n_models/n_signals.
- **An engine earns its place ONLY by being a genuinely DIFFERENT methodology (a decorrelated VIEW, not a
  re-weighting of the same rates).** AUDIT the current 7 first: player_impact / four_factors / team_score /
  attribute_matchup all ultimately read the same rate+vault tables → their margin ERRORS are correlated. Measure
  the cross-engine error-correlation on the cross-season backtest; treat highly-correlated engines as ONE
  effective view in fusion (don't let 4 redundant aggregations pose as 4 independent votes). Add `engine_corr`
  (error-corr to the existing ensemble) to the registry; admit a new engine only if it **lowers ensemble
  variance**, not merely adds a vote. New engines that consume information the box engines structurally cannot:
  1. **engine_shot_quality (xPTS):** points from shot location×type×defender-proxy×shot-clock EV vs opponent
     shot-quality-allowed — an EV view, not a rate view.
  2. **engine_lineup_markov:** a possession-state Markov chain over {origin, shot-clock band, outcome} per
     lineup → stationary PPP × pace — a stochastic-process view; the home of the shot-clock/origin domains.
  3. **engine_fatigue_schedule:** a rest/load margin adjustment from the schedule graph only (rest diff, B2B,
     trip, minutes trajectory), no box stats — a pure-context view, ~0 correlation with talent.
  4. **engine_pace_tempo:** possessions from the two teams' pace-imposition style-clash, decoupled from
     efficiency (total = pace × PPP, separately weighted).
  5. **engine_ft_environment:** game FT volume from crew + foul-draw/foul-commit identities → FT-point
     contribution — a whistle process, not a shooting process.
  6. **engine_matchup_physics:** assignment-level positional clashes (each offensive facet vs its specific
     defender/scheme, size/speed/switchability) — the §13b clash made predictive, distinct from the team-
     aggregate attribute_matchup.
  7. **engine_bayesian_power:** a hierarchical Bayesian/Elo latent team-strength updated game-by-game → margin +
     a principled posterior SD (the cleanest honest-uncertainty source; top-down, decorrelated from bottom-up).
  8. **engine_market_anchor (meta, READ-ONLY):** when an opening line exists, treat the market as one view and
     price the ensemble-vs-market DISAGREEMENT (the freshness signal + a phantom-edge gate) — NEVER copy the
     line into the marginal (circular).
  9. **engine_tracking_spacing (CV-fed, when tracking exists):** spacing/gravity/defender-distance/drive-geometry
     → PPP — the one view using information no box engine can see (the moat). Build gated behind tracking avail.

### 4D. RELIABILITY-WEIGHTED ENSEMBLE — learn the weights (the meta "retrain", can't overfit the marginal)
- Leak-free cross-season backtest **on TRAIN+VALIDATION seasons only (NEVER the FROZEN season, §8 law 9)**
  scoring each engine per game (Brier/log-loss on win-prob, RMSE on margin/total) → learn fusion weights,
  replacing equal-weight. Re-fit only as new seasons/games accrue (never in-sample). **BLOCKED until a real
  leak-free cross-season reliability backtest exists** — equal-weight stays the shipped default until then
  (manufacturing in-sample weights to satisfy this is a direct overfit-launder; don't).
- **Correlation guard (disagreement must be REAL):** weight off the engine **residual** correlation matrix
  (per-game error vs realized), NOT the prediction correlation (high by construction — all engines share the
  anchor marginals). Use constrained regression with a redundancy penalty / GLS stacking so residual-corr>~0.9
  engines split one engine's weight. Report `N_eff = (Σw)²/Σ(w·Cov·w)`; scale the "disagreement = uncertainty"
  overlay by `N_eff` — when engines are correlated, disagreement is NARROWER than it looks → WIDEN uncertainty,
  don't narrow it. Retire any engine whose marginal contribution to validation Brier ≤ 0.
- Do NOT auto-"fix" the team-total anchor asymmetry toward possession_mc (it does NOT generalize on team-total,
  acc .48); any refit is REJECTED if it lowers the proven AST edge or the calibrated SHAPE scorecard.

### 4E. CONTINUAL-CALIBRATION LOOP — auto-calibrate every prop + engine, every game
- Extend `update.py`+`learn_ledger.py`: after each game, grade every engine + every prop (shapeErr, coverage,
  reliability), update the calibration_registry + engine weights (Bayesian update), board-gate (no regression
  ships), record the delta. The "keep retraining" intuition, done at the calibration/meta layer.
- **The loop is FORBIDDEN from touching the protected-raw stats.** (a) AST (and any `keep-raw` stat) is
  calibrated for SHAPE/coverage ONLY, never LEVEL — the mean/median is anchor-owned; the loop may not shift it
  toward the line (CV_PREGAME_CAL killed AST +7.22→+1.12%). (b) Calibration is **mean-preserving by
  construction** (NB mean=λ, quarter-weights sum-preserved); a step that moves any prop MEAN is a BUG → revert.
  (c) Every step is **dual-scored**: it must improve a proper distribution metric (CRPS / shapeErr / coverage)
  AND not degrade the cross-season value-bet ROI CI-lower of ANY proven edge (re-run edge_walkforward as a
  regression gate) — improve-coverage-but-lower-a-proven-edge = REJECT. (d) Fitting the residual against the
  LINE (vs the realized outcome) is banned outright — that is fitting the market, not the truth.

### 4F. IN-GAME FAST PATH — PBP API → GPU re-price every possession, sub-second, NO LLM in the loop
- **LATENCY BUDGET (per possession, must hold on the 4060):** poll→parse PBP delta ≤50ms · incremental as-of
  snapshot (changed entities only) ≤100ms · GPU re-price all props+win-prob ≤250ms · serialize ≤50ms · slack
  50ms = **500ms total**. The hot path NEVER reads parquet, NEVER imports an LLM, NEVER rebuilds an engine.
- **Architecture (precompute → lookup, the `_ingame_fast_harness` pattern):** (1) **Pregame once:** materialize
  a `projection_table` (per player×stat: deployed `routed` full-game proj + remaining-fraction curve) + a
  precomputed **state→multiplier tensor** (period × score_bucket × foul_bucket × minutes_bucket), pin on GPU
  (~MB). (2) **Live per possession:** the PBP delta updates a small as-of state vector (CPU, O(changed players));
  re-pricing = a tensor gather/index into the precomputed tables + `cur + (routed−cur)·mult` — NOT a re-sim
  (microseconds; budget is dominated by poll+parse I/O). (3) Run the possession MC live ONLY at coarse cadence
  (timeout/quarter-end) for win-prob shape, n_sims sized so one batch ≤6GB and ≤250ms; interpolate between.
  (4) **Adaptive poll** 3–5s live / 15–20s dead time, never busy-poll; the poller is the ONLY long-lived
  process (reapable, single instance — §6B).
- **The live PBP→model map (every detail drives something fast; all numerical, LLM offline only):**
  possession origin (made / live-TO / dead-ball / OREB / inbound + fastbreak) → lineup_markov origin state
  (off-TO≈1.38, 2nd-chance≈1.34, halfcourt≈1.04) · shot-clock-at-action → shot_clock_state make/EV haircut ·
  lineup on floor (sub events) → re-select active 5, recompute on-court defense/usage/synergy for those entities
  only · foul count+period → bonus_penalty_state (in-bonus = every drive carries FT-EV) + foul_trouble (star at
  4 → minutes/aggression down, re-route usage like the OUT path) · score margin+clock → score_margin_state
  (blowout → garbage regime) + clutch leverage ramp + win-prob trajectory · timeout/ATO → timeout_state +
  dead_ball_set next-poss PPP, reset the momentum accumulator · minutes-load → in_game_fatigue (legs on late 3s)
  · momentum_run computed but **weight 0 by default** (measured ~0) — war-room only until it clears the live
  harness. (3) The **LLM offline** proposes new state→effect candidates (disposed by the leak-free harness) +
  the live natural-language war-room read + a rare-context guardrail. The LLM informs/narrates; never computes.

### 4G. SCORING DISCIPLINE — proper rules + minimum-N before any verdict
- **Use the proper scoring rule per output type, ALWAYS:** win-prob → log-loss + Brier (+ reliability diagram/
  ECE); point → RMSE (NEVER MAE-alone — it rewards the median-shrink artifact the project already burned on;
  a signal that wins on MAE but not RMSE is REJECTED); full distribution → CRPS + PIT-uniformity + interval
  coverage (shapeErr is a centered approximation — fine for shape, report CRPS for the full picture); money →
  ROI + bootstrap-95%-CI excluding 0, playoffs separated (never pooled).
- **Minimum-N gate (HARD, pre-verdict):** no VALIDATED/PROVEN/REJECTED-as-edge verdict below the per-grain N
  floor: possession ≥50 games/season; **prop money ≥100 bets/corpus** (below → `directional-insufficient-n`,
  NEVER `PROVEN` — EDGE_GATE's n=14/33/36 verdicts are explicitly noise); win-prob ≥500 games. Below floor the
  only legal verdict is `provisional`.
- **Stability gate must be multivariate:** replace signal_lab's univariate corr-sign split-half (`:71`) with the
  signal's **partial effect controlling for the baseline** (coefficient/SHAP sign-consistent AND within ~2×
  magnitude across split-halves) — so a signal whose "stability" is just baseline correlation fails, as it should.

---

## 5. MEMORY / KNOWLEDGE — make it 10× better, 10× more efficient, ZERO redundancy
- The registries (signal/model/engine/calibration parquet) ARE the operational memory: queryable, hashed,
  deduped, the single source of truth. Obsidian notes are AUTO-GENERATED from the registries (no hand-kept
  duplication — fold scripts read registries; a fact lives in exactly one place).
- Restructure the Claude memory: `MEMORY.md` is bloated (~306 lines) and has drift (referenced files
  missing). Rebuild it as a compact, hash-indexed knowledge graph — atomic facts, deduped, one line per fact
  in the index, detail in topic files, dead/duplicate memories retired, `[[links]]` consistent. Add a
  `memory_lint` pass that flags duplicates + broken links + stale file:line citations.
- Every artifact (parquet/json/note) carries a provenance stamp (builder + inputs hash + as-of) so nothing is
  recomputed if inputs are unchanged (content-addressed caching = the speed AND the no-redundancy guarantee).
- **Transactional writes (every artifact, no exceptions):** write `<path>.staging` → run its validator (schema +
  range + non-null + a fixed golden-row checksum) + re-run the board + a downstream smoke-prediction A/B → only
  on all-green `os.replace()` to live, keeping `<path>.bak` (one deep) for instant rollback. A STALE upstream
  marks every descendant STALE and forces re-validation before any serve path reads it; the live (LLM-free) path
  refuses a STALE/unvalidated artifact and falls back to last-known-good (logged). No artifact feeds the live
  path until it has passed one full pregame board-green cycle.
- **Concurrency:** registry writes are SERIALIZED through a single writer behind `data/registry/.lock`;
  subagents RETURN rows to the orchestrator, they never write registries concurrently. After every write, assert
  no two rows share an id with different definitions (provenance integrity); on violation STOP + report.
- **memory_lint runs at the START of every session and BLOCKS** if MEMORY.md > 200 index lines OR any broken
  `[[link]]`/stale file:line citation: the session's FIRST lever must then be the memory cleanse, nothing else,
  until lint passes. Memory is append-with-dedup (sharpen the existing fact, never a second copy); NEVER delete a
  recorded rejection (knowledge), only de-duplicate it.

---

## 6. EFFICIENCY MANDATE (tens of thousands of signals/models must stay interactive)
- GPU/torch vectorization for anything over many players/sims/candidates; batch, don't loop.
- Content-addressed caching everywhere (recompute only on input-hash change); incremental per-game updates.
- Registry-driven lazy evaluation: a signal/model is computed only when an engine actually consumes it.
- The board (`pytest tests/test_sim_engine.py -q`, 5 pass) stays green after every change; fast harnesses for
  iteration (re-score in ~0.1s via cached projection tables, not full re-sims). **The 5-test board is NECESSARY,
  NOT SUFFICIENT** — it covers only the possession sim. Any new subsystem (foundry, registry, dedup, ensemble
  weights, domain model, calibration, live path) ships WITH its own regression test ADDED to the board, and is
  not "board-green" until that test exists + passes + asserts byte-identical when its flag is OFF.

### 6.1 CONTENT-ADDRESSED CACHE + DEPENDENCY DAG (the actual "recompute only what changed" mechanism — BUILD IT)
- **Cache key** `blake2b(node_id+":"+input_hash)`. `node_id` = the signal/model/engine content hash (§3).
  `input_hash` = blake2b over the SORTED `(upstream_path, mtime_ns, size, upstream_key)` of every declared input
  → valid iff (definition unchanged) AND (every upstream byte-identical). Files: `data/cache/cas/<key[:2]>/<key>.
  parquet` + `<key>.meta.json`. **Per-entity keying** for player/team/lineup (`node_id:entity:input_hash`) so one
  player's new game invalidates one player's signals, not the league's.
- **DAG:** every builder declares `INPUTS`/`OUTPUT`; `dag.py` topo-sorts; `materialize(node)` = cache-hit or
  compute+atomic-write+record. **Lazy:** materialize only when an engine actually calls it. A builder reading an
  undeclared input = a cache-correctness bug (lint it). **Acceptance:** after ingesting ONE new game,
  `dag.stale_count() < 5%` of nodes (assert it; 100% = the cache is broken). This is what makes a days-long tick
  run in seconds (incremental) instead of re-running the universe (the documented "rebuild every run" bottleneck).

### 6.2 GPU / MEMORY BUDGET (RTX 4060 = 8.59 GB → treat as 6.0 GB usable working set)
- **HARD VRAM CAP 6.0 GB.** Every GPU batch computes its footprint up front (`bytes = rows·cols·dtype·fudge(3)`)
  and CHUNKS so peak ≤ 6e9; loop over CHUNKS (fine) never over ROWS (banned). float32 for math, int16/int8 for
  indices/codes, bool masks. Move each chunk's result to CPU immediately; don't accumulate GPU tensors across
  chunks. Wrap all sim/scoring in `torch.inference_mode()`; `torch.cuda.empty_cache()` once per loop iteration
  (fight fragmentation over days). **GPU is for the dense inner loop** (possession MC, batched candidate scoring
  over >1k entities, the ensemble backtest); **CPU/numpy for** registry/DAG/dedup/hashing/FDR + anything called
  once per game (SRS, 30-team aggregates — GPU launch overhead dominates). A 10k×560k panel on GPU at once = OOM
  → chunk the candidate axis (e.g. 256 candidates × poss-panel, score per chunk).
- **ANTI-PATTERNS (the existing `engine_power_ratings.py` violates these — do NOT propagate 10,000×):** BANNED:
  `DataFrame.iterrows()` / per-row Python loops over substrate rows (vectorize: groupby/matrix/fixed-point);
  `pd.read_parquet` inside `predict()`/per-call (load substrates ONCE into the CAS, build the artifact ONCE,
  cache the BUILT object by input_hash — not `lru_cache(maxsize=1)` which dies per process + ignores data
  changes); re-`exec_module` of every engine per ensemble call (load once into a dispatch table; engines expose
  cached `build()` + cheap `predict()`).

### 6A. HARD BUDGET CEILINGS (enforced — the run STOPS when hit; soft budget logic is §7.7)
`data/registry/run_ledger.json` updated EVERY iteration (iter#, wall-clock, cumulative subagent calls, candidate
count, lever+verdict). CEILINGS (hit → write a STOP report, do not "just one more"): ≤6 concurrent subagents,
≤20 subagent invocations/iteration; ≤5,000 candidates/foundry batch (chunk larger grammars across iterations);
≤25 iterations OR ≤12 wall-clock hours per session → PAUSE + session summary (no auto session-2 without the
§STOP resume); 3 consecutive iterations with ZERO new cross-season survivors AND zero calibration gain →
frontier EXHAUSTED, STOP. Never spawn a subagent to retry a recorded-rejected lever. Recompute nothing whose
provenance hash is unchanged (a budget rule, not just speed).

### 6B. PROCESS / DISK / NETWORK HYGIENE (the run owns its own cleanup over days)
- Every spawned process registered in `data/registry/proc_ledger.json` (pid, cmd, start, purpose); reap ALL on
  PAUSE/STOP/error. NEVER `Start-Process -WindowStyle Hidden` for loop-internal work (orphans on Windows) — run
  foreground/tracked. The in-game poller is the ONLY long-lived process: a single named instance (kill prior
  before start; no duplicate pollers); a watchdog kills+restarts a >60s-silent poller.
- **Disk guard:** require ≥20 GB free before any large write else STOP (`data/cache` is already ~1.4 GB). CAS
  runs an LRU GC above a cap (default 20 GB; never evict an artifact a `validated`/`caveat` row references;
  rejected-candidate data is GC-eligible immediately). Logs rotate at 50 MB / 7 days. Delete `*.staging` on
  success; keep one `.bak`.
- **Network:** stats.nba.com is BLOCKED — cdn.nba.com liveData ONLY, never retry stats.nba.com in a loop. Any
  feed (odds/PBP/injury) stale-or-erroring → mark its input STALE, skip dependent levers, record the gap; NEVER
  fabricate/extrapolate a value into a prediction.
- **PowerShell:** any `.ps1` the loop writes/edits MUST be UTF-8 **with BOM** and ASCII-only (em-dashes/smart-
  quotes → PS 5.1 parse-abort that froze the live stack for days). Board check: assert `EF BB BF` prefix + ASCII.
  Prefer native `Invoke-WebRequest` over embedded here-strings.

---

## 7. MULTI-AGENT ORCHESTRATION (opus / sonnet / haiku) + THE NEVER-STOP LOOP

### 7.0 TWO PHASES — you are in exactly one; the BUILD-DONE gate is the boundary
The run has two phases and you MUST know which you are in (read `state.json.phase` on wake — §7.6).
- **PHASE = BUILD** — stand up the layered machine (§3, §4, §9.1–9.4). The loop's job is to *complete the
  scaffold*, not to chase edge. Build levers only. Exit BUILD only when the **BUILD-DONE CHECKLIST (§7.1)
  passes in full** — write `phase="IMPROVE"` to state.json, append a `PHASE-TRANSITION` row to the ledger,
  and STOP picking build levers.
- **PHASE = IMPROVE** — the never-stop self-improvement loop (§7.4+). Build levers are now forbidden unless a
  *validated* domain model/engine is missing a consumer (a wiring gap, not new scaffold). The loop optimizes
  the §7.5 metrics, one surgical lever at a time, forever, until the user says stop.

Never run IMPROVE levers while BUILD-DONE is incomplete (you'd be tuning a half-built machine), and never
re-open BUILD scaffold work once IMPROVE has started (that is scope-thrash — log it as a deferred item).

### 7.1 BUILD-DONE CHECKLIST (every box must be machine-checkable + checked before phase flips)
Write `scripts/team_system/build_done_check.py` that asserts each item and prints `BUILD-DONE: PASS/FAIL`
with the failing items. The phase flip is gated on its exit code 0 (the human-in-the-loop optionally confirms).
- [ ] **B1 Board green:** `pytest tests/test_sim_engine.py -q` = 5/5.
- [ ] **B2 Engines load + fuse:** `predict_ensemble.py` discovers ≥7 `engine_*.py`, each returns the full
      `predict()` contract (no NaN/None), and the fuser emits one prediction.
- [ ] **B3 Registries exist + schema-valid:** signal / model / engine / calibration parquet all present with
      the §3 columns; every row hashed; `dedup_pass` runs clean (0 unmerged |corr|>0.97 pairs).
- [ ] **B4 Foundry TRUST GATE passed:** the funnel reproduces the 2 hand-written CAVEAT auto-rejections
      (opp_position_defense_reb sign-confound, oreb_matchup engine-redundancy) — recorded in the ledger.
- [ ] **B5 FDR wired:** GATE-A applies Benjamini-Hochberg over a batch; a synthetic null batch (random
      signals) yields ≤ expected-FDR survivors (a planted-null test, not a claim).
- [ ] **B6 Cross-season bar reproduces:** `cross_season.py` returns poss_dur −2.06/−2.01% (±0.1) and
      after_to ≈ +0.0% (the known-good control).
- [ ] **B7 Domain router live:** ≥3 validated signals route into their `DomainModel` and ≥1 engine consumes
      ≥1 domain model end-to-end (n_models/n_signals > 0 on a real prediction).
- [ ] **B8 Reliability-weighted ensemble fitted:** fusion weights learned cross-season (NOT equal-weight);
      per-engine reliability recorded.
- [ ] **B9 Continual-calibration loop runs:** `update.py`→`learn_ledger.py` grades engines+props, updates
      calibration_registry, board-gates, appends a delta row — on a real (or replayed) game.
- [ ] **B10 In-game fast path measured:** `live_engine` re-prices the full board from a replayed PBP stream
      <500ms/possession with NO LLM in the loop.
- [ ] **B11 State + ledger spine exist:** `state.json` (§7.6) and `iteration_ledger.parquet` (§7.3) are
      written and re-read on a simulated restart.
- [ ] **B12 Memory not corrupting:** `memory_lint` runs; 0 broken `[[links]]`, 0 stale file:line citations.

### 7.2 ROLES + WHEN TO USE WHICH MODEL (budget discipline — the cost lever)
- **Opus** (you): plan, decompose, **score levers (§7.4)**, review every subagent output adversarially,
  decide WIRE/REJECT, write records. Opus is the scarcest token — spend it on JUDGMENT, never on bulk.
- **Sonnet** (parallel executors): build/extend ONE module to spec (one engine / domain model / gate /
  parser) with self-tests; return artifact + numbers. The default builder.
- **Haiku** (parallel bulk, cheapest): mass PBP/CV parse+extract, run the validation funnel over big candidate
  batches, dedup scans, memory-lint, registry queries, log greps — high-volume, low-judgment, deterministic.
- **ESCALATION RULE (default cheap, escalate on evidence):** start every sub-task at the cheapest tier that
  can do it (Haiku for extraction/funnel/scan, Sonnet for build, Opus only for cross-engine judgment). Escalate
  a tier ONLY when the cheaper tier fails its self-test twice or returns ambiguous numbers. Never use Opus for
  anything a script can compute — write the script (deterministic, free to re-run) instead of reasoning it out.
- **BATCH the fan-out:** propose/extract/validate candidates in one big Haiku batch (FDR needs the whole batch
  anyway), not one-signal-per-call. One Sonnet builder owns one module end-to-end (build+self-test+numbers) so
  there's no Opus round-trip mid-build. Target ≤ 1 Opus judgment call per lever, not per sub-step.

### 7.3 ANTI-LOOP / ANTI-DRIFT — the iteration ledger (the registries dedup SIGNALS; this dedups ATTEMPTS)
The signal/model registries stop you re-building the same *artifact*. They do NOT stop you re-*trying* the same
*idea* (e.g. "wire the effect spine as a marginal multiplier" — already KEPT-OFF, §8/EDGE_GATE) or two agents
doing the same work. Add `scripts/team_system/iteration_ledger.py` writing
`data/registry/iteration_ledger.parquet`, one row per iteration:

  `iter_id, ts, phase, frontier, lever_id (=hash(frontier+target+method)), agents_spawned, tokens_est,
   verdict ∈ {WIRED, REJECTED, NULL, BLOCKED, DEFERRED}, metric_before, metric_after, delta, board, notes`

Hard rules the loop obeys:
1. **Never pick a `lever_id` already in the ledger with verdict ∈ {WIRED, REJECTED, BLOCKED}.** A REJECTED
   idea is permanent knowledge — re-trying it is the #1 days-long failure. (NULL/DEFERRED may be retried ONLY
   if a *named precondition* changed — e.g. new data substrate, a new season — and you state which.)
2. **In-flight claim:** before spawning agents, append the row with `verdict=IN_FLIGHT` + `lever_id`. No second
   agent may take a `lever_id` that is IN_FLIGHT. This is the lock that stops duplicate work.
3. **NET-NEW-KNOWLEDGE detector (the dead-end escape):** an iteration "produced knowledge" iff it added a row
   with verdict ∈ {WIRED, REJECTED} OR moved a §7.5 metric beyond noise. If the **last 3 iterations on the
   current `frontier` are all NULL/BLOCKED → that frontier is EXHAUSTED**: write `frontier_status[frontier] =
   EXHAUSTED(asof, reason)` to state.json and the priority function (§7.4) drops it to score 0 until its
   precondition changes. This is how it moves on instead of grinding a dead end for days.
4. **Stuck-tripwire:** if 5 consecutive iterations are ALL non-knowledge (no WIRED/REJECTED, no metric move),
   STOP the loop, write a `STUCK` summary to state.json + `OVERNIGHT_MORNING_REPORT.md`, and wait for the user.
   Spinning with no net-new knowledge is the cost-blowup failure — fail loud, don't burn days silently.

### 7.4 THE PRIORITY FUNCTION — how Opus picks the ONE lever each iteration WITHOUT a human
Do not "intuit" the lever. Enumerate the candidate levers from state (the FIX/WATCH props, the untested signal
batches, the unconsumed validated domain models, the un-fit ensemble weights, the in-game gaps, the
memory/dedup debt), drop any whose `lever_id` is barred by §7.3, then SCORE each and take the argmax:

  **score = (Value × Confidence × Reach) / (Cost × (1 + StaleAttempts)) × FrontierAlive × PhaseFit**

- **Value (1–5):** expected effect on a §7.5 metric. A FIX prop (shapeErr>9) = 5; WATCH (5–9) = 3; a new
  validated domain model wiring = 4; a fresh candidate batch = 2 (most reject by design); a cosmetic/memory
  cleanse = 1. CLV/freshness + in-game are the documented money lanes → +1 when their data precondition is met.
- **Confidence (0.1–1.0):** P(this actually moves the metric), from prior ledger verdicts on the frontier and
  whether a substrate exists. Anything with no cross-season substrate caps at 0.4 (you can't prove it).
- **Reach (1–N):** how many engines/props/markets the win touches (a domain model feeding 3 engines = 3). This
  is the §4B many-to-many multiplier — prefer levers that lift many consumers at once.
- **Cost (1–5):** est. agent-tokens (Haiku batch = 1, one Sonnet module = 2, new engine + refit = 4–5). The
  denominator is what keeps days-long cost bounded.
- **StaleAttempts:** count of prior NULL/DEFERRED ledger rows on this `frontier` (decays repeat-grinding).
- **FrontierAlive ∈ {0,1}:** 0 if §7.3.3 marked the frontier EXHAUSTED (hard mute until precondition changes).
- **PhaseFit ∈ {0,1}:** 1 if the lever's type matches the current phase (§7.0), else 0.

Print the scored table (top 5 rows) each iteration BEFORE acting, so the choice is auditable and you don't
thrash. Ties → take the lower-Cost one (cheap knowledge first). If the argmax score < a floor (e.g. all
remaining levers are Value≤1 or Confidence≤0.2 and every real frontier is EXHAUSTED), the system has converged
on available data → write `CONVERGED` to state.json + the morning report and idle until new games/data arrive
(schedule the next wake at the next NBA game time; do NOT keep spinning).

### 7.5 THE METRICS THE LOOP OPTIMIZES (and how an iteration PROVES it helped)
The loop improves the SYSTEM, never just churns. An iteration "helped" iff it moves one of these the right way
AND board stays green AND (for any edge claim) it survives cross-season — recorded as a `delta` in the ledger:
- **Calibration:** prop `shapeErr` (calibrate_all_props), engine Brier (win-prob), coverage→nominal.
- **Accuracy:** cross-season MAE on margin/total (walk-forward only; in-sample does not count).
- **Edge (gated, never auto-applied):** ROI/CI vs real odds, ≥2 reg-season corpora, playoffs separate.
- **Validated-signal count that SURVIVES cross-season** (the §0 north-star — NOT signals created).
- **Health/debt:** board pass-rate, redundancy (unmerged dup pairs → 0), memory-lint (broken links → 0),
  in-game latency (<500ms/poss), token-cost per net-new-knowledge unit (must trend flat, not blow up).
A "win" requires a measured before→after delta beyond noise. No delta = NULL (record it; do not claim a win).
**Anti-Goodhart:** never optimize a metric by loosening its gate, by fitting in-sample, or by deleting a
failing test. If a metric improves only in-sample or only by relaxing a threshold, it is a REJECT, not a win.

### THE LOOP (never stop until the user says stop)
Each iteration:
1. **WAKE + READ STATE:** load `state.json` (§7.6) → know `phase`, last `iter_id`, `frontier_status`,
   token-budget remaining, any IN_FLIGHT row to resume. Then read live state: `signal_orchestrator.py
   --status`, `calibrate_all_props.py`, the registries, EDGE_GATE. (Cheap; Haiku can summarize.)
2. **BUDGET CHECK (§7.7):** if today's token budget is spent → checkpoint + schedule next wake; do not proceed.
3. **ENUMERATE + SCORE LEVERS (§7.4):** build the candidate list, drop §7.3-barred ones, score, print the
   top-5 table, take the argmax. (PHASE=BUILD → only build levers; PHASE=IMPROVE → only improve/wiring levers.)
4. **CLAIM IT:** append an `IN_FLIGHT` ledger row with the `lever_id` (the lock — §7.3.2).
5. **BUILD IT:** fan out Sonnet/Haiku at the cheapest sufficient tier (§7.2), batched. ONE lever — surgical;
   kitchen-sink overfits. Capture `metric_before`.
6. **VALIDATE:** leak-free + board-green (5/5) + cross-season for ANY edge claim. Adversarially review the
   subagent's numbers (Opus) — assume the agent is wrong until the numbers say otherwise.
7. **RECORD THE VERDICT:** update the registry + EDGE_GATE + memory + close the ledger row (verdict + delta).
   Win or honest-reject, it's net-new knowledge. Update `frontier_status` (EXHAUSTED if §7.3.3 trips).
8. **RE-SCORE to confirm** the gain is real (e.g. phantom edges shrank); update `state.json` (phase, iter_id,
   metrics, budget spent). Checkpoint.
9. **NEXT:** if BUILD-DONE just passed → flip phase (§7.0). If STUCK/CONVERGED → fail loud + idle (§7.4/7.3).
   Else START THE NEXT ITERATION (or schedule the next wake — §7.6). Numbers every step.

### 7.6 CHECKPOINT / RESUME — survive context resets + process restarts across days
A days-long run WILL hit context-window resets and restarts. The loop must be **resumable from disk alone**,
never from chat memory. Single source of truth = `data/registry/state.json` (the loop reads it on EVERY wake):

  `{ phase, iter_id, asof, frontier_status:{frontier:{status,asof,reason}},
     in_flight:{lever_id,agents,started_ts}|null, metrics:{shapeErr_worst,brier,xseason_mae,n_survivors,...},
     budget:{day, tokens_spent_today, tokens_cap_today}, last_board, next_wake_ts, status ∈
     {RUNNING,STUCK,CONVERGED,STOPPED}, notes }`

- **Write-after-every-step**, atomically (write `state.json.tmp` then rename) so a crash never leaves a torn
  file. The ledger (§7.3) is the append-only history; `state.json` is the current cursor.
- **On wake, ALWAYS re-derive truth from disk** (registries + state.json + ledger), never trust prior-turn
  memory — memories drift (see MEMORY.md's own drift warning). If `in_flight` is set, either finish that lever
  or roll it back to its `metric_before` and mark it BLOCKED before picking a new one (no orphaned half-work).
- **Scheduled wakeups:** when idling (CONVERGED / budget spent / waiting for the next game), set `next_wake_ts`
  and schedule the loop to resume then (the harness's cron/schedule). Do NOT busy-spin to "stay alive" — that
  is pure cost. The first action on every wake is "read state.json and continue from the cursor."
- **STOP FILE (the unattended kill-switch — the user is away for days):** check for `data/registry/STOP` at the
  TOP of every iteration AND before every subagent fan-out. If present → finish the current atomic write, reap
  all `proc_ledger` processes, write a STOP report (last lever, verdicts, open frontiers, resume note), set
  `status=STOPPED`, EXIT. The user stops with `New-Item data/registry/STOP -ItemType File`. NEVER ignore/delete
  it; there is no "just one more iteration." Build `scripts/team_system/loop/stop_run.py` in iteration 0 (hard
  kill: reap every proc_ledger pid, drop the STOP file, release the `.lock`) and document it at the top of the run.
- **`bot stop` / "stop" → set `status=STOPPED`, finish the in-flight lever cleanly (or roll back), write a
  final morning report, and halt.** Stopping is a first-class state, not a crash.
- **The loop PAUSES and asks the human (does not proceed) when** a lever would touch a serve/golive/public/git/
  real-money path · a change moves the AST edge or any prop MEAN or lowers the SHAPE scorecard · an ensemble
  refit wants to replace equal-weight as the shipped default · a registry-integrity/downstream-A/B/board check
  fails after a write (→ rollback to .bak, PAUSE) · all levers are feed-blocked · it is about to "fix" the
  team-total asymmetry toward possession_mc. Resume contract: every STOP/PAUSE leaves the system known-good
  (live files = last board-green; staging cleaned; processes reaped; lock released) + a human-readable report;
  the run NEVER auto-starts a new multi-day session — a human re-pastes the prompt to resume.

### 7.7 TOKEN / COMPUTE BUDGET over days (don't burn cost spinning)
- **Daily cap:** `budget.tokens_cap_today` in state.json. Each iteration estimates its spend (Cost in §7.4 ×
  a per-tier token constant) and decrements. At 80% → only Value≥4 levers; at 100% → checkpoint + next-wake.
- **Cost per net-new-knowledge** is the health metric (§7.5): tokens_spent / (#WIRED + #REJECTED this day). If
  it climbs while metrics are flat → you're spinning → trip the §7.3.4 STUCK tripwire early.
- **Prefer deterministic re-runs over re-reasoning:** anything verified once is a script + a ledger row; never
  pay LLM tokens to re-derive a measured number. The fast harnesses (~0.1s) are the iteration substrate, not
  full re-sims. Cache by input-hash (§5) so unchanged inputs cost zero.
- **Cap fan-out width:** at most ~6 parallel subagents per lever (FDR wants the batch together, but a swarm of
  50 agents per iteration is cost-blowup with no extra signal). One module = one Sonnet; one batch = one Haiku.

### 7.8 SAFETY / GUARDRAILS for unattended running (these are HARD; an unattended loop must not go rogue)
- **NEVER auto-apply un-gated.** Every validated change ships behind a default-OFF `CV_*` flag, centered at
  neutral. The loop *proposes + A/B-tests + records*; **a human/owner flips the flag.** Auto-flipping is the
  single most dangerous unattended action — forbidden.
- **NEVER loosen a gate, lower a threshold, delete/skip a test, or pool playoffs into reg-season** to force a
  pass. A gate change is itself a human-approval item. Goodharting a metric = REJECT (§7.5).
- **NEVER publish edge claims** (the public-repo rule, `feedback_edge_publish_pressure_hold_honest_line`). The
  loop writes to private registries/audits only; it never pushes, never posts, never emails an edge claim.
- **Board-red = halt:** if `learn_ledger` gate goes RED, STOP, write the regression to state.json + morning
  report, do not proceed (a half-validated loop must not stack changes on a broken board).
- **STOP CONDITIONS (any → idle/halt, never spin):** user says stop · STUCK (§7.3.4) · CONVERGED (§7.4) ·
  board RED · token cap hit · a subagent returns an un-reviewable/contradictory result twice. Human-in-the-loop
  is required only for: flag FLIPS, gate changes, anything that would publish. Everything else is autonomous.
- **Idempotence + rollback:** every lever must be revertible (gated flag OFF / artifact retired in registry).
  If validation fails mid-lever, roll back to `metric_before`, mark BLOCKED, do not leave the system dirtier.

---

## 8. DISCIPLINE — the hard-won laws (do NOT relearn the expensive way)
1. **Accuracy ≠ edge.** The historical marginal point is at the ceiling; calibration makes predictions
   HONEST (phantom edges die, real ones surface), it does not add marginal accuracy. Grow edge via
   JOINT/SHAPE/in-game/freshness + the meta layer, never by piling features on the point model.
2. **PROVEN = cross-season walk-forward**, never in-sample. A signal/model/engine/policy fit on season A must
   hold OOS on season B (CI excludes 0). The ONE proven prop edge = reg-season ASSIST value bets; PLAYOFFS
   have NO edge (don't bet the model there).
3. **A phantom edge (many props +EV / both sides / huge edges) is a MODEL BUG**, not money — fix the
   calibration; the survivors are the real disagreements.
4. **FDR control is mandatory at scale — over the ENTIRE RUN, not one batch** (BY / online alpha-investing +
   an append-only test log + the family-key anti-re-roll, §4A). Per-batch BH over days still manufactures false
   positives by the hundred; re-rolling a rejected family until it passes is the #1 self-deception.
5. **Never fake it. Record rejections.** Most candidates reject — that IS the deliverable. Never loosen a gate
   to force a pass. The discipline is the product. Proper scoring rule + minimum-N before any verdict (§4G).
6. **Board stays green; nothing auto-applied un-gated.** Validated changes are gated/centered-at-neutral
   (byte-identical OFF); marginals are anchor-owned; the sim's job is JOINT/SHAPE/in-game. The board is
   necessary-not-sufficient — every subsystem ships its own test (§6).
7. **No redundancy, ever** — content-hash-dedup signals/models; one source of truth; content-addressed caching;
   transactional writes + a registry lock (§5).
8. **Honest reporting + no autonomous publishing/betting.** Surface uncertainty (N_eff-scaled engine
   disagreement); every edge number carries CI/n/corpus/regime; never pool playoffs; distinguish a projection
   from a bet. The loop NEVER writes a public/recruiter file, NEVER pushes git, NEVER places/sizes/recommends a
   real-money bet (§0.1.2-3).
9. **The FROZEN VAULT season — the meta-layers' blindfold.** Exactly one full season is the FROZEN TEST set,
   NEVER read by the proposer, the gates, model selection, the ensemble weight-fit, OR the calibration loop —
   only by a final adjudication run (at most ~K=10 touches total; more = selection-contaminated → designate a
   new one + downgrade prior results to "suggestive"). A signal→model→engine→ensemble chain is PROVEN only if it
   survives the FROZEN season after every upstream layer was fit without it. This is the only defense against
   NESTED OVERFIT (each layer's "OOS" is the prior layer's training data; without a season nothing in the stack
   has touched, "cross-season" is just a second training set wearing an OOS costume).
10. **SCOUTING ≠ edge — the honesty class is router-ENFORCED, not advisory.** Descriptive/leak-prone domains
    (spacing_gravity, lineup_synergy, clutch, matchup_history, defender_assignment, schedule_spot, referee_crew,
    the effect spine) are `honesty_class=SCOUTING`: they shape the JOINT/SHAPE distribution + the war-room read
    only; the router BLOCKS them from any marginal-affecting model until they independently clear GATE-X cross-
    season. The effect spine's split-half +0.131 < the +0.2 trait bar is the worked example (heavily shrunk,
    joint-only). A SCOUTING signal that "feels" predictive is the most common leak; the class column makes
    wiring one to the point structurally impossible without a cross-season pass first.

---

## 9. START HERE (first moves; then never stop)

**On EVERY wake (incl. the first): read `data/registry/state.json` first.** If it exists with
`status=RUNNING/STOPPED/CONVERGED/STUCK`, you are resuming — go to §7's loop step 1 (read the cursor, resume
the in-flight lever or pick the next). The steps below are the FIRST-EVER boot (no state.json yet); they build
the spine, then PHASE=BUILD, then the §7.0 phase gate carries you into PHASE=IMPROVE.

### 9.0 First boot — create the autonomy + SAFETY spine BEFORE any modeling (resumable + safe from line one)
0a. Write `state.json` (§7.6 schema): `phase="BUILD"`, `iter_id=0`, empty `frontier_status`, a daily token cap,
    `status="RUNNING"`. Write the empty `iteration_ledger.parquet` (§7.3), `run_ledger.json`/`proc_ledger.json`
    (§6A/§6B), and `build_done_check.py` (§7.1).
0b. **Build the safety scaffolding (every §0.1 invariant must be ENFORCEABLE before day 2):** the STOP-file check
    + `loop/stop_run.py` (§7.6), the registry `.lock` + transactional staging→validate→atomic-rename→.bak write
    (§5), the content-hash + sharded registry I/O (§3), the CAS+DAG (§6.1), the disk/feed-stale/PS-BOM guards
    (§6B), and `memory_lint` (§5). Without these, every law is unenforceable on an unattended run — build them
    FIRST, before the foundry.

### 9.1–9.4 PHASE=BUILD (loop §7 with build levers only until BUILD-DONE §7.1 passes)
1. Confirm §2 state against current code (memories may be stale): board green, the 7 engines load, the
   registry counts, `cross_season.py` reproduces poss_dur −2.06/−2.01% (this is checklist items B1/B2/B6).
2. Stand up the registries (signal/model/engine/calibration schemas) + the **content-hash dedup** + the
   **provenance/caching** layer — the spine everything else hangs on (B3).
3. Build the FOUNDRY funnel (§4A) with **FDR + JUDGE first**, and pass the TRUST GATE (reproduce the 2
   CAVEAT auto-rejections) BEFORE proposing at scale (B4/B5).
4. Stand up `domain_registry.parquet` (the §4B ~70-domain taxonomy with family/scopes/honesty_class) + a
   **coverage scoreboard** — for every (domain × scope) cell: count {candidate signals, GATE-A survivors, GATE-X
   survivors, models built, engines consuming}. This makes "EVERY aspect of basketball feeds the prediction" a
   MEASURABLE matrix (green = a validated model exists + is consumed; grey = no substrate, honest N/A; red =
   substrate exists but no survivor). **Progress = the count of GREEN cells, never signals proposed.** Then build
   the DOMAIN-MODEL router (§4B) starting with the cleanly-validated signals (pbp_origin_transition's wireable
   parts → transition/possession_origin; rest_x_age → rest_fatigue/physical_age; shot_clock_leverage →
   shot_clock_state); extend the legacy parser (had_oreb/fastbreak) to unblock the transition+possession_origin
   families' cross-season test (B7); fit the reliability-weighted ensemble (B8); wire the continual-calibration
   loop + in-game fast path (B9/B10/B12).
5. **Run `build_done_check.py`.** When it prints `BUILD-DONE: PASS`, flip `phase="IMPROVE"` in state.json,
   append the `PHASE-TRANSITION` ledger row, and stop taking build levers.

### 9.5 PHASE=IMPROVE — loop §7 forever (the never-stop self-improvement loop)
Each iteration: read state → budget-check → enumerate+score levers (§7.4) → claim (lock) → build (cheapest
tier, batched) → validate (leak-free + board + cross-season) → record verdict+delta → re-score → checkpoint →
next. Frontiers: foundry batches · domain models · new engines · reliability-weighted ensemble · continual
calibration · in-game fast path · CLV/freshness (when data lands) · memory cleanse. EXHAUSTED frontiers mute
themselves (§7.3.3); STUCK/CONVERGED/board-RED/budget-cap idle the loop loud (§7.8). Highest-value lever each
time; ONE at a time; numbers every step; nothing un-gated; only the user (or an owner flag-flip) intervenes.

**The system's job is to make every aspect of basketball imaginable lead, through validated models and
simulation engines, to the single best prediction of what happens on the court — and to keep getting smarter
at it on its own. Build that. Don't stop until told.**
