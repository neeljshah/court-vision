# S393: state-row scheduled starts
## FIX 1o
Implements AMENDMENT 10 and AMENDMENT 11 of docs/evidence/tracking/specs/S393_spec.md (both present in this worktree). Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.
Machine: local Windows, C:/Users/neelj/nba-harness-h73, on master. Interpreter: Python 3.10.0, C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
Inputs: injected CONSTRUCT fixtures only; external video/capture paths, byte sizes and resolution: n/a. No network, commit, git metadata writes, production captures or production STOP files touched.
The required landed test's temporary STOP_STATE construct ran under pytest. Changes:
- local_state_capture_io.py:196 guards both diagnostic-failure tallies independently,
  global first; a counter/storage failure is absorbed without recursion.
- local_state_capture_io.py:206 supplies guard_diagnostics to keep every resolver
  diagnostic drop best-effort, including diagnostics from landed helpers.
- local_state_capture_sources.py:50 and :112 wrap the evidence helper and resolver;
  the landed dates resolver is unchanged.
- local_state_capture_io.py:249 hashes the WHOLE id-null failed item as JSON with
  sort_keys=True, separators=(',', ':'), default=repr; supplied ids stay supplied.
- local_state_capture.py is unchanged by FIX 1o; inherited FIX 1j-1n edits remain.
No emission-counter, schedule-selection, recovery or commit behavior was changed. Pinned both-order tests:
- test_state_capture_sources.py:238: exact tracked event() construct, all six
  discovery/poller paths, complete returned rows equal the healthy diagnostic run.
- test_local_state_capture_schedule.py:248: 24 diagnostic cases x 6 sources x 2
  orders; event/competition officialDate/localDate format and calendar failures,   timezone lookup/type errors, ambiguous/nonexistent/invalid wall time and overflow,
  invalid timestamp/fraction/infinity and numeric overflow. :263 covers MLB feed;   :280 covers the evidence helper's global diagnostic and tally failures.
- test_state_capture_io.py:252: storage, callback, source-counter, global-counter
  and both-counter failures, every sport and both orders; independent tallies.
- test_state_capture_sources.py:263: nested key reversal, distinct whole content
  and default=repr values through malformed id-null tennis competitions. Existing assertions remain except the mandated AMENDMENT 11(b) identity change.
