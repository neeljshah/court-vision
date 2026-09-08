GAP S321 | sport nba | worktree a5 | log cx_s321_nba_prior_score_clock

**MODEL ROW (S register; astra 2026-09-08 per-sport row 1, the highest-ranked).** `src/`, `kernel/`, `api/`
and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/ingame/`. NEVER write `data/registry/`,
never flip a flag, never claim an edge (calibration language only; never the word AHEAD versus the market --
the pass label is "bar C met"), never edit a landed memo, `docs/evidence/HARNESS_GAPS_2026-09-03.md` or
`docs/evidence/RESULTS_LEDGER_SYSTEM.md` (the lander appends; put the proposed ledger line in the memo).

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Input:
`data/cache/inplay_odds/nba_checkpoints_full.parquet` (465,249 ticks / 1,593 games; read columns). The S309
canonical loss module (active-status mask, s86 denominator), the S310 / S309 recalibrated null, and the
`scripts/platformkit/eval_gate/walkforward.py` route with embargo. S320 must be CLEAN on master before this
row's finisher scores (if not landed, the finisher reports BLOCKED-ON S320 and commits the prepared harness).

**WHY THIS ROW EXISTS.** Every landed in-game row conditioned on the market probability or searched the tail
(S272/S277/S289/S291 BEHIND or null; S310 CLOSED AT LIMIT; S307/S308 no sharpness). None scored the simplest
transparent state model: the pregame prior as an offset plus a low-dimensional monotone score-differential x
remaining-time surface. If that model cannot meet bar C against the recalibrated null, no richer in-game
model will, and the program's model lane changes course.

**PREMISE (step 0, BINDING before-condition):** audit M0: print, per season, n games with a valid pre-start
market-implied home-win probability (the M0 column and its time), n games with live quotes (ML), n active
ticks after the S309 mask, and the frozen landmark coverage. **If fewer than 400 games per corpus carry a
valid M0 in >= 2 seasons, the premise is FALSE for bar C: STOP, write the memo with the counts, commit,
report INSUFFICIENT.**

METHOD:
  1. **CORPORA.** >= 2 seasons as independent corpora (chronological; a season is a corpus). Frozen landmarks
     per game (remaining 2400, 1800, 1200, 600, 300, 120, 60 s and each overtime start), one canonical
     active tick per landmark, equal-game weights.
  2. **MODEL (`s321_prior_state_model.py`, <= 250 lines).** logit(p) = logit(M0) + f(margin, remaining_s) +
     g(OT), f a monotone-in-margin spline with <= 12 knots (sealed), fit train-only inside chronological
     walk-forward folds with whole-game grouping and a 24 h embargo (S299 design; symmetric CPCV as a
     sensitivity only). Baselines on IDENTICAL states: M0; ML (the live quote at the tick); N = the strongest
     train-selected null (recalibrated ML, else recalibrated M0 + basic state per S309/S310).
  3. **SCORING (prereg it).** Brier, ECE (10 frozen bins), negative log score, each vs M0, ML and N with
     paired game-cluster bootstrap 95 pct CIs (2,000 resamples); game-label shuffle z >= 3; landmark
     ablation; family correction for the number of scored comparisons; reliability bins with game counts
     (bins with < 50 games descriptive only).
  4. **BAR C (sealed):** Brier improvement vs N >= 0.002 with CI lower > 0 in EACH corpus; vs M0 lower > 0;
     vs ML noninferiority (lower >= -0.001); guards: log-loss lower >= -0.002 and ECE worsening upper <=
     0.010 vs N and vs the markets. All folds improve. Anything less is BEHIND, NULL or INSUFFICIENT.
  5. **TESTS.** A hand-pinned 40-tick construct with known M0 and outcomes: the fit reproduces a planted
     monotone surface; the comparer returns the pinned Brier deltas; the embargo rejects a planted same-game
     row (S302 pattern).
  6. CHANGE NOTHING ELSE. No production flag, no `src/` edit; a PROPOSED integration snippet only if bar C is
     met.

**HONEST LIMITATIONS to state, not discover:** a season is one corpus (venue/tick variety is not
replication); ML may be missing at some landmarks (report coverage); M0 quality bounds the model; a pass is a
calibration result, never a market claim.

ACCEPTANCE RULE:
  metric        = premise counts; the per-corpus table (Brier / ECE / log score vs M0, ML, N with CIs and n);
                  reliability bins; shuffle z; ablation; the bar C decision per corpus
  before        = no transparent prior + score/clock model has been scored under the S309 denominator
  bar           = the bar C decision is applied exactly as sealed (met or not, per corpus); every cell has n
                  and a CI; all tests pass; 0 landed files edited
  n             = >= 400 games per corpus at >= 7 landmarks; 2 corpora
  eye check     = NONE. Say that.
  must not move = every landed number; `src/`; `data/`; the registers/ledgers; every flag default
  verdict       = **BAR C MET** / **BEHIND** / **NULL** / **INSUFFICIENT** (state which and why); **PARTIAL**
                  only if an arm could not run.
EVIDENCE: `docs/evidence/harness/S321_nba_prior_score_clock_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S321 | <finding with n> | <VERDICT>`) + per-corpus tick CSVs and the
bootstrap table under `docs/evidence/harness/S321_nba_prior_score_clock_2026-09-08/` (each <= 5 MB).
TEST: `tests/platformkit/test_s321_prior_state_model.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: knots, landmarks, folds, embargo, bar
C, the resample count, the family correction), the model, the comparer, the tests and the memo skeleton,
and exits `PREPARED FOR FINISHER` with the exact commands; it must NOT score the parquet itself (Q1).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08

