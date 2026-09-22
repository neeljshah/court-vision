GAP S346 | sport mlb + soccer_intl | worktree (claude sonnet, isolated) | log cx_s346_segmenter_rev3
# Segmenter revision 3: corroborated breaks + first-pitch anchor + a checker that can fail (astra round 10 rank 2)

SOURCE OF TRUTH: docs/research/ghperfect_2026-09-17/05_mlb_segment_anchor_verification.md section 8 (local-only file; the
binding text is restated here). SINGLE PROBLEM: scripts/platformkit/segment_ingame_join.py keeps a TRUNCATED TAIL FRAGMENT
of the correct game in about 20 pct of kept MLB files, because (a) `_is_break` (:94-96) treats a bare clock decrease as a game
break, and (b) `select_segment` (:136-177) anchors on close_ts, which is the last tick of the same file (tautological: distance 0).

BINDING BEFORE-CONDITION (re-run, quote): `grep -n "close_ts" scripts/platformkit/segment_ingame_join.py` shows the anchor at
:161 and :197-198; `grep -n "def _is_break" -A 4` shows no score-reset or gap corroboration.

CHANGE (ADDITIVE, contract B2 -- revision 2 behaviour stays reachable and is the default until the finisher row flips nothing):
1. NEW scripts/platformkit/segment_ingame_join_r3.py (<= 300 LOC, stdlib; import and reuse revision-2 helpers, do not edit them):
   - break = clock decrease AND (score reset to 0-0 from non-zero OR timestamp gap >= 60 min); a one-inning wobble with an
     unchanged score is jitter.
   - anchor = the segment whose FIRST stated tick is nearest the ticker's encoded first pitch (KXMLBGAME-<YY><MON><DD><HHMM>...,
     HHMM is ET; +4 h to UTC in season), inside a declared +/- 90 min window; no selection by outcome agreement; label agreement
     is a VERIFICATION gate reported after selection, and disagreements are RETAINED in an audit list, never dropped silently.
   - gate: a kept segment must carry a non-constant market_prob.
   - tolerate delayed starts and doubleheaders (two tickers same teams same date differ in HHMM); unresolvable -> status
     `no_anchor` with counts, never a guess.
   - output root is a NEW sibling directory `<sport>_segmented_r3` plus a manifest JSON (per file: segments found, kept index,
     anchor distance minutes, ticks in/kept/dropped, label agreement, reason codes). CLI `--check` prints the census without writing.
2. NEW scripts/platformkit/check_ingame_join_integrity_r3.py: assertions that CAN fail -- (a) non-constant market_prob,
   (b) first stated tick within +/- 90 min of the encoded first pitch; the memo states that revision 2's two green after-metrics
   (label_disagreements, multi_game_files) could never fail.
3. tests/platformkit/test_segment_ingame_join_r3.py: construct cases -- jitter not split, true break split, delayed start,
   doubleheader, deliberately mis-anchored file, constant-price segment rejected, no_anchor path, soccer ticker (document the
   soccer ticker time encoding you find; if none exists, soccer keeps revision 2 selection and the memo says so).

CONTROLS: PREPARE only. Do NOT regenerate any corpus, do NOT touch webapp/, do NOT edit gate_a0 (that is S347). No measured
calibration number. ACCEPTANCE: the per-file test passes; `python -m scripts.platformkit.segment_ingame_join_r3 --help` works;
diff = NEW files only. Vocabulary follows contract Q6; automated scan required. Memo docs/evidence/harness/
S346_segmenter_rev3_2026-09-21.md ends with a NOT VERIFIED list.

AMENDMENT 1 (orchestrator, 2026-09-21, AFTER the first verifier REJECT; this block is binding and supersedes the break rule in
CHANGE item 1). Process note, stated plainly: the orchestrator changed the break rule by message to the builder WITHOUT amending
this spec, and the verifier correctly rejected the candidate for contradicting the sealed text. The rule is amended here instead
of being overruled from the chair.
FINAL BREAK RULE -- a game break is ANY of:
  (a) revision 2's standalone large-gap rule, reused byte-exact by import (GAP_HOURS / BACKWARD_HOURS; never re-tuned);
  (b) a clock decrease corroborated by a score reset to 0-0 from non-zero OR a timestamp gap >= 60 min;
  (c) a decrease in either team's cumulative score (impossible inside one game).
  A BARE clock decrease with no corroboration is NOT a break (the jitter fix; the reason this row exists).
