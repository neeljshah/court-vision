# Live Engine v2 — operator runbook

> **Web dashboard:** the always-on browser UI (Next.js + Tailwind) is
> documented separately in [LIVE_ENGINE_V2_WEB.md](LIVE_ENGINE_V2_WEB.md).
> Backend: `api/live_v2_app.py` (FastAPI WS bridge). Frontend: `webapp/`.
>
> **Related:** the pregame distribution this engine reprices comes from the
> [possession Monte-Carlo simulator](architecture/possession-simulator.md);
> the game-day operating sequence is in
> [LIVE_OPERATOR_RUNBOOK.md](LIVE_OPERATOR_RUNBOOK.md). Full doc map:
> [INDEX.md](INDEX.md).

Event-driven in-play intelligence engine. Replaces the 5-minute polling
cadence of `scripts/live_inplay_daemon.py` with sub-30-second reactive
projections, in-process pub/sub, parallel multi-book line scraping,
and a `rich` terminal dashboard.

**Latency budget:** play-by-play event → re-projected bet → dashboard
render in **< 500 ms** (measured by `tests/test_live_engine_v2_integration.py`).

**Measured latency (20-sample burst, stubbed project + line lookup):**
- p50 **0.24 ms**
- p95 **0.85 ms**
- max **0.85 ms**

The real-world bottleneck will be the projection math
(`src.prediction.live_engine.project_from_snapshot`) which runs a
LightGBM minute-trajectory inference + 5 residual heads per snapshot
— typically 30-80 ms per snapshot in production. Still well inside
the 500ms budget.

## Quick start

Headless:
```
python scripts/live_orchestrator.py --game-id 0042500315
```

With dashboard (recommended):
```
python scripts/live_orchestrator.py --game-id 0042500315 --enable-dashboard
```

Custom cadences:
```
python scripts/live_orchestrator.py \
  --game-id 0042500315 \
  --pbp-interval 10 \
  --snapshot-interval 30 \
  --lineup-interval 30 \
  --line-scrape-interval 30 \
  --books pin,bov,fd,pp \
  --enable-dashboard
```

## Architecture (event flow)

```
                ┌──────────────────────────────────────────────┐
                │                EventBus (in-proc)            │
                │  pbp.*  lineup.*  snapshot.*  lines.*        │
                │  projection.updated  bet.recommended         │
                └──────────────────────────────────────────────┘
                  ▲      ▲          ▲           ▲       │
                  │      │          │           │       ▼
   ┌───────────┐  │  ┌───────┐ ┌──────────┐ ┌────────┐ ┌──────────┐
   │pbp_poller │──┘  │lineup │ │parallel_ │ │box_snap│ │dashboard │
   │  (10s)    │     │tracker│ │scraper   │ │_poller │ │  (rich)  │
   └───────────┘     │ (30s) │ │ (30s)    │ │ (30s)  │ └──────────┘
                     └───────┘ └──────────┘ └────────┘       ▲
                                                              │
   ┌─────────────────────────────────┐  ┌──────────────────┐  │
   │ reactive_projector              │  │ decision_engine  │──┘
   │  - on pbp.foul reproject player │  │  - 8-gate chain  │
   │  - on pbp.sub  reproject players│  │  - Kelly cap 25% │
   │  - on lineup.* stamp defender   │  │  - tier S/A/B    │
   │  - on pbp.period_end full slate │  └──────────────────┘
   └─────────────────────────────────┘
```

## Dashboard panes

| Pane | Content |
|------|---------|
| HEADER  | game card: teams, score, period, clock, momentum arrow |
| LEFT    | on-court lineups, foul counts (red ≥4, yellow ≥3) |
| CENTER  | top 5 live bets — tier badge, EV%, Kelly%, EV sparkline |
| RIGHT   | last 10 PBP events with timestamps and topic colour |
| BOTTOM  | last 5 alerts + per-daemon health strip + render stats |

Colour conventions:
- **green** — upside / positive EV
- **red** — downside / high foul count
- **gold1** — S-tier bet (EV ≥ 8% AND projection delta ≥ 1.0 stat units)
- **cyan** — PBP timestamps, headline period/clock
- **dim** — idle / non-LIVE games

## Decision engine — 8-gate chain

A bet must pass all of these (in order) to be ranked:

1. `player_present` — projection row has `projected_final`
2. `line_present` — book line is numeric
3. `sigma_known` — stat is in the calibrated sigma table
4. `odds_sane` — American odds within ±300
5. `stat_supported` — stat in {pts, reb, ast, fg3m, stl, blk, tov, pra}
6. `market_open` — book has not closed the market
7. `not_settled` — current_stat < line + 50 (skip already-settled bets)
8. `min_edge` — projection must be ≥ 0.05 σ away from the line (anti-noise)

