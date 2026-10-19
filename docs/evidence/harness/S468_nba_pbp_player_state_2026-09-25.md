# S468 build memo: NBA per-player live block from play-by-play (PREPARE)

2026-09-25, worktree `C:/Users/neelj/nba-harness-h123` (branch `harness-h123`), master-based,
construct-only (no network, no real archive, no pod). Three new modules (`nba_pbp_player_state.py`,
`nba_pbp_registry_adapter.py`, `nba_pbp_player_census.py`) plus five test files
(`test_nba_pbp_player_state.py` and siblings `_1b`/`_1c`/`_1d`/`_1e`) implement the six declared
per-player field groups through a shared opt-in seam with `local_state_capture.py` (additive;
`nba_pbp_player` threaded only through `capture_state_once`/`_prepare_tick`, never a CLI flag),
additive to `nba_pbp_source.py` (`player_block()` called from `nba_pbp_poll` right after
`_state()`, same parsed actions, zero extra requests, now wrapped -- see FIX 1e). Premises
re-verified against the landed files before each round; `FIELDS`/`_empty()`/`SPORTS_AVAILABLE`/
`_CADENCE`/`_state()` unedited every round (confirmed by `git diff`). Metric: this row's own count
is **6 of 7 CHANGE items** (item 6's registry-perturbation case 16 is BLOCKED-ON-S460, deferred to
a joint S467+S468 register row -- see FIX 1d -- never 7 of 7); an unproven or unresolved value is a
named `'refused'`/`'lineup_unresolved'` declaration, never a zero-fill. Of the spec's 16
reproduction cases, 15 covered, 1 partial (BLOCKED-ON-S460).

## Per-case before/after (spec's own 16-case reproduction list)

| # | case | result |
|---|---|---|
| 1 | flag/opt-in absent -> byte-identical row | COVERED -- `test_flag_absent_row_byte_identical` |
| 2 | opted-in -> all six field groups present | COVERED -- `test_opted_in_all_six_field_groups_present` |
| 3 | two-action score delta attributed | COVERED -- `test_score_delta_attributed_to_scorer` |
| 4 | score field absent -> unproven | COVERED -- `test_score_field_absent_is_unproven` |
| 5 | same-side decrease -> correction unresolved | COVERED -- `test_score_decrease_is_correction_unresolved` |
| 6 | string-typed score -> unproven, no crash/coerce | COVERED -- `test_string_typed_score_refused_upstream_propagates_unproven` |
| 7 | minutes accumulate, reset at rollover, `present` | COVERED -- `test_minutes_accumulate_and_reset_at_rollover` |
| 8 | mid-period start -> `lower_bound` | COVERED -- `test_mid_period_start_is_lower_bound` |
| 9 | lineup unresolved -> `lineup_unresolved` | COVERED -- `test_lineup_unresolved_status` |
| 10 | personal_fouls independent of `_state()` | COVERED -- `test_personal_fouls_independent_of_state_replay` |
| 11 | assist/rebound/turnover + unconfirmed | COVERED -- `test_assists_rebounds_turnovers_and_unconfirmed` |
| 12 | **INTERPRETATION CALL**: OT rollover resets minutes, not cumulative `personal_fouls` (game-cumulative is the right basketball reading) | COVERED -- `test_overtime_rollover_resets_minutes_keeps_fouls` |
| 13 | simultaneous substitutions, no cross-side bleed | COVERED (FIX 1b) -- `test_case_13_adjacent_opposite_side_substitutions_no_cross_side_bleed` |
| 14 | duplicate/future/malformed reuse `_state()` names | COVERED -- `test_duplicate_future_malformed_reuse_state_drop_names` |
| 15 | writer-commit failure / period-start-missing | COVERED -- `test_writer_failure_leaves_no_player_state_promoted`, `test_period_start_missing_marks_history_incomplete` |
| 16 | **BLOCKED-ON-S460**: perturbation deferred to a joint S467+S468 register row (see FIX 1d) | PARTIAL -- census cross-check + `--out` refusal COVERED |

