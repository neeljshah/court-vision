# 01 -- Platform Architecture + the DATA->...->INTELLIGENCE Funnel

> Area owner doc for the deep-dive report. Scope: platform architecture, the
> DATA -> SIGNALS -> MODELS -> ENGINES -> PREDICTIONS -> INTELLIGENCE funnel, the
> kernel/adapter design, and the two halves (original NBA CV/AI system vs the new
> multi-sport betting-decision-support product).
>
> Honesty rails (binding): markets are efficient; the honest win is CALIBRATION,
> not a $-edge. No profit edge is claimed anywhere. Numbers below are calibration/
> sharpness (Brier/RMSE/ECE) and are sourced from `docs/JOB_EVIDENCE_PACKET.md`
> (the single truth source). Several famous figures are documented MEASUREMENT
> ARTIFACTS and are NOT repeated here as live results.

---

## 0. What IS the system, end-to-end (one paragraph)

Two systems share one repo. **Half A (origin, ~3 months, 1,470 commits)** is an
NBA broadcast-video computer-vision -> ML -> FastAPI production stack: YOLOv8
detection -> SIFT homography -> Kalman+Hungarian tracking -> OSNet/HSV re-ID ->
EasyOCR -> EventDetector produces court-coordinate tracking, which feeds a
multi-output prop/win-prob ML stack, a possession Monte-Carlo simulator, a
Kelly/CLV betting layer, ~99 FastAPI endpoints, and an autonomous signal-discovery
loop. **Half B (current frontier, 2026-06)** is a domain-agnostic, calibrated
multi-sport forecasting + betting-decision-support product: per-sport adapters
(`domains/<sport>/predictor.py`) emit a coherent pregame surface + an in-game
repricer, judged by a sport-blind eval gate, surfaced through a snapshot-backed
React/FastAPI front end and a paper-only auto-bettor with a CLV ledger. The stated
architectural direction is a sport-blind `kernel/` + thin `domains/<sport>/`
adapters; in practice the shared machinery currently lives in
`scripts/platformkit/`, and `kernel/` is an (almost entirely empty) aspirational
namespace.

---

## 1. INVENTORY -- components that EXIST and are USED

### 1a. Top-level navigation / truth-source docs
- `CLAUDE.md` -- agent onboarding; funnel one-liner; Task->Files table; rules import.
- `docs/JOB_EVIDENCE_PACKET.md` -- THE truth source: every claim + proof artifact + the do-not-claim list (retracted +18.38% / 0.119 / +54% / 78.11).
- `.planning/NOW.md` -- single source of truth for "what's done / what's next"; loop queue source.
- `docs/PLATFORM.md` -- the kernel/adapter thesis + the 4-sport calibration scoreboard.
- `docs/research/revamp/REVAMP_MASTER_PLAN.md` + `REVAMP_DECISIONS_AND_PHASES.md` -- the 12-workstream / 5-phase revamp map (snapshot keystone).
- `README.md`, `docs/PUBLIC_EVIDENCE.md`, `docs/INTELLIGENCE.md`, `docs/PREDICTOR_PLATFORM.md`, `docs/MARKET_EFFICIENCY_PROOF.md` -- public funnel narrative + intelligence manifest + efficiency proof.

### 1b. The kernel namespace (`kernel/`) -- ASPIRATIONAL, mostly empty
- `kernel/__init__.py` and ALL twelve subpackage `__init__.py` files (`brain/`, `calibration/`, `config/`, `data_infra/`, `decision/`, `fusion/`, `loop/`, `model_ops/`, `sim_framework/`, `spatial/`, `testing/`, `validation/`) are **1-line stubs** (`wc -l` = 1 each; 13 total). FINDING: the "sport-blind kernel" described in `docs/PLATFORM.md` is NOT populated here.
- The only non-stub kernel files: `kernel/config/*.py` (atlas_schema, clock, context, court, entities, game_state, pbp, registry, roster, speed, stats -- sport-config schema layer), `kernel/paths.py`, `kernel/testing/{conformance,domain_conformance_kit,fixtures,golden,invariants}.py`, `kernel/validation/proof_metrics.py`. That is the entire real kernel surface: a config/schema + testing-conformance + proof-metrics layer. The loop/sim/decision/brain/api kernels are stubs.

