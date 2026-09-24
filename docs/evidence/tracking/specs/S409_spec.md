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

AMENDMENT 1 (2026-09-23 16:2xZ; binding; from the ORCHESTRATOR REAL RUN of the build candidate over the 2026-09-22 shards:
--schedule docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json (sha256 27465f64ca2a7ef232a1a3dfd6412f
7c448905b9bc30b9c0217f40760eaddadd) --states data/cache/ingame_capture_view_v2/state/mlb/2026-09-22.jsonl --books
data/cache/ingame_capture_view_v2/kalshi/mlb/2026-09-22.jsonl --generated-at 2026-09-23T16:15:00Z). RESULT: ATTESTED 0,
REFUSED 6, UNATTESTABLE 0; every game state_vs_title_mismatch; E_state and E_ticker agree on all six (BAL/TOR, MIL/PHI,
PIT/STL, BOS/CLE, ATL/CIN, CHC/MIA) while E_title is ["EDT", "PM"] on all six; ignored_record_type 127201. CAUSE, MEASURED on
the real snapshot row for KXMLBGAME-26SEP221835TORBAL-BAL: raw_market.title = 'Toronto wins', subtitle None, yes_sub_title =
'Toronto', no_sub_title = 'Toronto', event_title None, rules_primary = 'If Toronto wins the Toronto vs Baltimore professional
baseball game originally scheduled for Sep 22, 2026 at 6:35 PM EDT, then the market resolves to Yes.' -- the venue's text
carries team NAMES (city names), never codes, and the candidate's TOKEN regex ([A-Z]{2,} runs over every TEXT field including
the rules) harvested the clock tokens PM and EDT as codes. A construct fixture without a scheduled time could not show this.
RULINGS. (1) Title evidence is NAME evidence: E_title is the set of codes whose team NAME appears in the text, resolved through
a DECLARED alias table derived from the landed full-name table (scripts/platformkit/ingame/ingame_id_resolver_mlb.py:60-92,
'toronto blue jays' -> 'TOR' etc.; the row does not edit that module, it imports the table and derives city and nickname
aliases from it by a documented rule); matching is case-insensitive on word boundaries over title, subtitle, yes_sub_title,
no_sub_title, event_title, rules_primary and rules_secondary. (2) An ambiguous city (Chicago, Los Angeles, New York) maps to
NO code by itself and is counted title_city_ambiguous; it maps only when the nickname is present. (3) An uppercase token is
team evidence ONLY when it is itself a code in the sport's declared code set; every other uppercase token (PM, EDT, ET, AM,
UTC, TBD, ...) is dropped and counted title_tokens_ignored, never evidence. (4) A text with names that map to nothing stays
title_team_names_unmapped (REFUSED, as today); a text with no names and no codes stays title_evidence_absent. (5) Sports other
than MLB whose landed resolver has no name table: E_title is title_evidence_absent -> UNATTESTABLE, never a guess; the memo
names which sports have a table. (6) The memo records THIS real run verbatim (the counts above) as the BEFORE state, and the
fix's own real re-run by the orchestrator must ATTEST all six 2026-09-22 games or name the per-game reason; a fixture built
from the verbatim TORBAL raw_market text above (with its 6:35 PM EDT clause) is the first test. (7) The attestation artifact is
written next to the schedule as <schedule>.attestation.json (as the candidate does); the orchestrator's real-run artifact from
the BEFORE state is not committed.

