GAP S404 | sport all captured | worktree harness-h65 (master-based) | log opus_s404_bridge_partial_metadata
# The native bridge treats a missing scheduled start as a linkage CONFLICT (found on the real state archive 2026-09-22)

SINGLE PROBLEM: scripts/platformkit/execution/forward_capture_bridge.py _links (its lines 50-84) groups state rows by (sport,
game_key) and requires ONE metadata tuple (date, home_abbr, away_abbr, scheduled_start_utc) per key; a second tuple is
conflicting_state_linkage and the game is LINKAGE_INVALID. MEASURED on data/cache/ingame_books_local/state/mlb/2026-09-22.jsonl
(4924 rows, real archive, 16:3xZ): every scheduled game carries 192 rows with scheduled_start_utc None and 2 rows with the start
(the landed state writer fills the field only from discovery payloads; row S393 fixes the writer), so the daily qualification
(S390 candidate) reported conflicting_state_linkage 17 and LINKAGE_INVALID for all six scheduled games. A missing value is partial
evidence, not a conflict: only two DIFFERENT non-missing values disagree.

BINDING BEFORE-CONDITION: quote from master forward_capture_bridge.py lines 50-84 and game_market_link.link_game (its
scheduled_start_utc handling for multiple candidate events), then reproduce the measured conflict on a two-row construct (one row
with the start, one without) through _links and quote the counts.

CHANGE (owned files: forward_capture_bridge.py (MODIFIED, minimal), tests/platformkit/execution/test_forward_capture_bridge.py
(MODIFIED, additive), memo; the qualification module and its frozen constants are NOT touched):
1. Per (sport, game_key) the metadata is reduced per FIELD: for each of date, home_abbr, away_abbr, scheduled_start_utc the set of
   NON-MISSING values (None and empty strings are missing) must have at most one element; two different non-missing values are
   conflicting_state_linkage (counted, the game excluded as today); a field with no non-missing value stays missing and link_game
   receives None for it (link_game already handles a missing start: a single candidate event links without it, multiple candidates
   refuse with ambiguous_multiple_kalshi_events). The counts gain state_rows_missing_start (strict int) so the shortfall stays
   visible.
2. Tests: the measured two-row construct now links (counts: conflicting_state_linkage 0, state_rows_missing_start 1); two different
   non-missing starts still conflict; two different home codes still conflict; a key with no start at all links when the Kalshi
   index has one event for the date and teams; the landed tests pass unchanged.
3. Memo docs/evidence/harness/S404_bridge_partial_metadata_2026-09-22.md.

CONTROLS: construct tests only; no network; no real archive run by the builder; the orchestrator re-runs the S390 candidate on the
real archives after the fix. ACCEPTANCE: per-file tests pass; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED.

AMENDMENT 1 (2026-09-22 17:1xZ; binding; from the orchestrator's real-archive run of the candidate through the landed replay CLI).
The per-field reduction works (conflicting_state_linkage 0; state_rows_missing_start 4891), but every scheduled game is STILL
LINKAGE_INVALID: the directional linker refuses with missing_directional_team_evidence 19 because the Kalshi book rows carry no
home / away team evidence (the index derives none from orderbook snapshots), so link_game cannot match a state game to an event.
The schedule entries now carry game_key (the state capture's key) beside game_id (the Kalshi event ticker) and ticker. CHANGE item
4 (additive): when a schedule entry carries a non-empty game_key, the bridge links by EXACT IDENTITY -- the state rows grouped under
(sport, game_key) must exist (else LINKAGE_INVALID with reason state_key_absent) and book rows whose event_ticker equals game_id
and whose ticker set contains the entry's ticker must exist (else LINKAGE_INVALID with reason book_event_absent); the directional
link_game path is used ONLY for entries without game_key (legacy) and its refusal reasons stay counted. When both a keyed identity
and the directional linker are available and DISAGREE (the keyed state rows link to a different event), the entry is
LINKAGE_INVALID with reason linkage_disagreement, counted. Tests: the real-shaped two-row construct plus book rows with no team
evidence now links through the key; a keyed entry whose game_key has no state rows fails state_key_absent; a keyed entry whose
game_id has no book rows fails book_event_absent; a legacy entry without game_key still goes through link_game; a disagreement
fails; the landed replay and qualification test files pass unchanged.
