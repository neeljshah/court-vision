# S432 MLB live feed state
PREPARE: implemented as an opt-in sibling block; no corpus is declared or scored.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h88.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.
The prompt's shorter docs/evidence/VERIFIER_CONTRACT.md path is absent; the binding spec names the existing tracking contract.
Only the six spec-owned files changed. The binding CHANGE explicitly authorizes the two additive landed-file edits.

## Corrected premise and before-condition
The poller already fetches the MLB live feed once per game tick. A second source poller would duplicate that request.
The actual omission is the three derived fields: times_through_order, bullpen_used_home, bullpen_used_away.
No running capture, cache, registry, network, pod, or production STOP file was accessed.
Inputs were injected CONSTRUCT dictionaries and temporary synthetic JSONL shards; video resolution is n/a.
Before editing, git show master:<path> plus numbered range reads produced this exact output:
```text
scripts/platformkit/ingame/local_state_capture_sources.py master_sha256=d876ae69825121f95d1bf3b9c8e622d4a4590be6daca7e1ebf08e6d28e77c92f
23: MLB_LIVE_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
34: SPORTS_AVAILABLE: List[str] = (["mlb", "nba", "soccer"] + ["tennis"] * (_tennis_parse_scoreboard is not None)
35:                                + ["nfl", "ncaaf"] * (_nfl_normalize_scoreboard is not None))
166:     doc = get(MLB_LIVE_URL.format(game_pk=game_pk))
167:     receipt = _receipt(get)
168:     if not isinstance(doc, dict):
169:         return None
170:     fields = _mlb_extract_state(doc)
171:     data = doc.get("gameData") or {}
172:     teams, dates, status = data.get("teams") or {}, data.get("datetime") or {}, data.get("status") or {}
173:     state = {k: v for k, v in fields.items() if k not in ("game_pk", "ts")}
174:     state.update(_mlb_last_play(doc, get))
175:     delayed = "delay" in str(status.get("detailedState", "")).lower()
176:     row = {"game_key": str(game_pk), "home_abbr": (teams.get("home") or {}).get("abbreviation"),
177:             "away_abbr": (teams.get("away") or {}).get("abbreviation"),
178:             "_start": dict(dates, date=dates.get("dateTime")), "_rank": 1,
179:             "_fields": dict(prefix="gameData.datetime.", date_field="dateTime"),
180:             "status": "delayed" if delayed else _MLB_STATUS.get(status.get("abstractGameState"), "pre"),
181:             "source_ts": fields.get("ts"), "state": state, "raw": doc, "receipt": receipt}
299: POLLERS = {"mlb": None, "nba": nba_poll, "soccer": soccer_poll, "tennis": tennis_poll,
300:            "nfl": nfl_poll, "ncaaf": ncaaf_poll}
worktree_matches_master=True
scripts/platformkit/ingame/local_state_capture.py master_sha256=2ba6ccb8c4889c89993cef1fd9948dbad397edd65c40324a272a5be329181514
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
184:             if sport == 'mlb':
185:                 item = src.mlb_poll(getter, task_key)
186:                 items = [item] if item is not None else []
210:                 record = nba_state_enrichment.attach_enrichment(_build_row(sport, item, receipt['request_start_utc'], receipt['response_end_utc'],
211:                                     iso(now), previous), item, state.setdefault('last_enrichment', {}))
285: def _main(argv: list[str] | None = None) -> dict:
286:     parser = argparse.ArgumentParser(description=__doc__)
287:     parser.add_argument('--output-root', type=Path, default=os.environ.get('LOCAL_STATE_ROOT'))
288:     parser.add_argument('--max-ticks', type=int)
289:     parser.add_argument('--sports', nargs='+', help='Comma-separated supported sports: ' + ','.join(src.SPORTS_AVAILABLE))
290:     args = parser.parse_args(argv)
291:     if args.max_ticks is not None and args.max_ticks < 1:
292:         parser.error('--max-ticks must be positive')
293:     if args.sports is not None:
294:         args.sports = [sport.strip() for group in args.sports for sport in group.split(',')]
295:         if any(sport not in src.SPORTS_AVAILABLE for sport in args.sports):
296:             parser.error('--sports must contain only supported sports')
297:     return run_local_state_capture(**vars(args))
worktree_matches_master=True
scripts/platformkit/ingame/nba_state_enrichment.py master_sha256=be46b4ecc694ee3d8bd4add0a96bf130ea7ef733a520894dd852e9abd1596fdb
1: """S414 row-builder step for the NBA sibling `state_enrichment` block (construct-tested).
2: 
3: The block never enters the row's `state`, so the landed state_changed keeps its
4: pre-S414 meaning. enrichment_changed is this block's own flag: None with no
5: previous accepted enrichment for the game, else whether the block (everything but
6: its receipt reference) differs from that previous one.
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
worktree_matches_master=True
scripts/platformkit/ingame/baseline_four_arm_features.py master_sha256=0a436098e54f9377ae2f4c174bb5463a0d71f9484fb52b76a5fb05e38982aaf3
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
31:                'bonus_home', 'bonus_away', 'timeouts_home', 'timeouts_away')
32: NBA_PLAY_CODES = ('92', '93', '94', '95', '96', '97', '98', '99')
33: FEATURES['nba_enriched'] = FEATURES['nba'] + tuple(
34:     name for field in NBA_NUMERIC for name in (field, field + '_present')) + (
35:     'lineup_home_present', 'lineup_away_present', 'last_play_type_present',
36:     *(f'last_play_type_{code}' for code in NBA_PLAY_CODES))
worktree_matches_master=True
S393 schedule provenance:
1: # S393: state-row scheduled starts
2: ## FIX 1o
3: Implements AMENDMENT 10 and AMENDMENT 11 of docs/evidence/tracking/specs/S393_spec.md (both present in this worktree). Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.
4: Machine: local Windows, C:/Users/neelj/nba-harness-h73, on master. Interpreter: Python 3.10.0, C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
5: Inputs: injected CONSTRUCT fixtures only; external video/capture paths, byte sizes and resolution: n/a. No network, commit, git metadata writes, production captures or production STOP files touched.
6: The required landed test's temporary STOP_STATE construct ran under pytest. Changes:
7: - local_state_capture_io.py:196 guards both diagnostic-failure tallies independently,
8:   global first; a counter/storage failure is absorbed without recursion.
9: - local_state_capture_io.py:206 supplies guard_diagnostics to keep every resolver
10:   diagnostic drop best-effort, including diagnostics from landed helpers.
11: - local_state_capture_sources.py:50 and :112 wrap the evidence helper and resolver;
12:   the landed dates resolver is unchanged.
13: - local_state_capture_io.py:249 hashes the WHOLE id-null failed item as JSON with
14:   sort_keys=True, separators=(',', ':'), default=repr; supplied ids stay supplied.
15: - local_state_capture.py is unchanged by FIX 1o; inherited FIX 1j-1n edits remain.
16: No emission-counter, schedule-selection, recovery or commit behavior was changed. Pinned both-order tests:
probe scratchpad exists=False
```
The S393 memo was read as supporting schedule-provenance evidence; _build_row's scheduled_start_utc and scheduled_start_source remain untouched.