WHY (a) and (c): under the pure conjunction, a file holding game A truncated at inning 3 followed hours later by game B first
  seen at inning 5 never splits, because the clock INCREASES; revision 2 already split that case, so dropping (a) is a regression.
ALSO BINDING (from the same verifier round): an MLB ticker that is missing, unparseable or ambiguous (equidistant candidates)
  returns status no_anchor with a detail code -- it NEVER falls through to revision 2's close_ts selection; that fallback is
  permitted ONLY for soccer_intl, whose tickers carry no encoded start time. The r3 checker inspects ONLY directories ending
  _segmented_r3, exits nonzero when none exist, and treats an empty or wholly malformed r3 file as an explicit FAILURE.
  `--check` writes nothing: every output option is rejected under --check; a normal run always emits the manifest.

AMENDMENT 2 (orchestrator, 2026-09-21, after the second verifier REJECT; binding). PARTIAL STATE ROWS ARE NORMAL in the real
corpus, so absence of a field is never evidence:
  - a score comparison (trigger (c), score decrease) is made for a team ONLY when that team's score is present in BOTH the
    previous and the current state; a missing score is never read as zero;
  - a score RESET (the corroborator in trigger (b)) requires BOTH current scores present and equal to 0, and at least one
    previous score present and non-zero;
  - the clock-decrease + timestamp-gap >= 60 min corroboration in trigger (b) is evaluated INDEPENDENTLY of score availability
    (absent scores must not suppress it);
  - the r3 checker accepts ONLY decoded JSON objects as records: valid JSON that is not an object (null, a list, a number, a
    string) is a malformed record, counted as parse_failure, and a file made only of such records is an explicit FAILURE with
    exit code 1 -- never an unhandled exception.
Regression tests required: a tick missing away_score inside an otherwise increasing game does NOT split; a clock decrease with a
>= 60 min gap and NO score fields DOES split; check_root / main injections using `null` and `[]` lines.

AMENDMENT 3 (orchestrator, 2026-09-21, after the independent Claude review REJECT; binding). AMENDMENT 1 trigger (c) rested on the
orchestrator's premise that a score decrease is impossible inside one game. THE CORPUS FALSIFIES IT: real pair from
mlb_clean/KXMLBGAME-26JUL011420SDCHC.jsonl -- 18:53:20Z home_score=4 inning=2, then 18:53:46Z home_score=3 inning=3 (a scoring
correction 26 s later with the clock advancing). Reviewer measurement (pure functions in memory, counts only): 18 of 227 MLB
files carry such a pair; on 12 files the kept segment changes and 1,140 same-game ticks leave the corpus.
  (c') A SCORE DECREASE IS A BREAK ONLY WHEN CORROBORATED, exactly like trigger (b): by a clock decrease OR a timestamp gap >=
       the same 60 min corroboration constant. An uncorroborated score decrease is an in-game correction and never splits.
  (d') STATE IS CARRIED FORWARD PER FIELD: prev_state = {**prev_state, **state}. A partial row (for example a clock-only tick)
       never erases a remembered score or clock, because absence is never evidence. Required regression: 5-3 in inning 9, then a
       clock-only tick at inning 1, then 0-0 inning 1 -> TWO segments (revision 2 already splits this; the candidate did not);
       the same with game B first seen at 2-1.
  (e') AN ANCHOR 'STATED TICK' requires a score or clock field (same gate as revision 2's segment_end); a row carrying only an
       unrelated numeric field never anchors.
  (f') Memo correction: the claim that the real sample files are unstated on every row is false (52,646 of 78,986 mlb_clean rows
       are stated); remove it and say which files were sampled.
Required tests: the real 4 -> 3 correction pair does NOT split; a score decrease WITH a clock decrease splits; a score decrease
WITH a >= 60 min gap splits; both carry-forward regressions; the anchor gate.
