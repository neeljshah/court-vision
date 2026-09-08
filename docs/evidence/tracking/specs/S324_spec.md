GAP S324 | sport mlb | worktree a17 | log cx_s324_mlb_baseout_count

**MODEL ROW (S register; astra 2026-09-08 per-sport row 3, MLB).** `src/`, `kernel/`, `api/` and `intel/` are
READ and IMPORT only. Build in `scripts/platformkit/ingame/` and `domains/mlb/`. NEVER write `data/registry/`,
never flip a flag, never claim an edge (calibration language only; never the word AHEAD versus the market --
the pass label is "bar C met"), never edit a landed memo, `docs/evidence/HARNESS_GAPS_2026-09-03.md` or
`docs/evidence/RESULTS_LEDGER_SYSTEM.md` (the lander appends; put the proposed ledger line in the memo).

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line; use the conda
interpreter for every python call -- the system python was RAM-killed today loading a 13.5 M-row store).
Inputs, read in row-group batches (never a whole-store load over 300 MB):
`data/cache/ingame/mlb_pitch_states__{2022,2023,2024,2025,2026}.parquet` (~66-70 k rows each; columns sport,
game_id like `2024-03-20-SDG-LAD-1`, asof_idx, state_diff, frac_elapsed, p0, outcome, home_team, away_team,
date, season, half_inning_label, count_balls, count_strikes, runners, outs, atbat_pitch_number, pitch_type,
pitch_velocity, pitch_loc_x, pitch_loc_y, sp_pitch_count_prior, velo_decline_vs_early, base_run_value,
leverage_bucket), `data/cache/ingame/mlb_states__{2021..2024}.parquet` (half-inning grain; base_out_known),
`data/cache/ingame/mlb_atbat_states__{2022,2023}.parquet`, and `data/cache/inplay_odds/mlb_price_series.parquet`
(13,473,591 rows; kalshi; ticker_or_slug, event_key, market_type, side, ts, prob, traded, close_time,
result_where_known) for the live market ML where the seasons overlap. S320's audit pattern (availability,
status, polarity, duplicates, prefix replay) must be applied to THIS corpus before scoring (a 100-state sealed
audit inside this row; a VIOLATION blocks scoring and is reported).

**WHY THIS ROW EXISTS.** No MLB in-game model has been scored under the S309 discipline. The per-pitch state
archive already carries inning/half, score differential, base occupancy, outs, count, pitch number and a
pre-game probability `p0`, so the astra row 3 model (M0 offset + base-out/count conditioning, shrunk pitcher
role / pitch count) can be scored on >= 4 seasons WITHOUT new acquisition, if `p0`'s provenance qualifies.

**PREMISE (step 0, BINDING before-condition):** print per season: n games, n states, n with `p0` non-null,
the producer of `p0` (`file:line` of the writer under `scripts/platformkit/` or `domains/mlb/`; state
whether it is a pre-start market-implied probability, a rating (Elo), or an in-play first tick -- NEVER
substitute a rating for M0), n games with live ML quotes joinable from the price series (by date + teams
parsed from `ticker_or_slug`), and the share of states with `base_out_known`. **If `p0` is a rating and no
market-implied pre-start probability can be joined for >= 300 games in >= 2 seasons, the premise is FALSE
for bar C: STOP, write the memo with the counts, commit, report INSUFFICIENT.**

METHOD:
  1. **CORPORA.** Each season is a corpus (>= 2 required; report all available). Estimand: final home-win
     probability at the first eligible state after a completed pitch (per-pitch grain), scored on frozen
     landmarks (end of each half-inning through the 9th plus each extra half-inning), equal-game weights.
  2. **MODEL (`s324_mlb_state_model.py`, <= 250 lines).** logit(p) = logit(M0) + f(state_diff, inning /
     frac_elapsed, half) + g(runners, outs) + h(count) + shrunk pitcher terms (sp_pitch_count_prior,
     velo_decline_vs_early) using prior games only; fit train-only inside chronological walk-forward folds
     with whole-game grouping and a 24 h embargo. Baselines on IDENTICAL states: M0; ML where joinable;
     N = strongest train-selected null (recalibrated ML, else recalibrated M0 + score/inning only).
     Ablation arm: score/inning-only.
  3. **SCORING + BAR C (sealed):** Brier / ECE (10 frozen bins) / negative log score vs M0, ML, N with paired
     game-cluster bootstrap 95 pct CIs (2,000); bar C = Brier improvement vs N >= 0.002 with CI lower > 0
     in EACH corpus; vs M0 lower > 0; vs ML noninferiority lower >= -0.001 where ML exists; log-loss and
     ECE guards; shuffle z >= 3; landmark ablation; family correction.
  4. **LEAK CONTROLS.** The eventual pitch result must never be matched to a pre-result state (asof_idx
     ordering audit); received-time joins for ML; prefix replay on 100 sealed states; pitch-delay stress
     (+1 pitch). Report every check with n.
  5. **TESTS.** A hand-pinned 40-state construct with known M0 and outcomes: the fit reproduces a planted
     base-out effect; the comparer returns pinned Brier deltas; the ordering audit catches a planted
     post-result state.
  6. CHANGE NOTHING ELSE; no production flag; a PROPOSED integration snippet only if bar C is met.

**HONEST LIMITATIONS to state, not discover:** `p0` provenance bounds every claim; ML coverage may be a
subset of seasons (report it); a season is one corpus; MLB tie/termination rules differ from KBO/NPB (out of
scope); a pass is a calibration result, never a market claim.

ACCEPTANCE RULE:
  metric        = premise table (per season, p0 provenance, ML coverage); the audit table (100 states); the
                  per-corpus scoring table with CIs and n; the bar C decision per corpus; tests
  before        = no MLB in-game model scored under the S309 discipline; p0 provenance undocumented
  bar           = the audit shows 0 violations (else VIOLATION, reported, scoring blocked); the bar C
                  decision is applied exactly as sealed per corpus; every cell has n and a CI; all tests
                  pass; 0 landed files edited
  n             = >= 300 games per corpus; >= 2 corpora; 100 sealed audit states
  eye check     = NONE. Say that.
  must not move = every landed number; `src/`; `data/`; the registers/ledgers; every flag default
  verdict       = **BAR C MET** / **BEHIND** / **NULL** / **INSUFFICIENT** / **VIOLATION**; **PARTIAL** only
                  if an arm could not run.
EVIDENCE: `docs/evidence/harness/S324_mlb_baseout_count_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S324 | <finding with n> | <VERDICT>`) + per-corpus CSVs and the audit CSV
under `docs/evidence/harness/S324_mlb_baseout_count_2026-09-08/` (each <= 5 MB; integer cells zero-padded).
TEST: `tests/platformkit/test_s324_mlb_state_model.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: landmarks, folds, embargo, model
terms, bar C, the audit strata, the resample count), the model, the comparer, the audit, the tests and
the memo skeleton, and exits `PREPARED FOR FINISHER` with the exact commands; it must NOT score the stores
itself (Q1). A missing `data/registry` in the worktree is expected; absent stores are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
