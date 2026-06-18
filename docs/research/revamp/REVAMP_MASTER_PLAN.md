# REVAMP MASTER PLAN -- multi-sport AI -> advanced frontend + paper auto-betting
_Authored 2026-06-17. The single map for the full revamp. Tracks to .planning/NOW.md._

## North star + honesty rails (non-negotiable)
- Goal = **best predictions** (most accurate / best-calibrated per sport), measured vs the devigged close, and a system that **knows every bet, prices it, ranks it by expected money, and proves it on paper before real money.**
- Honest truths held: the **sharp** pregame close is efficient and our model ~matches it; real value lives in **soft books, props, live/in-game lag, stale lines, prediction markets, and correlated SGPs** -- NOT in a model that beats sharp mainlines. "Lines aren't as good as we think" is true **only for soft/lazy markets**; widening scope = more shots at those, measured by **CLV**, never asserted.
- Paper-only now; real money **gated on proven positive CLV**. No fabricated edges. Leak-free + eval-gate on every model change.

## Target end state (your vision, precise)
One fast service where the **same AI feeds both** (a) a highly-advanced frontend (every live line, all sports, future games, click-a-game -> full report, always reloading fast) and (b) a paper auto-bettor that scores **1000s of live bets**, ranks by which makes the most money, and trades them on paper -- with correct, fast line scraping underneath, and a self-improving loop that gets smarter from real outcomes.

## Architecture keystone: ONE compute -> snapshot -> both consumers
The current killer of "fast": the API rebuilds predictors + refetches odds on every request. Fix = a **background snapshot service** that, each cycle, computes per-sport (predictions + full bet boards + live in-game + ranked best bets + odds) ONCE, writes `data/frontend/snapshots/<sport>.json`, and BOTH the frontend API and the paper auto-bettor **read the snapshot** (never recompute in the request path). Frontend becomes instant; auto-bet and UI show the identical ranked book; models compute once.

```
ingest/odds-scrape --> [warm models + odds]  --(every cycle)-->  snapshot/*.json
                                                                   |        |
                                                          frontend API   paper auto-bettor
                                                          (instant read)  (ranks+trades paper)
                                                                   |
                                                          self-improve loop <-- grade settled
```

## The 12 workstreams (mapped)

**01 Cleanup + speed.** Remove dead/duplicate modules + _archive/worktrees clutter; kill per-request predictor rebuilds (warm cache); TTL-cache odds; precompute bet boards; obey 300-LOC. Outcome: every surface reads a snapshot; nothing blocks on compute/network.

**02 Smart AI per sport.** MLB pitcher-blind -> add starting-pitcher ratings (biggest single lever). Soccer goals-rate -> fitted Dixon-Coles (attack/defense/home/time-decay). Tennis -> wire serve/return sidecar + surface-Elo + WTA. NBA -> same-day freshness/availability (the only real pregame lever; rest of pregame is at the data ceiling). Every change leak-free + eval-gate-gated; honest null is fine.

**03 Funnel actually flowing.** Known breaks: next-tier data is on disk but discarded at ingest; atlas/intelligence features are built but NOT read at predict time; freshness flag off. Fix = wire each stage to feed the next, validated, so DATA->SIGNALS->MODELS->ENGINES->PREDICTIONS->INTELLIGENCE is a live pipe, not disconnected parts.

**04 Every bet (taxonomy + payouts).** Enumerate every market per sport incl. player props, alt-line ladders, combos (PRA), period/inning, SGP + correlations, futures. Know the payout math (odds<->implied prob, how alt-ladders price off the distribution, how SGP correlation reprices a parlay). "10 pts vs 30 pts" = full prop-ladder pricing off each player's projected distribution. Map to what markets.py already emits vs gaps (props depth, SGP correlation engine).

