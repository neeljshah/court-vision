# S433 NBA PBP state adapter - PREPARE candidate

LOCAL: all reads, implementation, construct tests and preflight ran in C:/Users/neelj/nba-harness-h89.
This row CHANGES NO VERDICT: no corpus, score, seal, charge or ledger row.
Before = 0: master has no nba_pbp source. Metric = passing enumerated construct cases.
Eye check = n/a (S-row); reproduction = the per-file commands below.

## BINDING BEFORE-CONDITION
Executed before coding: Python subprocess.run([git, show, master:<path>]) with the exact ranges below.
Verbatim stdout (each master_read_exit was 0):
```text
scripts/platformkit/ingame/local_state_capture.py master_read_exit= 0
22: _CADENCE = {'live': 7.0, 'pre': 60.0, 'delayed': 60.0, 'final': 300.0, 'none': 300.0}
23: def _build_row(sport: str, item: dict, request_start: str, response_end: str,
24:                capture_ts: str, last_state: dict) -> dict:
25:     raw = item.get('raw')
26:     receipt = item.get('receipt') or {}
27:     digest = receipt.get('raw_sha256')
28:     if digest is None and raw is not None:
29:         digest = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()
30:     key = sport + ':' + str(item['game_key'])
31:     canonical = (item.get('status'), deepcopy(item.get('state')))
32:     changed = None if key not in last_state else last_state[key] != canonical
33:     last_state[key] = canonical
34:     return dict(sport=sport, game_key=item['game_key'], request_start_utc=request_start,
35:                 response_end_utc=response_end, http_status=receipt.get('http_status', 200),
36:                 source_ts=item.get('source_ts'), state=item.get('state'), state_changed=changed,
37:                 date=item.get('date'), home_abbr=item.get('home_abbr'), away_abbr=item.get('away_abbr'),
38:                 status=item.get('status'), capture_ts=response_end, tick_start_ts=capture_ts,
39:                 raw_sha256=digest, capture_version=CAPTURE_VERSION,
40:                 scheduled_start_utc=item.get('scheduled_start_utc'), date_reason=item.get('date_reason'),
41:                 scheduled_start_source=item.get('scheduled_start_source', 'unavailable'))
87:     sports = list(src.SPORTS_AVAILABLE if sports is None else sports)
176:         if sport != 'mlb' and sport in src.POLLERS:
210:                 record = nba_state_enrichment.attach_enrichment(_build_row(sport, item, receipt['request_start_utc'], receipt['response_end_utc'],
211:                                     iso(now), previous), item, state.setdefault('last_enrichment', {}))
212:                 rows.append(record)
295:         if any(sport not in src.SPORTS_AVAILABLE for sport in args.sports):
296:             parser.error('--sports must contain only supported sports')
scripts/platformkit/ingame/local_state_capture_sources.py master_read_exit= 0
34: SPORTS_AVAILABLE: List[str] = (["mlb", "nba", "soccer"] + ["tennis"] * (_tennis_parse_scoreboard is not None)
35:                                + ["nfl", "ncaaf"] * (_nfl_normalize_scoreboard is not None))
36: def _receipt(get: GetFn) -> dict:
37:     return dict(getattr(get, "last_receipt", None) or {})
299: POLLERS = {"mlb": None, "nba": nba_poll, "soccer": soccer_poll, "tennis": tennis_poll,
300:            "nfl": nfl_poll, "ncaaf": ncaaf_poll}
scripts/platformkit/ingame/baseline_four_arm_features.py master_read_exit= 0
13: FEATURES = {
14:     'mlb': ('score_diff', 'inning', 'half', 'outs',
15:             *(f'base_{value}' for value in range(1, 8))),
16:     'soccer': ('score_diff', 'minute', 'home_red_cards', 'away_red_cards',
17:                'home_red_present', 'away_red_present'),
18:     'nba': ('score_diff', 'quarter', 'seconds_remaining'),
19:     'nfl': ('score_diff', 'period', 'game_seconds_remaining', 'down', 'distance',  # S413: no CORPORA
20:             'possession_is_home', 'home_timeouts', 'away_timeouts'),  # entry; yardline_100 undeclared
21: }
22: CORPORA = {
23:     name + suffix: sport
24:     for name, sport in [('mlb', 'mlb'), ('mlb_clean', 'mlb'),
25:                         ('soccer_intl', 'soccer'), ('nba', 'nba'),
26:                         ('nba_checkpoints', 'nba')]
27:     for suffix in ('', '_segmented', '_segmented_r3')
28: }
29: CORPORA['nba_checkpoints_r1'] = 'nba'
30: NBA_NUMERIC = ('possession', 'team_fouls_home', 'team_fouls_away',
scripts/platformkit/ingame/nba_state_enrichment.py master_read_exit= 0
30: def attach_enrichment(row: dict, item: dict, last_enrichment: dict) -> dict:
31:     """Return the row with the item's sibling block and its enrichment_changed flag.
32: 
33:     last_enrichment maps 'sport:game_key' to the previous accepted block content and
34:     is updated in place. A row without a block is returned unchanged.
35:     """
36:     block = item.get('state_enrichment')
37:     if block is None:
38:         return row
39:     block = deepcopy(block)
40:     block['enrichment_census']['receipt'] = receipt_census(row.get('response_end_utc'), block.get('receipt_utc'))
41:     key = row['sport'] + ':' + str(row['game_key'])
42:     content = deepcopy(_content(block))
43:     changed = None if key not in last_enrichment else last_enrichment[key] != content
44:     last_enrichment[key] = content
45:     return dict(row, state_enrichment=dict(block, enrichment_changed=changed))
SPEC S413: FEATURES declared, no CORPORA; duplicate identical once, conflicting all refused; invalid time before grouping.
SPEC S423: home side attested by NAMED source; refusals counted, never imputed.
```

