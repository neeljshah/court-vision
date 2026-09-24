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

AMENDMENT 1 (2026-09-23 18:0xZ; binding; dispatch note). S393 LANDED at 6edce1f9d (2026-09-23), so the before-condition's
line numbers for local_state_capture_sources.py and local_state_capture.py are stale: the nba branch's emitted five keys
(period, clock_sec, home_score, away_score, elapsed_min) now sit at local_state_capture_sources.py:209-211 and the row's
raw_sha256 at local_state_capture.py:27 / :39; baseline_four_arm_features.py:17 and live_state_nba.py:93 are unchanged.
RULING: the before-condition is satisfied by the SAME TEXT at its current lines; the build quotes the current lines from master
at 6edce1f9d or later; every modification is ADDITIVE on the post-S393 code (the S393 per-item isolation, guarded
diagnostics and canonical identities are never bypassed -- an enrichment that cannot be read is a named ABSENT, never an
exception escaping the isolation), and every S393 test file (test_state_capture_io.py, test_state_capture_sources.py,
test_local_state_capture_schedule.py, test_state_capture_fix_1q.py, test_state_capture_fix_1s.py, plus the landed
test_local_state_capture.py, test_state_capture_recovery.py, test_state_capture_commit.py) keeps passing UNEDITED, run per
file; the S393 reproductions archive is not touched. The row's worktree is nba-harness-h83. The live state2 writer runs the
pre-S393 landed code; adopting S393 + S414 is one supervised relaunch (owner-visible) before the NBA season, never an
agent-written STOP file.