## Real-fixture probe (READ-ONLY, this session's first round)

`data/domains/wnba/cdn_backfill/1012600001/playbyplay.json` (gitignored, not shipped with this
row's owned paths), 405353 bytes, sha256
`883a0071362970768bf66ae4cefcdb90bd05721685aebe27dc049ca6fefffa91`, 546 actions. Every one of the
546 actions carries `scoreHome`/`scoreAway` as a STRING, not just scoring actions -- `_state()`'s
`put()` validator (`type(v) is int`) refuses both fields, and neither side's lineup resolves in the
final tick. `player_block()` over the same window: 23 distinct players, `action_type_unconfirmed:
45`, `personal_fouls` summed to 44 (the `personal`-subType fouls exactly).

## FIX 1b/1c/1d (AMENDMENTs 1-3, rounds 1-3 -- all addressed; condensed, historical)

**FIX 1b**: points forced to `None` (never `0`) under `score_attribution_unproven`/
`score_correction_unresolved`; only a MADE 2pt/3pt/freethrow of the scoring side is ever credited;
never-seen players get `lineup_unresolved`, never `None`; `lower_bound` follows
`player_history_incomplete` alone; a foul's `teamId` must be one of the game's own two teams
(named+counted else); a missing/invalid score clears the baseline; census `rows_absent`/
`rows_refused` replace a silent skip; `minutes_so_far` becomes minutes; case 13 tracked. Per-file:
`test_nba_pbp_player_state.py` 20/20, new `_1b` 13/13, `test_nba_pbp_source.py` 68/68 (unchanged);
`contract_preflight` 9/9 over 8 owned paths; must-not-move empty.

**FIX 1c**: orderNumber bound widened `0..1,000,000` -> `0..10**9` (fixture: 20,000-6,730,000);
lineup/minutes sorts EACH SIDE by its own single scale, refusing a side that MIXES a valid
orderNumber with a missing one. A made shot never yields zero without a flag (implicit 0-0
baseline); `score_vector` names `lineup_unresolved`, never the generic `<field>_absent`. Census
validates per-player counters (NaN/string/negative/non-integral -> `refused`). `minutes_so_far`
quantised to 0.01 minute. Per-file: new `_1c` 9/9; `contract_preflight` 9/9 over 9 owned paths.

**FIX 1d**: `nba_pbp_player_state.py` exposes `eligible_order` on every return path;
`nba_pbp_player_census.py` counts a non-dict top-level row `rows_invalid` and a non-dict player
record `players_refused` (never `rows_refused`, which used to double-count). S460 landed at
`19213365f`; this row states the fact and defers the case-16 test to a joint S467+S468 register
row. The `minutes_so_far` registry encoding renamed `decimal_minutes_wallclock_proxy`. The lineup
refusal rule narrowed to MIXED-scale sides only. **WITHDRAWN this round**: FIX 1d's own "mutant
proof" ran constructs OUTSIDE the delivered suite (the exact defect AMENDMENT 4 below found) -- it
proved nothing; see FIX 1e for the re-run against the actual delivered suite. Evidence-run figures
(throwaway script, coerced `int` scores, per side home/away, unaffected by FIX 1e): actionNumber
order total `[133, 152] = 285`, decreases `[6, 6] = 12`, wrong-kind `[4, 6] = 10` worth
`[41, 43] = 84` points; orderNumber order total `[91, 109] = 200`, 0 decreases, 0 wrong-kind -- the
module itself still refuses points on this feed regardless of order (two scoring-order conflicts
on the real fixture). Per-file: new `_1d` 3/3; `contract_preflight` 9/9 over 11 paths (10 code
files + this memo); must-not-move empty.

## FIX 1e (AMENDMENT 4, round 4 REJECT: tier 1 one blocker/one correction/three notes, tier 2 one
blocker/two corrections/one note -- all addressed)