**05 Line scraping (correct + fast, 1000s of bets).** Source stack for breadth+props legitimately (The Odds API paid tier for props/alts; ESPN; Kalshi/Polymarket official; NO ToS-violating DK/FD scraping). Free /events enumeration + batched /odds + prop endpoints; quota budgeting via x-requests-remaining; team/market normalization + cross-book matching (the load-bearing correctness problem); stale-line detection; devig. Feeds the snapshot.

**06 EV ranking (which bet makes the most money).** fair prob -> devig best/sharp price -> EV/$1 -> rank by **fractional-Kelly expected growth** (not raw EV), correlation-aware (don't double-count SGP legs), limit/variance/payout-aware. Honesty: most "+EV" is vs soft books, not the sharp line; every ranked bet must clear CLV before trust. Feeds both UI best-bets and the paper bettor.

**07 Advanced fast frontend.** React+shadcn served from FastAPI (one URL). Screens: live board (all sports), futures, +EV feed, arb feed, **click-game -> full report** (every market, model vs line, EV, live in-game), bet tracker/CLV. Real-time via SSE/fast-poll off the snapshot; virtualized tables for 1000s of rows; never blocks. Honesty UI rails throughout.

**08 Paper auto-bet + execution.** Live loop scores+ranks 1000s of bets, sizes (frac-Kelly + caps + correlation), records paper, grades on settle, computes CLV, feeds the frontend the same ranked book. Real-money path designed but HARD-GATED (Kalshi/Polymarket order APIs; place_order stubs raise; ENABLED=False; kill-switch; only unlocks on proven CLV).

**09 Data backbone.** One warm prediction+odds service -> snapshot -> shared by frontend + auto-bet (compute once). Incremental data updates (append, don't rebuild). Refresh cadences: ratings daily, lines minutes, live seconds.

**10 Inefficiency + widen scope (honest).** Real beatable pockets, ranked: soft/recreational books off sharp consensus; lazily-priced player props + obscure markets; live/in-game lag; stale lines on slow books; prediction-market vs sportsbook mispricing; niche leagues; correlated SGP mispricing. Detect each in-data; PROVE with CLV. Widen scope = cover more of these, not "beat sharp lines."

**11 Props + correlation modeling.** Per-player projected distributions -> every prop + ladder priced; joint/correlation structure (the playstyle-correlation work) for SGP pricing. The "10->30 points" knowledge = the player's scoring distribution, surfaced as a priced ladder.

**12 Orchestration + self-improvement.** auto_loop (paper->grade->improve) already running; extend it to drive the snapshot + ranking; eval-gate ratchet makes models only-improve-or-hold from real outcomes.

## Phased build order (what runs, in order)
- **Phase 0 -- Clean + Fast backbone (FOUNDATION FIRST, per your ask):** snapshot service (compute once -> snapshot), frontend + auto-bet read it, warm predictor cache, kill per-request rebuilds, archive dead code. _Outcome: everything fast + AI feeds both surfaces from one source._
- **Phase 1 -- Smart AI + funnel:** MLB starting pitcher, soccer Dixon-Coles, tennis serve/return+WTA, NBA freshness; wire the dead funnel stages; all gated. _Outcome: models genuinely better, measured vs close._
- **Phase 2 -- Full bet coverage + line scraping:** every market incl. props/alts/SGP; the real multi-book/prop line scraper feeding the snapshot. _Outcome: 1000s of live bets, correct + fast._
- **Phase 3 -- EV ranking + advanced frontend:** the Kelly-growth correlation-aware ranker; the served, real-time, click-through React UI. _Outcome: see + rank every bet, fast._
- **Phase 4 -- Paper auto-bet at scale + prove:** auto-bet the ranked book on paper, grade, accrue CLV; self-improve ratchet. Real money ONLY after CLV proves positive. _Outcome: the measured verdict on whether it makes money._

## Run now
Phase 0 keystone first: the snapshot backbone + warm cache, so the frontend is instant and the AI feeds both the UI and the paper bettor from one fast source. Everything else builds on it.