Statement compaction preserved test ASTs; every owned file stays <=300 lines. The static diagnostic-handler check permits only the explicit nonrecursive
last-boundary continue inside _diagnostic_failed, alongside atomic staging.
## Exact before/after reproductions
Each source below was run unchanged before and after the patch as a Python one-liner: python -B -c exec(bytes.fromhex('SOURCE_HEX')).
SOURCE_HEX is the UTF-8 hex encoding of the exact displayed source block. Every shell invocation used cd C:\Users\neelj\nba-harness-h73 &&.
The tennis adapter receives the tracked event() plus fixture competitors. All outputs below are verbatim from this session.
### AMENDMENT 10
```python
from scripts.platformkit.ingame import local_state_capture_sources as s
from tests.platformkit.ingame.test_state_capture_sources import Getter,event,tennis_payload,isolation_payload
s.TENNIS_LEAGUES=('atp',)
for sport in ('nba','soccer','nfl','ncaaf','mlb','tennis'):
 for reverse in (False,True):
  records=[dict(event(),id='a',officialDate='bad'),dict(event(),id='good')]
  if sport=='tennis':
   for r in records: r['competitors']=tennis_payload()['events'][0]['groupings'][0]['competitions'][0]['competitors']
  payload=isolation_payload(sport,records[::(-1 if reverse else 1)])
  get=Getter(payload,sport);drop=get.metrics.drop
  def broken(source,reason):
   if reason=='timestamp_parse_errors': raise RuntimeError('diagnostic storage')
   drop(source,reason)
  get.metrics.drop=broken
  poll=s.mlb_discover if sport=='mlb' else s.POLLERS[sport]
  rows=poll(get,'2026-09-21');counts=get.metrics.source(sport)['drops_by_reason']
  baseline=poll(Getter(payload,sport),'2026-09-21')
  print('10',sport,reverse,[r['game_key'] for r in rows],'schedule_adapter_errors',counts['schedule_adapter_errors'],'diagnostic_write_failed',counts['diagnostic_write_failed'],'unchanged',rows==baseline)
```
Before FIX 1o:
```text
10 nba False ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 nba True ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 soccer False ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 soccer True ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 nfl False ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 nfl True ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 ncaaf False ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 ncaaf True ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 mlb False ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 mlb True ['good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 tennis False ['atp:good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
10 tennis True ['atp:good'] schedule_adapter_errors 1 diagnostic_write_failed 0 unchanged False
```
After FIX 1o:
```text
10 nba False ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 nba True ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 soccer False ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 soccer True ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 nfl False ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 nfl True ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 ncaaf False ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 ncaaf True ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 mlb False ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 mlb True ['a', 'good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 tennis False ['atp:a', 'atp:good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
10 tennis True ['atp:a', 'atp:good'] schedule_adapter_errors 0 diagnostic_write_failed 1 unchanged True
```
### AMENDMENT 11(a)
```python
from collections import Counter
from scripts.platformkit.ingame import local_state_capture_sources as s
from tests.platformkit.ingame.test_state_capture_sources import Getter,event
class Broken(Counter):
 def get(self,key,default=None):
  if key=='diagnostic_write_failed': raise RuntimeError('counting the diagnostic failure')
  return super().get(key,default)
def callback(exc): raise RuntimeError('diagnostic callback')
for reverse in (False,True):
 get=Getter({'events':[dict(event(),id='bad',venue='malformed'),dict(event(),id='good')][::(-1 if reverse else 1)]})
 get.metrics.source('nba')['drops_by_reason']=Broken()
 try: result=[r['game_key'] for r in s.nba_poll(get,'2026-09-21',callback)]
 except Exception as exc: result=type(exc).__name__+': '+str(exc)+', no result'
 print('11a',reverse,result,'global tally',get.metrics.errors['diagnostic_write_failed'])
```
Before FIX 1o:
```text
11a False RuntimeError: counting the diagnostic failure, no result global tally 1
11a True RuntimeError: counting the diagnostic failure, no result global tally 1
```
After FIX 1o:
```text
11a False ['good'] global tally 1
11a True ['good'] global tally 1
```
### AMENDMENT 11(b)
```python
from copy import deepcopy
from scripts.platformkit.ingame.local_state_capture_io import failure_identity
from tests.platformkit.ingame.test_state_capture_sources import tennis_payload
a=deepcopy(tennis_payload()['events'][0]['groupings'][0]['competitions'][0])
a.update(id=None,date={'value':'2026-09-21T20:00:00-05:00','zone':'America/Chicago'})
a['competitors'][0]['linescores']=[{'period':'bad'}]
b=deepcopy(a);b['date']=dict(reversed(list(b['date'].items())))
print('11b equal_content',a==b,'same_identity',failure_identity(a,'atp',0)==failure_identity(b,'atp',0))
```
Before FIX 1o:
```text
11b equal_content True same_identity False
```
After FIX 1o:
```text
11b equal_content True same_identity True
```
## Earlier exact reproductions
The owned companion archive is necessary to keep this memo <=300 lines: [S393_reproductions_2026-09-22.md](S393_reproductions_2026-09-22.md).
SHA-256: 2e96a5115a33af641729cc06b21200881ddcc716441499f387dbcd4b5b0d9fd0.
It preserves 22 exact source blocks as reversible source bytes with SHA-256, origin and decoding instructions, plus the original receipt tie-break invocation.
Rounds 10-13 cover the five-counter deltas, remembered starts, missing-id dedupe, feed-first selection, receipt-id tie-break, restart, and AMENDMENT 8/9 constructs.
The AMENDMENT 9 blocks and their complete historical before/after outputs remain. These are historical outputs, not new measurements; current compatibility is
verified by the pinned tests below. The 9(e) identity format is superseded by 11(b).
## Historical verification (FIX 1o)
The seven historical per-file pass counts were 355, 195, 234, 19, 5, 25 and 11 (844 total). Historical help and all nine preflight checks passed. FIX 1p results remain below.
Current FIX 1q validation supersedes those historical execution claims.
## Restored round-10 source dependency (FIX 1p; AMENDMENT 12(b))
Exact original preamble bytes, hex-wrapped; historical reproduction sources are unchanged.
BEGIN_REPRO_SOURCE
```python
exec(bytes.fromhex('66726f6d20636f707920696d706f72742064656570636f70790a66726f6d20747970657320696d706f72742053696d706c654e616d6573706163650a66726f6d20736372697074732e706c6174666f726d6b69742e696e67616d6520696d706f7274206c6f63616c5f73746174655f6361707475726520617320630a66726f6d2074657374732e706c6174666f726d6b69742e696e67616d652e746573745f6c6f63616c5f73746174655f6361707475726520696d706f7274206d616b655f636c69656e742c20526573706f6e73650a66726f6d2074657374732e706c6174666f726d6b69742e696e67616d652e746573745f73746174655f636170747572655f736f757263657320696d706f7274204765747465722c206576656e742c2074656e6e69735f7061796c6f61642c205f47554d424f5f4c4956450a66726f6d20736372697074732e706c6174666f726d6b69742e696e67616d652e6c6f63616c5f636170747572655f74696d6520696d706f72742070617273655f74730a6f726967696e616c3d632e7372632e7363686564756c650a63616c6c733d5b5d0a632e7372632e7363686564756c653d6c616d626461202a613a2063616c6c732e617070656e6428615b305d2e676574282764617465272929206f72206f726967696e616c282a61290a413d27323032362d30392d32325430313a30303a30305a270a423d27323032362d30392d32335430333a30303a30305a270a646566207469636b28726573706f6e7365732c73706f72743d276d6c62272c73746174653d4e6f6e65293a0a20636c69656e742c636c6f636b2c5f3d6d616b655f636c69656e74285b526573706f6e736528782920666f72207820696e20726573706f6e7365735d293b636c6f636b2e626173653d70617273655f74732827323032362d30392d32315432303a30303a30305a27290a2073746174653d7b7d206966207374617465206973204e6f6e6520656c73652073746174650a20726f77732c5f2c5f3d632e5f707265706172655f7469636b28636c69656e742c5b73706f72745d2c636c6f636b2e75746328292c73746174652c636c6f636b2e6d6f6e6f746f6e69632c53696d706c654e616d657370616365287265636f7665725f7374617465733d6c616d626461202a613a7b7d29290a20643d636c69656e742e6d6574726963732e736f757263652873706f7274295b2764726f70735f62795f726561736f6e275d0a2072657475726e20726f77732c73746174652c5b645b277363686564756c65645f73746172745f272b6b5d20666f72206b20696e202827756e617661696c61626c65272c277061727469616c272c2773757065727365646564272c27636f6e666c6963747327295d2c636c69656e742c636c6f636b0a64656620646973632873746172743d412c7374617475733d274c69766527293a0a2072657475726e207b276461746573273a5b7b2764617465273a27323032362d30392d3231272c2767616d6573273a5b7b2767616d65506b273a312c2767616d6544617465273a73746172742c27737461747573273a7b27616273747261637447616d655374617465273a7374617475737d7d5d7d5d7d0a6465662066656564287374617274293a0a20663d64656570636f7079285f47554d424f5f4c495645293b665b2767616d6544617461275d5b276461746574696d65275d5b276461746554696d65275d3d73746172743b72657475726e20660a'))
for label,start in (): pass
```
END_REPRO_SOURCE
## FIX 1p -- AMENDMENTS 12-13 (local constructs)
Interpreter: C:\Users\neelj\AppData\Local\Programs\Python\Python310\python.exe, Python 3.10.0.
12(a): local_state_capture.py:140 routes capture errors through src.report; io.py:229 guards write-error reporting too.
Every drop call in the three owned modules is enumerated by test_state_capture_io.py:16; only two guarded leaves remain.
12(b): the restored preamble above closes all six deleted dependencies; original archive sources/output seals remain unchanged.
test_state_capture_io.py:5 executes three seeded-order archived sources in both orders, comparing stdout bytes exactly.
The selected round-10 event 37 depends on this restored preamble, so deleting it fails the pinned test.
13(a): io.py:255 tags and renders keys before sorting; io.py:265 isolates all serialization and uses a named positional fallback.
13(b): canonical nodes include fully qualified types; Decimal/string, datetime/ISO and equal-repr classes differ.
Nested reordered content stays equal; mixed-key and unrenderable-repr tests run both orders (test_state_capture_sources.py:273).
Exact one-liners and verbatim before/after stdout: [FIX 1p reproductions](S393_reproductions_2026-09-22.md#fix-1p-exact-beforeafter-reproductions).
12(a) n=12 CONSTRUCT: six sports x both orders, RuntimeError/zero appends/zero failures before; one peer append/one diagnostic failure after.
12(b) n=6 CONSTRUCT: IndexError before; all exit 0 after. Three unchanged historical outputs also match byte-for-byte.
13(a) n=2 CONSTRUCT: TypeError and {} before; ['good'] with event_adapter_errors 1 after; unrenderable input uses a named position.
13(b) n=2 CONSTRUCT: same_identity True before; same_identity False after.
Earlier resolver, raising-counter, restart, five-counter, feed-first, receipt tie and remembered-start closures remain covered.
Each following file ran separately with python -B -m pytest tests/platformkit/ingame/<file> -q -p no:cacheprovider:
```text
test_local_state_capture_schedule.py: 367 passed in 2.48s
test_state_capture_io.py: 198 passed in 8.20s
test_state_capture_sources.py: 240 passed in 1.64s
test_local_state_capture.py: 19 passed in 0.98s
test_local_state_capture_differential.py: 5 passed in 8.18s
test_state_capture_recovery.py: 25 passed in 0.95s
test_state_capture_commit.py: 11 passed in 0.96s
```
python -B -m scripts.platformkit.ingame.local_state_capture --help: exit 0. Contract preflight --paths (all eight owned files) --base master --spec docs/evidence/tracking/specs/S393_spec.md; FAIL=0:
```text
PASS vocab clean over 8 files
PASS crlf no index-side CRLF over 8 file(s); 3 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```
LOC: capture 299; sources 300; io 289; tests io/sources/schedule 300/300/300; memo 289; archive 281.
Only owned paths appear in git diff HEAD --stat and git status --porcelain (same eight paths listed above).
No commit, network, capture-cache access or capture STOP operation. Landed commit, dates resolver and S401 tests untouched.
NOT VERIFIED below retains the excluded gaps; historical round-10 outputs altered by earlier fixes remain labelled historical.
## FIX 1q -- both round-16 verdicts, AMENDMENT 14
Local constructs only, in C:/Users/neelj/nba-harness-h73; no external input. Tier 1 #1 / Tier 2 dedupe BLOCKING: sources.unique_games prepares receipt and semantic
keys inside isolate_game, sorts successful preparations only, and names failures by game. Mixed-key-safe typed serialization now applies to receipt keys as well as semantic keys.
Tier 1 #2 / Tier 2 identity BLOCKING: canonicalization recurses through dict/list/tuple/set/ frozenset keys and values; container tags remain. Full class inheritance tags distinguish
factory-created equal-name classes where the second inherits the first's identical repr. Indistinguishable same-base factory classes refuse fingerprinting with counted positional fallbacks.
Tier 2 commit BLOCKING: capture passes the same guarded metrics adapter at all three commit/heartbeat boundaries. The landed helper is unchanged. The diagnostic inventory now
includes commit and dates helpers; a separate test pins guards at every owned call boundary. Guarded source entries retain last_write_error locally when diagnostic storage refuses its write.
Tier 1 #3 / Tier 2 archive CORRECTION: refreshed the seal above after archive finalization. The archive carries an executable wrapper containing the exact historical dependency;
all six original sources remain unchanged and run with the memo pathname unavailable. Regression file: tests/platformkit/ingame/test_state_capture_fix_1q.py; both orders throughout.
Verbatim before output examples (the same failure held for every stated construct):
```text
nba False TypeError: '<' not supported between instances of 'str' and 'int' {}
exact-null False TypeError: '<' not supported between instances of 'str' and 'int' {}
a == b: True same_identity: False
class/container same_identity: True
nba False append RuntimeError: diagnostic storage diagnostic_write_failed 0 heartbeats 0
```
Dedupe: n=12 CONSTRUCT (six helpers x two orders), plus both exact id-null NBA inputs. Identity: the exact nested-tuple pair and factory subclass values/tuple keys/frozenset keys.
Commit: n=72 CONSTRUCT (six sports x two orders x three writer failures x drop/storage failure). Archive before: all six sources raised FileNotFoundError on the hard-coded memo pathname.
Seal before: recorded 82502a9c... versus current 7b91941f...; matches: False. Additional before: same-base classes gave same_identity True; storage raised RuntimeError with count 0.
After: position:0/1:identity_serialization_errors; storage failures counted 2/3/1, writer error retained. Exact current reproduction entry points (the functions contain the complete fixture sources):
```python
from tests.platformkit.ingame.test_state_capture_fix_1q import *
for sport in SPORTS:
 for reverse in (False, True):
  rows, metrics = mixed_key_construct(sport, reverse)
  print(sport, reverse, [r['game_key'] for r in rows], dict(metrics.errors))
  for phase in PHASES:
   error, metrics, heartbeats, rows, state = commit_diagnostic_construct(sport, reverse, phase)
   print(sport, reverse, phase, error, metrics.errors['diagnostic_write_failed'], len(heartbeats))
for reverse in (False, True):
 test_exact_id_null_nba_mixed_key_reproduction(reverse)
 test_exact_nested_tuple_identity_equality(reverse)
 for container in ('value', 'tuple_key', 'frozenset_key', 'set', 'nested_key'):
  test_same_qualified_name_subclass_is_distinct_inside_keys_and_values(reverse, container)
```
After: every helper returns both valid games in stable order; the id-null case counts one missing_game_id. Unrenderable receipt/semantic keys drop only that item and count its identity.
Nested tuples compare equal; the three formerly colliding class/container pairs are distinct. Commit after: StateWriteError retains the writer cause, diagnostic_write_failed is 1 for
append/heartbeat and 2 for sync (writer plus sport). Append/sync write one failed heartbeat. Archive after: six exit 0 with identical current outputs and the patched reader restored;
event 37 also matches its historical bytes. No universal historical byte-equality claim. Intermediate checks: 12 assertions included reordered raw envelopes; corrected to compare emitted fields.
An intermediate non-finite rejection was corrected to preserve the resolver's counted null schedule.
Final per-file CONSTRUCT tests, each python -m pytest tests/platformkit/ingame/FILE -q -p no:cacheprovider: local_state_capture_schedule 367; state_capture_io 198; state_capture_sources 240;
local_state_capture 19; local_state_capture_differential 5; state_capture_recovery 25; state_capture_commit 11; state_capture_fix_1q 154. Total: 1019 passed.
Writable TEMP/TMP: .tmp_s393_1q inside this worktree. No setup errors in the final sequence. Verbatim after examples:
```text
nba False ['bad', 'good'] {}
a == b: True same_identity: True
class/container same_identity: False
nba False append StateWriteError: state append failed for nba: writer append diagnostic_write_failed 1 heartbeats 1
```
CLI --help exited 0; no separate self-check option exists. Final preflight: 9 PASS, 0 FAIL over the nine owned files.
## FIX 1r -- round-17 verdicts, AMENDMENT 16 (CONSTRUCT, local only)
Tier 2 identity BLOCKINGs: _canonical dispatches containers by isinstance (subclasses recurse, tag = concrete
module.qualname); any class whose module import + qualname getattr chain is not that very class refuses under
identity_unresolvable_class with a counted positional surrogate. Tier 1 CORRECTION: TEMP/TMP = .tmp_s393_1r.
Before (archived block "FIX 1r exact before/after reproductions", source SHA256 1f0209ae..., both orders):
```text
factory False same_identity True counts {}
L False equal_content True same_identity False
D_key False equal_content True same_identity False
```
After (same source re-executed at finish): factory same_identity False, counts {'identity_unresolvable_class': 2},
identities position:0/1:identity_unresolvable_class; L, D, D_key same_identity True; both orders.
Regression tests (test_state_capture_fix_1q.py): factory pair, local/missing-module/rebound refusals, adapter peer kept,
L/D/T/S/F subclass reorder, module-level class vs module-level subclass distinct. Final per-file runs (Python 3.10.0):
schedule 367; io 198; sources 240; local_state_capture 19; differential 5; recovery 25; commit 11; fix_1q 183 (1048).
CLI --help exit 0; preflight 9 PASS, 0 FAIL. Archive seal above equals current archive bytes.
## FIX 1s -- round-18 verdicts, AMENDMENT 17 (CONSTRUCT, local only)
Tier 1 #1 / 17(1) CORRECTION: failure_identity(item, league, position, id_field="id", get=None, source=None) reports through
report(get, source or league, reason) (io.py:287); all five sources.py call sites pass the getter: :89, :147, :216,
:239 (source="tennis") and :293 (source=source, i.e. 'nfl' / 'ncaaf'). Landed convention, quoted from io.py report():
`metrics = getattr(get, "metrics", SOURCE_METRICS)` then `metrics.drop(getattr(get, "source", source), reason)` -- the count
lands in the getter's own Metrics under the getter's source key, else under the passed sport key; tennis under 'tennis'.
Tier 2 #1 / 17(2) CORRECTION: io.py:271 sorts dict entries by (canonical key text, canonical value text).
Before (archived block "FIX 1s exact before/after reproductions", source SHA256 561721e1..., excerpt; both orders identical):
```text
nba False rows ['good'] client_errors None client_drops None global_delta 2
tennis False rows [] client_errors None client_drops None global_delta 2
dict_keys equal True same_identity False
```
After (same source, fix 1s modules): nba / ncaaf / tennis x both orders give client_errors 2, client_drops 2, global_delta 0;
dict_keys same_identity True. The archived after stdout re-executes byte-identical.
Regression file tests/platformkit/ingame/test_state_capture_fix_1s.py (new, 9 tests; fix_1q is near the cap): routing for
nba / ncaaf / tennis x both orders through a getter with no source attribute, asserted on get.metrics with the global
SOURCE_METRICS unchanged; serialization refusal on get.metrics; same-canonical-key reorder. All 9 fail on the pre-fix modules.
fix_1q's factory-refusal test now passes get=get and no longer monkeypatches io.SOURCE_METRICS.
Final per-file runs (Python 3.10.0; TEMP/TMP = .tmp_s393_1s): schedule 367; io 198; sources 240; local_state_capture 19;
differential 5; recovery 25; commit 11; market_link 23; fix_1q 183; fix_1s 9 (1080).
CLI --help exit 0; preflight 9 PASS, 0 FAIL over the ten owned files. Archive seal above equals current archive bytes.
Layout only: memo prose lines outside code blocks were rejoined (no words changed) and the archive's two NOT VERIFIED bullets joined, to stay <= 300 lines.
## NOT VERIFIED
- Real feeds, production captures, running services, rollout and network behavior.
- S407: rollover terminal-state and remembered-schedule recovery gaps.
- S408: cross-identity reconciliation when upstream game ids change.
- Broader competition-shape changes (missing/duplicate competitions, walkover/retired).
- AMENDMENT 17 notes, not changed: a module raising anything but ImportError in the resolvability import counts identity_serialization_errors, and the import may run module top-level code;
  a __main__ class resolves to '__main__.X' (two entry scripts could share it); two instances of one resolvable class with one repr but different attributes share an identity (13(b)).
- Tennis construct: a valid competition whose event holds a sibling with an unresolvable object drops as schedule_adapter_errors (its _start embeds the event groupings); non-JSON inputs only.
- Production StateClient routing and heartbeat rendering of the identity counters (constructs use test getters).
