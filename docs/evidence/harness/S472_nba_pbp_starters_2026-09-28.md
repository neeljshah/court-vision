# S472 FIX 1e - I2 verified; current E1/E2 accepted under AMENDMENT 2(a)
Machine: local Windows, C:/Users/neelj/nba-harness-h125. Evidence is local and read-only.
Initial build: only the new module, test file and memo were saved; integration and E1/E2 were unapplied.
FIX 1a integrated player_state and the two source lines. FIX 1b applies the authorized census/adapter integration; current results follow the historical FIX 1a record.
## Owner decisions (quoted)
> OWNER DECISIONS (orchestrator, 2026-09-26, binding): (1) NO extra live request. Inference from the play-by-play the poll already fetched stays the ONLY runtime path (S468 promised zero extra requests; cdn.nba.com is 403-blocked from this host). The boxscore is used ONLY as a read-only truth oracle inside the evidence run (E2), never at poll time, never imported by a capture path, never read by a test. (2) E2 GATES the landing on the period-1 starter match against the boxscore starter flags: any difference on either side rejects the row. A per-player game-clock minutes mismatch beyond one second does NOT block the landing; it is recorded per player and refuses that player's inferred minutes BY NAME (inferred_minutes_mismatch) in the memo's evidence table, and the row states how many players match (k of M). (3) One WNBA game is enough for this construct-only row. The future NBA-REGISTRY-E row must NOT read player_state.lineup_inferred until the orchestrator's first-live-night census of the 2026-27 season has compared it against that night's boxscore.
## BINDING BEFORE-CONDITION
The following output was captured before coding, at HEAD/master 8f1753ebd0f3414177f83817b2de5889287c4393:
```text
BINDING BEFORE-CONDITION
scripts.platformkit.ingame.nba_pbp_source.instant(value: 'object') -> 'Decimal | None'
scripts.platformkit.ingame.nba_pbp_source._integer(value: 'object', low: 'int', high: 'int') -> 'bool'
scripts.platformkit.ingame.nba_pbp_source._state(actions: 'object', teams: 'tuple[int, int]', receipt: 'dict', drop: 'Callable') -> 'tuple'
scripts.platformkit.ingame.nba_pbp_player_state._refused(reason: 'str', dropped: 'Optional[dict]' = None) -> 'dict'
scripts.platformkit.ingame.nba_pbp_player_state.player_block(actions: 'object', teams: 'tuple', receipt: 'object') -> 'dict'
scripts.platformkit.ingame.nba_pbp_player_census.census(rows: 'list') -> 'dict'
scripts.platformkit.ingame.nba_pbp_registry_adapter.player_coverage(tick: 'dict') -> 'Decimal | None'
scripts.platformkit.ingame.nba_pbp_registry_adapter.score_vector(tick: 'dict', config_version: 'str') -> 'dict'
FOUL_TYPES=('personal',)
PID_BOUNDS=(1, 9999999999)
ORDER_BOUNDS=(0, 1000000000)
starters_module_exists=False
nba_pbp_player_state.py:234:     period_current = [(s, a) for s, a in by_action if a['period'] == period]
nba_pbp_player_state.py:235:     incomplete = not any(a.get('actionType') == 'period' for _, a in period_current)
nba_pbp_player_state.py:236:     on: list = [set(), set()]
nba_pbp_player_state.py:237:     bad = [False, False]
nba_pbp_player_state.py:238:     first_in: list = [dict(), dict()]
nba_pbp_player_state.py:239:     last_in: list = [dict(), dict()]
nba_pbp_player_state.py:240:     for _, action in period_current:
nba_pbp_player_state.py:241:         if action.get('actionType') != 'substitution':
nba_pbp_player_state.py:242:             continue
nba_pbp_player_state.py:243:         team = action.get('teamId')
nba_pbp_player_state.py:244:         if not (_integer(team, 1, 9999999999) and team in teams):
nba_pbp_player_state.py:245:             bad[0] = bad[1] = True  # an unattributable team taints both sides' lineups.
nba_pbp_player_state.py:246:     for side_idx in (0, 1):
nba_pbp_player_state.py:247:         side_actions = [(s, a) for s, a in period_current if a.get('actionType') == 'substitution'
nba_pbp_player_state.py:248:                          and a.get('teamId') == teams[side_idx]]
nba_pbp_player_state.py:249:         order_ok = [_integer(a.get('orderNumber'), _ORDER_LOW, _ORDER_HIGH) for _, a in side_actions]
nba_pbp_player_state.py:250:         if any(order_ok) and not all(order_ok):
nba_pbp_player_state.py:251:             bad[side_idx] = True  # a mix of the two scales on one side -- refuse, never guess.
nba_pbp_player_state.py:252:         key = (lambda pair: pair[1]['orderNumber']) if all(order_ok) else (lambda pair: pair[1]['actionNumber'])
nba_pbp_player_state.py:253:         for stamp, action in sorted(side_actions, key=key):
nba_pbp_player_state.py:254:             pid, subtype = action.get('personId'), action.get('subType')
nba_pbp_player_state.py:255:             if not _integer(pid, _PID_LOW, _PID_HIGH) or subtype not in ('in', 'out'):
nba_pbp_player_state.py:256:                 bad[side_idx] = True
nba_pbp_player_state.py:257:                 continue
nba_pbp_player_state.py:258:             if subtype == 'in':
nba_pbp_player_state.py:259:                 if pid in on[side_idx] or len(on[side_idx]) >= 5:
nba_pbp_player_state.py:260:                     bad[side_idx] = True
nba_pbp_player_state.py:261:                 else:
nba_pbp_player_state.py:262:                     on[side_idx].add(pid)
nba_pbp_player_state.py:263:                     first_in[side_idx].setdefault(pid, stamp)
nba_pbp_player_state.py:264:                     last_in[side_idx][pid] = stamp
nba_pbp_player_state.py:265:             else:
nba_pbp_player_state.py:266:                 on[side_idx].discard(pid)
nba_pbp_player_state.py:267:     resolved = [len(on[i]) == 5 and not bad[i] for i in (0, 1)]
nba_pbp_source.py:259:                         player_state = nba_pbp_player_state.player_block(payload.get('actions'), teams, own)
nba_pbp_source.py:260:                     except Exception as exc:
nba_pbp_source.py:261:                         # FIX 1f (round 5 CORRECTION, both tiers): forward the real exception to
nba_pbp_source.py:262:                         # on_error, the way the neighbouring game_invalid path does -- drop()
nba_pbp_source.py:263:                         # alone synthesises a ValueError('player_block_error') and loses it.
nba_pbp_source.py:264:                         src.report(get, 'nba_pbp', 'player_block_error', exc, on_error)
nba_pbp_source.py:265:                         player_state = nba_pbp_player_state._refused('player_block_error')
nba_pbp_player_state.py:124:     if not eligible:
nba_pbp_player_state.py:125:         return dict(refused=None, dropped=dict(dropped), action_type_unconfirmed=0,
nba_pbp_player_state.py:126:                     player_history_incomplete=False, score_attribution_unproven=False,
nba_pbp_player_state.py:127:                     score_correction_unresolved=False, players=dict(_EMPTY_PLAYERS),
nba_pbp_player_state.py:128:                     period=None, last_action_number=None, eligible_order=())
state_sha256=c50cb658d2d0e6442a7dc3658dc1d6c953f5181afcce320e37ea0eb7c1512408
capture_sha256=db3fa46233ddf802958378001f4145cc7e52a7735c23e02a6233e258247c97dc
construct_first_appearances_statuses=['lineup_unresolved', 'lineup_unresolved', 'lineup_unresolved', 'lineup_unresolved', 'lineup_unresolved']
```
Additional imported signatures read before use: parse_venue_time(value: object) -> float | None; register_block(**attrs: Any) -> dict.
The helper instant validates through parse_venue_time and preserves all nine fractional digits. side_lineups imports the four quoted bounds.
Read-only seal audit: execution/registry_scorer_e_config.py IMPLEMENTATION_FILES contains no NBA module; the NBA adapter remains unsealed.
## FIX 1a
Applied exactly the memo's player_state integration and source lines 259/265 after rechecking spec CHANGE items 1-3.
player_block and _refused gain keyword-only infer_starters=False. All enabled return paths carry both inference keys; side_lineups supplies lineups and inferred-starter timing. Poll success and error paths pass True.
The user's two-file restriction leaves spec items 4/5 (census/adapter) pending authorization; their exact unapplied diff is below. No existing test changed.
Saved new test: 30 passed, 6 failed (previous build: 1 passed, 35 failed). Failures are C1 player_coverage, C11 census keys, C12 adapter encoding, and three malformed-metadata census variants.
Acceptance counts remain separate: constructs 13/16; full invariants 2/3 (I2 partial); evidence 1/1. Three saved invariant tests passed, but I2's full literal enumeration is absent.
C1/C11/C12 FAIL; C2-C10/C13-C16 PASS. No test or evidence threshold changed.
Every listed file ran separately: python -m pytest <one file> -q -p no:cacheprovider.
| Test file (under tests/platformkit/) | Passed | Failed |
| --- | ---: | ---: |
| ingame/test_nba_pbp_starters.py | 30 | 6 |
| ingame/test_nba_pbp_player_state.py | 20 | 0 |
| ingame/test_nba_pbp_player_state_1b.py | 13 | 0 |
| ingame/test_nba_pbp_player_state_1c.py | 9 | 0 |
| ingame/test_nba_pbp_player_state_1d.py | 5 | 0 |
| ingame/test_nba_pbp_player_state_1e.py | 4 | 0 |
| ingame/test_nba_pbp_player_state_1f.py | 4 | 0 |
| ingame/test_nba_pbp_source.py | 68 | 0 |
| ingame/test_nba_pbp_source_1c.py | 20 | 0 |
| test_loc_rail_scope.py | 1 | 0 |
All nine regression files kept their listed counts (144 passes). The full saved S472 file does not yet pass.
Additional read-only construct check: poll additive paths 2/2 PASS (success and boom error, original RuntimeError retained).
Independent scoped code review found no blocking defect in the two-file integration; it did not grant full-row acceptance.
## EVIDENCE RUN (E1 + E2; never a test)
The exact command below ran locally twice, read-only; both executions exited 0 with matching specified metrics. No runtime boxscore reader was added.
```text
python -m scripts.platformkit.ingame.nba_pbp_starters --probe data/domains/wnba/cdn_backfill/1012600001/playbyplay.json --home 1611661313 --away 1611661325 --boxscore data/domains/wnba/cdn_backfill/1012600001/boxscore.json
```
Fixture identities were rechecked before the first run; the full output records both absolute paths, byte sizes and SHA256 values. JSON has no image resolution.
```json
{"E1": {"after": {"inferred_starter": 6, "lineup_unresolved": 13, "present": 4}, "before": {"lineup_unresolved": 23}, "cutoffs": 388, "first_events": {"act": 29, "in": 31, "out": 11}, "identity": {"bytes": 405353, "path": "C:\\Users\\neelj\\nba-harness-h125\\data\\domains\\wnba\\cdn_backfill\\1012600001\\playbyplay.json", "sha256": "883a0071362970768bf66ae4cefcdb90bd05721685aebe27dc049ca6fefffa91"}, "legacy_drops": {"foul_invalid": 1083, "future_action": 103723, "invalid_possession_team_id": 1, "invalid_score_away": 388, "invalid_score_home": 388, "lineup_conflict": 24}, "lineup_inferred": {"away": ["1628278", "1641672", "1642799", "1642815", "1643499"], "home": ["1629566", "1630993", "1642328", "1643523", "1643524"]}, "periods": {"1": {"away": {"act": 5, "in": 3}, "home": {"act": 5, "in": 4}}, "2": {"away": {"act": 2, "in": 4, "out": 3}, "home": {"act": 2, "in": 4, "out": 3}}, "3": {"away": {"act": 4, "in": 7, "out": 1}, "home": {"act": 3, "in": 4, "out": 2}}, "4": {"away": {"act": 4, "in": 3, "out": 1}, "home": {"act": 4, "in": 2, "out": 1}}}, "sweep": {"away:agreement": 167, "away:legacy_resolved": 167, "away:resolved": 304, "away:starters_unseen": 84, "home:agreement": 105, "home:legacy_resolved": 105, "home:resolved": 314, "home:starters_unseen": 74}, "technical_counterfactual": {"lineup_inference": {"away": {"marker_agree": 0, "marker_unassigned": 0, "mode": "inferred", "person_id": null, "reason": null}, "home": {"marker_agree": 0, "marker_unassigned": 0, "mode": "inferred", "person_id": "1627666", "reason": "starter_overflow"}}, "lineup_inferred": {"away": ["1628278", "1641672", "1642799", "1642815", "1643499"], "home": null}}}, "E2": {"M": 23, "fields": ["personId", "starter", "statistics.minutes"], "gate": "ACCEPT", "identity": {"bytes": 39200, "path": "C:\\Users\\neelj\\nba-harness-h125\\data\\domains\\wnba\\cdn_backfill\\1012600001\\boxscore.json", "sha256": "dea8da6213c94d04b4f691f41209e5078031ce6528a27e96b4e3a839f4280cc7"}, "k": 23, "minutes_format": "PT<minutes>M<seconds>S", "players": {"1627668": {"boxscore_minutes": "PT11M45.00S", "inferred_seconds": "705.00", "result": "match"}, "1627673": {"boxscore_minutes": "PT13M23.00S", "inferred_seconds": "803.00", "result": "match"}, "1628278": {"boxscore_minutes": "PT22M10.60S", "inferred_seconds": "1330.60", "result": "match"}, "1628881": {"boxscore_minutes": "PT21M21.00S", "inferred_seconds": "1281.00", "result": "match"}, "1628899": {"boxscore_minutes": "PT17M39.00S", "inferred_seconds": "1059.00", "result": "match"}, "1628909": {"boxscore_minutes": "PT17M10.00S", "inferred_seconds": "1030.00", "result": "match"}, "1629477": {"boxscore_minutes": "PT14M42.20S", "inferred_seconds": "882.20", "result": "match"}, "1629482": {"boxscore_minutes": "PT14M28.00S", "inferred_seconds": "868.00", "result": "match"}, "1629566": {"boxscore_minutes": "PT22M29.00S", "inferred_seconds": "1349.00", "result": "match"}, "1630993": {"boxscore_minutes": "PT29M41.00S", "inferred_seconds": "1781.00", "result": "match"}, "1641672": {"boxscore_minutes": "PT12M53.00S", "inferred_seconds": "773.00", "result": "match"}, "1642286": {"boxscore_minutes": "PT16M39.40S", "inferred_seconds": "999.40", "result": "match"}, "1642328": {"boxscore_minutes": "PT13M21.40S", "inferred_seconds": "801.40", "result": "match"}, "1642799": {"boxscore_minutes": "PT10M31.40S", "inferred_seconds": "631.40", "result": "match"}, "1642815": {"boxscore_minutes": "PT24M44.00S", "inferred_seconds": "1484.00", "result": "match"}, "1643433": {"boxscore_minutes": "PT17M32.20S", "inferred_seconds": "1052.20", "result": "match"}, "1643495": {"boxscore_minutes": "PT10M24.00S", "inferred_seconds": "624.00", "result": "match"}, "1643499": {"boxscore_minutes": "PT14M27.40S", "inferred_seconds": "867.40", "result": "match"}, "1643523": {"boxscore_minutes": "PT14M25.00S", "inferred_seconds": "865.00", "result": "match"}, "1643524": {"boxscore_minutes": "PT24M02.80S", "inferred_seconds": "1442.80", "result": "match"}, "1643525": {"boxscore_minutes": "PT22M45.60S", "inferred_seconds": "1365.60", "result": "match"}, "203822": {"boxscore_minutes": "PT21M02.00S", "inferred_seconds": "1262.00", "result": "match"}, "204335": {"boxscore_minutes": "PT12M23.00S", "inferred_seconds": "743.00", "result": "match"}}, "starters": {"away": {"boxscore": ["1628881", "1628899", "1628909", "1629482", "1642286"], "equal": true, "inferred": ["1628881", "1628899", "1628909", "1629482", "1642286"]}, "home": {"boxscore": ["1627668", "1627673", "1629477", "203822", "204335"], "equal": true, "inferred": ["1627668", "1627673", "1629477", "203822", "204335"]}}}}
```
E1: 388/388 cutoffs retained; resolved home 314, away 304; starters_unseen 74/84; inference refusals 0; legacy agreement 105/105 and 167/167. First events act/out/in = 29/11/31. Technical counterfactual refuses period-4 home starter_overflow (1627666).
E2(i): period-1 starter sets equal on both sides (sets quoted above); gate ACCEPT. E2(ii): 23 of 23 players within one second; zero inferred_minutes_mismatch refusals. This checks game-clock lineups, not runtime wall-clock minutes_so_far.
| personId | Inferred game-clock seconds | Boxscore statistics.minutes (PT format) | Result |
| --- | ---: | --- | --- |
| 1627668 | 705.00 | PT11M45.00S | match |
| 1627673 | 803.00 | PT13M23.00S | match |
| 1628278 | 1330.60 | PT22M10.60S | match |
| 1628881 | 1281.00 | PT21M21.00S | match |
| 1628899 | 1059.00 | PT17M39.00S | match |
| 1628909 | 1030.00 | PT17M10.00S | match |
| 1629477 | 882.20 | PT14M42.20S | match |
| 1629482 | 868.00 | PT14M28.00S | match |
| 1629566 | 1349.00 | PT22M29.00S | match |
| 1630993 | 1781.00 | PT29M41.00S | match |
| 1641672 | 773.00 | PT12M53.00S | match |
| 1642286 | 999.40 | PT16M39.40S | match |
| 1642328 | 801.40 | PT13M21.40S | match |
| 1642799 | 631.40 | PT10M31.40S | match |
| 1642815 | 1484.00 | PT24M44.00S | match |
| 1643433 | 1052.20 | PT17M32.20S | match |
| 1643495 | 624.00 | PT10M24.00S | match |
| 1643499 | 867.40 | PT14M27.40S | match |
| 1643523 | 865.00 | PT14M25.00S | match |
| 1643524 | 1442.80 | PT24M02.80S | match |
| 1643525 | 1365.60 | PT22M45.60S | match |
| 203822 | 1262.00 | PT21M02.00S | match |
| 204335 | 743.00 | PT12M23.00S | match |
## FIX 1b
The orchestrator corrected FIX 1a's two-file ownership restriction: S472 CHANGE owns FOUR modified files, including census and adapter. Rechecked items 4/5 against the spec and applied the previously proposed edits. The corrected ownership takes precedence over the earlier dispatch; edits stay in this worktree.
Before this fix, the saved starter file reproduced 30 passes and six failures: C1 coverage, C11 census keys, C12 adapter encoding, and three malformed-metadata variants. After: 36 passes, zero failures, with the saved test file unchanged.
Census now counts inferred_starter and its separate inferred-minutes bucket, per-side reasons before refused rows continue, absent metadata, and disagreements. Adapter emits tagged inferred minutes, counts inferred starters resolved, forwards named reasons, and adds the eleven refusal names. Existing points and early block-refusal behavior are preserved.
Scoped review caught a heterogeneous-list sorting crash in the proposed disagreement counter. The comparison now sorts with key=repr; four new constructs cover reordered IDs, mixed JSON values, and nested malformed values while asserting all old counters stay equal.
Every command ran one file at a time: python -m pytest <one file> -q -p no:cacheprovider.
| Test file (under tests/platformkit/) | Passed | Failed |
| --- | ---: | ---: |
| ingame/test_nba_pbp_starters.py | 36 | 0 |
| ingame/test_nba_pbp_starters_census.py | 4 | 0 |
| ingame/test_nba_pbp_player_state.py | 20 | 0 |
| ingame/test_nba_pbp_player_state_1b.py | 13 | 0 |
| ingame/test_nba_pbp_player_state_1c.py | 9 | 0 |
| ingame/test_nba_pbp_player_state_1d.py | 5 | 0 |
| ingame/test_nba_pbp_player_state_1e.py | 4 | 0 |
| ingame/test_nba_pbp_player_state_1f.py | 4 | 0 |
| ingame/test_nba_pbp_source.py | 68 | 0 |
| ingame/test_nba_pbp_source_1c.py | 20 | 0 |
| test_loc_rail_scope.py | 1 | 0 |
Total: 184 passes across eleven separate files, zero failures; existing regression counts remain 144. The census/adapter suite inventory found no additional existing suites beyond those listed. Affected suites were rerun after the malformed-list correction.
Acceptance counts stay separate: constructs 16/16; full invariants 2/3 (I2 partial, although all three saved invariant tests pass); evidence 1/1 from FIX 1a, not rerun in FIX 1b. Four supplementary census regressions do not enlarge the spec's construct denominator.
E1/E2 were not rerun: only census/adapter code changed this round, and the probe imports/calls neither. Starter inference, player_state, source, saved starter tests, and the probe retain their FIX 1a hashes. The prior evidence output above is historical, not a new measurement.
Read-only seal/reader check: execution/registry_scorer_e_config.py IMPLEMENTATION_FILES still has no NBA module; no production census/adapter callers were found under scripts/platformkit. Source still differs from master only at lines 259/265; git diff --check passed.
## FIX 1b historical identity and preflight
- NEW scripts/platformkit/ingame/nba_pbp_starters.py: 15948 bytes; 286 lines; SHA256 57b864b128fd8081674e7f47f655ebad3dd31f5a7d2e6385534e3a55b408c744.
- MODIFIED scripts/platformkit/ingame/nba_pbp_player_state.py: 18800 bytes; 279 lines; SHA256 a9e855ec4841c1b2e1f5da4175f2fdb564de4d0c07fcdd5addb5f85e27c09f60.
- MODIFIED scripts/platformkit/ingame/nba_pbp_source.py: 15765 bytes; 271 lines; SHA256 befb9a3cb8eab1a2583d260b167b0ec2f558d3810df4f353535dbc17db136371.
- MODIFIED scripts/platformkit/ingame/nba_pbp_player_census.py: 11353 bytes; 213 lines; SHA256 d6c1347808f5d399a63d4e30c430bca6536aba4479aaa290b1617f6c1b2a5eb2.
- MODIFIED scripts/platformkit/ingame/nba_pbp_registry_adapter.py: 7586 bytes; 128 lines; SHA256 af332350827114b5e21818514fde70996883545e8e47c0bbd630ecd68ecf5bfe.
- NEW tests/platformkit/ingame/test_nba_pbp_starters.py: 14346 bytes; 299 lines; SHA256 08595fa8f22ac17177afbbc0bdf09afff59ea757987151ef1fedfba019f88bff.
- NEW tests/platformkit/ingame/test_nba_pbp_starters_census.py: 1180 bytes; 26 lines; SHA256 9c65471cf73f1ac11b242c5110af7e6610919c4950135ee9864197efc61caa31.
- Unchanged scripts/platformkit/ingame/local_state_capture.py: 300 lines; SHA256 db3fa46233ddf802958378001f4145cc7e52a7735c23e02a6233e258247c97dc.
Frozen _state function, LF-normalized SHA256 on current master: 4591ede56004da06a2628f0c25ea3bb39a827f14bc975f5414582a6146fac2b9.
Frozen _state function, LF-normalized SHA256 on candidate: 4591ede56004da06a2628f0c25ea3bb39a827f14bc975f5414582a6146fac2b9.
EQUAL: the two full SHA256 values match. FIX 1b used historical baseline 6dbb2c3172e1a9cd54a0ca63f37fa51a25ece745; current FIX 1c provenance is recorded below.
Preflight command: python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/nba_pbp_starters.py scripts/platformkit/ingame/nba_pbp_player_state.py scripts/platformkit/ingame/nba_pbp_source.py scripts/platformkit/ingame/nba_pbp_player_census.py scripts/platformkit/ingame/nba_pbp_registry_adapter.py tests/platformkit/ingame/test_nba_pbp_starters.py tests/platformkit/ingame/test_nba_pbp_starters_census.py docs/evidence/harness/S472_nba_pbp_starters_2026-09-28.md --base master --spec docs/evidence/tracking/specs/S472_spec.md
FIX 1b preflight: 9 PASS, 0 FAIL across all eight owned paths. Scoped final review: PASS after the malformed-list correction.
A9 final-edit identity check: both fixture byte sizes and SHA256 values still EQUAL the full identities in the historical evidence output above; only hashes were checked, not E1/E2 rerun.
Memo line count (wc -l equivalent, newline bytes): 181.
Only census, adapter, the new supplementary test and this memo changed in FIX 1b. All existing test contents and the saved starter test remain unchanged. No flags, registry, capture cadence, or seal changed.
SHA: NOT CREATED (sandbox); files ready for lane_commit
## FIX 1c
The binding verdict was read first, followed by every S472 AMENDMENT 1 clause. Work stayed in C:/Users/neelj/nba-harness-h125; no other worktree, real archive, network, pod, or live request was used.
Findings and exact fixes (the two tiers repeat I2 and test ownership):
- Tier 1 BLOCKING 1 / tier 2 CORRECTION 4, I2: replace the single-literal baseline with recorded master outputs for every S468 construct input; compare player_block with inference off, _state, and _refused. Pin the exact source changes at 259/265 and compare capture records, including their complete key sets and values, with opt-in absent.
- Tier 1 BLOCKING 2 / tier 2 NOTE 9: C8 now asserts marker_unassigned exactly (0 for known starters, 1 on each side for a participant unseen on either side); C11 compares the entire dictionary of existing census fields, including nested field counters.
- Tier 1 CORRECTION 3 / tier 2 CORRECTION 3: AMENDMENT 1(e) already authorizes both owned test files and the JSON fixture. Preserve the four correct supplementary census cases; the split stays within 300 lines.
- Tier 1 CORRECTION 4: replace the stale current-master statement with the full FIX 1c provenance below. The externally advancing master ref does not change the owned baseline module blobs.
- Tier 2 CORRECTION 1 / AMENDMENT 1(a): declared mode silently discards an off-court OUT and bypasses acted_off_court. Two C5 regressions compare every player record with inference off, assert present, and repeat in reversed input order.
- Tier 2 CORRECTION 2 / AMENDMENT 1(b): delete the four lines copying inference refusals into dropped. Overflow and unattributable-team regressions assert dropped remains exactly {} as on S468.
- AMENDMENT 1(f) / tier 2 NOTE 8: move _load, _boxcheck and the evidence CLI into nba_pbp_starters_evidence.py; runtime nba_pbp_starters.py contains inference only. The subprocess import regression proves the evidence module is absent, and runtime has no reader or main entry.
- AMENDMENT 1(g) / tier 2 NOTEs 5-7: retain the adjudicated unassigned-marker tally and duplicate-order refusal (existing reversed-order regression); select the final period explicitly from each action for the technical counterfactual, removing reliance on leftover current. An AST regression pins that expression.
Minimal reproductions BEFORE edits, quoted from this FIX 1c session:
```text
I2 literal_expected_assignments=1
C8 asserts_marker_unassigned=False
C11 all_existing_fields_compared=False
substitution: in_declared out_not_on_court person_id=9; inferred_status=lineup_unresolved S468_status=present
rebound: in_declared acted_off_court person_id=9; inferred_status=lineup_unresolved S468_status=present
starter_overflow dropped={'starter_overflow': 1} S468 dropped={}
evidence_reader_in_runtime=True
supplementary_test_owned_in_amendment=True
```
The first six lines reproduce defects. The last line resolves the ownership finding through the already-binding amendment. Initial master read was 3da3d215b394f3cb0e32b51a09f9f78dce6f2141, not the memo's historical baseline or the verifier's earlier master.
Same runtime reproductions AFTER the exact fixes:
```text
C8 asserts_marker_unassigned=True
C11 all_existing_fields_compared=True
substitution: in_declared reason=None person_id=None; inferred_status=present S468_status=present
rebound: in_declared reason=None person_id=None; inferred_status=present S468_status=present
starter_overflow dropped={} S468 dropped={}
evidence_reader_in_runtime=False
construct_ids=01,02,03,04,05,06,07,08,09,10,11,12,13,14,15,16
construct_coverage=16/16
```
Case-to-file map: tests/platformkit/ingame/test_nba_pbp_starters.py contains C1-C16 (test_c01 through test_c16), C5 declared-mode regressions, dropped regression, evidence-import/period regression, I1 recording oracle, I2 frozen _state hash, and I3 capture hash. test_nba_pbp_starters_census.py contains the four preserved census variants plus I2 per-suite master literals, exact source diff, capture identity, and poll success/error schema checks. fixtures/s472_i2_master_outputs.json stores literal input/output pairs and baseline provenance.
Fixture reproduction command (from this worktree; only constructs, one S468 test file per pytest invocation):
```text
python -m tests.platformkit.ingame.test_nba_pbp_starters_census --generate-master-fixture
```
The generator loads the pinned master blobs and records every exercised construct, including seeded variants, deduplicating identical inputs. No real fixture contributes to it.
Each verification command was python -m pytest <one file> -q -p no:cacheprovider, with PYTHONDONTWRITEBYTECODE=1. Per-file results:
| Test under tests/platformkit/ | Passed | Failed |
| --- | ---: | ---: |
| ingame/test_nba_pbp_starters.py | 40 | 0 |
| ingame/test_nba_pbp_starters_census.py | 15 | 0 |
| ingame/test_nba_pbp_player_state.py | 20 | 0 |
| ingame/test_nba_pbp_player_state_1b.py | 13 | 0 |
| ingame/test_nba_pbp_player_state_1c.py | 9 | 0 |
| ingame/test_nba_pbp_player_state_1d.py | 5 | 0 |
| ingame/test_nba_pbp_player_state_1e.py | 4 | 0 |
| ingame/test_nba_pbp_player_state_1f.py | 4 | 0 |
| ingame/test_nba_pbp_source.py | 68 | 0 |
| ingame/test_nba_pbp_source_1c.py | 20 | 0 |
| test_loc_rail_scope.py | 1 | 0 |
Historical FIX 1c tests: 199 passes, zero failures; constructs 16/16; invariants 3/3. Current E1/E2 accepted under AMENDMENT 2(a), as recorded in FIX 1d below.
CLI checks: python -m scripts.platformkit.ingame.nba_pbp_starters_evidence --help and python -m scripts.platformkit.ingame.nba_pbp_player_census --help each exit 0; the fixture generator --help also exits 0 (three CLI checks). No row --self-check flag exists; the saved regression files supply the construct checks.
Historical FIX 1c E1/E2 deferral is superseded by the accepted Opus rerun in AMENDMENT 2(a); command, identities and unchanged output are recorded in FIX 1d below.
## FIX 1c historical identities and preflight
Fixture generation master: f042695c23e1e32af4bd04f8ca66782c9f79e971. Final audit master: f79aaa7ab6bb3d8d9eafaecf545894b3612c5b6c.
The final master module hashes match the fixture baseline (asserted by I2); no owned baseline module changed from this worktree HEAD. The master ref advanced externally during the session.
I2 literal_inputs=2907; eight S468 files enumerated; all literal comparisons PASS.
- test_nba_pbp_player_state.py: 16 distinct inputs, 2 refused-block literals.
- test_nba_pbp_player_state_1b.py: 513 distinct inputs, 3 refused-block literals.
- test_nba_pbp_player_state_1c.py: 7 distinct inputs, 0 refused-block literals.
- test_nba_pbp_player_state_1d.py: 0 distinct inputs, 0 refused-block literals.
- test_nba_pbp_player_state_1e.py: 2304 distinct inputs, 3 refused-block literals.
- test_nba_pbp_player_state_1f.py: 1 distinct inputs, 1 refused-block literals.
- test_nba_pbp_source.py: 60 distinct inputs, 3 refused-block literals.
- test_nba_pbp_source_1c.py: 6 distinct inputs, 0 refused-block literals.
- scripts/platformkit/ingame/nba_pbp_starters.py: 8728 bytes; 165 lines; SHA256 217e065c8f6e465d0ad9df2f09c532f5e41d95e5042ef30a62175c49dd52426c.
- scripts/platformkit/ingame/nba_pbp_starters_evidence.py: 7973 bytes; 133 lines; SHA256 59f59502be2bdb774078be53f18151d7a02f044b258e2b4b0e4cb63586d565ae.
- scripts/platformkit/ingame/nba_pbp_player_state.py: 18621 bytes; 275 lines; SHA256 4b14031c7d11c2609e2daaf57463ee1c689abb80266122425aa6cc168a97160c.
- scripts/platformkit/ingame/nba_pbp_source.py: 15765 bytes; 271 lines; SHA256 befb9a3cb8eab1a2583d260b167b0ec2f558d3810df4f353535dbc17db136371.
- scripts/platformkit/ingame/nba_pbp_player_census.py: 11353 bytes; 213 lines; SHA256 d6c1347808f5d399a63d4e30c430bca6536aba4479aaa290b1617f6c1b2a5eb2.
- scripts/platformkit/ingame/nba_pbp_registry_adapter.py: 7586 bytes; 128 lines; SHA256 af332350827114b5e21818514fde70996883545e8e47c0bbd630ecd68ecf5bfe.
- tests/platformkit/ingame/test_nba_pbp_starters.py: 16089 bytes; 299 lines; SHA256 ba769b7b9b6e83b749479e19270e0527c5603338011652b76d7ae6a7b4157319.
- tests/platformkit/ingame/test_nba_pbp_starters_census.py: 11980 bytes; 249 lines; SHA256 46d92df7d7e610489376c43749e48aed0dadac28c4a6f5133d5f04b98deae373.
- tests/platformkit/ingame/fixtures/s472_i2_master_outputs.json: 5051883 bytes; 1 lines; SHA256 836f5af00272609b572d113cbdc2e5ffdf8b5efb754f814b9d8db7de62006bed.
Frozen _state LF-normalized SHA256 on final master: 4591ede56004da06a2628f0c25ea3bb39a827f14bc975f5414582a6146fac2b9.
Frozen _state LF-normalized SHA256 on candidate: 4591ede56004da06a2628f0c25ea3bb39a827f14bc975f5414582a6146fac2b9.
EQUAL: the two full SHA256 values match. Source diff contains exactly lines 259 and 265; git diff --check passes.
Unchanged capture SHA256: db3fa46233ddf802958378001f4145cc7e52a7735c23e02a6233e258247c97dc. No construct scratch directory was created in the worktree.
Final preflight command: python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/nba_pbp_starters.py scripts/platformkit/ingame/nba_pbp_starters_evidence.py scripts/platformkit/ingame/nba_pbp_player_state.py scripts/platformkit/ingame/nba_pbp_source.py scripts/platformkit/ingame/nba_pbp_player_census.py scripts/platformkit/ingame/nba_pbp_registry_adapter.py tests/platformkit/ingame/test_nba_pbp_starters.py tests/platformkit/ingame/test_nba_pbp_starters_census.py tests/platformkit/ingame/fixtures/s472_i2_master_outputs.json docs/evidence/harness/S472_nba_pbp_starters_2026-09-28.md --base master --spec docs/evidence/tracking/specs/S472_spec.md
Final preflight result: 9 PASS, 0 FAIL across all ten owned paths; the verdict file is excluded.
Memo final line count: 268.
FIX 1c audited owned construct inputs and code only; FIX 1d records the accepted verifier evidence identities.
SHA: NOT CREATED (sandbox); files ready for lane_commit
## FIX 1d
Only AMENDMENT 2(a)-(e) changed: census, adapter, both owned tests and this memo. No real archive, network, pod or scratch directory was used. Baseline master at audit: 5fbec07114673d019a58486c8568fb271e174a93.
- (a) Tier 1 BLOCKING 1 / tier 2 CORRECTION 2: the orchestrator accepts the Opus current-candidate E1/E2 rerun. The code changes here cannot move it: evidence calls source, player_state and starters, never census or adapter. No lane rerun was needed or performed.
- (b) Tier 1 BLOCKING 2: require explicit per-side reason and dictionary lineup_inferred; missing/malformed metadata counts block_refused. Nine shape regressions cover missing side/reason/lineups and malformed values.
- (c) Tier 2 CORRECTION 1: BASELINE_REF now defaults to the fixture's recorded master SHA, f042695c23e1e32af4bd04f8ca66782c9f79e971. Generator rev-parse is unchanged. The new landing simulation redirects moving-master blob reads to candidate bytes and checks the exact source diff and capture identity.
- (d) Tier 2 NOTEs 3/4, now binding: adapter reasons come only from unresolved players' sides; both-side cases use fixed home/away priority. Four parameterized regressions also reverse player insertion order and cover missing inferred minutes. C11 adds five declared-mode present players and asserts lower_bound remains zero.
- (e) Tier 1 CORRECTION 3 / tier 2 CORRECTION 2: title now FIX 1d, I2 verified, accepted current E1/E2 recorded, NOT VERIFIED remains last. Tier 1 NOTE 5: normal per-file pytest execution succeeded with writable system temporary storage.
Reproductions before edits (constructs, in-memory landing/mutation simulation and memo text), then the same checks after:
```text
empty home BEFORE {'home': {'resolved': 1}, 'away': {'starters_unseen': 1}}; AFTER {'home': {'block_refused': 1}, 'away': {'starters_unseen': 1}}
missing lineup BEFORE {'home': {'resolved': 1}, 'away': {'resolved': 1}}; AFTER {'home': {'block_refused': 1}, 'away': {'block_refused': 1}}
away refusal BEFORE {'refused': 'starters_unseen'}; AFTER {'refused': 'acted_off_court'}
post-landing source diff BEFORE FAIL: [] != [259, 265]; AFTER PASS: [259, 265]; capture identity PASS
C11 lower_bound mutant BEFORE SURVIVED; AFTER KILLED: 5 != 0; unmutated PASS
memo BEFORE '# S472 FIX 1b - integration tests PASS; full I2 remains NOT VERIFIED'; current evidence unverified=True
memo AFTER FIX 1d; I2 verified; current E1/E2 accepted under AMENDMENT 2(a)
```
Accepted Opus evidence command (read-only in the verifier session, exit 0): `python -m scripts.platformkit.ingame.nba_pbp_starters_evidence --probe data/domains/wnba/cdn_backfill/1012600001/playbyplay.json --home 1611661313 --away 1611661325 --boxscore data/domains/wnba/cdn_backfill/1012600001/boxscore.json`.
Verifier-reported identities: playbyplay.json 405353 bytes, SHA256 883a0071362970768bf66ae4cefcdb90bd05721685aebe27dc049ca6fefffa91; boxscore.json 39200 bytes, SHA256 dea8da6213c94d04b4f691f41209e5078031ce6528a27e96b4e3a839f4280cc7. Full paths are in the retained evidence JSON above; these are accepted verifier results, not new lane measurements.
Opus reported identical E1/E2 output with zero key differences from that JSON: 388 cutoffs, resolved home/away 314/304, starters_unseen 74/84, zero refusals, agreement 105/105 and 167/167. E2 starter sets EQUAL on both sides; 23 of 23 players match within one second. AMENDMENT 2(a) establishes current evidence acceptance.
Current per-file commands: `python -m pytest <one file> -q -p no:cacheprovider`, PYTHONDONTWRITEBYTECODE=1. In tests/platformkit/ingame/: test_nba_pbp_starters.py 40 PASS; test_nba_pbp_starters_census.py 29 PASS; test_nba_pbp_player_state.py 20 PASS; _1b 13 PASS; _1c 9 PASS; _1d 5 PASS; _1e 4 PASS; _1f 4 PASS; test_nba_pbp_source.py 68 PASS; test_nba_pbp_source_1c.py 20 PASS. tests/platformkit/test_loc_rail_scope.py 1 PASS. Total 213 PASS, zero failures; constructs 16/16 and invariants 3/3 (I2 verified).
CLI: `python -m <module> --help` exits 0 for scripts.platformkit.ingame.nba_pbp_starters_evidence, scripts.platformkit.ingame.nba_pbp_player_census, tests.platformkit.ingame.test_nba_pbp_starters_census (3/3). No row --self-check flag exists; construct files provide self-checks.
- FIX 1d identity scripts/platformkit/ingame/nba_pbp_starters.py: 8728 bytes; 165 lines; SHA256 217e065c8f6e465d0ad9df2f09c532f5e41d95e5042ef30a62175c49dd52426c. | - FIX 1d identity scripts/platformkit/ingame/nba_pbp_starters_evidence.py: 7973 bytes; 133 lines; SHA256 59f59502be2bdb774078be53f18151d7a02f044b258e2b4b0e4cb63586d565ae. | - FIX 1d identity scripts/platformkit/ingame/nba_pbp_player_state.py: 18621 bytes; 275 lines; SHA256 4b14031c7d11c2609e2daaf57463ee1c689abb80266122425aa6cc168a97160c. | - FIX 1d identity scripts/platformkit/ingame/nba_pbp_source.py: 15765 bytes; 271 lines; SHA256 befb9a3cb8eab1a2583d260b167b0ec2f558d3810df4f353535dbc17db136371. | - FIX 1d identity scripts/platformkit/ingame/nba_pbp_player_census.py: 11536 bytes; 216 lines; SHA256 4e9554664aa86b5d3b7ca3ec40834b434d97533c2a6bffed015abdca70838b68. | - FIX 1d identity scripts/platformkit/ingame/nba_pbp_registry_adapter.py: 7844 bytes; 131 lines; SHA256 55e5805ce365458ccb81526a55b62cab709fee21a4cf730b80da5dca6c5066b2. | - FIX 1d identity tests/platformkit/ingame/test_nba_pbp_starters.py: 15949 bytes; 299 lines; SHA256 8b7cdbcab0642074a2fd5468a93e6ccfd32dcba719110cda36d81291044a35eb. | - FIX 1d identity tests/platformkit/ingame/test_nba_pbp_starters_census.py: 14905 bytes; 290 lines; SHA256 acfd833f3b70e8a435be92bb3d845639c9204e93c411f4aa1e77da0ffff82714. | - FIX 1d identity tests/platformkit/ingame/fixtures/s472_i2_master_outputs.json: 5051883 bytes; 1 lines; SHA256 836f5af00272609b572d113cbdc2e5ffdf8b5efb754f814b9d8db7de62006bed.
FIX 1d preflight uses the ten-path command above, --base master and --spec docs/evidence/tracking/specs/S472_spec.md; verdict excluded. Result: 9 PASS, 0 FAIL. git diff --check passed; read-only scoped review found no blocking defects. All ten files are ASCII and at most 300 lines; this memo is 300 lines.
SHA: NOT CREATED (sandbox); files ready for lane_commit
## FIX 1e
Scope: AMENDMENT 3(a)-(b) only; census, owned census tests and memo. Local constructs only, no archive/network/pod/scratch. Existing assertions retained; blank lines and historical identity formatting compacted for the 300-line rail.
- Tier 1 BLOCKING 1 / 3(a): increment lineup_inference_absent only for a missing key; retain both block_refused counts for present malformed values. Three regressions assert both counters for missing/[]/string.
- Tier 2 NOTE 1 adopted by 3(b): reason=None requires a list on that inferred side, else block_refused. Twelve regressions cover both sides and string/None/dict/int/tuple/missing values. Other side remains resolved; existing named unresolved reasons stay unchanged.
Reproduction (a): [] BEFORE {'lineup_inference_absent': 1, 'lineup_inference_reasons': {'home': {'block_refused': 1}, 'away': {'block_refused': 1}}}, FAIL; AFTER absent=0, same refusal counts, PASS. Missing key: absent=1 and reasons={'home': {}, 'away': {}}, PASS before/after.
Reproduction (b): lineup_inferred={'home': 'x'}, home reason=None BEFORE home {'resolved': 1}, FAIL; AFTER home {'block_refused': 1}, PASS; away {'starters_unseen': 1} unchanged. Direct probes: 3 PASS. Regression file BEFORE 14 failed, 30 passed ('assert 1 == 0'; "{'resolved': 1} != {'block_refused': 1}"); AFTER 44 passed.
Commands: PYTHONDONTWRITEBYTECODE=1; python -m pytest <one file> -q -p no:cacheprovider, sequentially. In tests/platformkit/ingame/: test_nba_pbp_starters_census.py 45 PASS (orchestrator landing edit: Opus r4 case lineup_inference=None added); test_nba_pbp_starters.py 40 PASS; test_nba_pbp_player_state.py 20 PASS; _1b 13 PASS; _1c 9 PASS; _1d 5 PASS; _1f 4 PASS. Total 135 PASS, 0 failures after fix.
CLI: python -m <module> --help for scripts.platformkit.ingame.nba_pbp_starters_evidence, scripts.platformkit.ingame.nba_pbp_player_census, tests.platformkit.ingame.test_nba_pbp_starters_census: 3/3 exit 0. No --self-check option exists; construct tests provide checks.
E1/E2 not rerun: census is not an input to either evidence path; accepted verifier evidence above is unchanged.
FIX 1e identities: scripts/platformkit/ingame/nba_pbp_player_census.py: 11656 bytes; 218 lines; SHA256 48bb6d9777152ec8cd17b9811d8e87b7d90a77c504572dc1139d4d2af0127852 | tests/platformkit/ingame/test_nba_pbp_starters_census.py: 16048 bytes; 300 lines; SHA256 326fcbf74fa0541bc2f2affdd8f37ab3bad95b77922fc53db4b3fc6f15530249.
FIX 1e preflight: 9 PASS, 0 FAIL; ten-path command above, --base master --spec docs/evidence/tracking/specs/S472_spec.md, verdict excluded. SHA: NOT CREATED (sandbox); files ready for lane_commit
## NOT VERIFIED
No NBA-live starter shape, live startperiod jumpball, foul subtype spellings outside constructs, bench time accuracy, wall-clock proxy accuracy, or player id appearing on both sides was verified. E2 game-clock matching does not validate runtime wall-clock minutes. No live flag, capture opt-in, registry, or deployment was changed.
