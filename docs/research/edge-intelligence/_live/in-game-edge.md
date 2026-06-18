# IN-GAME / LIVE EDGE -- cross-sport (the cleanest measured calibration win, structurally hard to TRADE)

_Part of the edge-intelligence corpus. Grounds: project-deep-dive/11-live-ingame-layer.md
(authoritative), 04-soccer-wc-prop-engine.md, 05-mlb-prop-engine.md, and the real proof
harnesses (run live below). Binding frame: markets are efficient; the north star is CALIBRATION
vs reality, NOT a $-edge. A live book ALSO sees the score, so the in-game improvement is
forecaster QUALITY, not realized profit. No $-edge claimed anywhere. ASCII only._

---

## 0. TL;DR (the honest two sentences)

Conditioning a forecast on the REALIZED in-game score is the single largest, cleanest
calibration improvement in the whole project -- measured, leak-free, replicable across all four
sports (NBA, MLB, soccer, tennis). It is mostly NOT tradeable because the live sportsbook prices
the same realized score in real time (and sees substitutions/injuries/pace we do not); the NARROW
exceptions are (a) thin/slow in-play markets where the book lags, and (b) IN-GAME PROP
DISTRIBUTIONS conditioned on realized minutes/usage -- the highest-upside frontier, still a
calibration play, gated, never a claimed edge.

---

## 1. HOW LIVE REPRICING WORKS -- `GameState -> predict_live`, score-anchor + variance-collapse

The platform stack is sport-blind and uniform (`scripts/platformkit/live_repricer.py:29`):
`GameState(sport, elapsed_minutes, home_score, away_score, pregame_params, extra)` ->
`get_repricer(sport).reprice(state) -> Dict` (factory `:236`). Consumers never call the raw
repricer; they call `domains/<sport>/predictor.py::predict_live(...)`, which (1) ANCHORS the
repricer's pregame win-prob to the SAME Elo/MOV win-prob the pregame `predict()` reports (so
pregame and in-game agree at elapsed=0 -- the W146/W156/W157 cohesion fix), then (2) applies a
fitted recalibrator. Unwired sports degrade to a graceful `_SportStub` (`status="not_wired"`,
never crashes).

The shared idea splits by score topology:

- **Continuous / high-scoring (NBA)** -- `domains/basketball_nba/repricer.py:43`. A discrete
  scoreline matrix is the wrong shape, so it uses a **Gaussian score-anchor remaining-points**
  model:
  `margin_mean = (h0-a0) + (mu_home-mu_away)*rem_frac` (`repricer.py:57`),
  `margin_sd = margin_sigma * sqrt(rem_frac)` (`:59`, Brownian),
  `win_home = Phi(margin_mean/margin_sd)` (`:62`, `_norm_cdf` erf-based, no scipy).
  Defaults: `_DEF_MARGIN_SIGMA = 13.5`, `_DEF_TOTAL_SIGMA = 18.0` (`:29-30`). As the clock runs,
  `rem_frac -> 0`, the realized score becomes a fixed anchor and the variance **collapses** onto
  the outcome. The empirical justification (the keystone): pooled team-score RMSE shrinks
  Q1 ~= 12.5 -> Q4 ~= 4.2.

- **Discrete / low-scoring (soccer, MLB)** -- scale the pregame scoring-rate lambdas by the
  REMAINING fraction of the match, build a remaining-score probability MATRIX, SHIFT it by the
  score already on the board, read all markets off the final-score distribution.
  - Soccer (`live_repricer.py:88`): `lam_rem = lam_pregame * (90-elapsed)/90`, Dixon-Coles
    `scoreline_matrix`, emit 1X2 / O-U / BTTS / correct-score live.
  - MLB (`domains/mlb/repricer.py:79`): over-dispersed NegBinom run engine; `_remaining_frac`
    uses an EMPIRICAL per-inning run curve `_INNING_SHARES = (0.122, 0.101, ... , 0.096)`
    (`:36`) interpolated at fractional innings, NOT a flat 1/9 (1st inning ~12.2%, late innings
    less). A regulation tie stays live with one residual `_EXTRA_INNING_FRAC = 1/9` lambda so
    the over is not frozen (`:114`).

- **Set-level (tennis)** -- `domains/tennis/repricer.py:44`. Conditions on the completed-set
  score and computes the analytic race-to-N-sets conditional `_race_win_prob(p, need_1, need_2)`
  (`:31`) -- deliberately NOT a re-sim, so a probability is Brier-graded (dodges the
  MAE-vs-RMSE median-shift artifact). Small bounded `_GAMES_LEAN = 0.04` (`:28`).

