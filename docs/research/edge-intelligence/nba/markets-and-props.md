# NBA MARKETS + PROP LADDER -- the full surface, what we price, which lines are soft

_Sport = NBA. The complete market/prop surface, mapped to what the MC sim + prop stack can
price coherently, where the book lines are soft/lazy, and where we have gaps. Grounded in
08-nba-montecarlo-sim-ratings (one sim -> whole menu) + 07-nba-prediction-models. ASCII._

## How NBA markets are priced here (two engines)
1. **Per-game prop stack** (`src/prediction/prop_pergame.py`, 5,403 LOC): marginal per-stat
   distributions for pts/reb/ast/fg3m/stl/blk/tov; leak-free per-game; XGB+LGB+MLP NNLS blend
   + isotonic + q50 quantile heads for {reb,blk,stl,tov,fg3m}. This is the marginal book.
2. **Possession MC sim** (`src/sim/basketball_sim.py` + `fast_sim.py`): ONE 20k-sim run yields
   15 per-sim sample arrays per player + per-sim team totals, so EVERY market below is read
   off the SAME simulated games -> internally COHERENT. `build_cv_board.py` prices the board;
   `market_catalog.py` / `sim_derivative_markets.py` enumerate the menu; `sgp_from_sim.py`
   prices joints. This is the engine that makes combos/SGPs possible.

## Team markets (EFFICIENT -- match the close)

| Market | We price it? | Source | Soft? | Verdict |
|---|---|---|---|---|
| Moneyline | yes | win-prob model + sim win_home | NO (sharp) | match close; CLV~0 |
| Spread (full) | yes | sim margin distribution | NO | "trust spread not total" (08:201) |
| Game total | yes | sim home+away totals | mild bias (+4.5 playoff) | trails close by freshness |
| Team total | yes | per-team sim totals | mild | derived; same bias |
| Alt-spreads / alt-totals | yes | read off margin/total dist | sometimes lazy on soft books | calibration-prove first |
| 1H / 1Q / quarter lines | partial | `game_clock_sim.py` quarter scores | YES on soft books | gap: not calibration-proven |
| Race-to-N / first-basket / exotics | sim-derivable | `sim_derivative_markets.py` | YES (low attention) | HYPOTHESIS, unproven |

## Player prop ladder (the P1 pocket -- where soft lines live)

| Prop stat | Marginal model | Sim sample | Holdout R2 | Soft-book softness | Verdict |
|---|---|---|---|---|---|
| Points | blend (NOT q50) | yes | 0.5105 | medium | at ceiling; match close |
| Rebounds | q50 | yes | 0.4224 | medium | at ceiling |
| **Assists** | **blend, calibration OFF on purpose** | yes | 0.4988 | **soft books lazy on playmakers** | the ONE model edge (~+7%); KEEP RAW; never playoffs |
| 3PM | q50 | yes | 0.3151 | high (volatile, lazily priced) | only atlas-positive stat; modest |
| Steals | q50 | yes (recal Poisson) | 0.1120 | n/a | NON-BETTABLE (noise) -- flag, do not price |
| Blocks | q50 | yes (NB if overdispersed) | 0.2166 | high | sigma too tight x1.86; CV-feature candidate |
| Turnovers | q50 | yes | 0.2960 | low | match close |

### Derived / combo prop markets (all coherent off one sim run)
- **PRA / PR / PA / RA combos** -- summed per-sim arrays; books price these reasonably but soft
  books lag on injured-teammate redistribution.
- **Double-double / triple-double** -- count-stat recal matters here: raw chain under-counts
  (sim P(Wemby>=1 blk) 60% vs 95% real, 08:122); fixed via `secondary_targets` Poisson/NB recal.
  DD/TD priced in `build_cv_board.py`; calibration-prove vs realized before trusting.
- **Milestone ladders / thresholds** (>=10 ast, >=20 pts, >=3 3PM) -- read off the CDF of the
  per-sim sample; soft books price ladders independently of the marginal -> mispricing pocket.
- **Alt prop lines** -- same CDF read; soft books often set alt lines off a stale base.

### Same-game parlays (the P5 pocket -- the sim's structural advantage)
`sgp_from_sim.joint_prob` reads the joint hit-prob directly off the coherent samples and reports
correlation lift vs the independence product. Teammate correlation EMERGES (~-0.10) from the
shared scoring pie rather than being imposed (08:93,174). Books price SGP legs independently and
misjudge the joint -> this is the most structurally defensible NBA pocket. CAVEATS: (1) no real
SGP price history on disk -> ROI unproven, joint calibration must be proven vs realized first;
(2) same-player cross-stat correlation only PARTIALLY modeled -- realized pts-reb corr runs
+0.2..0.35 above the raw sim, patched by a bolt-on CV_MIN_VAR corrector at board time (08:208).

## Which lines are SOFT / LAZY (where to point the feed once wired)
- DFS pick'em (PrizePicks/Underdog) standard projections: lazily set, fixed payout, CANNOT move
  to kill a genuinely mispriced projection (structural crack, framework P1). Prove via P(over)
  calibration vs realized + realized ROI at fixed payout + DFS-line movement (CLV-vs-close undefined).
- Soft-book ALT lines and PROP LADDERS (independent of the marginal).
- AST props on high-playmaking roles (the documented model divergence).
- Quarter / 1H lines on low-attention books.
- SGP legs (correlation blindspot, all books).

## Gaps (priced but not validated, or not priced)
- We PRICE the full menu but have NO book-line comparison for props at scale (no keyless prop
  feed -- the top get-to-edge step). EV vs a soft line is a CANDIDATE, not proven.
- DD/TD/milestone/SGP calibration vs realized is NOT yet measured leak-free.
- In-game props are research-only (routed ensemble OFF, single-corpus).
- Quarter/1H markets: sim can produce them (`game_clock_sim`) but no calibration proof.
