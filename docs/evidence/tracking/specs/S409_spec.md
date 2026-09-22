GAP S409 | sport all captured | worktree harness-h74 (master-based) | log cx_s409_schedule_identity_attestation
# The keyed schedule mapping is trusted absolutely: two swapped game_keys yield clean counts for the wrong games

SINGLE PROBLEM: scripts/platformkit/execution/forward_capture_bridge.py _resolve (its lines 79-97) links a committed schedule
entry by EXACT IDENTITY -- "if (sport, key) not in state_keys" (:89), "if entry is None or game['ticker'] not in
entry['tickers']" (:92), then "return key, None" (:97). Presence of the key and presence of the ticker are the whole check; no
team evidence is ever compared. docs/evidence/tracking/specs/S404_spec.md AMENDMENT 1 put that path in precisely because the
directional linker refuses -- "missing_directional_team_evidence 19", the book rows carrying no home / away evidence. Hence
docs/evidence/harness/S390_astra_r4_critique_2026-09-22.md item 2: "Swapping two existing keys can yield clean PASS counts for
the wrong games ... The artifact alone cannot reveal this error." The schedule hash identifies a mapping; nothing on master
attests one against independent event metadata before qualification.

BINDING BEFORE-CONDITION: quote from master (a) forward_capture_bridge.py:79-97 (_resolve) and :72-76 (_duplicated -- it
catches a duplicate claim, never a swapped one); (b) forward_schedule_writer.py:232-237 (key = _text(game.get('game_key')) and
the entry it appends); (c) game_market_link.py:25 ALIASES, :30 alias, :58 team_code_from_ticker, :64-95 index_kalshi_events
(entry['team_codes'], entry['tickers'], and home_abbr / away_abbr left None when the rows carry no team evidence); (d)
local_state_capture.py:39-45 (the emitted state row -- sport, game_key, date, home_abbr, away_abbr, status are the only team
evidence a state row carries); (e) local_capture_runner_row.py:44-50 envelope (no title and no rules field) with :63 and :102
(raw_market=deepcopy(...) is the only carrier of Kalshi title / rules text), plus local_capture_state.py:49 event_title.

CHANGE (owned files: NEW scripts/platformkit/ops/schedule_identity_attestation.py, NEW tests/platformkit/ops/
test_schedule_identity_attestation.py, memo; forward_capture_bridge.py, forward_schedule_writer.py, game_market_link.py, the
S390 runner and every landed test file are NOT edited -- this row adds a reader and changes no linkage):
1. Three INDEPENDENT team-evidence sets per committed (sport, game_key, game_id, ticker) entry, each built only from what the
   cited paths carry. E_state = {alias(sport, home_abbr), alias(sport, away_abbr)} over the state rows whose (sport, game_key)
   matches the entry on the entry's UTC date; two different non-missing codes for one side is state_team_set_conflicted.
   E_title = the uppercase tokens of the event's Kalshi title / rules text (raw_market keys title, subtitle, yes_sub_title,
   rules_primary, rules_secondary, and event_title) mapped through alias(); ALIASES (game_market_link.py:25) maps abbreviation
   to abbreviation only and carries NO full-team-name mapping, so a title carrying full names yields no code and the reason is
   title_team_names_unmapped -- never a guessed code. E_ticker = index_kalshi_events(...)[game_id]['team_codes'] union
   {team_code_from_ticker(entry ticker)}.
2. One verdict per entry, counts only, no linkage decision and no qualification consequence. ATTESTED when all three sets are
   non-empty and agree. REFUSED when any two non-empty sets disagree, with the disagreeing pair named --
   state_vs_title_mismatch, state_vs_ticker_mismatch or title_vs_ticker_mismatch, never a generic reason. UNATTESTABLE with the
   named reason state_teams_absent, title_evidence_absent, title_team_names_unmapped or ticker_codes_absent when the evidence is
   simply not there; UNATTESTABLE is counted on its own line and is NEVER folded into ATTESTED.
3. A SWAP is cross-entry and refuses both sides: for i != j in the same (sport, date), when entry i's E_state agrees with entry
   j's (E_title union E_ticker) and entry j's E_state agrees with entry i's, both entries are REFUSED
   schedule_identity_swapped. A swap in which either side is UNATTESTABLE stays UNATTESTABLE -- absence never proves a swap.
4. Output: one attestation JSON per schedule, written beside the schedule, carrying schedule_sha256, generated_at, the per-entry
   records (sport, game_key, game_id, ticker, verdict, reason, the three evidence sets sorted) and the verdict counts. The S390
   runner may consume it later; this row does not modify S390 and grants nothing to it.
5. Tests (construct only): a matched fixture attests; a SWAPPED PAIR built by exchanging two entries' game_keys refuses both
   with schedule_identity_swapped; a title carrying full team names is title_team_names_unmapped and is not attested; book rows
   with no team evidence whose tickers carry no outcome suffix are ticker_codes_absent; a game_key whose state rows carry two
   different home codes is state_team_set_conflicted; a repeat run on the same input serializes byte-identically.
6. Memo docs/evidence/harness/S409_schedule_identity_attestation_2026-09-22.md: the before-condition quotes, the fixture
   verdicts, and the verdict counts from the orchestrator's real run on the 2026-09-22 and 2026-09-23 committed schedules
   (counts only, per sport and per reason, no game named as qualified); ends with NOT VERIFIED.

CONTROLS: PREPARE only -- construct tests only; no network; the builder reads no archive and never touches the live captures or
any STOP file; the orchestrator alone runs the module on the two committed schedules; never write data/registry; never edit the
bridge, the writer or S390. ACCEPTANCE: per-file tests pass; --help works; <= 300 LOC per file; ASCII; contract Q6 vocabulary;
the landed bridge and writer test files pass unchanged; memo ends with NOT VERIFIED.
