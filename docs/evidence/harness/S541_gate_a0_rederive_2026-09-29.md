re-quote of Gate A0 under S541 hygiene

# S541 Gate A0 re-derivation (2026-09-29)

| sport / run | n_ticks | n_games | brier_model | brier_market | brier_delta | CI95 | logloss_delta | verdict |
|---|---|---|---|---|---|---|---|---|
| mlb_clean original | 78986 | 227 | 0.23768 | 0.20665 | 0.03103 | [0.01704, 0.04535] | 0.10624 | BEHIND |
| mlb_clean cleaned | 30940 | 177 | 0.16912 | 0.15216 | 0.01696 | [0.00834, 0.02542] | 0.04789 | BEHIND |
| soccer_intl original | 9003 | 51 | 0.22789 | 0.14273 | 0.08516 | [0.04876, 0.12696] | 0.40488 | BEHIND |
| soccer_intl cleaned (UNDERPOWERED, not quotable) | 1704 | 11 | 0.06538 | 0.12651 | -0.06113 | [-0.11039, -0.01152] | -0.16355 | UNDERPOWERED |

## mlb_clean exclusions

```
{
 "census": {
  "capture_ends_before_inning_9": 67,
  "capture_ends_empty": 49,
  "close_ts_equals_last_tick": 227,
  "first_kept_minus_start_min_range": [
   -29.966666666666665,
   90.21666666666667
  ],
  "kept_rows": 30940,
  "late_capture_games": 11,
  "missing_half_kept": 758,
  "no_initial_state_prefix_rows": 19,
  "no_rows_kept_games": 50,
  "reasons": {
   "bad_row": 0,
   "bad_ticker": 0,
   "carried_state_prefix": 0,
   "empty_state": 14695,
   "missing_half": 0,
   "no_initial_state_prefix": 19,
   "pre_start_window": 33332
  },
  "rows_in": 78986,
  "state_regress_games": 38,
  "state_regressions": 42,
  "ts_ties": 1659
 },
 "stream": {
  "files": 227,
  "game_id_mismatch": 0,
  "lines": 78986,
  "malformed_lines": 0
 }
}
```

## soccer_intl exclusions

```
{
 "census": {
  "kept_rows": 1704,
  "live_rows_dropped": 4649,
  "reasons": {
   "bad_row": 0,
   "empty_state": 4649,
   "unlabelled_game": 2650
  },
  "rows_in": 9003,
  "source_outcome_agrees": 4
 },
 "stream": {
  "files": 51,
  "game_id_mismatch": 0,
  "lines": 9003,
  "malformed_lines": 0
 }
}
```

Soccer labels (unlabelled games by reason; positives disclosed):

```
{
 "by_reason": {
  "all_live_no_state": 22,
  "labelled": 11,
  "last_minute_lt_90": 18
 },
 "games": 51,
 "labelled": 11,
 "labelled_last_minute_90": 11,
 "positives": 0
}
```

## Disclosures

- the 697-tick / 7-game contamination claim is not reproduced; carried_state_prefix dropped 0 rows (0 expected)
- the 30-min rule is clock-only in effect: pre_start_window dropped 33332 rows; the state rule trimmed 0 rows
- no-initial-state fallback: no_initial_state_prefix dropped 19 rows over 11 late-capture games
- by_minutes_to_close is relabelled by_minutes_to_capture_end: close_ts is the last captured tick, not the game end
- no game-end source exists on disk, so no post-final trim is possible
- soccer: 11 games labelled, 0 home wins, 11 end at minute 90 exactly; regulation label only
- extra-time / penalty outcomes are not labelled: minute_gt_90 games = 0
- missing_half rows are kept (Gate A0 phases use inning only): 758 kept
- soccer cells are UNDERPOWERED by construction (labelled games < N_MIN_GAMES 30); no soccer number from this row may be quoted elsewhere
- model_prob provenance not audited
- single capture window
- one venue
- calibration language only; this is a re-quote, not a new trial (no ledger trial charged)

## Build record (S541 builder)