Re-fast-forwarded at this round's start and confirmed again at its end:
`git -C /c/Users/neelj/nba-harness-h123 merge --ff-only master` reported already up to date both
times; `HEAD` `0cb25d05d79e4679ede97fdb4dadb47953b6c11f` and `master`
`0cb25d05d79e4679ede97fdb4dadb47953b6c11f` are EQUAL (the only such sentence in this memo).

**(e) BLOCKING, player_block never drops a game** (`nba_pbp_player_state.py:216`, called from
`nba_pbp_source.py:259` inside `nba_pbp_poll`): `SHOT_VALUES.get(action.get('actionType'))` ran on
every score increase; an `actionType` that is a list/dict raised `TypeError: unhashable type`,
which escaped into `nba_pbp_poll`'s own `except (KeyError, TypeError, ...)` and dropped the WHOLE
game -- even with the opt-in off, breaking acceptance case (1). Reproduction (period marker at the
implicit 0-0, then actionNumber 2 with `actionType=['2pt']`, Made, teamId 100, 2-0), quoted before
the fix: `RAISED: TypeError unhashable type: 'list'`; through `nba_pbp_poll`: `games returned: 0`.
A fuzz of 20000 near-valid lists (one garbage/unhashable field each) raised 400 times pre-fix, all
at this call site (re-derived fresh this round, matching the verifier's count exactly). Fix, two
layers: (1) the lookup is now guarded, `expect = SHOT_VALUES.get(action.get('actionType')) if
is_made else None` -- `is_made` already implies a hashable `str` in `SCORING_TYPES`, so this can
never receive a list/dict; anything else still falls to the pre-existing `else: score_unproven =
True` branch. (2) `nba_pbp_source.py:259-262` now wraps the call: `try: player_state = ... except
Exception: drop('player_block_error'); player_state = nba_pbp_player_state._refused
('player_block_error')` -- the base row can never depend on the sibling's health, whatever the
cause. After the fix, quoted: `refused None score_attribution_unproven True`; through
`nba_pbp_poll`: `games returned: 1`, `state.score_home 2`, `player_state refused None`,
`player_state score_attribution_unproven True`. The near-valid 20000-case fuzz re-run: 0 raises.
A forced, UNRELATED exception (`RuntimeError`, monkeypatched into `nba_pbp_player_state.
player_block`) still yields one game, the base `state` built normally, and
`player_state['refused'] == 'player_block_error'` -- the wrap, not the guard, is what saves that
case. New tests: `test_nba_pbp_player_state_1e.py` (NEW sibling, 4 tests) --
`test_unhashable_action_type_never_raises_sets_unproven`,
`test_near_valid_fuzz_of_scoring_action_fields_raises_nothing`,
`test_regression_through_nba_pbp_poll_guard_fix_no_game_lost`,
`test_regression_through_nba_pbp_poll_wrap_catches_any_exception`.

**(c) CORRECTION, the census never reads a malformed `players` value as empty**
(`nba_pbp_player_census.py:89-93`): a non-dict or missing `players` value on an otherwise-valid
block was silently read as `{}`, counting the row `rows_with_player_state` with no refusal
anywhere. Reproduction, before the fix: `census([{'player_state': {'refused': None,
'action_type_unconfirmed': 0, 'players': 'garbage'}}])` gave `rows_with_player_state 1` and no
`players_invalid` key at all. Fix: a new `players_invalid` counter, incremented whenever `players`
is not a dict (covers both a non-dict value and a missing key), returned alongside the existing
row/player counters; the docstring at :57-59 no longer says a non-dict row "is skipped" (it is
counted `rows_invalid`, unchanged behavior, corrected wording only). After the fix, quoted:
`players_invalid 1`, `rows_with_player_state 1` (garbage value) and `players_invalid 1` (missing
key). New tests in `_1d`: `test_census_nondict_players_value_counted_players_invalid`,
`test_census_missing_players_key_counted_players_invalid`.

**(a) BLOCKING, the parity fuzz must compare something**
(`test_nba_pbp_player_state_1b.py:212-254`): replaying the OLD generator (seed 468, 500 cases)
gave `refused 397, accept_empty 103, accept_nonempty 0` -- zero non-empty `eligible_order`
comparisons ever ran, so a mutant dropping `'3pt'`, `'freethrow'`, or `'foul'` from the sieve
passed all 45 owned tests (re-derived fresh this round, matching the verifier's count exactly).
Fix: (i) a FIXED case (`kinds_case`, added to `test_sieve_parity_with_state_fixed_cases`) carrying
all eight action kinds in one eligible list, actionNumbers 1-8. (ii) the fuzz generator
(`test_sieve_parity_with_state_fuzzed`) now builds mostly WELL-FORMED action lists (unique
actionNumbers via `rng.sample`, valid period/time, a random kind per action, ~20% of cases getting
exactly one garbage field or entry) instead of ~50%-garbage entries. (iii) an asserted floor,
`assert nonempty >= 200`, and a per-kind coverage assertion, `assert kinds_seen == set(kinds)`.
Measured this round: 421 of 500 cases produced a non-empty `eligible_order` comparison (was 0), and
all eight kinds were compared at least once.

Mutant re-run against the DELIVERED suite (a scratch copy of `nba_pbp_player_state.py` with one
line inserted into the eligibility loop, `if action.get('actionType') == KIND: continue`, then
`test_sieve_parity_with_state_fixed_cases` and `test_sieve_parity_with_state_fuzzed` called
directly against the mutant's `player_block`) -- all three now FAIL (caught), both by the fixed
case and by the fuzz, at `assert _state_eligible_order(actions, monkeypatch) ==
out['eligible_order']`:
- drop `'3pt'`: FAILED (caught) in both `test_sieve_parity_with_state_fixed_cases` and
  `test_sieve_parity_with_state_fuzzed`.
- drop `'freethrow'`: FAILED (caught) in both.
- drop `'foul'`: FAILED (caught) in both -- this is the exact mutant AMENDMENT 4 named as passing
  on a construct "not in the delivered suite"; it now fails on the delivered `kinds_case` alone.

**(b) NOTE, the oracle asserts its call count** (`test_nba_pbp_player_state_1b.py:138-163`):
`_state()` calls a keyed `sorted()` zero times (an early refusal), once (`ordered` at
`nba_pbp_source.py:78`, on an empty/all-dropped input), or twice (also `by_action` at :88) --
empirically confirmed this round for all six ORIGINAL fixed cases (`dup`/`bad`: 0 calls; `future`:
1 call, empty; the rest: 2 calls). Whenever the first call (`ordered`) is non-empty, `_state()`
ALWAYS reaches the second next -- this is a structural property of its own control flow, not an
accident of these six cases. Fix: `_state_eligible_order` now asserts `len(calls) == 2` whenever
its own recorded `last` call is non-empty, so a future keyed sort added to `_state()` can never
silently become "the oracle" by luck of being last.

**Cutoff citation**: the cutoff comparison (`stamp > cutoff`) is confirmed at
`nba_pbp_player_state.py:108` this round (not :103, per AMENDMENT 4's own host-fact correction);
unchanged by this round's edits.

**Per-file pass counts (current, one file at a time)**: `test_nba_pbp_player_state.py` 20/20
(unchanged); `_1b` 13/13 (2 parity tests reworked internally, same 13 test functions); `_1c` 9/9
(unchanged); `_1d` 5/5 (2 new: the `players_invalid` regressions); `_1e` 4/4 (NEW sibling);
`test_nba_pbp_source.py` 68/68 (unchanged, additive wrap only). Every unchanged suite reconfirmed
at its original count this round: `test_nba_pbp_source_1c.py` 20/20, the seven `test_mlb_lineup_
state*.py` files 18/15/4/19/16/6/7, `test_mlb_live_feed_state.py` 73/73, `test_local_state_
capture.py` 19/19, `scripts/platformkit/ingame/test_ingame_pitcher_mlb.py` 9/9 -- all green, one
file at a time. Owned total this round: 51 tests (20/13/9/5/4).

`contract_preflight --paths <11 code files> --base master --spec S468_spec.md` (plus this memo,
12 paths total): 9/9 PASS (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact, row_duplication). Must-not-move: `nba_pbp_source.py`'s edit is confined to the
`try`/`except` wrap inside `nba_pbp_poll` (lines 259-262); `_state()`, `FIELDS`, the 16-key state
dict, `SPORTS_AVAILABLE`, `_CADENCE` are untouched (confirmed by `git diff master` over those
symbols); `local_state_capture.py` and `test_nba_pbp_source.py` received NO edits this round.

## FIX 1f (round 5 ACCEPT WITH CORRECTIONS, both independent Opus tiers -- codex lane down this
round, an Opus stand-in covered tier 1 as in round 4; three CORRECTIONS, no BLOCKING findings, no
amendment written this round)

Re-fast-forwarded at this round's start: `git -C /c/Users/neelj/nba-harness-h123 merge --ff-only
master` reported already up to date. `HEAD` `0cb25d05d79e4679ede97fdb4dadb47953b6c11f` and `master`
`0cb25d05d79e4679ede97fdb4dadb47953b6c11f` are EQUAL.

**Citation correction (both tiers, NOTE)**: the parity fuzz (`test_sieve_parity_with_state_fuzzed`)
spans `test_nba_pbp_player_state_1b.py:212-257` -- the function starts at :212, and its floor and
coverage asserts (`assert nonempty >= 200`, `assert kinds_seen == set(kinds)`) sit at :256-257, one
line further than FIX 1e's own citation above stated. The `nba_pbp_poll` wrap's `try:` is at
`nba_pbp_source.py:258`; the whole try/except block now runs :258-265 after this round's fix. Both
re-confirmed against disk this round; FIX 1e's prose above is left historical/unedited, corrected
only here.

**Correction 1 (both tiers), the wrap forwarded a synthesised exception, never the real one**
(`nba_pbp_source.py:260-262`, inside `nba_pbp_poll`'s player_block wrap): `drop
('player_block_error')` calls `src.report(get, 'nba_pbp', reason, on_error=on_error)` with no
`error=` argument, so `on_error` always received a synthesised `ValueError('player_block_error')`
-- the real exception's type and message, potentially the only evidence identifying an
unenumerable sibling defect, were discarded. The neighbouring `game_invalid` path
(`nba_pbp_source.py:266-267`) already forwards its own caught `exc`; this wrap did not. Repro,
quoted before the fix: `player_block` monkeypatched to raise `RuntimeError('secret detail')`, one
live game, `on_error=errs.append` -> `errs == [ValueError('player_block_error')]` (message
'player_block_error', type `ValueError` -- not the injected `RuntimeError`/'secret detail'). Fix:
`except Exception as exc: src.report(get, 'nba_pbp', 'player_block_error', exc, on_error)` in place
of `drop('player_block_error')`, mirroring the `game_invalid` call site; the refused `player_state`
and the `drops_by_reason` count are unchanged. After the fix, quoted: `errs == [RuntimeError(
'secret detail')]`. New test (sibling `_1f`):
`test_wrap_forwards_original_exception_not_synthesized_valueerror`, asserting `type(errs[0]) is
RuntimeError` and `str(errs[0]) == 'secret detail'`.

Layer distinction (tier 2 NOTE, reconfirmed): through `nba_pbp_poll`, a `['2pt']` Made action (an
unhashable `actionType`) never reaches this wrap -- `nba_pbp_player_state.py`'s own `SHOT_VALUES`
guard (FIX 1e, layer 1) catches it first and returns a normal, non-raising block: `refused: None`,
`score_attribution_unproven: True`. Quoted, reconfirmed this round: `games 1`, `state.score_home 2`,
`player_state {refused: None, score_attribution_unproven: True, action_type_unconfirmed: 1,
players: {}, eligible_order: (1, 2)}`. Only an ACTUAL raise out of `player_block` (something layer
1's guard does not anticipate) reaches this wrap and yields `refused: 'player_block_error'`.
S468_spec.md's AMENDMENT 4(e) sentence describing the `['2pt']` case as "a refused player_state"
should read "points refused (unproven)" -- the block itself is not refused, only its `points` field
is (tier 1 NOTE, not edited here per this round's own no-amendment framing).

**Correction 2 (both tiers), the census lineup lookup raised on a malformed `side`**
(`nba_pbp_player_census.py:125`, inside `census()`): `side_lineup.get(rec.get('side'))` raises
`TypeError: unhashable type` whenever a player record's `side` is a list/dict/set, contradicting
the module's own docstring (`:61-63`) that census "never raises on a malformed row" -- one bad row
would abort the whole date. Repro, quoted before the fix: `census([{'player_state': {'refused':
None, 'action_type_unconfirmed': 0, 'players': {'1': {'side': ['home'], 'points': 0}}}, 'state': {
'lineup_home': ['1'], 'lineup_away': ['2']}}])` -> `RAISED: TypeError unhashable type: 'list'`. Fix:
the lineup lookup now runs only when `side` is exactly `'home'` or `'away'`; any other value is
counted under a new named key, `side_invalid`, never skipped silently and never looked up at all.
After the fix, quoted: `side_invalid 1`, `lineup_mismatch 0`, no raise. A second regression confirms
the existing `lineup_mismatch` check is unchanged for a valid side. New tests (sibling `_1f`):
`test_census_unhashable_side_counted_side_invalid_never_typeerror`,
`test_census_valid_side_still_checks_lineup_mismatch`.

Audit (this round, requested alongside correction 2): the row's other two owned modules were
checked for the same shape of defect -- a fixed-key dict indexed by an untrusted per-record field.
`nba_pbp_player_state.py:289-291` indexes `points`/`personal_fouls`/`rebounds`/`turnovers`/
`assists` by `pid`, but those dicts are built FROM the same action stream that produces the `pid`
set itself (not from an independent, caller-supplied field like `side`), so they are not the same
class of defect. No other instance found in this row's three owned modules this round; a wider
sweep of OTHER harness census/reporting code is out of this row's scope (see NEW GAPS below).

**Correction 3 (tier 2), `player_block_error` was not a declared refusal reason**
(`nba_pbp_registry_adapter.py:57-59`): `BLOCKS[field]['refusal_vocabulary']` -- read by
`score_vector` and any downstream consumer validating declared reasons -- omitted the one reason
correction 1's own wrap actually produces. Repro, quoted before the fix: `'player_block_error' in
reg.BLOCKS['points']['refusal_vocabulary']` -> `False`, while `reg.score_vector(pstate._refused(
'player_block_error'), 'v')['points'] == {'refused': 'player_block_error'}` -- an undeclared reason
reaching a declared-vocabulary consumer. Fix: added `'player_block_error'` to the shared tuple
built into every field's block (all six `FIELDS` inherit it via the existing comprehension). New
test (sibling `_1f`): `test_registry_declares_player_block_error_refusal`, asserting membership for
every field plus the `score_vector` round-trip.

**Per-file pass counts (current, one file at a time)**: `test_nba_pbp_player_state.py` 20/20
(unchanged); `_1b` 13/13 (unchanged); `_1c` 9/9 (unchanged); `_1d` 5/5 (unchanged); `_1e` 4/4
(unchanged); `_1f` 4/4 (NEW sibling); `test_nba_pbp_source.py` 68/68 (unchanged, additive wrap
only). Every unchanged suite reconfirmed at its original count this round, one file at a time:
`test_nba_pbp_source_1c.py` 20/20, `test_local_state_capture.py` 19/19, `test_local_state_capture_
differential.py` 5/5, `test_local_state_capture_schedule.py` 367/367 (the last three import the
modified `nba_pbp_source.py`/`local_state_capture.py`). Owned total this round: 55 tests
(20/13/9/5/4/4).

`contract_preflight --paths <12 code/test files> --base master --spec S468_spec.md` (plus this
memo, 13 paths total): 9/9 PASS (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact, row_duplication). Must-not-move: `nba_pbp_source.py`'s round-5
edit is confined to the `except` clause inside the pre-existing player_block wrap (still inside
`nba_pbp_poll`, `try:` unchanged at :258); `nba_pbp_player_census.py`'s edit is confined to the
`side_lineup` lookup inside `census()`; `nba_pbp_registry_adapter.py`'s edit is confined to the
`refusal_vocabulary` tuple literal; `local_state_capture.py` and `test_nba_pbp_source.py` received
NO edits this round (`git status --porcelain` before and after this round: identical, confirmed by
diff).

**NEW GAPS (register, both tiers)**: (1) `nba_pbp_player_census.py`'s `rows_refused` counter has no
per-reason split, so a `player_block_error` row is indistinguishable from an `action_shape_invalid`
row in the census output -- a `rows_refused_by_reason` counter would close this; out of this row's
own scope. (2) the sibling import `from scripts.platformkit.ingame import nba_pbp_player_state` at
`nba_pbp_source.py:182` sits OUTSIDE the try/except wrap (the wrap only guards the `player_block(
...)` call itself) -- an import-time defect in `nba_pbp_player_state.py` (a syntax error, a bad
module-level default) would still raise unguarded and could sink the base poll, even with the
opt-in off. (3) carried from the audit above: a wider sweep of OTHER harness census or reporting
code for the same unhashable-key-lookup class of defect (this row's own three modules are clear).

## A9 identities (regenerated from disk, this round's closing edit)

LF-normalised (`\r\n` -> `\n`) bytes and sha256 below, regenerated from disk as this round's
closing edit, all eleven owned code files.

| path | LOC | raw bytes | LF bytes | sha256 (LF-normalised) |
|---|---|---|---|---|
| scripts/platformkit/ingame/nba_pbp_player_state.py | 299 | 19269 | 19269 | 35c13235eca462cb104c2f6085d041b9c3b8ed030b13048c80680894e0cabdb8 |
| scripts/platformkit/ingame/nba_pbp_registry_adapter.py | 111 | 6519 | 6519 | f4870cec1ae224c39b8f1c8b6aeae286f12624c39f8a29aa64b2ec67d8609646 |
| scripts/platformkit/ingame/nba_pbp_player_census.py | 187 | 9523 | 9523 | c9e279c8c5fa12c0f7791eb0de18577e55ca1b9db7960d8b563cca783f6053c8 |
| tests/platformkit/ingame/test_nba_pbp_player_state.py | 250 | 13561 | 13561 | 96a35508464398f535c96f38a559f8e40a328962793fcf02dba6c55f683f2198 |
| tests/platformkit/ingame/test_nba_pbp_player_state_1b.py | 299 | 17737 | 17737 | 708fd298341df5b57cbd308b0645b59162b70404d55947586b95b1a96336e5f8 |
| tests/platformkit/ingame/test_nba_pbp_player_state_1c.py | 119 | 7081 | 7081 | 6ab2958ce10d70f9893a66733d737125d61e4582ce52f1db1dfa50dcc3a554d8 |
| tests/platformkit/ingame/test_nba_pbp_player_state_1d.py | 58 | 3372 | 3372 | 3f6f3307fbabd3893c6327bb87ab276801e3dacc72d4441f70821aaed5df1de4 |
| tests/platformkit/ingame/test_nba_pbp_player_state_1e.py | 87 | 5221 | 5221 | ee596aa3c31bdab876199f050a23599ebd6d2bd12b49253bdc0adea4635d2a6d |
| tests/platformkit/ingame/test_nba_pbp_player_state_1f.py | 77 | 4256 | 4256 | 7eb4f2b492b02a510f9ca8c998f2f59ae331497e20368c8d92567515be868434 |
| scripts/platformkit/ingame/nba_pbp_source.py | 271 | 15723 | 15452 | 9bda5bb62eaf912f103850452b3ce07724d8d4b39497570d4ec5bac8cd49dd13 |
| scripts/platformkit/ingame/local_state_capture.py | 300 | 18158 | 17858 | 60eac7412421886563f269691e4ad92b76df6d32be3267a44cf207d84f82000b |
| tests/platformkit/ingame/test_nba_pbp_source.py | 300 | 20585 | 20285 | 3bfcf4956759bf2c7575b0971d71595124251a5f107d3ab1ce1cd01a668f3a6c |

`local_state_capture.py` and `test_nba_pbp_source.py` hashes above are BYTE-IDENTICAL to the FIX
1d table (re-verified, not assumed) -- confirming neither received an edit this round.

Owned-path list for the landing pathspec (12 files, 9 new / 3 modified-additive):
```
scripts/platformkit/ingame/nba_pbp_player_state.py
scripts/platformkit/ingame/nba_pbp_registry_adapter.py
scripts/platformkit/ingame/nba_pbp_player_census.py
tests/platformkit/ingame/test_nba_pbp_player_state.py
tests/platformkit/ingame/test_nba_pbp_player_state_1b.py
tests/platformkit/ingame/test_nba_pbp_player_state_1c.py
tests/platformkit/ingame/test_nba_pbp_player_state_1d.py
tests/platformkit/ingame/test_nba_pbp_player_state_1e.py
tests/platformkit/ingame/test_nba_pbp_player_state_1f.py
scripts/platformkit/ingame/nba_pbp_source.py
scripts/platformkit/ingame/local_state_capture.py
tests/platformkit/ingame/test_nba_pbp_source.py
```

SHA: NOT CREATED (sandbox); files ready for lane_commit -- this lane made no commit (never
commits by rail); files are left on disk in `/c/Users/neelj/nba-harness-h123`.

## NOT VERIFIED

Everything above the "Real-fixture probe" section is construct-only (`n = 16 (CONSTRUCT)`,
matching the spec's own enumeration); the probe itself is one real read, not a sampled or scored
measurement, and not a second corpus (WNBA, not NBA). Case 13, the census's `points` ambiguity, the
orderNumber bound/mixing, the made-shot-never-silent rule, counter validation, minutes
quantisation, the parity oracle (now proven against the delivered suite, FIX 1e), the census unit
split, and the game-loss/unhashable-actionType defect are all now COVERED. Still NOT VERIFIED,
last: (1) whether live NBA feeds use this WNBA fixture's orderNumber scale; cdn.nba.com is
403-blocked from this host (S433 P1), so this stays the orchestrator's first-live-night PREMISE
probe; (2) whether real NBA-live payloads carry the same vocabulary and string-typed scores this
WNBA fixture does; (3) the registry adapter's real consumption now that S460 has landed (deferred
to the joint S467+S468 register row, now S471 per the register, MLB-only); (4) whether the
wall-clock-minutes proxy tracks real on-court minutes closely enough to be useful live; (5) any
real-game agreement rate between this module's lineup resolution and `_state()`'s own; (6) a
player id present in both sides' on-court sets, silently reporting whichever side is iterated
last; (7) whether a per-side monotonic check, instead of the current global scoring-order-
disagreement rule, would let orderNumber attribution actually produce a value on a feed like this
one (NEW GAP, register, not this row); (8) any mutant survival beyond the three named and probed
this round; (9) the census CLI end to end (`--help` confirmed only this round); (10) auditing every
other harness fuzz with this garbage-heavy generator shape for the same non-empty-comparison-floor
defect (register gap, not this row).

No trial charged; no ledger K read; calibration language only throughout this row; this session
made no network call and wrote nothing under `data/` or `vault/` beyond reading the one
already-present fixture file for the probe.
