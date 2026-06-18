---
updated: 2026-06-17
north_star: BEST predictions per sport (beat/match the devigged close on OOS calibration); honest, no fabricated edge.
active_project: sports-betting decision-support product (4 sports) + own keyless odds API
loop_queue_source: this file's NEXT list
---

# NOW -- the single source of truth for "what's done / what's next"

> Read THIS first (30s) before any work. Update it before you finish: tick a NEXT item, add the follow-up, rotate overflow into DONE.md. If git HEAD is newer than `updated` above, this file is stale -- refresh it.
> Invariants/gotchas/paths: memory `reference-invariants-paths-atlases`. Claimable vs retracted numbers: `docs/JOB_EVIDENCE_PACKET.md`.

## Active project
A decision-support betting product: model predictions for NBA / MLB / soccer-club / World-Cup(soccer_intl) / tennis, with full per-sport market surfaces, our own keyless odds aggregator (ESPN + Kalshi + Polymarket), line-shopping / arb / +EV, and a CLV ledger. Manual placement only; real money gated on proven CLV. Front end runs at http://127.0.0.1:8098/ (`python -m scripts.platformkit.frontend.serve`); React/shadcn UI in `scripts/platformkit/frontend/web/` (`npm run dev`).

## ACTIVE MILESTONE -- "First WORLD CUP prop edge, surfaced + paper-bet"
Plan LOCKED 2026-06-17: docs/research/revamp/REVAMP_DECISIONS_AND_PHASES.md (read it for the
full task graph + done-when + grounded probes). First vertical PIVOTED NBA->World Cup (NBA
offseason; WC = 3,927 live PrizePicks props NOW). Model = per-90 rate x E[minutes] ->
Poisson/NB; lines from Underdog/PrizePicks/FanDuel (probed keyless-OK) + DK via Playwright;
per-player stats from ESPN fifa.world rosters block (keyless, ~85% of prop volume). Surface
ALL edges tier-labeled (model-view/calibration/CLV); paper-only; CLV is the yardstick.

## NEXT (max 5 -- action | where | done-when)
1. Full club-prior build for ALL ~1200 WC players (running in bg) -> regen snapshot | domains/soccer/ingest_espn_athlete.py | espn_club_priors.parquet covers the slate; snapshot shows reliable edges across all matches not just sample
2. C6 props eval-gate: P(over) calibration + Brier/BSS on settled props | scripts/platformkit/eval_gate/ | gate scores forward-settled prop set per stat
3. UI: World Cup prop board view (click player -> priced ladder + tier labels) | scripts/platformkit/frontend/web/ or static | board visible at :8098 with reliable/thin labels
4. Sofascore deeper priors (tackles/passes) + closing-line capture for TRUE prop CLV | domains/soccer/ + refresh_daemon | tackles/passes modelable; closing prop line logged -> CLV computable
5. Run refresh_daemon + prop_paper grading on a cadence | scripts/platformkit/ | snapshots refresh + reliable prop bets auto-record/grade unattended