### 1c. The REAL shared machinery (`scripts/platformkit/`) -- this IS the kernel in practice
- `predict_matchup.py` -- the ONE buyer-facing CLI (`cv-matchup`); routes `--sport` to a domain predictor; pregame + optional in-game; degrades to "unavailable" on a fresh clone. (300 LOC)
- `predictor_jd.py` -- the cohesion seam: lazily builds + caches each sport's `Predictor`, exposes `get_demo_jd(sport)` / `demo_matchup(sport)`; `_build_predictor(sport)` is the factory used by the CLI and front end.
- `sim_framework.py` -- `JointDistribution` dataclass (line 54) + `market_surface(jd, spec)` (line 194): one sample matrix -> ML/spread/total/team-totals by counting. The sport-blind Monte-Carlo surface.
- `live_repricer.py` -- `GameState` + `get_repricer(sport)`: sport-blind in-game repricer the domain `predict_live` calls.
- `eval_gate/` -- the keystone validation core (see 1d).
- `proof_common/` (`runner.py`, `spec.py`, `paper.py`, `equivalence_check.py`) -- the sport-blind proof harness; `proof_nba/`, `proof_mlb/`, `proof_soccer/`, `proof_tennis/`, `proof_basketball_nba/` are the per-sport proof modules.
- `recalibration.py`, `calibrator_*.py`, `rating_calibrated.py`, `dist_metrics.py` -- conformal/temperature/isotonic calibration + distributional metrics.
- `self_improve.py` -- the "getting better" ratchet (SHIP/HOLD/REJECT/INSUFFICIENT_DATA) over real settled outcomes.
- `odds_provider/`, `odds_shop.py`, `clv_ledger.py`, `ledger/` -- keyless multi-book odds aggregator + line-shop/arb/EV + CLV ledger.
- `prop_engine`/`prop_edge.py`/`prop_tiering.py`/`prop_paper.py`/`prop_loop.py`/`prop_line_history.py`/`grade_paper.py` -- the player-prop pricing + paper + (true-)CLV capture stack.
- `frontend/` -- `serve.py` (FastAPI at :8098), `snapshot_writer.py` + `snapshot_scheduler.py` (the Phase-0 compute-once keystone), `slate.py`, `live_board.py`, `bet_board.py`, `web/` (React/shadcn).
- `brain_*.py` (~30 modules) + `sport_read.py` -- the LLM-free intelligence/brain read layer (writes prose only; the gate+engine compute every number).
- `mcp_server/`, `pm_trading/` (prediction-market trader, paper-first), `validate_adapter*.py`, `system_map.py`, `kernel_api_map.py`, `check_import_contract*.py` -- tooling/contract enforcement.

### 1d. Eval gate (`scripts/platformkit/eval_gate/`) -- the contract every change is judged by
- `run_gate.py` (203 LOC) -- `main(--golden|--corpus)`; `run_gate_in_process(predict_fn, ...)`; `evaluate_corpus(name, predict_fn, states)`; `gate_exit_code(rows)`. Offline `--golden` runs in <60s, no network, on a SYNTHETIC golden fixture; blocks ONLY on regression-vs-frozen-baseline or a leak-guard assertion -- never on "fails to beat the close".
- `walkforward.py` -- leak-free walk-forward driver. `scoring.py` (191 LOC) -- Brier/BSS/log_loss/ECE/resolution/sharpness + CRPS/pinball (C7). `dm_test.py` -- clustered Diebold-Mariano. `shin.py` -- Shin (1992) devig. `ingame_blend.py`, `freshness_schema.py`, `ledger.py`, `baseline.py`/`baselines/` (frozen baselines), `gen_golden.py`/`golden_loader.py`, `offline_predict.py`, `run_all.py`.