AMENDMENT 2 (2026-09-23 16:4xZ; binding; from the ORCHESTRATOR REAL RE-RUN of fix 1b over the 2026-09-22 selection, same
inputs as AMENDMENT 1, --generated-at 2026-09-23T16:40:00Z). RESULT: ATTESTED 5, REFUSED 1, UNATTESTABLE 0;
title_tokens_ignored 16520, title_city_ambiguous 2600, ignored_record_type 127201. CINATL, TORBAL, CLEBOS, MILPHI and STLPIT
attest with E_state == E_title == E_ticker. MIACHC is REFUSED state_vs_title_mismatch with E_state ['CHC', 'MIA'], E_ticker
['CHC', 'MIA'] and E_title ['MIA']: the venue's text names 'Chicago' without a nickname, so ruling (2) of AMENDMENT 1 maps it to
nothing (counted title_city_ambiguous) and the title evidence is a PROPER SUBSET of the state evidence, not a contradiction.
RULING: a set comparison that refuses a consistent subset throws away evidence that still catches a swap (two swapped keys put
a code in the title that the state does not carry). (1) E_title that is NON-EMPTY and a SUBSET of BOTH E_state and E_ticker
(with E_state == E_ticker) attests: verdict ATTESTED with the flag title_partial true and the missing codes listed under
title_codes_unresolved (counted per game and per sport); (2) any code in E_title absent from E_state or E_ticker remains
state_vs_title_mismatch / title_vs_ticker_mismatch (REFUSED); (3) an EMPTY E_title stays title_evidence_absent /
title_team_names_unmapped -> UNATTESTABLE or REFUSED as today, never attested by absence; (4) the swap-detection test
constructs two games with swapped game_keys and shows that partial titles still refuse the swapped pair when the one
resolved code contradicts the state; (5) the memo records the fix-1b real re-run above verbatim and the fix-1c real re-run
(orchestrator) must ATTEST all six with MIACHC title_partial true, title_codes_unresolved ['CHC'].

AMENDMENT 3 (2026-09-23 17:0xZ; binding; from round 1 -- BOTH Opus 5.5 tiers ACCEPT WITH CORRECTIONS on the same items; every
item MEASURED on constructs; codex was out of quota so both tiers ran on Opus with different briefs). (1) A DOUBLEHEADER IS NOT
A SWAP: two correctly keyed entries with the same team set on one day (both BAL/TOR, titles 'Toronto vs Baltimore') were
REFUSED schedule_identity_swapped on both (:230-236) because the swap test also admits entries whose own reason is None
(already attested) and identical team sets satisfy the cross condition trivially; CHANGE item 3 had the same hole. RULING:
the swap detector considers ONLY entries that already fail their own pairwise check (None is dropped from the admitted
reasons); an unswapped doubleheader attests both games; a doubleheader construct asserts ATTESTED 2; the memo's NOT VERIFIED
names that team evidence cannot detect a swap WITHIN a doubleheader (the ticker's time token would be the discriminator; a
later row, not this one). (2) THE STATE ROW'S DATE IS THE VENUE-LOCAL DATE (local_state_capture_dates.py:105-116) while the
entry's day was read as the UTC date of scheduled_start (:135-137): a start at 2026-09-23T02:10Z (22:10 ET) with state rows
dated 2026-09-22 gave UNATTESTABLE state_teams_absent -- every game starting at or after 20:00 ET would be unattestable.
RULING: state rows are located by game_key on EITHER the UTC date or the venue-local date of the start (both candidates,
deduplicated, conflicts counted), never one; the 02:10Z construct attests. (3) PROSE WITHOUT A TEAM NAME IS ABSENT, NOT
UNMAPPED: 'Will the game go to extra innings' was REFUSED title_team_names_unmapped through the closed NON_NAMES word list
(:41-43, :178-180). RULING: the NON_NAMES heuristic is retired; a text with no resolved code and no ambiguous-city hit is
title_evidence_absent (UNATTESTABLE), and title_team_names_unmapped is reserved for a text that hit a name-table token which
resolved to nothing. (4) A malformed state date yields the named reason invalid_state_date, never the library's message text
(:89 wrote 'month must be in 1..12' into record_counts). (5) The memo records the fix-1c real re-run verbatim (ATTESTED 6 /
REFUSED 0 / UNATTESTABLE 0; MIACHC title_partial true, title_codes_unresolved ['CHC']; title_city_ambiguous 2600;
title_tokens_ignored 16520; ignored_record_type 127201) and the fix-1d real re-run by the orchestrator; the 2026-09-23
schedule's run is recorded when its games have played and stays NOT VERIFIED until then. NOTES kept as notes: upper-case prose
that happens to be a code ('WAS', 'MIN') can only refuse, never attest; a partial E_ticker is refused while a partial title is
admitted (asymmetric, fails closed); invalid_json rows are counted and never refuse a game; no directory fsync after replace.
