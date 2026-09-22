GAP S414 | sport nba | worktree harness-h75 (master-based) | log cx_s414_nba_state_converter_enrichment
# The NBA state vector is three numbers; the converter drops everything else and the row keeps only a digest of the payload

SINGLE PROBLEM: scripts/platformkit/ingame/baseline_four_arm_features.py:17 declares FEATURES['nba'] = ('score_diff',
'quarter', 'seconds_remaining'); domains/basketball_nba/live_state_nba.py:93 sets "possession=None,  # ESPN scoreboard does not
expose possession; never faked."; docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md:35 states "Possession is absent
and is not inferred." .planning/direction/modelling_path_2026-09-22.md section 2 mechanism (1) ranks this the LARGEST mechanism
("NBA carries three numbers ... and no foul count. The venue prices all of that") and E3 (:200-209) is the highest-prior
experiment on its list. The converter scripts/platformkit/ingame/local_state_capture_sources.py:132-134 emits exactly five keys
(period, clock_sec, home_score, away_score, elapsed_min) while local_state_capture.py:39-45 emits raw_sha256 and NOT the raw
payload -- so any field the converter does not extract at poll time is unrecoverable from the archive afterwards, and the
2026-27 forward corpus is fixed at capture. ingame_tail_gate_multi.py:85 pins "nba": "2026-10-01T00:00:00Z": the season has not
started, so the enrichment must land before it does.

BINDING BEFORE-CONDITION: quote from master (a) baseline_four_arm_features.py:12-18 FEATURES, :19-26 CORPORA, :62-160
state_eligibility (its nba branch :131-158) and :163-168 parse_state ("return {key: result[key] for key in FEATURES[sport]}");
(b) the landed indicator precedent :127-130 (result[f'{side}_red_present'] = float(key in values)) and the landed categorical
precedent :122-124 ("Categorical codes only: zero is the reference; no bit decoding."); (c) live_state_nba.py:61-97
state_from_event and its extras dict; (d) local_state_capture_sources.py:116-134 (the nba branch) and live_board.py:242-271
_parse_event (which returns ten keys and is shared with the other sports); (e) local_state_capture.py:29-45 (the emitted row);
(f) nba_checkpoints_to_joined.py:172-173 (the sealed r1 state_summary text).

CHANGE (owned files: live_state_nba.py, local_state_capture_sources.py and baseline_four_arm_features.py (MODIFIED, ADDITIVE),
NEW tests/platformkit/ingame/test_nba_state_enrichment.py, memo; live_board.py, nba_checkpoints_to_joined.py and every landed
test file are NOT edited):
1. Five enrichments read from the stored ESPN event at NAMED paths and carried on the NBA state row: possession (which side
   holds the ball), lineup (the five on the floor per side when the feed carries it, else absent), team foul counts with the
   bonus indicator per side, timeouts remaining per side, and the last play type. Each is read at one named payload path,
   recorded in the memo; a path the payload does not carry yields ABSENT. Nothing is inferred: possession is never derived from
   a score change, a clock movement or play-by-play (E3 records that a play-by-play possession can encode the outcome of the
   current possession); an absent field is counted per field in the row census, never filled.
2. RECEIPT-CAUSAL: each enriched field carries <field>_asof equal to the row's response_end_utc (local_state_capture.py:40) --
   its receipt, never the feed's source_ts, never a clock-derived instant. A field whose only available instant is not the
   receipt is ABSENT and counted.
3. DECLARED features, additive: FEATURES gains a NEW key 'nba_enriched' holding the pre-existing NBA triple followed by the
   enriched names, and CORPORA gains the new corpus version that will use it. FEATURES['nba'], the nba branch of
   state_eligibility and parse_state(text, 'nba') stay BYTE-IDENTICAL, because the sealed r1 chain reads them and E3 (:205)
   requires "a NEW corpus version (never the sealed r1)". Each enriched numeric field pairs with a <field>_present indicator on
   the landed soccer pattern (:127-130); the last play type is a fixed categorical over a code list frozen in the module and
   never widened at read time, on the landed base_1..base_7 pattern (:122-124), with the absent code as the reference; lineup is
   carried on the state row and declared only as lineup_home_present / lineup_away_present (an identity encoding of the five is
   not declared by this row).
4. Tests (construct only): a real-shaped event carrying every path parses with all five enrichments present and each _asof equal
   to the row's response_end_utc; the same event with each block removed in turn yields the field ABSENT, the _present indicator
   zero and the census count incremented, with no exception and no inferred value; parse_state(text, 'nba') on a pre-enrichment
   state text returns a byte-identical dict before and after this row, and FEATURES['nba'] is unchanged; parse_state(text,
   'nba_enriched') returns the declared enriched names in declared order; an unknown last-play code is the reference, never a
   new category; a repeat parse of the same input is byte-identical.
5. Memo docs/evidence/harness/S414_nba_state_enrichment_2026-09-22.md: the before-condition quotes, the named payload path per
   field, the per-field counts from the orchestrator's probe on a real day once the season runs (ingame_tail_gate_multi.py:85),
   a plain statement that this row CHANGES NO VERDICT -- it scores nothing, builds no corpus and reads no result -- and that a
   sealed prereg must list the enriched features before any read of them; ends with NOT VERIFIED.

CONTROLS: PREPARE only -- construct tests only; no network in the builder's run; the builder never touches the live captures,
data/cache, data/registry or any STOP file; no scoring, no corpus build, no seal, no charge, no ledger row; the orchestrator
alone runs the real-day probe. ACCEPTANCE: per-file tests pass; <= 300 LOC per file; ASCII; contract Q6 vocabulary; FEATURES
['nba'] and the landed test files unchanged; memo ends with NOT VERIFIED.