### 1e. Domain adapters (`domains/<sport>/`) -- 203 py files across 5 sports
- `basketball_nba/`, `mlb/`, `soccer/`, `tennis/`, `soccer_intl/` (World Cup). Each has a `predictor.py` (`predict`/`to_jd`/`predict_live`), `ratings.py` (Elo/rates), `markets.py` (full market surface), `signal_catalog*.py`, `atlas*.py` / `memory_atlas*.py` (intelligence atlases), `ingest_*.py` (data connectors), and `adapter.py` (the gate seam -> `src.loop.gate.FeatureBundle`). soccer_intl is the thinnest (config/predictor/ratings only).

### 1f. Half A origin (still real, still the NBA data substrate) -- `src/` (430 py modules)
- `src/pipeline/unified_pipeline.py` (CV orchestrator), `src/tracking/{advanced_tracker,osnet_reid,color_reid,court_detector}.py`, `src/features/feature_engineering.py`, `src/prediction/{win_probability,player_props,betting_portfolio,devig,walk_forward_backtester,shadow_logger,settlement}.py` (~130 modules, ~12 load-bearing), `src/sim/basketball_sim.py`, `src/loop/{discovery,orchestrator,gate}.py`, `api/main.py` (~99 endpoints, 12 routers), `database/schema.sql`.

---

## 2. HOW IT WORKS -- data flow + key algorithms

### 2a. The funnel, stage by stage (as actually wired in Half B)
```
DATA        domains/<sport>/ingest_*.py  -> parquet corpora in data/ (gitignored)
SIGNALS     domains/<sport>/signal_catalog*.py + asof_*.py  (leak-safe as-of builders)
MODELS      domains/<sport>/ratings.py (Elo / per-90 rates / serve-hold) + calibration
ENGINES     domains/<sport>/predictor.py + sim_framework.JointDistribution
            + live_repricer.get_repricer(sport)
PREDICTIONS predict()/to_jd()/predict_live() -> markets.py full surface
            -> predict_matchup CLI / snapshot / front end
INTELLIGENCE atlas*.py -> brain_*.py knowledge graph -> sport_read.build_sport_read()
             (LLM writes prose only; gate+engine compute every number)
```

### 2b. The cohesion seam (one win-prob anchors everything)
Each `domains/<sport>/predictor.py` exposes three methods with a stable signature:
- `predict(home, away[, surface=])` -> calibrated pregame dict (p_home_win, totals ladder, ...).
- `to_jd(home, away, *, n_sims, seed) -> JointDistribution` -- coherent (home_score, away_score) sample matrix so ML/spread/total all read off ONE distribution.
- `predict_live(home, away, **state) -> dict` -- in-game repricer.

Concrete NBA example (`domains/basketball_nba/predictor.py`):
- `NBAPredictor.__init__` builds as-of Elo + pace + off/def efficiency by replaying the ingested ESPN box corpus (`_update`, lines 165-176; MOV-aware Elo at lines 168-171), then fits a dispersion recalibration (`np.polyfit(pr, tt, 1)`, line 85) and an in-game temperature recalibrator (`_fit_live_recalibrator`, lines 100-145, fit on ALL-PRIOR linescore history -> applied forward = leak-free; ECE 0.059 -> 0.012, T~1.45).
- `to_jd` (lines 179-200) samples total ~ N(total_mean, total_sigma) and ANCHORS the margin mean so P(margin>0) == the Elo win-prob -- ML/spread coherent with the win model, total from the possessions model.
- `predict_live` (lines 202-256) feeds the SAME anchored Elo prior into `get_repricer("nba").reprice(GameState(...))` + the realized score (W146 combined forecaster), then applies the W156 temperature map -- with a deterministic-game guard (lines 239-241) so a finished/buzzer result passes through untouched.

### 2c. The eval gate algorithm (`run_gate.evaluate_corpus`, lines 83-119)
Walk-forward with `select_inside=True` (feature selection inside the window; a False flag fails the run) -> per-corpus Brier(model), Brier(close), BSS, log_loss, ECE, resolution, sharpness, clustered DM stat + p + CI95. `_verdict` (lines 74-80): BEATS_CLOSE only if `bss>0 AND dm.p<0.05 AND n>=200`; MATCHES_CLOSE if the DM CI overlaps 0; else BEHIND (honest, recorded, NON-blocking). REGRESSION blocks only when `brier_model > baseline + 0.005` AND a DM test of model-vs-baseline per-game losses is significant. `gate_exit_code` fails CLOSED on an empty measured set.