Tiers:
- **S** EV ≥ 8% AND |projection delta| ≥ 1.0 stat units
- **A** EV ≥ 4%
- **B** EV ≥ 1% (display-only — below auto-bet threshold)

## The in-game repricer: pregame prior x realized state

What `reactive_projector` calls on each event is the in-game projection core
(`src.prediction.live_engine.project_from_snapshot`). Conceptually it FUSES two
sources of truth:

```
   PREGAME PRIOR                          REALIZED STATE
   (the possession sim /                  (this snapshot: score, clock, each
    rating distribution,                   player's box line, fouls, pace,
    "what we believed at tip")             who is on the floor)
        |                                        |
        |                                        |
        +------------------+   blend   +---------+
                           |  w(time, margin)    |
                           v                     v
            projected_final = prior_remaining * w  +  state_extrapolation * (1-w)
                           (q50 = the served point; q10/q90 bands around it)
```

The blend is **elapsed-weighted**: early in the game `w` leans on the prior (one
snapshot of a 6-minute Q1 is mostly noise); late in the game it leans on realized
state (at 36 minutes observed, linear extrapolation of the box is already near
optimal). This is exactly why the pregame-prior detail layer is measured to help
MOST at end-Q1 and LEAST at end-Q3 -- the tell that the gain is a real early-game
team-strength signal, not a shrink-to-current artifact (see Gating below).

In the consolidated path the engine stacks transforms keyed on snapshot BOUNDARIES
(endQ1 / endQ2 / endQ3), each one validated independently and applied only at the
boundary it was trained against. The canonical fully-parametric form is the
Bayesian repricer (`CV_INGAME_STATE` -> `src/ingame/live_state_hook.py`), whose
DEFAULT trust curve is the IDENTITY: trust_w = 0 -> posterior == prior -> every row
is left untouched -> byte-identical to OFF. It only re-prices once a trust curve is
GATED on held-out RMSE+bias. Default-OFF, the served numbers are the validated
cycle-88 core.

## Gating each in-game detail layer vs base (held-out Brier)

No detail layer ships on intuition. Each is gated by
`scripts/platformkit/ingame/ingame_layer_gate_nba.py`, which asks one question:

> Does adding this layer beat a simpler BASE in-game model on held-out Brier?

```
   BASE    = p_live(score_diff, frac_elapsed)        # (margin, time) only
   +PRIOR  = blend(p0_elo, p_live, w(time, margin))  # BASE + leak-free pregame Elo
```

Discipline (hard-learned -- single-fold lifts are artifacts):
- `p0` is a STRICTLY-pregame Elo snapshot (a game never sees its own or any later
  outcome); the weight surface `w` is fit on the TRAIN fold ONLY, never the test fold.
- >= 3 expanding-window walk-forward cutoffs, pooled OOS Brier + per-fold stability.
- Diebold-Mariano clustered by `game_id` (an iid SE manufactures fake significance).
- SHIP iff Brier(+PRIOR) < Brier(BASE) AND DM p < 0.05 AND the sign holds on >= 2/3
  folds. Otherwise REJECT -- a valid, honest result.

| layer / boundary | what it adds | verdict basis |
|------------------|--------------|---------------|
| pregame Elo prior | BASE + leak-free p0, w fit on train | held-out Brier, DM clustered |
| period-specific heads (endQ1/endQ2) | LightGBM remaining-stat vs linear | per-stat WF MAE, 4/4 folds |
| endQ3 learned-Q4 minutes | learned remaining min vs heuristic foul factor | WF MAE, 7/7 stats |
| residual heads (endQ2/endQ3) | per-stat learned correction | WF MAE, 4/4 folds |

**HONESTY RAIL (non-negotiable):** every number here is forecaster QUALITY
(calibration / sharpness), NOT a dollar edge. A live book sees the same game state
we do; in-game conditioning is a measured CALIBRATION win across all 4 sports
(NBA static->conditional Brier ~0.209 -> ~0.159; leak-free walk-forward endQ3 Brier
~0.141), and the "vs the close" verdict is UNPROVEN -- there is no in-play odds
archive to grade against. No `$` / ROI / edge is claimed anywhere in this engine.
See the retraction list and proof artifacts in
[../docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) and
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Alert dedup

- Same `(player, stat, side)` suppressed for **5 minutes** after first emit
- Drop if projection moved < **0.3 stat units**
- Severity floor configurable (`min_severity="medium"` default)
- Alerts within a **60-second** window bundle into a single digest
- All emits also flow to `WebhookNotifier` (Discord/Slack)

## Webhook setup

```powershell
pwsh scripts/setup_discord_webhook.ps1 -WebhookUrl "https://discord.com/api/webhooks/.../..."
```

