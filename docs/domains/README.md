# Domains — the per-sport adapters

Each `domains/<sport>/` package is a thin adapter over the sport-blind `kernel/` (see
[../PLATFORM.md](../PLATFORM.md) for the kernel/adapter contract). An adapter supplies a `SportContext`, a
`feature_spec.py` (the frozen train==inference base matrix), an `ingest_manifest.py` (leak-class
+ freshness contract), a rating system, a `predictor.py` exposing `predict()` / `predict_live()`
/ `to_jd()`, and — where the data supports it — signal catalogs, prop engines, gates, and an
Obsidian intelligence atlas. The full adapter contract and the 9-step "add a sport" playbook are
in [../PLATFORM.md](../PLATFORM.md).

> Every number a domain produces is calibration/sharpness, never a dollar edge. Honest REJECTs
> are recorded as successes. Truth-source: [../JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).

---

## The adapters at a glance

| Domain | Maturity | Anchor / ratings | Simulation engine | In-game | Notes |
|---|---|---|---|---|---|
| `basketball_nba` | **Full** | MOV-aware leak-free Elo (HFA 76, K 20) | possession MC (`domains/basketball_nba/sim2/` + `src/sim/basketball_sim.py`) | yes (`repricer.py` + temp recal) | Deepest stack: 7-stat prop chain, kernel `SportContext` seams (entity/pbp/league/atlas), memory atlas |
| `mlb` | **Full** | MOV-Elo + SP-form offset (HFA 24, K 4) | pitch-level engine (`pitch_engine/`) + NegBinom run model | yes (`repricer.py`, identity recal) | Statcast/Savant ingest, catcher-framing/umpire/platoon builders, weather & park gates |
| `soccer` | **Full** | EW goals-rate + mass-preserving HFA | Dixon-Coles bivariate Poisson (`scoreline_engine.py`) | yes (via `live_repricer` "soccer") | football-data.co.uk corpus, StatsBomb events, xG *proxy* (shots-based, not vendor xG) |
| `tennis` | **Full** (cleanest reference) | surface-blended Elo + leak-free Platt/temp recal | hold-rate MC bisected to anchor (`match_engine.py`); separate point-level validation harness (`point_engine/`) | yes (race-to-N repricer + W156 recal) | Untimed-sport clock support; Sackmann corpus (CC BY-NC-SA, private use) |
| `soccer_intl` | Predictor (census-first) | own EW ratings (slower decay), neutral-site aware | **reuses** `domains/soccer` scoreline engine by import | identity recal (no HT-goals corpus) | Single `results.parquet` corpus; honestly declares one ingest source |
| `basketball_wnba` / `wnba` | Adapter + descriptive atlas | duplicated Elo, WNBA-refit (HFA 40, K 30) | — (descriptive-only at current sample sizes) | anchored blend (`ingame_blend`) | No `feature_spec`/`ingest_manifest` yet; power-audit forbids predictive gates at this N |
| `baseball_kbo` / `baseball_npb` | Pregame-only | duplicated Elo, per-league grid-fit constants, tie-aware | — | none (no live PBP ingest) | League-specific scrapers (koreabaseball.com / npb.jp); `ingame_base_fit` quarantined as HONEST_NEGATIVE |
| `baseball_intl` | Claims-only | — | — | — | Cross-league NPB-vs-KBO descriptive tie-rate claims |
| `cross_sport_market` | Claims-only | — | — | — | Market-microstructure (line-drift, depth-imbalance) claims across sports from captured Kalshi/Polymarket data |
| `nfl` | **Scaffold** | placeholder `rating_diff` | — | — | Generator stub from `new_sport_scaffold.py`; no NFL-specific content yet |

---

## Shared patterns worth knowing

- **Anchor coherence.** Every full adapter pins its simulation/joint-distribution to the Elo
  (or rating) win-probability so the whole market surface stays mutually consistent — bisection
  (tennis hold-rate delta, NBA margin), or a sum-preserving tilt (MLB NegBinom, soccer lambdas).
  See [../models/possession-simulators.md](../models/possession-simulators.md).
- **Leak-free "as-of" builders.** `domains/<sport>/asof_*.py` all follow snapshot-before-update:
  a game's own realized stats never feed its own features. Post-game box stats are tagged
  `LEAK_POST_GAME` and used only as training targets or to *derive* as-of features.
- **Duplication over cross-adapter import.** `domains/<a>/` never imports `domains/<b>/` (enforced
  by `check_import_contract.py`). WNBA/KBO/NPB deliberately *duplicate* the NBA/MLB Elo replay
  rather than import it, because those engines aren't sport-blind-importable (F5 rule) — the
  exception is `soccer_intl`, which reuses `domains/soccer`'s scoreline engine by design.
- **Honest scope.** An adapter declares only ingest sources that actually exist on disk
  (`validate_against_inventory`), and records terminal REJECT / NOT_TESTABLE / QUARANTINED
  verdicts rather than hiding them (e.g. KBO/NPB `ingame_base_fit`).

---

## Reference adapter

`domains/tennis/` is cited in [../PLATFORM.md](../PLATFORM.md) as the cleanest end-to-end
reference: a minimal 5-field `feature_spec.py`, a clear `ingest_manifest.py` leak-class example
(post-game `match_stats` -> leak-free `asof_*` features), the anchor-bisection pattern in
`match_engine.py`, and both a production predictor and a separate validation harness. Read it
alongside [../models/possession-simulators.md](../models/possession-simulators.md) and
[../models/calibration-and-validation.md](../models/calibration-and-validation.md).

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