## RECENT DONE (max ~7; older -> DONE.md)
- OVERNIGHT IMPROVEMENT CYCLE (autonomous, 2026-06-17->18): added TRUE-CLV capture (prop_line_history.py logs lines each tick -> CLV-vs-close in prop_summary; loop restarted w/ it). Built + HONESTLY MEASURED 2 model levers, both correctly held back: opponent-adjustment (team_defense.py, leak-free, wired live) = measured NULL on the thin 1-round WC slice (opp has no strictly-earlier history yet; activates as rounds accrue); isotonic P(over) recal (prop_recal.py) = DEFER, proper temporal train/test shows it OVERFITS 24 matches (OOS Brier slightly worse) -- module ready, NOT applied live. Meta: WC is data-limited (24 matches); MLB (full season) is the higher-value next vertical. All per-file tests green; paper-only; no $-claims (2026-06-18)
- WORLD CUP PLAYER-PROP VERTICAL built end-to-end (Milestone 1, plan REVAMP_DECISIONS_AND_PHASES.md): snapshot backbone (compute-once -> snapshots/<sport>.json, serve reads it, refresh_daemon); deep prop scrapers (Underdog two-way priced + PrizePicks pick'em live; FanDuel parser ready/props-not-posted; DK=Playwright-deferred); ESPN per-player WC ingest (1241 rows/24 matches); Poisson/NB prop engine w/ dispersion calibration + EV honesty guard; resolver (98% name hit) + prop_edge board (/api/props, in snapshot); prop settlement + paper-CLV loop (records ONLY reliable+ok edges -> 0 today, honest); CLUB-SEASON PRIORS via ESPN athlete overview = the unlock (0 -> 321 reliable edges on a 36-player sample). ~15 new modules, all per-file tests green, all in scripts/platformkit + domains/soccer. PAPER ONLY, tier-labeled, no $-edge claims (2026-06-17)
- Clickable per-game BET BOARD: GET /api/game returns every market ranked (best_bets + groups) across all sports; React detail Dialog built (builds clean). Honest: EV only where priced, else MODEL_VIEW (2026-06-17)
- LIVE in-game tracking working end-to-end: ESPN keyless feed -> predict_live -> /api/live; verified on live MLB (4 games) + World Cup (England 1-1 Croatia 40' -> 45.1% as Croatia equalized) (2026-06-17)
- In-game bugs fixed: soccer_intl gained a predict_live (was pregame-only); MLB live anchored to Elo; NBA buzzer = exact 1.0 (2026-06-17)
- Paper/auto-bet loop verified SAFE: no real-money path (place_order stubs raise, ENABLED=False, gate needs BEATS_CLOSE); paper_autobet.py built; CLV loop end-to-end (2026-06-17)
- Claude-org reorg: memory 33.5KB->20.4KB; .planning/NOW.md SSOT; rules now load (@-imports); guard hooks wired+verified; skills consolidated (2026-06-17)
- Full per-sport market coverage built (NBA/MLB/soccer/tennis), 45 tests; soccer gained a real 1X2 moneyline (2026-06-17)
- Own keyless odds API (odds_provider/) + line-shop/arb/EV + CLV ledger; MLB odds attach via team_resolver (2026-06-17)
- Adversarial-review loop fixed 2 confirmed bugs (wrong-game odds match; MLB integer-line push) (2026-06-17)
- React+shadcn UI scaffolded + builds; World Cup wired into the board (2026-06-17)
- CRPS+pinball distributional metrics shipped to eval_gate/scoring.py (C7) (2026-06-17)

## Active blockers
- WC prop edges: reliability depends on CLUB priors (1 WC match/player so far). Sample of 36 -> 321 reliable; FULL ~1200-player prior build running in bg -> then snapshot has reliable edges slate-wide. CLV proof needs forward settlement to accrue (paper loop records reliable+ok only).
- WC prop CLV-vs-close not yet computable: DFS/book CLOSING prop lines aren't captured yet (need refresh_daemon to log line movement). Until then prove via P(over) calibration + realized ROI at taken price (Underdog two-way) -- honest, not CLV.
- Self-improve loop running but improve verdict = INSUFFICIENT_DATA until ~60 real games settle (cold start; accrues automatically).
- Early paper ROI is NEGATIVE (-47% on 7 bets, small-N): the naive permissive paper policy bets soft-book "+EV" artifacts on a model that matches the close. Expected; CLV/larger-N is the real verdict, not this.
- Live odds limited to ESPN's single republished line until a 2nd venue matches -> no real arb yet.
- Real-money execution: GATED on proven positive CLV (paper-first). Loop is the gate's data source.
- HUMAN-CONFIRM list from the 2026-06-16 org sprint still pending (public push, key rotation, MCP registration).

## Pointers (links, never inline)
- Betting product research: docs/research/betting-product/
- Claude-org reorg research: docs/research/claude-org/
- Memory frontier entries: memory `project-betting-product-research-2026-06-17`, `project-betting-frontend-intl-mlb-2026-06-17`