**Why variance-collapse is mathematically the win.** The pregame close integrates all PUBLIC
pre-match info but has NEVER seen the realized score. The realized score is genuinely new
information: it both shifts the conditional mean (`margin_mean` carries `h0-a0`) and shrinks the
conditional variance (`sqrt(rem_frac)`). A forecast that uses it is provably sharper than one
that does not -- this is the cleanest, most defensible improvement in the project precisely
because it is a calibration win and not a market-beating claim.

---

## 2. THE MEASURED IMPROVEMENTS (CALIBRATION-PROVEN, leak-free; NOT profit)

All numbers below are from the REAL leak-free proof harnesses, re-run 2026-06-18 (not copied
from docs). Each reconstructs mid-game states from the real corpus, reprices, and scores
Brier(conditional) vs Brier(pregame-Elo) on a held-out split. **Tier: CALIBRATION-PROVEN. These
are forecaster-quality (Brier/ECE) numbers, NOT a $-edge -- a live book also sees the score.**

| Sport | proof harness | corpus | pregame-Elo Brier | score-only | COMBINED (prior+score) | ECE raw -> recal |
|-------|---------------|--------|-------------------|-----------|------------------------|------------------|
| NBA   | `proof_nba/ingame_accuracy.py` | 1313 games, 3939 q-checkpoints | **0.20888** | 0.17235 | **0.15859** | 0.05921 -> 0.01211 (T=1.445) |
| MLB   | `proof_mlb/ingame_accuracy.py` | 23279 games, 31669 chk | **0.24096** | 0.12769 | **0.12640** | 0.00853 -> 0.00881 (NULL: already calibrated) |
| Soccer (HT) | `proof_soccer/ingame_ht_accuracy.py` | 25830 matches, holdout 12915 | O/U-2.5 0.26367 | -- | **0.17606** (1X2 0.62639 -> 0.50182) | 0.0429 -> 0.01653 (platt) |
| Tennis (after set 1) | `proof_tennis/ingame_accuracy.py` | 8608 matches, eval 4304 | **0.21941** | 0.16235 | **0.15130** | 0.04343 -> 0.00631 (platt) |

Reading the table honestly:
- The task's headline figures are exact: NBA **0.209 -> 0.159**, MLB **0.241 -> 0.126**. Both
  replicate on the real corpus, not synthetic.
- COMBINED (Elo prior + realized score) is the sharpest in every sport, and beats score-only
  (the score alone, rating-blind) -- so the pregame intelligence still adds value mid-game.
  MLB combined beats score-only by only -0.00129: once the score is known, the rating prior is
  nearly redundant (the realized runs dominate). NBA combined beats score-only by a wider
  0.0138 -- a basketball lead is noisier per-possession, so the prior matters longer.
- ECE: NBA raw is meaningfully over-confident (0.059) and a leak-free temperature (T=1.445,
  shrinks confidence) fixes it to 0.012 WITHOUT worsening Brier. MLB raw is already calibrated
  (ECE 0.0085) so recal is an honest NULL (a success -- forcing a Platt fit would worsen it,
  exactly the W156 identity verdict in `predictor.predict_live`). Soccer/tennis recal helps.
- The per-quarter NBA scoring curve is a NULL: Q1-Q4 shares [0.2537, 0.2493, 0.2526, 0.2444]
  ~= uniform; curve-RMSE (14.449) does NOT beat flat (14.354). Recorded as a rejected lever, not
  a lift. (Contrast MLB, where the inning curve IS non-uniform and helps.)

**Significance / leak-free discipline baked in (proof-standards.md compliance):**
- Walk-forward Elo prior (`_walk_forward_elo`, `ingame_accuracy.py:166`) -- each game's prior
  uses only prior games.
- Recalibrator fit on TRAIN games only, applied to held-out (split-by-GAME parity so a game's
  Q1/Q2/Q3 never straddle train/eval -> no within-game leak; index-parity not chronological to
  avoid the early-season Elo warm-up confound, `:231-237`).
- RMSE + signed-bias for the total, NEVER MAE; probabilities Brier-graded. This is the
  MAE-vs-RMSE artifact internalized: tennis uses an analytic probability not a re-sim;
  `universal_winprob` uses projected-final not raw-live margin; `pbp_replay` grades RMSE+bias.