## Author's probe receipt (quoted evidence, not repeated by this lane)
URL: https://statsapi.mlb.com/api/v1.1/game/824867/feed/live
Scratchpad identifier: s432_probe.json; not present at scratchpad/s432_probe.json in this checkout.
request_start 2026-09-24T18:27:02.746082Z; response_end 2026-09-24T18:27:02.861251Z.
HTTP 200; 785,917 bytes; SHA256 de976abc8969a048ec73a3853bec1a6e29eddfe4b6c01c01240c75afb47a78cb.
Author reports CIN@ATL, Final; metaData.timeStamp "20260923_014816"; currentPlay.about.atBatIndex 72.
Author reports 73 allPlays, home pitchers [702275, 702566, 800311], four away pitcher ids, no currentPlay.matchup.postOn* keys.
The first test fixture preserves these available values verbatim. Unspecified away ids, matchup ids, scores, counts and start are explicitly synthetic.
This is a projection of the spec's probe description, not the unavailable full response body.

## Landed interfaces read and relied on
Exact signatures, read before using these dependencies:
- local_state_capture_sources.py: `def mlb_poll(get: GetFn, game_pk: str) -> Optional[Dict[str, Any]]:`
- ingame_gumbo_mlb.py: `def extract_state(doc: GumboDoc) -> Dict[str, Any]:` (called by the unchanged poller).
- local_state_capture.py: `def _build_row(sport: str, item: dict, request_start: str, response_end: str, capture_ts: str, last_state: dict) -> dict:` (signature wrapped across two source lines above).
- nba_state_enrichment.py: `def attach_enrichment(row: dict, item: dict, last_enrichment: dict) -> dict:`
- venue_time.py: `def parse_venue_time(value: object) -> float | None:`
- local_state_capture_io.py: `def __init__(self, *args, max_retries: int = 5, **kwargs) -> None:` on StateClient.
- local_state_capture_io.py: `def get(self, url: str, params: dict | None = None, source: str = 'http') -> StateResponse:`
StateClient is injected with a fake session, sleep_fn, clock and utc_clock. No HTTP transport is used.
The new capture dependency is stdlib-only. The census imports only the shared venue parser and the new field declaration.

