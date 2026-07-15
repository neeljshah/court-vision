# 00 - Overview: What This System Is

> A single, all-in-one AI for **calibrated sports prediction** across four sports --
> NBA, MLB, soccer, and tennis (ATP/WTA) -- with a live, self-healing, self-improving
> serving stack and a **paper-only** decision layer (units, never dollars; real money is
> default-DENY).
>
> **Read this first for honesty framing:** every number in this guide traces back to
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), the adversarially-audited
> truth source, and obeys [.claude/rules/no-edge-claims.md](../../.claude/rules/no-edge-claims.md).

---

## The one-sentence version

It turns raw sports data into **well-calibrated probabilities** -- forecasts whose stated
confidence matches reality -- and proves, with leak-free instruments, that those forecasts
**match the sharp closing line** on team-strength markets rather than beating it. The honest
product is *decision support and forecast quality*, not a profit / picks / +EV engine.

## The honest north star (read this before any number)

The goal is the **best calibrated predictions per sport**, claimed honestly. Three rules
hold everywhere in this guide:

1. **Calibration, not edge.** We measure Brier / RMSE / BSS against the devigged market
   close. "We MATCH the close within noise" is the realistic best case for an efficient
   market -- beating it would imply information the close lacks.
2. **The market is efficient pregame.** A real-data hunt across 4 sports and 6 independent
   corpora REJECTED every candidate pregame edge; full-sample lifts that looked positive
   *sign-flipped* out-of-sample -- the overfit signature, caught by our own gate. An honest
   REJECT is a SUCCESS here, not a failure. See
   [docs/MARKET_EFFICIENCY_PROOF.md](../MARKET_EFFICIENCY_PROOF.md).
3. **The one measured win is IN-GAME conditioning.** Fusing the pregame prior with the
   realized mid-game state sharpens the win-prob forecaster (NBA Brier 0.209 -> 0.159,
   MLB 0.241 -> 0.126, real-corpus OOS). This is forecaster quality, **not** a dollar edge
   -- a live book also sees the score. `edge_claimed = False` everywhere.

Everything is **paper / units only**. No real money has been placed; the execution layer
ships with a drawdown-triggered kill-switch and a default-DENY real-money gate.

---

## The funnel: DATA -> SIGNALS -> MODELS -> ENGINES -> PREDICTIONS -> INTELLIGENCE

Every stage is re-validated by an agentic loop and a fail-closed ship gate.

```
   DATA            SIGNALS           MODELS            ENGINES           PREDICTIONS        INTELLIGENCE
 broadcast CV  ->  signal       ->  prop XGB (7)  ->  possession   ->  calibrated      ->  concept graph
 NBA/odds APIs     factory          win-prob          Monte Carlo      markets +           (playstyles,
 multi-book        (629 trained)    MOV-Elo           sim ->           Shin/Platt          schemes,
 scrapers          + 80-artifact    (per sport)       coherent         calibrated          dossiers)
 4-sport corpora   intel layer                        markets          probabilities
        \__________________________ agentic discover / validate / SHIP-or-REJECT loop __________________________/
```

- **DATA** -- a from-scratch computer-vision pipeline turns NBA broadcast video into
  player court coordinates and behavioral features (`src/pipeline/unified_pipeline.py`,
  `src/tracking/advanced_tracker.py`), plus keyless odds/box-score feeds and reverse-
  engineered multi-book scrapers, across four sports' historical corpora.
- **SIGNALS** -- a signal factory and an 80-artifact intelligence layer produce hundreds of
  candidate features per player/team. Note: CV-derived features are *wired in* as a future
  edge but do **not** yet move the model (SHAP ~ 0 in production today).
- **MODELS** -- seven per-stat prop models (XGBoost), a stacked win-probability model, and a
  margin-of-victory Elo, each leak-free walk-forward validated.
- **ENGINES** -- a player-level **possession Monte Carlo** simulator
  (`src/sim/basketball_sim.py`) where teammates compete for a shared scoring pie, so the
  correct *negative* teammate correlation emerges from the mechanics instead of a hand-tuned
  matrix. One simulation prices many markets coherently off one anchor.