Base: master 2c2ac60b365518f9f67aff060d6c0e9e3ccaa3ab (regenerated at landing; 586ec0224 at build) (worktree nba-harness-h210). Owned files, all new:
scripts/platformkit/ingame/corpus_hygiene.py, scripts/platformkit/ingame/gate_a0_rederive.py,
tests/platformkit/ingame/test_corpus_hygiene.py, tests/platformkit/ingame/test_gate_a0_rederive.py,
tests/platformkit/ingame/fixtures/s541_rows.jsonl + s541_provenance.json, this memo, two
.gitattributes lines (`tests/platformkit/ingame/fixtures/s541_* text eol=lf`,
`docs/evidence/harness/S541_gate_a0_rederive_2026-09-29.* text eol=lf`).
gate_a0_ingame_vs_market.py and docs/evidence/ingame/gate_a0_*.json are unmodified (git diff vs
586ec0224 empty); the CLI imports analyze_sport, the bootstrap, N_BOOT, SEED and N_MIN_GAMES read-only.

BEFORE (acceptance): on 586ec0224 both modules are absent (`git cat-file -e` fails for each), so
every enumerated case fails there.

BEFORE-CONDITION re-measure (read-only streaming probe, RSS 24 MB, 87,989 lines), verbatim:
`mlb_clean {'clock_dropped': 33332, 'close_eq_last': 227, 'games': 227, 'games_no_initial': 61,
'games_no_initial_all_empty': 50, 'games_one_float_outcome': 227, 'inning_no_half': 1314,
'last_empty': 49, 'last_inning_lt9': 67, 'live_exact': 26340, 'rows': 78986}`;
state domains: half top 27714 / bottom 23618 / absent 1314; outs and base absent in 100 stateful
rows; both scores present in all 52646 stateful rows.
`soccer_intl {'games': 51, 'games_all_live': 22, 'max_minute': 90, 'outcome_vals_0.0': 17,
'outcome_vals_0.5': 10, 'outcome_vals_1.0': 24, 'rows': 9003, 'rows_live': 4649}`; ts-last
minute >= 90 in 11 games, < 90 in 18.
Reproduced: 227 / 78,986 / 26,340 live / 1,314 missing half / close_ts == last tick 227 of 227 /
last inning < 9 in 67 / last empty 49 / 33,332 clock-dropped / 61 games without an initial-state
row / soccer 51 / 9,003 / 22 all-live / 11 vs 18. Differs from the spec: my initial-state test
(inning=1 half=top 0-0 among clock-kept rows) gives 50 all-empty + 11 stateful late captures, not
57 + 4 (the four named games are among the 11; the other seven are 26JUN271905WSHBAL,
26JUN271910CHCMIL, 26JUN271910COLMIN, 26JUN271910SEACLE, 26JUN271915MIASTL, 26JUN281335WSHBAL,
26JUN281337TEXTOR). AMENDMENT 1 (a) handles every such game the same way, so the rule is not
affected; the count is.

Fixture: ONE combined file s541_rows.jsonl (57 rows; per-game files tripped the preflight
row_duplication gate on game_id), one slice per source file in the order below. Source lines end
CRLF; the fixture keeps content bytes with an LF terminator. Per-slice bytes, CRLF source bytes,
sha256 and the combined sha256 are in tests/platformkit/ingame/fixtures/s541_provenance.json:
TEXCLE 1,2,3,45,190,192; CWSDET 1-4; COLLAD 1-3,185-186; SDLAD 1-3; WSHBOS 339,460-470;
PORCRO 261,267,268; MEXENG 91-92; PORESP 96-99; COLPOR 1-2,208,211-212; DZAAUT 155-156;
CODUZB 1-2,185-187; ARGSUI 1,77,78; ARGAUT 1-3 (an all-live file).
Line choices that differ from the spec text, confirmed at copy time:
- COLLAD lines 1-3 are the PRIOR day's game (07-07T02:11Z against a 07-08T02:10Z start), so they
  fall to pre_start_window; the clock-kept rows start at line 185 (inning 2 bottom 1-0) and the
  first post-start change is line 186. SDLAD 1-3: line 3 is the first change (outs/base).
- case (f): COLLAD line 1 is itself the initial state, so the carried row uses SDLAD line 1
  (1 bottom 0-2) with ts edited into the window.
- case (g): the WSHBOS pair is confirmed at lines 463 (1-2, 18:35:54Z) and 464 (0-2, 18:36:20Z);
  line 339 (the game's first clock-kept initial-state tick) is added so the slice is not a late
  capture and all rows stay kept.
- PORCRO 267-268 and COLPOR 211-212 carry no minute field; each file's last minute row (PORCRO 261,
  COLPOR 208, both minute 90) is added. A game with scores but no minute row is refused as
  `no_minute_state` (spec silent; counted).
