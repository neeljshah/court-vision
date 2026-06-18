# INEFFICIENCY: LIVE / IN-GAME LINE LAG (P2) -- detection recipe + proof

_Part of the edge-intelligence corpus (_framework/inefficiencies/). The DEEP, actionable layer
for ONE pocket: a soft/slow book's in-play line lagging the realized game state that our repricer
already reflects. Grounds: _live/in-game-edge.md (authoritative on the calibration win and the
structural wall), edge-theory.md (P2), proof-standards.md, cut-list-no-edge.md (CUT 6 fragile
execution edges), and the live code `scripts/platformkit/live_repricer.py` +
`domains/<sport>/repricer.py` + `odds_provider/espn.py`. Binding: no $-edge claimed; ASCII only._

---

## 1. THE EXACT MECHANISM (and where it does NOT exist)

When the score changes, the fair price changes. A live sportsbook reprices within seconds. The
crack is purely a LATENCY/STALE edge: a soft or slow book updates its in-play line AFTER the
realized state has already moved -- and our repricer reflects that state immediately. The edge is
NOT "we model the live game better"; it is "we see the score move and the book hasn't re-priced
yet."

THE STRUCTURAL WALL (the honest core, from _live/in-game-edge.md section 3): on a fast liquid
book this pocket is essentially empty, for three grounded reasons:
1. The book sees the SAME score -- its conditional and ours converge (every repricer carries
   `_honest_note`: "a live book also sees the score; forecaster quality, not a price edge" --
   `repricer.py:108`, mlb `:162`, tennis `:86`).
2. The book sees MORE than the score -- substitutions, foul trouble, pace shifts, injury news in
   real time. Our keyless feed (ESPN scoreboard: period/clock/score only) is strictly LESS.
3. Latency -- even a sharp number is matched within seconds on a liquid market.

So the team-level in-game number is a CALIBRATION win (the cleanest in the project) but a
$-ceiling ~0; it joins the sharp-mainline CUT. This pocket is ONLY non-empty in the NARROW cells
where a book updates in-play lines SLOWLY or suspends/reopens stale (soft books, niche leagues,
deep correlated in-play props). The detection recipe is therefore a LAG MEASUREMENT, not a model
contest.

---

## 2. IN-DATA DETECTION RECIPE (exactly what to compute)

The repricer side is built and uniform; the missing half is a TIMESTAMPED live in-play odds feed.
The recipe has two computations: (a) our conditional number per state, (b) the book's update lag.

### 2.1 Our conditional number (built, sport-blind)
- `GameState(sport, elapsed_minutes, home_score, away_score, pregame_params, extra)` ->
  `get_repricer(sport).reprice(state)` (`live_repricer.py:29`, factory `:236`). Consumers call
  `domains/<sport>/predictor.py::predict_live(...)`, which anchors the repricer's pregame win-prob
  to the SAME Elo/MOV the pregame `predict()` reports (cohesion at elapsed=0) then applies a
  fitted recalibrator. Unwired sport -> graceful `_SportStub` (`status="not_wired"`).
- Topology per sport: NBA = Gaussian score-anchor remaining-points
  (`basketball_nba/repricer.py:43`; `margin_mean=(h0-a0)+(mu_h-mu_a)*rem_frac` `:57`,
  `margin_sd=margin_sigma*sqrt(rem_frac)` `:59` Brownian, `win=Phi(mean/sd)` `:62`; defaults
  sigma 13.5 / total 18.0 `:29-30`). Soccer/MLB = remaining-lambda score MATRIX shifted by the
  board (MLB uses an EMPIRICAL per-inning run curve `_INNING_SHARES` `:36`, not flat 1/9, with a
  residual `_EXTRA_INNING_FRAC=1/9` so a tie stays live). Tennis = analytic race-to-N-sets
  conditional (`tennis/repricer.py:31`, deliberately NOT a re-sim so it is Brier-graded -- dodges
  the MAE-vs-RMSE artifact).
- DETECTION STATISTIC at each tick: `our_fair_prob(state)` from the repricer, devigged-equivalent
  (it is already a fair probability, no vig). This is the moving target the book is chasing.