---
**VERSION 2026-09-08b (orchestrator amendment after attempt 1 stopped INSUFFICIENT, 3d24ecdf5 in a5).** Attempt 1
measured that `nba_checkpoints_full.parquet` carries NO pre-start M0 column (`market_prob` exists only on in-game
rows; ESPN game ids; `market_ticker` = `nba-<away>-<home>-<date>`, venue polymarket for all 1,593 games). The only
close store is `data/cache/combo/gate_corpus_nba_close.parquet` (1,814 rows; `event_id` = NBA official ids such as
0022400061; `p_close`, `close_ts`, `close_kind` = first_inplay_tick, `close_sec_after_tip` ~ 0, `close_within_30s`),
whose `p_close` is the FIRST IN-PLAY QUOTE AT TIP, not a pre-start close. ATTEMPT 2 (a LIMIT measurement under
rule 2) therefore defines M0 as follows and labels it everywhere as "first in-play quote at tip (close_kind)":
  (a) build the NBA-id -> (event_date, home, away) map from any local store that carries the NBA official game id
      with team abbreviations and dates (print which store and its coverage; candidates: the box-score parquets
      named in `docs/evidence/harness/S296_full_boxscore_oof_2026-09-04.md`, `data/cache/omni_box_refresh/
      nba_player_box_extension.parquet`, an NBA stats schedule cache); join the close corpus to the checkpoints on
      (event_date, home, away) parsed from `market_ticker`; report join coverage per season (n games) and the
      distribution of `close_sec_after_tip`; games without a join get M0 = null and are EXCLUDED with n stated.
  (b) if the joined coverage is >= 400 games per season in >= 2 seasons, score bar C exactly as sealed with this
      M0; if not, the fallback M0' is the EARLIEST in-game quote of each game with game_clock_s within 60 s of the
      period-1 start (label it M0-proxy), coverage reported, and the verdict vocabulary gains the suffix
      "(M0-proxy)". Never substitute `p_elo` or `p_base` for M0 (astra rule).
  (c) S320 must be CLEAN on master before the finisher scores; if S320 landed VIOLATION, the finisher commits the
      prepared harness and reports BLOCKED-ON S320.
Everything else in VERSION 2026-09-08 stands (landmarks, folds, embargo, bar C, tests, division of labour).

---
**VERSION 2026-09-08c (orchestrator amendment, 14:50 CDT).** S320 attempt 2 (313 sealed states) found 0 ACCEPTED
terminal / future / wrong-target states and 0 prefix prediction changes, with the availability and polarity checks
NOT VERIFIED because the parquet carries no received_at or side field (verdict PARTIAL, not VIOLATION). The
gate for this row's finisher is therefore: S320 landed on master with 0 accepted violations (CLEAN or PARTIAL);
the finisher states in the memo that historical availability is NOT VERIFIED and that S328 (external as-of
replay with delay sweeps) is the falsification of any bar-C result. The M0 used is the first in-play quote at
tip (AT_TIP per S327 kinds, close_sec_after_tip ~ 0 from an independently recorded start); every result is an
AT_TIP-CONDITIONED experiment under this resealed rule, never a claim against the original pre-start bar
(astra midday review 2026-09-08); report the sensitivity note: an at-tip quote may carry early in-game
information, direction unidentified, bounded only where paired PRE_START quotes exist (none today).