---

## 3. WHY IT IS MOSTLY NOT TRADEABLE (the structural wall)

This is the honest core. The calibration win is real; the $-edge is essentially zero,
structurally, for the team-level markets. Four reasons, each grounded:

1. **The book sees the same score.** A live sportsbook reprices the identical realized score in
   real time. Our score-anchor model and theirs converge on the same conditional. We are not
   ahead of the market on information it also has. Every repricer carries this in-code:
   `_honest_note` = "a live book also sees the score; forecaster quality, not a price edge"
   (`repricer.py:108`, mlb `:162`, tennis `:86`).
2. **The book sees MORE than the score.** Live books price substitutions, pace shifts, foul
   trouble, and injury news in real time. Our live feed is the ESPN keyless scoreboard
   (period/clock/score only) for the board, or box snapshots for the legacy NBA stack
   (deep-dive 11, Limitation 9) -- strictly LESS than the book. This is the structural reason
   the edge is calibration, not profit.
3. **Latency.** Even when our number is sharp, the book updates within seconds. A standing model
   edge cannot persist against a faster repricer on a liquid market.
4. **Thin replay corpus on the hardest validation.** The PBP-level replay (Finals G1-G3,
   `finals_replay_eval.parquet`, N=3) came out WORSE than a coin flip on pooled win-prob
   (deep-dive 11, Limitation 2). The team-level Brier wins above are robust (N=1313+ games); the
   fine-grained PBP win-prob is NOT yet proven. Sober reminder: even the calibration win is
   fragile on thin data.

Per cut-list-no-edge.md: the in-game team-level number is KEEP-as-calibrated-decision-support +
a CLV yardstick, but do NOT hunt a team-level $-edge there. It joins the sharp-mainline cut.

---

## 4. THE NARROW PLACES IT COULD BE TRADEABLE (each with data + proof needed)

These are the only pockets where a live mispricing could persist. All tier HYPOTHESIS until a
forward-CLV (or, for DFS, P-over-calibration + line-movement) artifact earns a promotion.

### 4.1 Thin / slow IN-PLAY markets on soft books (HYPOTHESIS, P2/P3)
The wall in section 3 assumes a fast, liquid book. It cracks where a book updates in-play lines
slowly or suspends/reopens with a stale number (soft books, niche leagues, deep correlated
in-play props). The edge is a LATENCY/STALE edge, not a model edge: detect that the soft book's
in-play number lags the realized score that our repricer already reflects.
- **Data needed:** a live in-play odds feed per book with timestamps (to measure lag vs the
  realized state); we currently have only the ESPN scoreboard state, no live in-play odds.
  `pm_trading/live_ingame.py` + `run_live.py` is the paper arm but reads state, not book odds.
- **Proof needed:** measure book-update LAG (seconds between score change and line move) per book
  per market; forward paper CLV-vs-close at the moment we would take vs the eventual close
  (`grade_paper.py`, CLV-gated). A standing positive CLV at meaningful N on a specific
  book/market = CLV-PROVEN. Expect this to be RARE, fragile, and limit-constrained (cf.
  cut-list CUT 6 on arbitrage); keep it as a flag, do not architect the money engine around it.
- **Honest prior:** most liquid in-play markets will return CLV ~= 0 (efficient). The success
  criterion is finding the FEW book/market cells where lag is real, and quarantining the rest.

### 4.2 IN-GAME PROP DISTRIBUTIONS conditioned on realized minutes/usage (HYPOTHESIS, P1 -- the highest-upside frontier)
This is the most credible frontier, and it inherits the P1 soft/DFS-prop pocket rather than the
efficient team-mainline. The key asymmetry, grounded in the prop engines:

- **The largest pregame prop error source is minute/usage projection, and in-game it becomes
  OBSERVED.** The soccer prop backtest feeds REALIZED minutes as `e_minutes` to isolate rate
  calibration (deep-dive 04, `props_eval.py` path, lines 141/227-230): "the live board carries
  an UNMEASURED additional error source: `player_minutes` minute projection ... the reported
  calibration is optimistic relative to what the live board actually prices." Pregame,
  `expected_minutes = start_prob*85 + (1-start_prob)*avg_sub_min` (`player_minutes.py:29`) is a
  PROJECTION carrying lineup/rotation/sub risk. **In-game, realized minutes and usage are
  KNOWN** -- which collapses exactly the variance the backtest had to assume away. A player at 28
  minutes with 22 touches in Q3 has a far tighter remaining-points distribution than any pregame
  projection. This is the same variance-collapse that makes team win-prob sharp, applied to the
  per-player distribution where the soft/DFS line is lazily priced.