## Implementation and interpretation
MLB_LIVE_FIELDS, declared before reading any shard:
```text
inning, half, outs, balls, strikes, on_first, on_second, on_third,
pitcher_id, pitcher_pitches, times_through_order, batter_id,
score_home, score_away, bullpen_used_home, bullpen_used_away, last_play_id
```
FEATURES['mlb_live'] references that tuple; CORPORA has no new entry.
--mlb-live defaults off. The keyword travels through run_local_state_capture, capture_state_once (including owned-writer recursion), and _prepare_tick.
Only MLB rows gain the sibling block, with receipt_utc copied from response_end_utc and refused always a list.
Missing/null upstream paths omit the affected fact. Invalid containers or strict integer values refuse it.
Earlier duplicate atBatIndex values and duplicate pitcher ids refuse their fact; current/future plays are excluded before matchup checks and duplicate handling.
Mixed missing/refused earlier plays resolve deterministically to refused; input permutations are tested.
Generous malformed-input ceilings: current atBatIndex 10000; person ids 2**31-1; pitcher lists 1..100.
Identifiable future indexes are ignored regardless of size or count. An empty pitchers list is ABSENT with reason
no_pitchers_yet, never refused; the verifier's probe (home pitchers [1, 2], away pitchers []) yields times_through_order 3,
bullpen_used_home 1, bullpen_used_away absent, refused [].
The census validates strict integers with explicit generous bounds; base occupancy is boolean and half is a recognized string.
It reads state first, then mlb_live; a sibling refusal applies when state has no value for that field.
It partitions every accepted row into present/absent/null/refused for each declared field.
Raw JSON receipt keys preserve 1 versus 1.0 and distinct zoned timestamp spellings.
Identical copies count once with duplicate_identical; conflicts exclude the entire group with duplicate_conflict counting all members.
Invalid receipts are counted before grouping. Unparseable compact source_ts increments source_ts_unparsed without excluding the row.
Source timestamps are converted from YYYYMMDD_HHMMSS to zoned ISO and validated by parse_venue_time.
Exact Decimal fractions restore the shared parser's truncated submicrosecond digits for strict causality comparisons.
There is no as-of query or recovery in this census; it counts the complete supplied date shard.
Output paths are checked in lexical and resolved forms against data/cache, data/registry and --root before opening an input.
Census writes flush and fsync a unique sibling temporary file, then atomically replace the output; failures clean up and re-raise.