S413 CHANGE 1: "No declared field is ever zero-filled -- a missing field is counted absent."
S413 AMENDMENT 1(a): "rows with IDENTICAL content under one key are counted ONCE".
S413 AMENDMENT 2(a): "invalid or missing receipt time is refused and counted BEFORE duplicate classification".
S423 CHANGE 2: "the home side is attested by a NAMED source"; "Named refusals, counted per game, never imputed".

## Premises and fixture identity
P1, domains/basketball_nba/cdn_probe.py: "VERDICT THIS WAVE: BLOCKED"; "Plain urllib: HTTPError 403"; "ALSO HTTPError 403".
P2, binding S433 spec: "NO COMMITTED NBA SAMPLE"; "actions live at payload['game']['actions'], NOT a top-level actions[]".
P3, binding S433 spec: "S414 lineups are ESPN athlete ids; CDN personId is the league person id; no crosswalk exists in the tree".
A9 author-reported archive identity: data/domains/wnba/cdn_backfill/<gid>/playbyplay.json; 168 files; 62,159,595 bytes; JSON, image resolution not applicable.
Expected worktree path pattern: C:/Users/neelj/nba-harness-h89/data/domains/wnba/cdn_backfill/<gid>/playbyplay.json.
This lane opened zero archive files. The author supplied no verified absolute archive root; the path pattern and totals above are attributed to the spec, not remeasured.
The only payload input is documented_shape in tests/platformkit/ingame/test_nba_pbp_source.py: constructed values with the P2 key set verbatim, plus timeActual and qualifiers. Current file identity is in the Identities table below (the memo's one identity table, regenerated last).
The first test consumes that fixture through nba_pbp_poll and the landed _build_row end to end. No real NBA row was supplied.
The NBA payload shape is UNVERIFIED until the first live game.

## Imported contracts read before coding
Exact signatures (wrapped source lines joined):
```python
def parse_venue_time(value: object) -> float | None:
def _receipt(get: GetFn) -> dict:
def unique_games(rows: list[dict], get, source: str, resolve=None, on_error=None, **kw) -> list[dict]:
def report(get, source: str, reason: str, error=None, on_error=None) -> None:
def _build_row(sport: str, item: dict, request_start: str, response_end: str, capture_ts: str, last_state: dict) -> dict:
def _prepare_tick(client, sports: list[str], now: datetime, state: dict, clock: Callable, writer: StateWriter) -> tuple[list, list, int]:
def _main(argv: list[str] | None = None) -> dict:
def _norm_abbr(a: str) -> str:
def __init__(self, utc_clock=utcnow) -> None:
```
Read landed modules: execution/venue_time.py, ingame/local_state_capture_sources.py, ingame/local_state_capture.py, ingame/local_state_capture_io.py, ingame/local_capture_metrics.py, ingame/baseline_four_arm_features.py, ingame/nba_state_enrichment.py; paths prefixed scripts/platformkit/.
The census worker read domains/basketball_nba/espn_nba_bridge.py before importing _norm_abbr.
Read schedule dependency local_state_capture_dates.py to resolve the missing-local-date integration result.
FEATURES and CORPORA are imported declarations; _CADENCE is read at poll time to avoid a circular import.

## Implemented behavior
Three new modules (source, census, comparison) and two new test files (test_nba_pbp_source.py, test_nba_pbp_source_1c.py), 68 + 20 = 88 cases, this memo, and only the three spec-authorized additive wiring edits.
Source and feature files were already 300 lines. Additions share existing declaration lines to preserve the line cap.
SPORTS_AVAILABLE stays unchanged; nba_pbp is opt-in. NBA-only ticks keep the same request list. No capture was launched.
The live cadence constant asserts equality with the landed scheduler. Each live PBP response carries its own receipt.
State is exactly the fifteen named fields plus pbp_census. Strict integer count fields refuse booleans, floats, numeric strings and out-of-range values.
Clock parsing uses Decimal and serializes an exact decimal string for the landed JSON writer. No float conversion is used for clock arithmetic.
Team fouls are counts of personal foul actions in the current period, NOT official team-foul totals. The frozen subtype tuple is (personal,).
Lineups use only current-period substitution IN/OUT actions. A sixth or repeated IN refuses the side for the remainder of that period.
Bonus is 1 only after an opponent inpenalty foul; otherwise None. Timeout remaining counts are None/not_in_feed.
Possession may reflect the finished action (E3/S414 caution); a sealed prereg decides any use.
Future actions are counted and skipped before schema and duplicate validation. Duplicate action or game identities are counted and refused.
Provider timestamps use parse_venue_time for grammar/calendar validation and Decimal whole-seconds plus original fractions for comparisons.
Census groups raw canonical game/receipt keys: identical rows count once; conflicts exclude every member; invalid receipts are counted before grouping.
Malformed content cannot leave a valid twin admitted at a conflicting key. ESPN selection uses the maximum eligible parsed receipt, with conflicting latest evidence refused.
Census reports lineup presence cells, agree/disagree as null, and id_crosswalk_absent. It never compares IDs across providers.
When landed scheduling returns date=None, the census uses the UTC receipt shard day. Explicit valid dates are retained; malformed dates are counted refusals.
Output paths are checked as both absolute and resolved paths against capture, registry and cache roots. Output uses fsync plus atomic replacement and cleanup on failure.

## Verification (current, FIX a10; earlier per-fix deltas collapsed into Fix history below)
Reproduction, one file at a time: `python -m pytest <path> -q -p no:cacheprovider`.
Current construct-case counts: test_nba_pbp_source.py 68 passed; test_nba_pbp_source_1c.py 20 passed -- 68 + 20 = 88 total across both test files.
Unchanged-landed spot-checks run this fix: test_state_capture_sources.py 240 passed; test_local_state_capture.py 19 passed. No whole-suite run (forbidden).
`python -m scripts.platformkit.tracking.contract_preflight --base master --spec docs/evidence/tracking/specs/S433_spec.md --paths` over the nine owned/shared/memo files (nba_pbp_compare.py and this memo included; verdict files excluded): 9 PASS, 0 FAIL (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication).
Protected checks (AST-unchanged): _CADENCE, _build_row, SPORTS_AVAILABLE, CORPORA and FEATURES['nba'] still match master; the three shared files carry only their pre-existing additive edits, untouched by this fix.
Every candidate .py file is ASCII and <=300 lines (`len(text.splitlines())`): nba_pbp_source.py 258, nba_pbp_census.py 224, nba_pbp_compare.py 97, test_nba_pbp_source.py 300, test_nba_pbp_source_1c.py 259; the three shared files are 300, 299, 300. See the identity table below for byte/sha256 identity.
SHA: NOT CREATED (sandbox); files ready for lane_commit.

## Fix history

- 2026-09-24 FIX 1b (AMENDMENTS 1-2, round 1: ACCEPT WITH CORRECTIONS plus a separate REJECT of two blockers, both fixed): last-action-by-actionNumber ordering (never wall-clock), per-field foul refusals, one attempt per PBP GET, census other_date/input_rows partition, strict per-field/per-reason assertions; test_nba_pbp_source.py 56 -> 68 passed.
- 2026-09-24 FIX 1c (AMENDMENT 3, round 2: REJECT four blockers plus one correction, fixed): foul-shaped malformed actionType classified before the kind filter, future/conflicting rows folded into rows_refused, transport reasons de-duplicated against the real StateClient/ReceiptGetter, ESPN comparison pair-scoped before dedup; new test_nba_pbp_source_1c.py, 9 cases.
- 2026-09-24 FIX 1d (AMENDMENT 4, round 3: REJECT one blocker plus one correction, fixed): `_dedup` no longer double-counts a poisoned group in `rows_refused`; each group is now classified exactly once; memo collapsed to this Fix history section per AMENDMENT 4(b); test_nba_pbp_source_1c.py 9 -> 12 passed.
- 2026-09-24 FIX 1e (AMENDMENT 5, round 4: REJECT four blockers, fixed): `_comparison` scopes ESPN rows to the PBP game's team pair before latest-per-game_key selection, `run()` counts every parsed PBP-shard row before a sport-identity refusal, foul-shape detection uses the full FOUL_SHAPES vocabulary so a malformed technical is no longer unclassified; test_nba_pbp_source_1c.py 12 -> 15 passed.
- 2026-09-24 FIX 1f (AMENDMENT 6, round 5: REJECT two blockers, fixed): `run()` checks each shard's own rows against its own shard name (new nba_identity_refused counter, no leak into the PBP partition), foul-shape detection flags any non-foul actionType paired with a FOUL_SHAPES subType, `_comparison`/`_teams`/`_category`/`_lineup` moved verbatim into new nba_pbp_compare.py because census.py was at its 299-line cap; test_nba_pbp_source_1c.py 15 -> 18 passed.
- 2026-09-24 FIX 1g (AMENDMENT 8, round 6: REJECT two blockers plus one correction, fixed): `census()` now splits PBP/NBA rows by shard of origin before the future/cutoff check, so top-level and ESPN-side `future_rows` can never mix; one pre-existing test_nba_pbp_source.py assertion rewritten in place to match (file held at 300 lines); test_nba_pbp_source_1c.py 18 -> 19 passed.
- 2026-09-24 FIX a9 (AMENDMENT 9, round 7: independent-verifier REJECT three blockers plus one correction, all fixed; one NOTE item needed no code change): lineup/foul replay now orders by actionNumber (`by_action`) instead of time order, fixing a same-tick earlier-stamp double-IN; two test_nba_pbp_source.py assertions strengthened (census reason; agree/disagree/id_crosswalk_absent on both lineup fields) and one loosened `>=` corrected to `==`; test_nba_pbp_source_1c.py 19 -> 20 passed, test_nba_pbp_source.py 68 passed (edited in place, count unchanged).
- 2026-09-24 FIX a10 (AMENDMENT 10, round 8: independent-verifier REJECT one BLOCKING, fixed; memo-only, no code changed): this memo exceeded the 300-line cap (358 lines) and stated stale counts (19+68=87 vs the actual 20+68=88); collapsed the historical narrative above to one dated line per round, corrected the totals to 68 + 20 = 88 throughout, and regenerated the identity table below at base sha c4891f827.
- 2026-09-24 FIX a11 (AMENDMENT 11, round 9: sol REJECT two BLOCKING, both memo, fixed; no code changed): removed the stale duplicate test_nba_pbp_source.py fixture-identity row (19,991 bytes, near old line 100) so the memo carries exactly one identity table; corrected the implementation summary from "one new test file" to three new modules (source, census, comparison) and two new test files (test_nba_pbp_source.py, test_nba_pbp_source_1c.py), 68 + 20 = 88 cases; regenerated the Identities table below LAST at base sha f9dfd66eb, with the spec row and the three protected rows cross-checked against `git show master:<path>` LF-normalised bytes.

CDN-shape-UNVERIFIED unchanged across every fix above: no real NBA payload, CDN reachability, or live capture output was exercised in any of them; every case is CONSTRUCT against the documented P2 shape, the landed StateClient/ReceiptGetter, or (1e/1f/1g's run-level tests) a constructed shard file on disk.

## Identities (regenerated at FIX a11 time, LAST edit, base commit `git rev-parse HEAD` = `f9dfd66eb`)
Absolute paths; bytes = raw file size; sha256 is over LF-normalised content (`read_bytes().replace(b"\r\n", b"\n")`). This is the memo's only identity table. All candidate/test rows unedited by this fix (memo-only):
- C:/Users/neelj/nba-harness-h89/scripts/platformkit/ingame/nba_pbp_source.py: 14331; 05373bbcfd8959d9992cc78e42098de1941bb0e398f2cd0049b9903442afcede
- C:/Users/neelj/nba-harness-h89/scripts/platformkit/ingame/nba_pbp_census.py: 10479; de4aa8babfccecbc6e4c7c2bc50201f047b84106a60ead4d5b391e982260bb51
- C:/Users/neelj/nba-harness-h89/scripts/platformkit/ingame/nba_pbp_compare.py: 5009; 3aaa4b94c9dd7238f74a112166810c71f596d016b9408ed5f0fc772cda2bd914
- C:/Users/neelj/nba-harness-h89/tests/platformkit/ingame/test_nba_pbp_source.py: 20180; 2c90733d8871b2a6af3e4823e703fca003d267358413614ec5f2717b280bc98e
- C:/Users/neelj/nba-harness-h89/tests/platformkit/ingame/test_nba_pbp_source_1c.py: 13605; 01c033b4881f422888523c40ef8d39882e7003f2514899efc18a3692ac11fa69
- C:/Users/neelj/nba-harness-h89/scripts/platformkit/ingame/baseline_four_arm_features.py: 15766; 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade (shared, protected; cross-check `git show master:scripts/platformkit/ingame/baseline_four_arm_features.py` = 15257 bytes, sha 6d26db781bdf8efe1e8e8ca31e685796ca23b64aa3d9f9c735044af2df8d89f1 -- differs by the candidate's own pre-existing additive edit; protected symbols AST-unchanged per Verification above)
- C:/Users/neelj/nba-harness-h89/scripts/platformkit/ingame/local_state_capture.py: 17853; 1dead98bec9b6cef9eb711be5ef34b7a859f71a9121eda137c106ba7249c1879 (shared, protected; cross-check `git show master:scripts/platformkit/ingame/local_state_capture.py` = 17530 bytes, sha 243dd7bdb7a1ccfa8e985830b278c1e649a603194e9b1f86aa28c70d712c1b5c -- differs by additive edit; protected symbols AST-unchanged)
- C:/Users/neelj/nba-harness-h89/scripts/platformkit/ingame/local_state_capture_sources.py: 20636; c17bbb2e1f27c7f1ce09c97da6e954e7c93cea11e51448cff511b00978b83716 (shared, protected; cross-check `git show master:scripts/platformkit/ingame/local_state_capture_sources.py` = 20212 bytes, sha d876ae69825121f95d1bf3b9c8e622d4a4590be6daca7e1ebf08e6d28e77c92f -- differs by additive edit; protected symbols AST-unchanged)
- C:/Users/neelj/nba-harness-h89/docs/evidence/tracking/specs/S433_spec.md: 22552; dedb01b7f3660c6f4058f2f3b07250d29ef0d4bddb333f8ac5f4d3ca0e1dcc1f (spec now carries AMENDMENTS 1-11; unedited by this fix lane, read-only binding input; cross-check `git show master:docs/evidence/tracking/specs/S433_spec.md` = 22512 bytes, SAME sha256 -- LF-normalised content is byte-identical to master, the raw-byte gap is only the worktree's CRLF checkout)

## NOT VERIFIED
- No real NBA payload, CDN reachability, stored archive census, season-night behavior or real capture output was exercised.
- Author-reported WNBA archive identity was not remeasured; the canonical absolute archive location was not attested.
- Count fields encoded by the live provider as strings will be refused until that schema is independently verified.
- Filesystem power loss, disk exhaustion and symlink races were not exercised; replacement failure is constructed.
- A cross-provider player-ID crosswalk does not exist in this candidate. No lineup agreement is claimed.
- The ORCHESTRATOR owns the first-live-night step after season start: reachability first, then this census over that night's shard. An unreachable CDN may yield zero rows and CLOSED AT LIMIT.
- Adoption requires one supervised owner-visible relaunch naming nba_pbp; this lane did not restart any service.
- The independent sandbox verifier (AMENDMENT 9 and AMENDMENT 10 rounds) could not run its own pytest rerun because its environment's temporary directory is read-only; both rounds' fixes and this memo's counts were instead exercised and confirmed on this host, per-file (test_nba_pbp_source.py 68 passed, test_nba_pbp_source_1c.py 20 passed).