### 2.2 The book's in-play line + its LAG (the missing feed)
- The only keyless live two-way is ESPN's republished moneyline, in-game, from ONE book
  (`espn.py:30/49`, `summary?event=<id>` -> `pickcenter[].moneyLine`). Poll the scoreboard fast
  (the 60s TTL `http_cache` is too coarse for lag work -- bypass cache or shorten TTL for live).
- DETECTION (the core computation): build two synchronized time series per game --
  (i) realized SCORE-CHANGE events (from the scoreboard state stream), timestamped;
  (ii) book LINE-CHANGE events (from `pickcenter` moneyline), timestamped.
  Compute `lag_seconds = ts(book_line_move) - ts(score_change_that_should_cause_it)` per event.
  A book that reprices in <~2-3s is efficient (no pocket). A book that lags tens of seconds to
  minutes on a market we can take is a candidate cell.
- The TAKEABLE-EDGE statistic: at the moment a score change has occurred but the book line has
  NOT yet moved, compare `our_fair_prob(new_state)` to the book's STALE devigged implied prob.
  Flag `stale_edge = our_fair_prob - book_stale_implied` while `lag` is open. This is the only
  honest in-play candidate signal.
- Per-book per-market CELL MAP: aggregate `lag_seconds` distribution by (book, sport, market).
  Most cells will be ~0 lag (efficient) -- the SUCCESS is finding the few cells with real,
  repeatable lag and quarantining the rest (in-game-edge.md 4.1).

### 2.3 The higher-upside variant: in-game PROP distributions (P1, not team-level)
The team-level lag is thin; the real frontier (in-game-edge.md 4.2) is per-player PROP
distributions conditioned on REALIZED minutes/usage. Pregame, the largest prop error source is
minute projection (`player_minutes.py:29`, `expected_minutes = start_prob*85 + ...` -- a
projection carrying rotation risk). IN-GAME those minutes are OBSERVED -> the variance the
backtest had to assume away COLLAPSES. DETECTION: condition the per-player remaining-stat
distribution on realized minutes/usage at the current state, price P(over remaining-line) against
the (slower) in-play DFS/soft prop line. This inherits the P1 soft-prop pocket, not the efficient
team mainline -- which is why its lag crack (2.2) is WIDER (prop in-play markets are thinner and
slower than the moneyline).

---

## 3. PROOF METHOD (leak-free, which metric, and CLV)

Two distinct proof tracks. Do not conflate them.

### 3.1 The CALIBRATION win (already partly proven -- this is NOT the $ claim)
The conditioning-on-score Brier improvement is measured, leak-free, on the real corpus
(in-game-edge.md section 2, re-run 2026-06-18):
- NBA `proof_nba/ingame_accuracy.py`: 1313 games / 3939 q-checkpoints, pregame-Elo Brier 0.20888
  -> combined (prior+score) 0.15859; ECE 0.05921 -> 0.01211 (leak-free T=1.445).
- MLB `proof_mlb/ingame_accuracy.py`: 23279 games, 0.24096 -> 0.12640; ECE already calibrated
  (0.0085, recal is an honest NULL).
- Soccer (HT) 1X2 0.62639 -> 0.50182; Tennis (after set 1) 0.21941 -> 0.15130.
Leak-free discipline: walk-forward Elo prior (`_walk_forward_elo`, `ingame_accuracy.py:166`);
recalibrator fit on TRAIN games only, split BY GAME so a game's Q1/Q2/Q3 never straddle train/eval
(`:231-237`); RMSE+signed-bias for totals NEVER MAE; probabilities Brier-graded. TIER:
CALIBRATION-PROVEN (team win-prob, single-corpus for the blend). This proves SHARPNESS, NOT
profit -- the book sees the same score. Do NOT promote it to a $ claim.

### 3.2 The TRADEABLE proof (the lag pocket -- HYPOTHESIS, needs a live-odds feed)
- Data needed (the binding gap): a TIMESTAMPED live in-play odds feed per book. We currently have
  only the ESPN scoreboard STATE; `pm_trading/live_ingame.py` + `run_live.py` is the paper arm but
  reads state, not book odds. Until a timestamped book-odds stream exists, the lag in 2.2 is
  unmeasured.
- Metric: per (book, market), the `lag_seconds` distribution AND forward paper CLV-vs-close at the
  moment we would take vs the eventual settle (`grade_paper.py`, CLV-gated; for team markets CLV is
  defined because there is a two-way close). A standing positive CLV at meaningful N on a SPECIFIC
  book/market cell = CLV-PROVEN for that cell only.
