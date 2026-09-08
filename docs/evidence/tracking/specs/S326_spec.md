GAP S326 | sport tennis | worktree a11 | log cx_s326_tennis_serve_set_recursion

**MODEL ROW (S register; astra 2026-09-08 per-sport row 7, tennis).** `src/`, `kernel/`, `api/` and `intel/`
are READ and IMPORT only. Build in `scripts/platformkit/ingame/` and `domains/tennis/`. NEVER write
`data/registry/`, never flip a flag, never claim an edge (calibration language only; never the word AHEAD
versus the market -- the pass label is "bar C met"), never edit a landed memo,
`docs/evidence/HARNESS_GAPS_2026-09-03.md` or `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai` for every python call; print the interpreter
line). Inputs, read in row-group batches: `data/cache/ingame/tennis_states__{atp,wta}.parquet` (40,516 ATP
rows; columns sport, game_id like `20150104-atp-2015-339-105357-105733-1`, asof_idx, state_diff,
frac_elapsed, p0, outcome, set_score, game_score, surface), `tennis_gamestate__{atp,wta}.parquet` (48,512 ATP
rows; games_diff_in_set, sets_diff, break_pts_converted_diff, serve_holds_streak, date),
`tennis_setdetail__{atp,wta}.parquet`, and `data/cache/inplay_odds/tennis_price_series.parquet` (totals-only
per S290 / the S323 census; report what joins). S320's audit pattern (availability, status, polarity,
duplicates, prefix replay on sealed states) is applied to THIS corpus inside the row before scoring.

**WHY THIS ROW EXISTS.** ATP and WTA game-level state archives (set score, game score, break points, hold
streaks, surface, a pre-match probability `p0`) exist locally and have never been scored under the S309
discipline. Astra row 7: a scoring recursion over server, point / game / set state with pre-match shrunk
serve strengths, represented through state rather than retrospective coefficients. The target here is the
match-winner outcome carried by the state tables (`outcome`), NOT a total-games line (no quoted lines join
-- state it).

**PREMISE (step 0, BINDING before-condition):** print per tour: n matches, n states, n with `p0`, the
producer of `p0` (`file:line`; pre-match market-implied, rating, or first tick -- never substitute a
rating for M0), the date span, n distinct seasons, whether the state carries the server (if not, the
recursion runs at GAME grain with the server inferred from the alternation rule -- say so), retirement
handling in the store, n matches joinable to the price series. **If `p0` is a rating for both tours and no
market-implied pre-match probability can be joined for >= 500 matches in >= 2 seasons, the premise is
FALSE for bar C: STOP, write the memo with the counts, commit, report INSUFFICIENT.**

METHOD:
  1. **CORPORA.** Each tour x season is a corpus candidate; seal >= 2 corpora per tour with >= 500 matches
     each (chronological). Landmarks: end of each set and the first game state at games 3, 6 and 9 of each
     set where present; equal-match weights.
  2. **MODEL (`s326_tennis_recursion.py`, <= 250 lines).** Pre-match serve-hold strengths per player shrunk
     from PRIOR matches only (prefix rates), anchored to M0 through a logit offset; the match-win probability
     from the standard game -> set -> match recursion given set_score, game_score, the server (or the
     alternation rule), best-of format inferred from the tour / event, and tiebreak rules (sealed); surface
     as a shrunk adjustment. Fit the anchoring and shrinkage train-only inside chronological walk-forward
     folds with whole-match grouping and a 24 h embargo. Baselines on IDENTICAL states: M0 (p0, labelled by
     provenance); ML if joinable; N = the strongest train-selected null (recalibrated M0 + set/game
     difference only). Ablation: without the serve strengths (pure recursion at 0.5 hold).
  3. **SCORING + BAR C (sealed):** Brier / ECE (10 frozen bins) / log score vs M0, ML, N with paired
     match-cluster bootstrap 95 pct CIs (2,000); bar C = Brier improvement vs N >= 0.002 with CI lower > 0
     in EACH corpus; vs M0 lower > 0; vs ML noninferiority where ML exists; log-loss and ECE guards; shuffle
     z >= 3; landmark and serve-strength ablations; family correction.
  4. **LEAK CONTROLS.** Serve rates from prefix matches only (a final-match serve rate is the named false
     positive); retirements handled by the sealed rule (exclude from scoring after the retirement state;
     report n); prefix replay on 100 sealed states; settlement fixtures for walkovers.
  5. **TESTS.** A hand-pinned construct: the recursion reproduces closed-form match-win probabilities for
     symmetric players at 0.5 hold and for a planted 0.7 / 0.6 hold pair; the comparer returns pinned Brier
     deltas; the ordering audit catches a planted post-point state; a retirement state is excluded.
  6. CHANGE NOTHING ELSE; no production flag; a PROPOSED integration snippet only if bar C is met.

**HONEST LIMITATIONS to state, not discover:** `p0` provenance bounds every claim; game-grain states
without the server lose point-level information (stated); no total-games line means no totals claim;
price-only calibration cannot validate the state model; a pass is a calibration result, never a market claim.

ACCEPTANCE RULE:
  metric        = premise table per tour; the audit table; the per-corpus scoring table with CIs and n;
                  the bar C decision per corpus; ablations; tests
  before        = no tennis in-game model scored under the S309 discipline; p0 provenance undocumented
  bar           = audit 0 violations (else VIOLATION, scoring blocked); bar C applied exactly as sealed per
                  corpus; every cell has n and a CI; all tests pass; 0 landed files edited
  n             = >= 500 matches per corpus; >= 2 corpora per tour; 100 sealed audit states
  eye check     = NONE. Say that.
  must not move = every landed number; `src/`; `data/`; the registers/ledgers; every flag default
  verdict       = **BAR C MET** / **BEHIND** / **NULL** / **INSUFFICIENT** / **VIOLATION**; **PARTIAL** only
                  if an arm could not run.
EVIDENCE: `docs/evidence/harness/S326_tennis_serve_set_recursion_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S326 | <finding with n> | <VERDICT>`) + per-corpus CSVs and the audit CSV
under `docs/evidence/harness/S326_tennis_serve_set_recursion_2026-09-08/` (each <= 5 MB; integer cells
zero-padded).
TEST: `tests/platformkit/test_s326_tennis_recursion.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: corpora, landmarks, folds, embargo, the
recursion rules, bar C, audit strata, resamples), the model, the comparer, the audit, the tests and the memo
skeleton, and exits `PREPARED FOR FINISHER` with the exact commands; it must NOT score the stores itself
(Q1). A missing `data/registry` in the worktree is expected; absent stores are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