- Q4 near-boundary (1, top) games, confirmed on the real mlb_clean corpus (AMENDMENT 2 (a)):
  26JUL031605STLCHC lines 20-22 dropped (pre_start_window), 23-25 kept; 26JUL042008STLCHC 489
  dropped, 490 kept; 26JUL101840MILPIT 19 dropped, the first kept row is line 20 at 22:11:41Z;
  26JUL101845NYYWSH 6 dropped, 7 kept; 26JUL101915BOSNYM 27 dropped, 28-29 kept.

Reconciliations (AMENDMENT 2 (b)):
- no_rows_kept is 50 games (227 - 177), not the spec's 3: the spec's own all-empty count was 57,
  and the measured value is 50 all-empty games plus 11 late captures.
- the cleaned MLB model still trails the market (BEHIND, CI excludes 0).
- residual: 93 kept rows in 9 games are (1, top, 0-0) zero-pitch placeholders more than 30 min
  after the scheduled start (postponements or delays). Removing them moves the delta to +0.016930,
  still BEHIND. The rows are kept by the sealed rule and disclosed here.
- the CLI .json output stays UNTRACKED (AMENDMENT 2 (e)); only this .md is committed. The JSON's
  bare tick counts trip the vocabulary gate's integer check and .gitignore ignores harness JSON;
  the CLI regenerates the JSON byte-identically from the corpus, and this .md carries every
  headline cell.
- original_sha256_lf hashes the LF-normalised bytes of each original gate_a0 json, so the value
  does not depend on the checkout's eol (AMENDMENT 2 (c)).

Rules settled where the spec is silent (each counted, none clamped): an unparseable or absurd
state field (inning outside 1..30, half not top/bottom, outs outside 0..3, base outside 0..7, a
score not an integer in 0..99, a duplicated key) is `bad_row`; ties on ts are ordered by the
canonical row text, so output never depends on input order; minute_gt_90 is checked before the
ts-last minute rule; soccer rows are not checked on the source outcome (0.5 is legal there); the CLI
refuses a row whose game_id differs from its file name (counted `game_id_mismatch`, then bad_row).
ts parsing uses venue_time.parse_venue_time (naive refused; sub-microsecond digits truncate, which
cannot move a value across the whole-second window boundary).

Cases (fix r1): test_corpus_hygiene.py 39 passed; test_gate_a0_rederive.py 10 passed (cases
a-h, the soccer list, Z with the LF hash pin and the soccer brier_market = mean((market_prob -
label)^2) pin, the partial-failure trio, non-finite refusal, S439 constants, (1, top, 0-1) not
initial, (1, bottom, 0-0) carried, soccer final_score from the last scored row, first change
exactly at the scheduled start).
Mutation re-run (adversarial harness vscratch_adv_s541, 32 real mutants plus a no-op that passes
39 / 10). KILLED: M01 window <=, M02 window +1 s, M03 EDT offset, M04 fallback > start, M05
fallback drops the change row, M06 fallback off, M07 late count 0, M08 score-only change, M09
carried without the (1, bottom) clause, M10 carried without the score clause, M11 carried off,
M12 initial ignores score, M13 initial ignores half, M14 ts-only tie order, M15 no sort, M16
soccer bar <=, M17 max minute, M18 minute_gt_90 off, M19 draw as home win, M20 final score from
the last timed row, M21 final score from the first scored row, M22 outcome 0.5 allowed, M23
regression counter off, M24 prefix over empty rows, M25 missing_half counter, R01 relabel off,
R02 soccer outcome from source, R04 allow_nan. SURVIVED: R03 game_id-mismatch guard off, R05
--drop-missing-half not passed through, R06 quicksort (equivalent), R07 original_overall taken
from the cleaned cell; AMENDMENT 2 (d) names no test for these, so none was added.
<!-- end build record -->

## NOT VERIFIED

- no post-final trim: no game-end timestamp exists on disk (statsapi schedule has gameDate and status only; espn boxscores have start_time only)
- soccer stoppage-time goals after the last captured minute-90 tick are unobservable
- how model_prob was produced is not audited
- the unreproduced 697-tick / 7-game contamination claim is not re-examined beyond the carried_state_prefix count
- soccer: constant-label set (11 of 11 label 0); market contract semantics (regulation vs advancement) not verified; 4 of 11 source outcomes are 1.0 despite a regulation draw
