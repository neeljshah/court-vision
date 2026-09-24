# S414 NBA state enrichment - PREPARE

Local construct work only in nba-harness-h83.
## BINDING BEFORE-CONDITION
Master: 9e5bd3aac6959c7f12c2cd76b2e9d9daebc97968 (post-S393). Current lines quoted before edits.
```text
scripts/platformkit/ingame/baseline_four_arm_features.py
12: FEATURES = {
13:     'mlb': ('score_diff', 'inning', 'half', 'outs',
14:             *(f'base_{value}' for value in range(1, 8))),
15:     'soccer': ('score_diff', 'minute', 'home_red_cards', 'away_red_cards',
16:                'home_red_present', 'away_red_present'),
17:     'nba': ('score_diff', 'quarter', 'seconds_remaining'),
18: }
19: CORPORA = {
20:     name + suffix: sport
21:     for name, sport in [('mlb', 'mlb'), ('mlb_clean', 'mlb'),
22:                         ('soccer_intl', 'soccer'), ('nba', 'nba'),
23:                         ('nba_checkpoints', 'nba')]
24:     for suffix in ('', '_segmented', '_segmented_r3')
25: }
26: CORPORA['nba_checkpoints_r1'] = 'nba'
62: def state_eligibility(text: str, sport: str) -> tuple[dict, list[str]]:
63:     """Resolve every declared feature and name all unavailable state inputs."""
64:     values = state_fields(text)
65:     result, reasons = {}, []
67:     if sport == 'nba':
68:         keys = ['quarter' if 'quarter' in values else 'period']
69:         keys += [k for k in ('home_score', 'away_score', 'score_diff') if k in values]
70:         if 'home_score' in values or 'away_score' in values:
71:             keys += [k for k in ('home_score', 'away_score') if k not in values]
72:         for key in keys:
73:             try:
74:                 value = Decimal(values[key])
75:             except (InvalidOperation, KeyError, TypeError, ValueError):
76:                 reasons.append('non_integral_state' if values.get(key) in ('True', 'False')
77:                                else f'missing_state:{key}')
78:                 continue
79:             if not value.is_finite() or not math.isfinite(value):
80:                 reasons.append('nonfinite_value')
81:             elif value != value.to_integral_value():
82:                 reasons.append('non_integral_state')
83:             elif abs(value) > (100 if key in ('quarter', 'period') else 10000) or (
84:                     key != 'score_diff' and value < 0):
85:                 reasons.append('invalid_state_range')
87:     def number(key: str, value: object, valid=lambda v: True) -> None:
88:         if value is None:
89:             reasons.append(f'missing_state:{key}')
90:             return
91:         try:
92:             value = float(value)
93:         except (ValueError, TypeError):
94:             reasons.append(f'missing_state:{key}')
95:             return
96:         if not np.isfinite(value):
97:             reasons.append('nonfinite_value')
98:         elif not valid(value):
99:             reasons.append(f'missing_state:{key}')
100:         else:
101:             result[key] = value
103:     score = values.get('score_diff')
104:     if score is None and 'home_score' in values and 'away_score' in values:
105:         try:
106:             home, away = float(values['home_score']), float(values['away_score'])
107:             score = home - away if np.isfinite(home) and np.isfinite(away) else float('nan')
108:         except ValueError:
109:             reasons.append('missing_state:score_diff')
110:     number('score_diff', score)
111:     if sport == 'mlb':
112:         number('inning', values.get('inning'), lambda v: v >= 1)
113:         number('outs', values.get('outs'), lambda v: v in (0, 1, 2))
114:         half = values.get('half', '').lower()
115:         number('half', {'top': 0, 'bottom': 1}.get(half))
116:         try:
117:             base = float(values.get('base', 'nan'))
118:         except ValueError:
119:             base = float('nan')
120:         if base not in range(8):
121:             reasons.append('missing_state:base')
122:         else:
123:             # Categorical codes only: zero is the reference; no bit decoding.
124:             result.update({f'base_{value}': float(base == value) for value in range(1, 8)})
125:     elif sport == 'soccer':
126:         number('minute', values.get('minute'), lambda v: v >= 0)
127:         for side in ('home', 'away'):
128:             key = f'{side}_red_cards'
129:             number(key, values.get(key, 0), lambda v: v >= 0)
130:             result[f'{side}_red_present'] = float(key in values)
131:     elif sport == 'nba':
132:         number('quarter', values.get('quarter', values.get('period')), lambda v: v >= 1)
133:         remaining = values.get('seconds_remaining')
134:         if remaining is None and 'clock' in values:
135:             try:
136:                 minutes, seconds = values['clock'].split(':')
137:                 minutes, seconds = Decimal(minutes), Decimal(seconds)
138:                 if not all(v.is_finite() and 0 <= v <= limit for v, limit in (
139:                         (minutes, 48), (seconds, 60))):
140:                     reasons.append('invalid_state_range')
141:                 else:
142:                     remaining = minutes * 60 + seconds
143:                     if (minutes != 0 or seconds != 0) and remaining == 0:
144:                         reasons.append('invalid_state_range')
145:             except (DecimalException, ValueError):
146:                 reasons.append('missing_state:seconds_remaining')
147:         number('seconds_remaining', remaining, lambda v: v >= 0)
148:         try:
149:             exact = Decimal(remaining) if remaining is not None else Decimal('NaN')
150:             if exact.is_finite() and exact != 0 and result.get('seconds_remaining') == 0:
151:                 reasons.append('invalid_state_range')
152:         except (InvalidOperation, ValueError, TypeError):
153:             reasons.append('missing_state:seconds_remaining')
154:         if result.get('quarter', 0) >= 4 and result.get('seconds_remaining') == 0:
155:             reasons.append('post_final')
156:         if result.get('seconds_remaining', 0) > (2880 if result.get('quarter', 0) <= 4 else 300):
157:             reasons.append('invalid_state_range')
158:     else:
159:         raise ValueError('unknown sport')
160:     return result, sorted(set(reasons))
163: def parse_state(text: str, sport: str) -> dict:
164:     """Parse a complete declared state; eligibility callers retain reason counts."""
165:     result, reasons = state_eligibility(text, sport)
166:     if reasons:
167:         raise ValueError(', '.join(reasons))
168:     return {key: result[key] for key in FEATURES[sport]}
```
```text
domains/basketball_nba/live_state_nba.py
61: def state_from_event(ev: Dict[str, Any]) -> Optional[GameState]:
62:     """One ESPN scoreboard event -> an NBA GameState, or None if unparseable.
64:     Reuses live_board._parse_event for the home/away/score/clock/period extraction
65:     (single source of truth for the ESPN shape), then maps it onto GameState.
66:     Never raises; a malformed event returns None (not a fabricated game).
67:     """
68:     try:
69:         row = _lb._parse_event(ev, SPORT)
70:     except Exception as exc:  # noqa: BLE001 - one bad event never sinks ingest
71:         logger.warning("live_state_nba parse failed: %s", exc)
72:         return None
73:     if row is None:
74:         return None
75:     status = _status_from_state(row.get("state"))
76:     clock_sec = _clock_to_sec(row.get("clock"))
77:     elapsed_min = _lb._nba_elapsed(row.get("period"), row.get("clock"))
78:     extras: Dict[str, Any] = {
79:         "detail": row.get("detail"),
80:         "home_team": row.get("home"), "away_team": row.get("away"),
81:         "home_abbr": row.get("home_abbr"), "away_abbr": row.get("away_abbr"),
82:         "period_len_sec": _PERIOD_LEN_SEC,
83:     }
84:     if elapsed_min is not None:
85:         extras["elapsed_min"] = elapsed_min
86:     return GameState(
87:         sport=SPORT,
88:         game_id=_game_id(ev, row),
89:         period=row.get("period"),
90:         clock_sec=clock_sec,
91:         home_score=row.get("home_score") or 0,
92:         away_score=row.get("away_score") or 0,
93:         possession=None,  # ESPN scoreboard does not expose possession; never faked.
94:         status=status,
95:         extras=extras,
96:     )
```
```text
scripts/platformkit/ingame/local_state_capture_sources.py
188:         if payload is not None:
189:             report(get, sport, "scoreboard_shape_errors", on_error=on_error)
190:         return out
191:     for position, event in enumerate(payload["events"]):
192:         try:
193:             row = _espn_parse_event(event, sport)
194:             if row is None:
195:                 report(get, sport, "event_parse_empty", on_error=on_error)
196:                 continue
197:             ident = _identity(event, sport, row.get("home_abbr"), row.get("away_abbr"), get, sport)
198:             common = {"game_key": str(ident),
199:                       "_missing_game_id": event.get("id") is None,
200:                       "home_abbr": row.get("home_abbr"), "away_abbr": row.get("away_abbr"),
201:                       "_start": event, "status": _status(event),
202:                       "source_ts": None, "raw": payload, "receipt": dict(receipt)}
203:             if sport == "nba":
204:                 games = _nba_parse_scoreboard({"events": [event]})
205:                 if not games:
206:                     report(get, sport, "nba_adapter_empty", on_error=on_error)
207:                     continue
208:                 gs = games[0]
209:                 common["state"] = {"period": gs.period, "clock_sec": gs.clock_sec,
210:                                    "home_score": gs.home_score, "away_score": gs.away_score,
211:                                    "elapsed_min": gs.extras.get("elapsed_min")}
212:             else:
213:                 common["state"] = {k: row[k] for k in ("home_score", "away_score", "period", "clock", "detail") if k in row}
214:             out.append(common)
215:         except Exception as exc:
216:             adapter_error(get, sport, "event_adapter_errors", lambda: failure_identity(event, sport, position, get=get), exc, on_error)
```
```text
scripts/platformkit/frontend/live_board.py
242: def _parse_event(ev: Dict[str, Any], sport: str) -> Optional[Dict[str, Any]]:
243:     """One ESPN scoreboard event -> a normalized row (no prediction yet). None if unparseable."""
244:     comps = ev.get("competitions") or []
245:     if not comps:
246:         return None
247:     comp = comps[0]
248:     status = ev.get("status") or {}
249:     st_type = status.get("type") or {}
250:     state = st_type.get("state")  # 'pre' | 'in' | 'post'
251:     detail = st_type.get("shortDetail") or st_type.get("detail")
252:     clock = status.get("displayClock")
253:     period = status.get("period")
254:     home = away = None
255:     for c in comp.get("competitors") or []:
256:         team = c.get("team") or {}
257:         info = {"abbr": team.get("abbreviation"),
258:                 "display": team.get("displayName") or team.get("abbreviation"),
259:                 "score": c.get("score")}
260:         if c.get("homeAway") == "home":
261:             home = info
262:         elif c.get("homeAway") == "away":
263:             away = info
264:     if home is None or away is None:
265:         return None
266:     return {"sport": _norm_sport(sport),
267:             "home": home["display"], "away": away["display"],
268:             "home_abbr": home["abbr"], "away_abbr": away["abbr"],
269:             "state": state, "detail": detail, "clock": clock,
270:             "period": int(period) if period else None,
271:             "home_score": _to_int(home["score"]), "away_score": _to_int(away["score"])}
```
```text
scripts/platformkit/ingame/local_state_capture.py
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
```
```text
scripts/platformkit/ingame/nba_checkpoints_to_joined.py
172:     state = (f"home_score={home} away_score={away} quarter={period} " 173:              f"seconds_remaining={remaining:.12g}")
```
Before-condition PASS: unchanged NBA triple, five-key converter, receipt plus digest, sealed r1 text.
## Imported contracts read before implementation
live_board.py: `def _parse_event(ev: Dict[str, Any], sport: str) -> Optional[Dict[str, Any]]:`; `def _nba_elapsed(period: Optional[int], clock: Optional[str]) -> Optional[float]:`. live_state_nba.py: `def parse_scoreboard(payload: Optional[Dict[str, Any]]) -> List[GameState]:`. venue_time.py: `def parse_venue_time(value: object) -> float | None:`.
state_bus.py (dataclass constructor fields): `sport: str; game_id: str; period: Optional[int] = None; clock_sec: Optional[float] = None; home_score: int = 0; away_score: int = 0; possession: Optional[str] = None; status: str = "pre"; extras: Dict[str, Any] = field(default_factory=dict)`.
## Implementation and reproduction
Named paths below use C = event.competitions[0], and side = home or away; no alternate paths are searched. The spec provides no REAL ROW; the first test consumes the constructed fixture through capture, disk row, and feature parsing.
Possession: C.situation.possession, an explicit team id matched uniquely to C.competitors[homeAway=side].team.id; no play, score, or clock inference.
Lineup: C.competitors[homeAway=side].lineup; exactly five distinct ASCII digit-string athlete ids, each at most 20 characters; sorted for stable carriage, no identity feature.
Team fouls: C.competitors[homeAway=side].fouls (strict int, 0..20). Bonus: C.competitors[homeAway=side].bonus (strict bool, carried as 0/1).
Timeouts: C.competitors[homeAway=side].timeoutsRemaining (strict int, 0..7). Last play: C.situation.lastPlay.type.id (string; frozen codes 92,93,94,95,96,97,98,99).
Superseded by FIX 1b (AMENDMENT 2): the fields no longer sit in `state` and carry no per-field asof. Every carried field has a present flag; absent values are null. The sibling block's enrichment_census records present, absent, refused and reason for each of ten fields per row. A well-formed unlisted play code is counted under play_code_unlisted (not refused); a malformed one is a counted refusal; both use the absent reference.
Duplicate competitor sides refuse that side and possession; duplicate canonical game keys in one response refuse all enrichment before landed selection. Existing S393 isolation, diagnostics, identities and base-row selection remain in place.
FEATURES['nba_enriched'] and nba_state_enriched_r1 are additive. Missing numeric features use the zero reference with present=0, while the stored value remains null. Lineups declare presence only. Serialized enriched state text must include response_end_utc and a matching enrichment_receipt_utc (FIX 1b; was per-field asof); equality preserves all nine fractional digits.
Additional exact imported signatures: `def nba_poll(get: GetFn, date_iso: str, on_error=None) -> List[Dict[str, Any]]:`; `def __init__(self, *args, max_retries: int = 5, **kwargs) -> None:` (StateClient); `def __init__(self, *args, **kwargs) -> None:` (StateMetrics). `def capture_state_once(*, client: StateClient | None = None, sports: list[str] | None = None, now: datetime | None = None, state: dict | None = None, clock: Callable = time.monotonic, output_root: Path | None = None, writer: StateWriter | None = None) -> dict:` (line wrapping joined).
CHANGES NO VERDICT: this row scores nothing, builds no corpus and reads no result. A sealed prereg must list the enriched features before any read of them.
Reproduction: `python -m pytest <one file> -q -p no:cacheprovider`, independently for each file below; n = 1369 (CONSTRUCT), all passing.
Under tests/platformkit/ingame/: test_nba_state_enrichment.py 70; test_state_capture_io.py 198; test_state_capture_sources.py 240; test_local_state_capture_schedule.py 367; test_state_capture_fix_1q.py 183; test_state_capture_fix_1s.py 9.
Same directory: test_local_state_capture.py 19; test_state_capture_recovery.py 25; test_state_capture_commit.py 11; test_baseline_four_arm.py 53; test_baseline_four_arm_eligibility.py 45; test_baseline_four_arm_nba.py 134. tests/platformkit/test_ingame_state.py 15.
No new CLI. `python -m scripts.platformkit.ingame.local_state_capture --help` and `python -m scripts.platformkit.tracking.contract_preflight --help` exit 0. All five owned files are ASCII and <=300 lines.
Legacy NBA branch/precheck and parse_state have byte-hash construct assertions; landed tests and protected modules checked against master. Contract preflight: 9 PASS, 0 FAIL (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication), with --base master and --spec docs/evidence/tracking/specs/S414_spec.md over the five owned paths.
## FIX 1b (round 1: both tiers REJECT on the same blocker; ruling S414 AMENDMENT 2)
B1 / sol 1 (BLOCKING, state_changed corrupted by per-field receipt stamps inside `state`). Reproduced first with the exact construct (the fixture event polled through nba_poll and the landed _build_row at receipts 2026-10-10T01:02:03.123456789Z and 2026-10-10T01:02:10.123456789Z, 7 s apart): `OUTPUT state_changed None True`. Fix per AMENDMENT 2 (a): enrich_nba_event now returns a SIBLING block with ONE receipt reference `receipt_utc` (the row's response_end_utc; null when the receipt is invalid) and no `<field>_asof`; local_state_capture_sources.py puts it on the item as `state_enrichment` (one line replaced, no growth; the module stays at 300 lines) and never touches `state`. The NBA `state` is again exactly period, clock_sec, home_score, away_score, elapsed_min. After the fix the same construct prints `OUTPUT state_changed None False`. New module scripts/platformkit/ingame/nba_state_enrichment.py: attach_enrichment(row, item, last_enrichment) is the row-builder step that sets row['state_enrichment'] with its own enrichment_changed (None with no previous accepted block for the game, else whether the block minus its receipt differs); enriched_state_text(row) renders the flat text that parse_state(text, 'nba_enriched') reads FROM THE SIBLING KEY, carrying enrichment_receipt_utc. enriched_eligibility now requires enrichment_receipt_utc == response_end_utc (string equality, all nine fractional digits) instead of per-field asof. Regression tests: an identical event at two receipts gives state_changed (None, False) and enrichment_changed (None, False); a changed enrichment (home fouls 4 to 5) with an unchanged `state` gives state_changed False and enrichment_changed True.
OPEN CONFLICT (RESOLVED by AMENDMENT 3 and FIX 1c below; kept as the fix-1b record). The landed local_state_capture.py _build_row builds the archived row from a FIXED key list (sport, game_key, receipts, state, status, schedule fields, raw_sha256, ...) and passes no other item key through; AMENDMENT 2 (f) keeps that module untouched. So the sibling block reaches the row only through attach_enrichment, which nothing in the landed capture path calls: the end-to-end construct test (capture_state_once to the on-disk jsonl) now asserts the archived `state` holds exactly the five pre-S414 keys and the enrichment assertions run on the attach_enrichment row. PROPOSED wiring (NOT applied), one additive line in local_state_capture.py _prepare_tick right after `record = _build_row(...)`: `record = attach_enrichment(record, item, state.setdefault('last_enrichment', {}))` plus the import; the memory would also need pruning in _prune_game and a reset on day rollover. Without it the 2026-27 forward archive carries no enrichment.
C1 (CORRECTION, unsourced paths). UNSOURCED: C.competitors[homeAway=side].lineup, .fouls, .bonus, .timeoutsRemaining and the last-play codes 92, 93, 94, 95, 96, 97, 98, 99 are not sourced to any stored ESPN NBA payload; they may be permanently ABSENT. C.situation.possession and C.situation.lastPlay.type.id are likewise unconfirmed on a stored NBA payload. The first real preseason payload census (October) decides. C2 (CORRECTION, play_code_unlisted). A well-formed code (an ASCII digit string of 1 to 6 characters) outside the frozen list is counted under reason play_code_unlisted with refused 0; a malformed code stays `invalid` with refused 1. Both use the absent reference; the categories are never widened. Tests: '777', '100', '0' give play_code_unlisted; '9a', '', '1234567' and a non-ASCII digit string give invalid.
C3 (CORRECTION, adoption). Adopting S393 + S414 is ONE supervised, owner-visible relaunch before the NBA season, never an agent-written STOP file. sol 2 (CORRECTION, tests). The repeat-parse test now compares two SERIALIZED parse_state(text, 'nba_enriched') results (json.dumps, byte-identical); the per-path missing test asserts the stored `<field>_present == 0` and the null value on the sibling block directly, plus the census count and the parsed `_present == 0`.
AMENDMENT 2 (e). Four tests in test_nba_checkpoints_to_joined.py fail identically on a clean HEAD export (round-1 tier 2); they predate S414 and are not this row's. Unchanged by this fix: local_state_capture.py, local_state_capture_io.py, live_board.py and nba_checkpoints_to_joined.py (git diff against master is empty); FEATURES['nba'], the nba branch of state_eligibility and parse_state (byte-hash test unchanged and passing).
FIX 1b run (Python 3.10.0, one file at a time, `python -m pytest <one file> -q -p no:cacheprovider`): test_nba_state_enrichment.py 80 (was 70; +10 FIX 1b tests); S393 files unedited: test_state_capture_io.py 198, test_state_capture_sources.py 240, test_local_state_capture_schedule.py 367, test_state_capture_fix_1q.py 183, test_state_capture_fix_1s.py 9, test_local_state_capture.py 19, test_state_capture_recovery.py 25, test_state_capture_commit.py 11; four-arm: test_baseline_four_arm.py 53, test_baseline_four_arm_eligibility.py 45, test_baseline_four_arm_nba.py 134, test_nba_four_arm_primary_contrast.py 278; tests/platformkit/test_ingame_state.py 15; tests/platformkit/execution/test_paper_sizing_inputs.py 22; all passing (CONSTRUCT). test_nba_checkpoints_to_joined.py 61 pass, 4 fail (the predating failures of AMENDMENT 2 (e); that file imports no S414 module). local_state_capture --help exits 0. Contract preflight over the six owned paths with --base master and the S414 spec: 9 PASS, 0 FAIL.
## FIX 1c (AMENDMENT 3: wire the sibling block into the archive)
Reproduced first (capture_state_once to the on-disk jsonl, the fixture event polled twice 7 s apart): before, `ARCHIVED state_changed None has_state_enrichment False` then `ARCHIVED state_changed False has_state_enrichment False`; after, `ARCHIVED state_changed None has_state_enrichment True enrichment_changed None receipt_eq True` then `ARCHIVED state_changed False has_state_enrichment True enrichment_changed False receipt_eq True`.
local_state_capture.py against master, hunk by hunk (300 lines before, 299 after): hunk 1 (@@ -9,7 +9,7 @@) `-from scripts.platformkit.ingame import local_state_capture_sources as src` / `+from scripts.platformkit.ingame import local_state_capture_sources as src, nba_state_enrichment`. Hunk 2 (@@ -70,8 +70,7 @@, _prune_game) `-    state['last_state'].pop(key, None)` and `-    state['last_polled'].pop(key, None)` / `+    for name in ('last_state', 'last_polled', 'last_enrichment'): state.setdefault(name, {}).pop(key, None)`.
Hunk 3 (@@ -119,7 +118,7 @@, day rollover) the reset tuple `('last_state', 'last_polled', 'mlb_games', 'sport_status', 'known_games')` gains `'last_enrichment'`. Hunk 4 (@@ -208,8 +207,8 @@, _prepare_tick) `record = _build_row(sport, item, ..., iso(now), previous)` becomes `record = nba_state_enrichment.attach_enrichment(_build_row(sport, item, ..., iso(now), previous), item, state.setdefault('last_enrichment', {}))`, still two lines. _build_row, its (status, state) comparison, recovery and receipt handling are byte-identical; the memory lives in the tick draft, so a failed commit rolls it back with the rest of the draft. The byte-identical set is now local_state_capture_io.py, live_board.py and nba_checkpoints_to_joined.py (git diff against master empty).
New tests/platformkit/ingame/test_nba_state_enrichment_archive.py (6, construct): two archived polls of an identical event carry state_enrichment with receipt_utc == response_end_utc, enrichment_changed (None, False), state_changed (None, False) and a state of exactly the five pre-S414 keys; a fouls change with an unchanged state archives enrichment_changed True, state_changed False; an NBA item and an MLB item without the block archive NO state_enrichment key and the same jsonl bytes as with attach_enrichment replaced by the identity (the pre-S414 row that S390 / S421 / S424 read).
KNOWN LIMIT (tested): the enrichment memory is NOT recovered from the archive, so after a restart or a day rollover the first enrichment_changed is None (state_changed keeps its landed recovery: False after a restart on an identical event).
GameState.extras (corrected in FIX 1d): live_state_nba.py state_from_event now gives EVERY parse_scoreboard GameState 29 extras keys, up from 7: the 10 enriched fields, their 10 _present flags, receipt_utc and enrichment_census. With no receipt passed (ingest_router, parse_scoreboard) all 10 fields are null, every _present is 0, receipt_utc is null and every census reason is missing_receipt. No consumer iterates extras (live_loop.py reads names only). Accepted by AMENDMENT 3 (e). Adoption stays ONE supervised, owner-visible relaunch before the season; landing changes nothing running.
FIX 1c run (Python 3.10.0, one file at a time, `python -m pytest <one file> -q -p no:cacheprovider`, after the last code edit): test_nba_state_enrichment.py 80; test_nba_state_enrichment_archive.py 6; landed, unedited: test_state_capture_io.py 198, test_state_capture_sources.py 240, test_local_state_capture_schedule.py 367, test_state_capture_fix_1q.py 183, test_state_capture_fix_1s.py 9, test_local_state_capture.py 19, test_state_capture_recovery.py 25, test_state_capture_commit.py 11, test_local_state_capture_differential.py 5, tests/platformkit/execution/test_forward_capture_bridge_keyed.py 34, test_baseline_four_arm.py 53, test_baseline_four_arm_eligibility.py 45, test_baseline_four_arm_nba.py 134, tests/platformkit/test_ingame_state.py 15, tests/platformkit/execution/test_paper_sizing_inputs.py 22; all passing (CONSTRUCT). test_nba_checkpoints_to_joined.py 61 pass, 4 fail (the predating failures, AMENDMENT 2 (e)). local_state_capture --help exits 0. Contract preflight over the seven owned paths plus local_state_capture.py, --base master, S414 spec: 9 PASS, 0 FAIL.
## FIX 1d (round 2: tier 1 ACCEPT, tier 2 ACCEPT WITH CORRECTIONS)
Correction 1 (name the zeroed-receipt case in the returned reasons) was NOT APPLIED in FIX 1d (ruled by AMENDMENT 4, applied in FIX 1e): it conflicts with two binding constraints of the same correction. Applied as written (append enrichment_receipt_missing when either receipt is absent, enrichment_receipt_mismatch when they differ), the unedited test_nanosecond_receipt_preserved_and_source_not_used failed: `ValueError: enrichment_receipt_mismatch` from parse_state (baseline_four_arm_features.py:175-177 raises on ANY reason), `1 failed, 79 passed`. It would also change the gate: baseline_four_arm_eligibility.py:120-142 EXCLUDES every tick with a non-empty reason list, so a zeroed-enrichment tick would stop being scored instead of scoring with zeros. The edit was reverted (80 passed again). Needs a ruling: either accept exclusion (fail-closed, one existing test line edited) or name the case outside the reasons list.
Correction 2 applied (the extras line in FIX 1c). Notes folded in: enrichment_changed compares against the last PRESENT block for the game (a tick without a block leaves the memory alone; in production every NBA row carries a block); the block is inserted before the writer-appended response_end_ts and consumers read keys by name; _prune_game uses setdefault where master indexed directly (the AMENDMENT 3 compaction). Optional test added: a forced StateWriteError leaves state['last_enrichment'] unchanged and the retry archives enrichment_changed None then True. FIX 1d run (Python 3.10.0, one file at a time, `python -m pytest <one file> -q -p no:cacheprovider`, after the last edit): test_nba_state_enrichment.py 80; test_nba_state_enrichment_archive.py 7; test_baseline_four_arm.py 53; test_baseline_four_arm_eligibility.py 45; test_baseline_four_arm_nba.py 134; test_nba_four_arm_primary_contrast.py 278; test_local_state_capture.py 19; test_state_capture_commit.py 11; test_state_capture_recovery.py 25; all passing (CONSTRUCT); no module changed in FIX 1d (only the archive test file and this memo). Contract preflight over the owned paths plus local_state_capture.py, --base master, S414 spec: 9 PASS, 0 FAIL.
## FIX 1e (AMENDMENT 4: the zeroed-enrichment case is named OUTSIDE the reasons list)
baseline_four_arm_features.py gains receipt_census(receipt, enrichment_receipt): reason enrichment_receipt_missing when the row receipt is absent or unparseable or the block receipt is absent, enrichment_receipt_mismatch when both are present and differ; a malformed, empty or non-string block receipt is counted as mismatch (the producer writes a valid string or None), else None (same per-field shape: present, absent, refused 0, reason). enriched_eligibility gates on it exactly as before (receipt_ok is unchanged in meaning) and returns it as result['enrichment_census']['receipt']; the reasons list stays empty, parse_state does not raise, the eligibility gate and every landed test are unedited. attach_enrichment writes the same entry into the archived block's enrichment_census['receipt'] (row response_end_utc against block receipt_utc). No counter exists in this row; the zeroed-tick count is recoverable from the archived block or by running receipt_census again over the corpus text (NEXT-ROW). Tests (construct, test_nba_state_enrichment_archive.py): the block receipt moved 7 s gives census enrichment_receipt_mismatch, possession_present 0, reasons []; the block receipt absent gives enrichment_receipt_missing, possession_present 0, reasons []; an archived identical-receipt row carries reason None. This row's own test_only_receipt_can_qualify_fields now sums absences over the ten fields and asserts the receipt entry (enrichment_receipt_missing). FIX 1e run (Python 3.10.0, one file at a time, `python -m pytest <one file> -q -p no:cacheprovider`, after the last edit): test_nba_state_enrichment.py 80; test_nba_state_enrichment_archive.py 9; landed, unedited: test_baseline_four_arm.py 53, test_baseline_four_arm_eligibility.py 45, test_baseline_four_arm_nba.py 134, test_nba_four_arm_primary_contrast.py 278, test_local_state_capture.py 19, test_state_capture_commit.py 11, test_state_capture_recovery.py 25, test_state_capture_io.py 198, test_state_capture_sources.py 240, test_local_state_capture_schedule.py 367, test_state_capture_fix_1q.py 183, test_state_capture_fix_1s.py 9, test_local_state_capture_differential.py 5, tests/platformkit/execution/test_forward_capture_bridge_keyed.py 34; all passing (CONSTRUCT). local_state_capture --help exits 0. Contract preflight over the owned paths plus local_state_capture.py, --base master, S414 spec: 9 PASS, 0 FAIL.
## FIX 1f
FIX 1f (orchestrator ruling; import direction): receipt_census now lives in scripts/platformkit/ingame/nba_state_enrichment.py (same signature, same entry shape) and baseline_four_arm_features.py imports it FROM there; the capture path never imports the feature / arm module. nba_state_enrichment.py imports only the standard library plus the stdlib-only shared parser scripts/platformkit/execution/venue_time.py (binding: venue times parse only through parse_venue_time); a subprocess test asserts the modules it adds are exactly the scripts package chain, venue_time and itself, and that numpy is not loaded. Pre-existing and not this row's: the landed local_state_capture_sources.py already loads numpy through domains.tennis.ingest_espn and pandas (measured with -X importtime), so the capture process holds numpy on master too.
FIX 1f run (Python 3.10.0, one file at a time, after the last edit): test_nba_state_enrichment.py 80; test_nba_state_enrichment_archive.py 10 (+1 import test); landed, unedited: test_baseline_four_arm_nba.py 134, test_local_state_capture.py 19, test_baseline_four_arm.py 53, test_baseline_four_arm_eligibility.py 45; all passing (CONSTRUCT). Contract preflight over the owned paths plus local_state_capture.py, --base master, S414 spec: 9 PASS, 0 FAIL.
## NOT VERIFIED
Real-day per-field counts: UNAVAILABLE, zero real days probed. The orchestrator alone runs the probe after the 2026-10-01 season gate; provider path availability and play-code semantics are unverified. No live archive, network, pod, scoring, corpus build, seal, charge, registry, ledger, or STOP action was performed.
No supervised relaunch or production adoption occurred. The live capture still runs its own pre-S393 worktree code: landing changes nothing running, and no real archive has carried a state_enrichment block yet. Lineup presence in feature text trusts the producer validation. Tests did not exercise real provider payloads or historical enrichment migration.
