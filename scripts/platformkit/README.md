# `scripts/platformkit/`  -  the sport-blind platform toolkit

The shared machinery behind a converged **4-sport (NBA / MLB / Soccer / Tennis) calibrated
prediction platform.** One leak-free win-prob per sport anchors a coherent pregame surface
plus an in-game repricer. What it does well, measured leak-free / OOS on held-out data
(numbers: `vault/_Edge_Maps/`; honesty truth-source: `docs/JOB_EVIDENCE_PACKET.md`):

- **Pregame MATCHES the devigged close** within noise on team-strength markets
  (NBA moneyline, MLB moneyline, Soccer O/U-2.5), and trails only on totals / ATP-ml by
  freshness data (injuries, lineups, park / weather, starting pitchers) we cannot see.
- **In-game conditioning WINS in all 4 sports**  -  combining the pregame intelligence prior
  with realized score state beats the static pregame line (NBA, MLB, Soccer, Tennis all show
  a measured Brier reduction). This is the decisive, calibrated, delivered edge.
- **Reproducible in under 60s on committed fixtures:** the beat-the-close and in-game
  scoreboards rerun from a fresh clone (`scripts/platformkit/beat_the_close_scoreboard.py`
  and `ingame_scoreboard.py`, `--corpus tests/fixtures/proof`).

Built here (NOT in `kernel/`  -  kernel edits are human-gated); the validated prototypes carry
a **kernel-lift readiness map** (`.planning/intelligence/KERNEL_LIFT_READINESS.md`).

> **The honest disclaimer (binding contract, every module):** pregame sports markets are
> efficient; we MATCH the devigged close, we do not beat it, and we never claim a $ edge or
> ROI. **CALIBRATION / SHARPNESS != EDGE.** A baseline match, a calibration gain, or a
> beats-naive result validates a method, not a market edge. Honest nulls are first-class
> successes. Leak-free (truncation-invariance tested), default-OFF, `<=300` LOC/file,
> per-file tests (combined pytest pyarrow-contaminates).

## The brain (person-free organized memory)

| Module | Role |
|---|---|
| `vault_sources` / `vault_organize_multi` | build the canonical, deduped, person-free 4-sport `_Organized/` tree (players nested under teams; matchup notes dropped; dense team hubs) |
| `vault_person_free_lint` | measure person/matchup leaks |
| `brain_digest` | dense per-sport + cross-sport transfer digests |
| `brain_export` | per-sport intelligence READS as browsable markdown |
| `brain_query` | read-only retrieval seam (understanding + provenance, never a number) |
| `brain_critic` | rule-based self-check before a memory write (dedup / leak-flag / edge-claim) |
| `brain_audit` | tree-wide no-edge audit (caveat-aware)  -  the discipline gate |
| `brain_pipeline` | **one command** rebuilds the whole brain: organize -> digest -> export -> (models) -> audit |

## Models (C14)  -  one rating object, per-sport pinned constants

| Module | Role |
|---|---|
| `generic_rating.GenericRatingModel` | one leak-free walk-forward Elo across ALL 4 sports: logistic (NBA/MLB/tennis win) + score (soccer W/D/L). Validated OOS vs each baseline / naive |
| `poisson_rating.PoissonRatingModel` | attack/defense Poisson rating -> runs/goals (count markets) |
| `rating_calibrated` | composes rating -> best calibrator -> OOS scorecard |
| `model_card` | per-sport browsable Model Card artifact |

## Calibration (C14/C15)  -  leak-free, OOS-selected

| Module | Role |
|---|---|
| `recalibration` (isotonic) / `calibration_ladder` (Platt) | existing WF recalibrators |
| `calibrator_zoo` | adds temperature + beta + an N-method OOS-log-loss selector |
| `calibrator_select` / `calibrator_sweep` | per-sport selection on real data + robustness sweep (finding: isotonic overfits WF  -  see `CALIBRATION_RECOMMENDATION.md`) |
| `hier_priors` / `eb_base_rates` | closed-form Empirical-Bayes hierarchical priors + real per-(team,season) base rates |
| `dist_metrics` / `calibration_conformance` | proper scores, coverage, conformal |

## Engines, prediction surface & frontier

`sim_framework` (JointDistribution) | per-sport engines live in `domains/<sport>/` |
`scoreboard` (4-sport calibration vs the close) | `sgp_pricer` (joint/correlation lift) |
`live_repricer` (in-game) | `pipeline_integration` (one cohesive per-sport read).

## Frontend (the honest :8099 board  -  NOT `api/main.py`)

`frontend/app` (FastAPI :8099) | `board` / `board_html` (line-shop/devig/CLV rows) |
`intel_panel` (per-sport brain panels) | `feed` / `feed_espn` / `odds_snapshot` (free odds) |
`arbitrage` / `clv` (dormant until a live multi-book feed  -  the unlock is DATA).

## Guards & adapter contract

`check_import_contract` (kernel never imports domains/src) | `check_no_public_push` |
`validate_adapter*` | `hygiene_lint` | `select_tests` (per-file test selection).

## Run it (a buyer's two commands)

```
# Pregame + in-game for one matchup
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0

# Reproduce the scoreboards on committed fixtures (proof in <60s, fresh clone)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard       --corpus tests/fixtures/proof
```

---
_PRIVATE. The toolkit scouts / rates / calibrates / remembers; the gate + engines compute
every number. Pregame matches the close, never beats it; no $ edge is claimed. A REJECT /
honest-negative / parity is a SUCCESS._