### 2d. The "getting better" ratchet (`self_improve.py`)
Per sport per cycle: (a) load real settled (model_prob, outcome[, close]) from `clv_ledger.jsonl` + `paper_predictions.jsonl`; (b) honest Brier/ECE/BSS-vs-close readout; (c) leak-free walk-forward isotonic recal (game N uses only games < N); (d) the eval gate's OWN walk-forward + proper-scoring + cluster-robust DM checks no regression vs the frozen raw baseline; (e) verdict SHIP (ratchet forward) / HOLD / REJECT / INSUFFICIENT_DATA -> `data/frontend/improve_ledger.jsonl`.

### 2e. The Phase-0 snapshot keystone (`frontend/snapshot_writer.py`)
Compute a sport's board ONCE per cycle (calls real seams `slate.build_slate`, `live_board.todays_live_games`, `aggregate.to_odds_lookup`), write atomically (`.tmp` then `os.replace`) to `data/frontend/snapshots/<sport>.json`; both the FastAPI server and the paper bettor READ the snapshot. All seams guarded -> never raises; failure writes a `status="unavailable"` envelope.

---

## 3. HOW IT IS USED -- callers / consumers

- **CLI:** `python -m scripts.platformkit.predict_matchup --sport <s> --home --away [--elapsed/--inning/...]`; entry points `cv-matchup` / `cv-predict` / `cv-live` (pyproject). Calls `predictor_jd._build_predictor` -> domain `predict`/`predict_live` -> `markets.full_surface`.
- **Front end:** `scripts/platformkit/frontend/serve.py` (FastAPI at http://127.0.0.1:8098) reads snapshots; `/api/game`, `/api/props`, `/api/live`; React/shadcn UI in `frontend/web/`.
- **Loops:** `snapshot_scheduler.py` + `refresh_daemon.py` (refresh cadence); `prop_loop.py` / `prop_paper.py` / `grade_paper.py` (paper-bet + grade + true-CLV via `prop_line_history.py`); `self_improve.py` (improve ratchet).
- **Eval gate:** invoked by the `eval-gate` skill, by `self_improve`'s gate step, and as a CI/pre-ship contract (`run_gate.main` exit 0/1). Skills `predict-matchup`, `calibration-report`, `cross-sport-benchmark`, `signal-audit`, `state-roadmap` all wrap platformkit entry points.
- **Intelligence read:** `sport_read.build_sport_read(sport, jd)` consumes `brain_query` + the predictor JD + `model_card.parse_card_metrics`; LLM (default OFF) writes prose, `brain_critic` self-checks for edge-claim leakage and falls back to a safe template.
- **Gate seam (Half A reuse):** every `domains/<sport>/adapter.py` imports `src.loop.gate.FeatureBundle` + `src.loop.signal.Hypothesis` so the original NBA discovery/gate engine runs on any sport with zero kernel edits.

---

## 4. STRENGTHS (genuinely solid)

- **Validation discipline is the real product.** Leak-free walk-forward with assertion-level per-fold guards, truncation-invariance leak tests, clustered DM significance, multi-corpus accept gate, frozen-baseline regression block, fail-closed-on-empty. The gate is built to REFUTE, not confirm. This is senior-grade and it is reused sport-blind.
- **Honesty is enforced in code, not just prose.** `edge_claimed=False` is a literal field on the CLI result; `brain_critic` scans narratives for edge-claims and reverts to a safe template; `no-edge-claims.md` rule + the retracted-numbers list are wired into the agent rules. The system caught and documented its own +18.38% / 0.119 / +54% artifacts.
- **The cohesion seam is clean and consistent.** One win-prob anchors ML/spread/total/in-game across all 5 sports via a shared `JointDistribution` + a shared `live_repricer`. The pregame and in-game numbers are coherent by construction (the anchor pattern), not bolted on.
- **Adapter parity is real.** 5 sports each implement the same `predict`/`to_jd`/`predict_live` interface; `validate_adapter*.py` + `proof_common` enforce it. Adding a sport is mostly an adapter, as claimed.
- **Graceful degradation everywhere.** Fresh clone with no `data/` -> CLI prints "unavailable" and exits 0; snapshot writer writes an envelope; predictor cache returns None. Nothing fabricates numbers when the corpus is absent.
- **Calibration results are honest and reproducible.** NBA ML Brier 0.1735 vs close 0.1672 (MATCH within noise); totals BEHIND by the freshness gap; MLB/Soccer/Tennis reproduce on committed fixtures. In-game conditioning is the one measured calibration win (NBA 0.209->0.159, MLB 0.241->0.126), scoped real-corpus-only with edge_claimed=False.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

- **The `kernel/` is mostly a fiction.** `docs/PLATFORM.md` describes a populated sport-blind kernel (loop/sim/validation/decision/brain/api); on disk those subpackages are 1-line stubs. The real shared machinery is in `scripts/platformkit/`. This is the single biggest doc-vs-code gap and an architectural smell: "kernel" is a planned destination, not a built layer. A buyer reading PLATFORM.md and then opening `kernel/` will see the discrepancy.
- **Funnel stages are partially DISCONNECTED.** `REVAMP_MASTER_PLAN.md` workstream 03 admits it: next-tier data is on disk but discarded at ingest; atlas/intelligence (atlas*.py, brain_*.py) features are BUILT but NOT read at predict time; the freshness flag is OFF. So INTELLIGENCE is largely a parallel descriptive layer, not an input to PREDICTIONS. The CV/spatial layer's SHAP contribution to predictions is ~0 (documented).
- **Two halves are loosely coupled.** Half A (`src/`, 430 modules, ~12 load-bearing; the CV pipeline + ~99-endpoint API) and Half B (`domains/` + `platformkit/`) overlap only at the gate seam (`src.loop.gate.FeatureBundle`) and the NBA box/linescore data. Much of `src/prediction/` (~130 modules) is research surface, not in the live deployment graph. The CV pipeline is "real engineering history" but NOT the product and contributes no measured predictive value.
- **Thin / small-N corpora.** World Cup vertical is 24 matches (NOW.md: isotonic prop recal OVERFITS on it -> correctly DEFERRED; opp-adjustment measured NULL). Early paper ROI is -47% on 7 bets (small-N, expected). The improve loop is INSUFFICIENT_DATA until ~60 real games settle (cold start).
- **Reproducibility caveats.** NBA in-game WIN is real-corpus-only and VALIDATION_PENDING on a fresh clone (the committed synthetic fixture prints no-improvement due to a synthetic-anchor artifact). Half-A verify scripts (`verify_production_mae.py`, `verify_winprob.py`) crash / read uncommitted caches from a clean clone (documented in JOB_EVIDENCE_PACKET do-not-claim).
- **No real CLV yet.** Closing prop lines aren't captured for most markets, so prop "CLV" is not yet computable; current evidence is P(over) calibration + realized ROI at taken price. Real money is hard-gated on proven CLV that does not yet exist.
- **Speed debt (the Phase-0 motivation).** The API historically rebuilt predictors + refetched odds per request; the snapshot keystone exists to fix this but is mid-rollout (NOW.md NEXT items still wiring the prop board / refresh cadence).
- **Test suite is not fully green.** ~7,400 tests, ~97-98% pass with a documented tail (DB/GPU/optional-dep drift + a Windows pyarrow segfault); full `pytest tests/` freezes the box (per-file only).
- **Live odds breadth is thin.** Single republished ESPN line for live -> no real arb until a 2nd venue matches; no ToS-violating DK/FD scraping.

---

## 6. PLAN TO GET BETTER (prioritized)

**Quick wins (days):**
1. Reconcile `kernel/` with reality. Either (a) move the genuinely sport-blind platformkit modules (sim_framework, eval_gate, recalibration, live_repricer, proof_common) into the matching `kernel/` subpackages and re-export, or (b) rewrite `docs/PLATFORM.md` to say "the kernel currently lives in `scripts/platformkit/`; `kernel/` is the target namespace." Today the doc over-claims a layer that is empty.
2. Finish the snapshot keystone end-to-end (NOW.md NEXT 3+5): every surface reads `data/frontend/snapshots/<sport>.json`; nothing recomputes in the request path; refresh + paper grading on a cadence. Biggest speed + coherence win.
3. Land the props eval-gate (NOW.md NEXT 2): P(over) calibration + Brier/BSS on settled props per stat, so the prop layer is judged by the same fail-closed gate as game markets.
4. Capture closing prop lines (`prop_line_history.py` already logs ticks) so true prop CLV becomes computable -- the only honest path to a real-money unlock.

**Bigger bets (weeks):**
5. Wire the dead funnel stages (workstream 03): make atlas/intelligence features an ACTUAL gated input to predict-time (each must beat raw on >=2 corpora or stay descriptive), and stop discarding next-tier data at ingest. This is the difference between INTELLIGENCE-as-decoration and INTELLIGENCE-as-input.
6. The per-sport model levers (workstream 02), each leak-free + gate-gated: MLB starting-pitcher ratings (the biggest single lever; current Elo is pitcher-blind), soccer fitted Dixon-Coles, tennis serve/return sidecar + surface-Elo + WTA, NBA same-day freshness/availability (the only real NBA pregame lever; rest is at the data ceiling).
7. Accrue real settled outcomes to exit cold-start: let the paper loop + self_improve ratchet reach n>=60 per sport so the improve verdict becomes meaningful, and the calibration claims gain a forward-validated (not just historical-fixture) leg.
8. Genuinely separate the two halves or retire Half-A dead weight: prune the ~120 non-load-bearing `src/prediction/` research modules into `_archive/`, leaving a small documented deployment graph (judgment the JOB_EVIDENCE_PACKET already credits).

---

## 7. HOW GOOD CAN IT GET (honest ceiling)

- **Pregame on sharp team-strength markets: at the ceiling already.** The system MATCHES the Shin-devigged close within noise (NBA ML 0.1735 vs 0.1672) and the full-season backtest shows CLV ~= 0. You cannot durably beat the sharp close with a box model; "match it" IS the best honest outcome and it is reached. Totals/ATP stay BEHIND by a freshness gap (injuries/lineups/park/weather/SP) that a box model structurally cannot see -- closeable only by ingesting same-day availability, not by better modeling.
- **In-game conditioning: a measured, real calibration win, but not a $-edge.** Brier 0.209->0.159 (NBA), 0.241->0.126 (MLB) -- genuine sharpness. The honest ceiling: a live book sees the same score, so this is forecaster quality, not tradeable alpha. Realistic upside is broader, faster, better-calibrated live re-pricing across more sports/markets.
- **Where realistic value (if any) lives:** soft/recreational books, lazily-priced props/alts, live lag, stale lines, prediction-market vs sportsbook gaps, correlated SGP mispricing -- ALL to be PROVEN by CLV, never asserted. The platform is correctly built to surface and paper-trade these; the verdict is empirical and not yet in.
- **The durable, sellable ceiling is engineering, not alpha:** a clean kernel/adapter platform where a new sport is mostly an adapter, judged by a fail-closed eval gate, with honesty enforced in code. That ceiling is largely reached for 5 sports; the remaining gap is structural maturity (populate the kernel, connect the funnel, finish the snapshot service), not predictive accuracy.

**Bottom line:** architecturally mid-maturity -- a strong, reused validation+adapter spine and a clean cohesion seam, undercut by an empty `kernel/` namespace, a partially-disconnected intelligence funnel, and a loosely-coupled legacy half. The single biggest structural improvement is to **make the kernel real and wire the funnel** (populate `kernel/` from `platformkit/` or fix the doc, and turn atlas/intelligence from decoration into a gated predict-time input) -- the same move also closes the largest doc-vs-code honesty gap.