AMENDMENT 2 (2026-09-23 19:5xZ; binding; from round 1 -- Opus tier 2 REJECT and codex sol REJECT on the SAME blocker, found
independently). Tier 2 confirmed: no leakage (possession ABSENT when only scores move; a team-level flag or an
event-level situation ABSENT; an unmatched team id refused; the last play read from type.id only); bounds and shapes refused by
name; the S393 isolation holds (a raising enrichment is counted with its identity and the peer survives in both orders); the
sealed r1 preserved (FEATURES['nba'] and CORPORA['nba_checkpoints_r1'] unchanged; parse_state / state_eligibility output hash
identical on master and the candidate; 'nba_enriched' reachable only via CORPORA['nba_state_enriched_r1']); the four protected
modules byte-identical; 70 new tests plus every landed file passing. THE BLOCKER: (a) THE ENRICHMENT MUST NOT CHANGE THE LANDED
MEANING OF state_changed. The candidate writes a per-field '<field>_asof = response_end_utc' INSIDE the row's `state`
(live_state_nba.py:207 via local_state_capture_sources.py:211); the byte-identical local_state_capture.py:31-32 sets
state_changed by comparing (status, state), so the same event polled 7 s apart gives state_changed True instead of False;
forward_replay.py:108-110 pulls quotes and forward_replay_qualification.py:168 cuts the qualifying window on True, so every tick
of an enriched live NBA game would pull and cut -- corrupting S390, S421 and S424 on the very corpus this row enriches. The spec
required the per-field as-of and forbids editing local_state_capture.py. RULING: the enrichments live in a SIBLING key of the
row, `state_enrichment` (never inside `state`), with ONE receipt reference (the row's response_end_utc, which enriched_eligibility
already checks) instead of per-field stamps; the landed (status, state) comparison is therefore byte-identical to pre-S414
behaviour; FEATURES['nba_enriched'] reads from that sibling key; a test polls an identical event at two receipts and asserts
state_changed False, and a second test asserts that a changed enrichment with an unchanged `state` does NOT set state_changed
(the enrichment carries its own `enrichment_changed` flag, computed by the row builder from the previous accepted enrichment,
so a consumer that wants it has it by name). (b) Payload paths the memo cannot source to a stored ESPN NBA payload (the
competitor-level lineup, fouls, bonus and timeoutsRemaining paths and the play codes 92-99) are labelled UNSOURCED in the memo
and may be permanently ABSENT; the first real preseason payload census (October) decides. (c) An unlisted but well-formed play
code is counted under its own reason (play_code_unlisted), never `invalid`. (d) The memo states adoption as ONE supervised,
owner-visible relaunch before the season, never an agent-written STOP file. (e) The four tests failing in
test_nba_checkpoints_to_joined.py fail identically on a clean HEAD export and predate S414 (recorded, not this row's).
(f) Sol proposed an additive local_state_capture.py change (a comparison projection excluding the _asof keys); the ruling
in (a) is preferred because it edits no landed module and keeps the archived `state` byte-identical to the pre-S414 row --
the enrichment block is a sibling key; local_state_capture.py stays untouched. (g) Sol's corrections: the repeat-parse test
compares two SERIALIZED parse_state(..., 'nba_enriched') results (not two captures), and the missing-path test asserts the
stored `<field>_present == 0` (or the ABSENT marker the sibling block carries) directly.

AMENDMENT 3 (2026-09-23 18:1xZ; binding; from fix 1b -- the builder's OPEN CONFLICT). Fix 1b closed the round-1 blocker
(sibling key state_enrichment, one receipt reference, enrichment_changed; state_changed None then False on an identical event
polled 7 s apart) but the block never reaches the ARCHIVE: the landed local_state_capture.py _build_row emits a fixed key list
and nothing in the capture path calls attach_enrichment, so the 2026-27 forward archive would carry no enrichment and the row
would be dead. RULING (supersedes the 'local_state_capture.py stays untouched' clause of AMENDMENT 2 (f) and the spec's
byte-identical list for that ONE module): (a) local_state_capture.py receives the MINIMAL additive wiring and nothing else --
the import of attach_enrichment; the record built in _prepare_tick passed through
attach_enrichment(record, item, state.setdefault('last_enrichment', {})); 'last_enrichment' added to the day-rollover reset
tuple and to _prune_game. The (status, state) comparison in _build_row, the recovery path, the receipt handling and every
other line stay byte-identical; the file stays at or under 300 lines by compacting ONLY the lines the wiring touches (the two
_prune_game pops become one loop over three names; the record statement stays two lines; the import may join an existing
import line of the same package); no untouched code is reflowed. (b) The memo shows the diff of local_state_capture.py
against master hunk by hunk and states that the byte-identical set is now local_state_capture_io.py, live_board.py and
nba_checkpoints_to_joined.py. (c) Tests: the end-to-end construct (capture_state_once to the on-disk jsonl, two polls of an
identical NBA event at receipts 7 s apart) asserts the ARCHIVED rows carry state_enrichment with receipt_utc equal to
response_end_utc, enrichment_changed (None, False), state_changed (None, False) and a state of exactly the five pre-S414 keys;
a changed enrichment with an unchanged state gives an archived enrichment_changed True and state_changed False; an MLB item
(and any item without the block) produces an archived row with NO state_enrichment key, byte-identical to the pre-S414 row
(S390 / S421 / S424 read those rows); after a day rollover or a restart the first enrichment_changed is None (the enrichment
memory is not recovered from the archive -- stated in the memo as a known limit, not silently). Every landed
local_state_capture test file passes unedited (the eight files fix 1b listed plus test_local_state_capture.py itself);
contract_preflight over the owned paths plus local_state_capture.py with --base master passes. (d) The live capture keeps
running from its own worktree; landing on master changes nothing running; adoption stays ONE supervised, owner-visible
relaunch before the season (AMENDMENT 2 (d)). (e) GameState.extras carrying receipt_utc only when a caller passes a receipt is
accepted and noted in the memo.

AMENDMENT 4 (2026-09-23 18:4xZ; binding; from round 2 on fix 1c -- Opus tier 1 ACCEPT, Opus tier 2 ACCEPT WITH CORRECTIONS -- and
the fix-1d finding that the first correction conflicts with itself). Tier 2 asked that a zeroed enrichment (receipt mismatch or
missing) be NAMED so a corpus of silently zeroed rows can be counted; the builder applied it as a reasons-list entry and two
things broke: parse_state raises on any reason (an unedited landed test fails) and the eligibility gate excludes every tick whose
reasons list is non-empty (the tick would stop being scored instead of being scored with zeros). RULING: the case is named OUTSIDE
the reasons list -- the block's enrichment_census (which already carries per-field reasons such as missing_receipt) records
enrichment_receipt_mismatch or enrichment_receipt_missing for the tick, the reasons list stays empty, the gate and every landed test
stay unedited, and one construct test per case asserts the census entry with possession_present 0 and reasons []. A counter over a
corpus reads the census. The memo's extras statement (29 keys) and the notes stand as applied in fix 1d; the rollback test stays.