## Construct evidence and reproduction
Acceptance denominator: the three new fields available in the complete injected payload.
The first test uses real mlb_poll with an injected getter and receipt, then _build_row, then attach.
Observed:
```text
CONSTRUCT new fields before=0/3 after=3/3
master injected requests=3
candidate injected requests=3
master_vs_candidate_flag_off_bytes_equal=True
master_build_row_equals_candidate=True
```
The byte comparison executed git show master:scripts/platformkit/ingame/local_state_capture.py in an isolated module,
then ran that module and the candidate with separate client_for(probe_projection.__wrapped__()) clients and temporary roots.
Both used sports=['mlb'], clock=lambda: 0.0, max_ticks=1. Their state/mlb/*.jsonl bytes were identical.
No real requests were issued. Before/after is field coverage, not a forecasting measurement.

Run each file separately:
```text
python -m pytest tests/platformkit/ingame/test_mlb_live_feed_state.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_state_capture_sources.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_local_state_capture.py -q -p no:cacheprovider
```
Final per-file results: test_mlb_live_feed_state.py 70 passed; test_state_capture_sources.py 240 passed;
test_local_state_capture.py 19 passed. Total 329 passed, each file run separately with no cache provider.
Both CLI --help commands exited 0: scripts.platformkit.ingame.local_state_capture and scripts.platformkit.ingame.mlb_live_feed_census.
Contract preflight command (all six owned paths, --base master --spec docs/evidence/tracking/specs/S432_spec.md) produced:
```text
PASS vocab clean over 6 files
PASS crlf no index-side CRLF over 6 file(s); 4 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold 4 literal(s) matched
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```
Line counts using len(text.splitlines()): state 103, census 177, new tests 262, features 300, capture 299. Every owned file is ASCII.
AST checks confirmed _build_row and _CADENCE unchanged. Executed master/candidate FEATURES and CORPORA comparisons confirmed every old declaration unchanged.
git diff master was empty for local_state_capture_sources.py, ingame_gumbo_mlb.py, nba_state_enrichment.py and both required landed test files.
git status --short lists exactly the six owned paths. No commit was attempted; files remain ready for lane_commit.
The initial fixture clock was frozen and the run was interrupted; its clock now advances through injected sleep.
The initial landed CLI check failed because absent --mlb-live added a False keyword; argparse.SUPPRESS preserves the landed call shape.
Review found future-row list length/index could affect TTO; those checks now follow temporal exclusion, with a long-future-tail regression.
The new construct file covers TTO 1/2/3; all specified absence cases; strict type/nonfinite/large-value refusals; both orders;
sibling-only schema, request count and default-off bytes; real capture writer recursion and CLI threading;
hand-counted synthetic census, all duplicate cases, invalid receipts and exact causality boundaries;
lexical/resolved output protection, existing shard preservation and dump/fsync/replace failures.

## FIX 1b (AMENDMENT 1)
Scope: AMENDMENT 1(a) and 1(b) of docs/evidence/tracking/specs/S432_spec.md only. No commit, no network.
Files touched: mlb_live_feed_state.py, tests/platformkit/ingame/test_mlb_live_feed_state.py. mlb_live_feed_census.py
and this memo carry the 1(b) wording. baseline_four_arm_features.py was left untouched (see NEW GAPS below).

(a) Empty pitchers list is absent, not refused: `_bullpen` in mlb_live_feed_state.py previously refused any
pitchers list outside `1 <= len <= 100`, so a present-but-empty boxscore (pre-game) was wrongly refused instead
of absent. Fixed by splitting the check: a missing/null pitchers list still raises `_Absent('no_pitchers_list')`
(via `_path`, now caught and relabeled), a present empty list raises the new `_Absent('no_pitchers_yet')`, and
only a non-list value or a list over 100 entries is `_Refused('invalid pitchers')`. Neither absent case ever
yields bullpen_used_home/away = 0. Two new regressions added:
`test_bullpen_empty_or_null_pitchers_absent_not_refused` parametrized on `pitchers in ([], None)`, asserting the
field is neither in the block nor in `block['refused']`.

(b) times_through_order label: stated in words -- "1 plus the number of earlier plays in which the current
pitcher faced the current batter (a pitcher-batter pair count, not the lineup pass)" -- as the `_tto` docstring
in mlb_live_feed_state.py, as a comment above `_BOUNDS` in mlb_live_feed_census.py (the census output key
description), and in this paragraph (the memo).

Tests, each file run separately with no cache provider:
```text
python -m pytest tests/platformkit/ingame/test_mlb_live_feed_state.py -q -p no:cacheprovider   -> 72 passed
python -m pytest tests/platformkit/ingame/test_local_state_capture.py -q -p no:cacheprovider    -> 19 passed
python -m pytest tests/platformkit/ingame/test_baseline_four_arm.py -q -p no:cacheprovider      -> 53 passed
```
Contract preflight (--base master --spec docs/evidence/tracking/specs/S432_spec.md, all candidate paths): 9 PASS, 0 FAIL.
Line counts using len(text.splitlines()): state 112, census 179, tests 271, features 300 (unchanged), capture 299 (unchanged).

### NEW GAPS recorded (tier 2)
Carried forward from AMENDMENT 1(c), recorded non-blocking:
- baseline_four_arm_features.py sits at exactly 300 LOC after two cosmetic blank-line deletions; the next addition
  there must split the file. This fix lane hit that ceiling directly: the FEATURES['mlb_live'] docstring wording
  for times_through_order was NOT added to baseline_four_arm_features.py because doing so would push it over 300
  LOC; the wording lives in mlb_live_feed_state.py's `_tto` docstring instead (and in the census key comment).
  RESOLVED in FIX 1c below: the wording now lives in baseline_four_arm_features.py too, at the same 300-line cap.
- The census's `_instant` accepts a numeric response_end_utc because the shared parser (parse_venue_time) does;
  the spec is silent on this and it remains documented-but-unchanged behavior.

## FIX 1c (AMENDMENT 2)
Scope: AMENDMENT 2(a) and 2(b) of docs/evidence/tracking/specs/S432_spec.md only (round 1 codex sol REJECT on fix
1b: one blocker, one memo correction; Opus tier 2 ACCEPT stands). No commit, no network.
Files touched: baseline_four_arm_features.py, tests/platformkit/ingame/test_mlb_live_feed_state.py, this memo.

(a) Pair-count wording now lives in baseline_four_arm_features.py itself: a comment line on the
`FEATURES['mlb_live'] = MLB_LIVE_FIELDS` assignment carries the exact sentence "1 plus the number of earlier plays
in which the current pitcher faced the current batter (a pitcher-batter pair count, not the lineup pass)". Room
was made at the existing 300-line cap by deleting one blank line from a PEP8 double-blank-line function separator
(between `logit` and `logistic`): net change is +1 comment line, -1 blank line, file stays at exactly 300 LOC.
FEATURES values, CORPORA, `_tto`, `_bullpen` and every other helper's code are unchanged. Verified with an
AST-dump comparison (module/function/class docstrings and any other standalone string-expression statement
stripped from both trees) between the pre-edit and post-edit file, using a same-worktree scratch copy
(`_s432_before_tmp.py`, deleted after the check): EQUAL -- confirming a pure comment/docstring/blank-line change.
`test_tto_pair_count_wording_in_baseline_four_arm_features` (new) reads
`Path(baseline_four_arm_features.__file__).read_text(encoding='ascii')` and asserts the exact phrase is present in
that file's own source, not only in mlb_live_feed_state.py or the census.

(b) Memo line 185 restated above (this fix): an empty pitchers list is ABSENT with reason no_pitchers_yet, never
refused; the verifier's probe (home pitchers [1, 2], away pitchers []) yields times_through_order 3,
bullpen_used_home 1, bullpen_used_away absent, refused []. The prior "refuses the negative derived count" sentence
is removed; no contradictions remain with FIX 1b section (a) or the `_bullpen` behavior above.

Tests, each file run separately with no cache provider:
```text
python -m pytest tests/platformkit/ingame/test_mlb_live_feed_state.py -q -p no:cacheprovider   -> 73 passed
python -m pytest tests/platformkit/ingame/test_local_state_capture.py -q -p no:cacheprovider    -> 19 passed
python -m pytest tests/platformkit/ingame/test_baseline_four_arm.py -q -p no:cacheprovider      -> 53 passed
```
Contract preflight (`--base master --spec docs/evidence/tracking/specs/S432_spec.md --paths` over all six owned
paths): 9 PASS, 0 FAIL (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact,
row_duplication).
Line counts using len(text.splitlines()): features 300 (unchanged), tests 281 (was 271), state 112 (unchanged),
census 179 (unchanged), capture 299 (unchanged). Every edited file confirmed ASCII by decode check.

## NOT VERIFIED
- The author's full probe body, raw byte count or digest; only its quoted receipt and described fields were available.
- The real-night census, historical shard counts, live timing and provider behavior; these remain the orchestrator's steps.
- Master-side independent verification, production rollout, process restart, network behavior or any forecasting result.
- Actual Windows junction creation: resolved aliases are injected in a construct; no filesystem junction is created.
- Physical power loss or filesystem durability across a crash; tests inject write, fsync and replace failures.