Persists `DISCORD_ALERT_WEBHOOK` to your User environment block and
fires a test alert via `src/notifications/webhook_alerts.py`.

## Daemon watchdog

Live Engine v2 is registered in `scripts/daemon_registry.json` as
`live_orchestrator` with a 10s heartbeat (`heartbeat_optional: true`
because it's a multi-task asyncio process). The standard
`scripts/daemon_watchdog.py` will detect a hung process and restart it.

## Coexistence with legacy daemon

This engine runs **in parallel** to `scripts/live_inplay_daemon.py`
(the 5-minute snapshot poller). Both share the same canonical
snapshot dir (`data/live/`) and projection helper
(`src.prediction.live_engine.project_from_snapshot`). The legacy
daemon continues to drive the in-play ledger CSV; v2 drives the
real-time bet ranker + dashboard. Opt in to v2 by launching the
orchestrator — there is no rip-out of the legacy path.

## NBA API v3 wrapper

`scripts/nba_api_v3_patch.py` exposes three robust wrappers:

| Function | Endpoint |
|----------|----------|
| `fetch_pbp_v3(game_id)`     | `PlayByPlayV3` |
| `fetch_matchups_v3(game_id, period=None)` | `BoxScoreMatchupsV3` |
| `fetch_box_v3(game_id)`     | `BoxScoreTraditionalV3` + `BoxScoreAdvancedV3` |

Each respects the project-wide 0.6s rate limit, backs off on 403/429/timeout,
and patches `src.data.nba_api_headers_patch` on import.

Smoke test:
```
python scripts/nba_api_v3_patch.py 0042500315
```

## Troubleshooting

**Dashboard shows "Waiting for first snapshot…"**
The 30-sec snapshot poll hasn't completed yet. Wait ≤ 30s, or check
`data/live/` for fresh files.

**No bets appear in the Top Bets pane**
Either (a) no book line for the projected players has been scraped
yet (check `data/lines/<date>_*.csv`), or (b) all gate-passing bets
are below the `emit_floor_ev` (default 1%). Toggle
`DecisionEngine(emit_floor_ev=0.0)` to confirm.

**`aiohttp not installed; cannot run parallel_scraper`**
Install once into the conda env:
```
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pip install aiohttp rich
```

**Webhook env var not picked up by Python**
PowerShell `[Environment]::SetEnvironmentVariable(..., 'User')` only
affects NEW processes. Close + reopen your terminal, or set
`$env:DISCORD_ALERT_WEBHOOK = '<url>'` in the current session.

**SIGINT (Ctrl-C) on Windows doesn't gracefully stop**
Windows asyncio has no `add_signal_handler` for SIGINT. Send two
Ctrl-Cs; the asyncio run loop falls back to KeyboardInterrupt.

## Test coverage

| Suite | Count |
|-------|-------|
| `tests/test_event_bus.py` | 7 |
| `tests/test_latency_optimizer.py` | 9 |
| `tests/test_nba_api_v3_patch.py` | 8 |
| `tests/test_live_engine_v2_pollers.py` | 6 |
| `tests/test_live_engine_v2_reactive.py` | 8 |
| `tests/test_live_engine_v2_ui.py` | 7 |
| `tests/test_live_engine_v2_integration.py` | 3 |
| **TOTAL** | **48 new tests** |

Plus 60 legacy tests across `test_live_engine.py`,
`test_live_inplay_daemon.py`, `test_live_alerts.py`,
`test_live_dashboard.py`, `test_data_live.py`, `test_live_factors.py`
remain green — **0 regressions**.

## Files shipped

| Path | Purpose |
|------|---------|
| `src/live/__init__.py`           | new package |
| `src/live/event_bus.py`          | asyncio pub/sub |
| `src/live/latency_optimizer.py`  | LRU + coalescer + probes |
| `src/live/alert_dedup.py`        | cooldown + delta + digest |
| `src/prediction/reactive_projector.py` | event-driven reprojection |
| `src/prediction/decision_engine.py`    | EV ranker + tiers |
| `scripts/nba_api_v3_patch.py`    | v3 endpoint wrappers |
| `scripts/pbp_poller.py`          | 10s PBP fetcher |
| `scripts/lineup_tracker.py`      | 30s matchup fetcher |
| `scripts/parallel_scraper.py`    | async multi-book scraper |
| `scripts/box_snapshot_poller.py` | 30s box-score poller |
| `scripts/live_dashboard_v2.py`   | rich TUI |
| `scripts/setup_discord_webhook.ps1` | webhook helper |
| `scripts/live_orchestrator.py`   | entry point |
| `scripts/daemon_registry.json`   | watchdog registration (edited) |


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
