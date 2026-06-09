# New-session prompt — Agentic Signal Lab (surgical signal discovery for NYK/SAS)

Paste this into a fresh session to keep building the signal layer and the agentic system that drives it.

---

You are building the **agentic signal layer** for the CourtVision NYK/SAS team-vs-team prediction engine:
an autonomous loop that DISCOVERS candidate signals from play-by-play + NBA-API detail, VALIDATES each one
**surgically** (the gates below), and REGISTERS the verdict so a signal is tested once and never re-litigated.
The goal is the most accurate 2K-style simulation + fast in-game predictions, built as a COMPOSITION OF
VALIDATED SIGNALS (minutes, matchup, pace, foul, origin, defense, lineup, availability) — NOT a deeper model.
Run python from `C:\Users\neelj\nba-ai-system`; ascii prints; prefix background Bash with
`cd /c/Users/neelj/nba-ai-system &&`.

LOAD FIRST (memory): MEMORY.md + project_monte_carlo_engine_2026-06-06 (the engine, the 2026-06-07 sessions:
the matchup-composition generalization proof, the PBP origin lever, the deep 2K attributes, the player-game
walk-forward grounding [pregame mean near ceiling; minutes=22% of MSE = same-day/in-game; in-game RMSE
−47% by Q3], the minutes-signal surgical-not-kitchen-sink finding, the always-learning pipeline) +
project_pregame_model_ceiling_2026-06-04 (the marginal ceiling guardrail) +
feedback_edge_publish_pressure_hold_honest_line (accuracy != edge; don't overclaim).

## What is already built (use it, don't rebuild)
- **`scripts/team_system/signal_lab.py`** = `validate_signal(panel, name, baseline, feature, target, group,
  metric, asof, grain)` — runs the 4 gates and writes one row per signal to
  `data/registry/signal_lab_registry.parquet`. `python signal_lab.py --list` shows the registry.
- **`scripts/team_system/SIGNAL_BACKLOG.md`** = the queue of signal hypotheses (grain + what to mine).
- **Panels (as-of substrates):** `pbp_possessions.parquet` (possession grain, 39.5k), `nyksas_player_gamelog.parquet`
  (player-game, 2090, rich: pf/fga/rest/b2b/starter), `league_team_game.parquet` (team-game, 30 teams),
  `minutes_signal_preds.parquet`, `pbp_attributes.parquet` (shot diet × type × creation), `coverage_faced_allseasons`
  (defender pairs). Raw PBP in `data/cache/team_system/pbp/` (CDN actions: qualifiers/descriptor/area/x-y/clock).
- **Always-learning pipeline:** `update.py` rebuilds every identity after a game → `learn_ledger.py` snapshots
  beliefs + runs the board gate (pytest) → `vault/Intelligence/LEARNING_LOG.md`.

## THE GATES (a signal ships ONLY if all hold — signal_lab enforces them)
1. **OOS LIFT** — adding it lowers held-out error (5-fold by GAME = leak-free), on the RIGHT metric
   (rmse continuous / logloss binary), clearing the noise floor. Never in-sample, never MAE-only.
2. **STABILITY** — effect replicates split-half (sign-consistent across game halves).
3. **ORTHOGONAL** — not redundant with the baseline (else it double-counts what the model has).
4. **MATERIAL** — the lift beats the noise floor (no 0.0% mirages).
Guardrails: surgical (ONE signal at a time — kitchen-sink overfits, proven); board stays green; nothing
auto-applied to the engine (validated signals are flagged for GATED wiring + a separate board-green A/B);
record REJECTIONS (they're as valuable as wins); H2H (4 games) is for direction-check only, never fitting.

## The agentic loop (each iteration)
1. Read the registry (`signal_lab.py --list`) + `SIGNAL_BACKLOG.md`; pick the next untested hypothesis
   (prioritize the ⭐ high-value ones — start with **same_day_availability**, the dominant minutes signal).
2. Build the as-of panel for that signal (compute the leak-free feature from PBP/data at the right grain).
3. `validate_signal(...)` → it records the verdict.
4. If VALIDATED → write a one-line wiring proposal (which node it modulates, centered-at-neutral so it can't
   regress) for gated A/B; if REJECTED → note why (absorbed / unstable / immaterial) so it's not retried.
5. Check the box in SIGNAL_BACKLOG; when the queue runs low, append new hypotheses from un-mined PBP detail.

## BUILD OUT THE AGENTIC LAYER (this session's construction work — do this, not just iterate)
1. **`signal_orchestrator.py`** — drives the loop above end to end: reads backlog → for each untested
   hypothesis spawns the panel-builder + calls validate_signal → records → checks the box → appends a verdict
   line to a `SIGNAL_LAB_LOG.md`. One-command: `python signal_orchestrator.py --n 5` runs the next 5.
2. **Parallel mining** — for INDEPENDENT hypotheses, fan out (Agent subagents or a Workflow if the user opts in)
   so many candidate panels are built concurrently; the validator is the single serial judge (no race on the registry).
3. **Auto-gated-wiring proposer** — for VALIDATED signals, generate the exact centered-multiplier patch + a
   board-green A/B harness, but leave it BEHIND A FLAG (never auto-flip).
4. **First real signal to ship the loop on: `same_day_availability`** — join the injury/inactive feed as-of,
   compute teammates-OUT → usage/minute re-route, validate on player-game pts. This is the biggest minutes lever.
5. Fold a `## Signal Lab` status block (registry summary: validated/rejected counts + top signals) into the
   War Room, and add `signal_orchestrator.py` to the always-learning `update.py` chain (soft, board-gated).

## Start now (self-advancing loop — current state: 14 tested / 4 validated, all 4 grains live)
`python scripts/team_system/signal_orchestrator.py --status` shows the registry + the `NEXT_HYPOTHESES`
queue (the to-BUILD list) — the loop never redoes a tested signal (registry dedups). One iteration:
1. Pop the top `NEXT_HYPOTHESES` item; build its leak-free as-of panel feature + add a SPEC in
   `signal_orchestrator.py` (one signal, the right grain).
2. `python scripts/team_system/signal_orchestrator.py` (validates only the new spec; records verdict;
   if VALIDATED, appends a centered-at-neutral gated proposal to `WIRING_PROPOSALS.md` — mind the
   `CAVEATS` (orthogonality is baseline-relative: team-grain signals must be re-checked vs the ENGINE's
   own mechanics, not the toy baseline, before any wiring).
3. Check the box in `SIGNAL_BACKLOG.md`; refresh memory; keep the board green
   (`python -m pytest tests/test_sim_engine.py -q`). When `NEXT_HYPOTHESES` runs low, append more from
   un-mined PBP detail (descriptor/area/x-y, assist-network, foul-drawing per play-type).
- **Validated so far:** pbp_origin_transition, rest_x_age, shot_clock_leverage (−2.86%, biggest), oreb_matchup (caveat).
- **EDGE half:** `python scripts/team_system/signal_edge.py --baseline|--screen` grades ROI/CLV vs real lines
  (accuracy != edge). Map: reg-season AST has real edge, playoffs negative; AST+rested is the leading
  bet-selection candidate (not shipped). The untapped lane = freshness/CLV (needs open+close odds capture).
Numbers every step; record rejections; wire nothing un-gated; don't overclaim.
