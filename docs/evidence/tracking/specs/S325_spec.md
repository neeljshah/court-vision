GAP S325 | sport soccer | worktree aX | log cx_s325_soccer_remaining_goal

**MODEL ROW (S register; astra 2026-09-08 per-sport row 6, soccer).** `src/`, `kernel/`, `api/` and `intel/`
are READ and IMPORT only. Build in `scripts/platformkit/ingame/` and `domains/soccer/`. NEVER write
`data/registry/`, never flip a flag, never claim an edge (calibration language only; never the word AHEAD
versus the market -- the pass label is "bar C met"), never edit a landed memo,
`docs/evidence/HARNESS_GAPS_2026-09-03.md` or `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai` for every python call; print the interpreter
line). Inputs, read in row-group batches: `data/cache/ingame/soccer_states__{eng1,esp1,ger1,ita1}.parquet`
(~7 k rows each; columns sport, game_id, asof_idx, state_diff, frac_elapsed, p0, outcome, minute, home_goals,
away_goals, date), `soccer_states__combo_eng_ger.parquet`, `soccer_states__combo_esp_ita.parquet`,
`soccer_states__wc_2026.parquet`, the shot / xG states `soccer_shotxgstates__<league>.parquet` (game_id,
asof_idx, xgloc_diff, home_xgloc, away_xgloc, n_shots_loc) and `soccer_cardstates__*.parquet`, plus
`data/cache/inplay_odds/soccer_price_series.parquet` and `soccer_intl_price_series.parquet` (totals-only
odds per S290 / the S323 census: report what joins). S320's audit pattern (availability, status, polarity,
duplicates, prefix replay on sealed states) is applied to THIS corpus inside the row before scoring.

**WHY THIS ROW EXISTS.** Four domestic leagues plus a World Cup corpus carry per-state score, minute,
prefix xG and a pre-game probability `p0`, and none has been scored under the S309 discipline. Astra row 6:
a prior-anchored remaining-goal intensity model conditional on score, elapsed time, red-card differential
and decayed prefix xG. The target here is the home-win / draw / away-win outcome carried by the state tables
(`outcome`), NOT a totals line (no games.parquet or quoted lines exist -- state it; a totals estimand is a
later row if lines can be joined).

**PREMISE (step 0, BINDING before-condition):** print per league: n games, n states, n with `p0`, the
producer of `p0` (`file:line`; pre-start market-implied, rating, or first tick -- never substitute a rating
for M0), the outcome class set (2-way or 3-way), xG coverage (share of states with a joined xG row), n games
joinable to a price series. **If `p0` is a rating for every league and no market-implied pre-start
probability can be joined for >= 300 games in >= 2 leagues, the premise is FALSE for bar C: STOP, write
the memo with the counts, commit, report INSUFFICIENT.**

METHOD:
  1. **CORPORA.** Each league (eng1, esp1, ger1, ita1) is a corpus; the combo and wc_2026 stores are reported
     as sensitivity corpora only if their games are disjoint from the league corpora (check by game_id).
     Landmarks: minutes 15, 30, 45, 60, 75, 85 (and 90 when a state exists); equal-game weights.
  2. **MODEL (`s325_soccer_goal_intensity.py`, <= 250 lines).** Remaining-goal intensities per side
     lambda_h, lambda_a = exp(a_side + b logit-anchor from M0 + c goal-difference state + d elapsed share
     + e decayed prefix xG difference + f red-card differential when the card store joins); the outcome
     probability is the Poisson (or bivariate-Poisson with a shared term, sealed) distribution of remaining
     goals added to the current score, giving P(home) / P(draw) / P(away) (or the 2-way target if the store
     is 2-way -- say which). Fit train-only inside chronological walk-forward folds with whole-game grouping
     and a 24 h embargo. Baselines on IDENTICAL states: M0 (p0, labelled by provenance); ML if joinable; N =
     the strongest train-selected null (recalibrated M0 + score/time only). Ablation: without xG.
  3. **SCORING + BAR C (sealed):** multiclass Brier (frozen class order) / ECE per class / log score vs M0,
     ML, N with paired game-cluster bootstrap 95 pct CIs (2,000); bar C = Brier improvement vs N >= 0.002
     with CI lower > 0 in EACH corpus (>= 2 leagues); vs M0 lower > 0; vs ML noninferiority where ML exists;
     log-loss and ECE guards; shuffle z >= 3; landmark and xG ablations; family correction.
  4. **LEAK CONTROLS.** xG rows must carry availability no later than the state (retrospectively revised xG
     is the named false positive: compare the prefix xG at asof_idx against any later revision if the store
     carries revision fields; else state it cannot be checked); prefix replay on 100 sealed states; fixed
     landmark cohorts.
  5. **TESTS.** A hand-pinned 30-state construct with known p0 and outcomes: the intensity fit reproduces a
     planted goal-difference effect; the Poisson outcome mapping matches a closed-form case; the comparer
     returns pinned Brier deltas; the ordering audit catches a planted post-goal state.
  6. CHANGE NOTHING ELSE; no production flag; a PROPOSED integration snippet only if bar C is met.

**HONEST LIMITATIONS to state, not discover:** `p0` provenance bounds every claim; league corpora are one
season each unless the store spans more (report); no totals line means no totals claim; international and
domestic contexts validate separately; a pass is a calibration result, never a market claim.

ACCEPTANCE RULE:
  metric        = premise table per league; the audit table; the per-corpus scoring table with CIs and n;
                  the bar C decision per corpus; ablations; tests
  before        = no soccer in-game model scored under the S309 discipline; p0 provenance undocumented
  bar           = audit 0 violations (else VIOLATION, scoring blocked); bar C applied exactly as sealed per
                  corpus; every cell has n and a CI; all tests pass; 0 landed files edited
  n             = >= 300 games per corpus; >= 2 corpora; 100 sealed audit states
  eye check     = NONE. Say that.
  must not move = every landed number; `src/`; `data/`; the registers/ledgers; every flag default
  verdict       = **BAR C MET** / **BEHIND** / **NULL** / **INSUFFICIENT** / **VIOLATION**; **PARTIAL** only
                  if an arm could not run.
EVIDENCE: `docs/evidence/harness/S325_soccer_remaining_goal_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S325 | <finding with n> | <VERDICT>`) + per-corpus CSVs and the audit CSV
under `docs/evidence/harness/S325_soccer_remaining_goal_2026-09-08/` (each <= 5 MB; integer cells zero-padded).
TEST: `tests/platformkit/test_s325_soccer_goal_intensity.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: landmarks, folds, embargo, the
intensity form, bar C, audit strata, resamples), the model, the comparer, the audit, the tests and the memo
skeleton, and exits `PREPARED FOR FINISHER` with the exact commands; it must NOT score the stores itself
(Q1). A missing `data/registry` in the worktree is expected; absent stores are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
