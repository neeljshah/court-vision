# S346 -- segmenter revision 3: corroborated breaks + first-pitch anchor (prepare-only)

## What this row is

PREPARE-ONLY, worktree isolated (no corpus regeneration, no measured calibration
number). The original candidate added four code/test files; FIX 1d edits only
this row's modules, tests and memo and adds one regression test file:

- `scripts/platformkit/segment_ingame_join_r3.py` -- the revision-3
  segmenter. Imports and reuses revision-2 helpers (`read_rows`, `_ts`, `_clock`,
  `segment_end`, `write_segment`, `select_segment`, `LABEL_SIDE`, `DEFAULT_ROOT`,
  `DEFAULT_SPORTS`, `GAP_HOURS`, `BACKWARD_HOURS`) from
  `scripts/platformkit/segment_ingame_join.py` unedited, and `parse_state` from
  `scripts/platformkit/check_ingame_join_integrity.py` unedited.
- `scripts/platformkit/segment_ingame_join_r3_anchor.py` -- ticker
  first-pitch decoding (`ticker_first_pitch_utc`) and anchor-based segment
  selection (`select_segment_r3`), split out to keep both segmenter files under
  the 300 LOC rail.
- `scripts/platformkit/check_ingame_join_integrity_r3.py` -- a checker
  with three assertions that can fail on the revision-3 output.
- `tests/platformkit/test_segment_ingame_join_r3.py` --
  construct fixtures only, built under the pytest `tmp_path` fixture, never
  reads `data/`.