- Discipline: this is an EXECUTION edge (cut-list CUT 6 frame) -- expect it RARE, fragile,
  limit-constrained, and in-play suspension means the stale number often is not actually takeable.
  Keep it as a free FLAG, do not architect the money engine around it. Quarantine efficient cells.
- For the in-game PROP variant (2.3): cross-corpus RMSE+bias (totals) and Brier/ECE (P-over) on a
  leak-free linescore+box corpus, >=2 independent corpora (the N=3 PBP replay is the current
  bottleneck and came out WORSE than a coin flip pooled -- in-game-edge.md section 3.4; thin-data
  reminder). For DFS in-play props, the DFS proof substitute applies (no two-way close).

---

## 4. REALISTIC MAGNITUDE (honest)

- CALIBRATION (team win-prob): LARGE and real (NBA 0.209->0.159, MLB 0.241->0.126) -- but this is
  forecaster quality, NOT a tradeable magnitude.
- TRADEABLE lag (team mainline on a liquid book): ~0. The honest prior is that most liquid in-play
  cells return CLV~0 (efficient). The realistic non-zero magnitude lives ONLY in a few
  soft-book/niche/suspend-reopen cells and in thin in-play PROP markets, and even there it is
  fragile, transient, and limit-constrained. The success criterion is FINDING those few cells, not
  a slate-wide number.

---

## 5. THE HONEST CAVEATS (why this may NOT be real)

- **The book sees the same score** (the whole pocket is gone on a fast book) -- baked into every
  repricer's `_honest_note`. We are not ahead on information the book also has.
- **The book sees MORE** (subs/pace/foul-trouble/injury) than our period/clock/score feed -- so
  on net the book is often AHEAD of us, not behind. The stale window must be genuinely caused by
  book latency, not by the book pricing information we lack.
- **Suspension makes the stale number un-takeable.** Books suspend in-play around score events;
  the lagged-but-takeable window is narrower than the raw lag suggests.
- **No timestamped book-odds feed exists yet** -- 2.2 is currently UNMEASURED; everything tradeable
  here is HYPOTHESIS until that feed is built and the lag distribution is computed.
- **Thin replay corpus on the hardest validation** -- PBP-level win-prob (N=3 Finals replay) was
  worse than a coin flip pooled (in-game-edge.md 3.4). The team-level Brier wins are robust
  (N=1313+); the fine-grained number is NOT yet proven.
- **MAE-vs-RMSE artifact trap.** A shrink-toward-current-score model wins on MAE as a median-shift
  artifact, not real edge (project keystone). Score probabilities with Brier and totals with
  RMSE+bias, never MAE.

---

## 6. TIER + WHAT WOULD PROMOTE IT

- TIER: team-level calibration = CALIBRATION-PROVEN (single-corpus blend OOS still PENDING the
  real linescore-corpus run, NBA inefficiency-catalog N4); tradeable lag = HYPOTHESIS,
  data-blocked on a timestamped live-odds feed; in-game prop frontier = HYPOTHESIS, the
  highest-upside but blocked on a live minutes/usage (true PBP) feed.
- TO CALIBRATION-PROVEN (blend): run `ingame_blend_eval` on the REAL 1313-game `linescores.parquet`
  (end the SYNTHETIC PENDING flag), fit weight surface on season A, eval on B (+B->A),
  per-quarter Brier/ECE + game-id-clustered Diebold-Mariano vs pregame-only.
- TO CLV-PROVEN (lag cell): build the timestamped live-odds feed, compute the per-(book,market)
  lag map, accrue forward paper CLV on the lagging cells only, quarantine the rest.

ONE-LINE: conditioning on the realized score is the project's cleanest CALIBRATION win and almost
entirely UN-tradeable on team markets (the book sees the same score and more), so the only real
in-play candidates are (a) measured per-(book,market) LATENCY on slow/soft cells and (b) in-game
PROP distributions conditioned on realized minutes/usage where the soft line is slow -- both
HYPOTHESIS, both data-blocked on a timestamped live feed, both proven by lag + forward CLV (team)
or the DFS substitute (props), never by the calibration Brier alone.