- **PREDICTIONS** -- raw outputs pass through **Shin (1992)** de-vig
  (`src/prediction/devig.py`) and **Platt / isotonic** calibration, producing probabilities
  whose confidence is trustworthy. This is the load-bearing deliverable.
- **INTELLIGENCE** -- a person-free Obsidian concept graph of playstyles, schemes, and
  ~1,249 per-player dossiers, fully reachable from one index. Scouting context, explicitly
  *not* a betting edge.

## Architecture: a sport-blind kernel + per-sport adapters

The validated machinery lives in a sport-agnostic `kernel/` (calibration, validation, sim
framework, decision, loop, brain, fusion, model_ops). Each sport is a thin adapter under
`domains/<sport>/` (`basketball_nba`, `mlb`, `soccer`, `tennis`, ...). Adding a sport means
writing an adapter, not re-deriving the math -- which is how the same instruments produced
the 6-corpus efficiency proof. See [docs/PLATFORM.md](../PLATFORM.md).

## The live stack and the self-improving loop

- **Self-healing serving.** A fleet of long-running daemons (in-play projection, auto-
  place/settle on paper, CLV tracking, bankroll monitor, middle-finder, multi-book scraper,
  lineup ingest) sits behind a watchdog/registry supervisor
  (`scripts/daemon_watchdog.py`, `scripts/daemon_registry.json`) that restarts crashed
  services. A FastAPI layer of ~99 endpoints across 12 routers (`api/main.py`) serves the
  live page; it reads the canonical store and never recomputes.
- **Self-improving ratchet.** An autonomous two-arm daemon (`scripts/loop/run_loop.py`,
  `src/loop/`) mines residuals into hypotheses and validates each behind a fail-closed gate
  (`src/loop/gate.py`): expanding walk-forward (all folds must improve) + null-shuffle
  permutation (z >= 3) + ablation-vs-full-model + Benjamini-Hochberg FDR. **Most candidates
  correctly get REJECTED** -- the gate exists to refute, not confirm.

---

## A map of the rest of this guide

| Doc | Topic |
|---|---|
| `00_OVERVIEW.md` | (this file) what the system is + the honest north star |
| Data / CV | the broadcast-CV pipeline, odds feeds, and 4-sport corpora |
| Signals & intelligence | the signal factory + 80-artifact intelligence layer + concept graph |
| Models | the 7 prop XGBs, win-prob stack, and MOV-Elo |
| Engines | the possession Monte Carlo sim and coherent market pricing |
| Calibration & proof | Shin/Platt calibration, the leak-free gate, the efficiency proof |
| Platform | the sport-blind kernel + per-sport adapters |
| Live stack & loop | the daemon fleet, FastAPI surface, and self-improve ratchet |

For the authoritative claim-by-claim ledger, always defer to
[docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).

---

## Where to look in the repo

- `docs/JOB_EVIDENCE_PACKET.md` -- truth source for every claim + the do-not-claim list.
- `docs/MARKET_EFFICIENCY_PROOF.md` -- the 4-sport / 6-corpus efficiency proof and REJECT table.
- `.claude/rules/no-edge-claims.md` -- the calibration-not-edge honesty rule.
- `src/pipeline/unified_pipeline.py`, `src/tracking/advanced_tracker.py` -- CV/tracking pipeline.
- `src/prediction/player_props.py`, `src/prediction/win_probability.py` -- prop + win-prob models.
- `src/sim/basketball_sim.py`, `src/sim/fast_sim.py` -- possession Monte Carlo engine.
- `src/prediction/devig.py` -- Shin (1992) and three other de-vig methods.
- `kernel/` + `domains/<sport>/` -- sport-blind machinery + per-sport adapters.
- `scripts/loop/run_loop.py`, `src/loop/gate.py`, `src/loop/discovery.py` -- self-improve loop + ship gate.
- `scripts/daemon_watchdog.py`, `scripts/daemon_registry.json`, `api/main.py` -- live self-healing stack + API.
- `scripts/platformkit/ingame_scoreboard.py`, `scripts/platformkit/proof_nba/ingame_accuracy.py` -- the in-game calibration win.