- **Why upside > team markets** (deep-dive 11, section 7 ceiling): (a) realized minutes/usage
  massively reduce per-player variance; (b) in-play prop markets are thinner and slower than the
  moneyline (so the latency/stale crack in 4.1 is wider); (c) the routed-ensemble player-line
  MAE (1.01 vs 1.87 production) hints at attainable sharpness -- but is single-corpus and
  default-OFF (`CV_INGAME_SBS`), so NOT the served value and NOT yet proven.
- **Data needed:** a live minutes/usage feed (true PBP: substitutions, touches, shot attempts)
  -- the single largest lever and the binding constraint; box snapshots are a coarse proxy. Plus
  a multi-season leak-free player-box corpus for cross-corpus validation (N=3 PBP replay is the
  current bottleneck).
- **Proof needed:** extend the per-sport repricers to emit calibrated player-prop DISTRIBUTIONS
  (not point picks) conditioned on realized minutes/usage; validate leak-free on the linescore +
  box corpus with RMSE+bias (totals) and Brier/ECE (P-over), on >=2 independent corpora (a
  single backtest is a selection artifact). For DFS pick'em there is no two-way close -> prove
  via P(over)-vs-realized calibration + realized ROI at fixed payout + DFS-line MOVEMENT
  (edge-theory.md note). Promotion path: HYPOTHESIS -> CALIBRATION-PROVEN (OOS BSS>0 on the
  conditional prop) -> CLV-PROVEN (forward paper, gated). Never a claimed profit before CLV.
- **Honest caveats (binding):** (a) the book ALSO sees the realized minutes -- the edge is only
  in the SOFT/DFS line being slow to reprice the prop, not in us knowing the minutes; (b) the
  cut-list demoted stats apply (WC Cards/Assists/Goals BSS<=0; likely MLB Total-Bases/RBIs/Runs)
  -- concentrate on PROVEN stats (WC Saves, expected MLB Hits/Pitcher-Ks/Walks, NBA AST/REB);
  (c) too-tight distributions invent fat tails and absurd EVs -- use NB-where-overdispersed +
  conformal width, flag implausible |EV|.

### 4.3 Live prop CORRELATION inside one game (HYPOTHESIS, P5, lower priority)
Once mid-game minutes/usage are realized, the JOINT distribution of correlated in-game props
(a player's remaining PTS and the team total; two players' remaining usage) tightens more than
soft books re-price the legs independently. This is the P5 correlated-SGP pocket conditioned on
live state. Lower priority than 4.2 (needs 4.2's distribution layer first); same proof bar
(joint calibration on the FULL stat-pair surface, not just the dominant pair --
retro-full-surface-validation lesson).

---

## 5. WHAT TO DO (prioritized, honest)

1. **CUT** team-level in-game $-edge hunting. Keep the four-sport Brier scoreboard (section 2) as
   the calibration evidence; pin it into the evidence packet; stop looking for mainline profit
   there (it joins the sharp-mainline cut). This is reallocation, not defeatism.
2. **PUSH** the in-game PROP frontier (4.2) as the one place upside justifies effort -- but as a
   CALIBRATION product first. Build the conditional-prop distribution layer on REALIZED
   minutes/usage; validate leak-free, cross-corpus, RMSE+bias/Brier; never claim profit before
   forward CLV.
3. **Unblock the data** that caps everything: a live minutes/usage (true PBP) feed for NBA and a
   multi-season leak-free box corpus. Deep-dive 11 names this the single largest lever; the math
   is solved, the ceiling is data.
4. **Keep the in-play STALE-line detector (4.1) as a free flag**, not a money engine; measure
   book lag forward, quarantine the efficient cells.

**One-line summary of the whole file:** the in-game layer is the project's cleanest measured
calibration win (NBA 0.209->0.159, MLB 0.241->0.126, leak-free, all four sports) and almost
entirely UN-tradeable on team markets because the book sees the same score -- the only real
frontier is in-game PROP distributions conditioned on realized minutes/usage, where the soft/DFS
line is slow, and even that is a calibration play gated on forward CLV, never a claimed edge.