**REJECTED by the independent verifier (codex gpt-5.6-sol), then fixed.** The
verifier's finding 1 was correct against the spec text AS IT THEN STOOD: the
orchestrator had changed the break rule by message without amending the sealed
spec. `docs/evidence/tracking/specs/S346_spec.md` now carries **AMENDMENT 1**
(2026-09-21, orchestrator), which states the final three-trigger break rule and
two further binding rules from the same verifier round (the anchor-fallback
scope and the checker's directory scope). AMENDMENT 1 is the authority for
the original fixes below. AMENDMENTS 2 and 3 supersede it where noted.

## The break rule and the two original fixes (source of truth: AMENDMENT 1)

`docs/evidence/tracking/specs/S346_spec.md` (CHANGE item 1 + AMENDMENT 1) restates
`docs/research/ghperfect_2026-09-17/05_mlb_segment_anchor_verification.md` section
8 (local-only, gitignored, absent in this worktree by design). Restated binding
text: revision 2's `_is_break` (segment_ingame_join.py:94-96) treats a bare clock
decrease as a break with no corroboration; its `select_segment` (:136-177) anchors
on `close_ts`, the LAST tick of the SAME file -- a tautological distance of zero
that keeps a truncated tail fragment of the correct game in about 20 pct of kept
MLB files. AMENDMENT 1 additionally records WHY the break rule needs a standalone
large-gap trigger: under the pure clock-decrease-and-corroboration conjunction, a
file holding game A truncated at inning 3 followed hours later by game B first
seen at inning 5 never splits, because the clock only ever increases; revision 2
already split that case, so dropping its standalone rule is a regression.

1. `_is_break_r3`: three independent triggers. (a) revision 2's standalone
   large-gap rule, reused exactly (an absolute timestamp gap outside
   `[-BACKWARD_HOURS, GAP_HOURS]` is a break alone; `GAP_HOURS`/`BACKWARD_HOURS`
   imported, never re-tuned) -- catches two games sharing no clock/score signal.
   (b) a clock decrease, corroborated by a score reset to 0-0 from non-zero, OR a
   timestamp gap >= 60 minutes -- a BARE clock decrease with neither corroborator
   (a one-inning wobble, unchanged score, small gap) is jitter. AMENDMENT 3 replaces
   (c) with (c'): a score decrease requires a clock decrease or a >=60 minute gap.
   Uncorroborated scoring corrections do not split.
   Verified: `test_jitter_one_inning_wobble_not_split` (b, no break),
   `test_true_break_score_reset_splits` (c fires on the reset),
   `test_true_break_gap_corroboration_alone_splits` (b, gap-only corroboration),
   `test_score_correction_without_clock_decrease_does_not_split` (c', correction),
   `test_truncated_game_a_then_midgame_b_at_higher_clock_splits_via_gap_rule` (a,
   the coordinator's counter-example: clock only ever increases).
2. `select_segment_r3`: anchor on the ticker's ENCODED FIRST PITCH (decoded
   America/New_York via `zoneinfo`, DST-correct -- never a fixed UTC offset), not
   on `close_ts`. The kept segment is the one whose FIRST stated tick lands
   nearest that anchor, inside +/-90 minutes. Label agreement is a verification
   gate checked AFTER selection (never the selector); a disagreement is retained
   in the audit (`label_agreement=False`), the file is NOT dropped for it. A kept
   segment must carry a non-constant `market_prob` (>=2 distinct values) or it is
   rejected. Verified: `test_delayed_start_within_window_anchors_correctly`,
   `test_deliberately_mis_anchored_file_prefers_ticker_anchor_over_tail`,
   `test_constant_market_prob_segment_rejected`,
   `test_label_disagreement_retained_not_dropped`.

## Verifier findings 2-7, fixed (AMENDMENT 1 authority)

2. **BLOCKING -- MLB anchor fallback guessed.** `segment_file_r3` previously fell
   through to revision 2's tautological `close_ts` selection whenever
   `ticker_first_pitch_utc` returned `None`, which conflated "soccer_intl by
   design" with "an MLB ticker that failed to parse" -- exactly the guess this
   row exists to remove. Fixed: `NO_ANCHOR_SPORTS = frozenset({"soccer_intl"})`
   gates the fallback on the `sport` argument, never on whether the ticker
   happened to parse; an MLB file with a missing/unparseable ticker, no stated
   tick, an out-of-window anchor, or a genuine tie ALWAYS reports
   `reason="no_anchor"` plus a `detail` code (`unparseable_ticker`,
   `no_stated_tick`, `outside_window`, `equidistant_candidates`) and is
   quarantined (`rows=[]`), never resolved by guessing. `select_segment_r3`
   (moved to `segment_ingame_join_r3_anchor.py`) now returns the detail code
   directly instead of the old single generic `"ambiguous_two_segments_equidistant"`
   string. Verified: `test_mlb_unparseable_ticker_never_falls_back_to_revision_2`,
   `test_no_anchor_no_stated_tick_detail`, `test_no_anchor_outside_window_detail`,
   `test_no_anchor_equidistant_candidates_detail`.
3. **BLOCKING -- checker scanned the raw/revision-2 corpora too.** `check_root`
   previously iterated every subdirectory under root except ones starting with
   `_`, so it silently scanned `mlb`, `mlb_clean`, `mlb_segmented`, etc. Fixed:
   `check_root` selects only directories whose name ends `SUFFIX_R3`
   (`_segmented_r3`, imported from `segment_ingame_join_r3`, not re-declared);
   `main` exits 2 with a `NO_DATA` line when none exist. Verified:
   `test_check_root_ignores_non_r3_directories_and_exits_nonzero_when_none`.
4. **BLOCKING -- empty/malformed files verified nothing.** `check_file` set
   `non_constant_market`/`anchor_within_window` to `None` on a file with zero
   parsed rows, and `check_sport` excluded `None` records from every scored
   list -- an all-empty or all-garbage corpus could exit 0 having checked
   nothing. Fixed: `check_file` now records `"parse_failure": not rows`;
   `check_sport`/`check_root` tally `n_parse_failures_total` as its own failure
   category (not folded into the market/anchor scores, since those genuinely
   cannot be computed on an unparseable file), and `main` treats a nonzero
   `n_parse_failures_total` as a FAIL alongside the other two. Verified:
   `test_checker_r3_parse_failure_on_empty_and_malformed_files`,
   `test_check_root_and_main_aggregate_failures_and_exit_1`.
5. **CORRECTION -- doubleheader test didn't prove HHMM selects.** The prior
   fixture gave each ticker its OWN single-segment file, so passing proved
   nothing about the anchor discriminating between two candidate segments.
   Fixed: `test_doubleheader_same_teams_date_hhmm_selects_different_segment`
   writes the SAME byte-identical two-segment rows to both the early- and
   late-ticker files; only the ticker FILENAME differs between the two calls,
   and the test asserts `segment_kept == 0` for the early ticker and `== 1` for
   the late one on that identical input -- proof the ticker's own HHMM, not
   incidental row order, decides the selection.
6. **CORRECTION -- checker tests stopped at `check_file`.** No test exercised
   `check_root`/`main` against a real directory tree or the process exit code.
   Fixed: `test_check_root_and_main_aggregate_failures_and_exit_1` builds a
   `<tmp>/mlb_segmented_r3/` with a passing file, a constant-price file, a
   mis-anchored file, an empty file, and a malformed file; asserts
   `n_market_failures_total==1`, `n_anchor_failures_total==1`,
   `n_parse_failures_total==2`, AND `chk_main([...]) == 1`.
7. **CORRECTION -- manifest optional, `--check --out-json` still wrote.** Fixed:
   a normal run (no `--check`) always writes the manifest, to `--out-json PATH`
   when given or `<root>/DEFAULT_MANIFEST_NAME` ("_segmented_r3_manifest.json")
   otherwise; `--check` combined with `--out-json` is now a CLI error (exit 2,
   nothing written) instead of a silent write under the no-write contract.
   Verified: `test_segmenter_main_always_writes_manifest_default_path`,
   `test_segmenter_check_writes_nothing_and_rejects_out_json`.

## The soccer ticker finding

Read one small real file from each sport, read-only, from the main repo (not this
worktree): `data/cache/ingame_grade_joined/mlb_clean/KXMLBGAME-26JUN201310CWSDET.jsonl`
(4.0K) and `data/cache/ingame_grade_joined/soccer_intl/KXWCGAME-26JUN25TUNNED.jsonl`
(4.0K). MLB tickers carry an HHMM group between the date and the team codes
(`KXMLBGAME-26JUN201310CWSDET` -> date 26JUN20, HHMM 1310, teams CWSDET). Every
soccer_intl ticker checked (`KXWCGAME-26JUL01BELSEN`, `KXWCGAME-26JUN25TUNNED`, and
17 more listed in the directory) goes straight from the 2-digit day to the team
codes -- NO HHMM group at all. Finding: **soccer_intl tickers encode no first-pitch
time**, confirming the spec's fallback clause. `ticker_first_pitch_utc()` returns
`None` for every soccer ticker (`test_soccer_ticker_has_no_encoded_first_pitch`),
and `segment_file_r3` falls back to revision 2's unedited `select_segment` for
those files ONLY because `sport in NO_ANCHOR_SPORTS` (AMENDMENT 1 -- gated on
`sport`, never merely on the ticker failing to parse; reason prefixed
`r2_fallback_`, `test_soccer_file_falls_back_to_revision_2_selection`). Revision
3's own corroborated break rule (`split_segments_r3`) still runs ahead of the
fallback selection in both sports -- see NOT VERIFIED below for the one open
question this raises.

## DST note

`ticker_first_pitch_utc` decodes HHMM as America/New_York via the stdlib
`zoneinfo` module, not a fixed +4h offset. `test_ticker_first_pitch_utc_is_dst_aware_not_fixed_offset`
decodes the same "13:10" for a July ticker (EDT, UTC-4 -> 17:10 UTC) and a January
ticker (EST, UTC-5 -> 18:10 UTC) and asserts the January result differs from what
a fixed +4h rule would have produced.

## Prior builder command output (historical; not FIX 1c verification)

```
python -m pytest tests/platformkit/test_segment_ingame_join_r3.py -q -p no:cacheprovider
24 passed in 0.12s

python -m scripts.platformkit.segment_ingame_join_r3 --help        -> exit 0
python -m scripts.platformkit.check_ingame_join_integrity_r3 --help -> exit 0

python -m scripts.platformkit.tracking.contract_preflight --paths <the 5 new files> --base master
PASS vocab / crlf / loc / schema / head_slice / spec_threshold / proposed /
     removed_artifact / row_duplication  (9 of 9)
```

## FIX 1c -- AMENDMENT 2

Authority: [S346 spec, AMENDMENT 2](../tracking/specs/S346_spec.md).
At FIX 1c, AMENDMENT 1's three break triggers, anchor detail codes, soccer-only selection
fallback, output scope, manifest requirement, and no-write check mode remain.

Score decreases compare a team only when its score exists in both states. A
reset requires both current scores present and zero, plus a present nonzero
previous score. Clock decrease with a gap of at least one hour is independent
of score availability. FIX 1d corrects the partial-state replacement and narrows
the first-stated-tick gate as required by AMENDMENT 3.

The checker accepts only decoded dictionaries. Every non-object JSON record
or JSON decoding error increments `n_malformed_records` and marks the file's
`parse_failure`; empty files also fail. This includes mixed files, and files
containing only `null` or `[]` return exit code 1 through the normal failure path.
Regression constructs cover missing home/away scores, incomplete resets,
scoreless clock decreases at exactly one hour, partial-state anchors, and
`check_root`/`main` injections of null, lists, numbers, strings, and mixed files.
The check-mode regression also rejects an explicitly empty output argument.

FIX 1c validation in this worktree: pytest collected no tests successfully
(0 passed, 1 collection error); the segmenter help command also exited 1.
Both are blocked by the absent pre-existing module
`scripts.platformkit.segment_ingame_join`. No replacement or stub was added.
The authorized contract-preflight command, with all five paths, `--base master`,
and `--spec docs/evidence/tracking/specs/S346_spec.md`, exited 1 because
`scripts.platformkit.tracking` is absent. No automated contract PASS is claimed.
Only this row's three modules, test file, and memo were edited. No corpus was
regenerated, no calibration number measured, and no commit created.

## FIX 1d -- AMENDMENT 3

Authority: `docs/evidence/tracking/specs/S346_spec.md`, read in full.
Machine: local MASTER-based `C:/Users/neelj/nba-harness-h12`; PREPARE only.
The earlier FIX 1c missing-dependency report is historical: the revision-2
helpers and contract-preflight module are present in this worktree.
Before-condition rechecked: revision 2's `_is_break` lines 94-96 split on bare
clock decrease; `close_ts` drives selection at lines 161 and 198. It is unedited.

> (c') A SCORE DECREASE IS A BREAK ONLY WHEN CORROBORATED, exactly like trigger (b): by a clock decrease OR a timestamp gap >=
> the same 60 min corroboration constant. An uncorroborated score decrease is an in-game correction and never splits.

Satisfied by `scripts/platformkit/segment_ingame_join_r3.py:96-106`: both triggers
use `gap_corroborates` with the unchanged `CORROBORATE_GAP_HOURS`; absent team
scores are never compared as zero. The existing test
`test_true_break_score_decrease_alone_without_clock_decrease_splits` was renamed
to `test_score_correction_without_clock_decrease_does_not_split` and its expected
result changed from two segments to one, because (c') changes that exact rule.
No existing test was deleted. New tests live in
`tests/platformkit/test_segment_ingame_join_r3_breaks.py`; they reconstruct the
specified 4-to-3 pair and cover either team's score decrease with a clock
decrease, or with 59/60 minute gaps, including absent clocks.

> (d') STATE IS CARRIED FORWARD PER FIELD: prev_state = {**prev_state, **state}. A partial row (for example a clock-only tick)
> never erases a remembered score or clock, because absence is never evidence. Required regression: 5-3 in inning 9, then a
> clock-only tick at inning 1, then 0-0 inning 1 -> TWO segments (revision 2 already splits this; the candidate did not);
> the same with game B first seen at 2-1.

Satisfied by `scripts/platformkit/segment_ingame_join_r3.py:134-135`, using
`prev_state = {**(prev_state or {}), **state}`. Lines 114-137 retain a scoreless
clock decrease until the next score-bearing tick supplies corroboration; a
recovered clock, score-bearing tick, or confirmed break clears this pending
evidence. A bare clock decrease still never splits. This is needed because
merging alone would overwrite inning 9 with inning 1 before the scores arrive.
Both required regressions yield two segments, with the split at the confirming
score tick. Additional constructs retain a clock across a score-only row and
check that resolved clock wobbles do not cause later false breaks.

> (e') AN ANCHOR 'STATED TICK' requires a score or clock field (same gate as revision 2's segment_end); a row carrying only an
> unrelated numeric field never anchors.

Satisfied by `scripts/platformkit/segment_ingame_join_r3_anchor.py:58-65`: the
gate accepts `home_score`, `away_score`, `inning`, or `minute`. The checker
imports this same helper. New constructs exercise every accepted field and
verify unrelated numeric rows cannot anchor either segmenter or checker.
The local revision-2 `segment_end` actually gates on `home_score` alone;
the implementation follows (e')'s explicit score-or-clock requirement.

> (f') Memo correction: the claim that the real sample files are unstated on every row is false (52,646 of 78,986 mlb_clean rows
> are stated); remove it and say which files were sampled.

Satisfied by removing the erroneous NOT VERIFIED entry. The prior memo's
reported samples were `data/cache/ingame_grade_joined/mlb_clean/KXMLBGAME-26JUN201310CWSDET.jsonl`
and `data/cache/ingame_grade_joined/soccer_intl/KXWCGAME-26JUN25TUNNED.jsonl` in
the main repository. FIX 1d reads no corpus files. The stated-row count quoted
above and the correction pair come from AMENDMENT 3, not a new measurement.

Preserved checks cover missing away scores, scoreless clock decreases at one
hour, the +8 hour large-gap rule, DST, identical-row doubleheaders, all MLB
no_anchor detail codes, constant market_prob rejection, retained label
disagreements, checker scope/exit codes/non-object JSON, mandatory manifests,
and no writes under --check. New constructs also cover the 59-minute boundary.
Revision 2's `label_disagreements` and `multi_game_files` after-metrics could
never fail on its selected output; revision 3 tests market variation and first
stated tick distance independently, with explicit parse failures.

FIX 1d validation (local constructs only):
```text
python -m pytest tests/platformkit/test_segment_ingame_join_r3.py -q -p no:cacheprovider
41 passed in 0.71s
python -m pytest tests/platformkit/test_segment_ingame_join_r3_breaks.py -q -p no:cacheprovider
25 passed in 0.59s
```
`python -m scripts.platformkit.tracking.contract_preflight --paths` with the two
row modules, both test files, and this memo, followed by `--base master --spec
docs/evidence/tracking/specs/S346_spec.md`, exited 0: all nine checks PASS
(vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact, row_duplication). No other runtime checks were run in FIX 1d.
All changed files stay within 300 lines. No pre-existing revision-2 module or
checker was edited. SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

- No corpus regeneration, real-corpus yield measurement, or measured calibration
  number. The quoted corpus counts and truncated-tail rate were not remeasured.
- Prior real-file observations are historical; FIX 1d uses only constructs.
- Soccer uses revision-3 splitting and revision-2 selection; real contamination
  patterns for that combination remain unverified.
- The reset corroborator overlaps corroborated score decrease and is not
  isolated as a separate mechanism in the tests.
- No independent reviewer reproduction or commit was created in FIX 1d.
